"""LLM factory — universal caller supporting multiple providers.

Supported providers:
  openai           — OpenAI API (GPT-4o, etc.)
  anthropic_oauth  — Claude via claude CLI subprocess (free for OAuth users)
  claude_oauth     — Alias for anthropic_oauth
  anthropic        — Anthropic API (requires ANTHROPIC_API_KEY)
  local            — Ollama local model server
"""
import os
import subprocess


def call_llm(
    prompt: str,
    system: str = "",
    provider: str = "openai",
    model: str = "gpt-4o",
    temperature: float | None = None,
    **kwargs,
) -> str:
    """Universal LLM caller supporting multiple providers.

    Args:
        prompt:      User message
        system:      System prompt (optional)
        provider:    openai | anthropic_oauth | claude_oauth | anthropic | local
        model:       Model identifier (provider-specific)
        temperature: Sampling temperature (None = provider default).
                     같은 벤더 다양성 강제 시 A=0.3(정밀), B=1.1(창의) 로 사용.
        **kwargs:    Extra args forwarded to the underlying caller

    Returns:
        Response text string
    """
    if provider == "openai":
        return _call_openai(prompt, system, model, temperature=temperature, **kwargs)
    elif provider in ("anthropic_oauth", "claude_oauth"):
        return _call_claude_oauth(prompt, system)          # OAuth는 temp 미지원
    elif provider == "anthropic":
        return _call_anthropic(prompt, system, model, temperature=temperature)
    elif provider == "local":
        return _call_ollama(prompt, system, model, temperature=temperature)
    else:
        raise ValueError(f"알 수 없는 provider: {provider}")


def _call_openai(prompt: str, system: str, model: str, temperature: float | None = None, **kwargs) -> str:
    import openai

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    req: dict = {"model": model, "messages": messages}
    if temperature is not None:
        req["temperature"] = temperature

    # gpt-5.x / o-series: reasoning_effort 지원
    if model.startswith("gpt-5") or model.startswith("o"):
        reasoning_effort = kwargs.get("reasoning_effort") or os.environ.get("OPENAI_REASONING_EFFORT")
        if reasoning_effort:
            req["reasoning_effort"] = reasoning_effort

    # 기타 확장 옵션 전달 (None 제외)
    for k, v in kwargs.items():
        if v is not None and k != "reasoning_effort":
            req[k] = v

    resp = client.chat.completions.create(**req)
    return resp.choices[0].message.content


class OAuthNotAvailableError(Exception):
    """Claude OAuth CLI not logged in or unavailable."""


def _call_claude_oauth(prompt: str, system: str) -> str:
    """Call Claude via claude CLI subprocess (free for OAuth users).

    Raises OAuthNotAvailableError if not logged in, so callers can fallback.
    """
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    full_prompt = f"{system}\n\n{prompt}" if system else prompt

    # Strip Claude Code session vars that block nested invocations
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS")
    }
    env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token

    result = subprocess.run(
        ["claude", "-p", "--dangerously-skip-permissions", full_prompt],
        capture_output=True,
        text=True,
        timeout=90,
        env=env,
    )
    output = result.stdout.strip()

    # 미로그인 / 인증 실패 감지
    _auth_errors = ("not logged in", "please run /login", "authentication", "unauthorized")
    if any(e in output.lower() for e in _auth_errors) or result.returncode != 0:
        raise OAuthNotAvailableError(f"Claude OAuth unavailable: {output[:120]}")

    return output


def _call_anthropic(prompt: str, system: str, model: str, temperature: float | None = None) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    kw: dict = {}
    if system:
        kw["system"] = system
    if temperature is not None:
        kw["temperature"] = temperature

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        **kw,
    )
    return response.content[0].text


def _call_ollama(prompt: str, system: str, model: str, temperature: float | None = None) -> str:
    import httpx

    body: dict = {
        "model": model,
        "prompt": f"{system}\n\n{prompt}" if system else prompt,
        "stream": False,
    }
    if temperature is not None:
        body["options"] = {"temperature": temperature}

    response = httpx.post("http://localhost:11434/api/generate", json=body, timeout=120)
    response.raise_for_status()
    return response.json()["response"]


def call_llm_with_tools(
    prompt: str,
    system: str = "",
    provider: str = "openai",
    model: str = "gpt-4o",
    temperature: float | None = None,
    max_turns: int = 6,
    **kwargs,
) -> str:
    """Tool-calling 루프를 포함한 LLM 호출 (OpenAI 전용).

    LLM이 tool_calls를 반환하면 자동으로 실행하고 결과를 다시 LLM에 전달.
    최대 max_turns 반복 후 최종 텍스트 응답 반환.

    Args:
        prompt:     User message
        system:     System prompt
        provider:   현재 openai만 지원 (anthropic_oauth는 fallback으로 call_llm 사용)
        model:      OpenAI 모델명
        temperature: 샘플링 온도
        max_turns:  최대 tool-call 반복 횟수 (무한루프 방지)
        **kwargs:   reasoning_effort 등 추가 옵션

    Returns:
        최종 텍스트 응답
    """
    if provider != "openai":
        # anthropic_oauth 등은 tool-calling 미지원 → 일반 호출로 fallback
        return call_llm(prompt, system=system, provider=provider, model=model,
                        temperature=temperature, **kwargs)

    import openai
    import json
    from amp.core.tool_runtime import TOOL_SCHEMAS, dispatch

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    req_base: dict = {"model": model, "tools": TOOL_SCHEMAS, "tool_choice": "auto"}
    if temperature is not None:
        req_base["temperature"] = temperature
    if model.startswith("gpt-5") or model.startswith("o"):
        reasoning_effort = kwargs.get("reasoning_effort") or os.environ.get("OPENAI_REASONING_EFFORT")
        if reasoning_effort:
            req_base["reasoning_effort"] = reasoning_effort

    for turn in range(max_turns):
        resp = client.chat.completions.create(messages=messages, **req_base)
        msg = resp.choices[0].message

        # tool_calls가 없으면 최종 응답
        if not msg.tool_calls:
            return msg.content or ""

        # tool_calls 실행
        messages.append(msg)  # assistant message (with tool_calls)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = dispatch(tc.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    # max_turns 초과 시 마지막 응답 반환
    return msg.content or "[tool-calling max_turns 초과]"
