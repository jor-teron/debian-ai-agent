#!/bin/sh
# Start the agent with a real Python 3.8+.
# Resolves python / python2 / python3 confusion on mixed systems.
# Runs the ai_agent package: python3 -m ai_agent

cd "$(dirname "$0")" || exit 1

echo "·‿·  Starting linux-ai-agent…"

try_cmd() {
  # $1 = command, remaining args optional (e.g. py -3)
  cmd=$1
  shift
  if ! command -v "$cmd" >/dev/null 2>&1; then
    return 1
  fi
  if "$cmd" "$@" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
    echo "Using: $cmd $* ($("$cmd" "$@" -c 'import sys; print(sys.version.split()[0])'))"
    exec "$cmd" "$@" -m ai_agent
  fi
  return 1
}

try_cmd python3 && exit 0
try_cmd python && exit 0
try_cmd py -3 && exit 0

echo "Could not find Python 3.8+."
echo "Tried: python3, python, py -3"
echo "On Debian/Ubuntu:  sudo apt install python3"
echo "Then run:  ./run.sh   or   python3 -m ai_agent"
exit 1
