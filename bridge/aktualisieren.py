"""Claude Code aktualisieren, ohne die Terminals zu verlieren.

Ein Update heisst sonst: jede Sitzung beenden, jeden Tab neu einrichten, den
Faden neu aufnehmen. Dabei ist das gar nicht noetig - die Sitzung liegt als
Verlauf auf der Platte, und `claude --resume <id>` holt sie zurueck. Der Tab
bleibt stehen, das Arbeitsverzeichnis auch.

Der Schluessel einer Terminal-Sitzung in iris IST die Claude-Sitzungskennung
(`t-<id>`), und `--resume` behaelt sie - nur `--fork-session` vergibt eine
neue. Nach dem Neustart taucht dieselbe Sitzung wieder auf, mit demselben
Verlauf, auch auf dem Telefon.

Die Reihenfolge ist nicht beliebig: erst alle beenden, DANN aktualisieren.
`/opt/homebrew/bin/claude` ist ein Symlink in einen Ordner mit der
Versionsnummer darin, und brew loescht den beim Upgrade. Unter laufenden
Prozessen ist das bestenfalls unnoetig.

Das Update selbst laeuft hier und nicht in einer Claude-Sitzung. Die Bruecke
ist ein eigener Prozess; sie braucht niemanden, der fuer sie tippt.
"""
import os
import re
import shutil
import subprocess
import time

from . import typist

BREW = shutil.which("brew") or "/opt/homebrew/bin/brew"
CASK = "claude-code@latest"
# Wie lange auf das Beenden gewartet wird, bevor eine Sitzung als haengend
# gilt. Claude Code schreibt beim Verlassen noch seinen Verlauf.
ENDE_WARTEN = 20
# Und wie lange, bis eine wiederaufgenommene Sitzung wieder da sein muss.
START_WARTEN = 40


def _brew(*args, timeout=600):
    try:
        r = subprocess.run([BREW, *args], capture_output=True, text=True,
                           timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def installiert():
    """Welche Fassung liegt hier, und wie wurde sie installiert."""
    pfad = shutil.which("claude") or ""
    art, version = "unbekannt", ""
    if pfad:
        ziel = os.path.realpath(pfad)
        if "/Caskroom/" in ziel:
            art = "brew"
            teile = ziel.split("/Caskroom/")[1].split("/")
            version = teile[1] if len(teile) > 1 else ""
        elif "/node_modules/" in ziel or "/npm" in ziel:
            art = "npm"
        else:
            art = "sonstige"
    if not version:
        try:
            r = subprocess.run([pfad or "claude", "--version"],
                               capture_output=True, text=True, timeout=10)
            m = re.search(r"\d+(?:\.\d+)+", r.stdout or "")
            version = m.group(0) if m else ""
        except (OSError, subprocess.SubprocessError):
            pass
    return {"pfad": pfad, "art": art, "version": version}


def neue_fassung():
    """Was brew an Neuem kennt - "" wenn nichts ansteht."""
    code, out = _brew("outdated", "--cask", "--greedy", "--verbose", timeout=120)
    if code != 0:
        return ""
    for zeile in out.splitlines():
        if zeile.startswith(CASK):
            # "claude-code@latest (2.1.263) != 2.1.278"
            m = re.findall(r"\d+(?:\.\d+)+", zeile)
            return m[-1] if m else "neuere Fassung"
    return ""


def _kandidaten(manager):
    """Terminal-Sitzungen, die sich beenden und wieder aufnehmen lassen."""
    raus = []
    for s in manager.terminals.sessions.values():
        if getattr(s, "exited", False):
            continue
        sid = getattr(s, "claude_session_id", "") or ""
        tty = getattr(s, "tty", "") or ""
        if not sid or not tty:
            continue
        raus.append(s)
    return raus


def _hintergrund(s):
    """Wie viel in dieser Sitzung nebenher laeuft.

    Ein Agent aus `/fork` und ein mit Ctrl+B weggeschickter Befehl laufen
    weiter, waehrend der Zug selbst schon fertig ist - die Sitzung sieht
    dann untaetig aus und ist es nicht. `/exit` wuerde beides toeten, und
    ein Agent, der eine halbe Stunde gerechnet hat, ist danach weg.
    """
    laufend = getattr(s, "background", None) or {}
    if isinstance(laufend, dict):
        return sum(1 for t in laufend.values()
                   if (t or {}).get("status") in (None, "running"))
    return int(laufend or 0)


def plan(manager):
    """Was passieren wuerde, ohne dass etwas passiert."""
    fest = installiert()
    sitzungen = []
    for s in _kandidaten(manager):
        sitzungen.append({
            "key": s.key,
            "titel": getattr(s, "title", "") or s.label(),
            "cwd": getattr(s, "cwd", ""),
            "busy": bool(getattr(s, "busy", False)),
            "hintergrund": _hintergrund(s),
        })
    gruende = []
    if fest["art"] != "brew":
        gruende.append("Claude Code ist nicht über brew installiert")
    arbeiten = sum(1 for x in sitzungen if x["busy"])
    if arbeiten:
        # Kein Hindernis, sondern ein Hinweis: eine arbeitende Sitzung wird
        # uebersprungen und behaelt die alte Fassung, bis sie das naechste
        # Mal neu startet.
        gruende.append("1 Sitzung arbeitet gerade" if arbeiten == 1
                       else "%d Sitzungen arbeiten gerade" % arbeiten)
    nebenher = sum(1 for x in sitzungen if not x["busy"] and x["hintergrund"])
    if nebenher:
        gruende.append("1 Sitzung hat etwas im Hintergrund" if nebenher == 1
                       else "%d Sitzungen haben etwas im Hintergrund" % nebenher)
    if not sitzungen:
        gruende.append("Keine Terminal-Sitzung, in die zurückgekehrt werden könnte")
    return {"ok": not gruende, "grund": " · ".join(gruende),
            "installiert": fest, "neu": neue_fassung(), "sitzungen": sitzungen}


def lauf(manager, melde=lambda schritt, text: None):
    """Beenden, aktualisieren, zurueckholen.

    `melde(schritt, text)` bekommt jeden Zwischenstand. Was schiefgeht, wird
    benannt und nicht verschwiegen - eine Sitzung, die nicht zurueckkommt,
    steht mit ihrem Befehl im Ergebnis, damit sie von Hand zu retten ist.
    """
    vorher = installiert()
    ziele = []
    for s in _kandidaten(manager):
        if getattr(s, "busy", False):
            continue                      # arbeitet - wird nicht angefasst
        if _hintergrund(s):
            # Ein Agent aus `/fork` oder ein weggeschickter Befehl laeuft
            # nebenher. Die Sitzung sieht untaetig aus, ist es aber nicht.
            continue
        ziele.append({"key": s.key, "sid": s.claude_session_id, "tty": s.tty,
                      "titel": getattr(s, "title", "") or s.label()})
    if not ziele:
        return {"ok": False, "grund": "Keine Sitzung, die beendet werden könnte"}

    melde("beenden", "%d Sitzung%s werden beendet"
          % (len(ziele), "" if len(ziele) == 1 else "en"))
    for z in ziele:
        z["beendet"] = typist.type_into(z["tty"], "/exit") == "ok"

    ende = time.time() + ENDE_WARTEN
    while time.time() < ende:
        if all(typist.claude_gone(z["tty"]) for z in ziele if z["beendet"]):
            break
        time.sleep(1)
    for z in ziele:
        z["weg"] = typist.claude_gone(z["tty"])

    haengt = [z for z in ziele if not z["weg"]]
    if haengt:
        # Ein Tab, in dem noch Claude laeuft, wird nicht aktualisiert und
        # nicht ueberschrieben. Lieber gar nicht als halb.
        melde("abbruch", "%d Sitzung%s ließ sich nicht beenden"
              % (len(haengt), "" if len(haengt) == 1 else "en"))
        return {"ok": False, "grund": "Nicht alle Sitzungen ließen sich beenden",
                "haengen": [z["titel"] for z in haengt],
                "sitzungen": ziele}

    melde("aktualisieren", "brew upgrade %s" % CASK)
    code, ausgabe = _brew("upgrade", "--cask", CASK)
    nachher = installiert()
    # Auch wenn brew scheitert, kommen die Sitzungen zurueck. Sonst waere der
    # Preis eines fehlgeschlagenen Updates ein leerer Schreibtisch.
    gelungen = code == 0

    melde("zurückholen", "%d Sitzung%s werden wieder aufgenommen"
          % (len(ziele), "" if len(ziele) == 1 else "en"))
    for z in ziele:
        z["zurueck"] = typist.resume_in_tab(z["tty"], z["sid"]) == "ok"
        z["befehl"] = "claude --resume %s" % z["sid"]

    ende = time.time() + START_WARTEN
    while time.time() < ende:
        if all(not typist.claude_gone(z["tty"]) for z in ziele):
            break
        time.sleep(1)
    for z in ziele:
        z["laeuft"] = not typist.claude_gone(z["tty"])

    fehlen = [z for z in ziele if not z["laeuft"]]
    return {
        "ok": gelungen and not fehlen,
        "grund": ("" if gelungen else "brew: " + ausgabe.strip()[-300:])
                 or ("%d Sitzung%s kam nicht zurück"
                     % (len(fehlen), "" if len(fehlen) == 1 else "en") if fehlen else ""),
        "vorher": vorher["version"], "nachher": nachher["version"],
        "aktualisiert": gelungen and vorher["version"] != nachher["version"],
        "sitzungen": ziele,
        # Was von Hand nachzuholen waere, wortwoertlich.
        "von_hand": [{"titel": z["titel"], "befehl": z["befehl"]} for z in fehlen],
    }
