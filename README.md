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

Open http://127.0.0.1:8787

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

## Notes

- Code: `config.py`, `tools.py`, `brain.py`, `ui.py`, `server.py`; `run.py` starts it.  
- Keys only in `.env` (never commit).  
- Files/tools: `/home/$USER/ai-agent`  
- Phone on Wi‑Fi: `HOST=0.0.0.0` in `.env`, then restart.  
- Shell runs need Confirm in the UI.  
- Stop: `systemctl --user stop debian-ai-agent`  
- Manual run: `./run.sh`
