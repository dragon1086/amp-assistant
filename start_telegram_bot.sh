#!/bin/bash
# start_telegram_bot.sh — amp Telegram 봇 + MCP 서버 시작
# MACRS 통합: 시작 시 registry 등록 + MCP 서버 백그라운드 시작

source ~/amp/venv/bin/activate
export OPENAI_API_KEY=$(grep "OPENAI_API_KEY" ~/.zshrc | head -1 | sed "s/.*='//;s/'.*//")
export TELEGRAM_BOT_TOKEN=$1
cd ~/amp

# ── 1. MACRS Registry 등록 ──────────────────────────────────────
echo "[amp] MACRS registry 등록 중..."
python -c "
import sys, os
sys.path.insert(0, os.path.expanduser('~/ai-comms'))
sys.path.insert(0, os.path.expanduser('~/amp'))
from amp.core.agent_registration import register_amp
register_amp()
" 2>/dev/null || echo "[amp] registry 등록 실패 (무시 — 계속 진행)"

# ── 2. amp MCP 서버 백그라운드 시작 ────────────────────────────
echo "[amp] MCP 서버 시작 (port 3010)..."
# 이미 실행 중이면 스킵
if lsof -i :3010 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "[amp] MCP 서버 이미 실행 중"
else
    nohup python -m uvicorn amp.mcp_server:app \
        --host 127.0.0.1 --port 3010 --log-level warning \
        >> /tmp/amp-mcp-server.log 2>&1 &
    MCP_PID=$!
    echo "[amp] MCP 서버 PID: $MCP_PID (로그: /tmp/amp-mcp-server.log)"
    sleep 1  # 서버 기동 대기
fi

# ── 3. Telegram 봇 시작 ────────────────────────────────────────
echo "[amp] Telegram 봇 시작..."
python -m amp.interfaces.telegram_bot
