# AI Agent

Version: see `VERSION` (semver + change #, e.g. `0.1.26 (26)`).

Tiny browser chat agent (Gemini / ChatGPT / Grok / Claude / DeepSeek / OpenRouter / DeepInfra).  
Works on **most Linux distros**.

Install page: https://jor-teron.github.io/debian-ai-agent/

## Dependencies

- Python **3.8+** (`python3`)
- `git`
- `bubblewrap` (`bwrap`) — optional; setup asks **Install bubblewrap (sandbox)? [Y/n]** (pick **n** if unsupported). `INSTALL_BWRAP=0|1` skips the question.
- At least one provider API key (see below)

## Install

One line:

```bash
curl -fsSL https://raw.githubusercontent.com/jor-teron/debian-ai-agent/main/install.sh | bash
```

The installer detects `apt-get`, `dnf`, `yum`, `pacman`, `zypper`, or `apk`.  
Required: **python3**, **git**. Bubblewrap is optional (ask / `INSTALL_BWRAP=1`; skip on old glibc).  
If no package manager: **Manually install: python3, git**

Then edit keys and open the page:

```bash
nano ~/debian-ai-agent/.env
systemctl --user restart debian-ai-agent
```

Open http://127.0.0.1:9191

(`install.sh` is also in the repo if you prefer `git clone` then `./install.sh`.)

To **update** later, run the same install one-liner again (or `./install.sh` inside the folder). Your `.env` is kept.

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

In the page: **Provider → Model**.

## Telegram (optional)

Chat from your phone (PC stays on; browser not needed).

1. In Telegram, open **@BotFather** → `/newbot` → copy the token.
2. Put it in `.env` as `TELEGRAM_BOT_TOKEN=…` then restart the agent.
3. Message your bot once — it replies with your **chat id**.
4. Put that id in `.env` as `TELEGRAM_ALLOWED_CHAT_ID=…` and restart again.

Only your chat works. If it asks to run a command, reply **YES** or **NO**.

## Notes

- Local browser only (`127.0.0.1:9191`). Remote chat via optional Telegram above.  
- Code: `config.py`, `tools.py`, `brain.py`, `ui.py`, `server.py`, `telegram.py`; `run.py` starts it.  
- Keys only in `.env` (never commit).  
- Files/tools: `/home/$USER/ai-workspace`
- Memory: `ai-workspace/memory/` (`session.md`, `user.md`, `assistant.md`, `date/YYYY_MM.md`, `topic/*.md`); legacy `memory.md` migrates once  
- Shell: with `bwrap` installed, commands run freehand inside a bubblewrap sandbox (workspace RW, host tools RO). Without bubblewrap, Confirm in the UI (or YES/NO on Telegram) is still required.  
- Stop: `systemctl --user stop debian-ai-agent`  
- Manual run: `./run.sh`
