Versioning: `0.1.28 (28)` — semver + change # that +1 every release (never resets).

- One-line install via `install.sh` (detects apt-get/dnf/yum/pacman/zypper/apk; most Linux distros)
- Bubblewrap optional in install (`INSTALL_BWRAP=0/1` or prompt); install continues if bwrap unavailable

# Features

## Now
- **Modular layout** — `config.py` / `tools.py` / `brain.py` / `ui.py` / `server.py` / `telegram.py` / `run.py` (stdlib only)
- **Multi-provider chat** — Provider → Model in the UI (gemini, openai, xai, anthropic, deepseek, openrouter, deepinfra)
- **Workspace folders** — jail = whole `~/ai-workspace` with `memory/`, `workspace/`, `test/`, `trash/`, `user/`; prefer `workspace/` for new work; **`user/` agent read-only**
- **Light mode default** — dark available; theme toggle in header after version (`localStorage theme=light|dark`)
- **Update button** — after Model select → confirm → `POST /api/update` (`git pull --ff-only` + `systemctl --user restart`)
- Memory — `memory/` tree (`session.md`, `user.md`, `assistant.md`, `date/YYYY_MM.md`, `topic/*.md`); optional session reset envs
- Shell blocklist — destructive patterns blocked; **sudo allowed by default** (`ALLOW_SUDO=1`) but **always Confirm** (UI password / Telegram `YES password`)
- Shell sandbox — bubblewrap freehand when available; **network ON by default**; `SHELL_NET=0` → `--unshare-net`; without bwrap, Confirm / Telegram YES-NO
- Sticky confirm bar (sudo password field when pending sudo)
- Enter sends; Shift+Enter new line
- Header: version + theme toggle; status Ready · Provider / No key
- Upload / download in the page
- Web search — Gemini Google Search tool
- Reminders + scheduled jobs
- UI port **9191** (default localhost; `HOST=0.0.0.0` for LAN)
- **Telegram** — YES/NO case-insensitive; sudo: `YES password`; best-effort deleteMessage after password
- `/api/models`, `/api/health` (+ `shell_sandbox`, `shell_freehand`, `shell_net`, `allow_sudo`), `/api/update`

## Later
7. Command allow-list
