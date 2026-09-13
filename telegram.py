"""
Optional Telegram DM bridge (long polling, no webhook).

When TELEGRAM_BOT_TOKEN is set in .env, a background thread polls getUpdates
and routes private messages through brain.run_chat (same path as the web UI).
Shell confirm becomes YES/NO in the chat. Group chats and non-text are ignored.

Imports from: config.py (token, allow-list, optional provider/model),
              brain.py (run_chat), tools.py (confirm/cancel pending shell,
              PENDING_SHELL).
Used by: run.py (start_telegram_thread).
"""
import json
import threading
import time
import urllib.error
import urllib.request

from config import (
    PENDING_SHELL,
    default_model,
    default_provider,
    telegram_allowed_chat_id,
    telegram_bot_token,
    telegram_model,
    telegram_provider,
)
from brain import run_chat
from tools import cancel_pending_shell, confirm_pending_shell


# Max characters per Telegram sendMessage (Bot API hard limit).
_TG_MAX = 4096
# Keep last N history entries (user+assistant pairs → ~10 turns).
_HISTORY_MAX = 20
# Long-poll timeout (seconds) for getUpdates.
_POLL_TIMEOUT = 25

# Per-chat short history for run_chat (in-memory only).
_histories = {}
# Avoid re-prompting YES/NO for the same pending command string.
_last_shell_prompt = {}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# API helpers (urllib only — no pip)
# ---------------------------------------------------------------------------


def api_call(method, params=None, token=None):
    """Call api.telegram.org/bot<token>/<method>. Never logs the token.

    params: dict of query/JSON fields. Returns parsed JSON or {"ok": False, ...}.
    """
    tok = token or telegram_bot_token()
    if not tok:
        return {"ok": False, "description": "no token"}
    url = "https://api.telegram.org/bot%s/%s" % (tok, method)
    data = None
    headers = {}
    if params:
        # POST application/json is fine for Bot API methods we use.
        data = json.dumps(params).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=_POLL_TIMEOUT + 15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "description": "HTTP %s %s" % (e.code, body)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "description": str(e)}


def send_text(chat_id, text, token=None):
    """Send text via sendMessage, splitting into <=4096 chunks if needed."""
    text = text if text is not None else ""
    if not text:
        text = "(empty)"
    chunks = []
    s = str(text)
    while s:
        chunks.append(s[:_TG_MAX])
        s = s[_TG_MAX:]
    ok_all = True
    for chunk in chunks:
        res = api_call(
            "sendMessage",
            {"chat_id": chat_id, "text": chunk},
            token=token,
        )
        if not res.get("ok"):
            ok_all = False
    return ok_all


# ---------------------------------------------------------------------------
# Allow-list helpers
# ---------------------------------------------------------------------------


def _allowed_id_str():
    """TELEGRAM_ALLOWED_CHAT_ID as a stripped string, or '' if unset."""
    return (telegram_allowed_chat_id() or "").strip()


def _is_allowed(chat_id):
    """True if chat_id matches the configured allow-list id."""
    want = _allowed_id_str()
    if not want:
        return False
    return str(chat_id) == want


# ---------------------------------------------------------------------------
# Shell YES/NO confirm over Telegram
# ---------------------------------------------------------------------------


def _pending_command():
    """Return the queued shell command string, or None."""
    if not PENDING_SHELL.exists():
        return None
    try:
        data = json.loads(PENDING_SHELL.read_text(encoding="utf-8"))
        return (data.get("command") or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


def maybe_prompt_shell_confirm(chat_id, token=None):
    """If a pending shell exists, ask the user to reply YES or NO (once per cmd)."""
    cmd = _pending_command()
    if not cmd:
        _last_shell_prompt.pop(chat_id, None)
        return False
    prev = _last_shell_prompt.get(chat_id)
    if prev == cmd:
        return True  # already prompted for this command
    msg = "Run shell?\n`%s`\nReply YES or NO." % cmd
    send_text(chat_id, msg, token=token)
    _last_shell_prompt[chat_id] = cmd
    return True


def _handle_shell_reply(chat_id, text, token=None):
    """If pending shell exists, handle YES/NO (or remind). Returns True if consumed."""
    cmd = _pending_command()
    if not cmd:
        return False
    low = (text or "").strip().lower()
    if low in ("yes", "y"):
        result = confirm_pending_shell()
        _last_shell_prompt.pop(chat_id, None)
        out_parts = []
        if result.get("ok"):
            stdout = (result.get("stdout") or "").strip()
            stderr = (result.get("stderr") or "").strip()
            body = []
            if stdout:
                body.append(stdout)
            if stderr:
                body.append(stderr)
            if body:
                out_parts.append("Done.\n" + "\n".join(body))
            else:
                out_parts.append("Done.")
        else:
            out_parts.append(result.get("error") or "Command failed")
        send_text(chat_id, "\n".join(out_parts), token=token)


