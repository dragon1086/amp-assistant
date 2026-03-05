#!/bin/bash
# amp Telegram 봇 시작 스크립트
# 순서: registry 등록 → MCP 서버(백그라운드) → 텔레그램 봇

set -e

source ~/amp/venv/bin/activate
export OPENAI_API_KEY=$(grep "OPENAI_API_KEY" ~/.zshrc | head -1 | sed "s/.*='//;s/'.*//")
export TELEGRAM_BOT_TOKEN=$1

cd ~/amp

# 1. MACRS registry에 amp 자동 등록
echo "[start] MACRS registry 등록 중..."
python -c '
import sys
sys.path.insert(0, "/Users/rocky/ai-comms")
from amp.core.agent_registration import register_amp
register_amp()
'

# 2. amp MCP 서버 백그라운드 시작 (포트 3010)
echo "[start] amp MCP 서버 시작 (localhost:3010)..."
AMP_MCP_PORT=3010 python -m amp.mcp_server &
MCP_PID=$!
echo "[start] MCP 서버 PID: $MCP_PID"

# 서버 준비 대기 (최대 5초)
for i in 1 2 3 4 5; do
    sleep 1
    if curl -s http://localhost:3010/health > /dev/null 2>&1; then
        echo "[start] MCP 서버 준비 완료"
        break
    fi
done

# 3. 텔레그램 봇 시작 (포그라운드)
echo "[start] 텔레그램 봇 시작..."
python -m amp.interfaces.telegram_bot
