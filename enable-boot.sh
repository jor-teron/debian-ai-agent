#!/bin/sh
# Install user service so the agent starts at login/boot (background).
set -e
cd "$(dirname "$0")" || exit 1
DIR=$(pwd)
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
# Rewrite paths in case the folder isn't named/located as %h/debian-ai-agent
sed "s|%h/debian-ai-agent|$DIR|g" agent.service > "$UNIT_DIR/debian-ai-agent.service"
systemctl --user daemon-reload
systemctl --user enable --now debian-ai-agent.service
echo "Running in background. Open http://127.0.0.1:8787"
echo "Stop:  systemctl --user stop debian-ai-agent"
echo "Logs:  journalctl --user -u debian-ai-agent -f"
