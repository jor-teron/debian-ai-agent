- One-line install via `install.sh` (detects apt-get/dnf/yum/pacman/zypper/apk; most Linux distros)
- Bubblewrap optional in install (`INSTALL_BWRAP=0/1` or prompt); install continues if bwrap unavailable
# Features

## Now
- **Modular layout** — `config.py` / `tools.py` / `brain.py` / `ui.py` / `server.py` / `telegram.py` / `run.py` (stdlib only; same behavior as the old single-file app)
- **Multi-provider chat** — Provider → Model → Model in the UI
  - **gemini** — Gemini generateContent + function calling (`GEMINI_API_KEY`)
  - **openai** — Chat Completions + tools (`OPENAI_API_KEY`); free: `gpt-4o-mini`, `gpt-4.1-mini`; paid: `gpt-4o`, `gpt-4.1`
  - **xai** — OpenAI-compatible at `https://api.x.ai/v1` (`XAI_API_KEY`); free: `grok-4.3`, `grok-3-mini` (legacy); paid: `grok-4.6`, `grok-4.5` (2026-09 public catalog)
  - **anthropic** — Messages API + tools (`ANTHROPIC_API_KEY`); free: `claude-haiku-4-5`; paid: `claude-sonnet-5`, `claude-sonnet-4-6`
  - **deepseek** — OpenAI-compatible at `https://api.deepseek.com/v1` (`DEEPSEEK_API_KEY`); free: `deepseek-chat`; paid: `deepseek-reasoner`
  - **openrouter** — OpenAI-compatible at `https://openrouter.ai/api/v1` (`OPENROUTER_API_KEY`); e.g. `openrouter/auto`, `openai/gpt-4o-mini`, `google/gemini-2.0-flash-001`, `meta-llama/llama-3.3-70b-instruct`
  - **deepinfra** — OpenAI-compatible at `https://api.deepinfra.com/v1/openai` (`DEEPINFRA_API_KEY`); e.g. `meta-llama/Meta-Llama-3.1-8B-Instruct`, `google/gemma-2-9b-it`
- Files + shell in `/home/$USER/ai-workspace`
- Background + start at login
- Memory — `memory/` tree (`session.md`, `user.md`, `assistant.md`, `date/YYYY_MM.md`, `topic/*.md`); tools + injected into system prompt; optional `SESSION_RESET_HOURS` / `SESSION_RESET_AFTER`; legacy `memory.md` migrates once
- Shell blocklist — expanded (rm -rf ~/$HOME/*, chmod/chown -R /, mkfs, dd, shutdown/reboot, crontab -r, useradd/del/passwd, wipefs, losetup, systemctl start/stop/…, curl|sh); sudo still refused
- Shell sandbox — bubblewrap (`bwrap`) when available: freehand run inside sandbox (workspace RW, tools RO, network on); without bwrap, Confirm / Telegram YES-NO as before; BLOCKED + sudo still refused
- Confirm before shell (fallback when no bwrap); success shows "Done." — sticky amber bar above the text box (Confirm/Cancel)
- Enter sends; Shift+Enter new line
- Dark mode by default
- Header shows version beside title; status: Ready · Provider / No key for Provider
- Update by re-running install.sh (keeps .env)
- Upload / download in the page
- Web search — Gemini Google Search tool (`web_search`); needs `GEMINI_API_KEY` even if chatting via another provider
- Reminders — `reminders.json`, notify-send, `/api/reminders`
- Scheduled jobs — `jobs.json` → `jobs_log.md` (uses default `PROVIDER`)
- Local UI on port **9191** (localhost only)
- **Telegram optional bridge** — long-poll DMs when `TELEGRAM_BOT_TOKEN` is set; allow-list via `TELEGRAM_ALLOWED_CHAT_ID`; same `run_chat` + YES/NO shell confirm; no webhook
- `/api/models` — `{ providers: {…}, default_provider, default_model }`
- `/api/health` — `keys` booleans per provider + `version` + `shell_sandbox` (`bwrap`|`none`) + `shell_freehand`

## Later
7. Command allow-list
