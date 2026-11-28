#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d "node_modules" ]; then
  echo "Installing W5CDN RadioPlanner dependencies..."
  npm install
fi
exec npm start
