"""Wachen: ein Auftrag, eine beaufsichtigte Sitzung, eine Messreihe.

Der Plan dazu steht in docs/PLAN.md, Abschnitt 6b. Das Wesentliche hier:

**Der Zustand liegt in Dateien, nicht in Prozessen.** Je Auftrag eine Datei
mit Ziel, Maß, Messreihe, Budget und Stand. Kein Prozess wartet, nichts läuft
mit. Deshalb kostet die zweite Wache fast nichts, deshalb überlebt eine Wache
jeden Neustart, und deshalb kann „wie ist der Stand?" ein Blick in ein
Verzeichnis sein statt ein Gespräch je Auftrag.

**Der Auslöser ist das Ende eines Zuges.** Die Brücke weiß auf die Sekunde,
wann eine Sitzung fertig ist - dieselbe Stelle, an der die Mitteilung ans
Telefon geht. Wer dort eine Wache hat, weckt seinen Vorarbeiter, statt dass
der nachfragen müsste. Nachfragen wäre der größte Posten der ganzen Rechnung:
zwanzig Runden mal „bist du fertig?" sind zwanzig Züge für nichts.
"""
import json
import os
import re
import threading
import time

from . import config

DIR = os.path.join(config.CONFIG_DIR, "wachen")
_lock = threading.RLock()

# Wie die Brücke den Vorarbeiter erreicht. Wird vom Manager gesetzt, damit
# dieses Modul weder Sitzungen noch Registry kennen muss - dieselbe Bauart wie
# bei push.configure().
_wecken = None


def configure(wecken):
    """`wecken(sitzungs_key, text) -> bool` hinterlegen."""
    global _wecken
    _wecken = wecken


def _pfad(wid):
    return os.path.join(DIR, wid + ".json")


def _lade(wid):
    try:
        with open(_pfad(wid), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _schreibe(w):
    os.makedirs(DIR, exist_ok=True)
    tmp = _pfad(w["id"]) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(w, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, _pfad(w["id"]))
    return w


def _kennung(ziel):
    """Ein lesbarer Name aus dem Ziel - man soll die Datei wiedererkennen."""
    roh = re.sub(r"[^a-z0-9]+", "-", (ziel or "wache").lower()).strip("-")
    return (roh[:40] or "wache") + "-" + str(int(time.time()))[-6:]


def neu(ziel, sitzung, vorarbeiter, mass="", budget=20):
    """Einen Auftrag anlegen.

    `mass` darf leer bleiben - dann ist die erste Aufgabe des Vorarbeiters,
    danach zu fragen. Ohne Maß ist es keine Aufsicht, sondern Zusehen.
    """
    with _lock:
        w = {"id": _kennung(ziel), "ziel": ziel, "mass": mass,
             "sitzung": sitzung, "vorarbeiter": vorarbeiter,
             "budget": int(budget), "stand": "laeuft",
             "runden": [], "erstellt": time.time(), "geaendert": time.time()}
        return _schreibe(w)


def liste(nur_laufende=False):
    try:
        namen = sorted(f[:-5] for f in os.listdir(DIR) if f.endswith(".json"))
    except OSError:
        return []
    alle = [w for w in (_lade(n) for n in namen) if w]
    return [w for w in alle if not nur_laufende or w.get("stand") == "laeuft"]


def fuer_sitzung(key):
    """Die laufende Wache über dieser Sitzung, falls es eine gibt."""
    for w in liste(nur_laufende=True):
        if w.get("sitzung") == key:
            return w
    return None


def runde(wid, wert=None, notiz=""):
    """Eine Runde eintragen. `wert` ist die gemessene Zahl, wenn es eine gibt."""
    with _lock:
        w = _lade(wid)
        if not w:
            return None
        w["runden"].append({"n": len(w["runden"]) + 1, "wert": wert,
                            "notiz": notiz[:500], "ts": time.time()})
        w["geaendert"] = time.time()
        return _schreibe(w)


def beenden(wid, grund):
    with _lock:
        w = _lade(wid)
        if not w:
            return None
        w["stand"] = "fertig"
        w["grund"] = grund
        w["geaendert"] = time.time()
        return _schreibe(w)


# Wie viel besser eine Zahl sein muss, damit sie als Fortschritt zählt.
#
# Ohne Schwelle ist 41 → 40 ein Fortschritt, und der Vorarbeiter läuft ewig
# weiter, weil es jede Runde ein Zehntel besser wird. Fünf Prozent sind die
# Grenze, unterhalb derer das Ergebnis genauso gut Messrauschen sein kann.
SCHWELLE = 0.05


def stillstand(w, seit=3, schwelle=None):
    """Ob sich die Zahl seit `seit` Runden nicht spürbar verbessert hat.

    Der eigentliche Grund für den ganzen Bau: wer seit zwanzig Zügen an einer
    Optimierung sitzt, merkt das nicht mehr selbst. Kleiner ist besser - die
    Maße, um die es geht (ms je Bild, Laufzeit), zählen nach unten.
    """
    schwelle = SCHWELLE if schwelle is None else schwelle
    werte = [r["wert"] for r in w.get("runden", []) if isinstance(r.get("wert"), (int, float))]
    if len(werte) <= seit:
        return False
    bestes_vorher = min(werte[:-seit])
    if bestes_vorher <= 0:
        return min(werte[-seit:]) >= bestes_vorher
    noetig = bestes_vorher * (1 - schwelle)
    return min(werte[-seit:]) > noetig


def budget_verbraucht(w):
    return len(w.get("runden", [])) >= int(w.get("budget", 0) or 0)


def bericht(w, runden=6):
    """Die Messreihe in der Form, in der sie einem Modell vorgelegt wird."""
    zeilen = [f"Ziel: {w.get('ziel', '')}",
              f"Maß: {w.get('mass') or '— noch keines vereinbart'}",
              f"Runde {len(w.get('runden', []))} von {w.get('budget')}"]
    for r in w.get("runden", [])[-runden:]:
        wert = r.get("wert")
        zeilen.append(f"  {r['n']}: " + (f"{wert}" if wert is not None else "—")
                      + (f"  {r.get('notiz', '')}" if r.get("notiz") else ""))
    return "\n".join(zeilen)


def nach_zug(sitzungs_key, text):
    """Ein Zug ist zu Ende - hängt eine Wache daran, wird geweckt.

    Hier wird nicht bewertet und nicht entschieden. Beides braucht ein Modell,
    und welches, ist eine Frage für den Vorarbeiter: er bekommt die Messreihe
    und das, was gesagt wurde, und macht daraus die nächste Runde oder einen
    Schluss.
    """
    w = fuer_sitzung(sitzungs_key)
    if not w or not _wecken:
        return None
    anlass = []
    if budget_verbraucht(w):
        anlass.append("Das Budget ist aufgebraucht.")
    if stillstand(w):
        anlass.append("Seit drei Runden keine Verbesserung.")
    auftrag = (
        f"[Wache {w['id']}] Die beaufsichtigte Sitzung hat ihren Zug beendet.\n\n"
        f"{bericht(w)}\n\n"
        f"Was sie zuletzt gesagt hat:\n{(text or '').strip()[:4000]}\n\n"
        + ("\n".join(anlass) + "\n\n" if anlass else "")
        + "Trage die Runde ein (Zahl, wenn eine gemessen wurde) und entscheide: "
          f"weiter mit einem neuen Auftrag, oder Schluss mit Bericht an {config.nutzer()}."
    )
    return _wecken(w["vorarbeiter"], auftrag)
