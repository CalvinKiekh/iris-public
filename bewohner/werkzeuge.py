"""Eigene Werkzeuge — was ihm fehlt, lässt er sich bauen.

Merkt gpt-oss, dass ihm eine Faehigkeit fehlt, beauftragt der Bewohner Claude
damit: ein Skript plus ein Selbsttest. Danach prueft er es SELBST und traegt
es erst dann ein. Dirigent, nicht Handwerker - er schreibt den Code nicht,
aber er nimmt ihn ab.

    werkstatt\\werkzeuge\\<name>.py     das Werkzeug
    werkstatt\\werkzeuge.json          was es kann und ob es geprueft ist

Grenzen, die im Auftrag an Claude stehen und beim Pruefen kontrolliert werden:

  - Ein Werkzeug schreibt nur in werkstatt\\. Alles darueber hinaus ist ein
    Antrag an Calvin, kein Alleingang.
  - Kein Netz, ausser localhost.
  - Es muss `python <datei> --selbsttest` verstehen und dabei 0 zurueckgeben.
"""
from __future__ import annotations

import einstellungen
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"
ORDNER = WERKSTATT / "werkzeuge"
VERZEICHNIS = WERKSTATT / "werkzeuge.json"

# Was ein Werkzeug nicht tun darf. Beim Pruefen wird der Quelltext danach
# durchgesehen - eine grobe Sperre, aber sie faengt das Offensichtliche.
VERBOTEN = (
    (r"\bshutil\.rmtree\b", "löscht Verzeichnisbäume"),
    (r"\bos\.remove\b|\bos\.unlink\b|\bPath\([^)]*\)\.unlink\b", "löscht Dateien"),
    (r"\bsubprocess\b", "startet fremde Programme"),
    # Netz wird weiter unten geprueft - localhost ist erlaubt (die lokalen
    # Modelle laufen dort). Ein pauschales Verbot war strenger als die
    # Abmachung und hat ein brauchbares Werkzeug abgelehnt.
    # Aus dem Heimatordner dieses Rechners, nicht aus einem festen Pfad: mit
    # dem stand die Regel bei jedem anderen Nutzer ins Leere. Und sie erkennt
    # den Pfad jetzt auch mit einfachen Backslashes - vorher schluepfte ein
    # Werkzeug mit r"C:\Users\...\Desktop\x" unbemerkt hindurch.
    (einstellungen.ausserhalb_der_werkstatt(), "schreibt außerhalb der Werkstatt"),
    (r"\beval\b|\bexec\b|__import__", "führt Code aus Zeichenketten aus"),
)

AUFTRAG = """Bau mir ein Werkzeug als einzelne Python-Datei.

Name: {name}
Zweck: {zweck}

Dein Arbeitsordner IST die Werkstatt. Arbeite ausschließlich mit relativen
Pfaden darin - dann braucht es keine Freigabe und nichts hängt.

Bedingungen, die ich beim Abnehmen prüfe:
- Die Datei heißt werkzeuge/{name}.py, relativ zu deinem Arbeitsordner
- Sie versteht `python werkzeuge/{name}.py --selbsttest` und gibt dabei 0
  zurück, wenn alles stimmt, sonst ungleich 0. Der Selbsttest prüft die
  eigentliche Funktion, nicht nur den Import.
- Sie hängt ihre Pfade am Ort der Datei auf, nicht am Arbeitsverzeichnis
- Sie schreibt NICHTS außerhalb von {werkstatt}
- Sie geht nicht ins Netz und startet keine fremden Programme
- Nur die Standardbibliothek
- Deutsche Kommentare, sprechende Namen

Gib mir am Ende eine Zeile "FERTIG", wenn die Datei liegt und der Selbsttest
bei dir durchläuft."""


def verzeichnis_lesen() -> dict:
    """Gibt {name: eintrag} zurück, egal ob die Datei eine Liste oder ein
    Objekt ist. Geschrieben wird als Liste (so steht es im Vertrag)."""
    try:
        roh = json.loads(VERZEICHNIS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(roh, list):
        return {w.get("name"): w for w in roh if isinstance(w, dict)
                and w.get("name")}
    return roh if isinstance(roh, dict) else {}


def verzeichnis_schreiben(d: dict) -> None:
    """Als LISTE, wie im Vertrag: name, zweck, aufruf, erstellt, geprueft."""
    WERKSTATT.mkdir(parents=True, exist_ok=True)
    liste_raus = []
    for name, w in d.items():
        eintrag = dict(w)
        eintrag["name"] = name
        liste_raus.append(eintrag)
    t = VERZEICHNIS.with_suffix(".json.tmp")
    t.write_text(json.dumps(liste_raus, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    t.replace(VERZEICHNIS)


def auftrag_bauen(name: str, zweck: str) -> str:
    ORDNER.mkdir(parents=True, exist_ok=True)
    datei = ORDNER / f"{name}.py"
    return AUFTRAG.format(name=name, zweck=zweck, ziel=ORDNER, datei=datei,
                          werkstatt=WERKSTATT)


def pruefen(name: str) -> tuple[bool, str]:
    """Nimmt ein gebautes Werkzeug ab. Erst lesen, dann laufen lassen.

    Die Reihenfolge ist Absicht: Wer den Quelltext erst nach dem Ausführen
    liest, hat ihn schon ausgeführt.
    """
    datei = ORDNER / f"{name}.py"
    if not datei.is_file():
        return False, "die Datei gibt es nicht"

    try:
        quelle = datei.read_text(encoding="utf-8", errors="replace")
    except OSError as f:
        return False, f"nicht lesbar ({type(f).__name__})"

    for muster, grund in VERBOTEN:
        if re.search(muster, quelle):
            return False, f"abgelehnt, weil es {grund}"

    # Netz nur nach localhost. Jede Adresse im Quelltext muss dorthin zeigen.
    if re.search(r"\bsocket\b|\brequests\b|\burllib\b|\bhttpx\b", quelle):
        ziele = re.findall(r"https?://([^/\s\"']+)", quelle)
        fremd = [z for z in ziele
                 if not z.startswith(("localhost", "127.0.0.1", "[::1]"))]
        if fremd or not ziele:
            return False, (f"abgelehnt, weil es ins Netz geht "
                           f"({', '.join(fremd[:2]) if fremd else 'Ziel unklar'})")

    try:
        lauf = subprocess.run(
            [sys.executable, "-X", "utf8", str(datei), "--selbsttest"],
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace", cwd=str(WERKSTATT),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as f:
        return False, f"Selbsttest nicht startbar ({type(f).__name__})"

    if lauf.returncode != 0:
        kurz = " ".join((lauf.stderr or lauf.stdout or "").split())[:160]
        return False, f"Selbsttest fehlgeschlagen: {kurz}"
    return True, " ".join((lauf.stdout or "bestanden").split())[:160]


def eintragen(name: str, zweck: str, ergebnis: str) -> None:
    d = verzeichnis_lesen()
    # "geprueft" ist Ja/Nein - der Zeitpunkt steht daneben.
    d[name] = {"zweck": zweck, "aufruf": f"python werkzeuge/{name}.py",
               "erstellt": time.time(), "geprueft": True,
               "geprueft_am": time.time(), "ergebnis": ergebnis}
    verzeichnis_schreiben(d)


def benutzen(name: str, *argumente: str) -> tuple[bool, str]:
    """Ein eingetragenes Werkzeug aufrufen. Nur eingetragene - was die
    Prüfung nicht bestanden hat, wird nicht benutzt."""
    if name not in verzeichnis_lesen():
        return False, "nicht im Verzeichnis"
    datei = ORDNER / f"{name}.py"
    try:
        lauf = subprocess.run(
            [sys.executable, "-X", "utf8", str(datei), *argumente],
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace", cwd=str(WERKSTATT),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as f:
        return False, f"{type(f).__name__}"
    return lauf.returncode == 0, " ".join(
        (lauf.stdout or lauf.stderr or "").split())[:400]


def liste() -> list[str]:
    return [f"{n}: {w['zweck']}" for n, w in verzeichnis_lesen().items()]
