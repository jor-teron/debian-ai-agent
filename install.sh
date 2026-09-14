#!/bin/sh
# =============================================================================
# AI Agent — quiet one-shot installer
# =============================================================================
# Required: python3, git. Optional: bubblewrap (always asks [y/N] on /dev/tty).
# INSTALL_BWRAP=0|1 skips the question.
# curl -fsSL …/install.sh | bash
# =============================================================================

set -e

REPO_URL="https://github.com/jor-teron/debian-ai-agent.git"
INSTALL_DIR="${HOME}/debian-ai-agent"

say() { printf '%s\n' "$*"; }

need_cmd() { command -v "$1" >/dev/null 2>&1; }

detect_pkg() {
  for pm in apt-get dnf yum pacman zypper apk; do
    need_cmd "$pm" && { echo "$pm"; return 0; }
  done
  echo none
  return 1
}

run_root() {
  if [ "$(id -u)" -eq 0 ]; then "$@"
  else sudo "$@"
  fi
}

# Quiet package install. Args: manager, packages...
pkg_install() {
  PKG=$1
  shift
  case "$PKG" in
    apt-get)
      run_root apt-get update -qq
      run_root apt-get install -y -qq "$@"
      ;;
    dnf)
      run_root dnf install -y -q "$@"
      ;;
    yum)
      run_root yum install -y -q "$@"
      ;;
    pacman)
      run_root pacman -Sy --needed --noconfirm --quiet "$@"
      ;;
    zypper)
      run_root zypper --non-interactive --quiet install "$@"
      ;;
    apk)
      run_root apk add --no-cache --quiet "$@"
      ;;
    *) return 1 ;;
  esac
}

install_required_deps() {
  need_cmd python3 && need_cmd git && { say "Deps: ok"; return 0; }

  PKG=$(detect_pkg)
  if [ "$PKG" = "none" ]; then
    say "Please install python3 and git, then re-run."
    exit 1
  fi
  if ! need_cmd sudo && [ "$(id -u)" -ne 0 ]; then
    say "Need sudo to install python3/git."
    exit 1
  fi

  say "Installing python3 + git…"
  if [ "$PKG" = "pacman" ]; then
    pkgs="git"
    need_cmd python3 || pkgs="python git"
  else
    pkgs="git"
    need_cmd python3 || pkgs="python3 git"
  fi
  # shellcheck disable=SC2086
  pkg_install "$PKG" $pkgs

  if ! need_cmd python3 || ! need_cmd git; then
    say "Still missing python3 or git."
    exit 1
  fi
  say "Deps: ok"
}

want_bubblewrap() {
  case "${INSTALL_BWRAP-}" in
    1|y|Y|yes|YES) return 0 ;;
    0|n|N|no|NO) return 1 ;;
  esac

  printf '%s' "Install bubblewrap (sandbox)? [Y/n] "
  ans=
  if [ -r /dev/tty ]; then
    read -r ans < /dev/tty || ans=
  elif [ -t 0 ]; then
    read -r ans || ans=
  else
    say "No prompt available — skipping bubblewrap."
    return 1
  fi
  # Default Y if Enter / empty
  case "$ans" in
    ""|y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

install_optional_bwrap() {
  if need_cmd bwrap; then
    say "Sandbox: on"
    return 0
  fi
  if ! want_bubblewrap; then
    say "Sandbox: off (shell will ask Confirm)"
    return 0
  fi

  PKG=$(detect_pkg)
  if [ "$PKG" = "none" ] || { ! need_cmd sudo && [ "$(id -u)" -ne 0 ]; }; then
    say "Sandbox: off (could not install)"
    return 0
  fi

  say "Installing bubblewrap…"
  set +e
  pkg_install "$PKG" bubblewrap >/dev/null 2>&1
  set -e

  if need_cmd bwrap; then
    say "Sandbox: on"
  else
    say "Sandbox: off (not supported on this OS — that's fine)"
  fi
}

fetch_repo() {
  if [ -d "$INSTALL_DIR/.git" ]; then
    say "Updating…"
    git -C "$INSTALL_DIR" pull --ff-only --quiet
  elif [ -e "$INSTALL_DIR" ]; then
    say "Folder $INSTALL_DIR exists but isn't this repo. Move it and re-run."
    exit 1
  else
    say "Downloading…"
    git clone --quiet "$REPO_URL" "$INSTALL_DIR"
  fi
}

ensure_workspace_dirs() {
  # Default AI workspace (~/ai-workspace) + standard subdirs.
  # Expand ~ via $HOME. Safe to re-run (mkdir -p).
  WS="${HOME}/ai-workspace"
  mkdir -p "$WS/memory" "$WS/workspace" "$WS/test" "$WS/trash" "$WS/user"
  say "Workspace: $WS"
}

setup_env_and_service() {
  cd "$INSTALL_DIR" || exit 1
  if [ ! -f .env ]; then
    cp .env.example .env
    say "Created .env — add an API key next."
  fi
  chmod +x run.sh enable-boot.sh install.sh 2>/dev/null || true
  ensure_workspace_dirs
  if need_cmd systemctl; then
    ./enable-boot.sh >/dev/null
    say "Service: started"
  else
    say "Start with: ./run.sh"
  fi
}

# ---------------------------------------------------------------------------
say "AI Agent setup"
install_required_deps
install_optional_bwrap
fetch_repo
setup_env_and_service
ver=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || echo "?")
say ""
say "Done (v$ver)."
say "  nano $INSTALL_DIR/.env"
say "  open http://127.0.0.1:9191"
