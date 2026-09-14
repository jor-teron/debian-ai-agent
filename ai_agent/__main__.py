"""
Entry point for `python3 -m ai_agent`.

Starts the HTTP server (and optional Telegram bridge) via run.main().
"""
from ai_agent.run import main

if __name__ == "__main__":
    main()
