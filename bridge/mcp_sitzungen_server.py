#!/usr/bin/env python3
"""MCP-Server: andere Sitzungen führen und eine Messreihe halten.

Der dritte neben Freigaben und Inventar, und der Grund, warum es einen
Vorarbeiter überhaupt geben kann (docs/PLAN.md, 6b). Ohne ihn kann eine
Sitzung die Brücke nur von außen ansprechen - mit curl und Token, also gar
nicht.

Zwei Entscheidungen, die hier drinstecken:

**Alles geht über die HTTP-Schnittstelle der Brücke**, nichts direkt an die
Dateien. Die Brücke bleibt die Einzige, die Wachen schreibt; zwei Schreiber
auf dieselbe Datei wären ein Rennen, das niemand gewinnt.

**Es gibt kein `measure`.** Der naheliegende Wunsch wäre ein Werkzeug, das
einen Prüfbefehl ausführt und die Zahl zurückgibt. Das wäre ein zweiter Weg,
Befehle auf diesem Rechner zu starten - an den Freigaben vorbei. Stattdessen
lässt der Vorarbeiter die beaufsichtigte Sitzung messen: sie hat die Werkzeuge
schon, und sie fragt nach, wenn etwas heikel ist.

Spricht JSON-RPC 2.0 über stdin/stdout, ohne Fremdpakete.
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge import config  # noqa: E402

TOOLS = [
    {
        "name": "sitzungen",
        "description": ("Alle Sitzungen auf allen Rechnern, die iris kennt: "
                        "Rechner, Schlüssel, Titel, Verzeichnis, ob gerade "
                        "gearbeitet wird. Nennt auch, welcher Rechner nicht "
                        "antwortet - das ist etwas anderes als 'keine Sitzungen'."),
        "inputSchema": {"type": "object", "properties": {
            "maschine": {"type": "string", "description": "welcher Rechner; leer = der eigene"}}},
    },
    {
        "name": "sitzung_lesen",
        "description": ("Die letzten Nachrichten einer Sitzung, verdichtet. "
                        "Bewusst nicht der ganze Verlauf: sonst wächst der eigene "
                        "Kontext mit dem der beaufsichtigten Sitzung mit."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sitzung": {"type": "string", "description": "Schlüssel der Sitzung"},
                "anzahl": {"type": "integer", "description": "wie viele Karten, Vorgabe 12"},
                "maschine": {"type": "string"},
            },
            "required": ["sitzung"],
        },
    },
    {
        "name": "sitzung_beauftragen",
        "description": ("Einer Sitzung den nächsten Auftrag schicken. Sie arbeitet "
                        "ihn wie eine getippte Nachricht ab; das Ende ihres Zuges "
                        "weckt dich von selbst wieder."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sitzung": {"type": "string"},
                "text": {"type": "string"},
                "maschine": {"type": "string"},
            },
            "required": ["sitzung", "text"],
        },
    },
    {
        "name": "wache_anlegen",
        "description": ("Einen Auftrag unter Aufsicht stellen: Ziel, zu "
                        "beaufsichtigende Sitzung, Maß und Budget in Runden. Ohne "
                        "Maß ist es keine Aufsicht - frag zuerst danach."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ziel": {"type": "string"},
                "sitzung": {"type": "string"},
                "mass": {"type": "string", "description": "die Zahl, die zählt, z. B. 'ms je Bild'"},
                "budget": {"type": "integer", "description": "Runden, Vorgabe 20"},
            },
            "required": ["ziel", "sitzung"],
        },
    },
    {
        "name": "wache_runde",
        "description": ("Eine Runde eintragen. Gibt zurück, ob seit drei Runden "
                        "nichts besser wurde und ob das Budget aufgebraucht ist - "
                        "beides Gründe aufzuhören."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "wache": {"type": "string"},
                "wert": {"type": "number", "description": "die gemessene Zahl, kleiner ist besser"},
                "notiz": {"type": "string"},
            },
            "required": ["wache"],
        },
    },
    {
        "name": "wachen",
        "description": "Alle Aufträge mit Ziel, Messreihe, Budget und Stand.",
        "inputSchema": {
            "type": "object",
            "properties": {"nur_laufende": {"type": "boolean"}},
        },
    },
    {
        "name": "wache_beenden",
        "description": ("Einen Auftrag abschließen, mit Grund: Ziel erreicht, "
                        "Stillstand, Budget, oder «NAME» hat abgebrochen."),
        "inputSchema": {
            "type": "object",
            "properties": {"wache": {"type": "string"}, "grund": {"type": "string"}},
            "required": ["wache", "grund"],
        },
    },
]


# Andere Rechner, die dieser Vorarbeiter erreichen darf.
#
# Er läuft auf dem Rechner, der immer an ist - dem Pi -, und gearbeitet wird
# auf dem Mac. Ist der Mac zu, ist der Assistent trotzdem da; ist er offen,
# soll der Vorarbeiter auch dort etwas ausrichten können.
#
# Die Brücken kennen einander weiterhin nicht (siehe shared/Kurier.swift). Was
# hier steht, ist eine Klientenliste, wie die App sie ohnehin hat - der
# Vertrauensanker bleibt beim Klienten, nicht bei einer Brücke. Und er kann
# sie nicht selbst erweitern: die Datei legt ein Mensch an.
#
#   ~/.config/iris/maschinen.json
#   [{"name": "mac", "base": "http://100.64.0.1:8780", "token": "..."}]
MASCHINEN = os.path.join(config.CONFIG_DIR, "maschinen.json")


def _maschinen():
    c = config.load()
    hier = {"name": "hier",
            "base": f"http://{c.get('host') or '127.0.0.1'}:{c.get('port') or 8780}",
            "token": c.get("token") or ""}
    liste = [hier]
    try:
        with open(MASCHINEN, encoding="utf-8") as fh:
            weitere = json.load(fh)
        if isinstance(weitere, list):
            liste += [m for m in weitere if isinstance(m, dict) and m.get("base")]
    except (OSError, ValueError):
        pass
    return liste


def _waehle(name):
    alle = _maschinen()
    if not name:
        return alle[0]
    for m in alle:
        if (m.get("name") or "").lower() == name.lower():
            return m
    return alle[0]


def _ruf(pfad, koerper=None, methode=None, maschine=None):
    m = _waehle(maschine)
    url = f"{m['base'].rstrip('/')}/{pfad}"
    url += ("&" if "?" in url else "?") + "token=" + (m.get("token") or "")
    daten = json.dumps(koerper).encode() if koerper is not None else None
    req = urllib.request.Request(url, data=daten, method=methode or ("POST" if daten else "GET"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return {"error": f"{e.code}: {e.read().decode()[:200]}"}
    except OSError as e:
        return {"error": f"Brücke nicht erreichbar: {e}"}


def _text(x):
    return {"content": [{"type": "text", "text": x if isinstance(x, str)
                         else json.dumps(x, ensure_ascii=False, indent=1)}]}


# Welcher Rechner welche Sitzung haelt - gefuellt beim Auflisten, damit man
# eine Sitzung danach am Schluessel ansprechen kann, ohne zu wissen, wo sie
# liegt. Er denkt in Sitzungen, nicht in Rechnern.
_wo = {}


def _alle_sitzungen():
    zeilen, stumm = [], []
    for m in _maschinen():
        d = _ruf("api/sessions", maschine=m.get("name"))
        if "error" in d:
            stumm.append({"maschine": m.get("name"), "grund": d["error"][:120]})
            continue
        for s in d.get("sessions", []):
            _wo[s.get("key")] = m.get("name")
            zeilen.append({"maschine": m.get("name"), "key": s.get("key"),
                           "titel": s.get("title") or s.get("label"),
                           "cwd": s.get("cwd"), "busy": s.get("busy"),
                           "beendet": s.get("exited"), "rolle": s.get("rolle") or ""})
    # Ein stummer Rechner wird genannt, nicht verschwiegen: "keine Sitzungen"
    # und "nicht erreichbar" sind zweierlei, und der Unterschied entscheidet,
    # ob man wartet oder handelt.
    return {"sitzungen": zeilen, "nicht_erreichbar": stumm}


def _maschine_von(args):
    """Der Rechner zu einer Sitzung: gesagt, gemerkt, oder eben nachgesehen."""
    if args.get("maschine"):
        return args["maschine"]
    key = args.get("sitzung")
    if key not in _wo:
        _alle_sitzungen()
    return _wo.get(key)


def call(name, args):
    if name == "sitzungen":
        return _text(_alle_sitzungen())
    if name == "sitzung_lesen":
        anzahl = int(args.get("anzahl") or 12)
        d = _ruf(f"api/sessions/{args['sitzung']}/history?limit={anzahl}",
                 maschine=_maschine_von(args))
        karten = d.get("cards", d) if isinstance(d, dict) else d
        return _text(karten[-anzahl:] if isinstance(karten, list) else karten)
    if name == "sitzung_beauftragen":
        return _text(_ruf(f"api/sessions/{args['sitzung']}/message",
                          {"text": args.get("text", "")},
                          maschine=_maschine_von(args)))
    if name == "wache_anlegen":
        return _text(_ruf("api/wachen", {
            "ziel": args.get("ziel", ""), "sitzung": args.get("sitzung", ""),
            "vorarbeiter": os.environ.get("IRIS_SESSION_KEY", ""),
            "mass": args.get("mass", ""), "budget": args.get("budget") or 20}))
    if name == "wache_runde":
        return _text(_ruf(f"api/wachen/{args['wache']}/runde",
                          {"wert": args.get("wert"), "notiz": args.get("notiz", "")}))
    if name == "wachen":
        pfad = "api/wachen" + ("?stand=laeuft" if args.get("nur_laufende") else "")
        return _text(_ruf(pfad))
    if name == "wache_beenden":
        return _text(_ruf(f"api/wachen/{args['wache']}/ende",
                          {"grund": args.get("grund", "")}))
    return {"content": [{"type": "text", "text": f"Unbekanntes Werkzeug: {name}"}],
            "isError": True}


def respond(rid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": rid}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, rid = req.get("method"), req.get("id")
        if method == "initialize":
            respond(rid, {
                "protocolVersion": req.get("params", {}).get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "iris-sitzungen", "version": "1.0.0"},
            })
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            name = config.nutzer()
            respond(rid, {"tools": [
                {**t, "description": t["description"].replace("«NAME»", name)}
                for t in TOOLS]})
        elif method == "tools/call":
            params = req.get("params", {})
            try:
                respond(rid, call(params.get("name", ""), params.get("arguments") or {}))
            except Exception as exc:        # noqa: BLE001 - melden, nie sterben
                respond(rid, {"content": [{"type": "text", "text": f"Fehler: {exc}"}],
                              "isError": True})
        elif rid is not None:
            respond(rid, error={"code": -32601, "message": f"unknown: {method}"})


if __name__ == "__main__":
    main()
