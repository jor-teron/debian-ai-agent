#!/bin/sh
# =============================================================================
# debian-ai-agent — one-shot installer
# =============================================================================
# What this does:
#   1) Makes sure python3 + git exist (apt on Debian/Ubuntu if needed)
#   2) Clones or updates the repo into ~/debian-ai-agent
#   3) Creates .env from the example if missing
#   4) Enables the user background service (starts at login)
#
# How people run it (one line):
#   curl -fsSL https://raw.githubusercontent.com/jor-teron/debian-ai-agent/main/install.sh | bash
#
# Related files after install:
#   run.py / config.py / tools.py / brain.py / ui.py / server.py — the app
#   enable-boot.sh — systemd user service helper (called by this script)
#   .env — your API keys (you edit this once)
# =============================================================================

set -e

REPO_URL="https://github.com/jor-teron/debian-ai-agent.git"
INSTALL_DIR="${HOME}/debian-ai-agent"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

say() {
  # Simple status line so the install is easy to follow.
  printf '%s\n' "$*"
}

need_cmd() {
  # Return 0 if command exists.
  command -v "$1" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# Dependencies (python3 + git)
# ---------------------------------------------------------------------------

install_deps() {
  missing=""
  need_cmd python3 || missing="$missing python3"
  need_cmd git || missing="$missing git"

  if [ -z "$missing" ]; then
    say "Dependencies OK (python3, git)."
    return 0
  fi

  say "Need:$missing"
  if need_cmd apt-get; then
    if need_cmd sudo; then
      sudo apt-get update
      # shellcheck disable=SC2086
      sudo apt-get install -y $missing
    else
      say "Run as root or install:$missing"
      exit 1
    fi
  else
    say "Please install:$missing then re-run."
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Clone or update the project
# ---------------------------------------------------------------------------

fetch_repo() {
  if [ -d "$INSTALL_DIR/.git" ]; then
    say "Updating existing install at $INSTALL_DIR …"
    git -C "$INSTALL_DIR" pull --ff-only
  elif [ -e "$INSTALL_DIR" ]; then
    say "Folder $INSTALL_DIR exists but is not this git repo."
    say "Move or remove it, then re-run."
    exit 1
  else
    say "Cloning into $INSTALL_DIR …"
    git clone "$REPO_URL" "$INSTALL_DIR"
  fi
}

# ---------------------------------------------------------------------------
# Config (.env) and background service
# ---------------------------------------------------------------------------

setup_env_and_service() {
  cd "$INSTALL_DIR" || exit 1

  if [ ! -f .env ]; then
    cp .env.example .env
    say "Created .env — add at least one API key (see README)."
  else
    say "Keeping existing .env"
  fi

  chmod +x run.sh enable-boot.sh install.sh 2>/dev/null || true
  ./enable-boot.sh
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

say "=== debian-ai-agent install ==="
install_deps
fetch_repo
setup_env_and_service

say ""
say "Almost done:"
say "  1) Edit keys:  nano $INSTALL_DIR/.env"
say "     Example: PROVIDER=xai   and   XAI_API_KEY=your_key"
say "  2) Restart:    systemctl --user restart debian-ai-agent"
say "  3) Open:       http://127.0.0.1:8787"
say ""
say "Done."
