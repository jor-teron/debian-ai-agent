#!/usr/bin/env python3
"""
Minimal personal AI agent for Debian — launcher.

Starts the HTTP server and a background thread for reminders/jobs.
Stdlib only (no pip / venv / Apache). Local chat page uses HOST/PORT from .env.

Package entry via python3 -m ai_agent (see __main__.py).

Imports from: ai_agent.config, server, tools, telegram.
Used by: run.sh / systemd / python3 -m ai_agent.
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

from ai_agent.config import ENV_PATH, HOST, PORT, ROOT, WORKSPACE, app_version, default_provider, ensure_ws, keys_status
from ai_agent.server import Handler
from ai_agent.tools import background_loop
from ai_agent.telegram import start_telegram_thread


# ---------------------------------------------------------------------------
# Main: workspace, background thread, HTTP server
# ---------------------------------------------------------------------------


def main(argv=None):
    """Create the workspace, start reminders/jobs, then serve the chat UI.

    argv: optional CLI args (defaults to sys.argv[1:]). --help / -h prints
    a short usage line and returns without binding the port.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in args):
        print("linux-ai-agent — local chat agent (stdlib only)")
        print("Usage: python3 -m ai_agent")
        print("       ./run.sh")
        print("Env:   .env next to run.sh (see .env.example)")
        return
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
