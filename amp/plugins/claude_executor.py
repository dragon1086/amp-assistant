"""Claude Code executor plugin for amp.

Commands:
  /claude <task>  — Claude Code를 로컬에서 실행하고 결과 반환

자연어 패턴도 인식:
  "클로드코드로 [task]해줘"
  "claude code로 [task]"
  "코드 실행해줘: [task]"

환경 변수:
  CLAUDE_CODE_OAUTH_TOKEN  — claude OAuth 토큰 (우선)
  ANTHROPIC_API_KEY        — 또는 API 키

Config (config.yaml):
  plugins:
    claude_executor:
      workdir: ~/amp          # 기본 작업 디렉토리
      timeout: 120            # 초 (기본 120초)
      max_output: 3000        # 텔레그램 출력 최대 문자수
"""

import asyncio
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from amp.plugins.base import BasePlugin

logger = logging.getLogger(__name__)

# 자연어 트리거 패턴
_TRIGGER_PATTERNS = [
    r"클로드\s*코드.{0,10}(실행|써|해|돌려|써줘|실행해줘|해줘)",
    r"claude\s*[-\s]?code.{0,10}(run|execute|실행|해줘)",
    r"코드\s*(실행|돌려).{0,5}줘",
]


def _html_e(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class ClaudeExecutorPlugin(BasePlugin):
    name = "claude_executor"
    description = "Claude Code 로컬 실행 (/claude <작업>)"
    enabled_by_default = True

    def can_handle(self, update) -> bool:
        if not (update.message and update.message.text):
            return False
        text = update.message.text.strip()
        # 명시적 커맨드
        if text.startswith("/claude"):
            return True
        # 자연어 패턴 (단, 너무 짧은 메시지는 제외)
        if len(text) > 10:
            for pattern in _TRIGGER_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    return True
        return False

    async def handle(self, update, context, config: dict, user_config: dict) -> str | None:
        text = update.message.text.strip()

        # 작업 추출
        task = self._extract_task(text)
        if not task:
            await update.message.reply_text(
                "사용법: <code>/claude &lt;작업 설명&gt;</code>\n\n"
                "예시:\n"
                "<code>/claude hello.py 파일 만들어서 'Hello, amp!' 출력하게 해줘</code>\n"
                "<code>/claude ~/amp에서 git status 확인해줘</code>",
                parse_mode="HTML",
            )
            return None

        # Claude Code 바이너리 확인
        claude_bin = self._find_claude()
        if not claude_bin:
            await update.message.reply_text(
                "❌ <code>claude</code> 바이너리를 찾을 수 없어.\n"
                "<code>npm install -g @anthropic-ai/claude-code</code> 로 설치해줘.",
                parse_mode="HTML",
            )
            return None

        # 설정
        plugin_cfg = config.get("plugins", {}).get("claude_executor", {})
        workdir = Path(plugin_cfg.get("workdir", "~/amp")).expanduser()
        timeout = int(plugin_cfg.get("timeout", 120))
        max_output = int(plugin_cfg.get("max_output", 3000))

        # 진행 메시지
        status_msg = await update.message.reply_text(
            f"⚡ <b>Claude Code 실행 중...</b>\n\n"
            f"📋 작업: <i>{_html_e(task[:200])}</i>\n"
            f"📁 디렉토리: <code>{_html_e(str(workdir))}</code>",
            parse_mode="HTML",
        )

        # 실행
        try:
            result = await asyncio.wait_for(
                self._run_claude(claude_bin, task, workdir),
                timeout=timeout,
            )
            stdout, stderr, returncode = result
        except asyncio.TimeoutError:
            await status_msg.edit_text(
                f"⏱️ <b>타임아웃</b> ({timeout}초)\n\n"
                "작업이 너무 오래 걸려서 중단했어. "
                "더 구체적인 작업이나 짧은 작업으로 다시 시도해봐.",
                parse_mode="HTML",
            )
            return None
        except Exception as e:
            logger.error(f"Claude executor error: {e}", exc_info=True)
            await status_msg.edit_text(
                f"❌ <b>실행 오류:</b> <code>{_html_e(str(e)[:300])}</code>",
                parse_mode="HTML",
            )
            return None

        # 결과 포맷
        output = stdout.strip() if stdout else ""
        errors = stderr.strip() if stderr else ""

        if not output and not errors:
            output = "(출력 없음)"

        # 너무 길면 자르기
        combined = output
        if errors and returncode != 0:
            combined += f"\n\n⚠️ stderr:\n{errors}"
        if len(combined) > max_output:
            combined = combined[:max_output] + f"\n\n... (출력 {len(combined)}자 중 {max_output}자 표시)"

        status_icon = "✅" if returncode == 0 else "⚠️"
        reply = (
            f"{status_icon} <b>Claude Code 완료</b> (종료코드: {returncode})\n\n"
            f"<pre>{_html_e(combined)}</pre>"
        )

        await status_msg.edit_text(reply, parse_mode="HTML")
        return None

    def _extract_task(self, text: str) -> str:
        """메시지에서 실제 작업 내용 추출."""
        # /claude 커맨드
        if text.startswith("/claude"):
            task = text[len("/claude"):].strip()
            return task

        # 자연어: 패턴 뒤의 내용 추출 시도
        # 예: "클로드코드로 hello.py 만들어줘" → "hello.py 만들어줘"
        for pattern in _TRIGGER_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                # 패턴 앞뒤 내용 합치기
                before = text[:m.start()].strip()
                after = text[m.end():].strip()
                task_parts = [p for p in [before, after] if p]
                if task_parts:
                    return " ".join(task_parts)
                return text  # fallback: 전체 텍스트

        return text

    def _find_claude(self) -> str | None:
        """claude 바이너리 경로 탐색."""
        # 1. PATH에서
        found = shutil.which("claude")
        if found:
            return found

        # 2. 일반적인 설치 경로들
        candidates = [
            Path.home() / ".nvm/versions/node/current/bin/claude",
            Path("/usr/local/bin/claude"),
            Path("/opt/homebrew/bin/claude"),
            Path.home() / ".local/bin/claude",
        ]
        # nvm 버전 동적 탐색
        nvm_dir = Path.home() / ".nvm/versions/node"
        if nvm_dir.exists():
            for node_ver in sorted(nvm_dir.iterdir(), reverse=True):
                p = node_ver / "bin" / "claude"
                if p.exists():
                    candidates.insert(0, p)
                    break

        for c in candidates:
            if c.exists():
                return str(c)
        return None

    async def _run_claude(
        self, claude_bin: str, task: str, workdir: Path
    ) -> tuple[str, str, int]:
        """Claude Code를 서브프로세스로 실행."""
        env = os.environ.copy()

        # OAuth 토큰 주입 (zshrc에서 로드 시도)
        if not env.get("CLAUDE_CODE_OAUTH_TOKEN"):
            token = self._load_oauth_token()
            if token:
                env["CLAUDE_CODE_OAUTH_TOKEN"] = token

        # HOME 설정 (필요 시)
        env.setdefault("HOME", str(Path.home()))

        cmd = [claude_bin, "-p", "--dangerously-skip-permissions", task]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workdir) if workdir.exists() else str(Path.home()),
            env=env,
        )
        stdout, stderr = await proc.communicate()
        return (
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
            proc.returncode or 0,
        )

    def _load_oauth_token(self) -> str | None:
        """~/.zshrc 또는 ~/.amp/.env 에서 OAuth 토큰 추출."""
        sources = [
            Path.home() / ".amp" / ".env",
            Path.home() / ".zshrc",
            Path.home() / ".bashrc",
            Path.home() / ".bash_profile",
        ]
        # 싱글쿼트, 더블쿼트, 또는 따옴표 없는 형식 모두 처리
        patterns = [
            r"CLAUDE_CODE_OAUTH_TOKEN\s*=\s*'([^']+)'",   # single quote
            r'CLAUDE_CODE_OAUTH_TOKEN\s*=\s*"([^"]+)"',   # double quote
            r"CLAUDE_CODE_OAUTH_TOKEN\s*=\s*([^\s\n'\"]+)", # bare value
        ]
        for src in sources:
            if not src.exists():
                continue
            try:
                content = src.read_text(errors="ignore")
                for pattern in patterns:
                    m = re.search(pattern, content)
                    if m:
                        token = m.group(1).strip()
                        if len(token) > 20:
                            return token
            except Exception:
                pass
        return None

    def get_commands(self) -> list[tuple[str, str]]:
        return [("claude", "Claude Code 실행 (/claude <작업>)")]

    def setup(self, app, config: dict | None = None) -> None:
        """Register /claude command handler directly."""
        from telegram.ext import CommandHandler
        self._config = config or {}

        async def cmd_claude(update, ctx):
            """실제 /claude 명령어 처리."""
            # user_config는 bot level이라 여기서는 빈 dict 사용
            # (per-user 설정이 필요하면 user_config_store에서 로드)
            await self.handle(update, ctx, self._config, {})

        app.add_handler(CommandHandler("claude", cmd_claude))
