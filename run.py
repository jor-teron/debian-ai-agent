#!/usr/bin/env python3
"""
Minimal personal AI agent for Debian — launcher.

Starts the HTTP server and a background thread for reminders/jobs.
Stdlib only (no pip / venv / Apache). Local chat page uses HOST/PORT from .env.

Code layout: config.py, tools.py, brain.py, ui.py, server.py, telegram.py, run.py

Imports from: config.py (paths, version, keys), server.py (Handler),
              tools.py (background_loop), telegram.py (optional DM bridge).
Used by: run.sh / systemd (python3 run.py). Nothing imports this file.
"""
import sys
import threading
from http.server import ThreadingHTTPServer

# ---------------------------------------------------------------------------
# Python version gate (clear message on mixed systems)
# ---------------------------------------------------------------------------

# Refuse Python 2 / ancient 3.x early (clear message for mixed systems)
if sys.version_info[0] < 3:
    sys.stderr.write("This app needs Python 3. You ran Python %s.\n" % sys.version.split()[0])
    sys.stderr.write("Try:  python3 run.py   or   ./run.sh\n")
    sys.exit(1)
if sys.version_info < (3, 8):
    sys.stderr.write("Need Python 3.8+. You have %s\n" % sys.version.split()[0])
    sys.stderr.write("Try:  python3 run.py   or   ./run.sh\n")
    sys.exit(1)

from config import ENV_PATH, HOST, PORT, ROOT, WORKSPACE, app_version, default_provider, ensure_ws, keys_status
from server import Handler
from tools import background_loop
from telegram import start_telegram_thread


# ---------------------------------------------------------------------------
# Main: workspace, background thread, HTTP server
# ---------------------------------------------------------------------------


def main():
    """Create the workspace, start reminders/jobs, then serve the chat UI."""
    ensure_ws()
    if not ENV_PATH.exists() and (ROOT / ".env.example").exists():
        print("Tip: copy .env.example to .env and add provider API keys")
    t = threading.Thread(target=background_loop, name="reminders-jobs", daemon=True)
    t.start()
    if start_telegram_thread():
        print("Telegram: on")
    else:
        print("Telegram: off (no token)")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("linux-ai-agent v%s" % app_version())
    print("Workspace: %s" % WORKSPACE)
    print("Default provider: %s" % default_provider())
    if HOST in ("0.0.0.0", "::"):
        print("Open http://127.0.0.1:%s  (this PC)" % PORT)
        print("LAN: http://<this-pc-ip>:%s  (same Wi-Fi; allow firewall TCP %s)" % (PORT, PORT))
    else:
        print("Open http://%s:%s  (Ctrl+C to stop)" % (HOST, PORT))
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
