"""Configuration loading for amp.

Loads from ~/.amp/config.yaml with environment variable interpolation.
Environment variables override config file values.
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml

AMP_DIR = Path.home() / ".amp"
DEFAULT_CONFIG_PATH = AMP_DIR / "config.yaml"


def _resolve_env_vars(value: Any) -> Any:
    """Resolve ${ENV_VAR} patterns in config values."""
    if isinstance(value, str):
        pattern = re.compile(r"\$\{([^}]+)\}")
        def replacer(match):
            env_var = match.group(1)
            return os.environ.get(env_var, "")
        return pattern.sub(replacer, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


def load_config(config_path: Path | None = None) -> dict:
    """Load configuration from file and environment variables.

    Priority: env vars > config file > defaults
    """
    defaults = {
        "llm": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "",
        },
        "telegram": {
            "token": "",
        },
        "amp": {
            "default_mode": "auto",
            "kg_path": str(AMP_DIR / "kg.json"),
        },
    }

    path = config_path or DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path) as f:
            file_config = yaml.safe_load(f) or {}
        # Deep merge file config into defaults
        _deep_merge(defaults, file_config)

    # Resolve env var interpolation
    config = _resolve_env_vars(defaults)

    # Direct env var overrides
    if api_key := os.environ.get("OPENAI_API_KEY"):
        config["llm"]["api_key"] = api_key
        if not config["llm"].get("provider") or config["llm"]["provider"] == "openai":
            config["llm"]["provider"] = "openai"

    if api_key := os.environ.get("ANTHROPIC_API_KEY"):
        if config["llm"]["provider"] == "anthropic":
            config["llm"]["api_key"] = api_key

    if token := os.environ.get("TELEGRAM_BOT_TOKEN"):
        config["telegram"]["token"] = token

    if model := os.environ.get("AMP_MODEL"):
        config["llm"]["model"] = model

    if mode := os.environ.get("AMP_DEFAULT_MODE"):
        config["amp"]["default_mode"] = mode

    return config


def _deep_merge(base: dict, override: dict) -> None:
    """Merge override into base in-place."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def save_config(config: dict, config_path: Path | None = None) -> None:
    """Save configuration to file."""
    path = config_path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def ensure_amp_dir() -> Path:
    """Ensure ~/.amp/ directory exists."""
    AMP_DIR.mkdir(parents=True, exist_ok=True)
    return AMP_DIR
