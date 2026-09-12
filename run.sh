#!/usr/bin/env bash
# Start the personal AI agent on localhost only.
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -d .venv ]]; then
  echo "Missing .venv — run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
# Load .env into the process (uvicorn child inherits env; python-dotenv also loads it)
set -a
[[ -f .env ]] && . ./.env
set +a
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8787}"
exec .venv/bin/uvicorn app.server:app --host "$HOST" --port "$PORT"
