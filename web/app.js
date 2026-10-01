/* iris - remote control for Claude Code sessions.
 *
 * Three screens: projects -> sessions -> conversation. The conversation is a
 * stream of cards from the bridge; the only card that demands attention is
 * `ask`, which is why it is the loudest thing on screen.
 *
 * Everything here assumes a flaky link: the event stream carries sequence
 * numbers, we remember the last one we saw, and reconnect asks for the rest.
 */
const $ = (s) => document.querySelector(s);
const state = {
  token: "",
  project: null,
  session: null,       // {key, cwd, ...}
  lastSeq: 0,
  es: null,
  busy: false,
  asks: new Map(),     // request_id -> element
  timing: new Map(),   // tool_use_id -> duration in ms
  away: false,
  usage: null,
  shortcuts: [],
  unread: 0,
  modes: [],
  mode: "",
};

/* ---------- transport ---------- */

function tokenFromUrl() {
  const u = new URL(location.href);
  const t = u.searchParams.get("token");
  if (t) {
    localStorage.setItem("iris_token", t);
    u.searchParams.delete("token");           // keep it out of the address bar
    history.replaceState({}, "", u.pathname + u.hash);
    return t;
  }
  return localStorage.getItem("iris_token") || "";
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: {
      "Authorization": "Bearer " + state.token,
      "Content-Type": "application/json",
      ...(opts.headers || {}),
    },
  });
  if (res.status === 401) { toast("Token ungültig"); throw new Error("unauthorized"); }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || res.statusText);
  return body;
}

/* ---------- screens ---------- */

function show(screen) {
  for (const id of ["projects", "sessions", "chat", "services"]) {
    $("#s-" + id).classList.toggle("hidden", id !== screen);
  }
  $("#composer").classList.toggle("hidden", screen !== "chat");
  $("#mode").classList.toggle("hidden", screen !== "chat");
  $("#toglasses").classList.toggle("hidden", screen !== "chat");
  $("#back").classList.toggle("hidden", screen === "projects");
  $("#services").classList.toggle("hidden", screen === "services");
}

function fmtDur(ms) {
  if (ms == null) return "";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
}

function fmtAge(ts) {
  const d = Math.max(0, Date.now() / 1000 - ts);
  if (d < 60) return "gerade eben";
  if (d < 3600) return `vor ${Math.floor(d / 60)} min`;
  if (d < 86400) return `vor ${Math.floor(d / 3600)} h`;
  return `vor ${Math.floor(d / 86400)} d`;
}

async function loadProjects() {
  show("projects");
  setTitle("iris", "Projekt wählen");
  const el = $("#projects-list");
  el.innerHTML = `<div class="empty">lade …</div>`;
  try {
    const [{ projects }, { sessions }] = await Promise.all([
      api("/api/projects"), api("/api/sessions"),
    ]);
    el.innerHTML = "";
    el.appendChild(awayRow());
    const live = sessions.filter((s) => !s.exited);
    if (live.length) {
      el.insertAdjacentHTML("beforeend", `<h2>Laufend</h2>`);
      for (const s of live) el.appendChild(liveRow(s));
    }
    el.insertAdjacentHTML("beforeend", `<h2>Projekte</h2>`);
    if (!projects.length) {
      el.insertAdjacentHTML("beforeend",
        `<div class="empty">Noch keine Projekte.<br>Starte Claude Code einmal in einem Verzeichnis.</div>`);
    }
    for (const p of projects) {
      const row = document.createElement("button");
      row.className = "row";
      row.innerHTML = `<div class="grow">
          <div class="name">${esc(p.label)}</div>
          <div class="meta">${p.sessions} Sitzungen · ${fmtAge(p.last_used)}</div>
        </div><span class="chev">›</span>`;
      row.onclick = () => loadSessions(p);
      el.appendChild(row);
    }
  } catch (e) { el.innerHTML = `<div class="empty">Fehler: ${esc(e.message)}</div>`; }
}

/* Unterwegs: Freigaben aus Terminal-Sitzungen kommen aufs Handy. Aus heißt,
   der Dialog erscheint wie immer am Rechner - wer dort sitzt, soll nie auf
   ein Handy warten, das in der Tasche steckt. */
function awayRow() {
  const row = document.createElement("button");
  row.className = "row away-row";
  const paint = () => {
    row.classList.toggle("on", !!state.away);
    row.innerHTML = `<span class="dot ${state.away ? "busy" : "gone"}"></span>
      <div class="grow">
        <div class="name">${state.away ? "Unterwegs" : "Am Rechner"}</div>
        <div class="meta">${state.away
          ? "Freigaben aus dem Terminal kommen hierher"
          : "Freigaben aus dem Terminal erscheinen am Rechner"}</div>
      </div><span class="badge ${state.away ? "live" : ""}">${state.away ? "an" : "aus"}</span>`;
  };
  paint();
  api("/api/terminals/away").then((r) => { state.away = r.away; paint(); })
    .catch(() => {});
  row.onclick = async () => {
    try {
      const r = await api("/api/terminals/away", {
        method: "POST", body: JSON.stringify({ away: !state.away }),
      });
      state.away = r.away;
      paint();
    } catch (e) { toast(e.message); }
  };
  return row;
}

function liveRow(s) {
  const row = document.createElement("button");
  row.className = "row";
  row.innerHTML = `<span class="dot ${s.busy ? "busy" : "live"}"></span>
    <div class="grow">
      <div class="name">${esc(s.title || s.label)}</div>
      <div class="meta">${s.terminal ? "Terminal · " : ""}${esc(s.label)} · ${
        s.busy ? "arbeitet" : "bereit"}${s.acts ? ` · ${s.acts} Befehle` : ""}${
        s.failed ? ` · ${s.failed} fehlgeschlagen` : ""}${
        s.open_asks ? " · Bestätigung offen" : ""}</div>
    </div>
    ${s.open_asks ? '<span class="badge live">!</span>' : ""}<span class="chev">›</span>`;
  row.onclick = () => openSession(s);
  return row;
}

async function loadSessions(project) {
  state.project = project;
  show("sessions");
  setTitle(project.label, "Sitzung wählen");
  const el = $("#sessions-list");
  el.innerHTML = `<div class="empty">lade …</div>`;

  const fresh = document.createElement("button");
  fresh.className = "row";
  fresh.innerHTML = `<div class="grow"><div class="name">＋ Neue Sitzung</div>
      <div class="meta">${esc(project.path)}</div></div>`;
  fresh.onclick = () => startSession(project.path, null);

  try {
    const { sessions } = await api(
      `/api/projects/${encodeURIComponent(project.id)}/sessions` +
      `?path=${encodeURIComponent(project.path)}`);
    el.innerHTML = "";
    el.appendChild(fresh);
    if (sessions.length) el.insertAdjacentHTML("beforeend", `<h2>Fortsetzen</h2>`);
    for (const s of sessions) {
      const row = document.createElement("button");
      row.className = "row";
      row.innerHTML = `<div class="grow">
          <div class="name">${esc(s.title || s.session_id.slice(0, 8))}</div>
          <div class="meta">${fmtAge(s.modified)}${
            s.likely_open ? " · läuft wohl im Terminal" : ""}</div>
        </div>${s.likely_open ? '<span class="badge open">offen</span>' : ""
        }<span class="chev">›</span>`;
      row.onclick = () => {
        // A conversation still live in a terminal is opened as a fork: the
        // history comes along, the original keeps running untouched. Work
        // done here does not flow back, so say so rather than hide it.
        if (s.likely_open) {
          if (!window.confirm(
                "Diese Unterhaltung läuft vermutlich gerade in einem Terminal.\n\n" +
                "iris öffnet sie als Abzweig: der bisherige Verlauf ist dabei, " +
                "die Sitzung am Rechner bleibt unberührt.\n\n" +
                "Was du hier tust, landet nicht in der Sitzung am Rechner.\n\nÖffnen?")) {
            return;
          }
          startSession(project.path, s.session_id, true);
          return;
        }
        startSession(project.path, s.session_id);
      };
      el.appendChild(row);
    }
  } catch (e) { el.innerHTML = `<div class="empty">Fehler: ${esc(e.message)}</div>`; }
}

async function startSession(cwd, resume, fork) {
  toast(fork ? "Öffne Abzweig …" : resume ? "Setze fort …" : "Starte …");
  try {
    const { session } = await api("/api/sessions", {
      method: "POST", body: JSON.stringify({ cwd, resume, fork }),
    });
    openSession(session);
  } catch (e) { toast("Start fehlgeschlagen: " + e.message); }
}

/* ---------- conversation ---------- */

async function openSession(s) {
  clearUnread();
  state.session = s;
  state.lastSeq = 0;
  state.asks.clear();
  state.mode = s.permission_mode || "";
  state.timing.clear();
  $("#cards").innerHTML = "";
  show("chat");
  // A terminal session has no control channel: mode and model belong to
  // whoever sits at that terminal. Offering the switch would be a lie.
  const chip = $("#mode");
  if (chip) chip.classList.toggle("hidden", !!s.terminal);
  setTitle(s.title || s.label,
           (s.terminal ? "Terminal · " : "") + (s.permission_label || s.cwd));
  await loadHistory();
  connect();
  $("#input").focus();
}

/* A resumed conversation used to open blank. Pull what was said before so
   you can see where you left off. */
async function loadHistory() {
  if (!state.session) return;
  try {
    const { cards } = await api(`/api/sessions/${state.session.key}/history?limit=120`);
    if (!cards.length) return;
    const box = $("#cards");
    box.insertAdjacentHTML("beforeend",
      `<div class="card done">— bisheriger Verlauf —</div>`);
    for (const c of cards) render(c, true);
    box.insertAdjacentHTML("beforeend",
      `<div class="card done">— hier geht es weiter —</div>`);
    box.scrollTop = box.scrollHeight;
  } catch { /* history is a nicety, never a blocker */ }
}

function connect() {
  if (state.es) state.es.close();
  const url = `/api/sessions/${state.session.key}/events?since=${state.lastSeq}` +
              `&token=${encodeURIComponent(state.token)}`;
  const es = new EventSource(url);
  state.es = es;
  es.onopen = () => setDot(state.busy ? "busy" : "live");
  es.onerror = () => setDot("gone");            // EventSource retries by itself
  es.onmessage = (ev) => {
    let card; try { card = JSON.parse(ev.data); } catch { return; }
    if (card.seq) state.lastSeq = Math.max(state.lastSeq, card.seq);
    render(card);
  };
}

function render(c, historic) {
  const box = $("#cards");
  // Wer hochgescrollt hat, liest gerade etwas. Dann wird nicht gesprungen -
  // weder für neue Karten noch beim Tippen. Neues meldet sich stattdessen.
  const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 120;
  let el = null;

  switch (c.kind) {
    case "ready":
      setDot("live"); break;
    case "sent":
      el = div("card me", `<div class="txt">${esc(c.text)}</div>`); break;
    case "say":
      el = div("card say", `<div class="txt">${esc(c.text)}</div>`); break;
    case "act":
      el = div("card act",
        `<div class="tool">${esc(c.tool)}</div><div class="detail">${esc(c.detail)}</div>` +
        `<div class="dur"></div>`);
      if (c.tool_use_id) {
        el.dataset.tu = c.tool_use_id;
        const ms = state.timing.get(c.tool_use_id);
        if (ms != null) el.querySelector(".dur").textContent = fmtDur(ms);
      }
      break;
    case "timing": {
      // The call comes from the transcript, its duration from a hook -
      // either can arrive first.
      state.timing.set(c.tool_use_id, c.duration_ms);
      const d = box.querySelector(`.card.act[data-tu="${CSS.escape(c.tool_use_id)}"] .dur`);
      if (d) d.textContent = fmtDur(c.duration_ms);
      break;
    }
    case "queued":
      el = div("card me queued", `<div class="txt">${esc(c.text)}</div>` +
        `<div class="lbl">wartet auf Übergabe</div>`);
      break;
    case "delivered":
      for (const q of box.querySelectorAll(".card.me.queued")) {
        q.classList.remove("queued");
        const l = q.querySelector(".lbl");
        if (l) l.textContent = "übergeben";
      }
      break;
    case "result":
      if (c.text) el = div("card res " + (c.ok ? "" : "bad"),
        `<div class="txt">${esc(c.text)}</div>`);
      break;
    case "ask":
      el = askCard(c); break;
    case "answered": {
      const prev = state.asks.get(c.request_id);
      if (prev) {
        prev.classList.add("settled");
        prev.querySelector(".verdict").className = "verdict " + (c.allow ? "y" : "n");
        prev.querySelector(".verdict").textContent = c.allow ? "erlaubt" : "abgelehnt";
      }
      break;
    }
    case "think":
      setDot("busy"); state.busy = true; break;
    case "usage":
      state.usage = c;
      updateQuota();
      break;
    case "done":
      state.busy = false; setDot("live"); setSending(false);
      el = div("card done", esc(doneLine(c)));
      break;
    case "closed":
      setDot("gone"); setSending(false);
      el = div("card done", "Sitzung beendet — " + esc(c.reason || ""));
      break;
    case "mode":
      state.mode = c.mode;
      updateModeChip();
      el = div("card done", "Modus: " + esc(modeLabel(c.mode)));
      break;
    case "error":
      el = div("card err", esc(c.text)); break;
  }
  if (el) {
    if (historic) el.classList.add("historic");
    box.appendChild(el);
    if (!stick && !historic && ["say", "act", "ask", "result"].includes(c.kind)) {
      state.unread++;
      showUnread();
    }
  }
  if (stick && el) box.scrollTop = box.scrollHeight;
}

function doneLine(c) {
  // Deliberately no dollar figure: on a subscription nothing is billed, so
  // showing a price would be misleading. Quota lives in the header instead.
  const secs = c.duration_ms ? Math.round(c.duration_ms / 1000) : null;
  if (c.is_error) return "abgebrochen";
  return secs ? `fertig · ${secs}s` : "fertig";
}

/* What /usage shows: how much of each window is spent, and when it resets.
   On a subscription this is the real constraint, so it sits in the header. */
function updateQuota() {
  const u = state.usage;
  if (!u) return;
  const w = u.windows || {};
  const pct = (x) => x == null ? "–" : Math.round(x * 100) + "%";
  const clock = (ts) => {
    if (!ts) return "";
    const d = new Date(ts * 1000);
    return String(d.getHours()).padStart(2, "0") + ":" +
           String(d.getMinutes()).padStart(2, "0");
  };
  const five = w.five_hour, week = w.seven_day;
  const parts = [];
  if (five) parts.push(`5h ${pct(five.used)}`);
  if (week) parts.push(`Woche ${pct(week.used)}`);
  if (u.using_overage) parts.push("Overage");
  const el = $("#quota");
  el.textContent = parts.join(" · ") || "";
  el.title = five ? `5-Stunden-Fenster endet ${clock(five.resets_at)}` : "";
  // Colour the header hint once a window gets tight.
  const worst = Math.max(five ? five.used : 0, week ? week.used : 0);
  el.style.color = worst >= 0.9 ? "var(--bad)"
                 : worst >= 0.7 ? "var(--warn)" : "var(--dim)";
}

function askCard(c) {
  const el = div("card ask", `
    <div class="lbl">Bestätigung nötig</div>
    <div class="tool">${esc(c.tool)}</div>
    <div class="detail">${esc(c.detail)}</div>
    <div class="askbtns">
      <button class="deny">Ablehnen</button>
      <button class="allow">Erlauben</button>
    </div>
    <div class="verdict"></div>`);
  const answer = async (allow) => {
    el.classList.add("settled");
    try {
      await api(`/api/sessions/${state.session.key}/permission`, {
        method: "POST",
        body: JSON.stringify({ request_id: c.request_id, allow }),
      });
    } catch (e) { toast(e.message); el.classList.remove("settled"); }
  };
  el.querySelector(".allow").onclick = () => answer(true);
  el.querySelector(".deny").onclick = () => answer(false);
  state.asks.set(c.request_id, el);
  if (navigator.vibrate) navigator.vibrate([40, 60, 40]);
  // A pending confirmation is the one thing worth stealing focus for.
  if (window.Wheel) requestAnimationFrame(() => Wheel.focusFirst(".allow"));
  return el;
}

/* ---------- gelesen / ungelesen ---------- */

/* Der Hinweis erscheint nur, wenn man oben liest. Ein Tippen darauf springt
   ans Ende - von allein passiert das nie. */
function showUnread() {
  let el = $("#unread");
  if (!el) {
    el = div("unread-pill", "");
    el.id = "unread";
    el.onclick = () => {
      const box = $("#cards");
      box.scrollTo({ top: box.scrollHeight, behavior: "smooth" });
      clearUnread();
    };
    $("#s-chat").appendChild(el);
  }
  el.innerHTML =
    `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
       <path d="M12 5v14"/><path d="M19 12l-7 7-7-7"/></svg>` +
    `<span>${state.unread} neue</span>`;
  el.style.display = "flex";
}

function clearUnread() {
  state.unread = 0;
  const el = $("#unread");
  if (el) el.style.display = "none";
}

/* Beim Tippen darf sich die Leseposition nicht bewegen. Auf dem Handy
   schiebt die eingeblendete Tastatur die Seite - das fangen wir ab. */
function keepScrollWhileTyping() {
  const box = $("#cards");
  const ta = $("#input");
  let frozen = null;

  const freeze = () => {
    const atEnd = box.scrollHeight - box.scrollTop - box.clientHeight < 120;
    frozen = atEnd ? null : box.scrollTop;   // unten: normal weiterlaufen
  };
  const restore = () => {
    if (frozen !== null && Math.abs(box.scrollTop - frozen) > 2) {
      box.scrollTop = frozen;
    }
  };

  ta.addEventListener("focus", () => { freeze(); requestAnimationFrame(restore); });
  ta.addEventListener("input", () => { requestAnimationFrame(restore); });
  // Die Bildschirmtastatur verändert die sichtbare Höhe, nicht das Fenster.
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", () => {
      requestAnimationFrame(restore);
    });
  }
  box.addEventListener("scroll", () => {
    const atEnd = box.scrollHeight - box.scrollTop - box.clientHeight < 120;
    if (atEnd) { frozen = null; clearUnread(); }
    else if (document.activeElement === ta) { frozen = box.scrollTop; }
  }, { passive: true });
}

/* ---------- services ---------- */

/* Services report in by themselves; iris never goes looking. So the one
   state a service cannot tell us about itself - "I stopped" - is inferred
   from a heartbeat that did not arrive, and shown as its own kind. */
let svcTimer = null;

async function showServices() {
  show("services");
  setTitle("Dienste", "melden sich selbst");
  await loadServices();
  clearInterval(svcTimer);
  svcTimer = setInterval(loadServices, 15000);
}

function stopServices() {
  clearInterval(svcTimer);
  svcTimer = null;
}

async function loadServices() {
  try {
    const { services, summary } = await api("/api/services");
    renderSummary(summary);
    renderServices(services);
  } catch (e) {
    $("#svc-list").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}

function renderSummary(s) {
  const tile = (n, label, cls) =>
    `<div class="tile ${cls}"><div class="n">${n}</div><div class="l">${label}</div></div>`;
  $("#svc-summary").innerHTML =
    tile(s.healthy, "läuft", s.healthy ? "good" : "") +
    tile(s.unhealthy, "auffällig", s.unhealthy ? "warn" : "") +
    tile(s.missing, "vermisst", s.missing ? "bad" : "") +
    tile(s.hosts.length, "Geräte", "");
}

function renderServices(services) {
  const el = $("#svc-list");
  if (!services.length) {
    el.innerHTML = `<div class="empty">Noch meldet sich nichts.<br><br>
      <code>make ingest-token</code> zeigt, was ein Dienst braucht.</div>`;
    return;
  }
  // Anything broken first - a dashboard you have to scroll to find the
  // problem is not doing its job. But group by machine, and sort the
  // machines by their worst service: sorting services globally would list
  // the same host twice, once per severity.
  const rank = (s) => s.missing ? 0 : s.reported_status === "error" ? 1
                    : s.reported_status === "warn" ? 2 : 3;
  const byHost = new Map();
  for (const s of services) {
    if (!byHost.has(s.host)) byHost.set(s.host, []);
    byHost.get(s.host).push(s);
  }
  const hosts = [...byHost.entries()]
    .map(([host, list]) => ({
      host,
      list: list.sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name)),
      worst: Math.min(...list.map(rank)),
    }))
    .sort((a, b) => a.worst - b.worst || a.host.localeCompare(b.host));

  el.innerHTML = "";
  for (const { host, list } of hosts) {
    el.insertAdjacentHTML("beforeend", `<div class="svc-host">${esc(host)}</div>`);
    for (const s of list) renderService(el, s);
  }
}

function renderService(el, s) {
  {
    const cls = s.missing ? "s-missing" : "s-" + (s.reported_status || "ok");
    const bits = Object.entries(s.detail || {})
      .map(([k, v]) => `${esc(k)} ${esc(v)}`).join(" · ");
    el.insertAdjacentHTML("beforeend", `
      <div class="svc ${cls}">
        <span class="led"></span>
        <div class="grow">
          <div class="nm">${esc(s.name)}${
            s.version ? ` <span class="hostname">${esc(s.version)}</span>` : ""}</div>
          <div class="meta">${s.missing
            ? "meldet sich nicht mehr"
            : (bits || esc(s.reported_status))}</div>
        </div>
        <div class="age">${fmtSilent(s.silent_for, s.interval)}</div>
      </div>`);
  }
}

/* How long since the last beat, measured against what it promised. */
function fmtSilent(sec, interval) {
  const s = Math.round(sec);
  const txt = s < 90 ? `${s}s` : s < 5400 ? `${Math.round(s / 60)} min`
            : `${Math.round(s / 3600)} h`;
  return txt;
}

/* ---------- canned prompts ---------- */

/* On glasses these carry most of the input: the wheel scrolls the list,
   one press sends. Loaded from the bridge so every client agrees. */
async function loadShortcuts() {
  try {
    const { shortcuts } = await api("/api/shortcuts");
    state.shortcuts = shortcuts;
  } catch { state.shortcuts = []; }
}

function toggleShortcuts(force) {
  const panel = $("#shortcuts");
  const open = force !== undefined ? force : panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !open);
  $("#quick").classList.toggle("on", open);
  if (!open) { if (window.Wheel) Wheel.refresh(); return; }

  panel.innerHTML = `<div class="sc-head"><span class="lbl">Standard-Abfragen</span>
      <button class="iconbtn" id="sc-close">Schließen</button></div>`;
  panel.querySelector("#sc-close").onclick = () => toggleShortcuts(false);
  for (const sc of state.shortcuts || []) {
    const b = document.createElement("button");
    b.className = "shortcut";
    b.innerHTML = `<span class="sc-label">${esc(sc.label)}</span>
                   <span class="sc-text">${esc(sc.text)}</span>`;
    b.onclick = () => {
      $("#input").value = sc.text;
      autogrow($("#input"));
      toggleShortcuts(false);
      send();
    };
    panel.appendChild(b);
  }
  if (window.Wheel) Wheel.focusFirst(".shortcut");
}

/* ---------- permission mode ---------- */

async function loadModes() {
  try { state.modes = (await api("/api/modes")).modes; }
  catch { state.modes = []; }
}

function modeLabel(id) {
  const m = (state.modes || []).find((x) => x.id === id);
  return m ? m.label : id;
}

function updateModeChip() {
  const el = $("#mode");
  if (!el) return;
  el.textContent = modeLabel(state.mode) || "Modus";
  // Modes that stop asking are worth seeing at a glance.
  const loose = ["bypassPermissions", "dontAsk", "auto", "acceptEdits"];
  el.classList.toggle("loose", loose.includes(state.mode));
  el.classList.toggle("plan", state.mode === "plan");
}

function toggleModes(force) {
  const panel = $("#shortcuts");
  const open = force !== undefined ? force : panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !open);
  if (!open) { if (window.Wheel) Wheel.refresh(); return; }

  panel.innerHTML = `<div class="sc-head"><span class="lbl">Modus</span>
      <button class="iconbtn" id="sc-close">Schließen</button></div>`;
  panel.querySelector("#sc-close").onclick = () => toggleModes(false);
  for (const m of state.modes) {
    const b = document.createElement("button");
    b.className = "shortcut" + (m.id === state.mode ? " current" : "");
    b.innerHTML = `<span class="sc-label">${esc(m.label)}</span>
                   <span class="sc-text">${esc(m.id)}</span>`;
    b.onclick = async () => {
      try {
        await api(`/api/sessions/${state.session.key}/mode`, {
          method: "POST", body: JSON.stringify({ mode: m.id }),
        });
        toggleModes(false);
      } catch (e) { toast(e.message); }
    };
    panel.appendChild(b);
  }
  if (window.Wheel) Wheel.focusFirst(".shortcut");
}

/* ---------- composer ---------- */

async function send() {
  const ta = $("#input");
  const text = ta.value.trim();
  if (!text || !state.session) return;
  setSending(true);
  try {
    const r = await api(`/api/sessions/${state.session.key}/message`, {
      method: "POST", body: JSON.stringify({ text }),
    });
    ta.value = ""; ta.style.height = "auto";
    // A terminal session takes the message when its turn ends, not now:
    // the input stays free, and the note says when it will arrive.
    if (r && r.queued) { setSending(false); if (r.note) toast(r.note); }
  } catch (e) { toast(e.message); setSending(false); }
}

function setSending(on) {
  state.busy = on;
  $("#send").disabled = on;
  $("#input").disabled = on;
  setDot(on ? "busy" : "live");
}

/* Dictation: the primary input once this runs on glasses. */
function setupMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const mic = $("#mic");
  if (!SR) { mic.style.display = "none"; return; }
  const rec = new SR();
  rec.lang = "de-DE"; rec.interimResults = true; rec.continuous = false;
  let base = "";
  rec.onresult = (e) => {
    let txt = "";
    for (let i = e.resultIndex; i < e.results.length; i++) txt += e.results[i][0].transcript;
    $("#input").value = (base + " " + txt).trim();
    autogrow($("#input"));
  };
  rec.onend = () => mic.classList.remove("on");
  rec.onerror = () => { mic.classList.remove("on"); toast("Diktat nicht möglich"); };
  mic.onclick = () => {
    if (mic.classList.contains("on")) { rec.stop(); return; }
    base = $("#input").value;
    mic.classList.add("on");
    try { rec.start(); } catch { mic.classList.remove("on"); }
  };
}

/* ---------- chrome ---------- */

function setTitle(t, sub) {
  $("#title").textContent = t;
  $("#subtitle").textContent = sub || "";
}
function setDot(cls) { $("#dot").className = "dot " + cls; }
function div(cls, html) { const d = document.createElement("div"); d.className = cls; d.innerHTML = html; return d; }
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (m) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}
let toastTimer;
function toast(msg) {
  let t = $("#toast");
  if (!t) { t = div("toast", ""); t.id = "toast"; document.body.appendChild(t); }
  t.textContent = msg; t.style.display = "block";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.style.display = "none"; }, 2600);
}
function autogrow(ta) {
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 130) + "px";
}

/* ---------- boot ---------- */

window.addEventListener("DOMContentLoaded", () => {
  state.token = tokenFromUrl();
  if (!state.token) {
    document.body.innerHTML =
      `<div class="empty">Kein Zugangstoken.<br><br>
        Die Adresse braucht den Token angehängt:<br>
        <code>…:8780/?token=…</code><br><br>
        Die vollständige URL zeigt am Mac<br><code>make token</code>
        im Ordner <code>~/Documents/iris</code>.</div>`;
    return;
  }
  $("#send").onclick = send;
  $("#services").onclick = () => showServices();
  $("#back").onclick = () => {
    stopServices();
    if (state.es) { state.es.close(); state.es = null; }
    if (!$("#s-services").classList.contains("hidden")) loadProjects();
    else if (!$("#s-chat").classList.contains("hidden") && state.project)
      loadSessions(state.project);
    else loadProjects();
  };
  $("#stop").onclick = async () => {
    if (!state.session) return;
    await api(`/api/sessions/${state.session.key}/interrupt`, { method: "POST" });
    toast("Angehalten");
  };
  const ta = $("#input");
  ta.addEventListener("input", () => autogrow(ta));
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); }
  });
  $("#quick").onclick = () => toggleShortcuts();
  keepScrollWhileTyping();
  $("#mode").onclick = () => toggleModes();
  // Same session, other screen. The glasses view keeps the session in the
  // URL so switching back and forth never loses your place.
  $("#toglasses").onclick = () => {
    if (!state.session) return;
    location.href = "/sim/?token=" + encodeURIComponent(state.token) +
                    "&session=" + encodeURIComponent(state.session.key);
  };
  setupMic();
  loadShortcuts();
  loadModes();
  loadProjects();

  // Coming back from the lock screen must not leave a dead stream behind.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && state.session && !$("#s-chat").classList.contains("hidden")) connect();
  });
});
