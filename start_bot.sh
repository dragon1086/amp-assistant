#!/bin/bash
# amp Telegram Bot 시작 스크립트
# 토큰/키는 .env 파일 또는 환경변수에서 로드합니다.
# 설정: amp setup 실행 (대화형 wizard)

set -e
cd "$(dirname "$0")"

# venv 활성화
if [[ -f venv/bin/activate ]]; then
  source venv/bin/activate
fi

# .env 파일 로드 (있으면)
ENV_FILE="${HOME}/.amp/.env"
if [[ -f "$ENV_FILE" ]]; then
  echo "⚙️  .env 로드: $ENV_FILE"
  set -a
  source "$ENV_FILE"
  set +a
fi

# 필수 변수 체크
if [[ -z "$TELEGRAM_BOT_TOKEN" ]]; then
  echo "❌ TELEGRAM_BOT_TOKEN이 설정되지 않았습니다."
  echo "   방법 1: amp setup 실행"
  echo "   방법 2: export TELEGRAM_BOT_TOKEN=your_token"
  echo "   방법 3: ~/.amp/.env 파일에 TELEGRAM_BOT_TOKEN=your_token 추가"
  exit 1
fi

if [[ -z "$OPENAI_API_KEY" && -z "$CLAUDE_CODE_OAUTH_TOKEN" && -z "$ANTHROPIC_API_KEY" ]]; then
  echo "⚠️  경고: OPENAI_API_KEY 또는 CLAUDE_CODE_OAUTH_TOKEN 중 하나가 필요합니다."
  echo "   amp setup 을 실행해 설정하세요."
fi

echo "🚀 amp bot 시작..."
python3 -m amp.interfaces.telegram_bot
