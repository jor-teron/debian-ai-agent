#!/usr/bin/env python3
"""
Minimal personal AI agent for Debian.

- Stdlib only (no pip / venv / Apache)
- Local chat page (HOST/PORT from .env)
- Multiple AI providers (Gemini, OpenAI, xAI, Anthropic, DeepSeek)
- File + shell tools jailed to workspace
"""
import base64
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

# Refuse Python 2 / ancient 3.x early (clear message for mixed systems)
if sys.version_info[0] < 3:
    sys.stderr.write("This app needs Python 3. You ran Python %s.\n" % sys.version.split()[0])
    sys.stderr.write("Try:  python3 run.py   or   ./run.sh\n")
    sys.exit(1)
if sys.version_info < (3, 8):
    sys.stderr.write("Need Python 3.8+. You have %s\n" % sys.version.split()[0])
    sys.stderr.write("Try:  python3 run.py   or   ./run.sh\n")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent


def app_version():
    vp = ROOT / "VERSION"
    if vp.exists():
        return vp.read_text(encoding="utf-8").strip() or "0.0.0"
    return "0.0.0"


ENV_PATH = ROOT / ".env"


def _read_dotenv():
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
    raw = (_read_dotenv().get("WORKSPACE") or "").strip()
    if raw:
        raw = os.path.expandvars(raw)  # supports $USER, $HOME
        return Path(raw).expanduser()
    return Path.home() / "ai-agent"


def _host_port():
    env = _read_dotenv()
    host = (env.get("HOST") or os.environ.get("HOST") or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int((env.get("PORT") or os.environ.get("PORT") or "8787").strip() or "8787")
    except ValueError:
        port = 8787
    return host, port


WORKSPACE = _workspace_path()
MEMORY_FILE = WORKSPACE / "memory.md"
PENDING_SHELL = WORKSPACE / ".pending_shell.json"
REMINDERS_FILE = WORKSPACE / "reminders.json"
JOBS_FILE = WORKSPACE / "jobs.json"
JOBS_LOG = WORKSPACE / "jobs_log.md"
HOST, PORT = _host_port()

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Provider catalog: Free = cheaper/faster defaults, Paid = stronger.
# Model IDs chosen from current public docs (2026-09); see FEATURES.md.
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

DEFAULT_PROVIDER = "gemini"

BLOCKED = re.compile(
    r"(?ix)(rm\s+-rf\s+/)|(mkfs\b)|(\bdd\b.*\bof=/dev/)|(shutdown\b)|(reboot\b)|(poweroff\b)"
)

SYSTEM_BASE = (
    "You are a helpful agent on the user's Linux PC. "
    "Workspace tools: list/read/write files, memory_read/memory_append, run_shell, "
    "web_search, reminder_add/reminder_list, job_add/job_list. "
    "Shell commands need the user to confirm in the UI — if run_shell returns needs_confirm, "
    "tell them briefly what you want to run and wait. "
    "Use memory_append for lasting notes. Use web_search for current info. "
    "Keep answers short. When you create a file the user may download, mention its name."
)


def load_env():
    return _read_dotenv()


def _env_get(name):
    return (load_env().get(name) or os.environ.get(name) or "").strip()


def provider_key(provider):
    meta = PROVIDERS.get(provider) or {}
    ek = meta.get("env_key") or ""
    return _env_get(ek) if ek else ""


def keys_status():
    return {pid: bool(provider_key(pid)) for pid in PROVIDERS}


def default_provider():
    p = (_env_get("PROVIDER") or DEFAULT_PROVIDER).lower()
    return p if p in PROVIDERS else DEFAULT_PROVIDER


def default_model(provider=None):
    provider = provider or default_provider()
    meta = PROVIDERS[provider]
    # Optional per-provider model env: GEMINI_MODEL, OPENAI_MODEL, etc.
    env_name = meta["env_key"].replace("_API_KEY", "_MODEL")
    m = _env_get(env_name) or meta["default"]
    return allowed(provider, m)


def allowed(provider, model):
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
    WORKSPACE.mkdir(parents=True, exist_ok=True)


def memory_load():
    ensure_ws()
    if not MEMORY_FILE.exists():
        return ""
    return MEMORY_FILE.read_text(encoding="utf-8")[:20000]


def memory_save(text):
    ensure_ws()
    MEMORY_FILE.write_text(text or "", encoding="utf-8")
    return {"ok": True, "path": str(MEMORY_FILE), "bytes": len((text or "").encode("utf-8"))}


def memory_append(note):
    ensure_ws()
    cur = memory_load()
    add = (note or "").strip()
    if not add:
        return {"ok": False, "error": "Empty note"}
    sep = "\n" if cur and not cur.endswith("\n") else ""
    memory_save(cur + sep + add + "\n")
    return {"ok": True, "path": str(MEMORY_FILE)}


def build_system():
    mem = memory_load().strip()
    if mem:
        return SYSTEM_BASE + "\n\n## Memory (from workspace/memory.md)\n" + mem[:8000]
    return SYSTEM_BASE


def safe_path(user_path: str) -> Path:
    raw = Path(user_path).expanduser()
    cand = (WORKSPACE / raw).resolve() if not raw.is_absolute() else raw.resolve()
    try:
        cand.relative_to(WORKSPACE.resolve())
    except ValueError as e:
        raise PermissionError("Path outside workspace") from e
    return cand


def tool_list_dir(path: str = ".") -> dict:
    ensure_ws()
    t = safe_path(path)
    if not t.is_dir():
        return {"ok": False, "error": "Not a directory: %s" % t}
    entries = [{"name": c.name, "type": "dir" if c.is_dir() else "file"} for c in sorted(t.iterdir())]
    return {"ok": True, "path": str(t), "entries": entries}


def tool_read_file(path: str) -> dict:
    ensure_ws()
    t = safe_path(path)
    if not t.is_file():
        return {"ok": False, "error": "Not a file: %s" % t}
    data = t.read_bytes()[:200_000]
    return {"ok": True, "path": str(t), "content": data.decode("utf-8", errors="replace")}


def tool_write_file(path: str, content: str) -> dict:
    ensure_ws()
    t = safe_path(path)
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(t), "name": t.name}


def tool_write_bytes(path: str, data: bytes) -> dict:
    ensure_ws()
    t = safe_path(path)
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_bytes(data)
    return {"ok": True, "path": str(t), "name": t.name, "bytes": len(data)}


def _shell_execute(cmd):
    try:
        p = subprocess.run(
            cmd, shell=True, cwd=str(WORKSPACE), capture_output=True, text=True, timeout=30
        )
        return {
            "ok": p.returncode == 0,
            "exit_code": p.returncode,
            "stdout": p.stdout[-40000:],
            "stderr": p.stderr[-10000:],
            "command": cmd,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Timed out", "command": cmd}


def tool_run_shell(command, confirmed=False):
    """Queue shell for user confirm unless confirmed=True."""
    ensure_ws()
    cmd = (command or "").strip()
    if not cmd:
        return {"ok": False, "error": "Empty command"}
    if BLOCKED.search(cmd) or cmd.startswith("sudo"):
        return {"ok": False, "error": "Command blocked for safety"}
    if not confirmed:
        PENDING_SHELL.write_text(json.dumps({"command": cmd}), encoding="utf-8")
        return {
            "ok": False,
            "needs_confirm": True,
            "command": cmd,
            "error": "Waiting for user confirm in the UI",
        }
    if PENDING_SHELL.exists():
        PENDING_SHELL.unlink()
    return _shell_execute(cmd)


def confirm_pending_shell():
    ensure_ws()
    if not PENDING_SHELL.exists():
        return {"ok": False, "error": "Nothing to confirm"}
    data = json.loads(PENDING_SHELL.read_text(encoding="utf-8"))
    cmd = data.get("command") or ""
    return tool_run_shell(cmd, confirmed=True)


def cancel_pending_shell():
    if PENDING_SHELL.exists():
        PENDING_SHELL.unlink()
    return {"ok": True, "cancelled": True}


# --- Reminders ---

def _load_json_list(path: Path):
    ensure_ws()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _save_json_list(path: Path, items):
    ensure_ws()
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_due(due_iso=None, in_minutes=None):
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


def tool_reminder_add(text, due_iso=None, in_minutes=None):
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


# --- Jobs ---

def tool_job_add(every_minutes, prompt):
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
    return {"ok": True, "jobs": _load_json_list(JOBS_FILE)}


def _http_json(url, body, headers, timeout=90):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _plain_chat(prompt, provider=None, model=None):
    """Short call without tools (for scheduled jobs)."""
    provider = provider or default_provider()
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    model = allowed(provider, model or default_model(provider))
    key = provider_key(provider)
    if not key:
        return {"ok": False, "error": "No API key for %s" % provider, "reply": ""}
    meta = PROVIDERS[provider]
    kind = meta["kind"]
    try:
        if kind == "gemini":
            url = "%s/models/%s:generateContent?key=%s" % (GEMINI_API_BASE, model, key)
            data = _http_json(
                url,
                {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 1024},
                },
                {"Content-Type": "application/json"},
                timeout=60,
            )
            parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
            texts = [p.get("text", "") for p in parts if "text" in p]
            reply = "\n".join(texts).strip() or "(No text)"
            return {"ok": True, "reply": reply, "model": model, "provider": provider}
        if kind == "openai":
            url = meta["base"].rstrip("/") + "/chat/completions"
            data = _http_json(
                url,
                {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1024,
                },
                {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer %s" % key,
                },
                timeout=60,
            )
            msg = ((data.get("choices") or [{}])[0].get("message") or {})
            reply = (msg.get("content") or "").strip() or "(No text)"
            return {"ok": True, "reply": reply, "model": model, "provider": provider}
        if kind == "anthropic":
            url = meta["base"].rstrip("/") + "/messages"
            data = _http_json(
                url,
                {
                    "model": model,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
                {
                    "Content-Type": "application/json",
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=60,
            )
            texts = [
                b.get("text", "")
                for b in (data.get("content") or [])
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            reply = "\n".join(texts).strip() or "(No text)"
            return {"ok": True, "reply": reply, "model": model, "provider": provider}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "reply": ""}
    return {"ok": False, "error": "Unknown provider kind", "reply": ""}


def process_due_jobs():
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


def background_loop():
    while True:
        try:
            process_due_reminders()
            process_due_jobs()
        except Exception as e:  # noqa: BLE001
            print("[bg] error: %s" % e)
        time.sleep(30)


# --- Web search via Gemini Google Search tool ---

def tool_web_search(query):
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
        "description": "Propose a shell command (cwd=workspace). User must confirm in UI before it runs.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "memory_read",
        "description": "Read long-term memory notes for this user",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "memory_append",
        "description": "Append a lasting note to memory",
        "parameters": {
            "type": "object",
            "properties": {"note": {"type": "string"}},
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
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t.get("parameters") or {"type": "object", "properties": {}},
        }
        for t in TOOL_DECLS
    ]


def dispatch(name, args):
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
            return {"ok": True, "memory": memory_load()}
        if name == "memory_append":
            return memory_append(args.get("note") or "")
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


def gemini_chat(message, model, history):
    key = provider_key("gemini")
    if not key:
        return {
            "ok": False,
            "error": "GEMINI_API_KEY missing. Copy .env.example to .env and add your key.",
            "reply": "",
            "tools": [],
            "provider": "gemini",
        }

    model = allowed("gemini", model)
    contents = []
    for turn in (history or [])[-16:]:
        role = "user" if turn.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": turn.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    url = "%s/models/%s:generateContent?key=%s" % (GEMINI_API_BASE, model, key)
    tool_trace = []
    reply = ""
    system = build_system()

    for _ in range(6):
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "tools": [{"function_declarations": TOOL_DECLS}],
        }
        try:
            data = _http_json(url, body, {"Content-Type": "application/json"}, timeout=90)
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")[:800]
            return {
                "ok": False,
                "error": "Gemini HTTP %s: %s" % (e.code, err),
                "reply": "",
                "tools": tool_trace,
                "model": model,
                "provider": "gemini",
            }
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "error": str(e),
                "reply": "",
                "tools": tool_trace,
                "model": model,
                "provider": "gemini",
            }

        parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
        fn_calls, texts = [], []
        for p in parts:
            if "functionCall" in p:
                fn_calls.append(p["functionCall"])
            elif "text" in p:
                texts.append(p["text"])

        if not fn_calls:
            reply = "\n".join(texts).strip() or "(No text)"
            break

        contents.append({"role": "model", "parts": parts})
        response_parts = []
        for fc in fn_calls:
            name = fc.get("name") or ""
            args = fc.get("args") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            result = dispatch(name, args)
            tool_trace.append({"name": name, "args": args, "result": result})
            response_parts.append({"functionResponse": {"name": name, "response": result}})
        contents.append({"role": "user", "parts": response_parts})
    else:
        reply = reply or "Stopped after too many tool steps."

    return {"ok": True, "reply": reply, "tools": tool_trace, "model": model, "provider": "gemini"}


def openai_compat_chat(provider, message, model, history):
    meta = PROVIDERS[provider]
    key = provider_key(provider)
    if not key:
        return {
            "ok": False,
            "error": "%s missing. Add it to .env." % meta["env_key"],
            "reply": "",
            "tools": [],
            "provider": provider,
        }

    model = allowed(provider, model)
    messages = [{"role": "system", "content": build_system()}]
    for turn in (history or [])[-16:]:
        role = "user" if turn.get("role") == "user" else "assistant"
        messages.append({"role": role, "content": turn.get("content", "")})
    messages.append({"role": "user", "content": message})

    url = meta["base"].rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer %s" % key,
    }
    tool_trace = []
    reply = ""

    for _ in range(6):
        body = {
            "model": model,
            "messages": messages,
            "tools": openai_tools(),
            "tool_choice": "auto",
        }
        try:
            data = _http_json(url, body, headers, timeout=90)
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")[:800]
            return {
                "ok": False,
                "error": "%s HTTP %s: %s" % (provider, e.code, err),
                "reply": "",
                "tools": tool_trace,
                "model": model,
                "provider": provider,
            }
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "error": str(e),
                "reply": "",
                "tools": tool_trace,
                "model": model,
                "provider": provider,
            }

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls") or []
        content = msg.get("content") or ""

        if not tool_calls:
            reply = (content or "").strip() or "(No text)"
            break

        # Append assistant turn (with tool_calls)
        messages.append(
            {
                "role": "assistant",
                "content": content if content else None,
                "tool_calls": tool_calls,
            }
        )
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except json.JSONDecodeError:
                args = {}
            result = dispatch(name, args)
            tool_trace.append({"name": name, "args": args, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id") or name,
                    "content": json.dumps(result),
                }
            )
    else:
        reply = reply or "Stopped after too many tool steps."

    return {"ok": True, "reply": reply, "tools": tool_trace, "model": model, "provider": provider}


def anthropic_chat(message, model, history):
    meta = PROVIDERS["anthropic"]
    key = provider_key("anthropic")
    if not key:
        return {
            "ok": False,
            "error": "ANTHROPIC_API_KEY missing. Add it to .env.",
            "reply": "",
            "tools": [],
            "provider": "anthropic",
        }

    model = allowed("anthropic", model)
    messages = []
    for turn in (history or [])[-16:]:
        role = "user" if turn.get("role") == "user" else "assistant"
        messages.append({"role": role, "content": turn.get("content", "")})
    messages.append({"role": "user", "content": message})

    url = meta["base"].rstrip("/") + "/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }
    tool_trace = []
    reply = ""
    system = build_system()

    for _ in range(6):
        body = {
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "messages": messages,
            "tools": anthropic_tools(),
        }
        try:
            data = _http_json(url, body, headers, timeout=90)
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")[:800]
            return {
                "ok": False,
                "error": "Anthropic HTTP %s: %s" % (e.code, err),
                "reply": "",
                "tools": tool_trace,
                "model": model,
                "provider": "anthropic",
            }
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "error": str(e),
                "reply": "",
                "tools": tool_trace,
                "model": model,
                "provider": "anthropic",
            }

        content_blocks = data.get("content") or []
        tool_uses = [b for b in content_blocks if isinstance(b, dict) and b.get("type") == "tool_use"]
        texts = [
            b.get("text", "")
            for b in content_blocks
            if isinstance(b, dict) and b.get("type") == "text"
        ]

        if not tool_uses:
            reply = "\n".join(texts).strip() or "(No text)"
            break

        messages.append({"role": "assistant", "content": content_blocks})
        result_blocks = []
        for tu in tool_uses:
            name = tu.get("name") or ""
            args = tu.get("input") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            result = dispatch(name, args)
            tool_trace.append({"name": name, "args": args, "result": result})
            result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu.get("id") or name,
                    "content": json.dumps(result),
                }
            )
        messages.append({"role": "user", "content": result_blocks})
    else:
        reply = reply or "Stopped after too many tool steps."

    return {
        "ok": True,
        "reply": reply,
        "tools": tool_trace,
        "model": model,
        "provider": "anthropic",
    }


def run_chat(message, provider=None, model=None, history=None):
    provider = (provider or default_provider() or DEFAULT_PROVIDER).lower().strip()
    if provider not in PROVIDERS:
        return {
            "ok": False,
            "error": "Unknown provider %r. Use one of: %s" % (provider, ", ".join(PROVIDERS)),
            "reply": "",
            "tools": [],
        }
    meta = PROVIDERS[provider]
    kind = meta["kind"]
    if kind == "gemini":
        return gemini_chat(message, model, history)
    if kind == "openai":
        return openai_compat_chat(provider, message, model, history)
    if kind == "anthropic":
        return anthropic_chat(message, model, history)
    return {"ok": False, "error": "Unsupported provider kind", "reply": "", "tools": []}


HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AI Agent</title>
<style>
body{margin:0;font-family:system-ui,sans-serif;background:#0f1419;color:#e7ecf3;display:flex;flex-direction:column;min-height:100vh}
header{padding:12px 16px;background:#1a2332;display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between}
h1{font-size:1.05rem;margin:0}
.controls{display:flex;gap:8px;flex-wrap:wrap;align-items:end}
label{font-size:.75rem;color:#9aa8bc;display:block}
select,button,textarea,input[type=file]{font:inherit;border-radius:8px;border:1px solid #2a3548;background:#0c1118;color:#e7ecf3}
select{padding:6px 8px}
#status{font-size:.8rem;color:#9aa8bc;max-width:320px}
#status.ok{color:#6ee7b7}#status.bad{color:#f87171}
#note{font-size:.75rem;color:#fbbf24;padding:0 16px;min-height:0}
#confirm{display:none;padding:10px 16px;background:#3a2a12;border-bottom:1px solid #5a4020;gap:8px;flex-wrap:wrap;align-items:center}
#confirm.show{display:flex}
#confirm code{flex:1;min-width:120px;word-break:break-all;font-size:.85rem}
#confirm .ok{background:#6ee7b7}#confirm .no{background:#f87171;color:#041018}
#log{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
.msg{max-width:820px;padding:10px 12px;border-radius:12px;white-space:pre-wrap;line-height:1.4}
.user{align-self:flex-end;background:#243247}
.bot{align-self:flex-start;background:#1a2332;border:1px solid #2a3548}
.tools{margin-top:6px;font-size:.75rem;color:#9aa8bc}
.dl{margin-top:6px;font-size:.8rem}
.dl a{color:#60a5fa}
form{display:flex;gap:8px;padding:12px;background:#1a2332;border-top:1px solid #2a3548;flex-wrap:wrap;align-items:end}
textarea{flex:1;min-height:44px;padding:8px;min-width:160px}
button{padding:10px 14px;background:#60a5fa;border:none;color:#041018;font-weight:600;cursor:pointer}
button:disabled{opacity:.5}
.up{font-size:.75rem}
</style></head><body>
<header>
  <h1>AI Agent</h1>
  <div class="controls">
    <div><label>Provider</label>
      <select id="provider"></select>
    </div>
    <div><label>Category</label>
      <select id="tier"><option value="free" selected>Free</option><option value="paid">Paid</option></select>
    </div>
    <div><label>Model</label><select id="model"></select></div>
    <div id="status">…</div>
  </div>
</header>
<div id="note"></div>
<div id="confirm"><span>Run shell?</span><code id="pendingCmd"></code>
  <button type="button" class="ok" id="btnConfirm">Confirm</button>
  <button type="button" class="no" id="btnCancel">Cancel</button>
</div>
<div id="log"></div>
<form id="f">
  <textarea id="input" placeholder="Ask something…" required></textarea>
  <div class="up"><label>Upload</label><input type="file" id="file"/></div>
  <button id="send">Send</button>
</form>
<script>
const log=document.getElementById('log'),provider=document.getElementById('provider');
const tier=document.getElementById('tier'),model=document.getElementById('model');
const status=document.getElementById('status'),input=document.getElementById('input'),send=document.getElementById('send');
const note=document.getElementById('note'),confirmBar=document.getElementById('confirm'),pendingCmd=document.getElementById('pendingCmd');
const fileInput=document.getElementById('file');
let catalog={providers:{},default_provider:'gemini',default_model:'gemini-3.6-flash'}, history=[], keys={};
function fillProviders(){
  provider.innerHTML='';
  Object.keys(catalog.providers||{}).forEach(pid=>{
    const o=document.createElement('option'); o.value=pid; o.textContent=pid; provider.appendChild(o);
  });
  const sp=localStorage.getItem('p');
  if(sp && catalog.providers[sp]) provider.value=sp;
  else if(catalog.default_provider && catalog.providers[catalog.default_provider]) provider.value=catalog.default_provider;
}
function fillModels(){
  const p=catalog.providers[provider.value]||{free:[],paid:[]};
  const list=p[tier.value]||[];
  model.innerHTML='';
  list.forEach(m=>{const o=document.createElement('option');o.value=m;o.textContent=m;model.appendChild(o);});
  const key='m:'+provider.value;
  const s=localStorage.getItem(key);
  const def=catalog.default_model;
  if(s&&list.includes(s)) model.value=s;
  else if(provider.value===catalog.default_provider && list.includes(def)) model.value=def;
  else if(list[0]) model.value=list[0];
}
function updateStatus(){
  const pid=provider.value;
  const has=!!keys[pid];
  const wsLabel=(window._ws||'').replace(/^.*\//,'…/');
  status.textContent=(has?(pid+' key OK'):(pid+' key missing — edit .env'))+' · v'+(window._ver||'?')+' · '+wsLabel;
  status.className=has?'ok':'bad';
}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function add(role,text,tools){const d=document.createElement('div'); d.className='msg '+(role==='user'?'user':'bot'); d.textContent=text;
  if(tools&&tools.length){const x=document.createElement('details'); x.className='tools'; x.innerHTML='<summary>'+tools.length+' tool(s)</summary><pre>'+esc(JSON.stringify(tools,null,2))+'</pre>'; d.appendChild(x);
    const names=[]; tools.forEach(t=>{const r=t.result||{}; const n=r.name||(r.path&&String(r.path).split('/').pop()); if(n&&(t.name==='write_file'||r.path)) names.push(n);});
    if(names.length){const dl=document.createElement('div'); dl.className='dl'; dl.innerHTML=names.map(n=>'<a href="/api/download?name='+encodeURIComponent(n)+'" download>'+esc(n)+'</a>').join(' · '); d.appendChild(dl);}
  }
  if(role!=='user' && text && text.indexOf('[[download:')>=0){
    const dl=document.createElement('div'); dl.className='dl';
    const re=/\[\[download:([^\]]+)\]\]/g; let m; const seen={};
    while((m=re.exec(text))){const n=m[1].trim(); if(n&&!seen[n]){seen[n]=1; dl.innerHTML+=(dl.innerHTML?' · ':'')+'<a href="/api/download?name='+encodeURIComponent(n)+'" download>'+esc(n)+'</a>';}}
    if(dl.innerHTML) d.appendChild(dl);
  }
  log.appendChild(d); log.scrollTop=log.scrollHeight;}
async function refreshPending(){
  try{
    const p=await fetch('/api/pending').then(r=>r.json());
    if(p.command){pendingCmd.textContent=p.command; confirmBar.classList.add('show');}
    else confirmBar.classList.remove('show');
  }catch(e){}
}
async function boot(){
  try{
    const h=await fetch('/api/health').then(r=>r.json());
    keys=h.keys||{};
    window._ws=h.workspace||'';
    window._ver=h.version||'?';
    if(h.due_reminders&&h.due_reminders.length){
      note.textContent='Due reminders: '+h.due_reminders.map(r=>r.text).join('; ');
    } else note.textContent='';
    const m=await fetch('/api/models').then(r=>r.json());
    catalog={providers:m.providers||{},default_provider:m.default_provider||'gemini',default_model:m.default_model||''};
    fillProviders();
    const t=localStorage.getItem('t'); if(t==='paid'||t==='free') tier.value=t;
    fillModels();
    updateStatus();
    await refreshPending();
  }catch(e){status.textContent='Cannot reach server'; status.className='bad';}
}
provider.onchange=()=>{localStorage.setItem('p',provider.value); fillModels(); updateStatus();};
tier.onchange=()=>{localStorage.setItem('t',tier.value); fillModels();};
model.onchange=()=>localStorage.setItem('m:'+provider.value,model.value);
document.getElementById('btnConfirm').onclick=async()=>{
  const res=await fetch('/api/confirm',{method:'POST'}).then(r=>r.json());
  add('bot', res.ok?('Shell OK (exit '+(res.exit_code??'?')+'):\n'+(res.stdout||'')+(res.stderr?('\n'+res.stderr):'')):(res.error||'Confirm failed'));
  refreshPending();
};
document.getElementById('btnCancel').onclick=async()=>{
  await fetch('/api/cancel',{method:'POST'});
  add('bot','Shell cancelled.');
  refreshPending();
};
fileInput.onchange=async()=>{
  const f=fileInput.files&&fileInput.files[0]; if(!f) return;
  send.disabled=true;
  try{
    const buf=await f.arrayBuffer();
    const bytes=new Uint8Array(buf);
    let b64=''; const chunk=0x8000;
    for(let i=0;i<bytes.length;i+=chunk){b64+=String.fromCharCode.apply(null,bytes.subarray(i,i+chunk));}
    b64=btoa(b64);
    const isText=/\.(txt|md|py|sh|json|csv|html|css|js|env|log|yml|yaml)$/i.test(f.name)&&f.size<200000;
    let body;
    if(isText){
      const text=await f.text();
      body={name:f.name,content:text};
    }else{
      body={name:f.name,content:b64,encoding:'base64'};
    }
    const res=await fetch('/api/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(r=>r.json());
    if(res.ok) add('bot','Uploaded '+f.name+' → download: /api/download?name='+encodeURIComponent(f.name)+'  ([[download:'+f.name+']])');
    else add('bot','Upload failed: '+(res.error||'?'));
  }catch(e){add('bot','Upload error: '+e);} finally{fileInput.value=''; send.disabled=false;}
};
document.getElementById('f').onsubmit=async ev=>{
  ev.preventDefault(); const message=input.value.trim(); if(!message) return;
  add('user',message); input.value=''; send.disabled=true;
  try{
    const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message,provider:provider.value,model:model.value,history})});
    const data=await res.json();
    if(!data.ok) add('bot', data.error||'Failed', data.tools); else {
      add('bot', data.reply, data.tools);
      history.push({role:'user',content:message},{role:'assistant',content:data.reply});
      if(history.length>20) history=history.slice(-20);
    }
    await refreshPending();
    const h=await fetch('/api/health').then(r=>r.json());
    keys=h.keys||keys;
    updateStatus();
    if(h.due_reminders&&h.due_reminders.length) note.textContent='Due reminders: '+h.due_reminders.map(r=>r.text).join('; ');
  }catch(e){add('bot','Network error: '+e);} finally{send.disabled=false; input.focus();}
};
boot();
setInterval(refreshPending, 4000);
setInterval(async()=>{try{const h=await fetch('/api/health').then(r=>r.json());
  keys=h.keys||keys; updateStatus();
  if(h.due_reminders&&h.due_reminders.length) note.textContent='Due reminders: '+h.due_reminders.map(r=>r.text).join('; ');
  else if(note.textContent.startsWith('Due reminders:')) note.textContent='';
}catch(e){}}, 15000);
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter terminal
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _send(self, code, body, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        raw = json.dumps(obj).encode("utf-8")
        self._send(code, raw, "application/json; charset=utf-8")

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/health":
            rem = tool_reminder_list()
            due = rem.get("due") or []
            keys = keys_status()
            self._json(
                200,
                {
                    "ok": True,
                    "keys": keys,
                    "api_key_set": any(keys.values()),
                    "workspace": str(WORKSPACE),
                    "pending_shell": PENDING_SHELL.exists(),
                    "version": app_version(),
                    "host": HOST,
                    "port": PORT,
                    "default_provider": default_provider(),
                    "due_reminders": [
                        {"id": r.get("id"), "text": r.get("text"), "due": r.get("due")} for r in due
                    ],
                },
            )
            return
        if path == "/api/models":
            providers = {
                pid: {"free": list(meta["free"]), "paid": list(meta["paid"])}
                for pid, meta in PROVIDERS.items()
            }
            dp = default_provider()
            self._json(
                200,
                {
                    "providers": providers,
                    "default_provider": dp,
                    "default_model": default_model(dp),
                },
            )
            return
        if path == "/api/reminders":
            self._json(200, tool_reminder_list())
            return
        if path == "/api/download":
            qs = parse_qs(urlparse(self.path).query)
            name = Path((qs.get("name") or [""])[0]).name
            if not name:
                self._json(400, {"ok": False, "error": "name required"})
                return
            try:
                target = safe_path(name)
            except PermissionError as e:
                self._json(403, {"ok": False, "error": str(e)})
                return
            if not target.is_file():
                self._json(404, {"ok": False, "error": "file not found"})
                return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % name)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/pending":
            if PENDING_SHELL.exists():
                self._json(200, json.loads(PENDING_SHELL.read_text(encoding="utf-8")))
            else:
                self._json(200, {"command": None})
            return
        self._json(404, {"ok": False, "error": "Not found"})

    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""

        if path == "/api/confirm":
            self._json(200, confirm_pending_shell())
            return
        if path == "/api/cancel":
            self._json(200, cancel_pending_shell())
            return
        if path == "/api/upload":
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._json(400, {"ok": False, "error": "Invalid JSON"})
                return
            name = Path(data.get("name") or "").name
            if not name:
                self._json(400, {"ok": False, "error": "name required"})
                return
            enc = (data.get("encoding") or "text").lower()
            content = data.get("content") or ""
            if enc == "base64":
                try:
                    blob = base64.b64decode(content)
                except Exception as e:  # noqa: BLE001
                    self._json(400, {"ok": False, "error": "bad base64: %s" % e})
                    return
                if len(blob) > 2_000_000:
                    self._json(400, {"ok": False, "error": "file too large (max ~2MB)"})
                    return
                result = tool_write_bytes(name, blob)
            else:
                result = tool_write_file(name, content)
            self._json(200 if result.get("ok") else 400, result)
            return
        if path != "/api/chat":
            self._json(404, {"ok": False, "error": "Not found"})
            return
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "error": "Invalid JSON"})
            return
        message = (data.get("message") or "").strip()
        if not message:
            self._json(400, {"ok": False, "error": "message required"})
            return
        result = run_chat(
            message,
            provider=data.get("provider"),
            model=data.get("model"),
            history=data.get("history") or [],
        )
        self._json(200 if result.get("ok") else 400, result)


def _lan_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    return ips


def main():
    ensure_ws()
    if not ENV_PATH.exists() and (ROOT / ".env.example").exists():
        print("Tip: copy .env.example to .env and add provider API keys")
    t = threading.Thread(target=background_loop, name="reminders-jobs", daemon=True)
    t.start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("debian-ai-agent v%s" % app_version())
    print("Workspace: %s" % WORKSPACE)
    print("Default provider: %s" % default_provider())
    print("Open http://%s:%s  (Ctrl+C to stop)" % (HOST if HOST != "0.0.0.0" else "127.0.0.1", PORT))
    if HOST == "0.0.0.0":
        tips = _lan_ips()
        print("LAN access: set phone browser to http://<this-pc-ip>:%s" % PORT)
        for ip in tips:
            print("  e.g. http://%s:%s" % (ip, PORT))
        print("(Same WiFi; firewall may need to allow TCP %s)" % PORT)
    keys = keys_status()
    if not any(keys.values()):
        print("WARNING: no provider API keys set in .env yet")
    else:
        set_names = [k for k, v in keys.items() if v]
        print("Keys set: %s" % ", ".join(set_names))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
