# Debian AI Agent

Version: see `VERSION`.

Chat with Gemini, OpenAI, xAI (Grok), Anthropic (Claude), or DeepSeek in your browser. Files, shell, memory, search, reminders, and jobs — one stdlib Python script.

**Needs:** Python 3.8+ only (`./run.sh`).  
**No:** Apache, pip, Node, or a local AI model.

## Setup

1. Get an API key for at least one provider (see below).  
2. `cp .env.example .env` → set `PROVIDER=` and the matching `*_API_KEY=`  
3. `./run.sh` (or `python3 run.py`)  
4. Open http://127.0.0.1:8787  

Stop with Ctrl+C.

## Provider keys

| Provider   | Env var             | Get a key |
|------------|---------------------|-----------|
| gemini     | `GEMINI_API_KEY`    | https://aistudio.google.com/apikey |
| openai     | `OPENAI_API_KEY`    | https://platform.openai.com/api-keys |
| xai        | `XAI_API_KEY`       | https://console.x.ai/ |
| anthropic  | `ANTHROPIC_API_KEY` | https://console.anthropic.com/ |
| deepseek   | `DEEPSEEK_API_KEY`  | https://platform.deepseek.com/ |

Set `PROVIDER=gemini` (default) or another id. In the page: **Provider → Free/Paid → Model**.

`web_search` always uses Gemini Google Search when `GEMINI_API_KEY` is set; otherwise it returns a clear error.

## Models

**Free** (cheaper/faster) or **Paid** (stronger) per provider. Allowlists are in the app; see `FEATURES.md`.

## Notes

- Keys stay in `.env`, never in the browser.  
- Workspace: `/home/$USER/ai-agent` (`WORKSPACE=` in `.env`).  
- Shell needs Confirm/Cancel in the UI.  
- Upload via file picker; download `/api/download?name=…`.  
- Reminders use `notify-send` when due; jobs append to `jobs_log.md`.  
- Set `HOST=0.0.0.0` to open from phone on same WiFi.

If `./run.sh` fails: `sudo apt install python3` then try again.

## Background + start at boot

```bash
./enable-boot.sh
```

Runs in the background after login. Stop: `systemctl --user stop debian-ai-agent`
