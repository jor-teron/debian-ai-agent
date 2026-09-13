- One-line install via `install.sh`
# Features

## Now
- **Modular layout** — `config.py` / `tools.py` / `brain.py` / `ui.py` / `server.py` / `run.py` (stdlib only; same behavior as the old single-file app)
- **Multi-provider chat** — Provider → Free/Paid → Model in the UI
  - **gemini** — Gemini generateContent + function calling (`GEMINI_API_KEY`)
  - **openai** — Chat Completions + tools (`OPENAI_API_KEY`); free: `gpt-4o-mini`, `gpt-4.1-mini`; paid: `gpt-4o`, `gpt-4.1`
  - **xai** — OpenAI-compatible at `https://api.x.ai/v1` (`XAI_API_KEY`); free: `grok-4.3`, `grok-3-mini` (legacy); paid: `grok-4.6`, `grok-4.5` (2026-09 public catalog)
  - **anthropic** — Messages API + tools (`ANTHROPIC_API_KEY`); free: `claude-haiku-4-5`; paid: `claude-sonnet-5`, `claude-sonnet-4-6`
  - **deepseek** — OpenAI-compatible at `https://api.deepseek.com/v1` (`DEEPSEEK_API_KEY`); free: `deepseek-chat`; paid: `deepseek-reasoner`
- Files + shell in `/home/$USER/ai-agent`
- Background + start at login
- Memory — `memory.md`; tools + injected into system prompt
- Confirm before shell — sticky amber bar above the text box (Confirm/Cancel)
- Enter sends; Shift+Enter new line
- Dark mode by default
- Upload / download in the page
- Web search — Gemini Google Search tool (`web_search`); needs `GEMINI_API_KEY` even if chatting via another provider
- Reminders — `reminders.json`, notify-send, `/api/reminders`
- Scheduled jobs — `jobs.json` → `jobs_log.md` (uses default `PROVIDER`)
- Phone/LAN — `HOST=0.0.0.0` in `.env`
- `/api/models` — `{ providers: {…}, default_provider, default_model }`
- `/api/health` — `keys` booleans per provider + `version`

## Later
7. Command allow-list
