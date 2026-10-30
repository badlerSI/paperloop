# SaaSpocalypse Now

The website at [saaspocalypsenow.ai](https://saaspocalypsenow.ai): the case that the ed tech subscription
is finished, dressed as a 1970s war-movie poster, with two live demos of Paper Loop that run on your Claude
API key:

- **Make a worksheet:** a visitor gives a topic and a grade, and Claude writes a one-page worksheet with
  an answer key and, if asked, a version in a home language. It streams onto the page as Claude writes it.
- **Mark an answer:** a visitor writes an answer with a mouse or finger, or photographs one on paper, and
  Claude reads it and comments the way Paper Loop does.

It's one Cloudflare Worker that serves the page from `public/` and the demos from `src/`. Nothing is
stored except a daily count of demos per visitor and the day's spending. Visitors are counted by a salted
hash of their IP address, and those hashes are wiped at midnight UTC.

## The quick way

**Upload it, demos included.** No command line needed.

1. In the Cloudflare dashboard, open **Workers & Pages → Create → Pages → Upload assets**, name the
   project `saaspocalypsenow`, drop in `saaspocalypsenow-upload.zip` (zipped, as it is), and deploy. The
   page works right away; the demo area says the demos are switched off until the next step.
2. In the project, open **Settings → Variables and Secrets** and add one, for Production: type
   **Secret**, name `ANTHROPIC_API_KEY`, value your Claude API key. Save.
3. Settings only reach new deployments, so open **Deployments → Create deployment** and drop in the same
   zip again. The demos now work.
4. Add the domain under **Custom domains**: `saaspocalypsenow.ai`.

The zip carries the demo server as `_worker.js`. A plain upload can't create the Durable Object that
holds the strict daily limits, so on this path the per-visitor and daily caps are kept in each server's
memory and are only approximate. The real cap is the key: its credit balance, or a workspace spend limit
in the Claude Console. If **auto-reload** is on in the Console's billing settings, turn it off so the
demos stop when the credit runs out instead of buying more.

**From GitHub, with strict limits and a redeploy on every push:** in the Cloudflare dashboard, open the
`saaspocalypsenow` Worker (or create one with that name; it must match `name` in `wrangler.jsonc`), go to
**Settings → Builds → Connect**, pick `badlerSI/paperloop`, set the root directory to `site` and the
production branch to `day-3`, and save. Then add the `ANTHROPIC_API_KEY` secret under **Settings →
Variables and Secrets**. The first build attaches saaspocalypsenow.ai and www, so remove the domain from
any other project first.

**From your computer, with strict limits:** double-click `deploy.command` in this folder (or in the
unzipped `saaspocalypsenow-full.zip`). It installs what it needs, opens your browser to sign in to
Cloudflare, publishes the site, and asks once for the API key. If saaspocalypsenow.ai isn't on your
Cloudflare account yet, it publishes to a `workers.dev` address instead and tells you. It needs Node.js
([nodejs.org](https://nodejs.org), the LTS version).

`tools/package.sh` rebuilds both zips into the project's `dist` folder.

## What it costs

Measured on October 29, 2026 with Claude Sonnet 5.5:

| Demo | About |
| --- | --- |
| Mark one answer | $0.006 |
| Make a worksheet | $0.015 |
| Make a worksheet with a home-language version | $0.025 |

Three limits keep the bill small. Change any of them in `wrangler.jsonc` and deploy again:

- `DAILY_BUDGET_USD` (default **$5**): the most all visitors together can spend in a day. Each request
  reserves its worst case first ($0.09 for a worksheet, $0.03 for a marking), so the cap holds even when
  many arrive at once. When the day's budget is gone, the page says so until midnight UTC.
- `WORKSHEETS_PER_VISITOR` (3) and `MARKS_PER_VISITOR` (8): per IP address, per day.
- `DEMOS`: set to `"off"` to turn both demos off.

At $5 a day the worst case is about $150 a month. Also set a spend limit on the API key itself (step 2
below), so a mistake here can't run up a bill.

## Deploy it

You need a free Cloudflare account and Node.js. Commands run from this `site` folder.

1. **Install and sign in to Cloudflare.**

   ```bash
   npm install
   ```

   ```bash
   npx wrangler login
   ```

2. **Make an API key just for the website.** In the [Claude Console](https://platform.claude.com),
   create a workspace (for example "Website demos"), give it a monthly spend limit (such as $50), and
   create an API key in it. A separate key means you can turn the site off without touching anything else.

3. **Give the Worker its secrets.** Each command asks you to paste the value; it's never written to a file.

   ```bash
   npx wrangler secret put ANTHROPIC_API_KEY
   ```

   For the second one, paste any long random string. It scrambles visitors' IP addresses before they're
   counted. (If you skip it, the API key is used instead.)

   ```bash
   npx wrangler secret put VISITOR_SALT
   ```

4. **Put saaspocalypsenow.ai on Cloudflare.** `wrangler.jsonc` serves the site at `saaspocalypsenow.ai`
   and `www.saaspocalypsenow.ai`, so the domain has to be on your Cloudflare account first. In the
   dashboard, choose **Add a domain**, enter `saaspocalypsenow.ai`, and pick the Free plan. Cloudflare gives
   you two nameservers: at the company you registered the domain with, replace its nameservers with those
   two. When the dashboard shows the domain as **Active** (often within an hour), go on.

5. **Deploy.**

   ```bash
   npm run deploy
   ```

   Wrangler sets up both addresses and their certificates. It also prints a backup address, something
   like `https://saaspocalypsenow.<your-account>.workers.dev`. Open the site and try both demos.

## A bot check (optional, recommended once it's shared widely)

The per-visitor limits stop casual overuse, but a script can change IP addresses. Cloudflare Turnstile
adds a free check box that's usually invisible.

1. In the Cloudflare dashboard, open **Turnstile → Add widget**, name it, add `saaspocalypsenow.ai`, and
   choose **Managed**.
2. Put the **site key** in `wrangler.jsonc` as `TURNSTILE_SITE_KEY`.
3. Store the **secret key**:

   ```bash
   npx wrangler secret put TURNSTILE_SECRET
   ```

4. Deploy again with `npm run deploy`. The demos now ask for the check before each call.

## Run it on your own computer

Copy `.dev.vars.example` to `.dev.vars`, paste a key into it (it's gitignored), then:

```bash
npm run dev
```

The site runs at <http://localhost:8787>, with the same limits, and spends real API credit.

## Watching what it spends

- **Cloudflare:** Workers & Pages → saaspocalypsenow → **Logs**. Each demo writes one line such as
  `{"demo":"mark","model":"claude-sonnet-5-5","stop":"end_turn","input":2033,"output":182,"usd":0.00589}`.
  Nothing a visitor typed or drew is logged, and Cloudflare's own per-request logs are switched off in
  `wrangler.jsonc` (`invocation_logs: false`), so the logs hold no addresses either.
- **Claude Console:** the workspace's usage page shows the real bill.

## The look and the score

- **The poster** is original art in the style of the 1979 film's poster, not a copy of it: the sun setting
  on ed tech, real lines of Paper Loop's code drifting across it like clouds, and paper airplanes flying
  off ahead of the dark. `tools/make_art.py` draws it (and the jungle strip and the title's worn-ink
  mask). The code lines are listed at the top of that script, and it stops with an error if one of them
  is no longer in Paper Loop's source. The footer says the site is a parody with no connection to the
  film.
- **The share image** (`public/img/og.png`) is rendered from `tools/og.html` by `tools/make_og.sh`, which
  needs Google Chrome.
- **The score** is `public/audio/valkyries.mp3`, made from your licensed `valkyries.wav`:

  ```bash
  ffmpeg -i valkyries.wav -codec:a libmp3lame -q:a 3 -map_metadata -1 public/audio/valkyries.mp3
  ```

  It plays only when a visitor presses **Play the score**, never on its own. Anyone can download a file a
  website plays, so check that your license covers streaming on a public site, and put the artist's
  credit in the footer if the license asks for one.

  The MP3 is in the repository, so a GitHub deploy includes it, and it becomes public when the
  repository does.

## Before you share the link

- **Make the GitHub repository public.** The page links to `github.com/badlerSI/paperloop`, which is
  private for now, so those links show a 404 to everyone else.
- **Read the page's claims about you.** "Three days" comes from the git history (October 26–28), "under
  $50 of a monthly plan" is your figure, and the "Who built it" section comes from The Oaklandside and The
  74 articles linked on badler.ai. Change anything that isn't how you'd say it.
- **The hero image** is the marked "Water's Wild Ride" test page from the day-2 handwriting run (ID 3158).
  To use a different page, replace `public/img/marked-page.webp` and `.jpg`, and move the numbered pins in
  `styles.css` (`.pin-1` to `.pin-5`).
- The sample PDFs in `public/samples/` still have QR codes pointing at the GitHub README. To point them at
  the site instead, run `devtools/samples.py --url <your site>` in the main project and copy the PDFs here.

## If something goes wrong

- **Error 1102, or "exceeded CPU" in the logs:** the free Workers plan allows 10 ms of computing per
  request. Waiting for Claude doesn't count, but a large photo might. The $5-a-month Workers Paid plan
  raises the limit.
- **"The demos are switched off for now":** `DEMOS` is `"off"`, or the `ANTHROPIC_API_KEY` secret is
  missing.
- **Models:** `WORKSHEET_MODEL` and `MARK_MODEL` in `wrangler.jsonc`. If you switch to a model the
  Worker doesn't have a price for, it budgets as if every token cost the most of any model, so the daily
  cap only gets stricter. Prices live in `PRICES` in `src/worker.ts`.

## Files

| File | What it is |
| --- | --- |
| `public/index.html`, `styles.css`, `app.js` | The page and the demos' browser side |
| `public/_headers` | Security headers for the page |
| `src/worker.ts` | The demos, the checks on every request, and the cost accounting |
| `src/limiter.ts` | The Durable Object that holds the day's counts and spending |
| `src/prompts.ts` | What Claude is told for each demo, the answer formats, and the sample questions |
| `wrangler.jsonc` | Cloudflare settings, the domain, and the limits |
| `public/img/poster.svg`, `jungle.svg`, `grit.png`, `og.png` | The poster art and the share image |
| `public/audio/valkyries.mp3` | The score |
| `tools/make_art.py`, `tools/og.html`, `tools/make_og.sh` | What draws the art and renders the share image |
| `deploy.command` | Double-click to publish the whole site |
| `tools/package.sh` | Builds the full and upload-only zips |
