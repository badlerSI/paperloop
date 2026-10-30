#!/bin/sh
# Build the two packages in ../dist:
#   saaspocalypsenow-upload.zip  for Cloudflare Pages' drag-and-drop upload: the page plus the demo
#                                server as _worker.js. Add the API key in the project's settings.
#   saaspocalypsenow-full.zip    the whole site; unzip it and double-click deploy.command
cd "$(dirname "$0")/.." || exit 1
out="$(cd .. && pwd)/dist"
mkdir -p "$out"
rm -f "$out/saaspocalypsenow-full.zip" "$out/saaspocalypsenow-upload.zip"
stage=$(mktemp -d)

# The demo server, bundled into one file the way Cloudflare Pages runs it.
npx wrangler deploy --dry-run --minify --outdir "$stage/build" >/dev/null 2>&1 || { echo "Bundling the Worker failed"; exit 1; }
mkdir "$stage/upload"
rsync -a --exclude .DS_Store public/ "$stage/upload/"
cp "$stage/build/worker.js" "$stage/upload/_worker.js"
# Only the page and the demo API go through the Worker; everything else is served as a plain file.
printf '{\n  "version": 1,\n  "include": ["/", "/index.html", "/api/*"],\n  "exclude": []\n}\n' > "$stage/upload/_routes.json"
(cd "$stage/upload" && zip -qr -X "$out/saaspocalypsenow-upload.zip" .)

mkdir "$stage/saaspocalypsenow"
rsync -a --exclude node_modules --exclude .wrangler --exclude .dev.vars --exclude .DS_Store ./ "$stage/saaspocalypsenow/"
(cd "$stage" && zip -qr -X "$out/saaspocalypsenow-full.zip" saaspocalypsenow)

rm -rf "$stage"
ls -lh "$out"/saaspocalypsenow-*.zip
