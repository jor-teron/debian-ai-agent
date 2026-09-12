"""
OS tool implementations for the agent.

Safety model (why this exists):
- By default every path is resolved and must stay inside WORKSPACE (the jail).
- AGENT_ALLOW_SYSTEM=1 lifts the jail for trusted local use — still your machine.
- Shell commands are blocked from obvious disasters (rm -rf /, mkfs, dd to disks)
  and from sudo unless AGENT_ALLOW_SUDO=1.
- Tool calls are appended to logs/tools.jsonl for later audit.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Project root = parent of app/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOG_PATH = _PROJECT_ROOT / "logs" / "tools.jsonl"

# Patterns that should never run accidentally from an LLM-chosen command.
_DISASTER_PATTERNS = [
    re.compile(r"\brm\s+(-[^\s]*\s+)*/*(?:\s|$)", re.I),  # rm … /
    re.compile(r"\brm\s+(-[^\s]*\s+)*--no-preserve-root", re.I),
    re.compile(r"\bmkfs(\.\w+)?\b", re.I),
    re.compile(r"\bdd\b.*\bof\s*=\s*/dev/", re.I),
    re.compile(r">\s*/dev/sd[a-z]", re.I),
    re.compile(r"\b(wipefs|shred)\b.*(/dev/|/)", re.I),
    re.compile(r":\(\)\s*\{\s*:\|:&\s*\}\s*;", re.I),  # fork bomb
]


def _workspace_root() -> Path:
    raw = os.environ.get("WORKSPACE", "/home/user/agent-workspace")
    return Path(raw).expanduser().resolve()


def _allow_system() -> bool:
    return os.environ.get("AGENT_ALLOW_SYSTEM", "").strip() in ("1", "true", "yes")


def _allow_sudo() -> bool:
    return os.environ.get("AGENT_ALLOW_SUDO", "").strip() in ("1", "true", "yes")


def _log_tool(name: str, args: dict[str, Any], result: dict[str, Any]) -> None:
    """Append one JSON line — keeps history small and grep-friendly."""
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": name,
        "args": args,
        "ok": result.get("ok", False),
        "error": result.get("error"),
    }
    with _LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def resolve_jail_path(path: str) -> Path:
    """
    Resolve path relative to WORKSPACE (or absolute if given).
    Raise PermissionError if the result escapes the jail (unless allow-system).
    """
    root = _workspace_root()
    root.mkdir(parents=True, exist_ok=True)
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = root / p
    resolved = p.resolve()
    if not _allow_system():
        try:
            resolved.relative_to(root)
        except ValueError as e:
            raise PermissionError(
                f"Path '{path}' is outside workspace jail ({root}). "
                "Set AGENT_ALLOW_SYSTEM=1 only if you intentionally want full-disk access."
            ) from e
    return resolved


def list_dir(path: str = ".") -> dict[str, Any]:
    try:
        target = resolve_jail_path(path)
        if not target.exists():
            out = {"ok": False, "error": f"Not found: {target}"}
        elif not target.is_dir():
            out = {"ok": False, "error": f"Not a directory: {target}"}
        else:
            entries = []
            for child in sorted(target.iterdir(), key=lambda c: c.name.lower()):
                kind = "dir" if child.is_dir() else "file"
                size = child.stat().st_size if child.is_file() else None
                entries.append({"name": child.name, "kind": kind, "size": size})
            out = {"ok": True, "path": str(target), "entries": entries}
    except Exception as e:
        out = {"ok": False, "error": str(e)}
    _log_tool("list_dir", {"path": path}, out)
    return out


def read_file(path: str) -> dict[str, Any]:
    try:
        target = resolve_jail_path(path)
        if not target.is_file():
            out = {"ok": False, "error": f"Not a file: {target}"}
        else:
            # Cap read size so a huge file cannot blow ~900 Mi free RAM.
            max_bytes = 512_000
            data = target.read_bytes()
            truncated = len(data) > max_bytes
            text = data[:max_bytes].decode("utf-8", errors="replace")
            out = {
                "ok": True,
                "path": str(target),
                "content": text,
                "truncated": truncated,
            }
    except Exception as e:
        out = {"ok": False, "error": str(e)}
    _log_tool("read_file", {"path": path}, out)
    return out


def write_file(path: str, content: str) -> dict[str, Any]:
    try:
        target = resolve_jail_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content if content is not None else "", encoding="utf-8")
        out = {"ok": True, "path": str(target), "bytes": target.stat().st_size}
    except Exception as e:
        out = {"ok": False, "error": str(e)}
    _log_tool("write_file", {"path": path, "content_len": len(content or "")}, out)
    return out


def _command_is_disaster(command: str) -> str | None:
    for pat in _DISASTER_PATTERNS:
        if pat.search(command):
            return f"Blocked dangerous pattern: {pat.pattern}"
    # sudo gate
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    if tokens and tokens[0] == "sudo" and not _allow_sudo():
        return "sudo blocked (set AGENT_ALLOW_SUDO=1 to allow)"
    return None


def run_shell(command: str, timeout: int = 30) -> dict[str, Any]:
    """
    Run a shell command with timeout.
    cwd is the workspace so relative paths stay inside the jail by habit.
    """
    reason = _command_is_disaster(command or "")
    if reason:
        out = {"ok": False, "error": reason}
        _log_tool("run_shell", {"command": command}, out)
        return out
    timeout = max(1, min(int(timeout or 30), 120))
    cwd = str(_workspace_root())
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        # Truncate outputs to keep chat payloads small.
        def clip(s: str, n: int = 8000) -> str:
            return s if len(s) <= n else s[:n] + "\n…[truncated]"

        out = {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": clip(proc.stdout or ""),
            "stderr": clip(proc.stderr or ""),
            "cwd": cwd,
        }
        if proc.returncode != 0:
            out["error"] = f"exit {proc.returncode}"
    except subprocess.TimeoutExpired:
        out = {"ok": False, "error": f"Timed out after {timeout}s"}
    except Exception as e:
        out = {"ok": False, "error": str(e)}
    _log_tool("run_shell", {"command": command, "timeout": timeout}, out)
    return out


# Gemini functionDeclarations schema — kept next to implementations.
TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "list_dir",
        "description": "List files and folders under a path (workspace-jail by default).",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to workspace or absolute (if allowed).",
                }
            },
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file from the workspace jail.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write/overwrite a text file inside the workspace jail.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_shell",
        "description": (
            "Run a shell command with timeout. cwd is the workspace. "
            "No sudo unless allowed; dangerous disk wipes are blocked."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "integer", "description": "Seconds, max 120."},
            },
            "required": ["command"],
        },
    },
]

_HANDLERS = {
    "list_dir": lambda a: list_dir(a.get("path") or "."),
    "read_file": lambda a: read_file(a.get("path") or ""),
    "write_file": lambda a: write_file(a.get("path") or "", a.get("content") or ""),
    "run_shell": lambda a: run_shell(a.get("command") or "", a.get("timeout") or 30),
}


def dispatch_tool(name: str, args: dict[str, Any] | None) -> dict[str, Any]:
    handler = _HANDLERS.get(name)
    if not handler:
        out = {"ok": False, "error": f"Unknown tool: {name}"}
        _log_tool(name, args or {}, out)
        return out
    return handler(args or {})
