"""
Persist and parse chat turns as Markdown under AI_HOME/memory/chats/.

Day files live at memory/chats/YYYY_MM/YYYY_MM_DD.md (e.g.
memory/chats/2026_09/2026_09_15.md). They are the disk archive / source of
truth for UI refresh and Telegram. HISTORY_TURNS (config) still caps how much
prior chat is sent to the model; these files may keep a full day on disk and
are NOT sent wholesale to the API.

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


def _month_dir(when):
    """memory/chats/YYYY_MM/ for the given local datetime."""
    return chats_dir() / ("%04d_%02d" % (when.year, when.month))


def _day_basename(when, sep="_"):
    """Day filename with underscore or dash separators (no extension)."""
    return "%04d%s%02d%s%02d" % (when.year, sep, when.month, sep, when.day)


def _legacy_flat_candidates(when):
    """Old flat layouts under memory/chats/ (pre month-folder layout).

    Candidates (in preference order for migration source):
      memory/chats/YYYY-MM-DD.md
      memory/chats/YYYY_MM_DD.md
    """
    root = chats_dir()
    return [
        root / (_day_basename(when, sep="-") + ".md"),
        root / (_day_basename(when, sep="_") + ".md"),
    ]


def _maybe_migrate_flat_day(new_path, when):
    """If an old flat day file exists and new_path does not, move it into place.

    Best-effort; never raises. Returns True if a migrate/move happened.
    """
    if new_path.exists():
        return False
    for old in _legacy_flat_candidates(when):
        # Skip if somehow the "legacy" path IS the new path (shouldn't happen).
        try:
            if old.resolve() == new_path.resolve():
                continue
        except OSError:
            pass
        if not old.exists() or not old.is_file():
            continue
        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            old.replace(new_path)
            return True
        except OSError:
            # Fall through: prefer reading from old in place if move failed.
            return False
    return False


def chat_path_for_day(when=None):
    """Path to memory/chats/YYYY_MM/YYYY_MM_DD.md for the given (or current) day.

    Prefers the new month-folder layout. Best-effort migrates an old flat
    day file (YYYY-MM-DD.md or YYYY_MM_DD.md under chats/) into the month
    folder on first access.
    """
    when = when or datetime.now()
    new_path = _month_dir(when) / (_day_basename(when, sep="_") + ".md")
    _maybe_migrate_flat_day(new_path, when)
    return new_path


def resolve_chat_path(when=None):
    """Return the path to read/write for a day, preferring new layout.

    If the new path exists (or was just migrated), use it. Else if a legacy
    flat file still exists (move failed), return that so reads still work.
    Writes always target the new path via chat_path_for_day.
    """
    when = when or datetime.now()
    new_path = chat_path_for_day(when)
    if new_path.exists():
        return new_path
    for old in _legacy_flat_candidates(when):
        if old.exists() and old.is_file():
            return old
    return new_path


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

    Always writes under the new month-folder layout (migrating flat files first).
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
    p = path or resolve_chat_path(when)
    if not p.exists() or not p.is_file():
        return []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return []
    return parse_chat_md(text)


def history_for_api(when=None):
    """Dict for GET /api/chat/history: ok, turns, file (basename), path.

    Disk archive only — callers still use HISTORY_TURNS for model context.
    """
    p = resolve_chat_path(when)
    turns = load_turns(path=p)
    return {
        "ok": True,
        "turns": turns,
        "file": p.name,
        "path": str(p),
    }
