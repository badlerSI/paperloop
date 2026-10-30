import { DurableObject } from "cloudflare:workers";

export type Kind = "worksheet" | "mark";

export type Caps = { worksheet: number; mark: number; budgetUsd: number };

export type Left = { worksheet: number; mark: number; open: boolean };

export type Reservation =
  | { ok: true; day: string; left: Left }
  | { ok: false; reason: "visitor" | "budget"; left: Left };

type Used = { worksheet: number; mark: number };

// One instance holds the day's spending and each visitor's demo count. A single Durable Object is
// strongly consistent, so the daily budget can't be overrun by requests arriving at once: each request
// reserves its worst-case cost first, then settles the real cost when Claude answers.
// Visitors are a salted hash of the IP address; raw addresses are never stored. Everything is wiped at
// midnight UTC.
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

  private async left(visitor: string, caps: Caps, probe: number): Promise<Left> {
    const used = (await this.ctx.storage.get<Used>(`v:${visitor}`)) ?? { worksheet: 0, mark: 0 };
    const spent = (await this.ctx.storage.get<number>("spent")) ?? 0;
    return {
      worksheet: Math.max(0, caps.worksheet - used.worksheet),
      mark: Math.max(0, caps.mark - used.mark),
      open: spent + probe <= caps.budgetUsd,
    };
  }

  // "open" means today's budget has room for one more call costing `probe` dollars.
  async status(visitor: string, caps: Caps, probe: number): Promise<Left> {
    await this.today();
    return this.left(visitor, caps, probe);
  }

  // `cost` is this call's worst case; `floor` is the cheapest demo's, so "open" in the answer says
  // whether anything at all still fits today.
  async reserve(visitor: string, kind: Kind, cost: number, caps: Caps, floor: number): Promise<Reservation> {
    const day = await this.today();
    const left = await this.left(visitor, caps, floor);
    if (left[kind] <= 0) return { ok: false, reason: "visitor", left };
    const spent = (await this.ctx.storage.get<number>("spent")) ?? 0;
    if (spent + cost > caps.budgetUsd) return { ok: false, reason: "budget", left };
    const key = `v:${visitor}`;
    const used = (await this.ctx.storage.get<Used>(key)) ?? { worksheet: 0, mark: 0 };
    used[kind] += 1;
    await this.ctx.storage.put(key, used);
    await this.ctx.storage.put("spent", spent + cost);
    left[kind] -= 1;
    left.open = spent + cost + floor <= caps.budgetUsd;
    return { ok: true, day, left };
  }

  // Replace the reservation with what the call really cost. A call that failed on Anthropic's side
  // gives the visitor their demo back. A reservation from before midnight belongs to a day that has
  // already been wiped, so it changes nothing.
  async settle(visitor: string, kind: Kind, day: string, reserved: number, actual: number, refund: boolean): Promise<void> {
    if ((await this.today()) !== day) return;
    const spent = (await this.ctx.storage.get<number>("spent")) ?? 0;
    await this.ctx.storage.put("spent", Math.max(0, spent - reserved + actual));
    if (refund) {
      const key = `v:${visitor}`;
      const used = await this.ctx.storage.get<Used>(key);
      if (used && used[kind] > 0) {
        used[kind] -= 1;
        await this.ctx.storage.put(key, used);
      }
    }
  }
}
