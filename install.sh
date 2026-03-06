#!/bin/bash
# amp one-line installer
# curl -fsSL https://raw.githubusercontent.com/amp-reasoning/amp/main/install.sh | bash

set -e

BOLD="\033[1m"
GREEN="\033[32m"
CYAN="\033[36m"
RED="\033[31m"
RESET="\033[0m"

echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════╗"
echo "  ║   amp — AI Debate Engine      ║"
echo "  ║   Two AIs argue. Better answer║"
echo "  ╚═══════════════════════════════╝"
echo -e "${RESET}"

# Python 버전 체크
PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ]]; then
    echo -e "${RED}❌ Python 3.11+ 필요 (현재: $PY_VERSION)${RESET}"
    echo "   https://python.org 에서 최신 Python을 설치하세요."
    exit 1
fi

echo -e "${GREEN}✅ Python $PY_VERSION${RESET}"

# pip install
echo -e "\n${BOLD}📦 설치 중...${RESET}"
pip install --quiet amp-reasoning

echo -e "${GREEN}✅ amp-reasoning 설치 완료${RESET}"

# amp init
echo -e "\n${BOLD}⚙️  초기 설정...${RESET}"
amp init --non-interactive 2>/dev/null || true

echo -e "\n${GREEN}${BOLD}🎉 설치 완료!${RESET}"
echo ""
echo -e "  ${BOLD}바로 시작:${RESET}"
echo -e "  ${CYAN}amp \"비트코인 지금 사야 할까?\"${RESET}"
echo ""
echo -e "  ${BOLD}MCP 서버:${RESET}"
echo -e "  ${CYAN}amp serve${RESET}  # http://localhost:3010"
echo ""
echo -e "  ${BOLD}설정:${RESET}"
echo -e "  ${CYAN}amp init${RESET}   # API 키 설정"
