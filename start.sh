#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "Error: Python 3.11+ not found. Create a venv with: uv sync" >&2
  exit 1
fi

# Default to chromeless --app-window on Linux so GTK/WebKit2GTK is not required
if [[ $# -eq 0 ]]; then
  exec "$PYTHON_BIN" -m web.desktop --app-window
else
  exec "$PYTHON_BIN" -m web.desktop "$@"
fi
