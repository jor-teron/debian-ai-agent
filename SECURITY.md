# Security notes — Debian AI Agent

## Localhost only

The server binds to **127.0.0.1** by default (`HOST` in `.env`).

- Browsers on **this** PC can open http://127.0.0.1:8787
- Other phones/PCs on your network **cannot** reach it unless you change `HOST` to `0.0.0.0` (not recommended)

Never expose this agent to the public internet without authentication and a reverse proxy you trust.

## Workspace jail

File tools (`list_dir`, `read_file`, `write_file`) and the default shell working directory are limited to:

```
WORKSPACE=/home/user/agent-workspace
```

Paths that resolve outside that folder are **rejected** unless:

```
AGENT_ALLOW_SYSTEM=1
```

That override is powerful: the agent could then read files like `/etc/passwd` with your user permissions. Only enable it when you intentionally want that.

## Shell safeguards

`run_shell`:

- Runs as your normal user (not root)
- Has a timeout (default 30s, max 120s)
- Blocks `sudo` unless `AGENT_ALLOW_SUDO=1`
- Blocks obvious disasters (`rm -rf /`, `mkfs`, `dd` to `/dev/…`, fork bombs)

These are **guards**, not a full sandbox. A clever command can still do a lot as your user. Prefer the workspace for file work.

## API key

- Stored in local `.env` (not committed; see `.gitignore`)
- Sent only to Google’s Gemini API over HTTPS
- Health endpoint reports **whether a key is set** (boolean), never the key itself

## Logs

`logs/tools.jsonl` records tool names, args, and success/error. Review it if something unexpected happened. It may contain file paths and command strings — treat it as sensitive.

## Summary

| Default | Safer choice |
|---|---|
| `HOST=127.0.0.1` | Keep it |
| Workspace jail on | Keep it |
| No sudo | Keep it |
| `.env` private | Never paste keys into chat or GitHub |
