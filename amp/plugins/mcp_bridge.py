"""MCP Bridge plugin — Model Context Protocol server integration.

연결된 MCP 서버의 도구(tools)를 amp 에이전트가 호출할 수 있게 합니다.

Commands:
  /mcp          — 등록된 MCP 서버 목록 + 연결 상태
  /mcp tools    — 사용 가능한 도구 목록
  /mcp call <server> <tool> <args_json>  — 도구 직접 호출

Config (config.yaml):
  mcp:
    servers:
      - name: filesystem
        url: http://localhost:3001
        enabled: true
      - name: brave-search
        url: http://localhost:3002
        enabled: true
      - name: github
        url: http://localhost:3003
        enabled: false

MCP Protocol:
  - JSON-RPC 2.0 over HTTP (POST /)
  - tools/list  → 사용 가능한 도구 목록
  - tools/call  → 도구 실행
  - Anthropic MCP 공식 스펙: https://modelcontextprotocol.io
"""
import json
import logging
from typing import Any

import httpx

from amp.plugins.base import BasePlugin

logger = logging.getLogger(__name__)


class MCPClient:
    """JSON-RPC 2.0 클라이언트 for MCP servers."""

    def __init__(self, name: str, url: str, timeout: float = 10.0):
        self.name = name
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._req_id = 0

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def call(self, method: str, params: dict | None = None) -> Any:
        """JSON-RPC 2.0 호출."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            resp = await http.post(self.url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            raise RuntimeError(f"MCP 오류 [{self.name}]: {data['error']}")
        return data.get("result")

    async def list_tools(self) -> list[dict]:
        """사용 가능한 도구 목록 반환."""
        result = await self.call("tools/list")
        return result.get("tools", []) if result else []

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """도구 실행 후 결과 반환."""
        return await self.call("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

    async def ping(self) -> bool:
        """서버 연결 상태 확인."""
        try:
            await self.call("ping", {})
            return True
        except Exception:
            # MCP 서버마다 ping 지원 여부 다름 — tools/list로 fallback
            try:
                await self.list_tools()
                return True
            except Exception:
                return False


class MCPRegistry:
    """설정에서 MCP 클라이언트 인스턴스 관리."""

    def __init__(self):
        self._clients: dict[str, MCPClient] = {}

    def load(self, config: dict) -> None:
        """config.mcp.servers 목록에서 클라이언트 초기화."""
        servers = config.get("mcp", {}).get("servers", [])
        self._clients.clear()
        for s in servers:
            if not isinstance(s, dict):
                continue
            name = s.get("name", "")
            url = s.get("url", "")
            enabled = s.get("enabled", True)
            if name and url and enabled:
                self._clients[name] = MCPClient(name=name, url=url)
                logger.info(f"MCP 클라이언트 등록: {name} → {url}")

    def get(self, name: str) -> MCPClient | None:
        return self._clients.get(name)

    def all(self) -> dict[str, MCPClient]:
        return dict(self._clients)

    async def get_all_tools(self) -> dict[str, list[dict]]:
        """모든 서버의 도구 목록 수집."""
        result: dict[str, list[dict]] = {}
        for name, client in self._clients.items():
            try:
                tools = await client.list_tools()
                result[name] = tools
            except Exception as e:
                logger.warning(f"MCP {name} tools/list 실패: {e}")
                result[name] = []
        return result

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        """지정 서버의 도구 실행."""
        client = self.get(server_name)
        if not client:
            raise ValueError(f"MCP 서버 '{server_name}'이 등록되지 않았습니다")
        return await client.call_tool(tool_name, arguments)


# 싱글톤 레지스트리
mcp_registry = MCPRegistry()


class MCPBridgePlugin(BasePlugin):
    name = "mcp_bridge"
    description = "MCP 서버 연결 브리지 — 외부 도구를 amp에 연결"
    enabled_by_default = False

    def __init__(self):
        self._config: dict = {}

    def can_handle(self, update) -> bool:
        return False  # setup()에서 CommandHandler로 등록

    async def handle(self, update, context, config: dict, user_config: dict) -> str | None:
        return None

    def get_commands(self) -> list[tuple[str, str]]:
        return [("/mcp", "MCP 서버 목록 / 도구 호출")]

    def setup(self, app, config: dict | None = None) -> None:
        from telegram.ext import CommandHandler

        self._config = config or {}
        mcp_registry.load(self._config)
        app.add_handler(CommandHandler("mcp", self._cmd_mcp))
        logger.info(f"MCPBridgePlugin: {len(mcp_registry.all())}개 서버 등록됨")

    # ── 커맨드 핸들러 ─────────────────────────────────────────

    async def _cmd_mcp(self, update, context) -> None:
        """/mcp [tools | call <server> <tool> [args_json]]"""
        args = context.args or []

        if not args:
            await self._show_servers(update)
        elif args[0] == "tools":
            await self._show_tools(update)
        elif args[0] == "call" and len(args) >= 3:
            server = args[1]
            tool = args[2]
            raw_args = " ".join(args[3:]) if len(args) > 3 else "{}"
            try:
                tool_args = json.loads(raw_args)
            except json.JSONDecodeError:
                tool_args = {"input": raw_args}
            await self._call_tool(update, server, tool, tool_args)
        else:
            await update.message.reply_text(
                "📌 *MCP 사용법:*\n"
                "`/mcp` — 서버 목록\n"
                "`/mcp tools` — 도구 목록\n"
                "`/mcp call <서버> <도구> [JSON]` — 도구 실행",
                parse_mode="Markdown",
            )

    async def _show_servers(self, update) -> None:
        clients = mcp_registry.all()
        if not clients:
            await update.message.reply_text(
                "🔌 *MCP 서버*\n\n"
                "등록된 서버가 없어요.\n"
                "`config.yaml`의 `mcp.servers`에 추가해주세요.\n\n"
                "예시:\n"
                "```yaml\n"
                "mcp:\n"
                "  servers:\n"
                "    - name: filesystem\n"
                "      url: http://localhost:3001\n"
                "```",
                parse_mode="Markdown",
            )
            return

        lines = [f"🔌 *MCP 서버 ({len(clients)}개)*\n"]
        for name, client in clients.items():
            ping_ok = await client.ping()
            status = "🟢" if ping_ok else "🔴"
            lines.append(f"{status} `{name}` — {client.url}")

        lines.append("\n도구 보기: `/mcp tools`")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _show_tools(self, update) -> None:
        all_tools = await mcp_registry.get_all_tools()
        if not any(all_tools.values()):
            await update.message.reply_text("⚠️ 사용 가능한 도구가 없어요. 서버 연결을 확인해주세요.")
            return

        lines = ["🛠️ *MCP 도구 목록*\n"]
        for server_name, tools in all_tools.items():
            if not tools:
                lines.append(f"**{server_name}** — _(연결 실패 또는 도구 없음)_")
                continue
            lines.append(f"*[{server_name}]*")
            for t in tools:
                t_name = t.get("name", "?")
                t_desc = t.get("description", "")[:60]
                lines.append(f"  • `{t_name}` — {t_desc}")

        lines.append("\n실행: `/mcp call <서버> <도구> {{\"key\": \"val\"}}`")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _call_tool(self, update, server: str, tool: str, arguments: dict) -> None:
        await update.message.chat.send_action("typing")
        try:
            result = await mcp_registry.call_tool(server, tool, arguments)
            result_str = json.dumps(result, ensure_ascii=False, indent=2)
            if len(result_str) > 3000:
                result_str = result_str[:3000] + "\n... (결과 잘림)"
            await update.message.reply_text(
                f"✅ *{server}/{tool}* 실행 결과:\n```json\n{result_str}\n```",
                parse_mode="Markdown",
            )
        except Exception as e:
            await update.message.reply_text(f"❌ 도구 실행 실패: {str(e)[:300]}")
