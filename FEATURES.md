Versioning: `0.4.0 (36)` — semver + change # that +1 every release (never resets).

- One-line install via `install.sh` (detects apt-get/dnf/yum/pacman/zypper/apk; most Linux distros)
- Bubblewrap optional in install (`INSTALL_BWRAP=0/1` or prompt); install continues if bwrap unavailable

# Features

## Now
- **Tasks** — header **Task** dropdown: Chat | Image | Video | Vision; **Mode** Online | Local (never grayed out); labels above Task/Mode/Provider/Model
- **Short LED** — status text `OK` / `No key` / `No model` (no provider/model name)
- **Image / Video / Vision** — Online APIs where available (Gemini image + Veo best-effort, OpenAI Images, multimodal vision); Local best-effort / clear unsupported; saves under `workspace/generated/`
- **Telegram media attach** — `sendPhoto` / `sendVideo` / `sendDocument` multipart (≤50MB); no Download: http link injection; photos → Vision; `/image` `/video` shortcuts
- **PUBLIC_BASE_URL** — still for web/LAN absolute `/api/download`; Telegram does not rely on links
- **Chat history Markdown** — persist turns under `memory/chats/YYYY-MM-DD.md`; `GET /api/chat/history`; web UI restores on refresh; `HISTORY_TURNS` caps model context
- **Memory date dedupe** — `_dated_line` strips a leading date the model may prepend
- **Package layout** — `ai_agent/` package; `media.py` + `tasks.py` helpers; `ai_agent/ui/` static files
- **Editable prompts** — `prompt_chat` / `prompt_tools` / `prompt_image` / `prompt_video` / `prompt_vision`
- **Token trim** — `TOOLS_DEFAULT=0`; UI **Tools** checkbox; keyword boost; `HISTORY_TURNS=10`
- **Online / Local modes** — Mode before Provider; catalogs for all tasks
- **Multi-provider chat (online)** — gemini, openai, xai, anthropic, deepseek, openrouter, deepinfra
- **Local providers** — Ollama + llama.cpp; OpenAI-compatible; no API key
- **Status LED** — green solid when ready; red blink when not; `STATUS_BLINK_MS`
- **Workspace folders** — jail = `~/ai-workspace` with `memory/`, `workspace/`, `workspace/generated/`, `test/`, `trash/`, `user/`
- **Light mode default** — dark available; optional `UI_LIGHT_*` hex overrides
- **Update button** — `POST /api/update`
- Shell blocklist + sudo Confirm; bubblewrap freehand when available
- Sticky confirm bar; Enter sends; upload/download; web search / reminders / jobs
- UI port **9191**; Telegram YES/NO / sudo password

## Later
7. Command allow-list
8. Optional UI install/pull helpers for Ollama models
9. **No Docker** — not pursuing; keep Bubblewrap.
