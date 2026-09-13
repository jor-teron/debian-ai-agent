#!/bin/sh
# =============================================================================
# AI Agent — one-shot installer (most Linux distros)
# =============================================================================
# What this does:
#   1) Detects the host package manager and installs python3, git, bubblewrap
#   2) Clones or updates the repo into ~/debian-ai-agent
#   3) Creates .env from the example if missing
#   4) Enables the user background service when systemd is available
#
# How people run it (one line):
#   curl -fsSL https://raw.githubusercontent.com/jor-teron/debian-ai-agent/main/install.sh | bash
#
# Package managers tried (first match): apt-get, dnf, yum, pacman, zypper, apk
# If none: print manual install line for python3, git, bubblewrap
# =============================================================================

set -e

REPO_URL="https://github.com/jor-teron/debian-ai-agent.git"
INSTALL_DIR="${HOME}/debian-ai-agent"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

say() {
  printf '%s\n' "$*"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# Host / package manager detection
# ---------------------------------------------------------------------------

detect_pkg() {
  # First match wins.
  for pm in apt-get dnf yum pacman zypper apk; do
    if need_cmd "$pm"; then
      echo "$pm"
      return 0
    fi
  done
  echo none
  return 1
}

show_host() {
  if [ -f /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    say "Host: ${PRETTY_NAME:-$NAME}"
  fi
}

# ---------------------------------------------------------------------------
# Dependencies (python3 + git + bubblewrap)
# ---------------------------------------------------------------------------

install_deps() {
  missing_py=0
  missing_git=0
  missing_bwrap=0
  need_cmd python3 || missing_py=1
  need_cmd git || missing_git=1
  need_cmd bwrap || missing_bwrap=1

  if [ "$missing_py$missing_git$missing_bwrap" = "000" ]; then
    say "Dependencies OK (python3, git, bubblewrap)."
    return 0
  fi

  PKG=$(detect_pkg)
  say "Package manager: $PKG"

  if [ "$PKG" = "none" ]; then
    say "Could not detect apt-get/dnf/yum/pacman/zypper/apk."
    say "Manually install: python3, git, bubblewrap"
    exit 1
  fi

  if ! need_cmd sudo && [ "$(id -u)" -ne 0 ]; then
    say "Need sudo (or root) to install packages."
    say "Manually install: python3, git, bubblewrap"
    exit 1
  fi

  run_root() {
    if [ "$(id -u)" -eq 0 ]; then
      "$@"
    else
      sudo "$@"
    fi
  }

  case "$PKG" in
    apt-get)
      run_root apt-get update
      run_root apt-get install -y python3 git bubblewrap
      ;;
    dnf)
      run_root dnf install -y python3 git bubblewrap
      ;;
    yum)
      run_root yum install -y python3 git bubblewrap
      ;;
    pacman)
      # Arch package for Python is "python" (provides python3).
      run_root pacman -Sy --needed --noconfirm python git bubblewrap
      ;;
    zypper)
      run_root zypper --non-interactive install python3 git bubblewrap
      ;;
    apk)
      run_root apk add --no-cache python3 git bubblewrap
      ;;
    *)
      say "Manually install: python3, git, bubblewrap"
      exit 1
      ;;
  esac

  # Re-check after install.
  if ! need_cmd python3 || ! need_cmd git; then
    say "Still missing python3 or git after install."
    say "Manually install: python3, git, bubblewrap"
    exit 1
  fi
  if ! need_cmd bwrap; then
    say "Warning: bubblewrap (bwrap) not found — shell will ask Confirm instead of freehand."
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

  if need_cmd systemctl; then
    ./enable-boot.sh
  else
    say "No systemd — start manually with: ./run.sh"
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

say "=== AI Agent install ==="
show_host
install_deps
fetch_repo
setup_env_and_service

say ""
say "Almost done:"
say "  1) Edit keys:  nano $INSTALL_DIR/.env"
say "     Example: PROVIDER=xai   and   XAI_API_KEY=your_key"
say "  2) Restart:    systemctl --user restart debian-ai-agent"
say "  3) Open:       http://127.0.0.1:9191"
say ""
say "Done."
