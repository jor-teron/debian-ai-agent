# Debian AI Agent (simple)

Chat with Gemini in your browser. The app can also work with files and shell commands inside a safe folder.

**Needs:** Python **3.8+** (the normal `python3` on Debian/Ubuntu/Raspberry Pi, Windows, macOS). Stdlib only — no special Python flavor.  
**Does not need:** Apache, Node, Docker, pip, or a local AI model.

---

## 1. Get a free API key

1. Open https://aistudio.google.com/apikey  
2. Sign in with Google  
3. Create an API key and copy it  
4. Do **not** share the key in chats or on GitHub  

## 2. Setup (one time)

```bash
cd debian-ai-agent
cp .env.example .env
nano .env
```

Put your key on this line:

```
GEMINI_API_KEY=paste_your_key_here
```

Save and exit (`Ctrl+O`, Enter, `Ctrl+X` in nano).

## 3. Run

```bash
./run.sh
# or: python3 run.py
```

## Which `python` command?

Some PCs have confusing names: `python`, `python2`, `python3`, `python3ispython`, …

**Easiest:** from this folder run:

```bash
./run.sh
```

That script picks a real **Python 3.8+** for you.

Or run explicitly:

```bash
python3 run.py
```

| If this happens | Do this |
|-----------------|--------|
| `python` opens Python 2 | Use `python3` or `./run.sh` |
| `python3: command not found` | Debian/Ubuntu: `sudo apt install python3` |
| Several versions installed | Prefer `./run.sh` — it checks the version |
| Windows | Install Python 3 from python.org, tick “Add to PATH”, then `py -3 run.py` or `python run.py` |

Check what you have:

```bash
python3 --version
# or
./run.sh
```



Open in your browser: **http://127.0.0.1:8787**

Stop the app with `Ctrl+C` in the terminal.

---

## Free vs Paid models

In the webpage, pick **Free** (default, Flash) or **Paid** (Pro).  
Same API key — Paid only works if your Google project allows those models.

---

## Safety

- Files/commands stay inside `agent-workspace/` next to this app (unless you change that in code later).
- Only listens on your own computer (`127.0.0.1`), not the whole Wi‑Fi.
- Your API key stays in `.env` on the PC, not in the webpage.

---

## Troubleshooting

| Problem | Fix |
|--------|-----|
| “API key missing” | Edit `.env`, save, run `python3 run.py` again |
| Browser can’t connect | Make sure `python3 run.py` is still running |
| Paid model error | Switch the UI back to **Free** |
| `Need Python 3.8+` | Install/update Python 3, then run `python3 --version` |

That’s it.
