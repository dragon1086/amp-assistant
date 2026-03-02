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
    **kwargs,
) -> str:
    """Universal LLM caller supporting multiple providers.

    Args:
        prompt: User message
        system: System prompt (optional)
        provider: One of openai | anthropic_oauth | claude_oauth | anthropic | local
        model: Model identifier (provider-specific)
        **kwargs: Extra args forwarded to the underlying caller

    Returns:
        Response text string
    """
    if provider == "openai":
        return _call_openai(prompt, system, model)
    elif provider in ("anthropic_oauth", "claude_oauth"):
        return _call_claude_oauth(prompt, system)
    elif provider == "anthropic":
        return _call_anthropic(prompt, system, model)
    elif provider == "local":
        return _call_ollama(prompt, system, model)
    else:
        raise ValueError(f"알 수 없는 provider: {provider}")


def _call_openai(prompt: str, system: str, model: str) -> str:
    import openai

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(model=model, messages=messages)
    return response.choices[0].message.content


def _call_claude_oauth(prompt: str, system: str) -> str:
    """Call Claude via claude CLI subprocess (free for OAuth users)."""
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
    return result.stdout.strip()


def _call_anthropic(prompt: str, system: str, model: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    kwargs: dict = {}
    if system:
        kwargs["system"] = system

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )
    return response.content[0].text


def _call_ollama(prompt: str, system: str, model: str) -> str:
    import httpx

    response = httpx.post(
        "http://localhost:11434/api/generate",
        json={
            "model": model,
            "prompt": f"{system}\n\n{prompt}" if system else prompt,
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["response"]
