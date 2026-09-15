Versioning: `0.3.2 (35)` — semver + change # that +1 every release (never resets).

- One-line install via `install.sh` (detects apt-get/dnf/yum/pacman/zypper/apk; most Linux distros)
- Bubblewrap optional in install (`INSTALL_BWRAP=0/1` or prompt); install continues if bwrap unavailable

# Features

## Now
- **PUBLIC_BASE_URL / Tailscale downloads** — absolute `/api/download` links for Telegram when `PUBLIC_BASE_URL` is set; `HOST=0.0.0.0` + Tailscale IP; relative links when empty; no sendDocument
- **Chat history Markdown** — persist turns under `memory/chats/YYYY-MM-DD.md` (`:` header, `#` user, `##` assistant); `GET /api/chat/history`; web UI restores on refresh; `HISTORY_TURNS` still caps model context
- **Memory date dedupe** — `_dated_line` strips a leading `[YYYY-MM-DD]` / `YYYY-MM-DD:` the model may prepend so log lines keep a single system date
- Old project-name migrate leftovers removed from README / install (new installs never see them)
- **Package layout** — `ai_agent/` package (`python3 -m ai_agent`); root keeps install/run scripts, VERSION, `.env.example`, docs. Flat package files + `ai_agent/ui/` for static HTML/CSS/JS
- **Editable prompts** — `ai_agent/prompt_chat` (short system) + `prompt_tools` (extra when tools on); no giant `SYSTEM_BASE` in config
- **Token trim** — `TOOLS_DEFAULT=0` (tools schemas omitted by default); UI **Tools** checkbox (localStorage); keyword boost (run/shell/file/…); `HISTORY_TURNS=10`; soft-capped memory injection (~400/section, ~800 total)
- **Curated model files** — `models_ollama` / `models_llamacpp` (one id per line); `shell_blocklist` for BLOCKED patterns
- **Online / Local modes** — Mode dropdown before Provider; Provider list filters by mode; Model list by provider; mode persisted in `localStorage` (migrates saved `offline` → `local` once)
- **Multi-provider chat (online)** — gemini, openai, xai, anthropic, deepseek, openrouter, deepinfra
- **Local providers** — Ollama (`OLLAMA_BASE_URL`) and llama.cpp (`LLAMACPP_BASE_URL`); OpenAI-compatible; no API key; curated small models + Llama 3.1 70B (RAM warning)
- **Local tool fallback** — Ollama/local auto-skip or retry without tools when the model lacks tool support
- **Status LED** — green solid when ready; red blink when not; blink period `STATUS_BLINK_MS` (default 2000)
- **providers.py** — catalogs + readiness helpers; `config.py` re-exports
- **Workspace folders** — jail = whole `~/ai-workspace` with `memory/`, `workspace/`, `test/`, `trash/`, `user/`; **`user/` agent read-only**
- **Light mode default** — dark available; optional `.env` `UI_LIGHT_*` hex overrides
- **Update button** — `POST /api/update` (`git pull --ff-only` + `systemctl --user restart`)
- Memory — `memory/` tree; optional session reset envs
- Shell blocklist — destructive patterns blocked; **sudo** always Confirm
- Shell sandbox — bubblewrap freehand when available; network ON by default; `SHELL_NET=0` → `--unshare-net`
- Sticky confirm bar; Enter sends; Shift+Enter new line; upload/download
- Web search — Gemini Google Search tool; reminders + scheduled jobs
- UI port **9191**; **Telegram** YES/NO / sudo password (same brain path; respects `TOOLS_DEFAULT`)
- Static UI routes: `/`, `/ui/style.css`, `/ui/app.js`

## Later
7. Command allow-list
8. Optional UI install/pull helpers for Ollama models
9. **No Docker** — not pursuing; keep Bubblewrap. Docker is a different model (images/containers), bigger install/RAM, extra command latency, and fights host OS hooks (workspace, systemd user service, Telegram, Update). Optional community Dockerfile only if someone asks — never default install.
