"""
Gemini REST brain + tool loop.

Uses generateContent over https (httpx) — no heavy Google SDK — to stay
tiny on a ~3.7 Gi machine. Caps chat history so RAM stays predictable.

Model choice: client may pass an allowlisted id (Free Flash vs Paid Pro).
Invalid ids fall back to the free default — see models_catalog.py.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from .models_catalog import DEFAULT_FREE_MODEL, resolve_model
from .tools import TOOL_DECLARATIONS, dispatch_tool

# Keep history short: each turn can include tool payloads.
MAX_HISTORY_MESSAGES = 24
MAX_TOOL_ROUNDS = 6

# Only used if the chosen model 404s — stay within the same “family” when possible.
FALLBACK_FREE = (
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-flash-latest",
)
FALLBACK_PAID = (
    "gemini-2.5-pro",
    "gemini-3.1-pro-preview",
    "gemini-pro-latest",
)

SYSTEM_INSTRUCTION = """You are a helpful personal AI agent running locally on the user's Debian PC.
You can use tools to list/read/write files and run shell commands inside their workspace jail.
Be concise. Prefer tools when the user asks about their files or to do something on disk.
If a tool fails because of the workspace jail, explain that clearly and suggest they can
set AGENT_ALLOW_SYSTEM=1 only if they really want broader access.
Never invent an API key. Never suggest disabling all safety blindly."""


def api_key_set() -> bool:
    return bool((os.environ.get("GEMINI_API_KEY") or "").strip())


def _endpoint(model: str) -> str:
    return (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )


def _trim_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(history) <= MAX_HISTORY_MESSAGES:
        return history
    return history[-MAX_HISTORY_MESSAGES:]


def _extract_text(candidate: dict[str, Any]) -> str:
    parts = (candidate.get("content") or {}).get("parts") or []
    bits = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
    return "\n".join(bits).strip()


def _extract_function_calls(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    parts = (candidate.get("content") or {}).get("parts") or []
    calls = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        fc = p.get("functionCall")
        if fc and fc.get("name"):
            calls.append(fc)
    return calls


async def _generate(
    client: httpx.AsyncClient,
    model: str,
    key: str,
    contents: list[dict[str, Any]],
) -> dict[str, Any]:
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": contents,
        "tools": [{"functionDeclarations": TOOL_DECLARATIONS}],
    }
    r = await client.post(
        _endpoint(model),
        params={"key": key},
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=90.0,
    )
    data = r.json() if r.content else {}
    if r.status_code >= 400:
        err = data.get("error", {})
        msg = err.get("message") if isinstance(err, dict) else str(data)
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {msg}")
    return data


async def chat_once(
    user_message: str,
    history: list[dict[str, Any]] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """
    One user turn: call Gemini, execute any function calls, loop until a
    final text answer (or round/history cap). Returns reply + tool_traces.
    """
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        return {
            "ok": False,
            "reply": (
                "No Gemini API key configured. Open the .env file in this project, "
                "paste your free key from https://aistudio.google.com/apikey into "
                "GEMINI_API_KEY=, save, and restart ./run.sh."
            ),
            "tool_traces": [],
            "error": "missing_api_key",
        }

    chosen, category = resolve_model(model)
    contents: list[dict[str, Any]] = list(_trim_history(history or []))
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    fallbacks = FALLBACK_FREE if category == "free" else FALLBACK_PAID
    models_to_try = [chosen] + [m for m in fallbacks if m != chosen]
    tool_traces: list[dict[str, Any]] = []
    last_error: str | None = None

    async with httpx.AsyncClient() as client:
        for mid in models_to_try:
            try:
                for _round in range(MAX_TOOL_ROUNDS):
                    data = await _generate(client, mid, key, contents)
                    cands = data.get("candidates") or []
                    if not cands:
                        fb = data.get("promptFeedback") or data
                        raise RuntimeError(f"Empty candidates from {mid}: {fb}")
                    cand = cands[0]
                    fcalls = _extract_function_calls(cand)

                    model_content = cand.get("content") or {"role": "model", "parts": []}
                    contents.append(model_content)

                    if not fcalls:
                        reply = _extract_text(cand) or "(No text reply from model.)"
                        return {
                            "ok": True,
                            "reply": reply,
                            "tool_traces": tool_traces,
                            "model": mid,
                            "category": category,
                            "history": _trim_history(contents),
                        }

                    fr_parts = []
                    for fc in fcalls:
                        name = fc.get("name") or ""
                        args = fc.get("args") or {}
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {"raw": args}
                        result = dispatch_tool(name, args if isinstance(args, dict) else {})
                        tool_traces.append(
                            {"tool": name, "args": args, "result": result}
                        )
                        fr_parts.append(
                            {
                                "functionResponse": {
                                    "name": name,
                                    "response": result,
                                }
                            }
                        )
                    contents.append({"role": "user", "parts": fr_parts})

                return {
                    "ok": True,
                    "reply": (
                        "I hit the tool-round limit before finishing. "
                        "Try a simpler request, or check logs/tools.jsonl."
                    ),
                    "tool_traces": tool_traces,
                    "model": mid,
                    "category": category,
                    "history": _trim_history(contents),
                }
            except Exception as e:
                last_error = str(e)
                low = last_error.lower()
                if "not found" in low or "is not supported" in low or "404" in low:
                    continue
                break

    hint = ""
    if category == "paid":
        hint = (
            " Paid/Pro models need a Gemini API key whose Google Cloud project "
            "has billing or Pro access enabled."
        )
    return {
        "ok": False,
        "reply": f"Gemini request failed: {last_error}.{hint}",
        "tool_traces": tool_traces,
        "error": last_error,
        "model": chosen,
        "category": category,
    }
