# Debian AI Agent

Chat with Gemini in your browser. Can use files/commands inside a safe folder.

**Needs:** Python 3.8+ only (`./run.sh` finds it).  
**No:** Apache, pip, Node, or a local AI model.

## Setup

1. Get a key: https://aistudio.google.com/apikey  
2. `cp .env.example .env` → put `GEMINI_API_KEY=...` in `.env`  
3. `./run.sh` (or `python3 run.py`)  
4. Open http://127.0.0.1:8787  

Stop with Ctrl+C.

## Models

**Free** (default) or **Paid** in the page. Same key; Paid needs Google access for Pro models.

## Notes

- Key stays in `.env`, not in the webpage.  
- Tools stay in `agent-workspace/`.  
- Listens on this PC only (`127.0.0.1`).

If `./run.sh` fails: `sudo apt install python3` then try again.

## Background + start at boot

```bash
./enable-boot.sh
```

Runs behind the scenes and starts after you log in.  
Stop: `systemctl --user stop debian-ai-agent`
