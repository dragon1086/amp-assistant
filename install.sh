#!/usr/bin/env bash
# amp 한 줄 설치 스크립트
# 사용법: curl -fsSL https://raw.githubusercontent.com/amp-assistant/amp/main/install.sh | bash
#
# 설치 방법 우선순위:
#   1. pipx  (격리된 환경, 권장)
#   2. uv tool install (uv 있으면 더 빠름)
#   3. pip install --user (fallback)

set -e

REPO="https://github.com/amp-assistant/amp"
CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${CYAN}"
echo "  ██████╗ ███╗   ███╗██████╗ "
echo "  ██╔══██╗████╗ ████║██╔══██╗"
echo "  ███████║██╔████╔██║██████╔╝"
echo "  ██╔══██║██║╚██╔╝██║██╔═══╝ "
echo "  ██║  ██║██║ ╚═╝ ██║██║     "
echo "  ╚═╝  ╚═╝╚═╝     ╚═╝╚═╝     "
echo -e "${NC}"
echo "  Two minds. One answer."
echo ""

# ── Python 확인 ─────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo -e "${RED}❌ Python 3이 필요합니다.${NC}"
  echo "   설치: https://python.org/downloads"
  exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
REQUIRED="3.11"
if python3 -c "import sys; exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
  echo -e "${GREEN}✓ Python ${PYTHON_VERSION}${NC}"
else
  echo -e "${RED}❌ Python 3.11+ 필요 (현재: ${PYTHON_VERSION})${NC}"
  exit 1
fi

# ── 설치 방법 선택 ───────────────────────────────────────────────
if command -v uv &>/dev/null; then
  echo -e "${GREEN}✓ uv 감지 — uv tool install 사용 (가장 빠름)${NC}"
  uv tool install "git+${REPO}"
  INSTALLED_BY="uv"
elif command -v pipx &>/dev/null; then
  echo -e "${GREEN}✓ pipx 감지 — pipx install 사용${NC}"
  pipx install "git+${REPO}"
  INSTALLED_BY="pipx"
else
  echo -e "${YELLOW}⚠ pipx/uv 없음 — pip install --user 사용${NC}"
  echo "  (pipx 설치 권장: pip install pipx)"
  pip3 install --user "git+${REPO}"
  INSTALLED_BY="pip"
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ amp 설치 완료! (${INSTALLED_BY})${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  다음 단계:"
echo -e "  ${CYAN}amp setup${NC}       # 대화형 설정 (API 키, 모델, 텔레그램)"
echo -e "  ${CYAN}amp '안녕!'${NC}     # 바로 시작"
echo -e "  ${CYAN}amp${NC}            # 대화형 REPL"
echo ""

# PATH 안내 (pip --user 설치 시)
if [[ "$INSTALLED_BY" == "pip" ]]; then
  USER_BIN=$(python3 -c "import site; print(site.getusersitepackages())" 2>/dev/null | sed 's/lib.*/bin/')
  echo -e "${YELLOW}  PATH에 추가 필요할 수 있음:${NC}"
  echo "  export PATH=\"\$PATH:${USER_BIN}\""
fi
