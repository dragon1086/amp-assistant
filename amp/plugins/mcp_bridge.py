"""MCP Bridge plugin — stub for MCP (Model Context Protocol) server integration.

Provides /mcp command to list configured MCP servers.
Actual MCP protocol bridging is a future extension point.

Config (config.yaml):
  mcp:
    servers:
      - name: filesystem
        url: http://localhost:3001
      - name: brave-search
        url: http://localhost:3002
"""
import logging

from amp.plugins.base import BasePlugin

logger = logging.getLogger(__name__)


class MCPBridgePlugin(BasePlugin):
    name = "mcp_bridge"
    description = "MCP 서버 연결 브리지"
    enabled_by_default = False

    def __init__(self):
        self._config: dict = {}

    def can_handle(self, update) -> bool:
        # Routing is done via CommandHandler registered in setup()
        return False

    async def handle(self, update, context, config: dict, user_config: dict) -> str | None:
        return None

    def get_commands(self) -> list[tuple[str, str]]:
        return [("/mcp", "MCP 서버 목록 보기")]

    def setup(self, app, config: dict | None = None) -> None:
        from telegram.ext import CommandHandler

        self._config = config or {}
        app.add_handler(CommandHandler("mcp", self._cmd_mcp))
        logger.info("MCPBridgePlugin registered /mcp command")

    async def _cmd_mcp(self, update, context) -> None:
        servers = self._config.get("mcp", {}).get("servers", [])

        if not servers:
            await update.message.reply_text(
                "🔌 *MCP 서버*\n\n"
                "등록된 MCP 서버가 없습니다\\.\n"
                "`config\\.yaml`의 `mcp\\.servers`에 서버를 추가하세요\\.",
                parse_mode="MarkdownV2",
            )
            return

        lines = ["🔌 *MCP 서버 목록:*\n"]
        for s in servers:
            if isinstance(s, dict):
                name = s.get("name", "?")
                url = s.get("url", "")
                lines.append(f"• `{name}` — {url}")
            else:
                lines.append(f"• `{s}`")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
