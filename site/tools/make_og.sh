#!/bin/sh
# Render the link-preview image from tools/og.html with headless Chrome.
cd "$(dirname "$0")/.." || exit 1
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --allow-file-access-from-files \
  --virtual-time-budget=3000 --window-size=1200,630 \
  --screenshot="$PWD/public/img/og.png" "file://$PWD/tools/og.html"
