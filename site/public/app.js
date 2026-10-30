"use strict";

// Paper Loop website: the two demos. Every string from Claude or the visitor is inserted with
// textContent, never as HTML.

const $ = (sel, root = document) => root.querySelector(sel);

function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === false || v == null) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

const state = {
  config: null,
  left: null,
  sheet: null,
  sheetGrade: 6,
  sheetLanguage: null,
  view: "student",
  turnstile: {},
  busy: { make: false, mark: false, page: false },
  pageImage: null,
};

/* ---------- Config, quota, and the optional Turnstile check ---------- */

function gradeName(g) {
  return `${g}${g === 2 ? "nd" : g === 3 ? "rd" : "th"} grade`;
}

function fillGrades(select, chosen) {
  for (let g = 2; g <= 12; g++) select.append(el("option", { value: g, selected: g === chosen }, gradeName(g)));
}

function showQuota() {
  const q = $("#quota");
  const c = state.config;
  if (!c) return;
  if (!c.demos) {
    q.textContent = c.offline
      ? "The live demos aren't running on this copy of the site. Everything else on the page works."
      : "The demos are switched off for now. Everything else on the page still works.";
    return;
  }
  const l = state.left;
  // A demo that's still running keeps its button off, whatever the counts say.
  $("#make-go").disabled = state.busy.make || !l.open || l.worksheet <= 0;
  $("#mark-go").disabled = state.busy.mark || !l.open || l.mark <= 0;
  $("#page-go").disabled = state.busy.page || !l.open || !(l.page > 0);
  if (!l.open) {
    q.textContent = "Today's free demos are used up. They reset at midnight UTC.";
    return;
  }
  const count = (n, one) => `${n ?? 0} ${one}${n === 1 ? "" : "s"}`;
  q.textContent = `You have ${count(l.worksheet, "worksheet")}, ${count(l.mark, "marked answer")} and ${count(l.page, "marked page")} left today.`;
}

function setLeft(left) {
  if (!left) return;
  state.left = left;
  showQuota();
}

function loadTurnstile(siteKey) {
  window.onTurnstileLoad = () => {
    for (const id of ["make-check", "mark-check", "page-check"]) {
      state.turnstile[id] = window.turnstile.render(`#${id}`, { sitekey: siteKey, size: "flexible" });
    }
  };
  document.head.append(
    el("script", {
      src: "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=onTurnstileLoad",
      async: true,
      defer: true,
    }),
  );
}

function checkToken(id) {
  const widget = state.turnstile[id];
  if (widget === undefined || !window.turnstile) return undefined;
  return window.turnstile.getResponse(widget) || undefined;
}

function resetCheck(id) {
  const widget = state.turnstile[id];
  if (widget !== undefined && window.turnstile) window.turnstile.reset(widget);
}

async function loadConfig() {
  try {
    const res = await fetch("/api/config", { headers: { accept: "application/json" } });
    if (!res.ok) throw new Error(String(res.status));
    state.config = await res.json();
  } catch {
    // No demo server: the page was uploaded as plain files.
    state.config = {
      demos: false,
      offline: true,
      left: { worksheet: 0, mark: 0, page: 0, open: false },
      questions: [],
      languages: [],
      samples: [],
    };
  }
  state.left = state.config.left;
  for (const lang of state.config.languages) $("#language").append(el("option", { value: lang }, lang));
  buildQuestions(state.config.questions);
  buildSamples(state.config.samples || []);
  if (state.config.turnstile) loadTurnstile(state.config.turnstile);
  if (!state.config.demos) {
    $("#make-go").disabled = true;
    $("#mark-go").disabled = true;
    $("#page-go").disabled = true;
  }
  showQuota();
}

/* ---------- Tabs ---------- */

function setupTabs() {
  const tabs = [...document.querySelectorAll('.tabs [role="tab"]')];
  const select = (tab) => {
    for (const t of tabs) {
      const on = t === tab;
      t.setAttribute("aria-selected", on);
      t.tabIndex = on ? 0 : -1;
      $(`#${t.getAttribute("aria-controls")}`).hidden = !on;
    }
    if (tab.id === "tab-mark") pad.resize();
  };
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => select(tab));
    tab.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      select(next);
      next.focus();
    });
  });
}

/* ---------- Reading a streamed answer ---------- */

// Close whatever is still open in a half-written JSON document so it can be shown as it arrives.
function closeJSON(text) {
  const stack = [];
  let inString = false;
  let escaped = false;
  for (const ch of text) {
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === "\\") escaped = true;
      else if (ch === '"') inString = false;
    } else if (ch === '"') inString = true;
    else if (ch === "{" || ch === "[") stack.push(ch);
    else if (ch === "}" || ch === "]") stack.pop();
  }
  let out = text;
  if (inString) out = (escaped ? out.slice(0, -1) : out) + '"';
  out = out.replace(/[\s,:]+$/, "");
  for (let i = stack.length - 1; i >= 0; i--) out += stack[i] === "{" ? "}" : "]";
  return out;
}

function partialParse(text) {
  let s = text;
  for (let tries = 0; tries < 12 && s.length; tries++) {
    try {
      return JSON.parse(closeJSON(s));
    } catch {
      const cut = Math.max(s.lastIndexOf(","), s.lastIndexOf("{"), s.lastIndexOf("["));
      if (cut <= 0) return null;
      s = s.slice(0, s.lastIndexOf(",") === cut ? cut : cut + 1);
    }
  }
  return null;
}

async function* ndjson(res) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) yield JSON.parse(line);
    }
  }
  if (buffer.trim()) yield JSON.parse(buffer);
}

/* ---------- Demo 1: make a worksheet ---------- */

const LETTERS = "ABCDEFGH";
const RTL = new Set(["Arabic"]);
const LANG_CODES = {
  Spanish: "es", Arabic: "ar", "Chinese (Simplified)": "zh-Hans", Vietnamese: "vi", Tagalog: "tl",
  "Haitian Creole": "ht", Portuguese: "pt", Russian: "ru", Korean: "ko", French: "fr", Somali: "so", Ukrainian: "uk",
};

function sheetHead(title, instructions, digits, lang) {
  const boxes = Array.from({ length: digits }, () => el("span"));
  return el(
    "header",
    { class: "sheet-head" },
    el("div", { class: "qr", "aria-hidden": "true" }),
    el(
      "div",
      {},
      el("h3", { text: title || " " }),
      el("p", { class: "sheet-sub", text: lang === "en" ? "Page 1 of 1" : "1 / 1" }),
      el("p", { class: "sheet-sub", text: instructions || "" }),
    ),
    el(
      "div",
      { class: "idbox" },
      el("div", { class: "idbox-row" }, "ID #", ...boxes),
      el("small", { text: "one digit per box, not your name" }),
    ),
  );
}

function questionBody(q, kind) {
  const parts = [];
  const prompt = String(q.prompt ?? "");
  if (kind === "fill" && prompt.includes("____")) {
    const p = el("p", { class: "qtext" });
    prompt.split(/_{3,}/).forEach((piece, i, all) => {
      p.append(piece);
      if (i < all.length - 1) p.append(el("span", { class: "blank", "aria-label": "blank" }));
    });
    return { promptNode: p, parts };
  }
  if (kind === "choice" && Array.isArray(q.options) && q.options.length) {
    parts.push(
      el(
        "ul",
        { class: "opts" },
        q.options.slice(0, 6).map((opt, i) => el("li", {}, el("b", { text: LETTERS[i] }), el("span", { text: opt }))),
      ),
    );
  } else if (kind === "math") {
    parts.push(el("div", { class: "work", "aria-label": "space to show work" }));
  } else if (kind === "short") {
    parts.push(el("div", { class: "lines", "aria-label": "space to write" }));
  }
  return { promptNode: el("p", { class: "qtext", text: prompt }), parts };
}

function renderSheet() {
  const ws = state.sheet;
  const out = $("#sheet-out");
  out.replaceChildren();
  if (!ws) return;
  const view = state.view;
  const version = view === "version" ? ws.version : null;
  const digits = state.sheetGrade <= 3 ? 2 : 4;
  const language = version ? state.sheetLanguage : null;
  const sheet = el("article", {
    class: `sheet${state.writing ? " writing" : ""}`,
    lang: version ? LANG_CODES[language] : "en",
    dir: version && RTL.has(language) ? "rtl" : undefined,
  });
  for (const c of ["tl", "tr", "bl", "br"]) sheet.append(el("span", { class: `corner ${c}`, "aria-hidden": "true" }));

  const title = version ? version.title : ws.title;
  const instructions = version ? version.instructions : ws.instructions;
  sheet.append(sheetHead(view === "key" ? `${ws.title ?? ""}: answer key` : title, instructions, digits, version ? "" : "en"));

  const qs = Array.isArray(ws.questions) ? ws.questions : [];
  const list = el("ol", { class: "qlist" });
  qs.slice(0, 8).forEach((q, i) => {
    if (!q || !q.prompt) return;
    const vq = version && Array.isArray(version.questions) ? version.questions[i] : null;
    const shown = vq ? { ...q, title: vq.title, prompt: vq.prompt, options: vq.options } : q;
    const kind = q.kind || "short";
    const { promptNode, parts } = questionBody(shown, kind);
    promptNode.prepend(el("b", { text: `${i + 1}. ${shown.title ? `${shown.title}: ` : ""}` }));
    const side = el("div", { class: "side" });
    if (view === "key") {
      const answer = kind === "choice" && /^[A-H]$/.test(String(q.answer ?? "").trim())
        ? `${q.answer}${q.options?.[LETTERS.indexOf(q.answer.trim())] ? `: ${q.options[LETTERS.indexOf(q.answer.trim())]}` : ""}`
        : q.answer;
      side.append(
        el("p", { class: "k", text: `Answer: ${answer ?? ""}` }),
        q.full_credit ? el("p", { text: `Full credit: ${q.full_credit}` }) : null,
        q.common_mistake ? el("p", { class: "k", text: `If a student writes “${q.common_mistake}”:` }) : null,
        q.comment ? el("p", { text: q.comment }) : null,
        q.skill ? el("p", { class: "skill", text: `Skill: ${q.skill}` }) : null,
      );
    }
    list.append(el("li", { class: "qitem" }, el("div", {}, promptNode, ...parts), side));
  });
  if (!qs.some((q) => q && q.prompt)) {
    list.append(el("li", { class: "placeholder", text: state.phase || "Claude is writing your worksheet…" }));
  }
  sheet.append(list);
  if (view !== "key") sheet.append(el("div", { class: "sheet-sum", text: version ? "" : "Next step:" }));
  sheet.append(el("p", { class: "sheet-foot", text: "paper loop demo · page 1 of 1 · please don't write in the corner squares" }));
  out.append(sheet);
}

function renderSheetTabs() {
  const ws = state.sheet;
  const tabs = $("#sheet-tabs");
  tabs.replaceChildren();
  const views = [["student", "Worksheet"], ["key", "Answer key"]];
  if (ws?.version?.questions?.length) views.push(["version", ws.version.language || "Other language"]);
  for (const [view, label] of views) {
    const b = el("button", { type: "button", role: "tab", "aria-selected": String(state.view === view) }, label);
    b.addEventListener("click", () => {
      state.view = view;
      renderSheetTabs();
      renderSheet();
    });
    tabs.append(b);
  }
}

async function makeWorksheet(e) {
  e.preventDefault();
  const status = $("#make-status");
  const go = $("#make-go");
  const topic = $("#topic").value.trim();
  if (topic.length < 2) {
    status.textContent = "Type a topic first.";
    status.className = "status err";
    $("#topic").focus();
    return;
  }
  const body = {
    topic,
    grade: Number($("#grade").value),
    language: $("#language").value || null,
    token: checkToken("make-check"),
  };
  if (state.config?.turnstile && !body.token) {
    status.textContent = "Please finish the check box first.";
    status.className = "status err";
    return;
  }
  state.busy.make = true;
  go.disabled = true;
  status.className = "status";
  status.textContent = "Sending your topic to Claude…";
  state.sheet = { questions: [] };
  state.sheetGrade = body.grade;
  state.sheetLanguage = body.language;
  state.view = "student";
  state.writing = true;
  state.phase = "Claude is writing your worksheet…";
  $("#sheet-area").hidden = false;
  $("#teacher-note").textContent = "";
  renderSheetTabs();
  renderSheet();

  let text = "";
  let shown = 0;
  let finished = false;
  try {
    const res = await fetch("/api/worksheet", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) {
      const err = await res.json().catch(() => ({}));
      setLeft(err.left);
      throw new Error(err.error || "Something went wrong. Try again in a minute.");
    }
    for await (const ev of ndjson(res)) {
      if (ev.t === "start") {
        setLeft(ev.left);
        status.textContent = "Claude is writing…";
      } else if (ev.t === "phase") {
        state.phase = "Claude is planning the questions…";
        status.textContent = state.phase;
        renderSheet();
      } else if (ev.t === "text") {
        text += ev.v;
        const partial = partialParse(text);
        if (partial && typeof partial === "object") {
          const count = (partial.questions || []).filter((q) => q && q.prompt).length;
          state.sheet = partial;
          if (count !== shown || count === 0) {
            shown = count;
            renderSheet();
          }
          status.textContent = count ? `Claude is writing question ${count}…` : "Claude is writing…";
        }
      } else if (ev.t === "done") {
        finished = true;
        setLeft(ev.left);
        state.sheet = ev.v;
        state.writing = false;
        if (!ev.v.ok) {
          $("#sheet-area").hidden = true;
          status.textContent = ev.v.message || "Try a topic a K-12 class would study.";
          return;
        }
        status.textContent = "Done. Print it, or open the answer key to see how Paper Loop would mark it.";
        $("#teacher-note").textContent = ev.v.teacher_note ? `For the teacher: ${ev.v.teacher_note}` : "";
        renderSheetTabs();
        renderSheet();
      } else if (ev.t === "error") {
        setLeft(ev.left);
        throw new Error(ev.v);
      }
    }
    if (!finished) throw new Error("The connection dropped before the worksheet was finished. Try again.");
  } catch (err) {
    // A half-written worksheet isn't worth printing.
    state.writing = false;
    state.sheet = null;
    $("#sheet-area").hidden = true;
    status.className = "status err";
    status.textContent = err.message || "Something went wrong. Try again in a minute.";
  } finally {
    state.writing = false;
    state.busy.make = false;
    resetCheck("make-check");
    showQuota();
  }
}

function setupMake() {
  fillGrades($("#grade"), 6);
  for (const chip of document.querySelectorAll(".chip")) {
    chip.addEventListener("click", () => {
      $("#topic").value = chip.textContent;
      $("#topic").focus();
    });
  }
  $("#make-form").addEventListener("submit", makeWorksheet);
  $("#print").addEventListener("click", () => window.print());
}

/* ---------- Demo 2: mark a handwritten answer ---------- */

const pad = {
  canvas: null,
  ctx: null,
  height: 300,
  strokes: [],
  current: null,
  photo: null,

  init() {
    this.canvas = $("#pad");
    this.ctx = this.canvas.getContext("2d");
    const c = this.canvas;
    c.addEventListener("pointerdown", (e) => {
      if (this.photo) return;
      c.setPointerCapture(e.pointerId);
      this.current = [this.point(e)];
      this.strokes.push(this.current);
      this.draw();
    });
    c.addEventListener("pointermove", (e) => {
      if (!this.current) return;
      for (const ev of e.getCoalescedEvents ? e.getCoalescedEvents() : [e]) this.current.push(this.point(ev));
      this.draw();
    });
    const end = () => (this.current = null);
    c.addEventListener("pointerup", end);
    c.addEventListener("pointercancel", end);
    window.addEventListener("resize", () => this.resize());
    this.resize();
  },

  // Points are stored in a space 900 wide, as tall as the box's shape (3:1, or 2:1 on a phone), so
  // the picture Claude gets matches what the visitor saw.
  point(e) {
    const r = this.canvas.getBoundingClientRect();
    return [((e.clientX - r.left) / r.width) * 900, ((e.clientY - r.top) / r.height) * this.height];
  },

  resize() {
    const r = this.canvas.getBoundingClientRect();
    if (!r.width) return;
    const dpr = window.devicePixelRatio || 1;
    const height = Math.round((900 * r.height) / r.width);
    // The box got shorter (a phone turned sideways): shrink the writing evenly so it all still fits.
    if (height < this.height) {
      const k = height / this.height;
      this.strokes = this.strokes.map((s) => s.map(([x, y]) => [x * k, y * k]));
    }
    this.height = height;
    this.canvas.width = Math.round(r.width * dpr);
    this.canvas.height = Math.round(r.height * dpr);
    this.draw();
  },

  paint(ctx, w, h) {
    ctx.save();
    ctx.scale(w / 900, h / this.height);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#1a1a1a";
    ctx.lineWidth = 3.2;
    for (const s of this.strokes) {
      ctx.beginPath();
      ctx.moveTo(s[0][0], s[0][1]);
      if (s.length === 1) ctx.lineTo(s[0][0] + 0.1, s[0][1]);
      for (let i = 1; i < s.length; i++) ctx.lineTo(s[i][0], s[i][1]);
      ctx.stroke();
    }
    ctx.restore();
  },

  draw() {
    const { width, height } = this.canvas;
    this.ctx.clearRect(0, 0, width, height);
    this.paint(this.ctx, width, height);
  },

  empty() {
    return !this.photo && this.strokes.length === 0;
  },

  clear() {
    this.strokes = [];
    this.setPhoto(null);
    this.draw();
  },

  undo() {
    if (this.photo) return this.setPhoto(null);
    this.strokes.pop();
    this.draw();
  },

  setPhoto(dataUrl) {
    this.photo = dataUrl;
    const img = $("#photo");
    img.hidden = !dataUrl;
    if (dataUrl) img.src = dataUrl;
    else img.removeAttribute("src");
    this.canvas.hidden = !!dataUrl;
  },

  // What goes to Claude: the writing on plain white, with no ruled lines to mistake for cross-outs.
  image() {
    if (this.photo) return this.photo;
    const out = document.createElement("canvas");
    out.width = 900;
    out.height = this.height;
    const ctx = out.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, 900, this.height);
    this.paint(ctx, 900, this.height);
    return out.toDataURL("image/png");
  },
};

// A JPEG small enough to send: lower the quality until it fits under the server's limit.
function encodeJpeg(canvas) {
  for (const quality of [0.85, 0.75, 0.65, 0.55]) {
    const url = canvas.toDataURL("image/jpeg", quality);
    if (url.length < 850_000) return url;
  }
  return canvas.toDataURL("image/jpeg", 0.45);
}

function shrinkPhoto(file, longest = 1200) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, longest / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * scale);
      c.height = Math.round(img.height * scale);
      const ctx = c.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(encodeJpeg(c));
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("That file isn't a picture this browser can open."));
    };
    img.src = url;
  });
}

function chosenQuestion() {
  const id = document.querySelector('input[name="q"]:checked')?.value;
  if (id === "custom") {
    return {
      id,
      prompt: $("#c-prompt").value.trim(),
      key: $("#c-key").value.trim(),
      grade: Number($("#c-grade").value),
      spelling: $("#c-spelling").checked,
    };
  }
  return state.config?.questions.find((q) => q.id === id) || null;
}

function showPrompt() {
  const q = chosenQuestion();
  $("#custom").hidden = q?.id !== "custom";
  $("#prompt-shown").textContent = q?.id === "custom" ? q.prompt || "Your question will show here." : q?.prompt || "";
}

function buildQuestions(questions) {
  const box = $("#qpick");
  box.replaceChildren();
  const all = [...questions, { id: "custom", from: "Your own question", prompt: "Write a question and what a right answer needs." }];
  all.forEach((q, i) => {
    const input = el("input", { type: "radio", name: "q", value: q.id, id: `q-${q.id}`, checked: i === 0 });
    input.addEventListener("change", () => {
      showPrompt();
      pad.clear();
    });
    box.append(
      el("label", { class: "qopt", for: `q-${q.id}` }, input, el("span", {}, el("b", { text: q.from }), q.prompt)),
    );
  });
  showPrompt();
}

function renderMarked(q, image, r) {
  const box = $("#marked");
  const right = r.verdict === "correct";
  const flagged = r.confidence < 0.8 || r.key_ambiguous || r.verdict === "unreadable";
  const label = { correct: "Correct", partial: "Partly right", incorrect: "Not yet", blank: "Blank", unreadable: "Couldn't read it" }[r.verdict] || r.verdict;
  box.replaceChildren(
    el(
      "div",
      { class: "crop" },
      el("p", { class: "crop-q", text: q.prompt }),
      el("div", { class: "crop-img" }, el("img", { src: image, alt: "Your handwritten answer" })),
      el("p", { class: "comment" }, right ? el("span", { class: "tick", "aria-label": "check mark", text: "✓" }) : null, el("span", { text: r.comment })),
      el(
        "div",
        { class: "read" },
        el("p", {}, el("span", { class: "verdict", text: label }), " "),
        el("p", {}, "Claude read: ", el("q", { text: r.transcription || "(nothing)" })),
        r.uncertain_words?.length ? el("p", { text: `Not sure of: ${r.uncertain_words.join(", ")}` }) : null,
        flagged ? el("p", {}, el("span", { class: "flag", text: `Flagged for the teacher to check (confidence ${Number(r.confidence).toFixed(2)})` })) : null,
        r.note ? el("p", { text: `Note for the teacher: ${r.note}` }) : null,
        el("p", { text: "On a real page, the comment prints beside the answer, and a check mark prints only when it's fully right." }),
      ),
    ),
  );
  box.hidden = false;
  box.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest" });
}

async function markAnswer(e) {
  e.preventDefault();
  const status = $("#mark-status");
  const go = $("#mark-go");
  const q = chosenQuestion();
  status.className = "status err";
  if (!q) return void (status.textContent = "Pick a question first.");
  if (q.id === "custom" && (q.prompt.length < 3 || !q.key)) return void (status.textContent = "Write your question and what a right answer needs.");
  if (pad.empty()) return void (status.textContent = "Write an answer in the box first.");
  const token = checkToken("mark-check");
  if (state.config?.turnstile && !token) return void (status.textContent = "Please finish the check box first.");

  const image = pad.image();
  if (image.length > 880_000) return void (status.textContent = "That photo is too big. Try a closer, smaller one.");
  const body = { question: q.id, image, token };
  if (q.id === "custom") body.custom = { prompt: q.prompt, key: q.key, grade: q.grade, spelling: q.spelling };

  state.busy.mark = true;
  go.disabled = true;
  status.className = "status";
  status.textContent = "Claude is reading your handwriting…";
  try {
    const res = await fetch("/api/mark", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    const out = await res.json().catch(() => ({}));
    setLeft(out.left);
    if (!res.ok) throw new Error(out.error || "Something went wrong. Try again in a minute.");
    status.textContent = "";
    renderMarked(q, image, out.result);
  } catch (err) {
    status.className = "status err";
    status.textContent = err.message;
  } finally {
    state.busy.mark = false;
    resetCheck("mark-check");
    showQuota();
  }
}

function setupMark() {
  fillGrades($("#c-grade"), 6);
  pad.init();
  $("#undo").addEventListener("click", () => pad.undo());
  $("#clear").addEventListener("click", () => pad.clear());
  $("#c-prompt").addEventListener("input", showPrompt);
  $("#file").addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      pad.setPhoto(await shrinkPhoto(file));
    } catch (err) {
      $("#mark-status").className = "status err";
      $("#mark-status").textContent = err.message;
    }
  });
  $("#mark-form").addEventListener("submit", markAnswer);
}

/* ---------- Demo 3: mark a whole sample page ---------- */

// The samples to print. Claude reads which one a page is from its footer, so nobody picks it here.
function buildSamples(samples) {
  const box = $("#spick");
  box.replaceChildren();
  for (const s of samples) {
    box.append(
      el(
        "a",
        { class: "sopt", href: `/samples/${s.id}.pdf`, target: "_blank", rel: "noopener" },
        el(
          "span",
          { class: "card-in" },
          el("img", { src: `/samples/${s.id}.jpg`, alt: "", loading: "lazy", width: "320", height: "414" }),
          el("b", { text: s.title }),
          el("span", { text: `Grade ${s.grade} · Print it` }),
        ),
      ),
    );
  }
}

// True when a rendered page is almost entirely white: a scan pdf.js couldn't decode.
function looksBlank(canvas) {
  const small = document.createElement("canvas");
  small.width = 64;
  small.height = 80;
  const ctx = small.getContext("2d");
  ctx.drawImage(canvas, 0, 0, 64, 80);
  const px = ctx.getImageData(0, 0, 64, 80).data;
  let ink = 0;
  for (let i = 0; i < px.length; i += 4) if (px[i] + px[i + 1] + px[i + 2] < 600) ink++;
  return ink < 20;
}

// A scan saved as a PDF (the iPhone's Notes or Files scanner, a copier) becomes a picture of its first
// page, here in the browser, with pdf.js. It's loaded only when someone picks a PDF.
async function pdfToImage(file) {
  const pdfjs = await import("/vendor/pdfjs/pdf.min.mjs");
  pdfjs.GlobalWorkerOptions.workerSrc = "/vendor/pdfjs/pdf.worker.min.mjs";
  const doc = await pdfjs.getDocument({ data: await file.arrayBuffer(), isEvalSupported: false }).promise;
  try {
    const page = await doc.getPage(1);
    const size = page.getViewport({ scale: 1 });
    const viewport = page.getViewport({ scale: 1600 / Math.max(size.width, size.height) });
    const c = document.createElement("canvas");
    c.width = Math.round(viewport.width);
    c.height = Math.round(viewport.height);
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, c.width, c.height);
    await page.render({ canvasContext: ctx, viewport }).promise;
    if (looksBlank(c)) throw new Error("blank");
    return { image: encodeJpeg(c), pages: doc.numPages };
  } finally {
    doc.destroy();
  }
}

async function choosePage(e) {
  const file = e.target.files?.[0];
  e.target.value = "";
  if (!file) return;
  const status = $("#page-status");
  status.className = "status";
  status.textContent = "Getting your page ready…";
  try {
    const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
    const out = isPdf ? await pdfToImage(file) : { image: await shrinkPhoto(file, 1600), pages: 1 };
    state.pageImage = out.image;
    const img = $("#page-preview");
    img.src = out.image;
    img.hidden = false;
    $("#page-drop-text").hidden = true;
    status.textContent = out.pages > 1 ? `That PDF has ${out.pages} pages; Claude will mark the first.` : "";
  } catch (err) {
    console.error(err);
    state.pageImage = null;
    status.className = "status err";
    status.textContent =
      err.message === "blank"
        ? "That PDF came out blank here. Try a photo of the page instead."
        : "That file couldn't be opened. Try a photo (JPEG or PNG) or a PDF scan.";
  }
}

function renderPage(sample, image, r) {
  const box = $("#page-result");
  const label = { correct: "Right", partial: "Partly right", incorrect: "Not yet", blank: "Blank", unreadable: "Couldn't read it" };
  const rows = (r.answers || []).map((a) => {
    const flagged = a.confidence < 0.8 || a.verdict === "unreadable";
    return el(
      "div",
      { class: "prow" },
      el("p", { class: "where" }, `Q${a.q}`, a.part ? el("span", { text: a.part }) : null),
      el(
        "div",
        {},
        el("p", { class: "said" }, "Read ", el("q", { text: a.read || "(blank)" }), ` · ${label[a.verdict] || a.verdict}`),
        el(
          "p",
          { class: "comment" },
          a.verdict === "correct" ? el("span", { class: "tick", "aria-label": "check mark", text: "✓" }) : null,
          el("span", { text: a.comment }),
        ),
        flagged ? el("span", { class: "flag", text: "Flagged for the teacher to check" }) : null,
      ),
    );
  });
  const right = (r.answers || []).filter((a) => a.verdict === "correct").length;
  box.replaceChildren(
    el("img", { src: image, alt: "Your filled-in page" }),
    el(
      "div",
      { class: "page-sheet" },
      el("h4", { text: sample.title }),
      el("p", { class: "meta", text: `ID read as ${r.id_read || "?"} · ${right} of ${(r.answers || []).length} parts right` }),
      ...rows,
      el(
        "div",
        { class: "page-sum" },
        r.strength ? el("p", {}, el("b", { text: "Strength: " }), r.strength) : null,
        r.next_step ? el("p", {}, el("b", { text: "Next step: " }), r.next_step) : null,
      ),
    ),
    el("p", { class: "page-note" }, "On paper, each comment prints beside its answer and the summary goes at the bottom of the page. ", el("a", { href: "#get" }, "Get Paper Loop for your class"), " to do this for a whole stack at once."),
  );
  box.hidden = false;
  box.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
}

async function markPage(e) {
  e.preventDefault();
  const status = $("#page-status");
  const go = $("#page-go");
  status.className = "status err";
  if (!state.pageImage) return void (status.textContent = "Add a photo or scan of your page first.");
  const token = checkToken("page-check");
  if (state.config?.turnstile && !token) return void (status.textContent = "Please finish the check box first.");

  const image = state.pageImage;
  state.busy.page = true;
  go.disabled = true;
  status.className = "status";
  status.textContent = "Claude is reading your page. This takes about half a minute…";
  try {
    const res = await fetch("/api/page", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ image, token }),
    });
    const out = await res.json().catch(() => ({}));
    setLeft(out.left);
    if (!res.ok || !out.result) throw new Error(out.error || "Something went wrong. Try again in a minute.");
    if (!out.result.ok) throw new Error(out.result.message || "Claude couldn't find a sample in that picture. Try another photo.");
    const sample = state.config?.samples?.find((s) => s.id === out.result.sample) || { title: "Your sample" };
    status.textContent = "";
    renderPage(sample, image, out.result);
  } catch (err) {
    status.className = "status err";
    status.textContent = err.message;
  } finally {
    state.busy.page = false;
    resetCheck("page-check");
    showQuota();
  }
}

function setupPage() {
  $("#page-file").addEventListener("change", choosePage);
  $("#page-form").addEventListener("submit", markPage);
}

/* ---------- The score ---------- */

// Never autoplays: it starts only when the visitor presses the button, fades in, and can be stopped
// from the header after they scroll away.
function setupScore() {
  const audio = $("#score");
  const play = $("#score-play");
  const stop = $("#score-stop");
  if (!audio || !play) return;
  let fade = null;
  const show = (on) => {
    play.setAttribute("aria-pressed", String(on));
    $(".score-icon", play).textContent = on ? "❚❚" : "▶";
    $(".score-label", play).textContent = on ? "Pause the score" : "Play the score";
    stop.hidden = !on;
  };
  const fadeIn = () => {
    clearInterval(fade);
    audio.volume = 0;
    fade = setInterval(() => {
      audio.volume = Math.min(0.8, audio.volume + 0.05);
      if (audio.volume >= 0.8) clearInterval(fade);
    }, 90);
  };
  play.addEventListener("click", async () => {
    if (!audio.paused) return audio.pause();
    try {
      fadeIn();
      await audio.play();
    } catch {
      clearInterval(fade);
      show(false);
    }
  });
  stop.addEventListener("click", () => audio.pause());
  audio.addEventListener("play", () => show(true));
  audio.addEventListener("pause", () => show(false));
  audio.addEventListener("ended", () => {
    audio.currentTime = 0;
    show(false);
  });
}

setupTabs();
setupMake();
setupMark();
setupPage();
setupScore();
loadConfig();
