#!/usr/bin/env python3
"""safe_edit.py — 공백/탭 오차에 강한 파일 편집 유틸리티.

Edit 툴 대신 사용하면 'Could not find exact text' 에러를 방지할 수 있음.

사용법:
  python3 scripts/safe_edit.py <file> <old_pattern> <new_text>  [--regex] [--dry-run]

예시:
  # 단순 문자열 교체 (공백 관대)
  python3 scripts/safe_edit.py amp/interfaces/cli.py "cli.add_command(setup)" "cli.add_command(setup)\ncli.add_command(init)"

  # 정규식 교체
  python3 scripts/safe_edit.py amp/core/llm_factory.py "timeout=\\d+" "timeout=120" --regex

  # 변경 내용만 미리보기 (실제 저장 안 함)
  python3 scripts/safe_edit.py amp/interfaces/cli.py "old text" "new text" --dry-run
"""
import re
import sys
import argparse
import difflib
from pathlib import Path


def normalize_ws(text: str) -> str:
    """공백 정규화: 줄 끝 공백 제거, 탭→스페이스."""
    lines = [line.rstrip().replace("\t", "    ") for line in text.splitlines()]
    return "\n".join(lines)


def safe_replace(
    content: str,
    old: str,
    new: str,
    regex: bool = False,
    ws_flexible: bool = True,
) -> tuple[str, int]:
    """파일 내용에서 old를 new로 교체.

    Returns:
        (new_content, count) — count=0이면 못 찾은 것
    """
    if regex:
        result, count = re.subn(old, new, content)
        return result, count

    # 1. 정확히 일치하는지 먼저 시도
    if old in content:
        return content.replace(old, new, 1), 1

    if not ws_flexible:
        return content, 0

    # 2. 공백 정규화 후 재시도
    norm_content = normalize_ws(content)
    norm_old = normalize_ws(old)

    if norm_old in norm_content:
        # 정규화된 버전에서 위치 찾아서 원본 파일에 적용
        idx = norm_content.find(norm_old)

        # 원본 content의 해당 위치 추정 (줄 번호 기준)
        target_line = norm_content[:idx].count("\n")
        lines = content.splitlines(keepends=True)

        # norm_old의 줄 수
        old_line_count = norm_old.count("\n") + 1

        # 원본에서 해당 범위 교체
        before = "".join(lines[:target_line])
        after = "".join(lines[target_line + old_line_count:])
        return before + new + ("\n" if not new.endswith("\n") else "") + after, 1

    # 3. 줄 단위 fuzzy 검색 (첫 줄/마지막 줄이 일치하면 블록으로 인식)
    old_lines = [normalize_ws(l) for l in old.strip().splitlines()]
    content_lines = [normalize_ws(l) for l in content.splitlines()]

    if not old_lines:
        return content, 0

    first_line = old_lines[0].strip()
    for i, line in enumerate(content_lines):
        if line.strip() == first_line:
            # 이 위치에서 블록이 일치하는지 확인
            block = content_lines[i : i + len(old_lines)]
            block_norm = [l.strip() for l in block]
            old_norm = [l.strip() for l in old_lines]
            if block_norm == old_norm:
                # 원본 줄들 교체
                orig_lines = content.splitlines(keepends=True)
                before = "".join(orig_lines[:i])
                after = "".join(orig_lines[i + len(old_lines):])
                return before + new + ("\n" if not new.endswith("\n") else "") + after, 1

    return content, 0


def main():
    parser = argparse.ArgumentParser(description="Safe file editor with whitespace flexibility")
    parser.add_argument("file", help="대상 파일 경로")
    parser.add_argument("old", help="찾을 텍스트 (또는 정규식)")
    parser.add_argument("new", help="교체할 텍스트")
    parser.add_argument("--regex", "-r", action="store_true", help="정규식 모드")
    parser.add_argument("--dry-run", "-n", action="store_true", help="저장 없이 미리보기만")
    parser.add_argument("--strict", action="store_true", help="공백 유연성 OFF (정확 일치만)")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"❌ 파일 없음: {path}", file=sys.stderr)
        sys.exit(1)

    original = path.read_text(encoding="utf-8")
    new_content, count = safe_replace(
        original,
        args.old,
        args.new,
        regex=args.regex,
        ws_flexible=not args.strict,
    )

    if count == 0:
        print(f"❌ 텍스트를 찾지 못했습니다: {repr(args.old[:60])}", file=sys.stderr)
        print("  --regex 플래그로 정규식 패턴을 사용하거나,", file=sys.stderr)
        print("  grep -n 으로 정확한 위치를 확인하세요.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
        print("".join(diff) or "변경 없음")
        return

    path.write_text(new_content, encoding="utf-8")
    print(f"✅ {count}곳 교체 완료: {path}")


if __name__ == "__main__":
    main()
