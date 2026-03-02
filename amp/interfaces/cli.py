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
    console.print(Panel(
        result["agent_a"],
        title=f"[cyan]Agent A — {persona_a}[/cyan]",
        border_style="cyan",
        expand=False,
    ))

    # Agent B
    console.print(Panel(
        result["agent_b"],
        title=f"[magenta]Agent B — {persona_b}[/magenta]",
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


def _handle_command(cmd: str, config: dict, kg: KnowledgeGraph, session_stats: dict) -> bool:
    """Handle REPL slash commands. Returns True if handled."""
    cmd = cmd.strip()

    if cmd in ("/help", "/h"):
        console.print(Panel(
            "[bold]REPL Commands:[/bold]\n"
            "  [cyan]/help[/cyan]       This help\n"
            "  [cyan]/stats[/cyan]      Show KG and session stats\n"
            "  [cyan]/mode[/cyan] MODE  Set mode (auto/solo/pipeline/emergent)\n"
            "  [cyan]/clear[/cyan]      Clear conversation history\n"
            "  [cyan]/quit[/cyan]       Exit amp",
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

    while True:
        try:
            query = Prompt.ask("[bold cyan]>[/bold cyan]", console=console)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        query = query.strip()
        if not query:
            continue

        # Handle commands
        if query.startswith("/"):
            _handle_command(query, config, kg, session_stats)
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

    # Check API key
    if not config["llm"].get("api_key"):
        console.print("[red]No API key found.[/red]")
        console.print("Run [bold]amp setup[/bold] or set [bold]OPENAI_API_KEY[/bold] env var.")
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


@click.command()
def setup():
    """Interactive setup wizard for amp."""
    console.print(Panel(
        "[bold cyan]amp setup[/bold cyan]\n"
        "Configure your local personal assistant",
        border_style="cyan",
    ))

    ensure_amp_dir()

    config = load_config()

    # API Key
    current_key = config["llm"].get("api_key", "")
    masked = f"...{current_key[-6:]}" if len(current_key) > 6 else "(not set)"
    console.print(f"\nCurrent OpenAI API key: [dim]{masked}[/dim]")

    new_key = Prompt.ask(
        "OpenAI API key (press Enter to keep current)",
        default="",
        password=True,
        console=console,
    )
    if new_key.strip():
        config["llm"]["api_key"] = new_key.strip()

    # Model
    console.print(f"\nCurrent model: [dim]{config['llm']['model']}[/dim]")
    model = Prompt.ask(
        "Model (gpt-4o-mini/gpt-4o/gpt-4.1)",
        default=config["llm"]["model"],
        console=console,
    )
    config["llm"]["model"] = model

    # Default mode
    console.print(f"\nCurrent default mode: [dim]{config['amp']['default_mode']}[/dim]")
    default_mode = Prompt.ask(
        "Default mode (auto/solo/pipeline/emergent)",
        default=config["amp"]["default_mode"],
        console=console,
    )
    config["amp"]["default_mode"] = default_mode

    # Save
    save_config(config)
    console.print(f"\n[green]✓ Config saved to {DEFAULT_CONFIG_PATH}[/green]")
    console.print("[dim]Run [bold]amp 'hello'[/bold] to test your setup.[/dim]")


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
