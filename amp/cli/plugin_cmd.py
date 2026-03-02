"""Plugin management CLI for amp.

Usage:
    amp plugin install <github_url|local_path>
    amp plugin list
    amp plugin remove <name>

SOURCE 형식:
    https://github.com/user/repo         GitHub 리포지토리 (git clone)
    https://.../plugin.py                단일 Python 파일 다운로드
    /path/to/plugin.py                   로컬 Python 파일
    /path/to/plugin_dir/                 로컬 디렉토리 (SKILL.md 포함 가능)
"""

import shutil
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from amp.plugins.skill_loader import EXTERNAL_PLUGINS_DIR, load_skill_from_dir, parse_skill_md

console = Console()


@click.group()
def plugin() -> None:
    """amp 플러그인 관리."""
    pass


@plugin.command("install")
@click.argument("source")
def install(source: str) -> None:
    """GitHub URL 또는 로컬 경로에서 플러그인 설치."""
    EXTERNAL_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    source_path = Path(source).expanduser()

    if source_path.exists():
        _install_local(source_path)
    elif source.startswith("http://") or source.startswith("https://"):
        _install_remote(source)
    else:
        console.print(f"[red]설치 실패: '{source}'를 찾을 수 없습니다.[/red]")
        sys.exit(1)


def _install_local(source: Path) -> None:
    """로컬 파일 또는 디렉토리 설치."""
    if source.is_file() and source.suffix == ".py":
        dest = EXTERNAL_PLUGINS_DIR / source.name
        shutil.copy2(source, dest)
        console.print(f"[green]✓ 설치됨: {source.name}[/green] → {dest}")
    elif source.is_dir():
        dest = EXTERNAL_PLUGINS_DIR / source.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
        console.print(f"[green]✓ 설치됨: {source.name}/[/green] → {dest}")
    else:
        console.print(f"[red]지원하지 않는 파일 형식: {source}[/red] (.py 파일 또는 디렉토리만 가능)")
        sys.exit(1)


def _install_remote(url: str) -> None:
    """원격 URL에서 플러그인 설치."""
    # Raw Python 파일 직접 다운로드
    if url.endswith(".py") or "raw.githubusercontent.com" in url:
        try:
            import httpx
        except ImportError:
            console.print("[red]httpx가 필요합니다: pip install httpx[/red]")
            sys.exit(1)

        file_name = url.rstrip("/").split("/")[-1]
        if not file_name.endswith(".py"):
            file_name += ".py"
        dest = EXTERNAL_PLUGINS_DIR / file_name

        with console.status(f"[dim]다운로드 중: {url}[/dim]"):
            resp = httpx.get(url, follow_redirects=True, timeout=30)
            resp.raise_for_status()
            dest.write_bytes(resp.content)

        console.print(f"[green]✓ 설치됨: {file_name}[/green]")
        return

    # GitHub 리포지토리 git clone
    repo_name = url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    dest = EXTERNAL_PLUGINS_DIR / repo_name
    if dest.exists():
        console.print(
            f"[yellow]이미 설치됨: {repo_name}[/yellow] "
            f"(재설치: amp plugin remove {repo_name} && amp plugin install {url})"
        )
        sys.exit(1)

    with console.status(f"[dim]git clone: {url}[/dim]"):
        result = subprocess.run(
            ["git", "clone", "--depth=1", url, str(dest)],
            capture_output=True,
            text=True,
        )

    if result.returncode != 0:
        console.print(f"[red]git clone 실패:[/red]\n{result.stderr.strip()}")
        sys.exit(1)

    console.print(f"[green]✓ 설치됨: {repo_name}/[/green]")


@plugin.command("list")
def list_plugins() -> None:
    """설치된 플러그인 목록 표시."""
    if not EXTERNAL_PLUGINS_DIR.is_dir():
        console.print("[dim]설치된 플러그인 없음 (~/.amp/plugins/)[/dim]")
        return

    table = Table(title="설치된 플러그인 (~/.amp/plugins/)", show_header=True)
    table.add_column("이름", style="cyan", no_wrap=True)
    table.add_column("타입", style="dim")
    table.add_column("설명")
    table.add_column("기본 활성화", style="green", justify="center")

    found = False

    # 단일 .py 파일
    for py_file in sorted(EXTERNAL_PLUGINS_DIR.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        table.add_row(py_file.stem, ".py", "-", "✓")
        found = True

    # 서브디렉토리
    for sub_dir in sorted(EXTERNAL_PLUGINS_DIR.iterdir()):
        if not sub_dir.is_dir() or sub_dir.name.startswith("."):
            continue

        meta: dict = {}
        skill_md = sub_dir / "SKILL.md"
        if skill_md.exists():
            meta = parse_skill_md(skill_md.read_text(encoding="utf-8"))

        name = str(meta.get("name") or sub_dir.name)
        desc = str(meta.get("description") or "-")
        enabled = "✓" if meta.get("enabled_by_default", True) else "✗"
        type_label = "SKILL.md" if skill_md.exists() else "dir"

        table.add_row(name, type_label, desc, enabled)
        found = True

    if found:
        console.print(table)
    else:
        console.print("[dim]설치된 플러그인 없음[/dim]")


@plugin.command("new")
@click.argument("name")
def new_plugin(name: str) -> None:
    """새 플러그인 스캐폴딩 생성.

    NAME 이름의 플러그인 디렉토리를 ~/.amp/plugins/<NAME>/에 만들고
    SKILL.md와 scripts/main.py 보일러플레이트를 자동 생성합니다.
    """
    plugin_dir = EXTERNAL_PLUGINS_DIR / name
    if plugin_dir.exists():
        console.print(f"[yellow]이미 존재합니다: {plugin_dir}[/yellow]")
        console.print(f"[dim]설치하려면: amp plugin install {plugin_dir}[/dim]")
        sys.exit(1)

    plugin_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir = plugin_dir / "scripts"
    scripts_dir.mkdir()

    # SKILL.md 보일러플레이트
    skill_md = plugin_dir / "SKILL.md"
    skill_md.write_text(
        f"""---
# 플러그인 이름 (amp plugin list에 표시됨)
name: {name}

# 플러그인 한 줄 설명
description: {name} 플러그인 설명을 여기에 입력하세요

# true이면 봇 시작 시 자동 활성화
# false이면 /plugin on {name} 으로 수동 활성화
enabled_by_default: true
---

# {name}

이 플러그인은 ...

## 기능

- 기능 1
- 기능 2

## 사용법

텔레그램에서 메시지를 보내거나 REPL에서 `\\plugin on {name}` 으로 활성화하세요.
""",
        encoding="utf-8",
    )

    # scripts/main.py 보일러플레이트
    main_py = scripts_dir / "main.py"
    main_py.write_text(
        f'''"""
{name} 플러그인 — amp BasePlugin 구현 예시.

amp 플러그인은 BasePlugin을 상속하고 아래 두 메서드를 구현해야 합니다:
  - can_handle(update): 이 플러그인이 메시지를 처리할지 여부
  - handle(update, context, config, user_config): 실제 처리 로직
"""

from amp.plugins.base import BasePlugin


class {name.replace("-", "_").title().replace("_", "")}Plugin(BasePlugin):
    name = "{name}"
    description = "{name} 플러그인 설명"
    enabled_by_default = True

    def can_handle(self, update) -> bool:
        """이 플러그인이 처리할 메시지 조건을 반환합니다.

        예시: 특정 키워드로 시작하는 메시지만 처리
        """
        text = getattr(getattr(update, "message", None), "text", None) or ""
        return text.lower().startswith("!{name}")

    async def handle(self, update, context, config: dict, user_config: dict) -> str | None:
        """메시지를 처리하고 응답 문자열을 반환합니다.

        None을 반환하면 amp가 직접 응답한 것으로 간주합니다
        (예: update.message.reply_text()를 직접 호출한 경우).
        """
        text = update.message.text or ""
        # TODO: 여기에 플러그인 로직을 구현하세요
        return f"[{name}] 받은 메시지: {{text}}"

    def get_commands(self) -> list[tuple[str, str]]:
        """이 플러그인이 제공하는 봇 커맨드 목록 (command, description)."""
        return []

    def get_system_prompt(self) -> str | None:
        """LLM에 주입할 추가 시스템 프롬프트. None이면 주입 안 함."""
        return None
''',
        encoding="utf-8",
    )

    console.print(f"[green]✓ 플러그인 생성됨:[/green] {plugin_dir}")
    console.print()
    console.print("[bold]다음 단계:[/bold]")
    console.print(f"  1. [cyan]{plugin_dir / 'SKILL.md'}[/cyan] 에서 메타데이터 수정")
    console.print(f"  2. [cyan]{main_py}[/cyan] 에서 플러그인 로직 구현")
    console.print(f"  3. [cyan]amp plugin install {plugin_dir}[/cyan] 로 설치")
    console.print()
    console.print("[dim]개발자 가이드: docs/plugin-guide.md[/dim]")


@plugin.command("remove")
@click.argument("name")
def remove(name: str) -> None:
    """플러그인 제거.

    NAME은 플러그인 파일명(확장자 제외) 또는 디렉토리명.
    """
    removed = False

    # .py 파일 시도
    py_target = EXTERNAL_PLUGINS_DIR / f"{name}.py"
    if py_target.exists():
        py_target.unlink()
        console.print(f"[green]✓ 제거됨: {name}.py[/green]")
        removed = True

    # 디렉토리 시도
    dir_target = EXTERNAL_PLUGINS_DIR / name
    if dir_target.is_dir():
        shutil.rmtree(dir_target)
        console.print(f"[green]✓ 제거됨: {name}/[/green]")
        removed = True

    if not removed:
        console.print(f"[red]플러그인을 찾을 수 없습니다: {name}[/red]")
        console.print("[dim]설치된 목록: amp plugin list[/dim]")
        sys.exit(1)
