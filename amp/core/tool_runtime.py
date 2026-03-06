"""Tool runtime — LLM이 호출할 수 있는 도구 실행기."""

import os
import subprocess
import json
from pathlib import Path

# 허용된 작업 경로 (보안)
ALLOWED_PATHS = [
    str(Path.home() / "amp"),
    str(Path.home() / ".amp"),
    str(Path.home() / "emergent"),
]

# 금지 패턴 (destructive commands)
BLOCKED_PATTERNS = [
    "rm -rf", "sudo", "mkfs", "dd if=", "> /dev/", ":(){ :|:& };:",
    "wget http", "curl http", "chmod 777", "chown root",
]

def _is_safe_path(path: str) -> bool:
    p = str(Path(path).resolve())
    return any(p.startswith(allowed) for allowed in ALLOWED_PATHS)

def _is_safe_command(cmd: str) -> bool:
    return not any(blocked in cmd for blocked in BLOCKED_PATTERNS)


def exec_command(command: str, workdir: str = None) -> dict:
    """셸 명령어를 실행하고 stdout/stderr/returncode 반환."""
    if not _is_safe_command(command):
        return {"error": f"Blocked command: {command}", "stdout": "", "returncode": -1}
    cwd = workdir or str(Path.home() / "amp")
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=30, cwd=cwd
        )
        return {
            "stdout": result.stdout[:3000],
            "stderr": result.stderr[:1000],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Timeout (30s)", "stdout": "", "returncode": -1}
    except Exception as e:
        return {"error": str(e), "stdout": "", "returncode": -1}


def fs_read(path: str) -> dict:
    """파일 내용 읽기 (최대 8000자)."""
    if not _is_safe_path(path):
        return {"error": f"Path not allowed: {path}"}
    try:
        content = Path(path).read_text(encoding="utf-8")
        return {"content": content[:8000], "truncated": len(content) > 8000}
    except Exception as e:
        return {"error": str(e)}


def fs_write(path: str, content: str) -> dict:
    """파일 쓰기."""
    if not _is_safe_path(path):
        return {"error": f"Path not allowed: {path}"}
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"success": True, "path": path}
    except Exception as e:
        return {"error": str(e)}


def fs_list(path: str) -> dict:
    """디렉토리 목록 반환."""
    if not _is_safe_path(path):
        return {"error": f"Path not allowed: {path}"}
    try:
        entries = []
        for p in sorted(Path(path).iterdir()):
            entries.append({"name": p.name, "type": "dir" if p.is_dir() else "file"})
        return {"entries": entries, "count": len(entries)}
    except Exception as e:
        return {"error": str(e)}


def claude_code(task: str, workdir: str = None) -> dict:
    """Claude Code를 서브프로세스로 실행."""
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    if not token:
        # ~/.zshrc에서 로드 시도
        import re
        try:
            zshrc = Path.home() / ".zshrc"
            m = re.search(r"CLAUDE_CODE_OAUTH_TOKEN='([^']+)'", zshrc.read_text())
            if m:
                token = m.group(1)
        except Exception:
            pass
    if not token:
        return {"error": "CLAUDE_CODE_OAUTH_TOKEN not found"}

    claude_bin = "/Users/rocky/.local/bin/claude"
    if not Path(claude_bin).exists():
        return {"error": f"claude binary not found at {claude_bin}"}

    cwd = workdir or str(Path.home() / "amp")
    # CLAUDECODE 등 중첩 방지 변수 제거 (OpenClaw 환경 호환)
    _STRIP = {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"}
    env = {k: v for k, v in os.environ.items() if k not in _STRIP}
    env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    try:
        result = subprocess.run(
            [claude_bin, "-p", "--dangerously-skip-permissions", task],
            capture_output=True, text=True, timeout=120, cwd=cwd, env=env
        )
        return {
            "stdout": result.stdout[:4000],
            "stderr": result.stderr[:1000],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Timeout (120s)"}
    except Exception as e:
        return {"error": str(e)}


# ── Tool dispatcher ──────────────────────────────────────────

TOOL_MAP = {
    "exec_command": exec_command,
    "fs_read": fs_read,
    "fs_write": fs_write,
    "fs_list": fs_list,
    "claude_code": claude_code,
}

def dispatch(tool_name: str, args: dict) -> str:
    """tool_name + args로 도구 실행, JSON 문자열 반환."""
    fn = TOOL_MAP.get(tool_name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        result = fn(**args)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── OpenAI JSON Schema definitions ──────────────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "exec_command",
            "description": "셸 명령어 실행. 파이썬 코드 실행, git 작업, 빌드, 테스트, 현재 상태 확인 등 모든 CLI 작업에 사용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "실행할 셸 명령어"},
                    "workdir": {"type": "string", "description": "작업 디렉토리 (선택)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fs_read",
            "description": "로컬 파일 내용 읽기. 코드 파일, 설정 파일, 로그 파일 확인 시 사용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "읽을 파일의 절대 경로"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fs_write",
            "description": "로컬 파일 쓰기/생성. 코드 작성, 설정 수정 시 사용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "쓸 파일의 절대 경로"},
                    "content": {"type": "string", "description": "파일 내용"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fs_list",
            "description": "디렉토리 내 파일/폴더 목록 조회. 프로젝트 구조 파악 시 사용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "조회할 디렉토리 절대 경로"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "claude_code",
            "description": "복잡한 코딩 작업을 Claude Code에게 위임. 리팩토링, 버그 수정, 새 기능 구현 등 파일 변경이 필요한 작업에 사용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Claude Code에게 전달할 작업 설명"},
                    "workdir": {"type": "string", "description": "작업 디렉토리 (선택)"},
                },
                "required": ["task"],
            },
        },
    },
]
