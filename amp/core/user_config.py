"""Per-user configuration stored in SQLite.

Stores user-specific settings (model preferences, plugin enable/disable)
keyed by Telegram user_id.
"""
import json
import sqlite3
from pathlib import Path


class UserConfigStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_config (
                    user_id INTEGER PRIMARY KEY,
                    config_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )

    def get(self, user_id: int) -> dict:
        """Get user config, returns defaults if not set."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT config_json FROM user_config WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row:
            return json.loads(row[0])
        return self._defaults()

    def set(self, user_id: int, config: dict) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_config (user_id, config_json) VALUES (?, ?)",
                (user_id, json.dumps(config)),
            )

    def update(self, user_id: int, **kwargs) -> dict:
        config = self.get(user_id)
        config.update(kwargs)
        self.set(user_id, config)
        return config

    def _defaults(self) -> dict:
        return {
            "agent_a": {"provider": "openai", "model": "gpt-4o"},
            "agent_b": {"provider": "anthropic_oauth", "model": "claude-sonnet-4-6"},
            "plugins": {},  # plugin_name: bool (True=enabled, False=disabled)
        }
