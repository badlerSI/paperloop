# Paper Loop's website

A one-page pitch with two live demos that run on your Claude API key:

- **Make a worksheet:** a visitor gives a topic and a grade, and Claude writes a one-page worksheet with
  an answer key and, if asked, a version in a home language. It streams onto the page as Claude writes it.
- **Mark an answer:** a visitor writes an answer with a mouse or finger, or photographs one on paper, and
  Claude reads it and comments the way Paper Loop does.

It's one Cloudflare Worker that serves the page from `public/` and the demos from `src/`. Nothing is
stored except a daily count of demos per visitor and the day's spending. Visitors are counted by a salted
hash of their IP address, and those hashes are wiped at midnight UTC.

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

4. **Deploy.**

   ```bash
   npm run deploy
   ```

   Wrangler prints the address, something like `https://paperloop.<your-account>.workers.dev`. Open it and
   try both demos.

5. **Use your own domain (optional).** In the Cloudflare dashboard, open **Workers & Pages → paperloop →
   Settings → Domains & Routes → Add → Custom domain**. The domain has to be on Cloudflare.

## A bot check (optional, recommended once it's shared widely)

The per-visitor limits stop casual overuse, but a script can change IP addresses. Cloudflare Turnstile
adds a free check box that's usually invisible.

1. In the Cloudflare dashboard, open **Turnstile → Add widget**, name it, add your site's hostname, and
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

- **Cloudflare:** Workers & Pages → paperloop → **Logs**. Each demo writes one line such as
  `{"demo":"mark","model":"claude-sonnet-5-5","stop":"end_turn","input":2033,"output":182,"usd":0.00589}`.
  Nothing a visitor typed or drew is logged, and Cloudflare's own per-request logs are switched off in
  `wrangler.jsonc` (`invocation_logs: false`), so the logs hold no addresses either.
- **Claude Console:** the workspace's usage page shows the real bill.

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
| `wrangler.jsonc` | Cloudflare settings and the limits |
