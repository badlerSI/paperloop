#!/bin/bash
# Double-click this file to put SaaSpocalypse Now on Cloudflare, with the live demos.
# It installs the tools, signs you in to Cloudflare in your browser, asks once for the
# website's Claude API key, and deploys. Run it again any time to publish changes.

cd "$(dirname "$0")" || exit 1

title() { printf '\n\033[1;33m%s\033[0m\n' "$*"; }
note() { printf '\033[0;37m%s\033[0m\n' "$*"; }
finish() {
  printf '\n%s\n' "$1"
  read -r -p "Press Return to close this window. " _
  exit "${2:-0}"
}
fail() { printf '\n\033[1;31m%s\033[0m\n' "$*"; finish "Nothing else was changed." 1; }

title "SaaSpocalypse Now → Cloudflare"

if ! command -v node >/dev/null 2>&1; then
  fail "Node.js isn't installed. Get the LTS version from https://nodejs.org, then double-click this file again."
fi
if [ ! -f public/audio/valkyries.mp3 ]; then
  note "public/audio/valkyries.mp3 isn't here, so the Play the score button won't work. Everything else will."
fi

title "1 of 4 · Installing the tools (about a minute the first time)"
npm install --no-audit --no-fund --loglevel=error || fail "Installing the tools failed. Check your internet connection and try again."

title "2 of 4 · Signing in to Cloudflare"
if ! npx wrangler whoami >/dev/null 2>&1; then
  note "A browser window will open. Sign in to Cloudflare and click Allow, then come back here."
  npx wrangler login || fail "Couldn't sign in to Cloudflare."
fi
npx wrangler whoami 2>/dev/null | grep -i -E "logged in|email" | head -2

title "3 of 4 · Publishing the site"
log=$(mktemp)
npx wrangler deploy 2>&1 | tee "$log"
if [ "${PIPESTATUS[0]}" -ne 0 ]; then
  if grep -qiE "zone|custom domain|route" "$log"; then
    note ""
    note "saaspocalypsenow.ai isn't on your Cloudflare account yet, so publishing to a"
    note "workers.dev address for now. Add the domain later (README.md, step 4) and run this again."
    sed -e '/"routes": \[/,/\],/d' -e '/The domain has to be on your Cloudflare account/d' wrangler.jsonc > wrangler.workersdev.jsonc
    npx wrangler deploy --config wrangler.workersdev.jsonc 2>&1 | tee "$log"
    status=${PIPESTATUS[0]}
    rm -f wrangler.workersdev.jsonc
    [ "$status" -eq 0 ] || fail "Publishing failed. The messages above say why."
  else
    fail "Publishing failed. The messages above say why."
  fi
fi
address=$(grep -oE 'https://[a-z0-9.-]+\.workers\.dev' "$log" | head -1)
grep -q "saaspocalypsenow.ai" "$log" && address="https://saaspocalypsenow.ai"
rm -f "$log"

title "4 of 4 · Connecting the demos to Claude"
secrets=$(npx wrangler secret list --format json 2>/dev/null)
if ! printf '%s' "$secrets" | grep -q '"VISITOR_SALT"'; then
  # A random string that scrambles visitors' IP addresses before they're counted.
  openssl rand -hex 24 | npx wrangler secret put VISITOR_SALT >/dev/null && note "Visitor salt set."
fi
if printf '%s' "$secrets" | grep -q '"ANTHROPIC_API_KEY"'; then
  note "The Claude API key is already set. (To change it: npx wrangler secret put ANTHROPIC_API_KEY)"
else
  note "Paste the website's Claude API key and press Return. It won't show on screen."
  note "Make it at platform.claude.com, in a workspace with a monthly spend limit."
  npx wrangler secret put ANTHROPIC_API_KEY || fail "The key wasn't saved. Double-click this file again to retry."
fi

title "Done"
if [ -n "$address" ]; then
  note "Your site: $address"
  note "(A new domain can take a few minutes to start working.)"
  open "$address" 2>/dev/null
fi
finish "Run this file again whenever you change the site."
