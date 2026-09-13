"""
Config, env, paths, providers, and constants (stdlib only).

Single place for workspace location, listen address, API provider catalog,
and the system prompt. Other modules import names from here — nothing
imports this file for side effects except the path constants.

Imports from: stdlib only (os, re, pathlib).
Used by: tools.py, brain.py, server.py, run.py.
"""
import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root and version
# ---------------------------------------------------------------------------

# Folder that contains this file (the app install directory).
ROOT = Path(__file__).resolve().parent


def app_version():
    """Read VERSION from disk so the UI and /api/health can show it."""
    vp = ROOT / "VERSION"
    if vp.exists():
        return vp.read_text(encoding="utf-8").strip() or "0.0.0"
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
    """Workspace folder: WORKSPACE from .env, else ~/ai-agent."""
    raw = (_read_dotenv().get("WORKSPACE") or "").strip()
    if raw:
        raw = os.path.expandvars(raw)  # supports $USER, $HOME
        return Path(raw).expanduser()
    return Path.home() / "ai-agent"


def _host_port():
    """Listen address: always localhost. Port from .env (default 9191).

    LAN / 0.0.0.0 phone access was removed — use Telegram for remote chat later.
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
# Long-term notes the model can read and append.
MEMORY_FILE = WORKSPACE / "memory.md"
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


# ---------------------------------------------------------------------------
# Provider catalog (UI model picker + brain.py dispatch)
# ---------------------------------------------------------------------------

# Gemini REST root. The API key is passed as a query parameter.
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Each provider: display label, env var for the key, API "kind"
# (gemini / openai / anthropic), free+paid model lists, and a default model.
# kind "openai" means Chat Completions (OpenAI, xAI, DeepSeek).
PROVIDERS = {
    "gemini": {
        "label": "Gemini",
        "env_key": "GEMINI_API_KEY",
        "kind": "gemini",
        "free": ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"],
        "paid": ["gemini-3.6-pro", "gemini-3.5-pro", "gemini-2.5-pro"],
        "default": "gemini-3.6-flash",
    },
    "openai": {
        "label": "OpenAI (ChatGPT)",
        "env_key": "OPENAI_API_KEY",
        "kind": "openai",
        "base": "https://api.openai.com/v1",
        "free": ["gpt-4o-mini", "gpt-4.1-mini"],
        "paid": ["gpt-4o", "gpt-4.1"],
        "default": "gpt-4o-mini",
    },
    "xai": {
        "label": "xAI (Grok)",
        "env_key": "XAI_API_KEY",
        "kind": "openai",
        "base": "https://api.x.ai/v1",
        "free": ["grok-4.3", "grok-3-mini"],
        "paid": ["grok-4.6", "grok-4.5"],
        "default": "grok-4.3",
    },
    "anthropic": {
        "label": "Anthropic (Claude)",
        "env_key": "ANTHROPIC_API_KEY",
        "kind": "anthropic",
        "base": "https://api.anthropic.com/v1",
        "free": ["claude-haiku-4-5"],
        "paid": ["claude-sonnet-5", "claude-sonnet-4-6"],
        "default": "claude-haiku-4-5",
    },
    "deepseek": {
        "label": "DeepSeek",
        "env_key": "DEEPSEEK_API_KEY",
        "kind": "openai",
        "base": "https://api.deepseek.com/v1",
        "free": ["deepseek-chat"],
        "paid": ["deepseek-reasoner"],
        "default": "deepseek-chat",
    },
}


# Fallback if PROVIDER in .env is missing or not in PROVIDERS.
DEFAULT_PROVIDER = "gemini"


# ---------------------------------------------------------------------------
# Safety and the model's system prompt
# ---------------------------------------------------------------------------

# Commands we refuse even if the user clicks Confirm (rm -rf /, mkfs, …).
BLOCKED = re.compile(
    r"(?ix)(rm\s+-rf\s+/)|(mkfs\b)|(\bdd\b.*\bof=/dev/)|(shutdown\b)|(reboot\b)|(poweroff\b)"
)


# Instructions sent to every provider. tools.build_system appends memory.md.
SYSTEM_BASE = (
    "You are a helpful agent on the user's Linux PC. "
    "Workspace tools: list/read/write files, memory_read/memory_append, run_shell, "
    "web_search, reminder_add/reminder_list, job_add/job_list. "
    "Shell commands need the user to confirm in the UI — if run_shell returns needs_confirm, "
    "tell them briefly what you want to run and wait. "
    "Use memory_append for lasting notes. Use web_search for current info. "
    "Keep answers short. When you create a file the user may download, mention its name."
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
    """Return model if it is in that provider's free/paid lists; else the default."""
    meta = PROVIDERS.get(provider)
    if not meta:
        provider = default_provider()
        meta = PROVIDERS[provider]
    all_m = set(meta["free"]) | set(meta["paid"])
    if model and model in all_m:
        return model
    d = meta["default"]
    return d if d in all_m else meta["free"][0]


def ensure_ws():
    """Create the workspace folder if it does not exist yet."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
