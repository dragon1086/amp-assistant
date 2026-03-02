"""Telegram bot interface for amp.

Commands:
  /start  - Welcome message
  /mode   - Show/set mode (auto|solo|pipeline|emergent)
  /stats  - Show KG and session stats
  /clear  - Clear conversation history

Regular messages are processed as queries.
"""

import asyncio
import logging
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from amp.config import load_config
from amp.core import emergent, router, solo
from amp.core import pipeline_engine as pipeline
from amp.core.kg import KnowledgeGraph
from amp.core.metrics import format_cser

logger = logging.getLogger(__name__)


def _build_emergent_message(result: dict) -> str:
    """Format emergent result for Telegram."""
    lines = ["🤔 *분석 중... (emergent mode)*\n"]

    lines.append("*\\[Agent A — Analyst\\]*")
    lines.append(result["agent_a"][:600] + ("..." if len(result["agent_a"]) > 600 else ""))
    lines.append("")

    lines.append("*\\[Agent B — Critic\\]*")
    lines.append(result["agent_b"][:600] + ("..." if len(result["agent_b"]) > 600 else ""))
    lines.append("")

    lines.append("━" * 20)

    if result.get("agreements"):
        lines.append("*✓ 합의:*")
        for a in result["agreements"][:2]:
            lines.append(f"• {a}")
        lines.append("")

    if result.get("conflicts"):
        lines.append("*⚡ 이견:*")
        for c in result["conflicts"][:2]:
            lines.append(f"• {c}")
        lines.append("")

    lines.append("*✅ 결론:*")
    lines.append(result["answer"])
    lines.append("")

    lines.append(f"📊 신뢰도: CSER {result['cser']:.2f} ({'높음' if result['confidence'] == 'high' else '낮음'})")
    lines.append("━" * 20)

    return "\n".join(lines)


class AmpBot:
    """Telegram bot wrapper for amp."""

    def __init__(self, config: dict, kg: KnowledgeGraph):
        self.config = config
        self.kg = kg
        # Per-user state
        self._contexts: dict[int, list[dict]] = {}
        self._modes: dict[int, str] = {}

    def _get_context(self, user_id: int) -> list[dict]:
        return self._contexts.setdefault(user_id, [])

    def _get_mode(self, user_id: int) -> str:
        return self._modes.get(user_id, self.config["amp"].get("default_mode", "auto"))

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 *amp에 오신 것을 환영합니다!*\n\n"
            "Two minds\\. One answer\\.\n\n"
            "저는 두 AI 에이전트가 독립적으로 분석하고 화해하는 방식으로 동작하는 "
            "로컬 개인 비서입니다\\.\n\n"
            "*명령어:*\n"
            "/mode \\- 현재 모드 확인/변경\n"
            "/stats \\- 지식 그래프 통계\n"
            "/clear \\- 대화 기록 초기화\n\n"
            "질문이나 도움이 필요한 것을 그냥 입력하세요\\!",
            parse_mode="MarkdownV2",
        )

    async def cmd_mode(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        args = ctx.args

        if args and args[0] in ("auto", "solo", "pipeline", "emergent"):
            self._modes[user_id] = args[0]
            await update.message.reply_text(f"✅ 모드 변경: *{args[0]}*", parse_mode="Markdown")
        else:
            current = self._get_mode(user_id)
            await update.message.reply_text(
                f"현재 모드: *{current}*\n\n"
                "변경하려면:\n"
                "`/mode auto` — 자동 감지\n"
                "`/mode solo` — 단일 응답\n"
                "`/mode pipeline` — 계획→해결→검토→수정\n"
                "`/mode emergent` — 2-에이전트 분석",
                parse_mode="Markdown",
            )

    async def cmd_stats(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        stats = self.kg.stats()
        await update.message.reply_text(
            f"📊 *amp 통계*\n\n"
            f"🧠 KG: {stats['node_count']} nodes, {stats['edge_count']} edges\n"
            f"🏷️ Tags: {', '.join(stats['tags'][:5]) or 'none'}",
            parse_mode="Markdown",
        )

    async def cmd_clear(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self._contexts[user_id] = []
        await update.message.reply_text("🗑️ 대화 기록이 초기화되었습니다.")

    async def handle_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Process a regular message as an amp query."""
        user_id = update.effective_user.id
        query = update.message.text

        if not query:
            return

        context = self._get_context(user_id)
        mode = self._get_mode(user_id)

        # Show typing indicator
        await update.message.chat.send_action(ChatAction.TYPING)

        try:
            effective_mode = router.detect_mode(query, mode)

            if effective_mode == "solo":
                result = await solo.run(query, context, self.config)
            elif effective_mode == "pipeline":
                result = await pipeline.run(query, context, self.config)
            else:
                result = await emergent.run(query, context, self.config)

            result["effective_mode"] = effective_mode

            # Auto-save emergent insights
            if effective_mode == "emergent" and result.get("answer"):
                node_id = self.kg.add(
                    f"Q: {query}\nA: {result['answer'][:500]}",
                    tags=["emergent", "telegram"],
                )
                result["kg_node_id"] = node_id

            # Format response
            if effective_mode == "emergent":
                reply = _build_emergent_message(result)
                try:
                    await update.message.reply_text(reply, parse_mode="MarkdownV2")
                except Exception:
                    # Fallback without markdown if parsing fails
                    await update.message.reply_text(result["answer"])
            else:
                label = "pipeline" if effective_mode == "pipeline" else "solo"
                reply = f"*amp ({label}):*\n\n{result['answer']}"
                try:
                    await update.message.reply_text(reply, parse_mode="Markdown")
                except Exception:
                    await update.message.reply_text(result["answer"])

            if "kg_node_id" in result:
                await update.message.reply_text(
                    f"💾 KG에 저장됨 (node #{result['kg_node_id']})"
                )

            # Update context
            context.append({"role": "user", "content": query})
            context.append({"role": "assistant", "content": result["answer"]})
            if len(context) > 20:
                self._contexts[user_id] = context[-20:]

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            await update.message.reply_text(
                f"❌ 오류가 발생했습니다: {str(e)[:200]}"
            )


def run_bot(config: dict | None = None):
    """Start the Telegram bot."""
    if config is None:
        config = load_config()

    token = config.get("telegram", {}).get("token", "")
    if not token:
        raise ValueError(
            "Telegram bot token not configured. "
            "Set TELEGRAM_BOT_TOKEN env var or add to config.yaml"
        )

    kg_path = Path(config["amp"].get("kg_path", "~/.amp/kg.json")).expanduser()
    kg = KnowledgeGraph(kg_path)

    bot = AmpBot(config, kg)

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", bot.cmd_start))
    app.add_handler(CommandHandler("mode", bot.cmd_mode))
    app.add_handler(CommandHandler("stats", bot.cmd_stats))
    app.add_handler(CommandHandler("clear", bot.cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))

    logging.basicConfig(level=logging.INFO)
    logger.info("Starting amp Telegram bot...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_bot()
