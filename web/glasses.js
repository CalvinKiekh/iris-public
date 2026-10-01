/* iris on glasses: one card at a time, one axis of input.
 *
 * The whole screen is 576x288 monochrome, so this is not the phone UI made
 * small - it is a different program against the same API. Three rules:
 *
 *   1. Exactly one thing is visible. The wheel moves between things.
 *   2. Long text paginates into screenfuls; it never scrolls freely,
 *      because there is no scrollbar to judge your position by.
 *   3. A pending confirmation takes the screen. It is the only state that
 *      interrupts, because it is the only one that blocks work.
 *
 * Input is abstracted to four intents - next, prev, confirm, back - so the
 * RayNeo SDK only has to feed those in. Today they come from the wheel and
 * the arrow keys.
 */
/* Device profiles.
 *
 * The geometry is NOT hard-coded, because the numbers are not all public
 * yet. Even Realities publishes 576x288 for the G2. RayNeo does not publish
 * a pixel count for the iO - only 23.5 degrees FOV, monochrome green - so
 * its entry is an estimate, flagged as such, and meant to be corrected the
 * day the SDK ships. Everything downstream reads from here.
 */
const PROFILES = {
  g2: {
    label: "Even Realities G2",
    w: 576, h: 288, fs: 19, line: 22, tint: "#ffffff",
    note: "Herstellerangabe",
  },
  io: {
    label: "RayNeo iO",
    // Estimate: JBD-class monochrome green panel behind a 23.5° waveguide.
    // Replace w/h once RayNeo publishes them or the SDK reports them.
    w: 640, h: 480, fs: 22, line: 26, tint: "#7dff9b",
    note: "geschätzt — RayNeo nennt keine Pixelzahl",
  },
  narrow: {
    label: "Schmales Band",
    // Worst case worth designing against: a single-strip teleprompter.
    w: 480, h: 160, fs: 18, line: 21, tint: "#7dff9b",
    note: "Härtefall zum Gegenprüfen",
  },
};

let PROFILE = PROFILES.g2;
let LINES = 8;                // content lines under the status bar
let COLS = 44;                // characters per line

/* Derive rows and columns from the panel, measuring a real glyph rather
   than guessing: a monospace character's width is what decides COLS. */
function applyProfile(id) {
  PROFILE = PROFILES[id] || PROFILES.g2;
  const r = document.documentElement.style;
  r.setProperty("--gw", PROFILE.w + "px");
  r.setProperty("--gh", PROFILE.h + "px");
  r.setProperty("--fs", PROFILE.fs + "px");
  r.setProperty("--line", PROFILE.line + "px");
  r.setProperty("--fg", PROFILE.tint);
  document.body.style.width = PROFILE.w + "px";
  document.body.style.height = PROFILE.h + "px";

  const probe = document.createElement("span");
  probe.style.cssText = `position:absolute;visibility:hidden;white-space:pre;
    font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
    font-size:${PROFILE.fs}px`;
  probe.textContent = "0".repeat(50);
  document.body.appendChild(probe);
  const chW = probe.getBoundingClientRect().width / 50;
  probe.remove();

  COLS = Math.max(16, Math.floor((PROFILE.w - 16) / chW));
  const statusRow = 24;
  LINES = Math.max(3, Math.floor((PROFILE.h - statusRow - 12) / PROFILE.line));
  S.geometry = { cols: COLS, lines: LINES, profile: PROFILE };
  // Re-paginate what is already on screen against the new geometry.
  if (S.raw && S.raw.length) {
    S.cards = [];
    for (const c of S.raw) S.cards.push(...expand(c));
    S.idx = Math.max(0, S.cards.length - 1);
  }
  render();
  parent !== window && parent.postMessage(
    { irisGeometry: { cols: COLS, lines: LINES, id, note: PROFILE.note } }, "*");
}

const S = {
  token: "", session: null, es: null,
  cards: [],                  // flattened pages
  raw: [],                    // original cards, so geometry changes re-flow
  idx: 0,
  geometry: null,
  ask: null, askChoice: 1,    // 1 = allow (default under the finger)
  busy: false, mode: "", usage: null,
  screen: "cards",            // cards | list
  list: null,                 // {title, items:[{label,run}], idx}
};

/* ---------- api ---------- */

async function api(path, opts = {}) {
  const r = await fetch(path, {
    ...opts,
    headers: { "Authorization": "Bearer " + S.token,
               "Content-Type": "application/json", ...(opts.headers || {}) },
  });
  const b = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(b.error || r.statusText);
  return b;
}

/* ---------- text fitting ---------- */

/* Markdown markup is noise on a text panel: there is no bold, no colour and
   no room. Strip the syntax and keep the emphasis where it still reads -
   as capitals - so nothing shows up as literal asterisks on the glass. */
function plain(text) {
  return String(text ?? "")
    .replace(/```[\s\S]*?```/g, (m) =>            // fenced code -> bare lines
      m.replace(/```[a-zA-Z]*\n?/g, "").trimEnd())
    .replace(/`([^`\n]+)`/g, "$1")
    .replace(/\*\*([^*\n]+)\*\*/g, (_, t) => t.toUpperCase())
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1$2")
    .replace(/(^|[\s(])_([^_\n]+)_/g, "$1$2")
    .replace(/^#{1,6}\s+(.*)$/gm, (_, t) => t.toUpperCase())
    .replace(/^\s*[-*+]\s+/gm, "· ")
    .replace(/^\s*(\d+)[.)]\s+/gm, "$1. ")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")     // links -> their text
    .replace(/^\s*>\s?/gm, "")
    .replace(/\n{3,}/g, "\n\n");
}

/* Wrap to COLS, then cut into pages of LINES. Returns an array of strings,
   each one a full screen. This is why nothing ever overflows. */
function paginate(text, lines = LINES, cols = COLS) {
  const out = [];
  for (const para of plain(text).split("\n")) {
    if (!para.trim()) { out.push(""); continue; }
    let line = "";
    for (const word of para.split(/\s+/)) {
      if (!line.length) {
        line = word;
      } else if (line.length + 1 + word.length <= cols) {
        line += " " + word;
      } else {
        out.push(line); line = word;
      }
      // A single word longer than a line has to be broken somewhere.
      while (line.length > cols) { out.push(line.slice(0, cols)); line = line.slice(cols); }
    }
    out.push(line);
  }
  const pages = [];
  for (let i = 0; i < out.length; i += lines) {
    pages.push(out.slice(i, i + lines).join("\n").replace(/\s+$/, ""));
  }
  return pages.length ? pages : [""];
}

/* One incoming card can become several pages; each page is its own stop
   on the wheel, so you never have to hunt for a scroll gesture. */
function expand(card) {
  const mk = (label, body, mono) =>
    paginate(body).map((page, i, all) => ({
      label: all.length > 1 ? `${label} ${i + 1}/${all.length}` : label,
      body: page, mono, kind: card.kind,
    }));

  switch (card.kind) {
    case "sent":   return mk("DU", card.text);
    case "say":    return mk("CLAUDE", card.text);
    case "act":    return mk(card.tool.toUpperCase(), card.detail, true);
    case "result": return card.text
      ? mk(card.ok ? "ERGEBNIS" : "FEHLER", card.text, true) : [];
    case "done":   return [{ label: "", body: "· fertig ·", center: true, kind: "done" }];
    case "closed": return [{ label: "", body: "Sitzung beendet", center: true, kind: "done" }];
    case "error":  return mk("FEHLER", card.text);
    case "mode":   return [{ label: "", body: "Modus: " + card.mode, center: true, kind: "done" }];
    default:       return [];
  }
}

/* ---------- rendering ---------- */

function render() {
  const stage = document.getElementById("stage");

  // A confirmation always wins the screen.
  if (S.ask) {
    const detail = paginate(S.ask.detail, 4)[0];
    stage.innerHTML = `<div class="ask">
      <div class="what"><div class="k">BESTÄTIGEN</div><div class="body mono">${
        esc(S.ask.tool)}\n${esc(detail)}</div></div>
      <div class="opts">
        <div class="opt${S.askChoice === 0 ? " sel" : ""}">NEIN</div>
        <div class="opt${S.askChoice === 1 ? " sel" : ""}">JA</div>
      </div></div>`;
    setBar();
    return;
  }

  if (S.screen === "list" && S.list) {
    const { items, idx, title } = S.list;
    const first = Math.max(0, Math.min(idx - Math.floor(LINES / 2),
                                       items.length - LINES));
    const win = items.slice(Math.max(0, first), Math.max(0, first) + LINES);
    stage.innerHTML = `<div class="list">` + win.map((it) => {
      const i = items.indexOf(it);
      return `<div class="item${i === idx ? " sel" : ""}">${esc(cut(it.label))}</div>`;
    }).join("") + `</div>`;
    setBar(title, `${idx + 1}/${items.length}`);
    return;
  }

  if (!S.cards.length) {
    stage.innerHTML = `<div class="empty">bereit</div>`;
    setBar();
    return;
  }
  S.idx = Math.max(0, Math.min(S.idx, S.cards.length - 1));
  const c = S.cards[S.idx];
  stage.innerHTML =
    (c.label ? `<div class="k">${esc(c.label)}</div>` : "") +
    `<div class="body${c.mono ? " mono" : ""}"${
      c.center ? ' style="text-align:center;margin-top:70px"' : ""}>${esc(c.body)}</div>` +
    (S.idx < S.cards.length - 1 ? `<div class="hint">▼</div>` : "");
  setBar();
}

function setBar(who, pos) {
  document.getElementById("who").textContent =
    who || (S.session ? cut(S.session.label || "iris", 22) : "iris");
  document.getElementById("mode").textContent = shortMode(S.mode);
  const p = document.getElementById("pos");
  p.textContent = pos || (S.cards.length ? `${S.idx + 1}/${S.cards.length}` : "");
  p.className = "pos" + (S.busy ? " busy" : "");
}

/* Mode has to fit in a handful of characters up there. */
function shortMode(m) {
  return { manual: "FRAGT", default: "STD", acceptEdits: "EDITS",
           auto: "AUTO", plan: "PLAN", dontAsk: "STUMM",
           bypassPermissions: "FREI" }[m] || "";
}

const cut = (s, n = COLS) =>
  String(s ?? "").length > n ? String(s).slice(0, n - 1) + "…" : String(s ?? "");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (m) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));

/* ---------- four intents ---------- */

function next() {
  if (S.ask) { S.askChoice = 1 - S.askChoice; return render(); }
  if (S.screen === "list") {
    S.list.idx = (S.list.idx + 1) % S.list.items.length; return render();
  }
  S.idx = Math.min(S.idx + 1, S.cards.length - 1); render();
}

function prev() {
  if (S.ask) { S.askChoice = 1 - S.askChoice; return render(); }
  if (S.screen === "list") {
    S.list.idx = (S.list.idx - 1 + S.list.items.length) % S.list.items.length;
    return render();
  }
  S.idx = Math.max(0, S.idx - 1); render();
}

async function confirm() {
  if (S.ask) {
    const allow = S.askChoice === 1;
    const id = S.ask.request_id;
    S.ask = null; render();
    try {
      await api(`/api/sessions/${S.session.key}/permission`,
        { method: "POST", body: JSON.stringify({ request_id: id, allow }) });
    } catch { /* the bridge denies on timeout anyway */ }
    return;
  }
  if (S.screen === "list") {
    const it = S.list.items[S.list.idx];
    S.screen = "cards"; S.list = null;
    render();
    if (it && it.run) await it.run();
    return;
  }
  // On the card stream, confirm opens the menu.
  openMenu();
}

function back() {
  if (S.screen === "list") { S.screen = "cards"; S.list = null; render(); }
  else { S.idx = lastMeaningful(); render(); }
}

function showList(title, items) {
  S.list = { title, items, idx: 0 };
  S.screen = "list";
  render();
}

/* ---------- menu ---------- */

async function openMenu() {
  const items = [
    { label: "▸ Standard-Abfrage", run: openShortcuts },
    { label: "▸ Modus wechseln", run: openModes },
    { label: "▸ Anhalten", run: async () => {
        try { await api(`/api/sessions/${S.session.key}/interrupt`, { method: "POST" }); }
        catch {} } },
    { label: "▸ Zum Ende", run: async () => { S.idx = lastMeaningful(); render(); } },
    { label: "▸ Normale Ansicht", run: async () => {
        // Leave the glasses view for the phone UI, same session.
        const url = "/?token=" + encodeURIComponent(S.token);
        (parent !== window ? parent : window).location.href = url;
      } },
  ];
  showList("MENÜ", items);
}

async function openShortcuts() {
  const { shortcuts } = await api("/api/shortcuts");
  showList("ABFRAGE", shortcuts.map((sc) => ({
    label: sc.label,
    run: async () => {
      try {
        await api(`/api/sessions/${S.session.key}/message`,
          { method: "POST", body: JSON.stringify({ text: sc.text }) });
      } catch (e) { push({ kind: "error", text: e.message }); }
    },
  })));
}

async function openModes() {
  const { modes } = await api("/api/modes");
  showList("MODUS", modes.map((m) => ({
    label: (m.id === S.mode ? "✓ " : "  ") + m.label,
    run: async () => {
      try {
        await api(`/api/sessions/${S.session.key}/mode`,
          { method: "POST", body: JSON.stringify({ mode: m.id }) });
      } catch (e) { push({ kind: "error", text: e.message }); }
    },
  })));
}

/* ---------- stream ---------- */

/* Status markers ("fertig", mode changes) are punctuation, not content.
   Landing on one shows an empty screen where an answer should be. */
const FILLER = new Set(["done", "closed", "mode"]);

function lastMeaningful() {
  for (let i = S.cards.length - 1; i >= 0; i--) {
    if (!FILLER.has(S.cards[i].kind)) return i;
  }
  return Math.max(0, S.cards.length - 1);
}

function push(card) {
  const pages = expand(card);
  S.raw.push(card);
  if (S.raw.length > 300) S.raw.splice(0, S.raw.length - 300);
  if (!pages.length) return;
  const wasAtEnd = S.idx >= S.cards.length - 1;
  S.cards.push(...pages);
  if (S.cards.length > 300) S.cards.splice(0, S.cards.length - 300);
  // Follow along unless you scrolled back - but never park on a status
  // marker, which would show a near-empty screen instead of the answer.
  if (wasAtEnd) S.idx = lastMeaningful();
  render();
}

function connect() {
  if (S.es) S.es.close();
  const es = new EventSource(
    `/api/sessions/${S.session.key}/events?since=0&token=${encodeURIComponent(S.token)}`);
  S.es = es;
  es.onmessage = (ev) => {
    let c; try { c = JSON.parse(ev.data); } catch { return; }
    switch (c.kind) {
      case "ask":  S.ask = c; S.askChoice = 1; render(); break;
      case "answered": if (S.ask && S.ask.request_id === c.request_id) S.ask = null;
                       render(); break;
      case "think": S.busy = true; setBar(); break;
      case "done": case "closed": S.busy = false; push(c); break;
      case "mode": S.mode = c.mode; push(c); break;
      case "usage": S.usage = c; setBar(); break;
      case "ready": S.busy = false; setBar(); break;
      default: push(c);
    }
  };
}

/* ---------- input ---------- */

/* The one place the RayNeo SDK plugs in: feed next/prev/confirm/back.
   Everything above is device-independent. */
function attachInput() {
  let acc = 0;
  addEventListener("wheel", (e) => {
    acc += e.deltaY;
    while (Math.abs(acc) >= 40) { acc > 0 ? next() : prev(); acc -= Math.sign(acc) * 40; }
  }, { passive: true });
  addEventListener("keydown", (e) => {
    const k = e.key;
    if (k === "ArrowDown" || k === "ArrowRight") { e.preventDefault(); next(); }
    else if (k === "ArrowUp" || k === "ArrowLeft") { e.preventDefault(); prev(); }
    else if (k === "Enter" || k === " ") { e.preventDefault(); confirm(); }
    else if (k === "Escape" || k === "Backspace") { e.preventDefault(); back(); }
  });
  // Message from the simulator shell, so the preview is really driven.
  addEventListener("message", (e) => {
    const d = e.data || {};
    if (d.irisProfile) return applyProfile(d.irisProfile);
    const a = d.iris;
    if (a === "next") next();
    else if (a === "prev") prev();
    else if (a === "confirm") confirm();
    else if (a === "back") back();
    // Head gestures on the iO: nod approves, shake rejects. They only mean
    // something while a confirmation is up - elsewhere they are ignored on
    // purpose, so a nod while reading never triggers anything.
    else if (a === "approve" && S.ask) { S.askChoice = 1; confirm(); }
    else if (a === "reject" && S.ask) { S.askChoice = 0; confirm(); }
  });
}

/* When there is nothing to attach to, offer a way forward on the glasses
   themselves rather than sending the user back to a phone. */
async function pickSession(list) {
  showList("SITZUNG", list.map((x) => ({
    label: cut(x.title || x.label, COLS - 2),
    run: async () => { await attach(x); },
  })));
}

async function offerStart() {
  const { projects } = await api("/api/projects");
  if (!projects.length) {
    document.getElementById("stage").innerHTML =
      `<div class="empty">keine Projekte</div>`;
    return;
  }
  showList("NEU IN …", projects.slice(0, 12).map((p) => ({
    label: cut(p.label, COLS - 2),
    run: async () => {
      try {
        const { session } = await api("/api/sessions",
          { method: "POST", body: JSON.stringify({ cwd: p.path }) });
        await attach(session);
      } catch (e) {
        push({ kind: "error", text: e.message });
      }
    },
  })));
}

async function attach(sess) {
  S.session = sess;
  S.mode = sess.permission_mode || "";
  S.cards = []; S.raw = []; S.idx = 0;
  S.screen = "cards"; S.list = null;
  try {
    const { cards } = await api(`/api/sessions/${sess.key}/history?limit=60`);
    for (const c of cards) { S.raw.push(c); S.cards.push(...expand(c)); }
  } catch { /* history is optional */ }
  S.idx = lastMeaningful();
  render();
  connect();
}

/* ---------- boot ---------- */

addEventListener("DOMContentLoaded", async () => {
  const u = new URL(location.href);
  S.token = u.searchParams.get("token") || localStorage.getItem("iris_token") || "";
  const key = u.searchParams.get("session");
  attachInput();
  applyProfile(u.searchParams.get("profile") || "g2");

  if (!S.token) {
    document.getElementById("stage").innerHTML =
      `<div class="empty">kein Token</div>`;
    return;
  }
  try {
    let sess = null;
    if (key) {
      // A stale key (bridge restarted, session closed) must not dead-end.
      try { sess = (await api(`/api/sessions/${key}`)).session; } catch { sess = null; }
    }
    if (!sess) {
      const { sessions } = await api("/api/sessions");
      const live = sessions.filter((x) => !x.exited);
      if (live.length === 1) {
        sess = live[0];
      } else if (live.length > 1) {
        return pickSession(live);
      } else {
        return offerStart();
      }
    }
    await attach(sess);
  } catch (e) {
    document.getElementById("stage").innerHTML =
      `<div class="empty">${esc(e.message)}</div>`;
  }
});
