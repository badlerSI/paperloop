import Anthropic from "@anthropic-ai/sdk";
import { zodOutputFormat } from "@anthropic-ai/sdk/helpers/zod";
import { z } from "zod";
import { Limiter, MemoryLedger, type Caps, type Kind, type Left, type Reservation } from "./limiter";
import {
  LANGUAGES,
  MARK_SYSTEM,
  MarkSchema,
  PAGE_SYSTEM,
  PageSchema,
  QUESTIONS,
  WORKSHEET_SYSTEM,
  WorksheetSchema,
} from "./prompts";
// Written by devtools/samples.py from the Paper Loop skill's sample worksheets.
import SAMPLES from "./samples.json";

export { Limiter };

interface Env {
  ASSETS: Fetcher;
  // Missing on a plain upload to Cloudflare Pages; see MemoryLedger.
  LIMITER?: DurableObjectNamespace<Limiter>;
  ANTHROPIC_API_KEY?: string;
  // Set in wrangler.jsonc. A plain upload to Cloudflare Pages has none of them, so each has a default.
  // Add DEMOS = off in the dashboard to switch the demos off; keep_vars keeps it across deploys.
  DEMOS?: string;
  WORKSHEET_MODEL?: string;
  MARK_MODEL?: string;
  DAILY_BUDGET_USD?: string;
  WORKSHEETS_PER_VISITOR?: string;
  MARKS_PER_VISITOR?: string;
  PAGES_PER_VISITOR?: string;
  TURNSTILE_SITE_KEY?: string;
  TURNSTILE_SECRET?: string;
  VISITOR_SALT?: string;
}

// Dollars per million input and output tokens; thinking is billed as output. A model missing here is
// priced as the dearest one, so a typo in wrangler.jsonc can only make the budget stricter.
const PRICES: Record<string, [number, number]> = {
  "claude-haiku-5-5": [0.1, 0.5],
  "claude-sonnet-5-5": [2, 10],
  "claude-opus-5-5": [4, 20],
};

// Worst cases for the budget. A marking's input is at most a 1600 x 1600 picture (about 3,400 tokens)
// plus the instructions and answer format.
const LIMITS = {
  worksheet: { maxTokens: 8000, inputTokens: 4000 },
  mark: { maxTokens: 2000, inputTokens: 6000 },
  // A whole page: a 1600 x 1600 picture, the instructions, and every sample's key.
  page: { maxTokens: 3000, inputTokens: 10000 },
};

const BODY_MAX = 900_000;
const IMAGE_SIDE_MAX = 1600;

// The answer formats, built once. They go to the API as plain JSON schemas, and the reply is checked
// here after its stop reason, so a cut-off or refused answer is never mistaken for a broken one.
function jsonFormat(schema: z.ZodType) {
  const { type, schema: json } = zodOutputFormat(schema);
  return { type, schema: json };
}
const WORKSHEET_FORMAT = jsonFormat(WorksheetSchema);
const MARK_FORMAT = jsonFormat(MarkSchema);
const PAGE_FORMAT = jsonFormat(PageSchema);

type Sample = (typeof SAMPLES)[keyof typeof SAMPLES];
const SAMPLE_IDS = Object.keys(SAMPLES) as (keyof typeof SAMPLES)[];

const DEFAULT_MODEL = "claude-sonnet-5-5";

function models(env: Env): { worksheet: string; mark: string } {
  return { worksheet: env.WORKSHEET_MODEL || DEFAULT_MODEL, mark: env.MARK_MODEL || DEFAULT_MODEL };
}

function price(model: string): [number, number] {
  return PRICES[model] ?? [10, 50];
}

function worstCase(kind: Kind, model: string): number {
  const [inp, out] = price(model);
  return (LIMITS[kind].inputTokens * inp + LIMITS[kind].maxTokens * out) / 1e6;
}

function cost(model: string, usage: Anthropic.Usage): number {
  const [inp, out] = price(model);
  const input =
    usage.input_tokens + (usage.cache_creation_input_tokens ?? 0) * 1.25 + (usage.cache_read_input_tokens ?? 0) * 0.1;
  return (input * inp + usage.output_tokens * out) / 1e6;
}

// One line per demo in the Worker's logs, for checking what the demos cost. No content, no visitor.
function logUsage(demo: Kind, model: string, usage: Anthropic.Usage, usd: number, stop: string | null): void {
  console.log(
    JSON.stringify({ demo, model, stop, input: usage.input_tokens, output: usage.output_tokens, usd: Number(usd.toFixed(5)) }),
  );
}

function caps(env: Env): Caps {
  const num = (v: string | undefined, d: number) => (v && Number.isFinite(Number(v)) ? Number(v) : d);
  return {
    worksheet: num(env.WORKSHEETS_PER_VISITOR, 3),
    mark: num(env.MARKS_PER_VISITOR, 8),
    page: num(env.PAGES_PER_VISITOR, 3),
    budgetUsd: num(env.DAILY_BUDGET_USD, 5),
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

function sorry(message: string, status: number, left?: Left): Response {
  return json({ error: message, left }, status);
}

// IPv6 visitors are counted by their /64 network, since one household can rotate through the rest.
function network(ip: string): string {
  const mapped = ip.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/i);
  if (mapped) return mapped[1];
  if (!ip.includes(":")) return ip;
  const [head, tail = ""] = ip.split("::");
  const a = head ? head.split(":") : [];
  const b = tail ? tail.split(":") : [];
  const full = [...a, ...Array(Math.max(0, 8 - a.length - b.length)).fill("0"), ...b];
  return full.slice(0, 4).map((g) => g.toLowerCase().replace(/^0+(?=.)/, "")).join(":") + "::/64";
}

// Without VISITOR_SALT the API key is the salt: it's just as secret, so the hashes still can't be
// reversed by trying every address.
async function visitor(req: Request, env: Env): Promise<string> {
  const ip = network(req.headers.get("CF-Connecting-IP") ?? "local");
  const salt = env.VISITOR_SALT || env.ANTHROPIC_API_KEY || "paper-loop";
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${salt}|${ip}`)));
  return [...digest.slice(0, 12)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Browsers always send Origin on a POST. This stops other websites from spending the budget through
// their visitors' browsers; scripts can fake it, which is what Turnstile and the budget are for.
function sameOrigin(req: Request, url: URL): boolean {
  const origin = req.headers.get("Origin");
  if (origin) return origin === url.origin;
  return req.headers.get("Sec-Fetch-Site") === "same-origin";
}

function turnstileOn(env: Env): boolean {
  return !!(env.TURNSTILE_SECRET && env.TURNSTILE_SITE_KEY);
}

async function human(token: string | undefined, req: Request, env: Env): Promise<boolean> {
  if (!turnstileOn(env)) return true;
  if (!token) return false;
  const res = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ secret: env.TURNSTILE_SECRET, response: token }),
  });
  const out = await res.json<{ success?: boolean }>();
  return out.success === true;
}

type Ledger = {
  status(visitor: string, caps: Caps, probe: number): Promise<Left>;
  reserve(visitor: string, kind: Kind, cost: number, caps: Caps, floor: number): Promise<Reservation>;
  settle(visitor: string, kind: Kind, day: string, reserved: number, actual: number, refund: boolean): Promise<void>;
};

const memory = new MemoryLedger();

function limiter(env: Env): Ledger {
  if (!env.LIMITER) return memory;
  return env.LIMITER.get(env.LIMITER.idFromName("demos")) as unknown as Ledger;
}

function demosOn(env: Env): boolean {
  return env.DEMOS !== "off" && !!env.ANTHROPIC_API_KEY;
}

// No automatic retries: a retry could bill tokens the reservation didn't cover.
function client(env: Env): Anthropic {
  return new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, maxRetries: 0, timeout: 120_000 });
}

type Failure = { message: string; status: number; refund: boolean; actual: number };

// What to tell the visitor when a call fails, what it cost, and whether they get the demo back. Only
// failures a visitor can't cause on purpose are refunded, so refunds can't be farmed for free calls.
function failure(err: unknown, reserved: number): Failure {
  const busy = "Claude is busy right now. Try again in a minute; this one didn't count.";
  if (err instanceof Anthropic.APIUserAbortError) {
    return { message: "Stopped.", status: 499, refund: false, actual: reserved };
  }
  if (err instanceof Anthropic.APIConnectionTimeoutError) {
    // A visitor can make a call run long on purpose (a page crammed with writing), so this isn't refunded.
    return { message: "That took too long and was stopped. Try a clearer picture with less on it.", status: 504, refund: false, actual: reserved };
  }
  if (err instanceof Anthropic.APIConnectionError) {
    // Tokens may have been billed, so the budget keeps the reservation.
    return { message: busy, status: 504, refund: true, actual: reserved };
  }
  if (err instanceof Anthropic.APIError) {
    const s = err.status ?? 0;
    if (s === 429 || s >= 500) return { message: busy, status: 503, refund: true, actual: 0 };
    if (s === 401 || s === 403) {
      return { message: "The demos aren't set up right. Please try again later.", status: 503, refund: true, actual: 0 };
    }
    return {
      message: "Claude couldn't use that. Try a clearer picture or a different topic.",
      status: 422,
      refund: false,
      actual: 0,
    };
  }
  return {
    message: "Something went wrong on our side. Try again in a minute; this one didn't count.",
    status: 500,
    refund: true,
    actual: reserved,
  };
}

function readJSON<T>(message: Anthropic.Message, schema: z.ZodType<T>): T | null {
  const text = message.content.map((b) => (b.type === "text" ? b.text : "")).join("");
  try {
    const out = schema.safeParse(JSON.parse(text));
    return out.success ? out.data : null;
  } catch {
    return null;
  }
}

const WorksheetRequest = z.object({
  topic: z.string().trim().min(2).max(160),
  grade: z.number().int().min(2).max(12),
  language: z.enum(LANGUAGES as [string, ...string[]]).nullable().optional(),
  token: z.string().max(4096).optional(),
});

const MarkRequest = z.object({
  question: z.string().max(20),
  custom: z
    .object({
      prompt: z.string().trim().min(3).max(300),
      key: z.string().trim().min(1).max(300),
      grade: z.number().int().min(2).max(12),
      spelling: z.boolean(),
    })
    .optional(),
  image: z
    .string()
    .max(BODY_MAX - 2000)
    .regex(/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/),
  token: z.string().max(4096).optional(),
});

function gradeName(g: number): string {
  const suffix = g === 2 ? "nd" : g === 3 ? "rd" : "th";
  return `${g}${suffix} grade`;
}

// Read at most BODY_MAX bytes, even from a request with no Content-Length.
async function readBody(req: Request): Promise<unknown | null> {
  if (Number(req.headers.get("content-length") ?? 0) > BODY_MAX || !req.body) return null;
  const reader = req.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > BODY_MAX) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const all = new Uint8Array(size);
  let at = 0;
  for (const c of chunks) {
    all.set(c, at);
    at += c.byteLength;
  }
  try {
    return JSON.parse(new TextDecoder().decode(all));
  } catch {
    return null;
  }
}

type Picture = { mediaType: "image/png" | "image/jpeg" | "image/webp"; width: number; height: number };

// The picture's real type and size, from its first bytes. The page sends a drawing 900 wide or a photo
// at most 1600 on its longest side, re-encoded in the browser, so the size is always near the start.
function picture(base64: string): Picture | null {
  let b: Uint8Array;
  try {
    const head = atob(base64.slice(0, 87_384));
    b = Uint8Array.from(head, (c) => c.charCodeAt(0));
  } catch {
    return null;
  }
  const u16 = (i: number) => (b[i] << 8) | b[i + 1];
  const u32 = (i: number) => ((b[i] << 24) | (b[i + 1] << 16) | (b[i + 2] << 8) | b[i + 3]) >>> 0;
  const ascii = (i: number, n: number) => String.fromCharCode(...b.slice(i, i + n));
  if (b.length > 24 && u32(0) === 0x89504e47) {
    return { mediaType: "image/png", width: u32(16), height: u32(20) };
  }
  if (b.length > 4 && b[0] === 0xff && b[1] === 0xd8) {
    let i = 2;
    while (i + 9 < b.length) {
      if (b[i] !== 0xff) {
        i++;
        continue;
      }
      const m = b[i + 1];
      // Start-of-frame markers carry the size; C4, C8 and CC are other segments.
      if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) {
        return { mediaType: "image/jpeg", width: u16(i + 7), height: u16(i + 5) };
      }
      if (m === 0xff) {
        i += 1;
        continue;
      }
      if (m === 0xd8 || m === 0x01 || (m >= 0xd0 && m <= 0xd7)) {
        i += 2;
        continue;
      }
      i += 2 + u16(i + 2);
    }
    return null;
  }
  if (b.length > 30 && ascii(0, 4) === "RIFF" && ascii(8, 4) === "WEBP") {
    const chunk = ascii(12, 4);
    if (chunk === "VP8 ") {
      return { mediaType: "image/webp", width: (b[26] | (b[27] << 8)) & 0x3fff, height: (b[28] | (b[29] << 8)) & 0x3fff };
    }
    if (chunk === "VP8L") {
      return {
        mediaType: "image/webp",
        width: 1 + (((b[22] & 0x3f) << 8) | b[21]),
        height: 1 + (((b[24] & 0x0f) << 10) | (b[23] << 2) | ((b[22] & 0xc0) >> 6)),
      };
    }
    if (chunk === "VP8X") {
      return {
        mediaType: "image/webp",
        width: 1 + (b[24] | (b[25] << 8) | (b[26] << 16)),
        height: 1 + (b[27] | (b[28] << 8) | (b[29] << 16)),
      };
    }
  }
  return null;
}

function refused(reason: "visitor" | "budget", kind: Kind, left: Left): Response {
  if (reason === "visitor") {
    return sorry("That's all of those for today from this connection. They reset at midnight UTC.", 429, left);
  }
  // "open" says whether the cheapest demo, one answer, still fits today.
  if (kind !== "mark" && left.open) {
    const what = kind === "worksheet" ? "worksheets" : "whole-page markings";
    return sorry(`Today's free ${what} are used up. Marking one answer still works.`, 429, left);
  }
  return sorry("Today's free demos are used up. They reset at midnight UTC.", 429, left);
}

async function config(req: Request, env: Env): Promise<Response> {
  const on = demosOn(env);
  const left = on
    ? await limiter(env).status(await visitor(req, env), caps(env), worstCase("mark", models(env).mark))
    : { worksheet: 0, mark: 0, page: 0, open: false };
  return json({
    demos: on,
    turnstile: turnstileOn(env) ? env.TURNSTILE_SITE_KEY : null,
    left,
    questions: QUESTIONS,
    samples: SAMPLE_IDS.map((id) => ({ id, title: SAMPLES[id].title, grade: SAMPLES[id].grade, shows: SAMPLES[id].shows })),
    languages: LANGUAGES,
  });
}

async function worksheet(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const parsed = WorksheetRequest.safeParse(await readBody(req));
  if (!parsed.success) return sorry("Give a topic (up to 160 characters) and a grade from 2 to 12.", 400);
  const { topic, grade, language, token } = parsed.data;
  if (!(await human(token, req, env))) return sorry("Please finish the check box first.", 403);

  const model = models(env).worksheet;
  const who = await visitor(req, env);
  const reserved = worstCase("worksheet", model);
  const booking = await limiter(env).reserve(who, "worksheet", reserved, caps(env), worstCase("mark", models(env).mark));
  if (!booking.ok) return refused(booking.reason, "worksheet", booking.left);

  const ask = [
    `Topic: ${JSON.stringify(topic)}`,
    `Grade: ${gradeName(grade)}`,
    language ? `Also make a version in ${language}.` : "No home-language version.",
  ].join("\n");

  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
  const writer = writable.getWriter();
  const encoder = new TextEncoder();
  let stream: ReturnType<Anthropic["messages"]["stream"]> | null = null;
  let gone = false;
  const send = async (event: object) => {
    if (gone) return;
    try {
      await writer.write(encoder.encode(JSON.stringify(event) + "\n"));
    } catch {
      // The visitor left: stop paying for tokens nobody will read.
      gone = true;
      stream?.abort();
    }
  };

  ctx.waitUntil(
    (async () => {
      let actual = reserved;
      let refund = false;
      let last: object;
      try {
        stream = client(env).messages.stream({
          model,
          max_tokens: LIMITS.worksheet.maxTokens,
          system: WORKSHEET_SYSTEM,
          output_config: { effort: "low", format: WORKSHEET_FORMAT },
          messages: [{ role: "user", content: ask }],
        });
        let planning = false;
        stream.on("thinking", () => {
          if (!planning) {
            planning = true;
            void send({ t: "phase", v: "planning" });
          }
        });
        stream.on("text", (delta: string) => void send({ t: "text", v: delta }));
        await send({ t: "start", left: booking.left });

        const message = await stream.finalMessage();
        actual = cost(model, message.usage);
        logUsage("worksheet", model, message.usage, actual, message.stop_reason);
        const sheet = message.stop_reason === "end_turn" ? readJSON(message, WorksheetSchema) : null;
        if (message.stop_reason === "refusal") {
          last = { t: "error", v: "Claude declined that one. Try a different school topic." };
        } else if (message.stop_reason === "max_tokens") {
          last = { t: "error", v: "That worksheet ran too long and got cut off. Try a narrower topic." };
        } else if (!sheet) {
          last = { t: "error", v: "Claude's answer came back garbled. Try again." };
        } else {
          last = { t: "done", v: sheet, left: booking.left };
        }
      } catch (err) {
        const f = failure(err, reserved);
        actual = f.actual;
        refund = f.refund;
        if (refund) booking.left.worksheet += 1;
        if (!gone) console.error("worksheet", err);
        last = { t: "error", v: f.message, left: booking.left };
      }
      await send(last);
      if (!gone) await writer.close().catch(() => {});
      try {
        await limiter(env).settle(who, "worksheet", booking.day, reserved, actual, refund);
      } catch (err) {
        console.error("settle", err);
      }
    })(),
  );

  return new Response(readable, {
    headers: {
      "content-type": "application/x-ndjson; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

function checkPicture(image: string): { pic: Picture; data: string } | Response {
  const data = image.slice(image.indexOf(",") + 1);
  const pic = picture(data);
  if (!pic || pic.width < 16 || pic.height < 16) return sorry("That picture couldn't be read. Try another one.", 400);
  if (pic.width > IMAGE_SIDE_MAX || pic.height > IMAGE_SIDE_MAX) {
    return sorry("That picture is too big. Try a smaller one.", 400);
  }
  return { pic, data };
}

async function mark(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const parsed = MarkRequest.safeParse(await readBody(req));
  if (!parsed.success) return sorry("Write an answer first, or use a smaller photo.", 400);
  const { question, custom, image, token } = parsed.data;

  let q = QUESTIONS.find((x) => x.id === question);
  if (question === "custom") {
    if (!custom) return sorry("Write your question and its answer key first.", 400);
    q = { id: "custom", subject: "", from: "", ...custom };
  }
  if (!q) return sorry("Pick a question first.", 400);

  const checked = checkPicture(image);
  if (checked instanceof Response) return checked;
  const { pic, data } = checked;
  if (!(await human(token, req, env))) return sorry("Please finish the check box first.", 403);

  const model = models(env).mark;
  const who = await visitor(req, env);
  const reserved = worstCase("mark", model);
  const booking = await limiter(env).reserve(who, "mark", reserved, caps(env), reserved);
  if (!booking.ok) return refused(booking.reason, "mark", booking.left);

  // The question and key may come from a visitor, so they go in as quoted strings.
  const work = [
    `Grade: ${gradeName(q.grade)}${q.subject ? ` ${q.subject}` : ""}`,
    `Question: ${JSON.stringify(q.prompt)}`,
    `Key: ${JSON.stringify(q.key)}`,
    `Spelling counts: ${q.spelling ? "yes" : "no"}`,
    "Feedback style: hint",
    "The student's answer is in the image above.",
  ].join("\n");

  return askAboutPicture(env, ctx, {
    kind: "mark",
    who,
    booking,
    reserved,
    model,
    system: MARK_SYSTEM,
    format: MARK_FORMAT,
    schema: MarkSchema,
    pic,
    data,
    work,
    tooLong: "That was too much writing to mark here. Try one short answer.",
  });
}

type Booked = Extract<Reservation, { ok: true }>;

type PictureJob = {
  kind: "mark" | "page";
  who: string;
  booking: Booked;
  reserved: number;
  model: string;
  system: string;
  format: typeof MARK_FORMAT;
  schema: z.ZodType;
  pic: Picture;
  data: string;
  work: string;
  tooLong: string;
};

// One picture to Claude, for either marking demo. The call and its settling run under waitUntil, so a
// visitor who closes the tab can't leave the worst case charged against the day's budget.
function askAboutPicture(env: Env, ctx: ExecutionContext, job: PictureJob): Promise<Response> {
  const { kind, booking, reserved, model } = job;
  const run = (async (): Promise<Response> => {
    let actual = reserved;
    let refund = false;
    try {
      const message = await client(env).messages.create({
        model,
        max_tokens: LIMITS[kind].maxTokens,
        system: job.system,
        output_config: { effort: "low", format: job.format },
        messages: [
          {
            role: "user",
            content: [
              { type: "image", source: { type: "base64", media_type: job.pic.mediaType, data: job.data } },
              { type: "text", text: job.work },
            ],
          },
        ],
      });
      actual = cost(model, message.usage);
      logUsage(kind, model, message.usage, actual, message.stop_reason);
      if (message.stop_reason === "refusal") return sorry("Claude declined to mark that one.", 422, booking.left);
      if (message.stop_reason === "max_tokens") return sorry(job.tooLong, 422, booking.left);
      const result = readJSON(message, job.schema);
      if (!result) return sorry("Claude's answer came back garbled. Try again.", 502, booking.left);
      return json({ result, left: booking.left });
    } catch (err) {
      console.error(kind, err);
      const f = failure(err, reserved);
      actual = f.actual;
      refund = f.refund;
      return sorry(f.message, f.status, refund ? { ...booking.left, [kind]: booking.left[kind] + 1 } : booking.left);
    } finally {
      try {
        await limiter(env).settle(job.who, kind, booking.day, reserved, actual, refund);
      } catch (err) {
        console.error("settle", err);
      }
    }
  })();
  ctx.waitUntil(run);
  return run;
}

const PageRequest = z.object({
  image: z
    .string()
    .max(BODY_MAX - 2000)
    .regex(/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/),
  token: z.string().max(4096).optional(),
});

// Every sample's key goes in, and Claude reads which one this is from the page, so a visitor never picks
// the wrong one.
const SAMPLE_KEYS = JSON.stringify(
  Object.fromEntries(
    SAMPLE_IDS.map((id) => {
      const { title, grade, subject, instructions, questions } = SAMPLES[id];
      return [id, { title, grade, subject, instructions, questions }];
    }),
  ),
);

// A whole filled-in sample page, from a phone photo or a scan the browser turned into a picture.
async function markPage(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const parsed = PageRequest.safeParse(await readBody(req));
  if (!parsed.success) return sorry("Add a photo or scan of your page, or use a smaller one.", 400);
  const { image, token } = parsed.data;
  const checked = checkPicture(image);
  if (checked instanceof Response) return checked;
  const { pic, data } = checked;
  if (!(await human(token, req, env))) return sorry("Please finish the check box first.", 403);

  const model = models(env).mark;
  const who = await visitor(req, env);
  const reserved = worstCase("page", model);
  const booking = await limiter(env).reserve(who, "page", reserved, caps(env), worstCase("mark", model));
  if (!booking.ok) return refused(booking.reason, "page", booking.left);

  const work = [
    "Feedback style: hint",
    "The samples, by id, with their questions and keys:",
    SAMPLE_KEYS,
    "The filled-in page is in the image above.",
  ].join("\n");

  return askAboutPicture(env, ctx, {
    kind: "page",
    who,
    booking,
    reserved,
    model,
    system: PAGE_SYSTEM,
    format: PAGE_FORMAT,
    schema: PageSchema,
    pic,
    data,
    work,
    tooLong: "That page had too much on it to mark here.",
  });
}

async function api(req: Request, env: Env, ctx: ExecutionContext, url: URL): Promise<Response> {
  if (url.pathname === "/api/config" && req.method === "GET") return config(req, env);
  const routes: Record<string, typeof mark | typeof worksheet> = {
    "/api/worksheet": worksheet,
    "/api/mark": mark,
    "/api/page": markPage,
  };
  const route = routes[url.pathname] ?? null;
  if (!route) return sorry("Not found.", 404);
  if (req.method !== "POST") return sorry("Use POST.", 405);
  if (!sameOrigin(req, url)) return sorry("Demos run from this site only.", 403);
  if (!demosOn(env)) return sorry("The demos are switched off for now.", 503);
  return route(req, env, ctx);
}

// The same as public/_headers, which Cloudflare Pages doesn't apply to pages this Worker serves.
const PAGE_HEADERS: Record<string, string> = {
  "Content-Security-Policy":
    "default-src 'self'; script-src 'self' 'wasm-unsafe-eval' https://challenges.cloudflare.com; frame-src https://challenges.cloudflare.com; " +
    "img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'self'; base-uri 'none'; " +
    "form-action 'self'; frame-ancestors 'none'; object-src 'none'",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(self), microphone=(), geolocation=(), interest-cohort=()",
};

// Link previews need absolute URLs, and the page doesn't know which domain it will live on.
async function home(req: Request, env: Env, url: URL): Promise<Response> {
  const res = await env.ASSETS.fetch(req);
  if (!res.headers.get("content-type")?.includes("text/html")) return res;
  const out = new Response(res.body, res);
  for (const [name, value] of Object.entries(PAGE_HEADERS)) {
    if (!out.headers.has(name)) out.headers.set(name, value);
  }
  return new HTMLRewriter()
    .on('meta[property="og:image"]', {
      element: (e) => {
        e.setAttribute("content", new URL("/img/og.png", url.origin).href);
      },
    })
    .on('meta[property="og:url"]', {
      element: (e) => {
        e.setAttribute("content", new URL("/", url.origin).href);
      },
    })
    .transform(out);
}

export default {
  async fetch(req, env, ctx): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname === "/" || url.pathname === "/index.html") return home(req, env, url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(req);
    try {
      return await api(req, env, ctx, url);
    } catch (err) {
      console.error("api", err);
      return sorry("Something went wrong on our side. Try again in a minute.", 500);
    }
  },
} satisfies ExportedHandler<Env>;
