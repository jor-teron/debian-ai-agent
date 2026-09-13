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
        return True
    if low in ("no", "n"):
        cancel_pending_shell()
        _last_shell_prompt.pop(chat_id, None)
        send_text(chat_id, "Shell cancelled.", token=token)
        return True
    # Pending but not YES/NO — require a clear answer first.
    send_text(chat_id, "Pending shell — reply YES or NO", token=token)
    maybe_prompt_shell_confirm(chat_id, token=token)
    return True


# ---------------------------------------------------------------------------
# Message handling + short history
# ---------------------------------------------------------------------------


def _history_for(chat_id):
    """Return (and keep) the in-memory history list for this chat."""
    with _lock:
        if chat_id not in _histories:
            _histories[chat_id] = []
        return _histories[chat_id]


def _append_history(chat_id, role, content):
    """Append one turn and trim to _HISTORY_MAX entries."""
    hist = _history_for(chat_id)
    hist.append({"role": role, "content": content})
    if len(hist) > _HISTORY_MAX:
        del hist[: len(hist) - _HISTORY_MAX]


def handle_message(update, token=None):
    """Process one Telegram update (private text only)."""
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    chat = msg.get("chat") or {}
    # v1: private DMs only
    if (chat.get("type") or "") != "private":
        return
    # Ignore non-text (stickers, photos, …)
    text = msg.get("text")
    if text is None:
        return
    text = str(text).strip()
    if not text:
        return
    chat_id = chat.get("id")
    if chat_id is None:
        return

    # Allow-list: if unset, tell them their chat id and do not run the agent.
    if not _allowed_id_str():
        send_text(
            chat_id,
            "Your Telegram chat id is: %s\n"
            "Add this to .env and restart:\n"
            "TELEGRAM_ALLOWED_CHAT_ID=%s" % (chat_id, chat_id),
            token=token,
        )
        return

    if not _is_allowed(chat_id):
        # Quietly ignore unknown chats (no info leak).
        return

    # Shell confirm takes priority over normal chat.
    if _handle_shell_reply(chat_id, text, token=token):
        return

    provider = telegram_provider()
    model = telegram_model()
    hist = list(_history_for(chat_id))
    result = run_chat(text, provider=provider, model=model, history=hist)
    reply = (result.get("reply") or "").strip()
    if not result.get("ok"):
        err = result.get("error") or "chat failed"
        reply = reply or ("Error: %s" % err)
    if not reply:
        reply = "(No reply)"
    send_text(chat_id, reply, token=token)
    _append_history(chat_id, "user", text)
    _append_history(chat_id, "assistant", reply)

    # After the chat reply, prompt for shell confirm if tools queued one.
    maybe_prompt_shell_confirm(chat_id, token=token)


# ---------------------------------------------------------------------------
# Long-polling loop
# ---------------------------------------------------------------------------


def _poll_loop(token):
    """Long-poll getUpdates forever (daemon thread). Uses offset to ack updates."""
    offset = None
    # Verify token once (mask in any print — we only print a short status).
    me = api_call("getMe", token=token)
    if not me.get("ok"):
        print("Telegram: getMe failed — check TELEGRAM_BOT_TOKEN")
        return
    while True:
        params = {"timeout": _POLL_TIMEOUT}
        if offset is not None:
            params["offset"] = offset
        try:
            # getUpdates with long poll — pass timeout in params.
            res = api_call("getUpdates", params, token=token)
        except Exception:  # noqa: BLE001
            time.sleep(3)
            continue
        if not res.get("ok"):
            # Transient network / 429 — back off briefly.
            time.sleep(3)
            continue
        for upd in res.get("result") or []:
            uid = upd.get("update_id")
            if uid is not None:
                offset = uid + 1
            try:
                handle_message(upd, token=token)
            except Exception as e:  # noqa: BLE001
                # Never crash the poller on one bad message.
                print("Telegram: handle error: %s" % e)


def start_telegram_thread():
    """Start the Telegram poller as a daemon thread if a token is set.

    No token → no-op (safe to call always). Returns True if started.
    """
    token = telegram_bot_token()
    if not token:
        return False
    t = threading.Thread(
        target=_poll_loop,
        args=(token,),
        name="telegram-poll",
        daemon=True,
    )
    t.start()
    return True
