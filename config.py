"""
Config, env, paths, and constants (stdlib only).

Single place for workspace location, listen address, system prompt,
.env helpers, and optional UI_LIGHT_* theme overrides. Provider catalogs live in providers.py; this module
re-exports the names brain/server/tools already import so nothing breaks.

Imports from: stdlib (os, re, pathlib, datetime); providers.py (catalog).
Used by: tools.py, brain.py, server.py, run.py, telegram.py, providers.py
         (lazy load_env only).
"""
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root and version
# ---------------------------------------------------------------------------

# Folder that contains this file (the app install directory).
ROOT = Path(__file__).resolve().parent


def app_version():
    """Read VERSION (e.g. "0.1.26 (26)") for UI /api/health.

    Format: semver + change counter in brackets; counter +1 every release.
    """
    vp = ROOT / "VERSION"
    try:
        return vp.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"



# User secrets and overrides (API keys, HOST, PORT, WORKSPACE, PROVIDER,
# ALLOW_SUDO, SHELL_NET).
ENV_PATH = ROOT / ".env"


# ---------------------------------------------------------------------------
# Load .env (simple KEY=value — no pip/dotenv library)
# ---------------------------------------------------------------------------


def _read_dotenv():
    """Parse .env into a dict. Missing file → empty dict. Reloaded each call."""
    env = {}
    if not ENV_PATH.exists():
        return env
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _workspace_path():
    """Workspace folder: WORKSPACE from .env, else ~/ai-workspace."""
    raw = (_read_dotenv().get("WORKSPACE") or "").strip()
    if raw:
        raw = os.path.expandvars(raw)  # supports $USER, $HOME
        return Path(raw).expanduser()
    return Path.home() / "ai-workspace"


def _host_port():
    """Listen address and port from .env (defaults: 127.0.0.1:9191).

    Set HOST=0.0.0.0 in .env for LAN access (other devices use http://PC-LAN-IP:9191).
    Default stays localhost-only for safety.
    """
    env = _read_dotenv()
    host = (env.get("HOST") or os.environ.get("HOST") or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int((env.get("PORT") or os.environ.get("PORT") or "9191").strip() or "9191")
    except ValueError:
        port = 9191
    return host, port


# ---------------------------------------------------------------------------
# Workspace files (created on demand when tools write them)
# ---------------------------------------------------------------------------

# Jail for file/shell tools = whole tree (default ~/ai-workspace).
# Subdirs created by ensure_ws: memory/, workspace/, test/, trash/, user/.
# Prefer workspace/ for new agent work; user/ is agent read-only.
WORKSPACE = _workspace_path()
# Agent must not write/delete under this folder (list/read OK).
USER_DIR = WORKSPACE / "user"
# Legacy single-file memory (migrated once into memory/date/YYYY_MM.md).
MEMORY_FILE = WORKSPACE / "memory.md"
# Split memory tree under workspace/memory/ (unchanged layout).
MEMORY_DIR = WORKSPACE / "memory"
MEMORY_SESSION = MEMORY_DIR / "session.md"
MEMORY_USER = MEMORY_DIR / "user.md"
MEMORY_ASSISTANT = MEMORY_DIR / "assistant.md"
MEMORY_DATE_DIR = MEMORY_DIR / "date"
MEMORY_TOPIC_DIR = MEMORY_DIR / "topic"
# JSON blob for a shell command waiting for the UI Confirm button.
# Shape: {"command": "...", "sudo": true|false}
PENDING_SHELL = WORKSPACE / ".pending_shell.json"
# Reminder list (id, text, due, notified).
REMINDERS_FILE = WORKSPACE / "reminders.json"
# Recurring jobs (every_minutes + prompt).
JOBS_FILE = WORKSPACE / "jobs.json"
# Append-only log of job results.
JOBS_LOG = WORKSPACE / "jobs_log.md"
# Bind address printed at startup and returned by /api/health.
HOST, PORT = _host_port()


def memory_date_path(when=None):
    """Path to memory/date/YYYY_MM.md for the given (or current) local month."""
    when = when or datetime.now()
    return MEMORY_DATE_DIR / ("%04d_%02d.md" % (when.year, when.month))


def memory_topic_path(name):
    """Safe path under memory/topic/<name>.md (alphanumeric, dash, underscore)."""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "").strip()).strip("_")
    if not safe:
        raise ValueError("Empty or invalid topic name")
    return MEMORY_TOPIC_DIR / (safe + ".md")


# ---------------------------------------------------------------------------
# Provider catalog — owned by providers.py; re-export for existing imports
# ---------------------------------------------------------------------------

# catalogs, defaults, key/status helpers, blink period, local base URLs
from providers import (  # noqa: E402
    DEFAULT_PROVIDER,
    DEFAULT_LLAMACPP_BASE_URL,
    DEFAULT_OLLAMA_BASE_URL,
    GEMINI_API_BASE,
    PROVIDERS,
    allowed,
    catalog_for_api,
    default_mode,
    default_model,
    default_provider,
    get_provider_meta,
    keys_status,
    list_modes,
    list_models,
    list_providers,
    llamacpp_base_url,
    ollama_base_url,
    provider_key,
    provider_openai_base,
    provider_ready,
    readiness_status,
    status_blink_ms,
)


# ---------------------------------------------------------------------------
# Status LED / local runtime env (also documented in .env.example)
# ---------------------------------------------------------------------------


def status_blink_ms_config():
    """Alias kept for clarity — STATUS_BLINK_MS from .env (default 2000)."""
    return status_blink_ms()


# ---------------------------------------------------------------------------
# Safety and the model's system prompt
# ---------------------------------------------------------------------------

# Commands we refuse even if the user clicks Confirm (destructive / privilege).
# Case-insensitive. Keep patterns tight to avoid blocking normal workspace cmds.
BLOCKED = re.compile(
    r"(?ix)"
    r"("
    r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/(?:\s|$|\*)"  # rm -rf / or /*
    r"|rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+~"  # rm -rf ~
    r"|rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+\$\{?HOME\}?"  # rm -rf $HOME
    r"|chmod\s+-R\b[^\n]*\s+/(?:\s|$)"  # chmod -R … /
    r"|chown\s+-R\b[^\n]*\s+/(?:\s|$)"  # chown -R … /
    r"|\bmkfs\b"
    r"|\bdd\b[^\n]*\bof=/dev/"
    r"|\b(shutdown|reboot|poweroff)\b"
    r"|crontab\s+-r\b"
    r"|\b(useradd|userdel|passwd)\b"
    r"|\bwipefs\b"
    r"|\blosetup\b"
    r"|\bsystemctl\s+(start|stop|restart|reload|enable|disable|mask|unmask)\b"
    r"|(?:curl|wget)\b[^\n]*\|\s*(?:ba)?sh\b"  # curl|sh / wget|sh
    r"|bash\s+<\(\s*curl\b"  # bash <(curl …
    r")"
)


# Short system prompt. tools.build_system injects memory/ files (user, assistant,
# current month date log, session). Memory layout: memory/session.md, user.md,
# assistant.md, date/YYYY_MM.md, topic/*.md.
# Folders under the jail (WORKSPACE): memory/, workspace/, test/, trash/, user/.
SYSTEM_BASE = (
    "Helpful agent on the user's Linux PC. "
    "Agent jail (whole tree): %s. "
    "Prefer workspace/ for new files and projects. "
    "user/ is read-only for the agent (list/read OK; no write/delete). "
    "Also: memory/, test/, trash/. "
    "Tools: files, memory, run_shell, web_search, reminders, jobs (workspace only). "
    "Memory: session.md (short), user.md (facts), assistant.md (extras), "
    "date/YYYY_MM.md + topic/*.md (logs). "
    "Shell has network by default; SHELL_NET=0 disables net inside bwrap. "
    "sudo (if ALLOW_SUDO) always needs Confirm / Telegram YES [password]. "
    "If run_shell needs confirm, say what you'll run and wait (UI or Telegram YES/NO); "
    "if it ran already, just report the result. "
    "Short answers. Name files the user can download."
) % (WORKSPACE,)


# ---------------------------------------------------------------------------
# Env helpers (provider defaults live in providers.py; re-exported above)
# ---------------------------------------------------------------------------


def load_env():
    """Public alias for _read_dotenv (reload each call so .env edits apply)."""
    return _read_dotenv()


def _env_get(name):
    """One env value: .env first, then the process environment, else empty."""
    return (load_env().get(name) or os.environ.get(name) or "").strip()


# ---------------------------------------------------------------------------
# Optional light-theme color overrides (UI_LIGHT_* in .env)
# ---------------------------------------------------------------------------
# Empty / unset → built-in soft-gray light defaults in ui.py.
# Served to the browser via /api/health and /api/models as "ui_light".

# Map: API/JSON key → env var name. CSS vars: --bg, --panel, …
_UI_LIGHT_ENV = (
    ("bg", "UI_LIGHT_BG"),
    ("panel", "UI_LIGHT_PANEL"),
    ("border", "UI_LIGHT_BORDER"),
    ("text", "UI_LIGHT_TEXT"),
    ("muted", "UI_LIGHT_MUTED"),
    ("user", "UI_LIGHT_USER"),
    ("bot", "UI_LIGHT_BOT"),
    ("bot_border", "UI_LIGHT_BOT_BORDER"),
    ("input", "UI_LIGHT_INPUT"),
)

# Loose hex: #rgb or #rrggbb (case-insensitive). Invalid values are ignored.
_HEX_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _valid_hex_color(raw):
    """Return normalized hex string if valid #rgb/#rrggbb, else None."""
    s = (raw or "").strip()
    if not s or not _HEX_COLOR_RE.match(s):
        return None
    return s


def ui_light_theme():
    """Optional UI_LIGHT_* hex overrides from .env for the soft light theme.

    Returns a dict of only valid keys (e.g. {"bg": "#d2d7e0"}). Empty dict
    when nothing is set or all values are invalid. Dark theme is never
    affected — the UI applies these only while data-theme=light.
    """
    out = {}
    for key, env_name in _UI_LIGHT_ENV:
        val = _valid_hex_color(_env_get(env_name))
        if val:
            out[key] = val
    return out


# ---------------------------------------------------------------------------
# Session memory reset (SESSION_RESET_HOURS / SESSION_RESET_AFTER)
# ---------------------------------------------------------------------------
# If neither env is set, default to clearing session.md when older than 24h.
# If both are set, either condition clears it.
# SESSION_RESET_AFTER=HH:MM — clear when local clock has passed that time since
# the session file's last modification (daily reset-at-clock pattern).


def session_reset_hours():
    """Optional SESSION_RESET_HOURS as float, or None if unset/invalid."""
    raw = _env_get("SESSION_RESET_HOURS")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def session_reset_after():
    """Optional SESSION_RESET_AFTER as (hour, minute), or None if unset/invalid."""
    raw = _env_get("SESSION_RESET_AFTER")
    if not raw or ":" not in raw:
        return None
    parts = raw.split(":", 1)
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h, m


def session_should_reset(mtime_ts, now=None):
    """True if session.md should be cleared given its mtime and current local time.

    Defaults: if neither SESSION_RESET_HOURS nor SESSION_RESET_AFTER is set,
    treat as HOURS=24. If both are set, either trigger clears the session.
    """
    now = now or datetime.now()
    hours = session_reset_hours()
    after = session_reset_after()
    if hours is None and after is None:
        hours = 24.0
    if hours is not None:
        age_s = now.timestamp() - float(mtime_ts)
        if age_s >= float(hours) * 3600.0:
            return True
    if after is not None:
        h, m = after
        boundary = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if now < boundary:
            boundary = boundary - timedelta(days=1)
        # Reset if file was last touched before the most recent HH:MM boundary.
        if float(mtime_ts) < boundary.timestamp():
            return True
    return False


# ---------------------------------------------------------------------------
# Optional Telegram bridge (remote DMs; UI stays on localhost)
# ---------------------------------------------------------------------------
# HOST stays 127.0.0.1. Telegram is the remote path: set TELEGRAM_BOT_TOKEN
# (and TELEGRAM_ALLOWED_CHAT_ID) in .env; run.py starts a long-poll thread.


def telegram_bot_token():
    """BotFather token from .env, or empty if Telegram is off."""
    return _env_get("TELEGRAM_BOT_TOKEN")


def telegram_allowed_chat_id():
    """DM allow-list chat id (string). Empty → bot replies with the caller's id only."""
    return _env_get("TELEGRAM_ALLOWED_CHAT_ID")


def telegram_provider():
    """Optional TELEGRAM_PROVIDER, else config default_provider()."""
    p = (_env_get("TELEGRAM_PROVIDER") or "").lower()
    if p and p in PROVIDERS:
        return p
    return default_provider()


def telegram_model():
    """Optional TELEGRAM_MODEL for the Telegram provider, else that provider's default."""
    provider = telegram_provider()
    m = _env_get("TELEGRAM_MODEL")
    if m:
        return allowed(provider, m)
    return default_model(provider)


def ensure_memory_dirs():
    """Create memory/, memory/date/, memory/topic/ if missing."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_DATE_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_TOPIC_DIR.mkdir(parents=True, exist_ok=True)


def allow_sudo():
    """True unless ALLOW_SUDO is 0/false/no/off (default: enabled)."""
    raw = (_env_get("ALLOW_SUDO") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def shell_net_env_off():
    """True when SHELL_NET=0/false/no/off (opt out of shell network under bwrap).

    Default is network ON. Unset or SHELL_NET=1/true/yes → keep host net.
    """
    raw = (_env_get("SHELL_NET") or "1").strip().lower()
    return raw in ("0", "false", "no", "off")


def ensure_ws():
    """Create WORKSPACE and standard subdirs (memory/workspace/test/trash/user).

    Does not delete existing content (upgrade-safe). Memory tree stays intact.
    """
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    for name in ("memory", "workspace", "test", "trash", "user"):
        (WORKSPACE / name).mkdir(parents=True, exist_ok=True)
    ensure_memory_dirs()
