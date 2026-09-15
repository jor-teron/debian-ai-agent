"""
Persist and parse chat turns as Markdown under AI_HOME/memory/chats/.

Day files (YYYY-MM-DD.md) are the source of truth for UI refresh and Telegram.
HISTORY_TURNS (config) still caps how much prior chat is sent to the model;
these files may keep a full day on disk.

Format (locked):
  : linux-ai-agent chat
  : # user | ## assistant
  : started: <iso or date>

  # user message here

  ## assistant reply here

  # next user
  ## next assistant

Rules:
  - Lines starting with ':' are file header/meta (skipped when parsing turns).
  - '#' at line start = user turn (rest of line + body until next turn heading).
  - '##' at line start = assistant turn (check '##' before '#').

Imports from: ai_agent.config (MEMORY_CHATS_DIR, ensure_ws / ensure_memory_dirs).
Used by: server (persist + GET /api/chat/history), telegram (persist).
Stdlib only; Python 3.8+.
"""
import re
import threading
from datetime import datetime

from ai_agent.config import MEMORY_CHATS_DIR, ensure_memory_dirs, ensure_ws

# Serialize appends from web handler threads + Telegram poller.
_lock = threading.Lock()

# Turn headings: match '##' or '#' at line start (hashes group length distinguishes).
_HEADING_RE = re.compile(r"^(#{1,2})\s?(.*)$")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def chats_dir():
    """Return memory/chats/, creating the tree if needed."""
    ensure_ws()
    ensure_memory_dirs()
    MEMORY_CHATS_DIR.mkdir(parents=True, exist_ok=True)
    return MEMORY_CHATS_DIR


def chat_path_for_day(when=None):
    """Path to memory/chats/YYYY-MM-DD.md for the given (or current) local day."""
    when = when or datetime.now()
    return chats_dir() / ("%04d-%02d-%02d.md" % (when.year, when.month, when.day))


def _header_text(when=None):
    """Meta header written once when a new day file is created."""
    when = when or datetime.now()
    started = when.replace(microsecond=0).isoformat(sep="T")
    return (
        ": linux-ai-agent chat\n"
        ": # user | ## assistant\n"
        ": started: %s\n"
        "\n" % started
    )


def _normalize_newlines(text):
    """CRLF/CR → LF so day files stay consistent across clients."""
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


# ---------------------------------------------------------------------------
# Write (append one completed user + assistant exchange)
# ---------------------------------------------------------------------------


def append_exchange(user_text, assistant_text, when=None):
    """Append one completed user+assistant exchange to today's day file.

    Creates the file with a ':' meta header if it does not exist yet.
    Multiline messages are fine: text after the heading line becomes body
    until the next '#' / '##' turn marker.

    Returns {"ok": True, "path": ...} or {"ok": False, "error": ..., "path": ...}.
    Never raises.
    """
    user_text = _normalize_newlines("" if user_text is None else user_text)
    assistant_text = _normalize_newlines("" if assistant_text is None else assistant_text)
    when = when or datetime.now()
    path = chat_path_for_day(when)
    # Heading line carries the first line of content; further lines are body.
    block = "\n# %s\n\n## %s\n" % (user_text, assistant_text)
    try:
        with _lock:
            new_file = not path.exists()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                if new_file:
                    fh.write(_header_text(when))
                fh.write(block)
        return {"ok": True, "path": str(path)}
    except OSError as e:
        return {"ok": False, "error": str(e), "path": str(path)}


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------


def parse_chat_md(text):
    """Parse Markdown chat text into a list of {role, content} turns.

    Skips lines that start with ':'. A line matching '^##' starts an
    assistant turn; '^#' (exactly one hash) starts a user turn. '###' and
    longer are not turn markers (treated as body if inside a turn).
    Content is the rest of the heading line plus following body lines until
    the next turn heading.
    """
    if not text:
        return []
    turns = []
    current_role = None
    current_parts = []

    def _flush():
        nonlocal current_role, current_parts
        if current_role is None:
            current_parts = []
            return
        # Join heading-rest + body; strip outer whitespace for cleaner UI.
        content = "\n".join(current_parts).strip()
        turns.append({"role": current_role, "content": content})
        current_role = None
        current_parts = []

    for raw_line in _normalize_newlines(text).splitlines():
        # Meta / header lines: skip (do not treat as body).
        if raw_line.startswith(":"):
            continue
        m = _HEADING_RE.match(raw_line)
        if m:
            hashes, rest = m.group(1), m.group(2)
            if hashes == "##":
                _flush()
                current_role = "assistant"
                current_parts = [rest]
                continue
            if hashes == "#":
                _flush()
                current_role = "user"
                current_parts = [rest]
                continue
            # '###'+ falls through as body when inside a turn
        if current_role is not None:
            current_parts.append(raw_line)
        # Preamble before the first turn heading is ignored.
    _flush()
    return turns


def load_turns(when=None, path=None):
    """Load parsed turns from a day file (default: today). Missing → []."""
    p = path or chat_path_for_day(when)
    if not p.exists() or not p.is_file():
        return []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return []
    return parse_chat_md(text)


def history_for_api(when=None):
    """Dict for GET /api/chat/history: ok, turns, file (basename), path."""
    p = chat_path_for_day(when)
    turns = load_turns(path=p)
    return {
        "ok": True,
        "turns": turns,
        "file": p.name,
        "path": str(p),
    }
