#!/usr/bin/env bash
# amp MCP 서버 launchd 등록 — 부팅 시 자동 시작, 크래시 시 자동 재시작
set -e

PLIST="$HOME/Library/LaunchAgents/ai.amp.mcp-server.plist"
AMP_DIR="$HOME/amp"
VENV_PYTHON="$AMP_DIR/venv/bin/python"
LOG_DIR="$HOME/.amp/logs"

mkdir -p "$LOG_DIR"

cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>ai.amp.mcp-server</string>

  <key>ProgramArguments</key>
  <array>
    <string>$VENV_PYTHON</string>
    <string>-m</string>
    <string>uvicorn</string>
    <string>amp.mcp_server:app</string>
    <string>--host</string>
    <string>127.0.0.1</string>
    <string>--port</string>
    <string>3010</string>
  </array>

  <key>WorkingDirectory</key>
  <string>$AMP_DIR</string>

  <!-- 환경변수: ~/.zshrc에서 읽어야 할 키들 -->
  <key>EnvironmentVariables</key>
  <dict>
    <key>OPENAI_API_KEY</key>
    <string>__OPENAI_API_KEY__</string>
    <key>ANTHROPIC_API_KEY</key>
    <string>__ANTHROPIC_API_KEY__</string>
    <key>CLAUDE_CODE_OAUTH_TOKEN</key>
    <string>__CLAUDE_CODE_OAUTH_TOKEN__</string>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
  </dict>

  <!-- 크래시 시 자동 재시작 -->
  <key>KeepAlive</key>
  <true/>

  <!-- 부팅 시 자동 시작 -->
  <key>RunAtLoad</key>
  <true/>

  <!-- 재시작 간 최소 대기 시간 (초) -->
  <key>ThrottleInterval</key>
  <integer>10</integer>

  <key>StandardOutPath</key>
  <string>$LOG_DIR/mcp-server.log</string>

  <key>StandardErrorPath</key>
  <string>$LOG_DIR/mcp-server.err</string>
</dict>
</plist>
EOF

# API 키 값 주입
OPENAI_KEY=$(grep 'OPENAI_API_KEY' ~/.zshrc | head -1 | grep -o "'[^']*'" | tr -d "'")
CLAUDE_TOKEN=$(grep 'CLAUDE_CODE_OAUTH_TOKEN' ~/.zshrc | head -1 | grep -o "'[^']*'" | tr -d "'")
ANTHROPIC_KEY=$(grep 'ANTHROPIC_API_KEY' ~/.zshrc | head -1 | grep -o "'[^']*'" | tr -d "'")

sed -i '' "s|__OPENAI_API_KEY__|$OPENAI_KEY|g" "$PLIST"
sed -i '' "s|__CLAUDE_CODE_OAUTH_TOKEN__|$CLAUDE_TOKEN|g" "$PLIST"
sed -i '' "s|__ANTHROPIC_API_KEY__|$ANTHROPIC_KEY|g" "$PLIST"

# 기존 서비스 중지 (있으면)
launchctl unload "$PLIST" 2>/dev/null || true

# 등록 + 시작
launchctl load "$PLIST"

echo "✅ amp MCP 서버 launchd 등록 완료!"
echo ""
echo "관리 명령어:"
echo "  상태 확인:  launchctl list | grep amp"
echo "  로그 보기:  tail -f $LOG_DIR/mcp-server.log"
echo "  수동 중지:  launchctl unload $PLIST"
echo "  수동 시작:  launchctl load $PLIST"
echo "  서버 주소:  http://127.0.0.1:3010"
