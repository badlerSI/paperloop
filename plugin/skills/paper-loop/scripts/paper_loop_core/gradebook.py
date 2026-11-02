"""Scores for the school's gradebook, with no name ever reaching Claude.

`gradebook.html` holds each student's score on each marked worksheet, by class ID. The teacher opens it in
a browser, then opens the file their gradebook exports. That file has names, so it stays on their computer.
The page matches each student in it to a class ID: by the teacher's own list of IDs and names when they open
one, else by order (setup numbers students in the order of the teacher's class list, so the nth student is
the nth ID). It then saves a file to import back into the gradebook. It needs no internet, and a
Content-Security-Policy in the file stops it from sending anything anywhere.

Practice sheets aren't graded here: each student's has different questions.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from . import progress as PG
from . import sheet as S


def _place(sid: str) -> int | None:
    """A setup-made ID's place in the class list: 2 digits (grades 2-3), or class, place, check digit."""
    if len(sid) <= 2 and sid.isdigit():
        return int(sid)
    if len(sid) == 4 and sid.isdigit() and sum(map(int, sid[:3])) % 10 == int(sid[3]):
        return int(sid[1:3])
    return None


def scores(runs: list[dict]) -> list[dict]:
    """Each graded worksheet, oldest first: its points, and each student's score on it."""
    out = []
    for run in runs:
        if run.get("practice"):
            continue
        key = S.read_json(Path(run["assignment_dir"]) / "key.json")
        possible = sum(i["points"] for i in key["items"] if not i.get("stretch"))
        students = {}
        for sid, st in sorted(run["students"].items()):
            earned = sum(a["earned"] for a in st["answers"].values())
            mine = sum(a["possible"] for a in st["answers"].values()) + \
                sum(S.form_items(key, st["form"])[q]["points"] for q in st.get("missing", []))
            students[sid] = {"earned": round(earned, 2), "possible": mine, "missing": st.get("missing", []),
                             "help": bool(st["support"]),
                             "version": run["versions"].get(st["form"], {}).get("name", "")}
        out.append({"id": f"w{len(out) + 1}", "title": run["title"], "date": run["date"], "possible": possible,
                    "students": students})
    return out


def build(folder: Path, out: Path | None = None, roster_path: Path | None = None, class_name: str = "") -> dict:
    """gradebook.html in out (default: FOLDER/progress). The roster is FOLDER/roster.csv unless one is given."""
    from . import prepare as P
    folder = Path(folder)
    if roster_path is None and (folder / "roster.csv").exists():
        roster_path = folder / "roster.csv"
    roster = P.load_roster(roster_path, PG.class_digits(folder)) if roster_path else None
    worksheets = scores(PG.collect(folder, roster))
    if not worksheets:
        raise PG.ProgressError(f"no marked worksheets under {folder} (practice sheets aren't graded): the "
                               "gradebook page reads each marking folder's results.json, which `check` writes")
    ids = sorted(roster or {sid for w in worksheets for sid in w["students"]})
    places = {sid: _place(sid) for sid in ids}
    in_order = all(places.values()) and len({sid[0] for sid in ids if len(sid) == 4}) <= 1 \
        and len(set(places.values())) == len(ids)
    if in_order:
        ids.sort(key=places.get)
    data = {"class": class_name or folder.name, "ids": ids, "numbered": in_order, "roster": roster is not None,
            "worksheets": worksheets}
    out = Path(out or folder / "progress")
    out.mkdir(parents=True, exist_ok=True)
    (out / "gradebook.html").write_text(gradebook_html(data))
    incomplete = [(w["title"], sid, s["missing"]) for w in worksheets for sid, s in w["students"].items()
                  if s["missing"]]
    return {"out": out / "gradebook.html", "worksheets": worksheets, "ids": ids, "numbered": in_order,
            "roster": roster_path, "incomplete": incomplete}


def gradebook_html(data: dict) -> str:
    """One self-contained page. It holds class IDs and scores only; names come from files the teacher opens."""
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")  # no "</script>" or "<!--" inside
    return (_PAGE.replace("{{PLATFORMS}}", _PLATFORMS).replace("{{TITLE}}", html.escape(f"{data['class']}: gradebook"))
            .replace("{{DATA}}", payload))


_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
<title>{{TITLE}}</title>
<style>
:root { --bg:#fbfaf7; --card:#ffffff; --ink:#1f2328; --muted:#5f6670; --line:#e3e0d8; --accent:#2453a6;
  --accent-bg:#eaf0fb; --warn:#8a5d00; --warn-bg:#fbf3df; --bad:#a8392f; --bad-bg:#fbe8e5; --ok:#2e7d4f; }
@media (prefers-color-scheme: dark) { :root { --bg:#16181b; --card:#1f2226; --ink:#e8e6e1; --muted:#a3a8ae;
  --line:#33373c; --accent:#8fb0f0; --accent-bg:#22304a; --warn:#e6c06a; --warn-bg:#332b1d; --bad:#f0928a;
  --bad-bg:#3a2321; --ok:#7fd29e; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font: 15px/1.45 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 20px 16px 64px; }
h1 { font-size: 26px; margin: 0 0 4px; } h2 { font-size: 19px; margin: 32px 0 8px; } h3 { font-size: 15px; margin: 0 0 6px; }
.sub { color: var(--muted); margin: 0 0 14px; }
.note { font-size: 13px; color: var(--muted); border-left: 3px solid var(--line); padding: 2px 10px; margin: 10px 0 0; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
.label, .muted { color: var(--muted); } .label { font-size: 13px; }
.row { display: flex; gap: 8px 14px; align-items: center; flex-wrap: wrap; margin: 8px 0; }
.sheet { display: flex; gap: 10px; align-items: baseline; padding: 4px 0; }
.sheet input { flex: none; }
ol.steps { margin: 6px 0 0; padding-left: 22px; } ol.steps li { margin: 3px 0; }
.scroll { overflow-x: auto; background: var(--card); border: 1px solid var(--line); border-radius: 10px; margin-top: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { padding: 6px 9px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }
th { font-weight: 600; color: var(--muted); }
td.n { font-variant-numeric: tabular-nums; white-space: nowrap; }
tr.off td { color: var(--muted); }
.msgs { display: grid; gap: 6px; margin-top: 10px; }
.msg { border-radius: 8px; padding: 7px 10px; font-size: 14px; }
.msg.warn { background: var(--warn-bg); color: var(--warn); } .msg.bad { background: var(--bad-bg); color: var(--bad); }
.msg.ok { color: var(--ok); border: 1px solid var(--line); }
a { color: var(--accent); }
select, button, input, textarea { font: inherit; color: var(--ink); }
select, button { padding: 6px 10px; border-radius: 8px; border: 1px solid var(--line); background: var(--card); cursor: pointer; }
button.main { background: var(--accent); color: var(--bg); border-color: var(--accent); font-weight: 600; }
button:disabled { opacity: .5; cursor: not-allowed; }
button:focus-visible, select:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
summary { cursor: pointer; } details[open] summary { margin-bottom: 6px; }
textarea { width: 100%; min-height: 90px; padding: 8px; border-radius: 8px; border: 1px solid var(--line); background: var(--bg); }
td select { padding: 3px 6px; }
[hidden] { display: none !important; }
</style></head>
<body><main>
<h1 id="title"></h1>
<p class="sub" id="subtitle"></p>
<p class="note">This page stays on this computer: it needs no internet, and it can't send anything anywhere. Your
gradebook's file has your students' names, so open it here, and don't give it to Claude.</p>

<section id="pick"><h2>1. Which worksheets</h2>
<div class="card"><div id="sheets"></div>
<div class="row" role="radiogroup" aria-label="Score as"><span class="label">Score as</span>
<label><input type="radio" name="scale" value="points" checked> points</label>
<label><input type="radio" name="scale" value="percent"> percent</label></div>
<p class="label" id="scale-note"></p></div></section>

<section id="file"><h2>2. Your gradebook</h2>
<div class="card"><div class="row"><label for="platform"><strong>Gradebook</strong></label><select id="platform"></select></div>
<div id="export-steps"></div>
<div class="row" id="file-row" hidden><label for="export-file"><strong>Then open the file it saved</strong></label>
<input type="file" id="export-file" accept=".csv,.txt,text/csv,text/plain"></div>
<p class="label" id="file-msg" role="status"></p></div></section>

<section id="match"><h2>3. Check who's who</h2>
<p class="label" id="match-how"></p>
<details class="card" id="list-box"><summary><strong>Match by your own list of class IDs and names</strong></summary>
<p class="label">If students joined or left since the class was numbered, the order is off. Open or paste your own list,
with each student's class ID and name (the class list from the ID cards, typed up), and students are matched by
name instead. The list stays in this page; it isn't saved.</p>
<textarea id="list-text" spellcheck="false" autocomplete="off" aria-label="Class IDs and names"></textarea>
<div class="row"><button type="button" id="list-use">Match by this list</button>
<label class="muted">or open a file <input type="file" id="list-file" accept=".csv,.txt,text/csv,text/plain"></label>
<button type="button" id="list-clear">Match by order again</button></div></details>
<div class="msgs" id="msgs" role="status"></div>
<div class="scroll"><table id="table"></table></div></section>

<section id="save-section"><h2>4. Save it and import it</h2>
<div class="card"><div id="targets"></div>
<div class="row"><button type="button" class="main" id="save">Save the file to import</button>
<button type="button" id="copy">Copy the scores in this order</button>
<button type="button" id="save-list">Save my list of class IDs and names</button></div>
<p class="label" id="save-msg" role="status"></p>
<div id="import-steps"></div>
<p class="note">The list of class IDs and names is for next time, here and in the progress dashboard's Show names.
Keep it on this computer, outside the Paper Loop folder, and don't give it to Claude.</p></div></section>
</main>
<script type="application/json" id="data">{{DATA}}</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const $ = id => document.getElementById(id);
const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k) ? o[k] : undefined;
const el = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) { if (v === undefined || v === null || v === false) continue;
    if (k === "class") e.className = v; else if (k.startsWith("on")) e[k] = v; else e.setAttribute(k, v === true ? "" : v); }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined) e.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  return e; };
const when = iso => { const d = new Date(iso + "T12:00:00"); return isNaN(d) ? iso : d.toLocaleDateString(undefined, {month: "short", day: "numeric"}); };
const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;
const num = x => String(Math.round(x * 100) / 100);
const W = D.worksheets, ids = D.ids;

// --- CSV in and out ------------------------------------------------------------------------------------
function parseCSV(text) {  // quotes, doubled quotes, and line breaks inside quotes; commas, tabs, or semicolons
  text = text.replace(/^\uFEFF/, "");
  const first = text.split(/\r?\n/, 1)[0];
  const sep = [",", "\t", ";"].map(c => [c, first.split(c).length]).sort((a, b) => b[1] - a[1])[0][0];
  const rows = []; let row = [], cur = "", q = false;
  for (let i = 0; i < text.length; i++) { const ch = text[i];
    if (q) { if (ch === '"' && text[i + 1] === '"') { cur += '"'; i++; } else if (ch === '"') q = false; else cur += ch; }
    else if (ch === '"') q = true;
    else if (ch === sep) { row.push(cur); cur = ""; }
    else if (ch === "\n" || ch === "\r") { if (ch === "\r" && text[i + 1] === "\n") i++; row.push(cur); rows.push(row); row = []; cur = ""; }
    else cur += ch; }
  if (cur || row.length) { row.push(cur); rows.push(row); }
  return rows.filter(r => r.some(c => c.trim()));
}
const cell = v => { v = v === undefined || v === null ? "" : String(v); return /[",\r\n]/.test(v) || /^\s|\s$/.test(v) ? `"${v.replace(/"/g, '""')}"` : v; };
const toCSV = rows => rows.map(r => r.map(cell).join(",")).join("\r\n") + "\r\n";
function download(text, name, type = "text/csv") {
  const a = el("a", {href: URL.createObjectURL(new Blob([text], {type: type + ";charset=utf-8"})), download: name});
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
const slug = s => s.replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "").toLowerCase() || "class";

// --- Class IDs in the order of the teacher's class list -----------------------------------------------
// Setup numbers students in the order of the teacher's own list: the class, the place (01-99), a check digit.
const place = id => id.length <= 2 ? +id : (id.length === 4 && (+id[0] + +id[1] + +id[2]) % 10 === +id[3]) ? +id.slice(1, 3) : null;
const placeOf = Object.fromEntries(ids.map((id, k) => [id, D.numbered ? place(id) : k + 1]));
function idAt(n) {  // the nth student's class ID
  if (!D.numbered) return ids[n - 1] || null;
  let id;
  if (ids[0].length <= 2) id = String(n).padStart(2, "0");
  else { const c = ids[0][0], p = String(n).padStart(2, "0"); id = c + p + ((+c + +p[0] + +p[1]) % 10); }
  return n <= 99 && (!D.roster || ids.includes(id)) ? id : null;
}
const known = new Set(ids);

// --- Scores --------------------------------------------------------------------------------------------
let chosen = new Set(W.length ? [W[W.length - 1].id] : []);
let scale = "points";
const picked = () => W.filter(w => chosen.has(w.id));
let targets = {};  // worksheet → the column of the teacher's file it goes in (else a new column)
const outOf = w => { const k = own(targets, w.id), c = k !== undefined && file ? file.columns.find(c => c.k === k) : null;
  return c && c.possible > 0 ? c.possible : w.possible; };  // an existing Canvas assignment's own points
function score(sid, w) {  // {v: what goes in the gradebook ("" for none), why: a note for the teacher}
  const s = sid ? own(w.students, sid) : undefined;
  if (!sid) return {v: "", why: ""};
  if (!s) return {v: "", why: "no score: absent, or no page scanned"};
  if (s.missing.length) return {v: "", why: `not finished marking: Q${s.missing.join(", Q")} still in the review pile`};
  const frac = s.possible ? s.earned / s.possible : 0, total = outOf(w);
  const version = s.possible !== w.possible ? `${num(s.earned)} of ${s.possible} on their version` : "";
  if (scale === "percent") return {v: num(frac * 100), why: version};
  if (s.possible === total) return {v: num(s.earned), why: ""};
  return {v: num(frac * total), why: (version || `${num(s.earned)} of ${s.possible}`) + `, scaled to ${total}`};
}
const ctx = () => ({score, targets, scale});
const columnName = w => `${w.title} (${when(w.date)})`;

// --- Names, from the teacher's own files only ----------------------------------------------------------
// A name is matched as its words in any order, so "Lopez, Ana" is "Ana Lopez".
const nameKey = s => s.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^\p{L}\p{N}'\s-]+/gu, " ")
  .split(/[\s-]+/).filter(Boolean).sort().join(" ");
let list = null;  // {key: id} from the teacher's own list, while this page is open
function readList(text) {
  const lines = parseCSV(text);
  const out = {}; let byPlace = 0;
  for (const f of lines) {
    const k = f.findIndex(x => /^\s*\d{1,6}\s*$/.test(x));
    const name = f.filter((x, j) => j !== k && x.trim() && !/^(id|name|student|class id)$/i.test(x.trim())).join(" ");
    if (!name) continue;
    if (k >= 0) { const id = f[k].trim().padStart(ids[0] ? ids[0].length : 4, "0"); out[nameKey(name)] = id; }
    else { const id = idAt(++byPlace); if (id) out[nameKey(name)] = id; }  // a plain list, in class-list order
  }
  return out;
}

// --- The gradebook's file -------------------------------------------------------------------------------
let platform = null, file = null, rows = [];  // rows: one per student in the file, {name, key, id, by}
const header = (rows, test) => rows.findIndex(r => r.some(c => test(c.trim())));
const col = (head, ...names) => { const low = head.map(h => h.trim().toLowerCase());
  for (const n of names) { const k = low.indexOf(n.toLowerCase()); if (k >= 0) return k; } return -1; };

{{PLATFORMS}}

// Each student in the file gets a class ID: one the teacher chose, else from their list by name, else the next
// in order. A student the teacher sets aside (joined later, say) drops out of the order, so everyone after
// them lines up again; and an ID chosen for one student isn't given to another.
let pins = {}, confirmed = false;  // pins: row → the class ID the teacher chose ("" for none)
function match() {
  const used = new Set(Object.values(pins).filter(Boolean));
  let n = 1;
  rows = file ? file.students.map((s, k) => {
    const key = nameKey(s.name);
    if (own(pins, k) !== undefined) return {...s, key, id: pins[k] || null, by: "you"};
    if (list) { const id = own(list, key); return {...s, key, id: id && !used.has(id) ? id : null, by: "list"}; }
    let id = null;
    while (!id && n <= 99) { const next = idAt(n++); if (next && !used.has(next)) id = next; }
    return {...s, key, id, by: "order"};
  }) : [];
  draw();
}
const restart = () => { pins = {}; confirmed = false; targets = {}; match(); };

function draw() {
  const sheets = picked();
  $("save").disabled = $("copy").disabled = $("save-list").disabled = true;
  const t = $("table"); t.replaceChildren();
  const box = $("msgs"); box.replaceChildren();
  const say = (kind, text) => box.append(el("div", {class: "msg " + kind}, text));
  if (!platform) return;
  if (!file) {
    $("match-how").textContent = platform.noFile
      ? "Without a file, here are the scores in class ID order (the order of your class list when the class was numbered)."
      : "Open your gradebook's file in step 2, and each student in it shows here with their class ID.";
    if (platform.noFile) {
      t.append(el("thead", {}, el("tr", {}, el("th", {}, "#"), el("th", {}, "Class ID"), ...sheets.map(w => el("th", {}, columnName(w))), el("th", {}, "Note"))));
      const b = el("tbody");
      ids.forEach((id, k) => { const sc = sheets.map(w => score(id, w));
        b.append(el("tr", {}, el("td", {class: "n"}, placeOf[id]), el("td", {class: "n"}, id), ...sc.map(s => el("td", {class: "n"}, s.v)), el("td", {class: "label"}, sc.map(s => s.why).filter(Boolean).join("; ")))); });
      t.append(b);
      $("copy").disabled = !sheets.length;
    }
    return;
  }
  $("match-how").textContent = list
    ? "Matched by name, from your list. Choose a class ID for anyone it couldn't match."
    : "Matched by order: the 1st student in your file is the 1st class ID, and so on, as the class was numbered. Check a few names against your class list.";
  const count = {};
  for (const r of rows) if (r.id) count[r.id] = (count[r.id] || 0) + 1;
  const twice = Object.keys(count).filter(id => count[id] > 1);
  const left = ids.filter(id => !count[id] && sheets.some(w => own(w.students, id)));
  const none = rows.filter(r => !r.id);
  // By order, a different count means someone joined or left since the class was numbered: until the teacher
  // has checked, saving waits.
  const unsure = !list && D.roster && rows.length !== ids.length;
  if (unsure) {
    const ok = el("input", {type: "checkbox", id: "confirm", checked: confirmed, onchange: e => { confirmed = e.target.checked; draw(); }});
    box.append(el("div", {class: "msg warn"}, `Your file has ${plural(rows.length, "student")}, and this class has ${plural(ids.length, "class ID")}. If someone joined or left since the class was numbered, the order is off from there. Match by your list above, or fix it below: give a student who joined later their own class ID (or none), and everyone after them lines up again.`,
      el("div", {class: "row"}, ok, el("label", {for: "confirm"}, "I've checked each class ID below"))));
  }
  if (twice.length) say("bad", `Two students have class ID ${twice.join(", ")}. Fix one before saving.`);
  if (left.length) say("warn", `Not matched to anyone in your file, so their scores won't go in: ${left.join(", ")}.`);
  const unfinished = rows.filter(r => r.id && sheets.some(w => { const s = own(w.students, r.id); return s && s.missing.length; }));
  if (unfinished.length) say("warn", `Left blank until marking is finished (pages in the review pile): ${unfinished.map(r => r.name).join(", ")}.`);
  if (none.length && list) say("warn", `${plural(none.length, "student")} in your file couldn't be matched by name. Choose their class IDs below, or leave them blank.`);
  if (!twice.length && !left.length && !none.length && !unsure) say("ok", `All ${plural(rows.length, "student")} matched. Check a few names, then save.`);
  t.append(el("thead", {}, el("tr", {}, el("th", {}, "#"), el("th", {}, "Name in your file"), el("th", {}, "Class ID"),
    ...sheets.map(w => el("th", {}, columnName(w))), el("th", {}, "Note"))));
  const b = el("tbody");
  rows.forEach((r, k) => {
    const pick = el("select", {"aria-label": `Class ID for ${r.name}`, onchange: e => { pins[k] = e.target.value; match(); }},
      el("option", {value: ""}, "none"), ...ids.map(id => el("option", {value: id, selected: id === r.id}, id)));
    const sc = sheets.map(w => score(r.id, w));
    b.append(el("tr", {class: r.id ? "" : "off"}, el("td", {class: "n"}, k + 1), el("td", {}, r.name), el("td", {}, pick),
      ...sc.map(s => el("td", {class: "n"}, s.v)), el("td", {class: "label"}, [twice.includes(r.id) ? "same class ID as another student" : "", ...sc.map(s => s.why)].filter(Boolean).join("; "))));
  });
  t.append(b);
  drawTargets(sheets);
  const placed = !platform.needsTarget || sheets.every(w => own(targets, w.id) !== undefined);
  const ready = sheets.length && !twice.length && rows.some(r => r.id) && (!unsure || confirmed);
  $("save").disabled = !ready || !placed || !platform.write;
  $("copy").disabled = !ready;
  $("save-list").disabled = !rows.some(r => r.id);
}

function drawTargets(sheets) {
  const box = $("targets"); box.replaceChildren();
  if (!file || !platform.targets || !file.columns.length || !sheets.length) return;
  box.append(el("p", {class: "label"}, platform.targetNote || ""));
  for (const w of sheets) {
    const k = own(targets, w.id);
    const pick = el("select", {id: "t-" + w.id, onchange: e => { e.target.value === "" ? delete targets[w.id] : targets[w.id] = +e.target.value; draw(); }},
      el("option", {value: ""}, platform.needsTarget ? "choose a column" : platform.newLabel || "a new column at the end"),
      ...file.columns.map(c => el("option", {value: c.k, selected: c.k === k}, c.name + (c.possible > 0 ? ` (${num(c.possible)} points)` : ""))));
    box.append(el("div", {class: "row"}, el("label", {for: "t-" + w.id}, el("strong", {}, columnName(w)), " goes in"), pick));
  }
}
function steps(target, title, list) {
  target.replaceChildren();
  if (list && list.length) target.append(el("h3", {style: "margin-top:10px"}, title), el("ol", {class: "steps"}, ...list.map(s => el("li", {}, s))));
}
function choosePlatform(pid) {
  platform = PLATFORMS.find(p => p.id === pid) || null;
  try { localStorage.setItem("paper-loop-gradebook", pid); } catch (e) {}  // which gradebook, for next time; nothing else
  file = null; $("export-file").value = ""; $("file-msg").textContent = ""; $("save-msg").textContent = "";
  const p = platform || {noFile: true};
  steps($("export-steps"), p.write ? "Save a file from it" : "", p.exportSteps);
  steps($("import-steps"), platform ? (p.noFile ? "Then" : "Then, in " + p.name.replace(/ \(.*\)$/, "")) : "", p.importSteps);
  $("file-row").hidden = !platform || !!p.noFile;
  $("save").hidden = !p.write;
  $("save-list").hidden = $("list-box").hidden = !platform || !!p.noFile;
  $("copy").hidden = !platform;
  $("save-section").hidden = $("match").hidden = !platform;
  restart();
}
function openFile(f) {
  if (/\.xlsx?$/i.test(f.name)) { $("file-msg").textContent = "That's a spreadsheet file. Open it in Excel or Google Sheets and save it as CSV, then open the CSV here."; return; }
  f.text().then(text => {
    const got = platform.read(parseCSV(text));
    if (got.error) { file = null; $("file-msg").textContent = got.error; }
    else { file = {...got, filename: f.name}; $("file-msg").textContent = `Read ${plural(file.students.length, "student")} from ${f.name}.` + (got.note ? " " + got.note : ""); }
    restart();
  });
}

// --- Saving ---------------------------------------------------------------------------------------------
$("save").onclick = () => {
  const files = [].concat(platform.write(file, rows, picked(), ctx()))
    .map(f => ({...f, name: f.name || `${platform.id}-import-${slug(D.class)}.csv`}));
  files.forEach((f, k) => setTimeout(() => download(f.text, f.name), k * 400));
  $("save-msg").textContent = `Saved ${files.map(f => f.name).join(", ")} to your downloads. Import ${files.length === 1 ? "it" : "them"} as below.`;
};
$("copy").onclick = () => {
  const sheets = picked();
  const lines = file ? rows.map(r => sheets.map(w => score(r.id, w).v).join("\t")) : ids.map(id => sheets.map(w => score(id, w).v).join("\t"));
  const text = lines.join("\n") + "\n";
  const done = () => { $("save-msg").textContent = `Copied ${plural(lines.length, "row")} of scores, in the order shown here.`; };
  const fail = () => { const ta = el("textarea", {"aria-label": "Scores to copy", readonly: true}); ta.value = text; $("save-msg").replaceChildren("Copy these (Ctrl+C or ⌘C):", ta); ta.select(); };
  if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, fail); else fail();
};
$("save-list").onclick = () => {
  const out = [["id", "name"], ...rows.filter(r => r.id).sort((a, b) => placeOf[a.id] - placeOf[b.id]).map(r => [r.id, r.name])];
  download(toCSV(out), `class-ids-and-names-${slug(D.class)}.csv`);
  $("save-msg").textContent = "Saved your list to your downloads. Keep it on this computer, outside the Paper Loop folder, and don't give it to Claude.";
};

// --- Setup ----------------------------------------------------------------------------------------------
$("title").textContent = D.class + ": scores for your gradebook";
$("subtitle").textContent = `${plural(W.length, "worksheet")} marked, ${plural(ids.length, "class ID")}. Students show by class ID until you open your gradebook's file.`;
const sheetsBox = $("sheets");
W.slice().reverse().forEach(w => {
  const scored = Object.values(w.students).filter(s => !s.missing.length).length;
  const unfinished = Object.values(w.students).length - scored;
  const box = el("input", {type: "checkbox", id: "w-" + w.id, checked: chosen.has(w.id), onchange: e => { e.target.checked ? chosen.add(w.id) : chosen.delete(w.id); draw(); }});
  sheetsBox.append(el("div", {class: "sheet"}, box, el("label", {for: "w-" + w.id}, el("strong", {}, w.title), ` · ${when(w.date)} · ${plural(w.possible, "point")} · ${scored} scored` + (unfinished ? `, ${unfinished} not finished marking` : ""))));
});
const scaleNote = () => { $("scale-note").textContent = scale === "points"
  ? "Points out of each worksheet's total. A student whose version had fewer points is scaled to the same total, so the assignment's points stay the same for everyone."
  : "Percent of the points on each student's own copy."; };
document.querySelectorAll("input[name=scale]").forEach(r => r.onchange = e => { scale = e.target.value; scaleNote(); draw(); });
scaleNote();
const pf = $("platform");
pf.append(el("option", {value: ""}, "Choose your gradebook"));
for (const p of PLATFORMS) pf.append(el("option", {value: p.id}, p.name));
let last = ""; try { last = localStorage.getItem("paper-loop-gradebook") || ""; } catch (e) {}
if (PLATFORMS.some(p => p.id === last)) pf.value = last;
pf.onchange = e => choosePlatform(e.target.value);
$("export-file").onchange = e => { const f = e.target.files[0]; if (f) openFile(f); };
$("list-use").onclick = () => { list = readList($("list-text").value); $("list-text").value = ""; restart(); };
$("list-file").onchange = e => { const f = e.target.files[0]; if (!f) return; f.text().then(t => { list = readList(t); restart(); }); e.target.value = ""; };
$("list-clear").onclick = () => { list = null; restart(); };
choosePlatform(pf.value);
</script></body></html>
"""

# Each gradebook: how to save a file from it, how to read that file's students, and what to import back. From
# each one's own help pages (November 2026). Google Classroom and Infinite Campus don't import scores from a file,
# so for them the page is a list to type in from.
_PLATFORMS = r"""
const NAME_HEAD = /^(student|student name|name|full name|legal name|last name|last|surname|first name|first)$/i;
const NOT_A_STUDENT = /^(points possible|manual posting|muted|test student|student, test)$/i;
// The header row is the first with a column of names (and the gradebook's own student IDs, when it needs them).
function readStudents(rows, refs, need) {
  const h = rows.findIndex(r => r.some(c => NAME_HEAD.test(c.trim())) && (!refs || col(r, ...refs) >= 0));
  if (h < 0) return {error: need};
  const head = rows[h];
  const full = col(head, "student name", "student", "name", "full name", "legal name");
  const last = col(head, "last name", "last", "surname"), first = col(head, "first name", "first");
  const ref = refs ? col(head, ...refs) : -1;
  const students = [];
  for (let r = h + 1; r < rows.length; r++) {
    const row = rows[r];
    const name = ((full >= 0 ? row[full] : [row[first], row[last]].filter(Boolean).join(" ")) || "").trim();
    if (!name || NOT_A_STUDENT.test(name) || (ref >= 0 && !(row[ref] || "").trim())) continue;
    students.push({name, r, ref: ref >= 0 ? row[ref].trim() : ""});
  }
  if (!students.length) return {error: "That file has a header row, but no students under it."};
  const skip = new Set([full, last, first, ref]);
  return {rows, h, students, columns: head.map((name, k) => ({k, name: name.trim()})).filter(c => c.name && !skip.has(c.k))};
}
// The teacher's own file, with each worksheet's scores in the column they chose or a new one at the end. A
// student with no score here keeps whatever the file had.
function fillColumns(file, matched, sheets, ctx) {
  const out = file.rows.map(r => r.slice());
  const width = Math.max(...out.map(r => r.length));
  out.forEach(r => { while (r.length < width) r.push(""); });
  const where = sheets.map(w => { const k = own(ctx.targets, w.id);
    if (k !== undefined) return k;
    out.forEach((r, j) => r.push(j === file.h ? columnName(w) : ""));
    return out[file.h].length - 1; });
  matched.forEach((m, k) => { const r = out[file.students[k].r];
    sheets.forEach((w, j) => { const v = m.id ? ctx.score(m.id, w).v : ""; if (v !== "") r[where[j]] = v; }); });
  return {text: toCSV(out)};
}
// Rows only for students with a score, so nothing already in the gradebook is touched for anyone else.
const scored = (file, matched, sheets, ctx, row) => matched.flatMap((m, k) => {
  const vals = sheets.map(w => m.id ? ctx.score(m.id, w).v : "");
  return vals.some(v => v !== "") ? [row(file.students[k], vals, file.rows[file.students[k].r])] : []; });
// One file per worksheet, for gradebooks that import one assignment at a time.
const perSheet = (prefix, head) => (file, matched, sheets, ctx) => sheets.map(w => ({name: `${prefix}-${slug(w.title)}-${w.date}.csv`,
  text: toCSV([head, ...scored(file, matched, [w], ctx, (s, vals) => [s.ref, s.name, vals[0]])])}));

// Canvas: the header starts Student, ID; then SIS and section columns; then a column per assignment.
const CANVAS_INFO = ["student", "id", "sis user id", "sis login id", "integration id", "root account", "section"];
const CANVAS_TOTAL = /^(unposted )?(current|final) (score|points|grade)$|override/i;
function readCanvas(rows) {
  const h = rows.findIndex(r => (r[0] || "").trim().toLowerCase() === "student" && (r[1] || "").trim().toLowerCase() === "id");
  if (h < 0) return {error: "That doesn't look like a Canvas gradebook export: its first row should start with Student and ID. In Canvas, use Grades, then Export, then Export Entire Gradebook."};
  const head = rows[h].map(c => c.trim());
  const info = head.map((c, k) => CANVAS_INFO.includes(c.toLowerCase()) ? k : -1).filter(k => k >= 0);
  const pp = rows.find((r, j) => j > h && /^points possible$/i.test((r[0] || "").trim()));
  const students = [];
  for (let r = h + 1; r < rows.length; r++) {
    const name = (rows[r][0] || "").trim();
    if (!name || NOT_A_STUDENT.test(name) || !(rows[r][1] || "").trim()) continue;
    students.push({name, r, ref: rows[r][1].trim()});
  }
  if (!students.length) return {error: "That Canvas file has no students in it."};
  const last = Math.max(...info);
  const columns = head.map((name, k) => ({k, name, possible: pp ? parseFloat(pp[k]) : NaN}))
    .filter(c => c.k > last && c.name && !CANVAS_TOTAL.test(c.name));
  return {rows, h, students, info, pp, columns};
}
// A fresh file: the student columns from Canvas's own export, a Points Possible row, and one column per worksheet.
// An existing assignment keeps its exact header (with its Canvas ID); a student with no score keeps their grade.
function writeCanvas(file, matched, sheets, ctx) {
  const head = file.rows[file.h];
  const cols = sheets.map(w => { const k = own(ctx.targets, w.id);
    if (k !== undefined) return {w, k, name: head[k], possible: file.pp ? file.pp[k] : ""};
    return {w, k: -1, name: columnName(w), possible: ctx.scale === "percent" ? 100 : w.possible}; });
  const out = [[...file.info.map(k => head[k]), ...cols.map(c => c.name)],
    ["Points Possible", ...file.info.slice(1).map(() => ""), ...cols.map(c => c.possible)]];
  matched.forEach((m, j) => { const row = file.rows[file.students[j].r];
    out.push([...file.info.map(k => row[k] || ""), ...cols.map(c => { const v = m.id ? ctx.score(m.id, c.w).v : "";
      if (v === "") return c.k >= 0 ? row[c.k] || "" : "";
      return c.k >= 0 && ctx.scale === "percent" ? v + "%" : v; })]); });
  return {text: toCSV(out), name: `canvas-import-${slug(D.class)}.csv`};
}

const PLATFORMS = [
  {id: "canvas", name: "Canvas", targets: true, newLabel: "a new assignment", read: readCanvas, write: writeCanvas,
   exportSteps: ["In Canvas, open the course and go to Grades.", "Choose Export, then Export Entire Gradebook, and save the file."],
   importSteps: ["In Grades, choose Import, choose the file you saved here, and upload it.",
     "Canvas shows what will change. A new column becomes a new assignment: check its points possible, then save the changes.",
     "If your course uses grading periods and Canvas won't make the new assignment, make it in Canvas first, export again, and choose its column in step 4."],
   targetNote: "Already made the assignment in Canvas? Choose its column, and anyone without a score here keeps their grade."},
  {id: "classroom", name: "Google Classroom (type them in)", read: rows => readStudents(rows, null, "Couldn't find your students' names in that file. Open the CSV Classroom downloaded, with a column called Name or Last Name and First Name."),
   exportSteps: ["Classroom can't import scores from a file, so this page makes a list to type them in from.",
     "To see names here, download grades as a CSV from Classroom (an assignment's Student work page has it under the settings menu), and open it."],
   importSteps: ["In Classroom, open the assignment's Student work page (or the Grades tab) and type each student's score.",
     "Classroom keeps them as draft grades until you return the work."]},
  {id: "powerteacher", name: "PowerSchool (PowerTeacher Pro)", write: perSheet("powerteacher", ["Student Number", "Student Name", "Score"]),
   read: rows => readStudents(rows, ["student number", "student_number", "student #", "student no", "student id", "number"], "Couldn't find a column of student numbers with names. Open the score template you exported from PowerTeacher Pro, saved from Excel as CSV UTF-8."),
   exportSteps: ["In PowerTeacher Pro, make the assignment for the worksheet if you haven't (Grading, then Assignment List).",
     "Select the assignment, click the gear, and choose Export Score Template.", "Open it in Excel, save it with Save As, CSV UTF-8, and open that file here."],
   importSteps: ["PowerTeacher Pro imports one assignment at a time, so you get one file per worksheet, with a row for each student who has a score.",
     "In Assignment List, select the assignment, click the gear, and choose Import Scores. Choose that worksheet's file, with format CSV.",
     "The file has a header row, so leave Include First Row unticked. Match Student Number to the students and Score to the scores, and set File Score Type to points (or percent, if you chose percent here).",
     "Review any alerts, then Import."]},
  {id: "schoology", name: "Schoology", write: (file, matched, sheets, ctx) => ({name: `schoology-import-${slug(D.class)}.csv`,
     text: toCSV([["Name", "Unique User ID", ...sheets.map(columnName)], ...scored(file, matched, sheets, ctx, (s, vals) => [s.name, s.ref, ...vals])])}),
   read: rows => readStudents(rows, ["unique user id", "unique id"], "Couldn't find the Unique User ID column, which Schoology matches students by. Open the gradebook you exported from Schoology as CSV."),
   exportSteps: ["In Schoology, open the course's Gradebook.", "From the more menu (⋯), choose Export, then Gradebook as CSV."],
   importSteps: ["In the Gradebook's more menu (⋯), choose Import, then choose the file you saved here and upload it.",
     "Match Unique User ID to the students, and each worksheet's column to New Assignment (or to an assignment you've already made). Preview, then confirm.",
     "A new assignment may need its category and grading period set before its grades show.",
     "Importing from a file is part of Schoology Enterprise. On the free Basic plan, type the scores in from the list above."]},
  {id: "campus", name: "Infinite Campus (type them in)", read: rows => readStudents(rows, null, "Couldn't find your students' names in that file. Open the CSV your Campus grade book exported, with a column of names."),
   exportSteps: ["Campus Instruction's grade book doesn't import scores from a file, so this page makes a list to type them in from.",
     "To see names here, export the class from the grade book (Grade Book Export, as CSV), and open it."],
   importSteps: ["In the grade book, open the assignment and type each student's score.",
     "If your district sends grades to Campus from Google Classroom or Schoology, you can enter them there instead."]},
  {id: "skyward", name: "Skyward", targets: true, needsTarget: true, write: fillColumns,
   read: rows => readStudents(rows, null, "Couldn't find your students' names in that file. Open the score entry file Skyward made, saved as CSV."),
   exportSteps: ["Make the assignment in your Skyward gradebook if you haven't.",
     "Educator Access Plus: in My Gradebook, go to Assignments, then Advanced Export/Import Assignment. Choose the assignment and Create File for Score Entry, and save it as CSV.",
     "Qmlativ: use Assignment Import in Teacher Access, if your district has turned it on.", "Open that file here, then choose its score column in step 4."],
   importSteps: ["Educator Access Plus: back in Advanced Export/Import Assignment, choose Import Scores From File and choose the file you saved here.",
     "Screens differ from district to district. If yours don't match, your district's Skyward contact can show you where score import is."],
   targetNote: "Choose the column in Skyward's file where each worksheet's scores go."},
  {id: "aeries", name: "Aeries", write: perSheet("aeries", ["Stu Id", "Student Name", "Score"]),
   read: rows => readStudents(rows, ["stu id", "student id", "stu#", "perm id", "student number", "id"], "Couldn't find a column of student IDs (Stu Id) with names. Open a CSV of your class from Aeries with each student's ID and name."),
   exportSteps: ["Make the assignment in your Aeries gradebook if you haven't.",
     "Save a list of your class with each student's ID (Stu Id) and name as a CSV file, and open it here. Your school's Aeries contact can tell you where to get one."],
   importSteps: ["You get one file per worksheet, with a row for each student who has a score.",
     "In Scores by Assignment, choose Import Scores from File. Choose that worksheet's file, tick Include Header, and upload it.",
     "Match Stu Id to Stu Id and Score to # Correct (Score), then Import Scores. Importing replaces any score already there for those students."]},
  {id: "brightspace", name: "D2L Brightspace", write: (file, matched, sheets, ctx) => {
     const head = file.rows[file.h], keep = [col(head, "orgdefinedid"), col(head, "username")].filter(k => k >= 0);
     return {name: `brightspace-import-${slug(D.class)}.csv`, text: toCSV([[...keep.map(k => head[k].trim()), ...sheets.map(w => columnName(w) + " Points Grade"), "End-of-Line Indicator"],
       ...scored(file, matched, sheets, ctx, (s, vals, row) => [...keep.map(k => row[k]), ...vals, "#"])])}; },
   read: rows => readStudents(rows, ["orgdefinedid", "username"], "Couldn't find an OrgDefinedId or Username column with names. Export your grades from Brightspace as CSV, with names and OrgDefinedId or Username."),
   exportSteps: ["In Brightspace, go to Grades, then Enter Grades, then Export.", "Export OrgDefinedId (or Username) with each student's first and last name, as CSV."],
   importSteps: ["In Grades, then Enter Grades, choose Import and choose the file you saved here.",
     "Tick the option to create grade items for unrecognized entries, and give each new item the worksheet's total as its maximum points (100 if you chose percent).",
     "Check the preview, then Import."]},
  {id: "other", name: "Another gradebook, or a spreadsheet", targets: true, write: fillColumns,
   read: rows => readStudents(rows, null, "Couldn't find a column of names in that file. It needs a header row with a column called Student, Name, or Last Name and First Name."),
   exportSteps: ["Save or download the class from your gradebook or spreadsheet as a CSV file: one row per student, with a header row that has a column called Student or Name (or Last Name and First Name)."],
   importSteps: ["The saved file is yours, with each worksheet's scores in the column you chose in step 4 or a new column at the end. Import it, or open it and copy the column into your gradebook."],
   targetNote: "Put a worksheet's scores in a column your file already has, or in a new column at the end."},
  {id: "none", name: "No file: copy the scores in class ID order", noFile: true,
   importSteps: ["Sort your gradebook in the order of your class list when the class was numbered, so the 1st student is the 1st class ID.",
     "Copy the scores here. If your gradebook takes a pasted column, click the first student's box for the assignment and paste; if not, type them in. Check a few students before you save."]},
];
"""
