"""SKILL.md 기반 플러그인 로더 — OpenClaw/AgentSkills 호환.

SKILL.md 포맷:
    ---
    name: my_skill
    description: 내 스킬 설명
    enabled_by_default: true
    ---

    # My Skill
    ...

사용법:
    from amp.plugins.skill_loader import discover_external
    from amp.plugins.registry import _registry

    discover_external(_registry)
"""

import importlib.util
import re
from pathlib import Path
from typing import Any

import yaml

from amp.plugins.base import BasePlugin
from amp.plugins.registry import PluginRegistry

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)

EXTERNAL_PLUGINS_DIR = Path.home() / ".amp" / "plugins"


def parse_skill_md(content: str) -> dict[str, Any]:
    """SKILL.md YAML frontmatter 파싱.

    Returns:
        파싱된 메타데이터 dict. frontmatter 없거나 파싱 실패 시 빈 dict.
    """
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _load_plugin_from_py(py_file: Path, meta: dict[str, Any]) -> BasePlugin | None:
    """Python 파일에서 BasePlugin 서브클래스를 로드하고 SKILL.md 메타데이터를 적용."""
    spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as e:
        print(f"[SkillLoader] {py_file.name} 로드 실패: {e}")
        return None

    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (
            isinstance(attr, type)
            and issubclass(attr, BasePlugin)
            and attr is not BasePlugin
        ):
            instance = attr()
            # SKILL.md 메타데이터로 오버라이드 (있는 경우만)
            if meta.get("name"):
                instance.name = meta["name"]
            if meta.get("description"):
                instance.description = meta["description"]
            if "enabled_by_default" in meta:
                instance.enabled_by_default = bool(meta["enabled_by_default"])
            return instance

    return None


def load_skill_from_dir(skill_dir: Path) -> BasePlugin | None:
    """SKILL.md와 Python 파일이 있는 디렉토리에서 플러그인 로드.

    탐색 순서:
      1. skill_dir/scripts/*.py
      2. skill_dir/*.py
    SKILL.md가 없어도 Python 파일만 있으면 로드 시도.
    """
    skill_md = skill_dir / "SKILL.md"
    meta: dict[str, Any] = {}

    if skill_md.exists():
        meta = parse_skill_md(skill_md.read_text(encoding="utf-8"))

    scripts_dir = skill_dir / "scripts"
    search_dirs: list[Path] = []
    if scripts_dir.is_dir():
        search_dirs.append(scripts_dir)
    search_dirs.append(skill_dir)

    for search_dir in search_dirs:
        for py_file in sorted(search_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            plugin = _load_plugin_from_py(py_file, meta)
            if plugin is not None:
                return plugin

    return None


def discover_external(registry: PluginRegistry, plugins_dir: Path | None = None) -> None:
    """~/.amp/plugins/ 에서 외부 플러그인 자동 탐색 및 등록.

    탐색 대상:
      - plugins_dir/*.py         직접 .py 파일
      - plugins_dir/<subdir>/    SKILL.md 또는 Python 파일이 있는 서브디렉토리
    """
    base_dir = plugins_dir or EXTERNAL_PLUGINS_DIR
    if not base_dir.is_dir():
        return

    # 1) 직접 .py 파일
    for py_file in sorted(base_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        plugin = _load_plugin_from_py(py_file, {})
        if plugin is not None:
            registry.register(plugin)

    # 2) 서브디렉토리 (SKILL.md 포함 여부 무관)
    for sub_dir in sorted(base_dir.iterdir()):
        if not sub_dir.is_dir() or sub_dir.name.startswith("."):
            continue
        plugin = load_skill_from_dir(sub_dir)
        if plugin is not None:
            registry.register(plugin)
