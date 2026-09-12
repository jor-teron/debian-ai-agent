"""
Localhost-only HTTP front-end for the personal AI agent.

Binds 127.0.0.1 by default so the chat UI is not reachable from other
devices on the network. Serves static chat UI + JSON API.

POST /api/chat accepts optional {"model": "<allowlisted-id>"}; see models_catalog.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import brain
from .models_catalog import public_catalog, resolve_model

# Load .env from project root before reading config.
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

# In-memory history per process — tiny; cleared on restart. Cap in brain.
_SESSION_HISTORY: list = []


async def health(_: Request) -> JSONResponse:
    default_model, default_cat = resolve_model(None)
    return JSONResponse(
        {
            "ok": True,
            "api_key_set": brain.api_key_set(),
            "host": os.environ.get("HOST", "127.0.0.1"),
            "workspace": os.environ.get("WORKSPACE", "/home/user/agent-workspace"),
            "default_model": default_model,
            "default_category": default_cat,
        }
    )


async def models(_: Request) -> JSONResponse:
    """UI loads Free/Paid dropdowns from this allowlist."""
    return JSONResponse(public_catalog())


async def chat(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400)
    message = (body.get("message") or "").strip()
    if not message:
        return JSONResponse({"ok": False, "error": "message is required"}, status_code=400)

    # Optional model override — validated/allowlisted inside resolve_model.
    requested_model = body.get("model")
    if requested_model is not None and not isinstance(requested_model, str):
        requested_model = None

    global _SESSION_HISTORY
    result = await brain.chat_once(
        message, history=_SESSION_HISTORY, model=requested_model
    )
    if result.get("history") is not None:
        _SESSION_HISTORY = result["history"]
    return JSONResponse(
        {
            "ok": result.get("ok", False),
            "reply": result.get("reply", ""),
            "tool_traces": result.get("tool_traces") or [],
            "error": result.get("error"),
            "model": result.get("model"),
            "category": result.get("category"),
            "api_key_set": brain.api_key_set(),
        }
    )


routes = [
    Route("/api/health", health, methods=["GET"]),
    Route("/api/models", models, methods=["GET"]),
    Route("/api/chat", chat, methods=["POST"]),
    Mount(
        "/",
        app=StaticFiles(directory=str(Path(__file__).parent / "static"), html=True),
        name="static",
    ),
]

app = Starlette(routes=routes)
