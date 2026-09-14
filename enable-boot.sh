#!/bin/sh
# Install user service so the agent starts at login/boot (background).
set -e
cd "$(dirname "$0")" || exit 1
DIR=$(pwd)
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
# Rewrite paths in case the folder isn't named/located as %h/linux-ai-agent
sed "s|%h/linux-ai-agent|$DIR|g" agent.service > "$UNIT_DIR/linux-ai-agent.service"
systemctl --user daemon-reload
systemctl --user enable --now linux-ai-agent.service
echo "Running in background. Open http://127.0.0.1:9191"
echo "Stop:  systemctl --user stop linux-ai-agent"
echo "Logs:  journalctl --user -u linux-ai-agent -f"
