// Render a video page to an MP4: set the time, screenshot, repeat; ffmpeg encodes the frames.
//   node render.mjs try-paper-loop.html                  the whole video, to out/try-paper-loop.mp4
//   node render.mjs try-paper-loop.html stills 2 8 15    PNG stills at those seconds, to check the design
// A video page draws every frame from the time alone: window.render(t) and window.DURATION, 1920 x 1080.
// Uses the installed Google Chrome; set CHROME to use another.
import puppeteer from "puppeteer-core";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const FPS = 30;
const [pageFile, mode, ...rest] = process.argv.slice(2);
if (!pageFile) {
  console.error("usage: node render.mjs PAGE.html [stills SECONDS...]");
  process.exit(1);
}
const name = path.basename(pageFile, ".html");
const out = path.join(here, "out");
mkdirSync(out, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
  args: ["--allow-file-access-from-files", "--hide-scrollbars", "--force-color-profile=srgb"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
await page.goto(`file://${path.resolve(here, pageFile)}`, { waitUntil: "load" });
await page.evaluate(async () => {
  await document.fonts.ready;
  await Promise.all([...document.images].map((i) => (i.complete ? null : new Promise((r) => (i.onload = r)))));
});

if (mode === "stills") {
  for (const s of rest) {
    await page.evaluate((t) => window.render(t), Number(s));
    await page.screenshot({ path: path.join(out, `${name}-${s}.png`) });
  }
  console.log(`wrote ${rest.length} stills to ${out}`);
} else {
  const outFile = path.join(out, `${name}.mp4`);
  const duration = await page.evaluate(() => window.DURATION);
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-i", "-",
    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", outFile],
    { stdio: ["pipe", "inherit", "inherit"] });
  const frames = Math.round(duration * FPS);
  for (let f = 0; f < frames; f++) {
    await page.evaluate((t) => window.render(t), f / FPS);
    const buf = await page.screenshot({ type: "jpeg", quality: 92 });
    if (!ff.stdin.write(buf)) await once(ff.stdin, "drain");
    if (f % 150 === 0) process.stdout.write(`${Math.round((100 * f) / frames)}% `);
  }
  ff.stdin.end();
  await once(ff, "close");
  console.log(`\nwrote ${outFile}`);
}
await browser.close();
