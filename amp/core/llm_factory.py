"""LLM factory — universal caller supporting multiple providers.

Supported providers:
  openai           — OpenAI API key (OPENAI_API_KEY)
  openai_oauth     — OpenAI via Codex CLI OAuth (~/.codex/auth.json, 무료)
  anthropic        — Anthropic API key (ANTHROPIC_API_KEY)
  anthropic_oauth  — Claude via claude CLI OAuth (~/.claude/oauth-token, 무료)
  claude_oauth     — Alias for anthropic_oauth
  gemini           — Google Gemini API key (GEMINI_API_KEY / GOOGLE_API_KEY)
  deepseek         — DeepSeek API key (DEEPSEEK_API_KEY, OpenAI-호환)
  zhipu / glm      — ZhiPu GLM API key (ZHIPUAI_API_KEY)
  xai / grok       — xAI Grok API key (XAI_API_KEY, OpenAI-호환)
  mistral          — Mistral AI API key (MISTRAL_API_KEY, OpenAI-호환)
  local            — Ollama local model server

최신 모델 (2026-03 기준):
  OpenAI:    gpt-5.4 / gpt-5.4-pro (최신), gpt-5.2, gpt-5.3-codex
             reasoning_effort: none | low | medium | high | xhigh
  Anthropic: claude-opus-4-6 (최상위), claude-sonnet-4-6, claude-haiku-4-5
             extended_thinking: enabled (budget_tokens) | adaptive | disabled
  Gemini:    gemini-2.5-pro (최상위), gemini-2.5-flash (빠름)
             thinking_budget: int 토큰 수 (0=비활성)
  DeepSeek:  deepseek-chat (V3.2 non-thinking), deepseek-reasoner (V3.2 thinking/R1)
  ZhiPu GLM: glm-5 (744B MoE, 2026.02 최신), glm-4.6 (355B/32B active), glm-4-plus
  xAI:       grok-4-0709 (최신, 256k), grok-4-fast-reasoning (2M ctx), grok-3, grok-3-mini
  Mistral:   mistral-large-3 (41B active/675B MoE, 최신), mistral-large-2, ministral-8b

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
        provider:         openai | anthropic_oauth | claude_oauth | anthropic |
                          gemini | deepseek | zhipu | glm | xai | grok | mistral | local
        model:            Model identifier (provider-specific)
        temperature:      Sampling temperature (None = provider default)
        **kwargs:
          reasoning_effort  — OpenAI GPT-5.x/o-series: none|low|medium|high|xhigh
          thinking          — Claude: {"type": "enabled"|"adaptive", "budget_tokens": N}
                              또는 True (자동 adaptive), False (비활성화)
          thinking_budget   — Gemini 2.5+: int 토큰 수 (0=비활성, 기본 없음)
          max_tokens        — DeepSeek: 최대 출력 토큰 (기본 4096)

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
        return _call_claude_oauth(prompt, system, model=model)  # OAuth는 temp/thinking 미지원
    elif provider == "anthropic":
        return _call_anthropic(prompt, system, model, temperature=temperature, **kwargs)
    elif provider == "gemini":
        return _call_gemini(prompt, system, model or "gemini-2.5-flash", temperature=temperature, **kwargs)
    elif provider == "deepseek":
        return _call_deepseek(prompt, system, model or "deepseek-chat", temperature=temperature, **kwargs)
    elif provider in ("zhipu", "glm"):
        return _call_zhipu(prompt, system, model or "glm-4-plus", temperature=temperature, **kwargs)
    elif provider in ("xai", "grok"):
        return _call_xai(prompt, system, model or "grok-4-0709", temperature=temperature, **kwargs)
    elif provider == "mistral":
        return _call_mistral(prompt, system, model or "mistral-large-3", temperature=temperature, **kwargs)
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
        if k in _handled or v is None:
            continue
        # gpt-5.x / o-series: max_tokens → max_completion_tokens 자동 변환
        if k == "max_tokens" and _is_reasoning:
            req["max_completion_tokens"] = v
        else:
            req[k] = v

    # gpt-5.x / o-series: max_completion_tokens 미설정 시 기본값 보장
    # (reasoning 토큰이 예산을 잠식해 output이 빈 문자열이 되는 버그 방지)
    if _is_reasoning and "max_completion_tokens" not in req:
        req["max_completion_tokens"] = 2000

    resp = client.chat.completions.create(**req)
    # o-series: finish_reason="length" 또는 content=None 시 방어적 처리
    content = resp.choices[0].message.content
    return content if content is not None else ""


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

    elif provider == "gemini":
        # Google AI Studio 모델 목록 API 있지만 하드코딩이 더 명확
        return [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
        ]

    elif provider == "deepseek":
        return [
            "deepseek-reasoner",   # thinking/R1 모드
            "deepseek-chat",       # V3.2 non-thinking
        ]

    elif provider in ("zhipu", "glm"):
        return [
            "glm-5",      # 최신: 744B 파라미터 MoE (2026.02)
            "glm-4.6",    # 355B total / 32B active, Claude Sonnet 4 수준 코딩
            "glm-4-plus", # 안정 버전
            "glm-4",      # 기본 모델
            "glm-4v",     # vision 모델
        ]

    elif provider in ("xai", "grok"):
        return [
            "grok-4-0709",            # Grok 4 (최신, 256k context)
            "grok-4-fast-reasoning",  # 빠른 Grok 4 with reasoning (2M context)
            "grok-4-fast-non-reasoning",  # 빠른 Grok 4 without reasoning (2M context)
            "grok-code-fast-1",       # 코드 특화 + reasoning
            "grok-3",                 # 이전 세대
            "grok-3-mini",            # 경량
        ]

    elif provider == "mistral":
        return [
            "mistral-large-3",    # 최신: 41B active/675B total MoE, Apache 2.0
            "mistral-large-2",    # 이전 세대 flagship
            "pixtral-large",      # vision 지원
            "ministral-14b",      # 새 경량 (Mistral 3 시리즈)
            "ministral-8b",       # 경량 고속
            "ministral-3b",       # 초경량
            "codestral-2501",     # 코드 특화
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


# Claude OAuth 세션 재사용 캐시 (시스템 프롬프트 단위)
# 첫 호출은 느릴 수 있지만, --resume으로 후속 호출은 2~5초대로 단축 가능.
_CLAUDE_OAUTH_SESSION_IDS: dict[str, str] = {}


def _call_claude_oauth(prompt: str, system: str, model: str | None = None) -> str:
    """Call Claude via claude CLI subprocess (free for OAuth users).

    성능 최적화:
    - --output-format json 사용 (session_id 추출)
    - 시스템 프롬프트별 session_id 캐시 후 --resume 재사용
      → subprocess는 유지하지만, Claude 측 캐시/세션 재사용으로 대폭 가속

    ⚠️ extended_thinking / temperature 미지원 (CLI 제한).
    고급 옵션이 필요하면 anthropic provider 사용.
    """
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    full_prompt = f"{system}\n\n{prompt}" if system else prompt

    # Claude Code 세션 중첩 방지 변수 제거
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS")
    }
    if oauth_token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token

    import shutil
    import hashlib

    claude_bin = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")

    # 시스템 프롬프트(+모델) 기준 세션 키
    session_key = hashlib.sha1(f"{model or ''}::{system}".encode("utf-8")).hexdigest()
    cached_session_id = _CLAUDE_OAUTH_SESSION_IDS.get(session_key)

    cmd = [
        claude_bin,
        "-p",
        "--dangerously-skip-permissions",
        "--output-format", "json",
    ]
    if model:
        cmd += ["--model", model]
    if cached_session_id:
        # --resume: 동일 session 재사용 → KV 캐시 활용으로 2nd+ 콜 단축
        cmd += ["--resume", cached_session_id]
    cmd += [full_prompt]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    output = result.stdout.strip()

    _auth_errors = ("not logged in", "please run /login", "authentication", "unauthorized")
    if result.returncode != 0 or any(e in (output + result.stderr).lower() for e in _auth_errors):
        # resume 세션이 깨졌을 수 있으니 1회 재시도 (resume 없이)
        if cached_session_id:
            _CLAUDE_OAUTH_SESSION_IDS.pop(session_key, None)
            cmd_retry = [
                claude_bin,
                "-p",
                "--dangerously-skip-permissions",
                "--output-format", "json",
            ]
            if model:
                cmd_retry += ["--model", model]
            cmd_retry += [full_prompt]
            result = subprocess.run(
                cmd_retry,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            output = result.stdout.strip()

        if result.returncode != 0:
            err = (result.stderr or output or "").strip()
            raise OAuthNotAvailableError(f"Claude OAuth unavailable: {err[:180]}")

    # JSON 결과 파싱 (실패 시 text 그대로 반환)
    try:
        payload = json.loads(output)
        session_id = payload.get("session_id")
        if session_id:
            _CLAUDE_OAUTH_SESSION_IDS[session_key] = session_id
        text = payload.get("result") or ""
        return text.strip()
    except Exception:
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


# ── Google Gemini ─────────────────────────────────────────────────

# thinking을 지원하는 Gemini 모델 목록 (2026-03 기준)
_GEMINI_THINKING_MODELS = {
    "gemini-2.5-pro",
    "gemini-2.5-flash",
}


def _call_gemini(
    prompt: str,
    system: str,
    model: str,
    temperature: float | None = None,
    **kwargs,
) -> str:
    """Google Gemini API 호출.

    Env: GEMINI_API_KEY 또는 GOOGLE_API_KEY
    SDK:  pip install google-genai

    kwargs:
      thinking_budget — int: thinking에 쓸 최대 토큰 수 (0=비활성, 기본 8192)
                         Gemini 2.5 계열만 지원
    """
    try:
        from google import genai
        from google.genai import types as gtypes
    except ImportError:
        raise ImportError(
            "google-genai 패키지가 필요합니다. 'pip install google-genai' 로 설치하세요."
        )

    api_key = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )
    if not api_key:
        raise ValueError("GEMINI_API_KEY 또는 GOOGLE_API_KEY 환경변수가 필요합니다.")

    client = genai.Client(api_key=api_key)

    # thinking 설정 (Gemini 2.5+ 전용)
    thinking_budget = kwargs.get("thinking_budget")
    config_kw: dict = {}
    if temperature is not None:
        config_kw["temperature"] = temperature

    if model in _GEMINI_THINKING_MODELS and thinking_budget is not None:
        config_kw["thinking_config"] = gtypes.ThinkingConfig(
            thinking_budget=int(thinking_budget)
        )

    # system_instruction 설정
    if system:
        config_kw["system_instruction"] = system

    config = gtypes.GenerateContentConfig(**config_kw) if config_kw else None

    kw: dict = {"model": model, "contents": prompt}
    if config:
        kw["config"] = config

    response = client.models.generate_content(**kw)
    return response.text or ""


# ── DeepSeek (OpenAI-호환, 중국) ───────────────────────────────────

def _call_deepseek(
    prompt: str,
    system: str,
    model: str,
    temperature: float | None = None,
    **kwargs,
) -> str:
    """DeepSeek API 호출 (OpenAI-호환 포맷).

    Env: DEEPSEEK_API_KEY
    Endpoint: https://api.deepseek.com

    Models:
      deepseek-chat      — DeepSeek-V3.2 (non-thinking, 빠름)
      deepseek-reasoner  — DeepSeek-V3.2 thinking/R1 (심층 추론)

    kwargs:
      max_tokens — int (기본 4096)
    """
    import openai

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 환경변수가 필요합니다.")

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    req: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": kwargs.get("max_tokens", 4096),
    }
    # deepseek-reasoner는 temperature 0 고정 (reasoning 모델)
    if temperature is not None and model != "deepseek-reasoner":
        req["temperature"] = temperature

    resp = client.chat.completions.create(**req)
    return resp.choices[0].message.content or ""


# ── ZhiPu GLM (중국 智谱AI) ────────────────────────────────────────

def _call_zhipu(
    prompt: str,
    system: str,
    model: str,
    temperature: float | None = None,
    **kwargs,
) -> str:
    """ZhiPu GLM API 호출.

    Env: ZHIPUAI_API_KEY
    SDK: pip install zhipuai

    Models (2026-03 기준):
      glm-5        — 최신 MoE (744B 파라미터, 2026.02 출시)
      glm-4.6      — 355B total / 32B active, 코딩 Claude Sonnet 4 수준
      glm-4-plus   — 안정 버전 일반 채팅
      glm-4        — 기본 모델
      glm-4v       — vision 모델
    """
    try:
        from zhipuai import ZhipuAI
    except ImportError:
        raise ImportError(
            "zhipuai 패키지가 필요합니다. 'pip install zhipuai' 로 설치하세요."
        )

    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise ValueError("ZHIPUAI_API_KEY 환경변수가 필요합니다.")

    client = ZhipuAI(api_key=api_key)

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    req: dict = {"model": model, "messages": messages}
    if temperature is not None:
        req["temperature"] = temperature

    response = client.chat.completions.create(**req)
    return response.choices[0].message.content or ""


# ── xAI Grok (OpenAI-호환) ────────────────────────────────────────

def _call_xai(
    prompt: str,
    system: str,
    model: str,
    temperature: float | None = None,
    **kwargs,
) -> str:
    """xAI Grok API 호출 (OpenAI-호환 포맷).

    Env: XAI_API_KEY
    Endpoint: https://api.x.ai/v1

    Models (2026-03 기준):
      grok-4-0709            — Grok 4 (최신, 256k context, $3/$15 per M)
      grok-4-fast-reasoning  — Grok 4 빠른 버전 + reasoning (2M context, $0.20/$0.50)
      grok-4-fast-non-reasoning  — Grok 4 빠른 버전 non-reasoning (2M context)
      grok-code-fast-1       — 코드 특화 + reasoning
      grok-3                 — 이전 세대 (131k context)
      grok-3-mini            — 경량 + reasoning
    """
    import openai

    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise ValueError("XAI_API_KEY 환경변수가 필요합니다.")

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1",
    )

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    req: dict = {"model": model, "messages": messages}
    if temperature is not None:
        req["temperature"] = temperature

    resp = client.chat.completions.create(**req)
    return resp.choices[0].message.content or ""


# ── Mistral AI (OpenAI-호환) ──────────────────────────────────────

def _call_mistral(
    prompt: str,
    system: str,
    model: str,
    temperature: float | None = None,
    **kwargs,
) -> str:
    """Mistral AI API 호출 (OpenAI-호환 포맷).

    Env: MISTRAL_API_KEY
    Endpoint: https://api.mistral.ai/v1

    Models (2026-03 기준):
      mistral-large-3  — 최신: 41B active / 675B total MoE, Apache 2.0 오픈소스 (2026)
      mistral-large-2  — 이전 세대 128K context
      pixtral-large    — vision 지원
      ministral-14b    — Mistral 3 시리즈 경량 (2026)
      ministral-8b     — 경량 고속
      ministral-3b     — 초경량
      codestral-2501   — 코드 특화
    """
    import openai

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY 환경변수가 필요합니다.")

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.mistral.ai/v1",
    )

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    req: dict = {"model": model, "messages": messages}
    if temperature is not None:
        req["temperature"] = temperature

    resp = client.chat.completions.create(**req)
    return resp.choices[0].message.content or ""


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
