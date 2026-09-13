# Debian AI Agent

Version: see `VERSION`.

Tiny browser chat agent (Gemini / ChatGPT / Grok / Claude / DeepSeek).

Install page: https://jor-teron.github.io/debian-ai-agent/

## Dependencies

- Python **3.8+** (`python3`)
- `git`
- At least one provider API key (see below)

## Install

One line:

```bash
curl -fsSL https://raw.githubusercontent.com/jor-teron/debian-ai-agent/main/install.sh | bash
```

Then edit keys and open the page:

```bash
nano ~/debian-ai-agent/.env
systemctl --user restart debian-ai-agent
```

Open http://127.0.0.1:9191

(`install.sh` is also in the repo if you prefer `git clone` then `./install.sh`.)

## API keys

| Provider | Env var | Get key |
|----------|---------|---------|
| gemini | `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| openai | `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| xai (Grok) | `XAI_API_KEY` | https://console.x.ai/ |
| anthropic | `ANTHROPIC_API_KEY` | https://console.anthropic.com/ |
| deepseek | `DEEPSEEK_API_KEY` | https://platform.deepseek.com/ |

In the page: **Provider → Free/Paid → Model**.

## Telegram (optional)

Chat from your phone without opening the LAN.

1. In Telegram, talk to **@BotFather** → `/newbot` → copy the token.
2. Put `TELEGRAM_BOT_TOKEN=…` in `~/debian-ai-agent/.env`.
3. Restart, DM the bot once — it replies with your **chat id**. Set `TELEGRAM_ALLOWED_CHAT_ID=…` and restart again.
4. Only that chat can talk to the agent. Shell confirm: reply **YES** or **NO**.

Uses long polling (no webhook / public URL). UI stays on `127.0.0.1:9191`.

## Notes

- Local browser only (`127.0.0.1:9191`). Remote chat via optional Telegram above.  

- Code: `config.py`, `tools.py`, `brain.py`, `ui.py`, `server.py`, `telegram.py`; `run.py` starts it.  
- Keys only in `.env` (never commit).  
- Files/tools: `/home/$USER/ai-agent`  
- Shell runs need Confirm in the UI (or YES/NO on Telegram).  
- Stop: `systemctl --user stop debian-ai-agent`  
- Manual run: `./run.sh`
