"""
Config, env, paths, providers, and constants (stdlib only).

Single place for workspace location, listen address, API provider catalog,
and the system prompt. Other modules import names from here — nothing
imports this file for side effects except the path constants.

Imports from: stdlib only (os, re, pathlib, datetime).
Used by: tools.py, brain.py, server.py, run.py, telegram.py.
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



# User secrets and overrides (API keys, HOST, PORT, WORKSPACE, PROVIDER).
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
    """Listen address: always localhost. Port from .env (default 9191).

    LAN / 0.0.0.0 phone access was removed — use optional Telegram for remote chat.
    """
    env = _read_dotenv()
    # Local browser UI only (no 0.0.0.0 / LAN exposure).
    host = "127.0.0.1"
    try:
        port = int((env.get("PORT") or os.environ.get("PORT") or "9191").strip() or "9191")
    except ValueError:
        port = 9191
    return host, port


# ---------------------------------------------------------------------------
# Workspace files (created on demand when tools write them)
# ---------------------------------------------------------------------------

# Jail for file/shell tools. User uploads and downloads live here too.
WORKSPACE = _workspace_path()
# Legacy single-file memory (migrated once into memory/date/YYYY_MM.md).
MEMORY_FILE = WORKSPACE / "memory.md"
# Split memory tree under workspace/memory/.
MEMORY_DIR = WORKSPACE / "memory"
MEMORY_SESSION = MEMORY_DIR / "session.md"
MEMORY_USER = MEMORY_DIR / "user.md"
MEMORY_ASSISTANT = MEMORY_DIR / "assistant.md"
MEMORY_DATE_DIR = MEMORY_DIR / "date"
MEMORY_TOPIC_DIR = MEMORY_DIR / "topic"
# JSON blob for a shell command waiting for the UI Confirm button.
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
# Provider catalog (UI model picker + brain.py dispatch)
# ---------------------------------------------------------------------------

# Gemini REST root. The API key is passed as a query parameter.
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Each provider: display label, env var for the key, API "kind"
# (gemini / openai / anthropic), one models list, and a default model.
# kind "openai" means Chat Completions (OpenAI, xAI, DeepSeek, OpenRouter, DeepInfra).
# No free/paid split in the UI — almost all keys are paid except Gemini.
PROVIDERS = {
    "gemini": {
        "label": "Gemini",
        "env_key": "GEMINI_API_KEY",
        "kind": "gemini",
        "models": [
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.6-flash",
            "gemini-3.6-pro",
            "gemini-3.5-pro",
            "gemini-2.5-pro",
        ],
        "default": "gemini-3.5-flash-lite",
    },
    "openai": {
        "label": "OpenAI (ChatGPT)",
        "env_key": "OPENAI_API_KEY",
        "kind": "openai",
        "base": "https://api.openai.com/v1",
        "models": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o", "gpt-4.1"],
        "default": "gpt-4o-mini",
    },
    "xai": {
        "label": "xAI (Grok)",
        "env_key": "XAI_API_KEY",
        "kind": "openai",
        "base": "https://api.x.ai/v1",
        "models": ["grok-4.3", "grok-3-mini", "grok-4.6", "grok-4.5"],
        "default": "grok-4.3",
    },
    "anthropic": {
        "label": "Anthropic (Claude)",
        "env_key": "ANTHROPIC_API_KEY",
        "kind": "anthropic",
        "base": "https://api.anthropic.com/v1",
        "models": ["claude-haiku-4-5", "claude-sonnet-5", "claude-sonnet-4-6"],
        "default": "claude-haiku-4-5",
    },
    "deepseek": {
        "label": "DeepSeek",
        "env_key": "DEEPSEEK_API_KEY",
        "kind": "openai",
        "base": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default": "deepseek-chat",
    },
    "openrouter": {
        "label": "OpenRouter",
        "env_key": "OPENROUTER_API_KEY",
        "kind": "openai",
        "base": "https://openrouter.ai/api/v1",
        "models": [
            "openrouter/auto",
            "openai/gpt-4o-mini",
            "google/gemini-2.0-flash-001",
            "meta-llama/llama-3.3-70b-instruct",
        ],
        "default": "openrouter/auto",
    },
    "deepinfra": {
        "label": "DeepInfra",
        "env_key": "DEEPINFRA_API_KEY",
        "kind": "openai",
        "base": "https://api.deepinfra.com/v1/openai",
        "models": [
            "meta-llama/Meta-Llama-3.1-8B-Instruct",
            "meta-llama/Meta-Llama-3.1-70B-Instruct",
            "google/gemma-2-9b-it",
            "mistralai/Mistral-7B-Instruct-v0.3",
        ],
        "default": "meta-llama/Meta-Llama-3.1-8B-Instruct",
    },
}


# Fallback if PROVIDER in .env is missing or not in PROVIDERS.
DEFAULT_PROVIDER = "gemini"


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
SYSTEM_BASE = (
    "Helpful agent on the user's Linux PC. "
    "Tools: files, memory, run_shell, web_search, reminders, jobs (workspace only). "
    "Memory: session.md (short), user.md (facts), assistant.md (extras), "
    "date/YYYY_MM.md + topic/*.md (logs). "
    "If run_shell needs confirm, say what you'll run and wait (UI or Telegram YES/NO); "
    "if it ran already, just report the result. "
    "Short answers. Name files the user can download."
)


# ---------------------------------------------------------------------------
# Env helpers and provider defaults
# ---------------------------------------------------------------------------


def load_env():
    """Public alias for _read_dotenv (reload each call so .env edits apply)."""
    return _read_dotenv()


def _env_get(name):
    """One env value: .env first, then the process environment, else empty."""
    return (load_env().get(name) or os.environ.get(name) or "").strip()


def provider_key(provider):
    """API key for a provider id (gemini, openai, …), or empty if unset."""
    meta = PROVIDERS.get(provider) or {}
    ek = meta.get("env_key") or ""
    return _env_get(ek) if ek else ""


def keys_status():
    """Map of provider id → True if that key is set (for /api/health)."""
    return {pid: bool(provider_key(pid)) for pid in PROVIDERS}


def default_provider():
    """PROVIDER from .env if valid, otherwise DEFAULT_PROVIDER."""
    p = (_env_get("PROVIDER") or DEFAULT_PROVIDER).lower()
    return p if p in PROVIDERS else DEFAULT_PROVIDER


def default_model(provider=None):
    """Default model for a provider (optional GEMINI_MODEL / OPENAI_MODEL / …)."""
    provider = provider or default_provider()
    meta = PROVIDERS[provider]
    # Optional per-provider model env: GEMINI_MODEL, OPENAI_MODEL, etc.
    env_name = meta["env_key"].replace("_API_KEY", "_MODEL")
    m = _env_get(env_name) or meta["default"]
    return allowed(provider, m)


def allowed(provider, model):
    """Return model if it is in that provider's models list; else the default."""
    meta = PROVIDERS.get(provider)
    if not meta:
        provider = default_provider()
        meta = PROVIDERS[provider]
    all_m = set(meta.get("models") or [])
    if model and model in all_m:
        return model
    d = meta["default"]
    return d if d in all_m else (meta["models"][0] if meta.get("models") else d)


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


def ensure_ws():
    """Create the workspace folder and memory tree if they do not exist yet."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    ensure_memory_dirs()
