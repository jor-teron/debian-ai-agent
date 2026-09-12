# Debian AI Agent

Version: see `VERSION`.

Tiny browser chat agent (Gemini / ChatGPT / Grok / Claude / DeepSeek).  
Python 3.8+ only — no pip, Apache, Node, or local model.

## Install

Copy-paste:

```bash
sudo apt update && sudo apt install -y python3 git
git clone https://github.com/jor-teron/debian-ai-agent.git ~/debian-ai-agent
cd ~/debian-ai-agent
cp .env.example .env
nano .env
# set at least one key, e.g.:
#   PROVIDER=xai
#   XAI_API_KEY=your_key_here
./enable-boot.sh
```

Then open http://127.0.0.1:8787

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

- Keys only in `.env` (never commit).  
- Files/tools: `/home/$USER/ai-agent`  
- Phone on Wi‑Fi: `HOST=0.0.0.0` in `.env`, then restart.  
- Shell runs need Confirm in the UI.  
- `web_search` needs a working Gemini key.  
- Stop service: `systemctl --user stop debian-ai-agent`  
- Manual run (no boot): `./run.sh`
