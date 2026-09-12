# Debian AI Agent

A **small personal AI chat** that runs on *your* Debian computer.

- Opens in your browser at **http://127.0.0.1:8787**
- Talks to **Google Gemini** online — no big AI model downloaded to your PC
- Lets you pick **Free** (Flash) or **Paid** (Pro) models in the UI
- Can list / read / write files and run shell commands **inside a safe folder** (`agent-workspace`)
- Listens on **localhost only** so other devices on your Wi‑Fi cannot open it

You do **not** need Git to run this app. Git is only optional if you also want a GitHub copy.

---

## What you need

1. **Debian** (or similar) with **Python 3.11+** (3.13 is fine)
2. A **Gemini API key** from Google AI Studio (free to create)
3. A few dozen megabytes of disk for a Python virtual environment

If you have a **Gemini Pro / paid Google AI** subscription or a billed Cloud project, you can also use the **Paid** models in the UI. The same `GEMINI_API_KEY` is used; access depends on what that key’s project is allowed to call.

No Node.js build. No local LLM. Designed for low RAM (~3–4 Gi machines).

---

## Free vs Paid models

| Category | When to use | Examples (allowlisted) |
|---|---|---|
| **Free** (default) | Everyday chat, more free-tier requests | `gemini-3.5-flash-lite` (default), `gemini-3.5-flash`, `gemini-3.6-flash`, `gemini-2.5-flash` |
| **Paid** | Harder reasoning / coding with Pro models | `gemini-2.5-pro`, `gemini-3.1-pro-preview` |

- First visit defaults to **Free → 3.5 Flash-Lite**.
- Your choice is remembered in the browser (`localStorage`) and sent as `"model"` on each chat request.
- The server **only** accepts models on its allowlist. Unknown values fall back to Free Flash.
- Paid models will fail with a clear error if your key/project does not have access — switch back to Free or enable billing / Pro on the Google side.

Default in `.env`:

```
GEMINI_MODEL=gemini-3.5-flash-lite
```

---

## 1. Get a Gemini API key

1. Open [Google AI Studio – API keys](https://aistudio.google.com/apikey).
2. Sign in with your Google account.
3. Click **Create API key**.
4. Copy the key (treat it like a password).

Use that key for both Free and Paid. Paid/Pro models need the project behind the key to have the right access (billing or Gemini Pro entitlements).

---

## 2. Put the key in `.env`

```bash
cd /home/user/debian-ai-agent
nano .env
```

Set:

```
GEMINI_API_KEY=AIza...yourkey...
```

Save (`Ctrl+O`, Enter, `Ctrl+X` in nano). **Do not** commit `.env` to GitHub (it is gitignored).

---

## 3. Install (one-time)

```bash
cd /home/user/debian-ai-agent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
chmod +x run.sh
mkdir -p /home/user/agent-workspace
```

If `.venv` already exists, you can skip creating it and just re-run `pip install -r requirements.txt` after updates.

---

## 4. Run

```bash
cd /home/user/debian-ai-agent
./run.sh
```

Open **http://127.0.0.1:8787** on the same computer. Stop with `Ctrl+C`.

In the header: choose **Free** or **Paid**, then pick a model from the dropdown.

---

## Safety (please read)

| Protection | Meaning |
|---|---|
| **Localhost only** | Bound to `127.0.0.1` — not your LAN |
| **Workspace jail** | Tools stay under `/home/user/agent-workspace` unless you opt out |
| **No sudo by default** | Shell rejects `sudo` unless `AGENT_ALLOW_SUDO=1` |
| **Disaster blocks** | Blocks `rm -rf /`, `mkfs`, `dd` to disks |

Optional (more power = more risk):

```bash
export AGENT_ALLOW_SYSTEM=1   # allow paths outside the workspace
export AGENT_ALLOW_SUDO=1     # allow sudo in run_shell
```

See **SECURITY.md**.

---

## Example chats

- “List the files in my workspace”
- “Create notes.txt saying hello”
- “Read notes.txt”
- “Run `ls -la`”
- Switch to **Paid → 2.5 Pro** and ask a harder coding/planning question

Tool chips under replies show which tools ran (✓ / ✗).

---

## API

- `GET /api/health` → ok + `api_key_set` (boolean only) + default model
- `GET /api/models` → Free/Paid allowlists for the UI
- `POST /api/chat` → `{ "message": "...", "model": "gemini-3.5-flash-lite" }`  
  → `{ reply, tool_traces, model, category, ... }`

Tool audit log: `logs/tools.jsonl`.

---

## Troubleshooting

**API key missing** — edit `.env`, restart `./run.sh`.

**Paid model errors** — your key may be free-tier only. Use **Free**, or enable billing/Pro for that Google project.

**Model not found** — pick another from the dropdown; the app also tries same-category fallbacks.

**Outside workspace jail** — put files in `/home/user/agent-workspace`, or only if you understand the risk set `AGENT_ALLOW_SYSTEM=1`.

**Port in use** — set `PORT=8788` in `.env`.

---

## Optional: GitHub copy

Running the app does **not** require Git. To keep a remote backup:

```bash
cd /home/user/debian-ai-agent
git init
git add .
git status   # confirm .env is NOT listed
git commit -m "Personal Debian AI agent"
# create an empty GitHub repo, then:
# git remote add origin git@github.com:YOU/debian-ai-agent.git
# git push -u origin main
```

Never delete or wipe this folder to “make room” for GitHub — keep the local install and push from it.

---

## Project layout

```
debian-ai-agent/
  app/
    server.py           # HTTP API + static UI
    brain.py            # Gemini + tool loop
    tools.py            # list/read/write/shell + jail
    models_catalog.py   # Free vs Paid allowlist
    static/index.html
  logs/
  .env / .env.example
  requirements.txt
  run.sh
  README.md
  SECURITY.md
```

Workspace: `/home/user/agent-workspace/`

Enjoy — keep the key private, prefer **Free** day-to-day, and use **Paid** when you need Pro muscle.
