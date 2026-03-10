"""Tests for get_fast_model() and pipeline defaults."""
import os
import importlib
from unittest.mock import patch, MagicMock
import pytest

from amp.config import get_fast_model


def test_get_fast_model_default():
    """Returns gpt-5.4 when no config or env var is set."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AMP_FAST_MODEL", None)
        result = get_fast_model()
    assert result == "gpt-5.4"


def test_get_fast_model_from_env():
    """Returns env var value when AMP_FAST_MODEL is set."""
    with patch.dict(os.environ, {"AMP_FAST_MODEL": "gpt-5.2"}):
        result = get_fast_model()
    assert result == "gpt-5.2"


def test_get_fast_model_from_config():
    """Config dict takes priority over env var."""
    config = {"llm": {"fast_model": "gpt-5-turbo"}}
    with patch.dict(os.environ, {"AMP_FAST_MODEL": "gpt-5.2"}):
        result = get_fast_model(config)
    assert result == "gpt-5-turbo"


def test_get_fast_model_config_empty_uses_env():
    """Empty config fast_model falls back to env var."""
    config = {"llm": {"fast_model": ""}}
    with patch.dict(os.environ, {"AMP_FAST_MODEL": "gpt-5.2"}):
        result = get_fast_model(config)
    assert result == "gpt-5.2"


def test_get_fast_model_no_llm_section():
    """Config without llm section falls back to env/default."""
    config = {}
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AMP_FAST_MODEL", None)
        result = get_fast_model(config)
    assert result == "gpt-5.4"
