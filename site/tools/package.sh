#!/bin/sh
# Build the two packages in ../dist:
#   saaspocalypsenow-full.zip    the whole site; unzip it and double-click deploy.command
#   saaspocalypsenow-upload.zip  just the page, for Cloudflare's drag-and-drop upload (no live demos)
cd "$(dirname "$0")/.." || exit 1
out="$(cd .. && pwd)/dist"
mkdir -p "$out"
rm -f "$out/saaspocalypsenow-full.zip" "$out/saaspocalypsenow-upload.zip"
stage=$(mktemp -d)
mkdir "$stage/saaspocalypsenow"
rsync -a --exclude node_modules --exclude .wrangler --exclude .dev.vars --exclude .DS_Store ./ "$stage/saaspocalypsenow/"
(cd "$stage" && zip -qr -X "$out/saaspocalypsenow-full.zip" saaspocalypsenow)
(cd public && zip -qr -X "$out/saaspocalypsenow-upload.zip" . -x '.DS_Store' '*/.DS_Store')
rm -rf "$stage"
ls -lh "$out"/saaspocalypsenow-*.zip
