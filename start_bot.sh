#!/bin/bash
cd ~/amp && source venv/bin/activate
export OPENAI_API_KEY=$(grep "OPENAI_API_KEY" ~/.zshrc | head -1 | sed "s/.*='//;s/'.*//")
export TELEGRAM_BOT_TOKEN="REDACTED_AMP_BOT_TOKEN"

echo "amp bot 시작..."
python3 -m amp.interfaces.telegram_bot
