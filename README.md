# AI Agent (linux-ai-agent)

Version: see `VERSION` (semver + change #, e.g. `0.3.2 (35)`).

Tiny browser chat agent for most Linux distros. Cloud providers (Gemini, ChatGPT, Grok, Claude, DeepSeek, OpenRouter, DeepInfra) plus **Online / Local** modes for Ollama or llama.cpp on your machine.

Install page: https://jor-teron.github.io/linux-ai-agent/

## Dependencies

- Python **3.8+** (`python3`)
- `git`
- `bubblewrap` (`bwrap`) — optional; setup asks **Install bubblewrap (sandbox)? [Y/n]** (pick **n** if unsupported). `INSTALL_BWRAP=0|1` skips the question.
- At least one provider API key for Online mode (Local needs a running Ollama / llama.cpp)

## Install

One line:

```bash
curl -fsSL https://raw.githubusercontent.com/jor-teron/linux-ai-agent/main/install.sh | bash
```

The installer detects `apt-get`, `dnf`, `yum`, `pacman`, `zypper`, or `apk`.  
Required: **python3**, **git**. Bubblewrap is optional (ask / `INSTALL_BWRAP=1`; skip on old glibc).  
If no package manager: **Manually install: python3, git**

Then edit keys and open the page:

```bash
nano ~/linux-ai-agent/.env
systemctl --user restart linux-ai-agent
```

Open http://127.0.0.1:9191

(`install.sh` is also in the repo if you prefer `git clone` then `./install.sh`.)

To **update** later: use the **Update** button in the UI, or run the install one-liner / `./install.sh` again. Your `.env` is kept.


## API keys

| Provider | Env var | Get key |
|----------|---------|---------|
| gemini | `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| openai | `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| xai (Grok) | `XAI_API_KEY` | https://console.x.ai/ |
| anthropic | `ANTHROPIC_API_KEY` | https://console.anthropic.com/ |
| deepseek | `DEEPSEEK_API_KEY` | https://platform.deepseek.com/ |
| openrouter | `OPENROUTER_API_KEY` | https://openrouter.ai/keys |
| deepinfra | `DEEPINFRA_API_KEY` | https://deepinfra.com/dash/api_keys |

In the page: **Mode (Online / Local) → Provider → Model**. Use the **Tools** checkbox when you want tool schemas (default off to save tokens).

## Telegram (optional)

Chat from your phone (PC stays on; browser not needed).

1. In Telegram, open **@BotFather** → `/newbot` → copy the token.
2. Put it in `.env` as `TELEGRAM_BOT_TOKEN=…` then restart the agent.
3. Message your bot once — it replies with your **chat id**.
4. Put that id in `.env` as `TELEGRAM_ALLOWED_CHAT_ID=…` and restart again.

Only your chat works. If it asks to run a command, reply **YES** or **NO** (any case). For sudo: **YES yourpassword** (or **Y yourpassword**).

File download links in Telegram use `PUBLIC_BASE_URL` when set (absolute URL to `/api/download`); otherwise relative. No `sendDocument` in this release — open the link in the phone browser (Tailscale).

## Notes

- Browser: default `127.0.0.1:9191`. For LAN / Tailscale, set `HOST=0.0.0.0` (localhost on the PC still works) and open `http://PC-IP:9191`. Set `PUBLIC_BASE_URL=http://100.x.y.z:9191` (your Tailscale IP) so Telegram download links are absolute and open on your phone. Telegram still optional for away-from-home.
- Chat history: each turn is appended to `~/ai-workspace/memory/chats/YYYY-MM-DD.md` (`#` user / `##` assistant). Web UI reloads today's file on refresh via `GET /api/chat/history`.
- Layout: install scripts + docs at repo root; Python package in `ai_agent/` (`python3 -m ai_agent` via `./run.sh`). Edit prompts in `ai_agent/prompt_chat` / `prompt_tools`, UI in `ai_agent/ui/`, model lists in `models_ollama` / `models_llamacpp`, shell blocklist in `shell_blocklist`.
- Token trim: `TOOLS_DEFAULT=0` (tools off unless UI Tools on or message keywords); `HISTORY_TURNS=10`.
- Keys only in `.env` (never commit).
- Files/tools jail: `/home/$USER/ai-workspace` with `memory/`, `workspace/`, `test/`, `trash/`, `user/` (prefer `workspace/` for new work; `user/` is agent read-only)
- Memory: `ai-workspace/memory/` (`session.md`, `user.md`, `assistant.md`, `date/YYYY_MM.md`, `topic/*.md`); legacy `memory.md` migrates once
- Shell: with `bwrap`, freehand inside sandbox (network ON by default; `SHELL_NET=0` to disable). Without bwrap, Confirm / Telegram YES-NO. `sudo` always Confirm (`ALLOW_SUDO=1` default).
- UI: light theme default (toggle for dark); **Update** button pulls git and restarts the user service.
- Stop: `systemctl --user stop linux-ai-agent`
- Manual run: `./run.sh`
