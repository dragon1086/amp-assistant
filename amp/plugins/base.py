"""Base plugin interface for amp extensibility."""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


class BasePlugin(ABC):
    name: str = ""
    description: str = ""
    enabled_by_default: bool = True

    @abstractmethod
    def can_handle(self, update) -> bool:
        """Return True if this plugin can handle the given update."""
        ...

    @abstractmethod
    async def handle(self, update, context, config: dict, user_config: dict) -> str | None:
        """Handle the update. Return response text or None (if already replied)."""
        ...

    def get_commands(self) -> list[tuple[str, str]]:
        """Return list of (command, description) tuples this plugin provides."""
        return []

    def get_system_prompt(self) -> str | None:
        """Return additional system prompt text to inject, or None.

        마크다운 전용 플러그인(Python 파일 없음)은 이 메서드로 내용을 주입한다.
        """
        return None

    def setup(self, app, config: dict | None = None) -> None:
        """Called once during bot setup. Register handlers here if needed."""
        pass
