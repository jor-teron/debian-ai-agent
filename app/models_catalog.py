"""
Allowlisted Gemini model ids grouped for the UI.

Free = default everyday use (Flash / Flash-Lite).
Paid = stronger Pro models — need a key/project with paid or Pro access.
Unknown ids from the client are rejected; we fall back to the free default.
"""

from __future__ import annotations

import os
from typing import Any

# Labels shown in the chat UI dropdowns.
FREE_MODELS: list[dict[str, str]] = [
    {
        "id": "gemini-3.5-flash-lite",
        "label": "3.5 Flash-Lite (default, most free requests)",
    },
    {"id": "gemini-3.5-flash", "label": "3.5 Flash"},
    {"id": "gemini-3.6-flash", "label": "3.6 Flash"},
    {"id": "gemini-2.5-flash", "label": "2.5 Flash"},
    {"id": "gemini-flash-latest", "label": "Flash latest (alias)"},
]

PAID_MODELS: list[dict[str, str]] = [
    {"id": "gemini-2.5-pro", "label": "2.5 Pro (strong reasoning)"},
    {"id": "gemini-3.1-pro-preview", "label": "3.1 Pro Preview"},
    {"id": "gemini-pro-latest", "label": "Pro latest (alias)"},
]

DEFAULT_FREE_MODEL = "gemini-3.5-flash-lite"

_FREE_IDS = {m["id"] for m in FREE_MODELS}
_PAID_IDS = {m["id"] for m in PAID_MODELS}
ALL_ALLOWED = _FREE_IDS | _PAID_IDS


def category_for(model_id: str) -> str | None:
    if model_id in _FREE_IDS:
        return "free"
    if model_id in _PAID_IDS:
        return "paid"
    return None


def resolve_model(requested: str | None) -> tuple[str, str]:
    """
    Return (model_id, category). Invalid/missing → env default or free Flash.
    """
    env_default = (os.environ.get("GEMINI_MODEL") or DEFAULT_FREE_MODEL).strip()
    # Env default must still be allowlisted; else hard-default free.
    if env_default not in ALL_ALLOWED:
        env_default = DEFAULT_FREE_MODEL

    cand = (requested or "").strip() or env_default
    if cand not in ALL_ALLOWED:
        cand = env_default
    return cand, category_for(cand) or "free"


def public_catalog() -> dict[str, Any]:
    return {
        "default": resolve_model(None)[0],
        "free": FREE_MODELS,
        "paid": PAID_MODELS,
    }
