"""
Thin loader for the browser chat page (ai_agent/ui/*).

HTML, CSS, and JS live as static files next to this module. server.py serves
GET / and /index.html from load_index(), and /ui/style.css + /ui/app.js from
load_static(). No giant embedded HTML string here.

Imports from: stdlib pathlib only.
Used by: server.py.
"""
from pathlib import Path

# Directory that holds index.html, style.css, app.js
_UI_DIR = Path(__file__).resolve().parent / "ui"

# Content-type map for static assets
_TYPES = {
    "style.css": "text/css; charset=utf-8",
    "app.js": "application/javascript; charset=utf-8",
    "index.html": "text/html; charset=utf-8",
}


def load_index():
    """Return the chat page HTML (UTF-8 text). Links CSS/JS at /ui/…."""
    path = _UI_DIR / "index.html"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return (
            "<!DOCTYPE html><html><body><h1>UI missing</h1>"
            "<p>Expected ai_agent/ui/index.html</p></body></html>"
        )


def load_static(name):
    """Load a static UI file by basename.

    Returns (bytes_or_None, content_type). Only allowlisted names under _UI_DIR
    (no path traversal).
    """
    base = Path(name).name
    if base not in _TYPES:
        return None, "text/plain; charset=utf-8"
    path = _UI_DIR / base
    try:
        return path.read_bytes(), _TYPES[base]
    except OSError:
        return None, _TYPES[base]
