/* Glasses simulator - device-agnostic shell.
 *
 * Knows two things: what panels look like, and what input a headset can
 * produce. It does not know anything about the app inside; apps speak the
 * contract in docs/GLASSES-APP.md (postMessage in, geometry back out).
 * That way a second app - anything you build later - drops straight in.
 *
 * The real device relays display and input over BLE via the phone. That
 * relay is not simulated: what matters for design is the panel size, the
 * monochrome rendering and the input vocabulary, and those are all here.
 */
const $ = (s) => document.querySelector(s);
let CFG = { profiles: [], apps: [] };
let profile = null, app = null, zoom = 1;

async function boot() {
  CFG = await (await fetch("/sim/apps.json")).json();

  const ps = $("#profile");
  ps.innerHTML = CFG.profiles
    .map((p) => `<option value="${p.id}">${p.label} — ${p.w}×${p.h}</option>`).join("");
  const as = $("#app");
  as.innerHTML = CFG.apps
    .map((a) => `<option value="${a.id}">${a.label}</option>`).join("");

  ps.onchange = () => setProfile(ps.value);
  as.onchange = () => setApp(as.value);
  $("#zoom").onchange = (e) => { zoom = parseFloat(e.target.value); layout(); };
  $("#mono").onclick = (e) => {
    $("#panel").classList.toggle("mono");
    e.target.classList.toggle("on", $("#panel").classList.contains("mono"));
  };
  $("#glow").onclick = (e) => {
    $("#panel").classList.toggle("glow");
    e.target.classList.toggle("on", $("#panel").classList.contains("glow"));
  };
  $("#reload").onclick = () => setApp(app.id);
  $("#fps").onchange = (e) => setFps(parseFloat(e.target.value));

  for (const b of document.querySelectorAll("[data-a]")) {
    b.onclick = () => send(b.dataset.a);
  }
  bindKeys();

  const u = new URL(location.href);
  setProfile(u.searchParams.get("profile") || CFG.profiles[0].id);
  setApp(u.searchParams.get("app") || CFG.apps[0].id);
}

function setProfile(id) {
  profile = CFG.profiles.find((p) => p.id === id) || CFG.profiles[0];
  $("#profile").value = profile.id;
  $("#est").hidden = profile.source !== "geschätzt";
  $("#note").textContent = profile.note || "";
  layout();
  send(null, { irisProfile: profile.id });
  showFacts();
  setFps(parseFloat($("#fps").value));
}

function setApp(id) {
  app = CFG.apps.find((a) => a.id === id) || CFG.apps[0];
  $("#app").value = app.id;
  let url = app.url;
  if (app.needsToken) {
    const tok = new URL(location.href).searchParams.get("token")
             || localStorage.getItem("iris_token") || "";
    if (tok) localStorage.setItem("iris_token", tok);
    const sess = new URL(location.href).searchParams.get("session");
    url += (url.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(tok)
         + (sess ? "&session=" + encodeURIComponent(sess) : "")
         + "&profile=" + encodeURIComponent(profile.id);
  }
  $("#frame").src = url;
}

function layout() {
  const panel = $("#panel"), frame = $("#frame"), bezel = panel.parentElement;
  frame.style.width = profile.w + "px";
  frame.style.height = profile.h + "px";
  panel.style.width = profile.w + "px";
  panel.style.height = profile.h + "px";
  panel.style.transform = `scale(${zoom})`;
  bezel.style.width = (profile.w * zoom + 34) + "px";
  bezel.style.height = (profile.h * zoom + 34) + "px";
}

/* Geometry comes back from the app, because only the app knows what font it
   renders with. Showing it here is the point: it is the budget you design to. */
function showFacts(geo) {
  const parts = [
    `Panel <b>${profile.w}×${profile.h}</b>`,
    `Quelle <b>${profile.source}</b>`,
  ];
  if (geo) {
    parts.push(`Platz <b>${geo.cols} Zeichen × ${geo.lines} Zeilen</b>`);
    parts.push(`rund <b>${Math.round(geo.cols * geo.lines / 6)}</b> Wörter je Seite`);
  }
  $("#facts").innerHTML = parts.map((p) => `<span>${p}</span>`).join("");
}

/* A ceiling, not a simulation of the radio: it shows how choppy the app
   will feel, which is the part that changes design decisions. */
function setFps(fps) {
  if (!profile) return;              // called before a device is chosen
  const panel = $("#panel");
  if (!fps) {
    panel.classList.remove("fps");
    $("#fpsnote").textContent = "";
    return;
  }
  panel.classList.add("fps");
  panel.style.setProperty("--fps-period", (1000 / fps) + "ms");
  const bytes = Math.round(profile.w * profile.h / 8 / 1024);
  $("#fpsnote").textContent =
    `Vollbild ≈ ${bytes} KB · bei ~100 KB/s über BLE rund ` +
    `${Math.max(1, Math.round(100 / bytes))} Vollbilder/s`;
}

function send(action, raw) {
  const f = $("#frame");
  if (!f.contentWindow) return;
  f.contentWindow.postMessage(raw || { iris: action }, "*");
}

function bindKeys() {
  addEventListener("message", (e) => {
    if (e.data && e.data.irisGeometry) showFacts(e.data.irisGeometry);
  });
  addEventListener("keydown", (e) => {
    const map = { ArrowDown: "next", ArrowUp: "prev", ArrowRight: "next",
                  ArrowLeft: "prev", Enter: "confirm", " ": "confirm",
                  Escape: "back", Backspace: "back",
                  j: "approve", n: "reject" };
    const a = map[e.key];
    if (a) { e.preventDefault(); send(a); }
  });
  // The wheel over the panel is the crown.
  $("#panel").addEventListener("wheel", (e) => {
    e.preventDefault();
    send(e.deltaY > 0 ? "next" : "prev");
  }, { passive: false });
}

boot();
