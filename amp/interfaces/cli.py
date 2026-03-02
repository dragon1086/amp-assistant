"""CLI interface for amp.

Supports two modes:
  1. Single query: amp "your question"
  2. Interactive REPL: amp (no args)

Usage:
  amp "hello"
  amp --mode emergent "should I use PostgreSQL or MongoDB?"
  amp --mode pipeline "write a Python file sorter"
  amp  # starts interactive REPL
"""

import asyncio
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.text import Text

from amp.cli.plugin_cmd import plugin
from amp.config import ensure_amp_dir, load_config, save_config, DEFAULT_CONFIG_PATH
from amp.core import emergent, router, solo
from amp.core import pipeline_engine as pipeline
from amp.core.kg import KnowledgeGraph
from amp.core.metrics import format_cser
from amp.core.user_config import UserConfigStore
from amp.plugins.registry import _registry as _plugin_registry
from amp.plugins.skill_loader import discover_external

console = Console()


def _print_banner():
    console.print(
        Panel(
            "[bold cyan]amp[/bold cyan] — Two minds. One answer.\n"
            "[dim]Local · Open-source · Privacy-first personal assistant[/dim]",
            expand=False,
            border_style="cyan",
        )
    )
    console.print("[dim]Type your question or /help for commands[/dim]\n")


def _print_solo_result(result: dict, mode_label: str):
    console.print(f"\n[bold green]amp ({mode_label}):[/bold green]")
    console.print(Markdown(result["answer"]))
    console.print()


def _print_pipeline_result(result: dict):
    console.print(f"\n[bold blue]amp (pipeline):[/bold blue]")
    console.print(Markdown(result["answer"]))
    console.print()


def _print_emergent_result(result: dict):
    cser = result["cser"]
    confidence = result["confidence"]

    console.print("\n[bold yellow]🤔 분석 중... (emergent mode)[/bold yellow]\n")

    # Persona header
    persona_a = result.get("persona_a", "분석적 전문가")
    persona_b = result.get("persona_b", "공감적 조언자")
    diversity = result.get("persona_diversity", "")
    diversity_str = f" · 다양성 {diversity}" if diversity else ""
    console.print(f"[dim]페르소나 도메인: {result.get('persona_domain', 'default')}{diversity_str}[/dim]\n")

    # Agent A
    label_a = result.get("agent_a_label", "Agent A")
    label_b = result.get("agent_b_label", "Agent B")
    console.print(Panel(
        result["agent_a"],
        title=f"[cyan]Agent A ({label_a}) — {persona_a}[/cyan]",
        border_style="cyan",
        expand=False,
    ))

    # Agent B
    console.print(Panel(
        result["agent_b"],
        title=f"[magenta]Agent B ({label_b}) — {persona_b}[/magenta]",
        border_style="magenta",
        expand=False,
    ))

    console.print(Rule(style="dim"))

    # Agreements / Conflicts
    if result["agreements"]:
        console.print("[bold green]✓ 합의된 사항:[/bold green]")
        for a in result["agreements"][:3]:
            console.print(f"  • {a}")

    if result["conflicts"]:
        console.print("[bold red]⚡ 이견:[/bold red]")
        for c in result["conflicts"][:3]:
            console.print(f"  • {c}")

    if result["agreements"] or result["conflicts"]:
        console.print()

    # Final answer
    console.print("[bold green]✅ 결론:[/bold green]")
    console.print(Markdown(result["answer"]))

    # CSER
    console.print()
    console.print(f"[bold]📊 신뢰도:[/bold] {format_cser(cser, confidence)}")

    # Insight panel
    if result.get("insights"):
        ins = result["insights"]
        lines = []
        if ins.get("agreements"):
            lines.append("[green]🤝 합의[/green]")
            for a in ins["agreements"][:2]:
                lines.append(f"  • {a}")
        if ins.get("gpt_only"):
            lines.append("\n[blue]🔵 GPT만 발견[/blue]")
            for a in ins["gpt_only"][:2]:
                lines.append(f"  • {a}")
        if ins.get("claude_only"):
            lines.append("\n[orange1]🟠 Claude만 발견[/orange1]")
            for a in ins["claude_only"][:2]:
                lines.append(f"  • {a}")
        if ins.get("trust_reason"):
            lines.append(f"\n[dim]💡 {ins['trust_reason']}[/dim]")
        if lines:
            console.print(Panel("\n".join(lines), title="📊 독창성 & 신뢰도", border_style="dim"))

    console.print(Rule(style="dim"))
    console.print()


async def _process_query(
    query: str,
    mode: str,
    context: list[dict],
    config: dict,
    kg: KnowledgeGraph,
) -> dict:
    """Route query to appropriate engine and return result."""
    effective_mode = router.detect_mode(query, mode)

    with console.status(f"[dim]Processing ({effective_mode} mode)...[/dim]", spinner="dots"):
        if effective_mode == "solo":
            result = await asyncio.to_thread(solo.run, query, context, config)
        elif effective_mode == "pipeline":
            result = await asyncio.to_thread(pipeline.run, query, context, config)
        else:  # emergent
            result = await asyncio.to_thread(emergent.run, query, context, config)

    # Auto-save emergent insights to KG
    if effective_mode == "emergent" and result.get("answer"):
        tags = ["emergent", "auto"]
        node_id = kg.add(
            f"Q: {query}\nA: {result['answer'][:500]}",
            tags=tags,
        )
        result["kg_node_id"] = node_id

    result["effective_mode"] = effective_mode
    return result


def _display_result(result: dict):
    """Display result based on mode."""
    mode = result.get("effective_mode", result.get("mode", "solo"))

    if mode == "emergent":
        _print_emergent_result(result)
    elif mode == "pipeline":
        _print_pipeline_result(result)
    else:
        _print_solo_result(result, mode)

    if "kg_node_id" in result:
        console.print(f"[dim]💾 KG에 저장됨 (node #{result['kg_node_id']})[/dim]\n")


def _handle_command(
    cmd: str,
    config: dict,
    kg: KnowledgeGraph,
    session_stats: dict,
    user_config_store: "UserConfigStore | None" = None,
    plugin_reg=None,
) -> bool:
    """Handle REPL slash/backslash commands. Returns True if handled."""
    cmd = cmd.strip()

    if cmd in ("/help", "/h"):
        console.print(Panel(
            "[bold]REPL Commands:[/bold]\n"
            "  [cyan]/help[/cyan]              This help\n"
            "  [cyan]/stats[/cyan]             Show KG and session stats\n"
            "  [cyan]/mode[/cyan] MODE         Set mode (auto/solo/pipeline/emergent)\n"
            "  [cyan]/clear[/cyan]             Clear conversation history\n"
            "  [cyan]/quit[/cyan]              Exit amp\n"
            "\n"
            "[bold]Plugin Commands:[/bold]\n"
            "  [cyan]\\plugin list[/cyan]        List all plugins and their status\n"
            "  [cyan]\\plugin on[/cyan] NAME     Enable a plugin\n"
            "  [cyan]\\plugin off[/cyan] NAME    Disable a plugin",
            title="amp help",
            border_style="dim",
        ))
        return True

    if cmd == "/stats":
        stats = kg.stats()
        avg_cser = (
            session_stats["total_cser"] / session_stats["emergent_count"]
            if session_stats["emergent_count"] > 0
            else 0.0
        )
        console.print(Panel(
            f"[bold]KG:[/bold] {stats['node_count']} nodes, {stats['edge_count']} edges\n"
            f"[bold]Sessions:[/bold] {session_stats['queries']} queries\n"
            f"[bold]CSER avg:[/bold] {avg_cser:.2f}",
            title="amp stats",
            border_style="dim",
        ))
        return True

    if cmd.startswith("/mode"):
        parts = cmd.split()
        if len(parts) == 2:
            new_mode = parts[1].lower()
            if new_mode in ("auto", "solo", "pipeline", "emergent"):
                config["amp"]["default_mode"] = new_mode
                console.print(f"[green]Mode set to: {new_mode}[/green]")
            else:
                console.print(f"[red]Unknown mode: {new_mode}. Use: auto/solo/pipeline/emergent[/red]")
        else:
            console.print(f"[dim]Current mode: {config['amp']['default_mode']}[/dim]")
        return True

    if cmd == "/clear":
        session_stats["context"].clear()
        console.print("[dim]Conversation history cleared.[/dim]")
        return True

    if cmd in ("/quit", "/exit", "/q"):
        console.print("[dim]Goodbye![/dim]")
        sys.exit(0)

    # \plugin commands (backslash prefix to distinguish from regular questions)
    if cmd.startswith("\\plugin"):
        parts = cmd.split()
        sub = parts[1].lower() if len(parts) > 1 else "list"

        if sub == "list":
            if plugin_reg is None:
                console.print("[dim]플러그인 없음 (registry not loaded)[/dim]")
                return True
            plugins = plugin_reg.all()
            if not plugins:
                console.print("[dim]등록된 플러그인 없음[/dim]")
                return True
            user_cfg = user_config_store.get(0) if user_config_store else {}
            lines = ["[bold]🔌 플러그인 목록:[/bold]\n"]
            for p in plugins:
                enabled = user_cfg.get("plugins", {}).get(p.name, p.enabled_by_default)
                status = "[green]✅[/green]" if enabled else "[red]❌[/red]"
                lines.append(f"  {status} [cyan]{p.name}[/cyan] — {p.description or '-'}")
            lines.append("\n[dim]토글: \\plugin on <이름>  /  \\plugin off <이름>[/dim]")
            console.print("\n".join(lines))
            return True

        if sub in ("on", "off") and len(parts) >= 3:
            name = parts[2]
            if plugin_reg is None or plugin_reg.get(name) is None:
                console.print(f"[red]플러그인을 찾을 수 없습니다: {name}[/red]")
                console.print("[dim]목록 확인: \\plugin list[/dim]")
                return True
            if user_config_store is None:
                console.print("[red]user_config_store not available[/red]")
                return True
            enabled = sub == "on"
            cfg = user_config_store.get(0)
            cfg.setdefault("plugins", {})[name] = enabled
            user_config_store.set(0, cfg)
            status_text = "활성화" if enabled else "비활성화"
            console.print(f"[green]✅ {name} 플러그인 {status_text}됨[/green]")
            return True

        console.print(
            "[dim]사용법: \\plugin list  /  \\plugin on <이름>  /  \\plugin off <이름>[/dim]"
        )
        return True

    return False


async def _repl(config: dict, kg: KnowledgeGraph, initial_mode: str):
    """Interactive REPL loop."""
    _print_banner()

    context: list[dict] = []
    session_stats = {
        "queries": 0,
        "emergent_count": 0,
        "total_cser": 0.0,
        "context": context,
    }

    # Set up plugin registry and per-user config store (user_id=0 for local single user)
    user_config_db = Path.home() / ".amp" / "user_config.db"
    user_config_store = UserConfigStore(user_config_db)
    plugin_reg = _plugin_registry
    plugin_reg.discover()
    try:
        discover_external(plugin_reg)
    except Exception:
        pass

    while True:
        try:
            query = Prompt.ask("[bold cyan]>[/bold cyan]", console=console)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        query = query.strip()
        if not query:
            continue

        # Handle commands (/ and \ prefixes)
        if query.startswith("/") or query.startswith("\\"):
            _handle_command(query, config, kg, session_stats, user_config_store, plugin_reg)
            continue

        try:
            result = await _process_query(
                query,
                config["amp"].get("default_mode", "auto"),
                context,
                config,
                kg,
            )
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            continue

        _display_result(result)

        # Update context
        context.append({"role": "user", "content": query})
        context.append({"role": "assistant", "content": result["answer"]})
        # Keep last 10 exchanges
        if len(context) > 20:
            context[:] = context[-20:]

        # Update stats
        session_stats["queries"] += 1
        if result.get("effective_mode") == "emergent":
            session_stats["emergent_count"] += 1
            session_stats["total_cser"] += result.get("cser", 0.0)


@click.command()
@click.argument("query", required=False)
@click.option("--mode", "-m", default=None,
              type=click.Choice(["auto", "solo", "pipeline", "emergent"]),
              help="Force a specific mode")
@click.option("--config-path", default=None, help="Path to config.yaml")
def main(query: str | None, mode: str | None, config_path: str | None):
    """amp — local personal assistant with emergent 2-agent collaboration.

    Run without arguments for interactive REPL mode.
    Pass a query for single-shot mode.

    \b
    Examples:
      amp "hello"
      amp --mode emergent "should I use PostgreSQL or MongoDB?"
      amp --mode pipeline "write a Python file sorter"
      amp  # interactive REPL
    """
    config = load_config(Path(config_path) if config_path else None)

    # Check API key — OpenAI 또는 Claude OAuth 중 하나면 OK
    has_openai = bool(config["llm"].get("api_key") or os.environ.get("OPENAI_API_KEY"))
    has_claude = bool(
        os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        or os.environ.get("ANTHROPIC_API_KEY")
        or config.get("agents", {}).get("agent_b", {}).get("provider") == "anthropic_oauth"
    )
    if not has_openai and not has_claude:
        console.print("[red]❌ API 키가 없습니다.[/red]")
        console.print("  [bold]amp setup[/bold] 을 실행해 설정하거나:")
        console.print("  [dim]export OPENAI_API_KEY=sk-...[/dim]")
        console.print("  [dim]export CLAUDE_CODE_OAUTH_TOKEN=...[/dim]")
        sys.exit(1)

    kg_path = Path(config["amp"].get("kg_path", "~/.amp/kg.json")).expanduser()
    kg = KnowledgeGraph(kg_path)

    effective_mode = mode or config["amp"].get("default_mode", "auto")

    if query:
        # Single-shot mode
        async def run_once():
            result = await _process_query(query, effective_mode, [], config, kg)
            _display_result(result)

        asyncio.run(run_once())
    else:
        # Interactive REPL
        asyncio.run(_repl(config, kg, effective_mode))


def _mask(val: str) -> str:
    return f"...{val[-6:]}" if len(val) > 6 else "(설정 안 됨)"


def _write_env(env_path: Path, entries: dict[str, str]) -> None:
    """~/.amp/.env 파일에 환경변수 저장 (기존 값 유지, 새 값 추가/갱신)."""
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()
    existing.update({k: v for k, v in entries.items() if v})
    lines = ["# amp 환경변수 — amp setup으로 자동 생성", "# 민감 정보가 포함됩니다. git에 커밋하지 마세요.\n"]
    for k, v in existing.items():
        lines.append(f"{k}={v}")
    env_path.write_text("\n".join(lines) + "\n")
    env_path.chmod(0o600)


@click.command()
def setup():
    """amp 설정 마법사 — API 키, 모델, 텔레그램 봇, 플러그인 설정."""
    console.print(Panel(
        "[bold cyan]✨ amp setup[/bold cyan]\n"
        "[dim]Two minds. One answer.[/dim]\n\n"
        "설정 마법사가 amp를 처음부터 끝까지 안내합니다.\n"
        "각 단계에서 Enter를 누르면 현재 값을 유지합니다.",
        border_style="cyan",
        expand=False,
    ))

    amp_dir = ensure_amp_dir()
    env_path = amp_dir / ".env"
    config = load_config()
    env_entries: dict[str, str] = {}

    # ── STEP 1: Agent A (OpenAI) ────────────────────────────────
    console.print("\n[bold]━━ STEP 1/5: Agent A — OpenAI[/bold]")
    console.print("[dim]Emergent 2-agent 모드에서 Agent A로 사용됩니다.[/dim]")
    current = config.get("agents", {}).get("agent_a", {}).get("model", "gpt-4o")
    console.print(f"  현재 모델: [cyan]{current}[/cyan]")

    openai_key = Prompt.ask(
        "  OpenAI API 키 (Enter = 유지)", default="", password=True, console=console
    ).strip()
    if openai_key:
        env_entries["OPENAI_API_KEY"] = openai_key
        config.setdefault("agents", {}).setdefault("agent_a", {})["provider"] = "openai"

    a_model = Prompt.ask(
        "  Agent A 모델", default=current, console=console
    ).strip()
    config.setdefault("agents", {}).setdefault("agent_a", {})["model"] = a_model

    # ── STEP 2: Agent B (Claude) ────────────────────────────────
    console.print("\n[bold]━━ STEP 2/5: Agent B — Claude[/bold]")
    console.print("[dim]Emergent 모드 핵심 — Agent B가 Agent A와 독립적으로 분석합니다.[/dim]")
    console.print()
    console.print("  [bold green]Claude OAuth (무료)[/bold green] — Claude Code가 설치되어 있으면 API 비용 없이 사용 가능")
    console.print("  [dim]Claude Code 설치: https://claude.ai/download[/dim]")
    console.print()
    console.print("  [bold yellow]Anthropic API 키[/bold yellow] — API 키가 있으면 직접 연결")

    b_choice = Prompt.ask(
        "  Agent B 방식 선택",
        choices=["oauth", "api", "skip"],
        default="oauth",
        console=console,
    )

    if b_choice == "oauth":
        oauth_token = Prompt.ask(
            "  CLAUDE_CODE_OAUTH_TOKEN (Enter = 환경변수 자동 사용)",
            default="", password=True, console=console
        ).strip()
        if oauth_token:
            env_entries["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
        config.setdefault("agents", {}).setdefault("agent_b", {})["provider"] = "anthropic_oauth"
        config["agents"]["agent_b"]["model"] = "claude-sonnet-4-6"
        console.print("  [green]✓ Claude OAuth 설정 완료[/green]")
    elif b_choice == "api":
        anthropic_key = Prompt.ask(
            "  Anthropic API 키", default="", password=True, console=console
        ).strip()
        if anthropic_key:
            env_entries["ANTHROPIC_API_KEY"] = anthropic_key
        b_model = Prompt.ask(
            "  Agent B 모델", default="claude-sonnet-4-6", console=console
        ).strip()
        config.setdefault("agents", {}).setdefault("agent_b", {})["provider"] = "anthropic"
        config["agents"]["agent_b"]["model"] = b_model
        console.print("  [green]✓ Anthropic API 설정 완료[/green]")
    else:
        console.print("  [dim]Agent B 스킵 — solo/pipeline 모드만 사용 가능[/dim]")

    # ── STEP 3: Telegram Bot ────────────────────────────────────
    console.print("\n[bold]━━ STEP 3/5: 텔레그램 봇[/bold]")
    console.print("[dim]텔레그램에서 amp를 사용하려면 봇 토큰이 필요합니다.[/dim]")
    console.print("  1. 텔레그램에서 @BotFather 검색")
    console.print("  2. /newbot 입력 → 봇 이름 설정")
    console.print("  3. 발급된 토큰을 아래에 입력")

    tg_token = Prompt.ask(
        "  텔레그램 봇 토큰 (Enter = 스킵)",
        default="", password=True, console=console
    ).strip()
    if tg_token:
        env_entries["TELEGRAM_BOT_TOKEN"] = tg_token
        config.setdefault("telegram", {})["token"] = "${TELEGRAM_BOT_TOKEN}"
        console.print("  [green]✓ 텔레그램 봇 토큰 저장됨[/green]")
    else:
        console.print("  [dim]텔레그램 스킵 — CLI/REPL 모드로만 사용[/dim]")

    # ── STEP 4: 이미지 생성 플러그인 ───────────────────────────
    console.print("\n[bold]━━ STEP 4/5: 이미지 생성 플러그인 (선택)[/bold]")
    console.print("[dim]/imagine 커맨드로 이미지를 생성할 수 있습니다.[/dim]")
    console.print()
    console.print("  [bold]나노바나나2[/bold] (Google Gemini 3.1 Flash Image) — ~$0.10/장, 최대 4K")
    console.print("  [bold]DALL-E 3[/bold] — OpenAI DALL-E 3 (OpenAI API 키 필요)")
    console.print("  [bold]로컬[/bold] — Automatic1111 / ComfyUI 로컬 서버")
    console.print("  [bold]스킵[/bold] — 이미지 생성 비활성화")

    img_choice = Prompt.ask(
        "  이미지 생성 백엔드",
        choices=["nanonbanana2", "dalle3", "local", "skip"],
        default="skip",
        console=console,
    )

    if img_choice == "nanonbanana2":
        google_key = Prompt.ask(
            "  Google API 키", default="", password=True, console=console
        ).strip()
        if google_key:
            env_entries["GOOGLE_API_KEY"] = google_key
        config.setdefault("plugins", {}).setdefault("image_gen", {})["backend"] = "nanonbanana2"
        console.print("  [green]✓ 나노바나나2 설정 완료[/green]")
        console.print("  [dim]pip install 'amp-assistant[nanonbanana2]' 로 SDK 설치 필요[/dim]")
    elif img_choice == "dalle3":
        config.setdefault("plugins", {}).setdefault("image_gen", {})["backend"] = "dalle3"
        console.print("  [green]✓ DALL-E 3 설정 완료 (OpenAI API 키 사용)[/green]")
    elif img_choice == "local":
        local_url = Prompt.ask(
            "  로컬 서버 URL", default="http://localhost:7860", console=console
        ).strip()
        config.setdefault("plugins", {}).setdefault("image_gen", {})["backend"] = "local"
        config["plugins"]["image_gen"]["local_url"] = local_url
        console.print(f"  [green]✓ 로컬 서버 설정: {local_url}[/green]")
    else:
        console.print("  [dim]이미지 생성 스킵[/dim]")

    # ── STEP 5: 기본 모드 ───────────────────────────────────────
    console.print("\n[bold]━━ STEP 5/5: 기본 설정[/bold]")
    current_mode = config.get("amp", {}).get("default_mode", "auto")
    console.print("  [bold]auto[/bold]    — 질문 유형에 따라 자동 선택 (권장)")
    console.print("  [bold]solo[/bold]    — 단일 AI, 빠른 답변")
    console.print("  [bold]emergent[/bold] — 2-agent 독립 분석 (최고 품질)")
    console.print("  [bold]pipeline[/bold] — 계획→실행→검토→수정 (코드/문서)")

    default_mode = Prompt.ask(
        "  기본 모드",
        choices=["auto", "solo", "pipeline", "emergent"],
        default=current_mode,
        console=console,
    )
    config.setdefault("amp", {})["default_mode"] = default_mode

    # ── 저장 ────────────────────────────────────────────────────
    save_config(config)
    if env_entries:
        _write_env(env_path, env_entries)

    console.print("\n" + "─" * 50)
    console.print("[bold green]✅ 설정 완료![/bold green]\n")
    console.print(f"  📄 config: [dim]{DEFAULT_CONFIG_PATH}[/dim]")
    if env_entries:
        console.print(f"  🔑 env:    [dim]{env_path}[/dim] (chmod 600)")
    console.print()

    # 다음 단계 안내
    if env_entries.get("TELEGRAM_BOT_TOKEN"):
        console.print("  [bold]텔레그램 봇 시작:[/bold]")
        console.print("    [cyan]bash start_bot.sh[/cyan]")
    console.print()
    console.print("  [bold]CLI 테스트:[/bold]")
    console.print("    [cyan]amp '안녕!'[/cyan]")
    console.print("    [cyan]amp --mode emergent '이 결정 어떻게 생각해?'[/cyan]")
    console.print()
    console.print("  [bold]플러그인 설치:[/bold]")
    console.print("    [cyan]amp plugin install https://github.com/user/my-plugin[/cyan]")
    console.print("    [cyan]amp plugin new my-plugin[/cyan]  # 새 플러그인 만들기")
    console.print()


@click.group(invoke_without_command=True)
@click.pass_context
@click.argument("query", required=False)
@click.option("--mode", "-m", default=None,
              type=click.Choice(["auto", "solo", "pipeline", "emergent"]),
              help="Force a specific mode")
@click.option("--config-path", default=None, help="Path to config.yaml")
def cli(ctx, query, mode, config_path):
    """amp — local personal assistant with emergent 2-agent collaboration."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(main, query=query, mode=mode, config_path=config_path)


cli.add_command(setup)
cli.add_command(main, name="ask")
cli.add_command(plugin)


if __name__ == "__main__":
    cli()
