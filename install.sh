#!/bin/sh
# =============================================================================
# AI Agent — one-shot installer (most Linux distros)
# =============================================================================
# What this does:
#   1) Detects the host package manager; installs python3 + git (required)
#   2) Optionally installs bubblewrap (ask, or INSTALL_BWRAP=1/0)
#   3) Clones or updates the repo into ~/debian-ai-agent
#   4) Creates .env from the example if missing
#   5) Enables the user background service when systemd is available
#
# How people run it (one line):
#   curl -fsSL https://raw.githubusercontent.com/jor-teron/debian-ai-agent/main/install.sh | bash
#
# Optional:
#   INSTALL_BWRAP=1  — try bubblewrap without asking (still continues if it fails)
#   INSTALL_BWRAP=0  — never install bubblewrap
#
# Package managers tried (first match): apt-get, dnf, yum, pacman, zypper, apk
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

run_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

# Install a list of packages with the detected manager. Returns 0/1.
pkg_install() {
  PKG=$1
  shift
  case "$PKG" in
    apt-get)
      run_root apt-get update
      run_root apt-get install -y "$@"
      ;;
    dnf)
      run_root dnf install -y "$@"
      ;;
    yum)
      run_root yum install -y "$@"
      ;;
    pacman)
      run_root pacman -Sy --needed --noconfirm "$@"
      ;;
    zypper)
      run_root zypper --non-interactive install "$@"
      ;;
    apk)
      run_root apk add --no-cache "$@"
      ;;
    *)
      return 1
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

install_required_deps() {
  missing_py=0
  missing_git=0
  need_cmd python3 || missing_py=1
  need_cmd git || missing_git=1

  if [ "$missing_py$missing_git" = "00" ]; then
    say "Required deps OK (python3, git)."
    return 0
  fi

  PKG=$(detect_pkg)
  say "Package manager: $PKG"

  if [ "$PKG" = "none" ]; then
    say "Could not detect apt-get/dnf/yum/pacman/zypper/apk."
    say "Manually install: python3, git"
    exit 1
  fi

  if ! need_cmd sudo && [ "$(id -u)" -ne 0 ]; then
    say "Need sudo (or root) to install packages."
    say "Manually install: python3, git"
    exit 1
  fi

  # Arch: package name is "python"
  if [ "$PKG" = "pacman" ]; then
    pkgs="git"
    [ "$missing_py" = 1 ] && pkgs="python $pkgs"
  else
    pkgs="git"
    [ "$missing_py" = 1 ] && pkgs="python3 $pkgs"
  fi

  # shellcheck disable=SC2086
  pkg_install "$PKG" $pkgs

  if ! need_cmd python3 || ! need_cmd git; then
    say "Still missing python3 or git after install."
    say "Manually install: python3, git"
    exit 1
  fi
}

want_bubblewrap() {
  # INSTALL_BWRAP=0/1 overrides. Otherwise ask if stdin is a TTY; default no when piped.
  case "${INSTALL_BWRAP-}" in
    1|y|Y|yes|YES) return 0 ;;
    0|n|N|no|NO) return 1 ;;
  esac
  if [ -t 0 ]; then
    printf '%s' "Install bubblewrap for sandboxed freehand shell? [y/N] "
    read -r ans || ans=
    case "$ans" in
      y|Y|yes|YES) return 0 ;;
      *) return 1 ;;
    esac
  fi
  say "Skipping bubblewrap (non-interactive). Shell will use Confirm."
  say "Later (if your OS supports it): install package 'bubblewrap', or re-run with INSTALL_BWRAP=1"
  return 1
}

install_optional_bwrap() {
  if need_cmd bwrap; then
    say "bubblewrap OK (sandboxed freehand shell)."
    return 0
  fi

  if ! want_bubblewrap; then
    say "No bubblewrap — agent still works; shell asks Confirm / Telegram YES-NO."
    return 0
  fi

  PKG=$(detect_pkg)
  if [ "$PKG" = "none" ]; then
    say "Cannot auto-install bubblewrap (no package manager)."
    say "Agent will work without it."
    return 0
  fi

  if ! need_cmd sudo && [ "$(id -u)" -ne 0 ]; then
    say "Need sudo to install bubblewrap — skipped."
    return 0
  fi

  say "Trying bubblewrap (optional; older systems like Debian 11 may fail)…"
  set +e
  pkg_install "$PKG" bubblewrap
  rc=$?
  set -e

  if need_cmd bwrap; then
    say "bubblewrap installed."
  else
    say "bubblewrap not installed (exit $rc or unsupported glibc). Continuing without it."
    say "Agent is fine — shell stays on Confirm until bwrap is available."
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
install_required_deps
install_optional_bwrap
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
