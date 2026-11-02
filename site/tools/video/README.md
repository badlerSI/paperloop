# Tutorial videos

Short silent how-to videos for the site, made from HTML. The first one, `try-paper-loop.html`, is the
45-second video at the top of Try it (`public/video/try-paper-loop.mp4`).

## Make one

Needs Node, ffmpeg (`brew install ffmpeg`), and Google Chrome. Set `CHROME` to another Chrome or Chromium
if it isn't in /Applications.

```bash
cd site/tools/video
npm install
node render.mjs try-paper-loop.html stills 2 14.5 33 44   # check a few moments first
node render.mjs try-paper-loop.html                       # the whole video, a few minutes
cp out/try-paper-loop.mp4 ../../public/video/
```

Stills and videos go in `out/`, which isn't committed. For the site's poster image, resize a still to
1280 × 720 and save it as `public/img/try-poster.jpg`.

## How a video page works

A page is a 1920 × 1080 stage, and every frame comes from the time alone: `window.render(t)` sets each
element's opacity, position, and clipping for second `t`, and `window.DURATION` is the length.
`render.mjs` calls `render` for every frame at 30 frames a second, screenshots it in headless Chrome, and
pipes the frames to ffmpeg. Nothing plays in real time, so every run gives the same video.

In `try-paper-loop.html`:

- `seg(t, a, b)` runs from 0 to 1 between seconds `a` and `b`; `ease`, `out`, and `lerp` shape it.
- `CAPTIONS` holds the numbered steps on the right, with the second each one starts and ends.
- `WRITE` and `AREAS` reveal the handwriting answer by answer: `assets/filled.png` (the plants sample
  with a student's answers) is clipped over `assets/blank.png` (the same page, blank).
- `COMMENTS` times the typed comments that appear beside the answers.
- `ME` and `CLAUDE` are the two lines of the setup chat at the end.

To make the next video in the series, copy the page, keep the helpers and the stage, and replace the
scenes. Fonts come from `public/fonts`, so the videos match the site.
