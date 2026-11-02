import { DurableObject } from "cloudflare:workers";

export type Kind = "worksheet" | "mark" | "page";

// `perAddress` is how many visitors' worth of demos one internet address gets in a day.
export type Caps = { worksheet: number; mark: number; page: number; budgetUsd: number; perAddress: number };

export type Left = { worksheet: number; mark: number; page: number; open: boolean };

// A visitor is one browser. A whole school can share one internet address, so each browser gets its own
// demos, and the address as a whole gets `perAddress` times as many.
export type Who = { visitor: string; address: string };

export type Reservation =
  | { ok: true; day: string; left: Left }
  | { ok: false; reason: "visitor" | "address" | "budget"; left: Left };

// Counts saved before the page demo existed have no "page".
type Used = { worksheet: number; mark: number; page?: number };

const NONE: Used = { worksheet: 0, mark: 0, page: 0 };

type Count = Omit<Left, "open">;

function remaining(caps: Caps, used: Used, times = 1): Count {
  return {
    worksheet: Math.max(0, caps.worksheet * times - used.worksheet),
    mark: Math.max(0, caps.mark * times - used.mark),
    page: Math.max(0, caps.page * times - (used.page ?? 0)),
  };
}

// What this browser has left, what its address has left, and the smaller of the two.
function tally(caps: Caps, mine: Used, shared: Used): { own: Count; all: Count; left: Count } {
  const own = remaining(caps, mine);
  const all = remaining(caps, shared, caps.perAddress);
  const left = {
    worksheet: Math.min(own.worksheet, all.worksheet),
    mark: Math.min(own.mark, all.mark),
    page: Math.min(own.page, all.page),
  };
  return { own, all, left };
}

function bump(used: Used | undefined, kind: Kind, by: number): Used {
  const out = { ...NONE, ...used };
  out[kind] = Math.max(0, (out[kind] ?? 0) + by);
  return out;
}

// One instance holds the day's spending and each visitor's demo count. A single Durable Object is
// strongly consistent, so the daily budget can't be overrun by requests arriving at once: each request
// reserves its worst-case cost first, then settles the real cost when Claude answers.
// Visitors and addresses are stored as salted hashes; raw addresses are never stored. Everything is
// wiped at midnight UTC.
export class Limiter extends DurableObject {
  private async today(): Promise<string> {
    const now = new Date();
    const day = now.toISOString().slice(0, 10);
    if ((await this.ctx.storage.get<string>("day")) !== day) {
      await this.ctx.storage.deleteAll();
      await this.ctx.storage.put("day", day);
      // Wipe the visitor hashes at midnight even if nobody visits tomorrow.
      const midnight = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1);
      await this.ctx.storage.setAlarm(midnight);
    }
    return day;
  }

  async alarm(): Promise<void> {
    await this.ctx.storage.deleteAll();
  }

  private async counts(who: Who, caps: Caps) {
    const mine = (await this.ctx.storage.get<Used>(`v:${who.visitor}`)) ?? NONE;
    const shared = (await this.ctx.storage.get<Used>(`a:${who.address}`)) ?? NONE;
    const spent = (await this.ctx.storage.get<number>("spent")) ?? 0;
    return { ...tally(caps, mine, shared), mine, shared, spent };
  }

  // "open" means today's budget has room for one more call costing `probe` dollars.
  async status(who: Who, caps: Caps, probe: number): Promise<Left> {
    await this.today();
    const { left, spent } = await this.counts(who, caps);
    return { ...left, open: spent + probe <= caps.budgetUsd };
  }

  // `cost` is this call's worst case; `floor` is the cheapest demo's, so "open" in the answer says
  // whether anything at all still fits today.
  async reserve(who: Who, kind: Kind, cost: number, caps: Caps, floor: number): Promise<Reservation> {
    const day = await this.today();
    const { own, all, mine, shared, spent, ...rest } = await this.counts(who, caps);
    const left = { ...rest.left, open: spent + floor <= caps.budgetUsd };
    if (own[kind] <= 0) return { ok: false, reason: "visitor", left };
    if (all[kind] <= 0) return { ok: false, reason: "address", left };
    if (spent + cost > caps.budgetUsd) return { ok: false, reason: "budget", left };
    await this.ctx.storage.put(`v:${who.visitor}`, bump(mine, kind, 1));
    await this.ctx.storage.put(`a:${who.address}`, bump(shared, kind, 1));
    await this.ctx.storage.put("spent", spent + cost);
    left[kind] -= 1;
    left.open = spent + cost + floor <= caps.budgetUsd;
    return { ok: true, day, left };
  }

  // Replace the reservation with what the call really cost. A call that failed on Anthropic's side
  // gives the visitor their demo back. A reservation from before midnight belongs to a day that has
  // already been wiped, so it changes nothing.
  async settle(who: Who, kind: Kind, day: string, reserved: number, actual: number, refund: boolean): Promise<void> {
    if ((await this.today()) !== day) return;
    const spent = (await this.ctx.storage.get<number>("spent")) ?? 0;
    await this.ctx.storage.put("spent", Math.max(0, spent - reserved + actual));
    if (refund) {
      for (const key of [`v:${who.visitor}`, `a:${who.address}`]) {
        const used = await this.ctx.storage.get<Used>(key);
        if (used) await this.ctx.storage.put(key, bump(used, kind, -1));
      }
    }
  }
}

// The same rules without a Durable Object, for a plain upload to Cloudflare Pages, which can't create
// one. Counts live in this server's memory, so they're approximate: each Cloudflare location keeps its
// own, and a fresh copy of the server starts from zero. There, the API key's own spend limit (or its
// credit balance) is the real cap.
export class MemoryLedger {
  private day = "";
  private spent = 0;
  private used = new Map<string, Used>();
  private shared = new Map<string, Used>();

  private today(): string {
    const day = new Date().toISOString().slice(0, 10);
    if (day !== this.day) {
      this.day = day;
      this.spent = 0;
      this.used.clear();
      this.shared.clear();
    }
    return day;
  }

  private counts(who: Who, caps: Caps) {
    const mine = this.used.get(who.visitor) ?? NONE;
    const shared = this.shared.get(who.address) ?? NONE;
    return { ...tally(caps, mine, shared), mine, shared };
  }

  async status(who: Who, caps: Caps, probe: number): Promise<Left> {
    this.today();
    return { ...this.counts(who, caps).left, open: this.spent + probe <= caps.budgetUsd };
  }

  async reserve(who: Who, kind: Kind, cost: number, caps: Caps, floor: number): Promise<Reservation> {
    const day = this.today();
    const { own, all, mine, shared, ...rest } = this.counts(who, caps);
    const left = { ...rest.left, open: this.spent + floor <= caps.budgetUsd };
    if (own[kind] <= 0) return { ok: false, reason: "visitor", left };
    if (all[kind] <= 0) return { ok: false, reason: "address", left };
    if (this.spent + cost > caps.budgetUsd) return { ok: false, reason: "budget", left };
    this.used.set(who.visitor, bump(mine, kind, 1));
    this.shared.set(who.address, bump(shared, kind, 1));
    this.spent += cost;
    left[kind] -= 1;
    left.open = this.spent + floor <= caps.budgetUsd;
    return { ok: true, day, left };
  }

  async settle(who: Who, kind: Kind, day: string, reserved: number, actual: number, refund: boolean): Promise<void> {
    if (this.today() !== day) return;
    this.spent = Math.max(0, this.spent - reserved + actual);
    if (!refund) return;
    const mine = this.used.get(who.visitor);
    if (mine) this.used.set(who.visitor, bump(mine, kind, -1));
    const shared = this.shared.get(who.address);
    if (shared) this.shared.set(who.address, bump(shared, kind, -1));
  }
}
