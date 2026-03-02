"""Telegram bot interface for amp.

Commands:
  /start   - Welcome message
  /mode    - Show/set mode (auto|solo|pipeline|emergent)
  /model   - Show/set per-user LLM models
  /plugins - List all plugins and their status
  /plugin  - Enable or disable a plugin
  /imagine - Generate an image from a text prompt
  /stats   - Show KG and session stats
  /clear   - Clear conversation history

Regular messages are processed as queries.
Photos are processed by the image_vision plugin (if enabled).
"""

import asyncio
import logging
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
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
from amp.core.user_config import UserConfigStore
from amp.plugins.registry import _registry as plugin_registry

logger = logging.getLogger(__name__)


def _html_e(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


import re

def _md_to_html(text: str) -> str:
    """Convert LLM markdown output to Telegram HTML.

    Handles the most common cases AI models produce:
      **bold** / __bold__  →  <b>bold</b>
      *italic* / _italic_  →  <i>italic</i>
      `code`               →  <code>code</code>
      ```lang\n...\n```    →  <pre>...</pre>
      ### heading          →  <b>heading</b>
    """
    # First escape HTML special chars
    text = _html_e(text)

    # Code blocks (before inline code to avoid double-processing)
    text = re.sub(r'```[a-zA-Z]*\n(.*?)```', lambda m: f'<pre>{m.group(1)}</pre>', text, flags=re.DOTALL)
    text = re.sub(r'```(.*?)```', lambda m: f'<pre>{m.group(1)}</pre>', text, flags=re.DOTALL)

    # Inline code
    text = re.sub(r'`([^`\n]+)`', lambda m: f'<code>{m.group(1)}</code>', text)

    # Bold: **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', lambda m: f'<b>{m.group(1)}</b>', text, flags=re.DOTALL)
    text = re.sub(r'__(.+?)__', lambda m: f'<b>{m.group(1)}</b>', text, flags=re.DOTALL)

    # Italic: *text* or _text_ (single, not double)
    text = re.sub(r'\*([^\*\n]+)\*', lambda m: f'<i>{m.group(1)}</i>', text)
    text = re.sub(r'(?<![_\w])_([^_\n]+)_(?![_\w])', lambda m: f'<i>{m.group(1)}</i>', text)

    # Headings: ### / ## / #
    text = re.sub(r'^#{1,6}\s+(.+)$', lambda m: f'<b>{m.group(1)}</b>', text, flags=re.MULTILINE)

    return text


def _build_emergent_message(result: dict) -> str:
    """Format emergent result for Telegram HTML parse mode.

    Layout (모바일 최적화):
      헤더 + 페르소나 한 줄
      ━━━
      ✅ 결론 (full)
      ━━━
      📊 CSER + 합의/이견 요약
    """
    persona_a = result.get("persona_a", "Agent A")
    persona_b = result.get("persona_b", "Agent B")
    persona_domain = result.get("persona_domain", "default")
    persona_diversity = result.get("persona_diversity", 0.0)

    # 페르소나 이름 짧게 (첫 구분자 앞까지)
    def _short(p: str) -> str:
        return p.split("—")[0].split("–")[0].split("-")[0].strip()[:24]

    lines = ["🤔 <b>emergent mode</b>"]
    lines.append(
        f"<i>🎭 {_html_e(_short(persona_a))} vs {_html_e(_short(persona_b))}"
        f" | 도메인: {_html_e(persona_domain)}"
        f" | 다양성: {round(persona_diversity, 2)}</i>"
    )
    lines.append("")
    lines.append("━" * 20)
    lines.append("")

    # 결론 (핵심 — 전체 표시)
    lines.append("<b>✅ 결론:</b>")
    lines.append(_md_to_html(result["answer"]))
    lines.append("")

    # CSER
    cser_display = format_cser(result["cser"], result["confidence"])
    lines.append(f"📊 {_html_e(cser_display)}")

    # 합의 / 이견 (간결하게)
    if result.get("agreements"):
        lines.append("")
        lines.append("<b>🤝 합의:</b>")
        for a in result["agreements"][:2]:
            lines.append(f"• {_html_e(a)}")

    if result.get("conflicts"):
        lines.append("")
        lines.append("<b>⚡ 이견:</b>")
        for c in result["conflicts"][:2]:
            lines.append(f"• {_html_e(c)}")

    lines.append("")
    lines.append("━" * 20)

    # Insights (있을 때만, trust_reason 우선)
    if result.get("insights"):
        ins = result["insights"]
        if ins.get("trust_reason"):
            lines.append(f"💡 <i>{_html_e(ins['trust_reason'])}</i>")

    return "\n".join(lines)


class AmpBot:
    """Telegram bot wrapper for amp."""

    def __init__(self, config: dict, kg: KnowledgeGraph):
        self.config = config
        self.kg = kg
        # Per-user in-memory state
        self._contexts: dict[int, list[dict]] = {}
        self._modes: dict[int, str] = {}

        # Per-user persistent config (SQLite)
        kg_path = Path(config["amp"].get("kg_path", "~/.amp/kg.db")).expanduser()
        self.user_config_store = UserConfigStore(kg_path.parent / "user_config.db")

        # Plugin registry — populated by run_bot after discover()
        self.plugin_registry = plugin_registry

    def _get_context(self, user_id: int) -> list[dict]:
        return self._contexts.setdefault(user_id, [])

    def _get_mode(self, user_id: int) -> str:
        return self._modes.get(user_id, self.config["amp"].get("default_mode", "auto"))

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 <b>amp에 오신 것을 환영합니다!</b>\n\n"
            "Two minds. One answer.\n\n"
            "저는 두 AI 에이전트가 독립적으로 분석하고 화해하는 방식으로 동작하는 "
            "로컬 개인 비서입니다.\n\n"
            "<b>명령어:</b>\n"
            "/mode - 현재 모드 확인/변경\n"
            "/model - LLM 모델 확인/변경\n"
            "/plugins - 플러그인 목록\n"
            "/imagine - 이미지 생성\n"
            "/stats - 지식 그래프 통계\n"
            "/clear - 대화 기록 초기화\n\n"
            "질문이나 도움이 필요한 것을 그냥 입력하세요!",
            parse_mode="HTML",
        )

    async def cmd_mode(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        args = ctx.args

        if args and args[0] in ("auto", "solo", "pipeline", "emergent"):
            self._modes[user_id] = args[0]
            await update.message.reply_text(f"✅ 모드 변경: <b>{args[0]}</b>", parse_mode="HTML")
        else:
            current = self._get_mode(user_id)
            await update.message.reply_text(
                f"현재 모드: <b>{current}</b>\n\n"
                "변경하려면:\n"
                "<code>/mode auto</code> — 자동 감지\n"
                "<code>/mode solo</code> — 단일 응답\n"
                "<code>/mode pipeline</code> — 계획→해결→검토→수정\n"
                "<code>/mode emergent</code> — 2-에이전트 분석",
                parse_mode="HTML",
            )

    async def cmd_stats(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        stats = self.kg.stats()
        await update.message.reply_text(
            f"📊 <b>amp 통계</b>\n\n"
            f"🧠 KG: {stats['nodes']} nodes, {stats['edges']} edges\n"
            f"💾 DB: <code>{_html_e(str(stats['db_path']))}</code>",
            parse_mode="HTML",
        )

    async def cmd_clear(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self._contexts[user_id] = []
        await update.message.reply_text("🗑️ 대화 기록이 초기화되었습니다.")

    # ------------------------------------------------------------------ #
    # Model management
    # ------------------------------------------------------------------ #

    async def cmd_model(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Show or update per-user LLM model settings.

        Usage:
          /model             — show current settings
          /model a gpt-4o   — set Agent A model
          /model b claude-sonnet-4-6 — set Agent B model
        """
        user_id = update.effective_user.id
        args = ctx.args
        user_config = self.user_config_store.get(user_id)

        if not args:
            agent_a = user_config.get("agent_a", {})
            agent_b = user_config.get("agent_b", {})
            await update.message.reply_text(
                "<b>현재 모델 설정:</b>\n\n"
                f"Agent A: <code>{_html_e(agent_a.get('provider', 'openai'))}</code> / <code>{_html_e(agent_a.get('model', 'gpt-4o'))}</code>\n"
                f"Agent B: <code>{_html_e(agent_b.get('provider', 'anthropic_oauth'))}</code> / <code>{_html_e(agent_b.get('model', 'claude-sonnet-4-6'))}</code>\n\n"
                "변경:\n"
                "<code>/model a gpt-4o</code>\n"
                "<code>/model b claude-sonnet-4-6</code>",
                parse_mode="HTML",
            )
            return

        if len(args) >= 2 and args[0] in ("a", "b"):
            agent_key = f"agent_{args[0]}"
            model = args[1]
            user_config[agent_key]["model"] = model
            self.user_config_store.set(user_id, user_config)
            await update.message.reply_text(
                f"✅ Agent {args[0].upper()} 모델 변경: <code>{_html_e(model)}</code>",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                "사용법: <code>/model</code> (현재 설정) 또는 <code>/model a gpt-4o</code>",
                parse_mode="HTML",
            )

    # ------------------------------------------------------------------ #
    # Plugin management
    # ------------------------------------------------------------------ #

    async def cmd_plugins(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """List all plugins and their enabled/disabled state."""
        user_id = update.effective_user.id
        user_config = self.user_config_store.get(user_id)
        plugins = self.plugin_registry.all()

        if not plugins:
            await update.message.reply_text("등록된 플러그인이 없습니다.")
            return

        lines = ["<b>🔌 플러그인 목록:</b>\n"]
        for p in plugins:
            enabled = user_config.get("plugins", {}).get(p.name, p.enabled_by_default)
            status = "✅" if enabled else "❌"
            lines.append(f"{status} <code>{_html_e(p.name)}</code> — {_html_e(p.description)}")

        lines.append("\n토글: <code>/plugin on image_vision</code> 또는 <code>/plugin off image_vision</code>")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def cmd_plugin(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Enable or disable a plugin for this user.

        Usage:
          /plugin on <name>
          /plugin off <name>
        """
        user_id = update.effective_user.id
        args = ctx.args

        if len(args) < 2 or args[0] not in ("on", "off"):
            await update.message.reply_text(
                "사용법: <code>/plugin on &lt;이름&gt;</code> 또는 <code>/plugin off &lt;이름&gt;</code>",
                parse_mode="HTML",
            )
            return

        action, name = args[0], args[1]
        plugin = self.plugin_registry.get(name)
        if not plugin:
            await update.message.reply_text(
                f"❌ 플러그인 <code>{_html_e(name)}</code>을 찾을 수 없습니다.",
                parse_mode="HTML",
            )
            return

        enabled = action == "on"
        user_config = self.user_config_store.get(user_id)
        user_config.setdefault("plugins", {})[name] = enabled
        self.user_config_store.set(user_id, user_config)

        status_text = "활성화" if enabled else "비활성화"
        await update.message.reply_text(
            f"✅ <code>{_html_e(name)}</code> 플러그인 {status_text}됨",
            parse_mode="HTML",
        )

    # ------------------------------------------------------------------ #
    # Image handlers
    # ------------------------------------------------------------------ #

    async def cmd_imagine(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Delegate /imagine to the image_gen plugin."""
        user_id = update.effective_user.id
        user_config = self.user_config_store.get(user_id)
        plugin = self.plugin_registry.get("image_gen")

        if not plugin:
            await update.message.reply_text("❌ 이미지 생성 플러그인이 없습니다.")
            return

        if not user_config.get("plugins", {}).get("image_gen", plugin.enabled_by_default):
            await update.message.reply_text(
                "❌ 이미지 생성 플러그인이 비활성화되어 있습니다. "
                "<code>/plugin on image_gen</code>으로 활성화하세요.",
                parse_mode="HTML",
            )
            return

        await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
        await plugin.handle(update, ctx, self.config, user_config)

    async def handle_photo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Process incoming photos via the image_vision plugin."""
        user_id = update.effective_user.id
        user_config = self.user_config_store.get(user_id)
        plugin = self.plugin_registry.get("image_vision")

        if not plugin:
            await update.message.reply_text("이미지를 처리할 플러그인이 없습니다.")
            return

        if not user_config.get("plugins", {}).get("image_vision", plugin.enabled_by_default):
            await update.message.reply_text("이미지 분석 플러그인이 비활성화되어 있습니다.")
            return

        await update.message.chat.send_action(ChatAction.TYPING)
        try:
            result = await plugin.handle(update, ctx, self.config, user_config)
            if result:
                await update.message.reply_text(result)
        except Exception as e:
            logger.error(f"Image vision error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ 이미지 처리 실패: {str(e)[:200]}")

    async def handle_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Process a regular text message — plugins first, then amp router."""
        user_id = update.effective_user.id
        query = update.message.text

        if not query:
            return

        user_config = self.user_config_store.get(user_id)

        # --- Plugin pass: let enabled plugins intercept before amp routing ---
        for plugin in self.plugin_registry.get_enabled(user_config):
            if plugin.can_handle(update):
                await update.message.chat.send_action(ChatAction.TYPING)
                try:
                    result = await plugin.handle(update, ctx, self.config, user_config)
                    if result is not None:
                        await update.message.reply_text(result)
                    return
                except Exception as e:
                    logger.error(f"Plugin {plugin.name} error: {e}", exc_info=True)
                    await update.message.reply_text(f"❌ 플러그인 오류: {str(e)[:200]}")
                    return

        # --- amp core routing ---
        context = self._get_context(user_id)
        mode = self._get_mode(user_id)

        status_msg = None
        try:
            effective_mode = router.detect_mode(query, mode)
            rounds = router.detect_rounds(query, effective_mode)

            # Collect system prompts from enabled MarkdownPlugins (SKILL.md 기반)
            run_config = dict(self.config)
            skill_prompts = []
            for plugin in self.plugin_registry.get_enabled(user_config):
                sp = plugin.get_system_prompt() if hasattr(plugin, "get_system_prompt") else None
                if sp:
                    skill_prompts.append(sp)
            if skill_prompts:
                run_config.setdefault("amp", {})["skill_prompts"] = skill_prompts

            # --- 실시간 진행 상황 메시지 (emergent 모드만) ---
            status_msg = None
            if effective_mode == "emergent":
                status_msg = await update.message.reply_text("⏳ 분석 시작 중...", parse_mode="HTML")
                loop = asyncio.get_event_loop()

                def on_progress(stage: str, data: dict):
                    pa = _html_e(data.get('persona_a', data.get('persona', 'Agent A')))
                    pb = _html_e(data.get('persona_b', data.get('persona', 'Agent B')))
                    stage_texts = {
                        "persona_selected": (
                            f"🎭 <b>페르소나 선택 완료</b>\n"
                            f"🔵 A: {pa}\n"
                            f"🔴 B: {pb}\n\n"
                            f"⏳ 두 전문가 분석 중..."
                        ),
                        "agent_a_start": (
                            f"🔵 <b>{pa}</b> 분석 중...\n"
                            f"🔴 Agent B 대기 중"
                        ),
                        "agent_a_done": (
                            f"🔵 <b>{pa}</b> ✅\n"
                            f"🔴 Agent B 분석 중..."
                        ),
                        "agent_b_start": (
                            f"🔵 Agent A ✅\n"
                            f"🔴 <b>{pb}</b> 분석 중..."
                        ),
                        "agent_b_done": (
                            f"🔵 Agent A ✅\n"
                            f"🔴 <b>{pb}</b> ✅\n\n"
                            f"🟡 두 관점 합성 중..."
                        ),
                        "reconciling": (
                            f"🔵 Agent A ✅  🔴 Agent B ✅\n\n"
                            f"🟡 합성 중... (CSER: {data.get('cser',0):.2f})"
                        ),
                        "verifying": (
                            f"🔵 Agent A ✅  🔴 Agent B ✅  🟡 합성 ✅\n\n"
                            f"✅ 최종 검증 중..."
                        ),
                    }
                    text = stage_texts.get(stage)
                    if text and status_msg:
                        async def _edit():
                            try:
                                await status_msg.edit_text(text, parse_mode="HTML")
                            except Exception:
                                pass
                        asyncio.run_coroutine_threadsafe(_edit(), loop)

                result = await asyncio.to_thread(
                    emergent.run, query, context, run_config, on_progress, rounds
                )
            elif effective_mode == "solo":
                status_msg = await update.message.reply_text("⏳ 분석 중...", parse_mode="HTML")
                result = await asyncio.to_thread(solo.run, query, context, run_config)
            else:
                # pipeline: plan→solve→review→fix 4단계
                status_msg = await update.message.reply_text(
                    "⏳ <b>분석 시작 중...</b>\n📋 1. 계획 수립 중",
                    parse_mode="HTML"
                )
                loop = asyncio.get_event_loop()
                step = [0]

                async def _update_pipeline_status():
                    steps = [
                        "⏳ <b>분석 시작 중...</b>\n📋 1. 계획 수립 중",
                        "📋 계획 ✅\n🔧 2. 해결 중...",
                        "🔧 해결 ✅\n🔍 3. 검토 중...",
                        "🔍 검토 ✅\n✨ 4. 최종 수정 중...",
                    ]
                    for i in range(1, len(steps)):
                        await asyncio.sleep(8)
                        if status_msg and step[0] < i:
                            step[0] = i
                            try:
                                await status_msg.edit_text(steps[i], parse_mode="HTML")
                            except Exception:
                                pass

                asyncio.ensure_future(_update_pipeline_status())
                result = await asyncio.to_thread(pipeline.run, query, context, run_config)

            result["effective_mode"] = effective_mode

            # 완료 — status 메시지를 삭제 대신 ✅ 완료 표시로 업데이트
            if status_msg:
                mode_label = {
                    "emergent": "🔵🔴 4-round 토론" if rounds == 4 else "🔵🔴 2-agent 분석",
                    "pipeline": "📋 4단계 파이프라인",
                    "solo": "💬 단일 응답",
                }.get(effective_mode, "분석")
                try:
                    await status_msg.edit_text(
                        f"✅ <b>{_html_e(mode_label)} 완료</b>",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

            # Auto-save emergent insights to KG
            if effective_mode == "emergent" and result.get("answer"):
                node_id = self.kg.add(
                    f"Q: {query}\nA: {result['answer'][:500]}",
                    tags=["emergent", "telegram"],
                )
                result["kg_node_id"] = node_id

            # Format response
            if effective_mode == "emergent":
                reply = _build_emergent_message(result)
                # Attach feedback keyboard if we have a KG node
                reply_markup = None
                if result.get("kg_node_id"):
                    node_id = result["kg_node_id"]
                    keyboard = [[
                        InlineKeyboardButton("👍 도움됐어", callback_data=f"feedback_good_{node_id}"),
                        InlineKeyboardButton("👎 별로야", callback_data=f"feedback_bad_{node_id}"),
                    ]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                try:
                    await update.message.reply_text(reply, parse_mode="HTML", reply_markup=reply_markup)
                except Exception:
                    # Fallback without markdown if parsing fails
                    await update.message.reply_text(result["answer"], reply_markup=reply_markup)
            else:
                label = "pipeline" if effective_mode == "pipeline" else "solo"
                reply = f"<b>amp ({label}):</b>\n\n{_md_to_html(result['answer'])}"
                try:
                    await update.message.reply_text(reply, parse_mode="HTML")
                except Exception:
                    await update.message.reply_text(result["answer"])

            # Update context
            context.append({"role": "user", "content": query})
            context.append({"role": "assistant", "content": result["answer"]})
            if len(context) > 20:
                self._contexts[user_id] = context[-20:]

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            err_text = f"❌ 오류: {str(e)[:200]}"
            if status_msg:
                try:
                    await status_msg.edit_text(err_text)
                except Exception:
                    await update.message.reply_text(err_text)
            else:
                await update.message.reply_text(err_text)

    async def feedback_handler(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Handle thumbs up/down feedback and save to KG as an edge."""
        query = update.callback_query
        await query.answer()
        data = query.data  # "feedback_good_abc123" or "feedback_bad_abc123"

        if data.startswith("feedback_good_"):
            rating = "positive"
            node_id = data[len("feedback_good_"):]
            weight = 1.0
        else:
            rating = "negative"
            node_id = data[len("feedback_bad_"):]
            weight = -1.0

        try:
            self.kg.relate(node_id, node_id, f"user_feedback_{rating}", weight)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("피드백 저장됐어! KG에 반영됐어 🧠", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Feedback save failed: {e}", exc_info=True)
            await query.message.reply_text("피드백 저장 실패 😅")


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

    kg_path = Path(config["amp"].get("kg_path", "~/.amp/kg.db")).expanduser()
    kg = KnowledgeGraph(kg_path)

    bot = AmpBot(config, kg)

    # Discover built-in plugins
    bot.plugin_registry.discover()
    # Discover external plugins from ~/.amp/plugins/ (SKILL.md or .py)
    try:
        from amp.plugins.skill_loader import discover_external
        discover_external(bot.plugin_registry)
    except Exception as e:
        logger.warning(f"외부 플러그인 로딩 실패 (무시): {e}")

    app = Application.builder().token(token).build()

    # Core command handlers
    app.add_handler(CommandHandler("start", bot.cmd_start))
    app.add_handler(CommandHandler("mode", bot.cmd_mode))
    app.add_handler(CommandHandler("stats", bot.cmd_stats))
    app.add_handler(CommandHandler("clear", bot.cmd_clear))

    # Model & plugin management
    app.add_handler(CommandHandler("model", bot.cmd_model))
    app.add_handler(CommandHandler("plugins", bot.cmd_plugins))
    app.add_handler(CommandHandler("plugin", bot.cmd_plugin))

    # Image generation
    app.add_handler(CommandHandler("imagine", bot.cmd_imagine))

    # Feedback callbacks
    app.add_handler(CallbackQueryHandler(bot.feedback_handler, pattern="^feedback_"))

    # Photo handler (image vision)
    app.add_handler(MessageHandler(filters.PHOTO, bot.handle_photo))

    # Text message handler (plugins + amp router)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))

    # Let plugins register their own handlers (e.g. mcp_bridge → /mcp)
    for plugin in bot.plugin_registry.all():
        plugin.setup(app, config)

    logging.basicConfig(level=logging.INFO)
    logger.info("Starting amp Telegram bot...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_bot()
