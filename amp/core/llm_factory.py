"""LLM factory — universal caller supporting multiple providers.

Supported providers:
  openai           — OpenAI API key (OPENAI_API_KEY)
  openai_oauth     — OpenAI via Codex CLI OAuth (~/.codex/auth.json, 무료)
  anthropic        — Anthropic API key (ANTHROPIC_API_KEY)
  anthropic_oauth  — Claude via claude CLI OAuth (~/.claude/oauth-token, 무료)
  claude_oauth     — Alias for anthropic_oauth
  local            — Ollama local model server

최신 모델 (2026-03 기준):
  OpenAI:    gpt-5.4 / gpt-5.4-pro (최신), gpt-5.2, gpt-5.3-codex
             reasoning_effort: none | low | medium | high | xhigh
  Anthropic: claude-opus-4-6 (최상위), claude-sonnet-4-6, claude-haiku-4-5
             extended_thinking: enabled (budget_tokens) | adaptive | disabled

모델 자동탐지: list_available_models(provider) 함수 사용
"""
import json
import os
import subprocess


def call_llm(
    prompt: str,
    system: str = "",
    provider: str = "openai",
    model: str = "gpt-5.2",
    temperature: float | None = None,
    **kwargs,
) -> str:
    """Universal LLM caller supporting multiple providers.

    Args:
        prompt:           User message
        system:           System prompt (optional)
        provider:         openai | anthropic_oauth | claude_oauth | anthropic | local
        model:            Model identifier (provider-specific)
        temperature:      Sampling temperature (None = provider default)
        **kwargs:
          reasoning_effort  — OpenAI GPT-5.x/o-series: none|low|medium|high|xhigh
          thinking          — Claude: {"type": "enabled"|"adaptive", "budget_tokens": N}
                              또는 True (자동 adaptive), False (비활성화)

    Returns:
        Response text string
    """
    if provider == "openai":
        return _call_openai(prompt, system, model, temperature=temperature, **kwargs)
    elif provider == "openai_oauth":
        # Codex CLI OAuth 토큰 사용 (ChatGPT Plus/Pro 구독자 무료)
        return _call_openai_oauth(prompt, system, model or "gpt-5.4", temperature=temperature, **kwargs)
    elif provider in ("anthropic_oauth", "claude_oauth"):
        # ANTHROPIC_API_KEY 있으면 API 직접 호출 (subprocess 대비 3~10배 빠름)
        if os.environ.get("ANTHROPIC_API_KEY"):
            return _call_anthropic(prompt, system, model or "claude-sonnet-4-6",
                                   temperature=temperature, **kwargs)
        return _call_claude_oauth(prompt, system)          # OAuth는 temp/thinking 미지원
    elif provider == "anthropic":
        return _call_anthropic(prompt, system, model, temperature=temperature, **kwargs)
    elif provider == "local":
        return _call_ollama(prompt, system, model, temperature=temperature)
    else:
        raise ValueError(f"알 수 없는 provider: {provider}")


# ── OpenAI ────────────────────────────────────────────────────────

def _call_openai(prompt: str, system: str, model: str, temperature: float | None = None, **kwargs) -> str:
    import openai

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    req: dict = {"model": model, "messages": messages}

    # temperature: reasoning 모델(gpt-5.x, o-series)은 temperature 미지원
    _is_reasoning = model.startswith("gpt-5") or model.startswith("o")
    if temperature is not None and not _is_reasoning:
        req["temperature"] = temperature

    # reasoning_effort: gpt-5.x / o-series 전용
    # 범위: none | low | medium | high | xhigh
    if _is_reasoning:
        reasoning_effort = (
            kwargs.get("reasoning_effort")
            or os.environ.get("OPENAI_REASONING_EFFORT")
        )
        if reasoning_effort and reasoning_effort != "none":
            req["reasoning_effort"] = reasoning_effort

    # 기타 확장 옵션 (None 제외, 이미 처리된 키 제외)
    _handled = {"reasoning_effort", "thinking"}
    for k, v in kwargs.items():
        if k not in _handled and v is not None:
            req[k] = v

    resp = client.chat.completions.create(**req)
    return resp.choices[0].message.content


# ── OpenAI OAuth (Codex CLI 토큰, 무료) ──────────────────────────

def _load_codex_token() -> str | None:
    """~/.codex/auth.json 에서 OAuth 토큰 로드."""
    auth_path = os.path.expanduser("~/.codex/auth.json")
    if not os.path.exists(auth_path):
        return None
    try:
        with open(auth_path) as f:
            data = json.load(f)
        # API 키 모드: auth_mode == "apikey"
        if data.get("auth_mode") == "apikey":
            return data.get("OPENAI_API_KEY")
        # OAuth 모드: access_token
        return data.get("access_token") or data.get("token")
    except Exception:
        return None


class OpenAIOAuthNotAvailableError(Exception):
    """Codex CLI not logged in or unavailable."""


def _call_openai_oauth(
    prompt: str, system: str, model: str,
    temperature: float | None = None, **kwargs
) -> str:
    """OpenAI Codex CLI OAuth를 통한 호출.

    ChatGPT Plus/Pro 구독자라면 API 비용 없이 GPT-5.x 사용 가능.
    토큰: ~/.codex/auth.json (codex login --device-auth 로 획득)

    Raises OpenAIOAuthNotAvailableError if not logged in.
    """
    token = _load_codex_token()
    if not token:
        raise OpenAIOAuthNotAvailableError(
            "Codex OAuth 토큰 없음. 'codex login --device-auth' 또는 "
            "'amp login --provider openai' 로 로그인하세요."
        )

    import openai
    client = openai.OpenAI(api_key=token)
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    _is_reasoning = model.startswith("gpt-5") or model.startswith("o")
    req: dict = {"model": model, "messages": messages}
    if temperature is not None and not _is_reasoning:
        req["temperature"] = temperature
    if _is_reasoning:
        reasoning_effort = kwargs.get("reasoning_effort") or os.environ.get("OPENAI_REASONING_EFFORT")
        if reasoning_effort and reasoning_effort != "none":
            req["reasoning_effort"] = reasoning_effort

    try:
        resp = client.chat.completions.create(**req)
        return resp.choices[0].message.content
    except Exception as e:
        raise OpenAIOAuthNotAvailableError(f"Codex OAuth 호출 실패: {e}") from e


# ── 모델 자동 탐지 ─────────────────────────────────────────────────

def list_available_models(provider: str = "openai", api_key: str | None = None) -> list[str]:
    """API에서 사용 가능한 최신 모델 목록 반환.

    Args:
        provider: openai | openai_oauth | anthropic
        api_key:  API 키 (None이면 환경변수/OAuth 자동 사용)

    Returns:
        모델 ID 리스트 (최신순 정렬)
    """
    if provider in ("openai", "openai_oauth"):
        key = api_key or os.environ.get("OPENAI_API_KEY") or _load_codex_token()
        if not key:
            return ["gpt-5.4", "gpt-5.4-pro", "gpt-5.2", "gpt-5.1"]  # 하드코딩 fallback
        try:
            import openai
            client = openai.OpenAI(api_key=key)
            models = client.models.list()
            # GPT-5.x + o-series만 필터링, 최신순
            gpt5 = sorted(
                [m.id for m in models.data if "gpt-5" in m.id],
                reverse=True
            )
            oseries = sorted(
                [m.id for m in models.data if m.id.startswith("o") and m.id[1:2].isdigit()],
                reverse=True
            )
            return gpt5 + oseries
        except Exception:
            return ["gpt-5.4", "gpt-5.4-pro", "gpt-5.2", "gpt-5.1"]

    elif provider == "anthropic":
        # Anthropic는 모델 목록 API 없음 → 하드코딩 (공식 최신 순)
        return [
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
        ]

    return []


def recommend_model(provider: str = "openai") -> str:
    """현재 사용 가능한 최신 권장 모델 반환."""
    models = list_available_models(provider)
    if not models:
        return "gpt-5.4" if "openai" in provider else "claude-sonnet-4-6"
    # pro/max 제외하고 기본 최신 모델 우선 (비용 고려)
    for m in models:
        if "gpt-5" in m and "pro" not in m and "codex" not in m and "chat" not in m:
            return m
    return models[0]


# ── Claude OAuth (subprocess, 무료) ───────────────────────────────

class OAuthNotAvailableError(Exception):
    """Claude OAuth CLI not logged in or unavailable."""


def _call_claude_oauth(prompt: str, system: str) -> str:
    """Call Claude via claude CLI subprocess (free for OAuth users).

    ⚠️ extended_thinking / temperature 미지원 (CLI 제한).
    고급 옵션이 필요하면 anthropic provider 사용.

    Raises OAuthNotAvailableError if not logged in.
    """
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    full_prompt = f"{system}\n\n{prompt}" if system else prompt

    # Claude Code 세션 중첩 방지 변수 제거
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS")
    }
    env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token

    import shutil
    claude_bin = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")

    result = subprocess.run(
        [claude_bin, "-p", "--dangerously-skip-permissions", full_prompt],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    output = result.stdout.strip()

    _auth_errors = ("not logged in", "please run /login", "authentication", "unauthorized")
    if any(e in output.lower() for e in _auth_errors) or result.returncode != 0:
        raise OAuthNotAvailableError(f"Claude OAuth unavailable: {output[:120]}")

    return output


# ── Anthropic API (유료, extended_thinking 지원) ──────────────────

# extended_thinking을 지원하는 모델 목록
_THINKING_MODELS = {
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
}

def _build_thinking_param(thinking_kwarg, model: str) -> dict | None:
    """
    thinking kwargs → Anthropic API thinking 파라미터 변환.

    kwargs 형식:
      thinking=True                        → adaptive (자동 결정, 권장)
      thinking="adaptive"                  → adaptive
      thinking="enabled"                   → enabled, budget_tokens=8000 (기본)
      thinking={"type":"enabled","budget_tokens":16000}  → 직접 지정
      thinking=False or thinking="disabled" → None (비활성)

    adaptive thinking: 모델이 스스로 "생각할지" 결정 → 비용 효율적
    enabled thinking:  항상 생각 → 더 깊은 추론, 비용 ↑
    """
    if model not in _THINKING_MODELS:
        return None
    if thinking_kwarg is None or thinking_kwarg is False or thinking_kwarg == "disabled":
        return None

    if thinking_kwarg is True or thinking_kwarg == "adaptive":
        return {"type": "adaptive"}
    if thinking_kwarg == "enabled":
        return {"type": "enabled", "budget_tokens": 8000}
    if isinstance(thinking_kwarg, dict):
        return thinking_kwarg  # 직접 지정
    return None


def _call_anthropic(
    prompt: str,
    system: str,
    model: str,
    temperature: float | None = None,
    **kwargs,
) -> str:
    """
    Anthropic API 호출.

    지원 옵션:
      thinking — extended_thinking / adaptive_thinking
               True/"adaptive" → adaptive (권장, 비용 효율)
               "enabled"       → always-on thinking
               {"type":...}    → 직접 지정
    """
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # thinking 파라미터 처리
    thinking_kwarg = kwargs.get("thinking")
    thinking_param = _build_thinking_param(thinking_kwarg, model)

    kw: dict = {}
    if system:
        kw["system"] = system

    # thinking 활성화 시 temperature 고정 (API 요구사항)
    if thinking_param:
        kw["thinking"] = thinking_param
        # thinking 사용 시 max_tokens 증가 (thinking 토큰 포함)
        max_tokens = 16000
    else:
        if temperature is not None:
            kw["temperature"] = temperature
        max_tokens = 4096

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        **kw,
    )

    # thinking block과 text block 분리하여 text만 반환
    text_blocks = [
        block.text
        for block in response.content
        if block.type == "text"
    ]
    return "\n".join(text_blocks) if text_blocks else ""


# ── Ollama (로컬) ─────────────────────────────────────────────────

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


# ── Tool-calling 루프 (OpenAI 전용) ──────────────────────────────

def call_llm_with_tools(
    prompt: str,
    system: str = "",
    provider: str = "openai",
    model: str = "gpt-5.2",
    temperature: float | None = None,
    max_turns: int = 6,
    **kwargs,
) -> str:
    """Tool-calling 루프 포함 LLM 호출 (OpenAI 전용).

    LLM이 tool_calls를 반환하면 자동 실행 후 다시 LLM에 전달.
    최대 max_turns 반복 후 최종 텍스트 응답 반환.

    kwargs:
      reasoning_effort — OpenAI GPT-5.x: none|low|medium|high|xhigh
    """
    if provider != "openai":
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

    _is_reasoning = model.startswith("gpt-5") or model.startswith("o")
    req_base: dict = {"model": model, "tools": TOOL_SCHEMAS, "tool_choice": "auto"}
    if temperature is not None and not _is_reasoning:
        req_base["temperature"] = temperature
    if _is_reasoning:
        reasoning_effort = kwargs.get("reasoning_effort") or os.environ.get("OPENAI_REASONING_EFFORT")
        if reasoning_effort and reasoning_effort != "none":
            req_base["reasoning_effort"] = reasoning_effort

    for _ in range(max_turns):
        resp = client.chat.completions.create(messages=messages, **req_base)
        msg = resp.choices[0].message

        if not msg.tool_calls:
            return msg.content or ""

        messages.append(msg)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = dispatch(tc.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return msg.content or "[tool-calling max_turns 초과]"
