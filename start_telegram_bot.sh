#!/bin/bash
source ~/amp/venv/bin/activate
export OPENAI_API_KEY=$(grep "OPENAI_API_KEY" ~/.zshrc | head -1 | sed "s/.*='//;s/'.*//")
export TELEGRAM_BOT_TOKEN=$1
cd ~/amp
python -m amp.interfaces.telegram_bot
