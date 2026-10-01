"""The slash commands a session knows - Claude Code's own, the skills and the
custom commands on disk - for the phone to browse, look up and pick.

Claude Code's own come from the installed program itself: they change with
every update (91 in 2.1.263), and a list kept here would be wrong within
weeks. What iris adds is the German, and whether a command makes sense from
the phone: many open a view in the terminal that only keys at the Mac can
close, and a few change more than this one session (/model).
"""
import json
import mmap
import os
import re
import shutil

from . import config

CACHE = os.path.join(config.CONFIG_DIR, "commands-cache.json")

# Work from the phone: they take their words in the input line and need no
# view at the Mac to finish.
PHONE = {"compact", "clear", "goal", "rename", "fork", "subtask", "plan", "effort",
         "autocompact", "cd", "export", "init", "security-review", "reload-skills",
         "reload-plugins", "advisor", "brief"}

# Never from outside, and why.
NEVER = {
    "model": "stellt das Modell für alle neuen Sitzungen mit um – nur am Mac",
    "background": "löst die Sitzung vom Terminal – iris verliert sie",
    "teleport": "schickt die Sitzung in die Cloud – iris verliert sie",
    "logout": "meldet Claude Code ab",
    "ultrareview": "läuft kostenpflichtig in der Cloud – bewusst am Mac starten",
    "ultraplan": "läuft in Claude Code im Web",
}

# Open a file in an editor in the terminal - nothing the phone can drive.
EDITOR = {
    "memory": "öffnet einen Editor im Terminal – nur am Mac",
    "keybindings": "öffnet eine Datei im Editor – nur am Mac",
}

# Views you page through with the arrow keys - from the phone they can be
# read, typed into, confirmed and closed, but not paged.
NAV = {"config", "permissions", "mcp", "hooks", "plugin", "theme", "tui", "skills", "tasks",
       "loops", "schedule", "privacy-settings", "scroll-speed", "wellbeing", "powerup", "ide",
       "color", "remote-env", "agents", "effort", "resume", "branch", "rename"}

# Show something and nothing else - the phone would not see it.
OUTPUT = {"context", "status", "usage", "version", "list-agents", "skill-doctor", "help"}

# Internal, or of no use to anyone reading this list.
HIDDEN = {"heapdump", "pro-trial-expired", "rate-limit-options", "workflow-launch-exec",
          "extra-usage", "plugin-types", "stickers", "radio", "design-consent",
          "design-login", "design-revoke", "setup-bedrock", "setup-vertex", "install",
          "install-github-app", "install-slack-app", "upgrade", "agents", "cloud-plugins"}

# German: short name, what it does, what goes into the input after it.
DE = {
    "compact": ("Kontext zusammenfassen", "Fasst das bisherige Gespräch zusammen und macht Platz im Kontext. Dahinter kannst du sagen, worauf es beim Zusammenfassen ankommt.", "worauf achten (optional)"),
    "clear": ("Neu anfangen", "Beginnt eine neue Sitzung mit leerem Kontext. Die alte bleibt gespeichert und lässt sich mit /resume wieder öffnen; in iris erscheint die neue als eigene Zeile.", "Name (optional)"),
    "goal": ("Ziel setzen", "Legt eine Bedingung fest, die Claude prüft, bevor es aufhört – es arbeitet weiter, bis sie erfüllt ist. „clear“ hebt das Ziel wieder auf.", "Bedingung oder clear"),
    "rename": ("Umbenennen", "Gibt dem Gespräch einen Namen – so heißt es dann auch in iris.", "Name"),
    "fork": ("Agent mit ganzem Gespräch", "Startet einen Agenten im Hintergrund, der das ganze bisherige Gespräch kennt, mit einem eigenen Auftrag.", "Auftrag"),
    "subtask": ("Teilaufgabe abgeben", "Schickt einen Subagenten mit dem vollen Kontext los; sein Ergebnis kommt hierher zurück.", "Aufgabe"),
    "plan": ("Planmodus", "Schaltet in den Planmodus: Claude plant erst und fragt, bevor es etwas ändert. Mit einer Beschreibung plant es gleich los.", "was geplant werden soll (optional)"),
    "effort": ("Denkaufwand", "Stellt ein, wie gründlich das Modell nachdenkt – mehr Aufwand ist langsamer, aber sorgfältiger.", "low, medium, high …"),
    "autocompact": ("Zusammenfassen ab …", "Legt fest, wie voll der Kontext werden darf, bevor Claude Code von selbst zusammenfasst.", "auto oder Anzahl Tokens"),
    "cd": ("Verzeichnis wechseln", "Zieht die Sitzung in ein anderes Arbeitsverzeichnis um.", "Pfad"),
    "export": ("Gespräch exportieren", "Schreibt das Gespräch in eine Datei. Ohne Dateinamen öffnet sich am Mac eine Auswahl – vom Handy aus daher immer mit Namen.", "Dateiname"),
    "init": ("CLAUDE.md anlegen", "Untersucht das Projekt und schreibt eine CLAUDE.md mit dem, was Claude darüber wissen sollte.", None),
    "security-review": ("Sicherheitsprüfung", "Prüft die offenen Änderungen im aktuellen Zweig auf Sicherheitslücken und schreibt einen Bericht.", None),
    "reload-skills": ("Skills neu laden", "Nimmt Skills auf, die während der Sitzung angelegt oder geändert wurden.", None),
    "reload-plugins": ("Plugins neu laden", "Aktiviert geänderte Plugins in der laufenden Sitzung.", None),
    "advisor": ("Berater", "Lässt Claude an wichtigen Stellen ein stärkeres Modell zu Rate ziehen.", None),
    "brief": ("Kurzmodus", "Schaltet knappe Antworten ein oder aus.", None),
    "add-dir": ("Verzeichnis hinzufügen", "Gibt Claude Zugriff auf ein weiteres Arbeitsverzeichnis.", "Pfad"),
    "artifacts": ("Veröffentlichte Seiten", "Zeigt deine veröffentlichten und geteilten Seiten.", None),
    "auto-mode-setup": ("Auto-Modus einrichten", "Bringt dem Auto-Modus deine Umgebung bei, mit optionalen eigenen Regeln.", None),
    "autofix-pr": ("PR reparieren", "Beobachtet den aktuellen Pull Request und behebt Probleme darin.", None),
    "branch": ("Gespräch abzweigen", "Legt an dieser Stelle eine Abzweigung des Gesprächs an – ein zweiter Weg ab hier.", "Name"),
    "btw": ("Nebenbei gefragt", "Eine kurze Frage nebenher, ohne die laufende Arbeit zu unterbrechen. Die Antwort erscheint in einem Fenster im Terminal.", "Frage"),
    "bug": ("Fehler melden", "Meldet einen Fehler an Anthropic.", None),
    "feedback": ("Rückmeldung", "Schickt Rückmeldung an Anthropic.", None),
    "chrome": ("Claude in Chrome", "Einstellungen für die Browser-Steuerung.", None),
    "color": ("Farbe der Eingabe", "Färbt die Eingabezeile dieser Sitzung.", None),
    "config": ("Einstellungen", "Öffnet die Einstellungen von Claude Code.", None),
    "context": ("Kontext ansehen", "Zeigt als Raster, womit der Kontext gerade belegt ist.", None),
    "copy": ("Antwort kopieren", "Kopiert Claudes letzte Antwort in die Zwischenablage des Mac.", None),
    "desktop": ("In Claude Desktop weiter", "Setzt die Sitzung in der Desktop-App fort.", None),
    "design": ("Design-Zugriff", "Erlaubt oder entzieht Claude den Zugriff auf deine Design-Projekte.", None),
    "help": ("Hilfe", "Zeigt die Hilfe und alle Befehle.", None),
    "hooks": ("Hooks", "Zeigt, welche Hooks bei welchen Werkzeug-Ereignissen laufen – über solche Hooks ist auch iris angebunden.", None),
    "ide": ("Entwicklungsumgebung", "Verbindung zu Entwicklungsumgebungen verwalten.", None),
    "import": ("Einstellungen übernehmen", "Übernimmt die Konfiguration aus einem anderen KI-Werkzeug (Codex, Gemini).", None),
    "keybindings": ("Tastenkürzel", "Öffnet die Datei mit den Tastenkürzeln.", None),
    "list-agents": ("Agenten auflisten", "Zeigt Subagenten und andere Claude-Sitzungen, denen man schreiben kann.", None),
    "loops": ("Schleifen", "Wiederkehrende Aufträge anzeigen, anlegen und löschen.", None),
    "mcp": ("MCP-Server", "Verbindungen zu Werkzeug-Servern verwalten.", None),
    "memory": ("Gedächtnis", "CLAUDE.md-Dateien und die Einstellungen fürs Gedächtnis bearbeiten.", None),
    "mobile": ("Handy-App", "Zeigt einen QR-Code für die Claude-App.", None),
    "pause-memory": ("Gedächtnis pausieren", "Schaltet das automatische Gedächtnis für diese Sitzung ab.", None),
    "permissions": ("Berechtigungen", "Regeln, welche Werkzeuge ohne Nachfrage laufen dürfen und welche nie.", None),
    "plugin": ("Plugins", "Plugins verwalten.", None),
    "powerup": ("Funktionen entdecken", "Kurze interaktive Lektionen zu Funktionen von Claude Code.", None),
    "privacy-settings": ("Datenschutz", "Datenschutz-Einstellungen ansehen und ändern.", None),
    "remote-control": ("Fernsteuerung", "Diese Sitzung vom Handy oder von claude.ai/code aus steuern.", None),
    "remote-env": ("Cloud-Umgebung", "Standardumgebung für Cloud-Agenten wählen.", None),
    "resume": ("Gespräch fortsetzen", "Ein früheres Gespräch wieder öffnen – mit Suche.", "Suchbegriff"),
    "schedule": ("Geplante Agenten", "Agenten anlegen, die zu festen Zeiten in der Cloud laufen.", None),
    "scroll-speed": ("Scrollgeschwindigkeit", "Wie schnell das Mausrad scrollt.", None),
    "session": ("Cloud-Sitzung", "Adresse und QR-Code der Cloud-Sitzung.", None),
    "skill-doctor": ("Skill-Prüfung", "Zeigt, welche geladenen Skills ungenutzt sind und Kontext kosten.", None),
    "skills": ("Skills", "Listet die verfügbaren Skills.", None),
    "status": ("Status", "Version, Modell, Konto, Verbindung und Werkzeuge auf einen Blick.", None),
    "stop": ("Hintergrundsitzung beenden", "Beendet eine Sitzung im Hintergrund; Verlauf und Arbeitsstand bleiben.", None),
    "tasks": ("Hintergrundaufgaben", "Alles ansehen und verwalten, was im Hintergrund läuft.", None),
    "team-onboarding": ("Team-Einführung", "Schreibt aus deiner Nutzung eine Anleitung für andere im Team.", None),
    "theme": ("Farbschema", "Farbschema des Terminals ändern.", None),
    "tui": ("Darstellung", "Zwischen normaler und Vollbild-Darstellung im Terminal wechseln.", None),
    "update": ("Aktualisieren", "Auf die neueste Version wechseln – das Gespräch läuft weiter.", None),
    "usage": ("Verbrauch", "Kosten der Sitzung, Abo-Verbrauch und Aktivität.", None),
    "usage-credits": ("Zusatzguthaben", "Guthaben für mehr Nutzung einrichten.", None),
    "version": ("Version", "Zeigt die Version dieser Sitzung.", None),
    "voice": ("Sprachmodus", "Sprachmodus ein- oder ausschalten.", None),
    "web-setup": ("Claude Code im Web", "Claude Code im Web mit GitHub einrichten.", None),
    "wellbeing": ("Pausen", "Erinnerungen an Pausen und Ruhezeiten einstellen.", None),
    "workflows": ("Workflows", "Laufende und fertige Workflows ansehen.", None),
    "model": ("Modell wechseln", "Wählt das Modell für diese und alle neuen Sitzungen.", None),
    "background": ("In den Hintergrund", "Schickt die Sitzung in den Hintergrund und gibt das Terminal frei.", None),
    "teleport": ("In die Cloud", "Schickt die Sitzung in die Cloud oder holt eine von claude.ai.", None),
    "ultraplan": ("Plan im Web", "Claude Code im Web entwirft einen Plan zum Bearbeiten und Freigeben.", None),
    "ultrareview": ("Tiefe Prüfung", "Sucht und prüft Fehler im Zweig mit Claude Code im Web – kostet extra.", None),
    "logout": ("Abmelden", "Meldet dich bei Anthropic ab.", None),
}

MAC_ONLY = "öffnet eine Ansicht im Terminal – nur am Mac bedienbar"
SHOWS_ONLY = "zeigt sein Ergebnis nur im Terminal"


# ---------- Claude Code's own, from the program ----------

def _binary():
    exe = shutil.which("claude")
    return os.path.realpath(exe) if exe else None


def _object(m, start):
    """The text of the object literal opening at `start`, braces counted,
    strings skipped. Minified, so an approximation - good enough here."""
    depth, i, end = 0, start, min(len(m), start + 2000)
    quote = None
    while i < end:
        ch = m[i:i + 1]
        if quote:
            if ch == b"\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in (b'"', b"`"):
            quote = ch
        elif ch == b"{":
            depth += 1
        elif ch == b"}":
            depth -= 1
            if depth == 0:
                return m[start:i + 1]
        i += 1
    return m[start:end]


def _text(raw):
    return re.sub(r"\$\{[^}]*\}", "…", raw.decode("utf-8", "replace"))


def extract(path):
    """Every command object in the program: name -> {description, hint, type,
    nonint}. Hidden ones are left out."""
    out = {}
    with open(path, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as m:
        for mo in re.finditer(rb'name:"([a-z][a-z0-9-]{1,30})"', m):
            start = m.rfind(b"{", max(0, mo.start() - 400), mo.start())
            if start < 0:
                continue
            obj = _object(m, start)
            if mo.group(0) not in obj:
                continue
            kind = re.search(rb'type:"(local|local-jsx|prompt|text)"', obj)
            if not kind and b"progressMessage:" not in obj and b"pluginCommand:" not in obj:
                continue
            d = (re.search(rb'description:"([^"]{4,300})"', obj)
                 or re.search(rb'get description\(\)\{return"([^"]{4,300})"', obj)
                 or re.search(rb'get description\(\)\{return`([^`]{4,300})`', obj)
                 # a choice between two texts: the second is the usual one
                 or re.search(rb'get description\(\)\{return[^"`]{1,80}\?"[^"]{4,300}":"([^"]{4,300})"', obj))
            if not d:
                continue
            name = mo.group(1).decode()
            hidden = b"isHidden:!0" in obj
            if name in out and (hidden or not out[name]["hidden"]):
                continue
            hint = re.search(rb'argumentHint:"([^"]{1,120})"', obj)
            out[name] = {"description": _text(d.group(1)),
                         "hint": hint.group(1).decode() if hint else "",
                         "type": kind.group(1).decode() if kind else "prompt",
                         "nonint": b"supportsNonInteractive:!0" in obj,
                         "hidden": hidden}
    return {n: c for n, c in out.items() if not c["hidden"]}


def builtin():
    """Claude Code's own commands, read once per installed version."""
    path = _binary()
    if not path or not os.path.isfile(path):
        return {}
    stamp = f"{path}:{os.path.getmtime(path)}"
    try:
        cached = config.read_json(CACHE)
        if cached.get("stamp") == stamp:
            return cached["items"]
    except (OSError, ValueError, KeyError):
        pass
    items = extract(path)
    try:
        os.makedirs(config.CONFIG_DIR, exist_ok=True)
        with open(CACHE, "w", encoding="utf-8") as fh:
            json.dump({"stamp": stamp, "items": items}, fh)
    except OSError:
        pass
    return items


# ---------- skills and custom commands, from disk ----------

def _frontmatter(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            head = fh.read(6000)
    except OSError:
        return {}
    if not head.startswith("---"):
        return {}
    meta = {}
    for line in head.split("\n")[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip().strip("'\"")
    return meta


def _first_sentence(text, limit=150):
    text = " ".join((text or "").split())
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    short = m.group(1) if m else text
    return short if len(short) <= limit else short[:limit - 1].rstrip() + "…"


def _plugin_roots():
    """Installed plugins: (plugin name, folder)."""
    try:
        with open(os.path.join(config.HOME, ".claude", "plugins", "installed_plugins.json")) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    rows = data.get("plugins", data) if isinstance(data, dict) else {}
    out = []
    for key, entries in rows.items() if isinstance(rows, dict) else []:
        for e in entries if isinstance(entries, list) else [entries]:
            path = isinstance(e, dict) and e.get("installPath")
            if path and os.path.isdir(path):
                out.append((key.split("@")[0], path))
    return out


def custom(cwd):
    """Skills and custom commands this session can call, by the name typed
    after the slash."""
    home = os.path.join(config.HOME, ".claude")
    places = [("skill", os.path.join(home, "skills"), ""),
              ("command", os.path.join(home, "commands"), "")]
    if cwd:
        places += [("skill", os.path.join(cwd, ".claude", "skills"), ""),
                   ("command", os.path.join(cwd, ".claude", "commands"), "")]
    for plugin, root in _plugin_roots():
        places += [("skill", os.path.join(root, "skills"), plugin + ":"),
                   ("command", os.path.join(root, "commands"), plugin + ":")]
    out = {}
    for group, folder, prefix in places:
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for n in names:
            if group == "skill":
                path = os.path.join(folder, n, "SKILL.md")
                name = n
            elif n.endswith(".md"):
                path = os.path.join(folder, n)
                name = n[:-3]
            else:
                continue
            meta = _frontmatter(path)
            if not meta and not os.path.isfile(path):
                continue
            desc = meta.get("description", "")
            out[prefix + (meta.get("name") if group == "skill" and meta.get("name") else name)] = {
                "group": group, "summary": _first_sentence(desc) or "ohne Beschreibung",
                "detail": desc[:700], "hint": meta.get("argument-hint", "")}
    return out


# ---------- together, for one session ----------

def for_session(sess):
    terminal = type(sess).__name__ == "TerminalSession"
    cwd = getattr(sess, "cwd", "") or ""
    rows = []
    for name, c in builtin().items():
        if name in HIDDEN:
            continue
        short, long, hint = DE.get(name, (None, None, None))
        # A view the command opens in the terminal - shown on the phone.
        view = (c.get("type") == "local-jsx" and name not in PHONE) or name in OUTPUT
        if terminal:
            # The phone sees the terminal's screen and has Esc, Enter and
            # typing for it: all but what changes more than this session
            # or opens an editor.
            ok = name not in NEVER and name not in EDITOR
        else:
            # A session iris hosts reads commands from a pipe, not a terminal:
            # only what Claude Code runs without one.
            ok = name in PHONE and c.get("nonint")
        why = None if ok else NEVER.get(name) or EDITOR.get(name) or (
            SHOWS_ONLY if name in OUTPUT else "geht in dieser Sitzung nicht" if name in PHONE else MAC_ONLY)
        detail = long or c["description"]
        shows = bool(ok and terminal and view)
        if shows:
            detail += (" Die Ansicht erscheint auf dem Handy – lesen, eintippen, Enter und Esc "
                       "gehen von dort; blättern mit den Pfeiltasten nur am Mac." if name in NAV else
                       " Die Ansicht erscheint auf dem Handy, Esc schließt sie.")
        rows.append({"name": name, "group": "claude", "phone": bool(ok), "why": why,
                     "summary": short or c["description"], "detail": detail,
                     "original": c["description"], "hint": hint or c["hint"], "view": shows})
    for name, c in custom(cwd).items():
        rows.append({"name": name, "group": c["group"], "phone": True, "why": None,
                     "summary": c["summary"], "detail": c["detail"], "original": "",
                     "hint": c["hint"], "view": False})
    order = {"claude": 0, "skill": 1, "command": 2}
    rows.sort(key=lambda r: (not r["phone"], order[r["group"]], r["name"]))
    return rows
