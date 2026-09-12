# Debian AI Agent

Version: see `VERSION`.

Chat with Gemini in your browser. Files, shell, memory, search, reminders, and jobs — one stdlib Python script.

**Needs:** Python 3.8+ only (`./run.sh`).  
**No:** Apache, pip, Node, or a local AI model.

## Setup

1. Get a key: https://aistudio.google.com/apikey  
2. `cp .env.example .env` → set `GEMINI_API_KEY=...`  
3. `./run.sh` (or `python3 run.py`)  
4. Open http://127.0.0.1:8787  

Stop with Ctrl+C.

## Models

**Free** (default) or **Paid** in the page. Same key; Paid needs Google access for Pro models.

## Notes

- Key stays in `.env`, never in the browser.  
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
