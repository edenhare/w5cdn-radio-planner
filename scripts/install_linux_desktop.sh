#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$APP_DIR/w5cdn-radio-planner.desktop"

chmod +x "$REPO_DIR/start.sh"
mkdir -p "$APP_DIR"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=W5CDN RadioPlanner
Comment=Local Ham Radio Travel Corridor, Proximity & Aviation Codeplug Studio
Exec=$REPO_DIR/start.sh
Path=$REPO_DIR
Icon=$REPO_DIR/src/static/icon.png
Terminal=false
Categories=HamRadio;Utility;Network;
StartupWMClass=w5cdn-radio-planner
EOF

chmod 644 "$DESKTOP_FILE"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

echo "Installed Linux desktop launcher: $DESKTOP_FILE"
