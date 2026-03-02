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
        return _call_openai(prompt, system, model, temperature=temperature)
    elif provider in ("anthropic_oauth", "claude_oauth"):
        return _call_claude_oauth(prompt, system)          # OAuth는 temp 미지원
    elif provider == "anthropic":
        return _call_anthropic(prompt, system, model, temperature=temperature)
    elif provider == "local":
        return _call_ollama(prompt, system, model, temperature=temperature)
    else:
        raise ValueError(f"알 수 없는 provider: {provider}")


def _call_openai(prompt: str, system: str, model: str, temperature: float | None = None) -> str:
    import openai

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs: dict = {"model": model, "messages": messages}
    if temperature is not None:
        kwargs["temperature"] = temperature
    # gpt-5.x는 max_completion_tokens 사용
    if model.startswith("gpt-5") or model.startswith("o"):
        resp = client.chat.completions.create(**kwargs)
    else:
        resp = client.chat.completions.create(**kwargs)
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
