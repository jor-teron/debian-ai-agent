Versioning: `0.1.31 (31)` — semver + change # that +1 every release (never resets).

- One-line install via `install.sh` (detects apt-get/dnf/yum/pacman/zypper/apk; most Linux distros)
- Bubblewrap optional in install (`INSTALL_BWRAP=0/1` or prompt); install continues if bwrap unavailable

# Features

## Now
- **Modular layout** — `config.py` / `providers.py` / `tools.py` / `brain.py` / `ui.py` / `server.py` / `telegram.py` / `run.py` (stdlib only)
- **Online / Offline modes** — Mode dropdown before Provider; Provider list filters by mode; Model list by provider; mode persisted in `localStorage`
- **Multi-provider chat (online)** — gemini, openai, xai, anthropic, deepseek, openrouter, deepinfra
- **Offline providers** — Ollama (`OLLAMA_BASE_URL`, default `http://127.0.0.1:11434`) and llama.cpp (`LLAMACPP_BASE_URL`, default `http://127.0.0.1:8080`); OpenAI-compatible; no API key; curated small models + Llama 3.1 70B (RAM warning). Local install stays out of `install.sh`
- **Offline tool fallback** — Ollama/local auto-skip or retry without tools when the model lacks tool support (tiny models like tinydolphin/tinyllama)
- **Status LED** — round LED beside short status (`OK · Gemini` / `No key · …` / `Offline · …`); green solid when ready; red blink when not; blink period `STATUS_BLINK_MS` (default 2000, `.env` only)
- **providers.py** — catalogs + `list_modes` / `list_providers` / `list_models` / `get_provider_meta` / `provider_ready`; `config.py` re-exports for compatibility
- **Workspace folders** — jail = whole `~/ai-workspace` with `memory/`, `workspace/`, `test/`, `trash/`, `user/`; prefer `workspace/` for new work; **`user/` agent read-only**
- **Light mode default** — dark available; theme toggle in header after version (`localStorage theme=light|dark`)
- **Softer light theme** — no pure white; soft gray page/panels/bubbles (~25/75); bigger header controls (`#themeBtn`, Update, selects, LED); optional `.env` `UI_LIGHT_*` hex overrides (served via `/api/health` + `/api/models`, applied in light theme only)
- **Update button** — after Model select → confirm → `POST /api/update` (`git pull --ff-only` + `systemctl --user restart`)
- Memory — `memory/` tree (`session.md`, `user.md`, `assistant.md`, `date/YYYY_MM.md`, `topic/*.md`); optional session reset envs
- Shell blocklist — destructive patterns blocked; **sudo allowed by default** (`ALLOW_SUDO=1`) but **always Confirm** (UI password / Telegram `YES password`)
- Shell sandbox — bubblewrap freehand when available; **network ON by default**; `SHELL_NET=0` → `--unshare-net`; without bwrap, Confirm / Telegram YES-NO
- Sticky confirm bar (sudo password field when pending sudo)
- Enter sends; Shift+Enter new line
- Composer — textarea, file upload, and Send aligned to ~44px height
- Upload / download in the page
- Web search — Gemini Google Search tool
- Reminders + scheduled jobs
- UI port **9191** (default localhost; `HOST=0.0.0.0` for LAN)
- **Telegram** — YES/NO case-insensitive; sudo: `YES password`; best-effort deleteMessage after password; uses stored/default provider (unchanged)
- `/api/models` — modes + providers + models + `status_blink_ms` + `ui_light`; `/api/health` — keys, `providers_ready`, optional `selected` readiness for LED, `status_blink_ms`, `ui_light`; `/api/update`

## Later
7. Command allow-list
8. Optional UI install/pull helpers for Ollama models
9. **No Docker** — not pursuing; keep Bubblewrap. Docker is a different model (images/containers), bigger install/RAM, extra command latency, and fights host OS hooks (workspace, systemd user service, Telegram, Update). Optional community Dockerfile only if someone asks — never default install.
