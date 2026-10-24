#!/usr/bin/env bash
# run_ui.sh: start the control room (a local web UI over the real project) and open it in the browser.
#   ./run_ui.sh            then use http://localhost:8765   (Ctrl+C here stops it)
set -euo pipefail
cd "$(dirname "$0")"
PORT="${UI_PORT:-8765}"
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "The control room is already running: http://localhost:$PORT"
  open "http://localhost:$PORT" 2>/dev/null || true
  exit 0
fi
(sleep 1.5; open "http://localhost:$PORT" 2>/dev/null || true) &
exec .venv/bin/python ui_server.py
