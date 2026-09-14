"""
Workspace tools: files, shell, memory, reminders, jobs, web_search.

The model calls these through brain.py → dispatch(). File and shell work is
jailed to WORKSPACE (whole tree). Shell runs freehand inside bubblewrap when bwrap
is on PATH (network ON by default; SHELL_NET=0 → --unshare-net); otherwise Confirm /
Telegram YES-NO. sudo always needs confirm. user/ is agent read-only.

Imports from: config.py (paths, BLOCKED, SYSTEM_BASE, keys). Lazily imports
              brain.py for _http_json (search) and _plain_chat (jobs).
Used by: brain.py (dispatch, TOOL_DECLS, schemas, build_system),
         server.py (upload/download/confirm/reminders),
         run.py (background_loop).
"""
import json
import re
import shutil
import subprocess
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from config import (
    BLOCKED,
    GEMINI_API_BASE,
    JOBS_FILE,
    JOBS_LOG,
    MEMORY_ASSISTANT,
    MEMORY_DATE_DIR,
    MEMORY_DIR,
    MEMORY_FILE,
    MEMORY_SESSION,
    MEMORY_TOPIC_DIR,
    MEMORY_USER,
    PENDING_SHELL,
    PROVIDERS,
    REMINDERS_FILE,
    ROOT,
    SYSTEM_BASE,
    USER_DIR,
    WORKSPACE,
    allow_sudo,
    allowed,
    app_version,
    ensure_memory_dirs,
    ensure_ws,
    memory_date_path,
    memory_topic_path,
    provider_key,
    session_should_reset,
    shell_net_env_off,
)


# ---------------------------------------------------------------------------
# Memory (workspace/memory/ — also injected into the system prompt)
# ---------------------------------------------------------------------------
# Layout:
#   memory/session.md     — short-lived (auto-cleared; see SESSION_RESET_*)
#   memory/user.md        — lasting user facts
#   memory/assistant.md   — extras for the AI (not a copy of SYSTEM_BASE)
#   memory/date/YYYY_MM.md — monthly logs: "- [YYYY-MM-DD] : text"
#   memory/topic/<name>.md — same line format
# Legacy: if workspace/memory.md exists and the new tree is empty, migrate once.

# Caps for prompt injection (chars). Full files still readable via memory_read.
_MEM_CAP_USER = 3000
_MEM_CAP_ASSISTANT = 3000
_MEM_CAP_DATE = 4000
_MEM_CAP_SESSION = 2000


def _read_capped(path, cap):
    """Read a UTF-8 file capped to cap chars, or empty string if missing."""
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")[:cap]


def _memory_tree_empty():
    """True if new memory tree has no non-empty content files yet."""
    if not MEMORY_DIR.exists():
        return True
    for p in (
        MEMORY_SESSION,
        MEMORY_USER,
        MEMORY_ASSISTANT,
    ):
        if p.exists() and p.stat().st_size > 0:
            return False
    if MEMORY_DATE_DIR.exists():
        for p in MEMORY_DATE_DIR.glob("*.md"):
            if p.is_file() and p.stat().st_size > 0:
                return False
    if MEMORY_TOPIC_DIR.exists():
        for p in MEMORY_TOPIC_DIR.glob("*.md"):
            if p.is_file() and p.stat().st_size > 0:
                return False
    return True


def migrate_legacy_memory():
    """One-shot: copy old memory.md into date/YYYY_MM.md if new tree is empty."""
    ensure_memory_dirs()
    if not MEMORY_FILE.exists():
        return False
    if not _memory_tree_empty():
        return False
    old = MEMORY_FILE.read_text(encoding="utf-8").strip()
    if not old:
        return False
    dest = memory_date_path()
    stamp = datetime.now().strftime("%Y-%m-%d")
    note = (
        "- [%s] : [migrated from memory.md]\n" % stamp
        + old
        + ("\n" if not old.endswith("\n") else "")
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(note, encoding="utf-8")
    return True


def maybe_reset_session():
    """Clear session.md when SESSION_RESET_HOURS / SESSION_RESET_AFTER say so."""
    ensure_memory_dirs()
    if not MEMORY_SESSION.exists():
        return False
    if MEMORY_SESSION.stat().st_size == 0:
        return False
    mtime = MEMORY_SESSION.stat().st_mtime
    if session_should_reset(mtime):
        MEMORY_SESSION.write_text("", encoding="utf-8")
        return True
    return False


def _dated_line(text):
    """Format one memory log line: '- [YYYY-MM-DD] : text'."""
    stamp = datetime.now().strftime("%Y-%m-%d")
    body = (text or "").strip().replace("\n", " ")
    return "- [%s] : %s\n" % (stamp, body)


def _append_to_file(path, chunk):
    """Append chunk to path (create parents). Returns path string."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cur = path.read_text(encoding="utf-8") if path.exists() else ""
    sep = "" if (not cur or cur.endswith("\n")) else "\n"
    path.write_text(cur + sep + chunk, encoding="utf-8")
    return str(path)


def memory_resolve_dest(dest):
    """Map dest string → Path. dest: session|user|assistant|date|topic:<name>."""
    ensure_memory_dirs()
    d = (dest or "date").strip().lower()
    if d == "session":
        return MEMORY_SESSION, False  # plain append, not dated line
    if d == "user":
        return MEMORY_USER, False
    if d == "assistant":
        return MEMORY_ASSISTANT, False
    if d == "date" or d == "":
        return memory_date_path(), True
    if d.startswith("topic:"):
        name = d.split(":", 1)[1].strip()
        return memory_topic_path(name), True
    raise ValueError(
        "dest must be session|user|assistant|date|topic:<name> (got %r)" % dest
    )


def memory_append(note, dest="date"):
    """Append a note. dest: session|user|assistant|date|topic:<name> (default date)."""
    ensure_ws()
    migrate_legacy_memory()
    maybe_reset_session()
    add = (note or "").strip()
    if not add:
        return {"ok": False, "error": "Empty note"}
    try:
        path, dated = memory_resolve_dest(dest)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    chunk = _dated_line(add) if dated else (add + "\n")
    out = _append_to_file(path, chunk)
    return {"ok": True, "path": out, "dest": (dest or "date").strip() or "date"}


def memory_read(target=None):
    """Read memory file(s). target: session|user|assistant|date|topic:<name>|all."""
    ensure_ws()
    migrate_legacy_memory()
    maybe_reset_session()
    t = (target or "all").strip().lower()
    if t in ("", "all"):
        # Combined dump (capped) for the model when no specific target.
        parts = []
        for label, path, cap in (
            ("user", MEMORY_USER, 8000),
            ("assistant", MEMORY_ASSISTANT, 8000),
            ("date", memory_date_path(), 8000),
            ("session", MEMORY_SESSION, 4000),
        ):
            body = _read_capped(path, cap).strip()
            if body:
                parts.append("### %s (%s)\n%s" % (label, path.name, body))
        # List topic files briefly
        topics = []
        if MEMORY_TOPIC_DIR.exists():
            for p in sorted(MEMORY_TOPIC_DIR.glob("*.md")):
                if p.is_file() and p.stat().st_size > 0:
                    topics.append(p.stem)
        text = "\n\n".join(parts) if parts else ""
        return {
            "ok": True,
            "target": "all",
            "memory": text[:20000],
            "topics": topics,
        }
    try:
        if t.startswith("topic:"):
            path, _ = memory_resolve_dest(t)
        elif t in ("session", "user", "assistant", "date"):
            path, _ = memory_resolve_dest(t)
        else:
            return {
                "ok": False,
                "error": "target must be session|user|assistant|date|topic:<name>|all",
            }
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    body = ""
    if path.exists():
        body = path.read_text(encoding="utf-8")[:20000]
    return {"ok": True, "target": t, "path": str(path), "memory": body}


def memory_load():
    """Legacy helper: combined memory text for callers expecting a string."""
    res = memory_read("all")
    return res.get("memory") or ""


def build_system():
    """System prompt = SYSTEM_BASE plus capped user/assistant/date/session notes."""
    ensure_ws()
    migrate_legacy_memory()
    maybe_reset_session()
    chunks = []
    user = _read_capped(MEMORY_USER, _MEM_CAP_USER).strip()
    if user:
        chunks.append("## User facts (memory/user.md)\n" + user)
    asst = _read_capped(MEMORY_ASSISTANT, _MEM_CAP_ASSISTANT).strip()
    if asst:
        chunks.append("## Assistant extras (memory/assistant.md)\n" + asst)
    month = _read_capped(memory_date_path(), _MEM_CAP_DATE).strip()
    if month:
        chunks.append(
            "## This month (memory/date/%s)\n" % memory_date_path().name + month
        )
    sess = _read_capped(MEMORY_SESSION, _MEM_CAP_SESSION).strip()
    if sess:
        chunks.append("## Session (memory/session.md)\n" + sess)
    if not chunks:
        return SYSTEM_BASE
    return SYSTEM_BASE + "\n\n" + "\n\n".join(chunks)


# ---------------------------------------------------------------------------
# File tools (jailed to WORKSPACE)
# ---------------------------------------------------------------------------


def safe_path(user_path: str) -> Path:
    """Resolve a path and reject anything that escapes the workspace."""
    raw = Path(user_path).expanduser()
    cand = (WORKSPACE / raw).resolve() if not raw.is_absolute() else raw.resolve()
    try:
        cand.relative_to(WORKSPACE.resolve())
    except ValueError as e:
        raise PermissionError("Path outside workspace") from e
    return cand


def path_under_user(path: Path) -> bool:
    """True if path is inside WORKSPACE/user/ (agent read-only zone)."""
    try:
        path.resolve().relative_to(USER_DIR.resolve())
        return True
    except (ValueError, OSError):
        return False


def _reject_user_write(path: Path):
    """Return an error dict if path is under user/; else None."""
    if path_under_user(path):
        return {
            "ok": False,
            "error": "user/ is read-only for the agent (list/read only)",
            "path": str(path),
        }
    return None


def tool_list_dir(path: str = ".") -> dict:
    """List files and folders under a workspace path (user/ allowed)."""
    ensure_ws()
    t = safe_path(path)
    if not t.is_dir():
        return {"ok": False, "error": "Not a directory: %s" % t}
    entries = [{"name": c.name, "type": "dir" if c.is_dir() else "file"} for c in sorted(t.iterdir())]
    return {"ok": True, "path": str(t), "entries": entries}


def tool_read_file(path: str) -> dict:
    """Read a text file in the workspace (user/ allowed; first 200 KB)."""
    ensure_ws()
    t = safe_path(path)
    if not t.is_file():
        return {"ok": False, "error": "Not a file: %s" % t}
    data = t.read_bytes()[:200_000]
    return {"ok": True, "path": str(t), "content": data.decode("utf-8", errors="replace")}


def tool_write_file(path: str, content: str) -> dict:
    """Write a UTF-8 text file in the workspace (blocked under user/)."""
    ensure_ws()
    t = safe_path(path)
    err = _reject_user_write(t)
    if err:
        return err
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(t), "name": t.name}


def tool_write_bytes(path: str, data: bytes) -> dict:
    """Write raw bytes (upload API; blocked under user/)."""
    ensure_ws()
    t = safe_path(path)
    err = _reject_user_write(t)
    if err:
        return err
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_bytes(data)
    return {"ok": True, "path": str(t), "name": t.name, "bytes": len(data)}



# ---------------------------------------------------------------------------
# Shell sandbox (bubblewrap freehand when available; else UI/Telegram confirm)
# ---------------------------------------------------------------------------
# When `bwrap` is on PATH, shell commands run immediately inside bubblewrap:
#   - WORKSPACE bind RW, cwd there; user/ rebound RO
#   - Host tools RO (/usr + /bin /sbin /lib /lib64 if present — usrmerge-safe)
#   - Minimal RO: resolv.conf, ssl/ca-certificates, passwd/group; --dev / --proc
#   - Network ON by default (no --unshare-net); SHELL_NET=0 adds --unshare-net
#   - --unshare-pid --die-with-parent
#   - BLOCKED regex always; sudo always needs Confirm (even with bwrap)
# Without bwrap: PENDING_SHELL → Confirm / Telegram YES-NO (no net isolation).


_BWRAP_BIN = None  # None = not probed yet; "" = missing; else absolute path
_BWRAP_BIND_TRY = None  # None = not probed; True/False = --ro-bind-try support

# Tokens that suggest a shell command may write/delete (used with user/ path check).
_WRITE_SHELL_RE = re.compile(
    r"(?ix)(?:^|[\s;&|])(?:rm|rmdir|unlink|shred|truncate|mv|cp|install|tee|touch|"
    r"mkdir|chmod|chown|ln|dd|sed\s+-i|gzip|gunzip|bzip2|"
    r"xz|zip|tar\s+[^\n]*[crux])\b|(?:>>?|2>>?)"
)


def bwrap_available():
    """True if bubblewrap (`bwrap`) is on PATH. Detected once per process."""
    global _BWRAP_BIN
    if _BWRAP_BIN is None:
        _BWRAP_BIN = shutil.which("bwrap") or ""
    return bool(_BWRAP_BIN)


def shell_sandbox_mode():
    """Return 'bwrap' when sandboxed freehand is active, else 'none'."""
    return "bwrap" if bwrap_available() else "none"


def shell_freehand():
    """True when non-sudo run_shell executes immediately (no Confirm / YES-NO)."""
    return bwrap_available()


def shell_net_enabled():
    """True if shell processes have network access.

    Default True. With bwrap, SHELL_NET=0/false/no/off adds --unshare-net.
    Without bwrap there is no isolation (always True).
    """
    if not bwrap_available():
        return True
    return not shell_net_env_off()


def _bwrap_has_bind_try():
    """Whether this bwrap supports --ro-bind-try (recent bubblewrap)."""
    global _BWRAP_BIND_TRY
    if _BWRAP_BIND_TRY is None:
        if not bwrap_available():
            _BWRAP_BIND_TRY = False
        else:
            try:
                p = subprocess.run(
                    [_BWRAP_BIN, "--help"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                help_text = (p.stdout or "") + (p.stderr or "")
                _BWRAP_BIND_TRY = "--ro-bind-try" in help_text
            except (OSError, subprocess.TimeoutExpired):
                _BWRAP_BIND_TRY = False
    return _BWRAP_BIND_TRY


def _ro_bind(argv, src, dest=None):
    """Append a read-only bind; use --ro-bind-try when available, else exist-check."""
    dest = dest or src
    if _bwrap_has_bind_try():
        argv.extend(["--ro-bind-try", src, dest])
    elif Path(src).exists():
        argv.extend(["--ro-bind", src, dest])


def _build_bwrap_argv(cmd):
    """Build argv: bwrap … -- /bin/bash -lc <cmd> (cwd = WORKSPACE).

    Skips --new-session so subprocess can still capture stdout/stderr cleanly.
    Network stays shared unless SHELL_NET=0 (then --unshare-net).
    user/ is rebound read-only after the RW workspace bind.
    """
    ws = str(WORKSPACE.resolve())
    user = str(USER_DIR.resolve())
    argv = [
        _BWRAP_BIN or "bwrap",
        "--die-with-parent",
        "--unshare-pid",
    ]
    # Default: keep host network. Opt out with SHELL_NET=0.
    if shell_net_env_off():
        argv.append("--unshare-net")
    argv.extend(
        [
            "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "--ro-bind", "/usr", "/usr",
        ]
    )
    # Debian usrmerge: /bin may be a symlink into /usr; bind only if present.
    for p in ("/bin", "/sbin", "/lib", "/lib64"):
        if Path(p).exists():
            argv.extend(["--ro-bind", p, p])

    # DNS + TLS roots + passwd/group (some tools look these up).
    if Path("/etc/resolv.conf").exists():
        argv.extend(["--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf"])
    _ro_bind(argv, "/etc/ssl")
    _ro_bind(argv, "/etc/ca-certificates")
    _ro_bind(argv, "/etc/passwd")
    _ro_bind(argv, "/etc/group")

    argv.extend(
        [
            "--bind", ws, ws,
            # After RW bind of the whole jail, lock user/ to read-only.
            "--ro-bind", user, user,
            "--chdir", ws,
            "--dev", "/dev",
            "--proc", "/proc",
            "--",
            "/bin/bash", "-lc", cmd,
        ]
    )
    return argv


def command_is_sudo(cmd):
    """True if the command invokes sudo as the first token (after optional env)."""
    s = (cmd or "").strip()
    if not s:
        return False
    # Strip simple leading VAR=value assignments: FOO=1 sudo …
    while True:
        m = re.match(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", s)
        if not m:
            break
        s = s[m.end() :]
    first = s.split(None, 1)[0] if s else ""
    return first == "sudo" or first.endswith("/sudo")


def _sudo_inject_flags(cmd, flags):
    """Insert flags after the sudo token: 'sudo -S …' / 'sudo -n …'."""
    return re.sub(r"(^|[\s;|&])sudo\b", r"\1sudo " + flags, (cmd or "").strip(), count=1)


def _shell_mentions_user_path(cmd):
    """True if cmd appears to reference a path under WORKSPACE/user/."""
    s = cmd or ""
    user_res = str(USER_DIR.resolve())
    if user_res in s or str(USER_DIR) in s:
        return True
    # Relative user/… tokens (avoid matching only memory/user.md)
    if re.search(r"(?x)(?:^|[\s\"'=])(?:\./)?user/", s):
        return True
    return False


def shell_would_write_user(cmd):
    """Heuristic: True if cmd looks like it would write/delete under user/."""
    if not _shell_mentions_user_path(cmd):
        return False
    if _WRITE_SHELL_RE.search(cmd or ""):
        return True
    if re.search(r"(?x)>>?\s*[\"']?(?:\./)?user/", cmd or ""):
        return True
    return False


def _shell_execute(cmd, password=None):
    """Run a command in the workspace with a 30s timeout. Internal only.

    Non-sudo: bwrap when available, else shell=True.
    Sudo: always host shell (not bwrap); password fed via sudo -S on stdin
    when provided (never logged). No password → try sudo -n.
    """
    is_sudo = command_is_sudo(cmd)
    try:
        if is_sudo:
            # Never run sudo inside bwrap (needs real privileges + stdin).
            if password is not None:
                run_cmd = _sudo_inject_flags(cmd, "-S")
                p = subprocess.run(
                    run_cmd,
                    shell=True,
                    cwd=str(WORKSPACE),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    input=(password + "\n"),
                )
            else:
                run_cmd = _sudo_inject_flags(cmd, "-n")
                p = subprocess.run(
                    run_cmd,
                    shell=True,
                    cwd=str(WORKSPACE),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
        elif bwrap_available():
            p = subprocess.run(
                _build_bwrap_argv(cmd),
                capture_output=True,
                text=True,
                timeout=30,
            )
        else:
            p = subprocess.run(
                cmd,
                shell=True,
                cwd=str(WORKSPACE),
                capture_output=True,
                text=True,
                timeout=30,
            )
        out = {
            "ok": p.returncode == 0,
            "exit_code": p.returncode,
            "stdout": p.stdout[-40000:],
            "stderr": p.stderr[-10000:],
            "command": cmd,
        }
        if is_sudo:
            out["sudo"] = True
        elif bwrap_available():
            out["sandbox"] = "bwrap"
        return out
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Timed out", "command": cmd}


def tool_run_shell(command, confirmed=False, password=None):
    """Run shell freehand when sandboxed; sudo always confirms; else queue.

    password: optional sudo password from UI/Telegram confirm only — never logged
    or written to memory files. Discarded after use.
    """
    ensure_ws()
    # Ensure user/ exists so bwrap --ro-bind succeeds.
    USER_DIR.mkdir(parents=True, exist_ok=True)
    cmd = (command or "").strip()
    if not cmd:
        return {"ok": False, "error": "Empty command"}
    if BLOCKED.search(cmd):
        return {"ok": False, "error": "Command blocked for safety"}
    is_sudo = command_is_sudo(cmd)
    if is_sudo and not allow_sudo():
        return {"ok": False, "error": "Command blocked for safety"}
    if shell_would_write_user(cmd):
        return {
            "ok": False,
            "error": "user/ is read-only for the agent (shell write/delete blocked)",
        }
    # sudo always needs Confirm (even when bwrap freehand is on).
    if is_sudo:
        if not confirmed:
            PENDING_SHELL.write_text(
                json.dumps({"command": cmd, "sudo": True}), encoding="utf-8"
            )
            return {
                "ok": False,
                "needs_confirm": True,
                "needs_password": True,
                "sudo": True,
                "command": cmd,
                "error": "Waiting for user confirm (sudo password) in the UI",
            }
        try:
            if PENDING_SHELL.exists():
                PENDING_SHELL.unlink()
            return _shell_execute(cmd, password=password)
        finally:
            password = None
    # Freehand path: bwrap on PATH → execute now (no PENDING_SHELL).
    if shell_freehand():
        if PENDING_SHELL.exists():
            PENDING_SHELL.unlink()
        return _shell_execute(cmd)
    if not confirmed:
        PENDING_SHELL.write_text(
            json.dumps({"command": cmd, "sudo": False}), encoding="utf-8"
        )
        return {
            "ok": False,
            "needs_confirm": True,
            "sudo": False,
            "command": cmd,
            "error": "Waiting for user confirm in the UI",
        }
    if PENDING_SHELL.exists():
        PENDING_SHELL.unlink()
    return _shell_execute(cmd)


def confirm_pending_shell(password=None):
    """UI/Telegram Confirm: run the queued command (clear queue; discard password)."""
    ensure_ws()
    if not PENDING_SHELL.exists():
        return {"ok": False, "error": "Nothing to confirm"}
    try:
        data = json.loads(PENDING_SHELL.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        PENDING_SHELL.unlink()
        return {"ok": False, "error": "Corrupt pending shell"}
    cmd = data.get("command") or ""
    is_sudo = bool(data.get("sudo")) or command_is_sudo(cmd)
    try:
        return tool_run_shell(
            cmd, confirmed=True, password=password if is_sudo else None
        )
    finally:
        password = None


def cancel_pending_shell():
    """UI Cancel: drop the queued command without running it."""
    if PENDING_SHELL.exists():
        PENDING_SHELL.unlink()
    return {"ok": True, "cancelled": True}


def apply_update():
    """git pull --ff-only in ROOT, then schedule user-service restart.

    No apt. Returns {ok, message, version}. Restart is fire-and-forget so the
    HTTP response can flush before the process is replaced.
    """
    try:
        p = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {
            "ok": False,
            "message": "git pull failed: %s" % e,
            "version": app_version(),
        }
    if p.returncode != 0:
        err = ((p.stderr or "") + "\n" + (p.stdout or "")).strip() or "git pull failed"
        return {"ok": False, "message": err[:2000], "version": app_version()}
    pull_msg = ((p.stdout or "") + (p.stderr or "")).strip() or "Already up to date."
    ver = app_version()
    # Schedule restart of the user systemd unit (no sudo for --user).
    try:
        subprocess.Popen(
            [
                "bash",
                "-lc",
                "sleep 1; systemctl --user restart linux-ai-agent",
            ],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        msg = "Updated. Restarting service…\n%s" % pull_msg
    except OSError as e:
        msg = "Pulled OK but could not schedule restart: %s\n%s" % (e, pull_msg)
    return {"ok": True, "message": msg[:2000], "version": ver}



# ---------------------------------------------------------------------------
# Small JSON / time helpers
# ---------------------------------------------------------------------------


def _load_json_list(path: Path):
    """Read a JSON array from disk, or [] if missing/corrupt."""
    ensure_ws()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _save_json_list(path: Path, items):
    """Write a JSON array (pretty-printed)."""
    ensure_ws()
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _now_iso():
    """UTC timestamp as ISO-8601 without microseconds."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_due(due_iso=None, in_minutes=None):
    """Turn in_minutes or due_iso into a UTC ISO string, or (None, error)."""
    if in_minutes is not None:
        try:
            mins = float(in_minutes)
        except (TypeError, ValueError):
            return None, "in_minutes must be a number"
        due = datetime.now(timezone.utc).timestamp() + max(0, mins) * 60
        return datetime.fromtimestamp(due, tz=timezone.utc).replace(microsecond=0).isoformat(), None
    if due_iso:
        s = str(due_iso).strip()
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat(), None
        except ValueError:
            return None, "Invalid due_iso"
    return None, "Need due_iso or in_minutes"


# ---------------------------------------------------------------------------
# Reminders (reminders.json + optional notify-send)
# ---------------------------------------------------------------------------


def tool_reminder_add(text, due_iso=None, in_minutes=None):
    """Add a reminder. Use in_minutes (number) or due_iso (ISO datetime)."""
    note = (text or "").strip()
    if not note:
        return {"ok": False, "error": "Empty text"}
    due, err = _parse_due(due_iso, in_minutes)
    if err:
        return {"ok": False, "error": err}
    items = _load_json_list(REMINDERS_FILE)
    rid = "r%d" % (int(time.time() * 1000) % 10_000_000_000)
    item = {"id": rid, "text": note, "due": due, "notified": False, "created": _now_iso()}
    items.append(item)
    _save_json_list(REMINDERS_FILE, items)
    return {"ok": True, "reminder": item}


def tool_reminder_list():
    """Split reminders into due vs upcoming (and return the full list)."""
    items = _load_json_list(REMINDERS_FILE)
    now = datetime.now(timezone.utc)
    due = []
    upcoming = []
    for it in items:
        try:
            d = datetime.fromisoformat(it.get("due") or "")
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
        except ValueError:
            upcoming.append(it)
            continue
        if d <= now:
            due.append(it)
        else:
            upcoming.append(it)
    return {"ok": True, "due": due, "upcoming": upcoming, "all": items}


def _notify_send(title, body):
    """Desktop notification if notify-send is installed; ignore failures."""
    try:
        subprocess.run(
            ["notify-send", str(title)[:80], str(body)[:200]],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def process_due_reminders():
    """Mark newly due reminders and fire notify-send once each."""
    items = _load_json_list(REMINDERS_FILE)
    if not items:
        return
    now = datetime.now(timezone.utc)
    changed = False
    for it in items:
        if it.get("notified"):
            continue
        try:
            d = datetime.fromisoformat(it.get("due") or "")
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if d <= now:
            _notify_send("AI Agent reminder", it.get("text") or "")
            it["notified"] = True
            it["notified_at"] = _now_iso()
            changed = True
    if changed:
        _save_json_list(REMINDERS_FILE, items)


# ---------------------------------------------------------------------------
# Scheduled jobs (jobs.json → jobs_log.md)
# ---------------------------------------------------------------------------


def tool_job_add(every_minutes, prompt):
    """Schedule a recurring prompt (every_minutes >= 1)."""
    try:
        mins = float(every_minutes)
    except (TypeError, ValueError):
        return {"ok": False, "error": "every_minutes must be a number"}
    if mins < 1:
        return {"ok": False, "error": "every_minutes must be >= 1"}
    p = (prompt or "").strip()
    if not p:
        return {"ok": False, "error": "Empty prompt"}
    items = _load_json_list(JOBS_FILE)
    jid = "j%d" % (int(time.time() * 1000) % 10_000_000_000)
    item = {
        "id": jid,
        "every_minutes": mins,
        "prompt": p,
        "last_run": None,
        "created": _now_iso(),
    }
    items.append(item)
    _save_json_list(JOBS_FILE, items)
    return {"ok": True, "job": item}


def tool_job_list():
    """Return the current jobs.json list."""
    return {"ok": True, "jobs": _load_json_list(JOBS_FILE)}


def process_due_jobs():
    """Run any job whose interval has elapsed; append the reply to jobs_log.md."""
    items = _load_json_list(JOBS_FILE)
    if not items:
        return
    now = time.time()
    changed = False
    for it in items:
        mins = float(it.get("every_minutes") or 0)
        if mins < 1:
            continue
        last = it.get("last_run")
        last_ts = 0.0
        if last:
            try:
                dt = datetime.fromisoformat(last)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                last_ts = dt.timestamp()
            except ValueError:
                last_ts = 0.0
        if last_ts and (now - last_ts) < mins * 60:
            continue
        prompt = it.get("prompt") or ""
        from brain import _plain_chat
        result = _plain_chat(
            "Scheduled job (%s). Respond briefly.\n\n%s" % (it.get("id"), prompt)
        )
        ensure_ws()
        stamp = _now_iso()
        line = "\n## Job %s @ %s\n**Prompt:** %s\n\n%s\n" % (
            it.get("id"),
            stamp,
            prompt,
            result.get("reply") or result.get("error") or "",
        )
        with JOBS_LOG.open("a", encoding="utf-8") as f:
            f.write(line)
        it["last_run"] = stamp
        changed = True
    if changed:
        _save_json_list(JOBS_FILE, items)


# ---------------------------------------------------------------------------
# Background loop (started from run.py)
# ---------------------------------------------------------------------------


def background_loop():
    """Every 30s: fire due reminders and due jobs. Errors are printed, not fatal."""
    while True:
        try:
            process_due_reminders()
            process_due_jobs()
        except Exception as e:  # noqa: BLE001
            print("[bg] error: %s" % e)
        time.sleep(30)


# ---------------------------------------------------------------------------
# Web search (Gemini Google Search tool — needs GEMINI_API_KEY)
# ---------------------------------------------------------------------------


def tool_web_search(query):
    """Ask Gemini to summarize live search results for the query."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "Empty query"}
    key = provider_key("gemini")
    if not key:
        return {
            "ok": False,
            "error": "web_search needs GEMINI_API_KEY (uses Gemini Google Search). Set it in .env or skip search.",
            "query": q,
        }
    model = allowed("gemini", PROVIDERS["gemini"]["default"])
    url = "%s/models/%s:generateContent?key=%s" % (GEMINI_API_BASE, model, key)

    tool_shapes = [{"google_search": {}}, {"googleSearch": {}}]
    last_err = ""
    from brain import _http_json
    for tools_obj in tool_shapes:
        body = {
            "contents": [{"role": "user", "parts": [{"text": "Summarize search results for: %s" % q}]}],
            "tools": [tools_obj],
        }
        try:
            data = _http_json(url, body, {"Content-Type": "application/json"}, timeout=60)
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")[:600]
            last_err = "HTTP %s: %s" % (e.code, err)
            continue
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e), "query": q}

        parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p]
        summary = "\n".join(texts).strip() or "(No search summary)"
        gm = ((data.get("candidates") or [{}])[0].get("groundingMetadata")) or {}
        return {
            "ok": True,
            "query": q,
            "summary": summary[:12000],
            "tool_shape": list(tools_obj.keys())[0],
            "grounding_chunks": len((gm.get("groundingChunks") or [])),
        }
    return {"ok": False, "error": last_err or "google_search failed", "query": q}


# ---------------------------------------------------------------------------
# Tool schemas the models see (Gemini native + OpenAI/Anthropic wrappers)
# ---------------------------------------------------------------------------

# Gemini functionDeclarations. openai_tools / anthropic_tools wrap this list.
TOOL_DECLS = [
    {
        "name": "list_dir",
        "description": "List files in the workspace",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
    },
    {
        "name": "read_file",
        "description": "Read a text file in the workspace",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write a text file in the workspace",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_shell",
        "description": "Run a shell command (cwd=workspace). Sandboxed freehand when bubblewrap is available; sudo always needs Confirm; otherwise Confirm in UI / YES-NO on Telegram. Prefer workspace/ for new work; user/ is read-only.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "memory_read",
        "description": "Read memory. target: session|user|assistant|date|topic:<name>|all (default all)",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "session|user|assistant|date|topic:<name>|all",
                }
            },
        },
    },
    {
        "name": "memory_append",
        "description": "Append a note. dest: session|user|assistant|date|topic:<name> (default date = this month)",
        "parameters": {
            "type": "object",
            "properties": {
                "note": {"type": "string"},
                "dest": {
                    "type": "string",
                    "description": "session|user|assistant|date|topic:<name>",
                },
            },
            "required": ["note"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web via Gemini Google Search; returns a text summary",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "reminder_add",
        "description": "Add a PC reminder. Use in_minutes (number) or due_iso (ISO datetime).",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "in_minutes": {"type": "number"},
                "due_iso": {"type": "string"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "reminder_list",
        "description": "List reminders (due and upcoming)",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "job_add",
        "description": "Schedule a recurring job: every_minutes + prompt; result appended to jobs_log.md",
        "parameters": {
            "type": "object",
            "properties": {
                "every_minutes": {"type": "number"},
                "prompt": {"type": "string"},
            },
            "required": ["every_minutes", "prompt"],
        },
    },
    {
        "name": "job_list",
        "description": "List scheduled jobs",
        "parameters": {"type": "object", "properties": {}},
    },
]


def openai_tools():
    """TOOL_DECLS in OpenAI Chat Completions tools[] shape."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t.get("parameters") or {"type": "object", "properties": {}},
            },
        }
        for t in TOOL_DECLS
    ]


def anthropic_tools():
    """TOOL_DECLS in Anthropic Messages tools[] shape (input_schema)."""
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t.get("parameters") or {"type": "object", "properties": {}},
        }
        for t in TOOL_DECLS
    ]


# ---------------------------------------------------------------------------
# Dispatch: model tool name → Python function
# ---------------------------------------------------------------------------


def dispatch(name, args):
    """Run one tool by name. Always returns a dict (ok/error), never raises."""
    try:
        if name == "list_dir":
            return tool_list_dir(args.get("path") or ".")
        if name == "read_file":
            return tool_read_file(args["path"])
        if name == "write_file":
            return tool_write_file(args["path"], args.get("content", ""))
        if name == "run_shell":
            return tool_run_shell(args["command"])
        if name == "memory_read":
            return memory_read(args.get("target"))
        if name == "memory_append":
            return memory_append(args.get("note") or "", dest=args.get("dest") or "date")
        if name == "web_search":
            return tool_web_search(args.get("query") or "")
        if name == "reminder_add":
            return tool_reminder_add(
                args.get("text") or "",
                due_iso=args.get("due_iso"),
                in_minutes=args.get("in_minutes"),
            )
        if name == "reminder_list":
            return tool_reminder_list()
        if name == "job_add":
            return tool_job_add(args.get("every_minutes"), args.get("prompt") or "")
        if name == "job_list":
            return tool_job_list()
        return {"ok": False, "error": "Unknown tool %s" % name}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
