"""Ein Fehlen, das wie ein Normalzustand aussieht - die gefaehrlichste Art.

    python -X utf8 verlust_test.py

Am 12.09. zweimal getroffen, und beide Male erst Stunden spaeter bemerkt:

    erinnerungen.json fehlt  -> "habe ich Termine?"     -> "nein"
    ERINNERUNG.md fehlt      -> Kernwissen im Prompt    -> einfach weg

Kein Fehler im Log, kein Absturz, keine leere Datei - nur eine leere Liste,
und die sieht aus wie "nichts eingetragen". Eine leere Liste heisst "nichts
vorgemerkt", eine fehlende Datei heisst "was du mir genannt hast, ist weg".
"""
from __future__ import annotations

import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
import probenort
import verlust

ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}"
          + (f"  [{dazu}]" if dazu else ""))


print("\nDer Unterschied zwischen 'leer' und 'fehlt'")
ort = probenort.ablage("verlust")
try:
    # Eine vollstaendige Werkstatt: nichts zu melden.
    (ort / "werkzeuge").mkdir(parents=True, exist_ok=True)
    for pfad in (ort / "ERINNERUNG.md", ort / "gedaechtnis.db",
                 ort / "journal.jsonl", ort / "sitzungen.jsonl",
                 ort / "werkzeuge" / "erinnerungen.json"):
        pfad.write_text("[]", encoding="utf-8")
    pruefen("alles da -> kein Satz fuer den Prompt",
            verlust.satz(ort) == "", verlust.satz(ort)[:40])
    pruefen("und nichts als tragend-fehlend gemeldet",
            verlust.tragend_fehlt(ort) == [])

    # Eine LEERE Terminliste ist kein Verlust.
    (ort / "werkzeuge" / "erinnerungen.json").write_text("[]",
                                                         encoding="utf-8")
    pruefen("eine LEERE Liste ist kein Verlust - da ist nichts vorgemerkt",
            verlust.satz(ort) == "")

    # Eine FEHLENDE schon.
    (ort / "werkzeuge" / "erinnerungen.json").unlink()
    s = verlust.satz(ort)
    pruefen("eine FEHLENDE Liste ist einer", s != "")
    pruefen("und der Satz verbietet ausdruecklich das 'nein'",
            "Sag NICHT" in s and "verloren" in s, s[:92])
    namen = [n for n, _ in verlust.tragend_fehlt(ort)]
    pruefen("gemeldet als 'Terminliste'", namen == ["Terminliste"], str(namen))

    # Und fuer jede tragende Datei einzeln.
    for name, pfad, _ in verlust.TRAGEND:
        p = pfad(ort)
        roh = p.read_bytes() if p.exists() else None
        if roh is not None:
            p.unlink()
        s = verlust.satz(ort)
        pruefen(f"{name} fehlt -> es steht im Prompt",
                name in [n for n, _ in verlust.tragend_fehlt(ort)], s[:50])
        if roh is not None:
            p.write_bytes(roh)

    print("\nWas im Prompt ankommt, steht GANZ VORN")
    import gedaechtnis
    quelle = Path(gedaechtnis.__file__).read_text(encoding="utf-8")
    pruefen("fuer_prompt() holt den Satz, bevor es Kernwissen anhaengt",
            quelle.index("import verlust") < quelle.index('f"[Kernwissen]'),
            "sonst stuende er hinter 1500 Zeichen und waere abgeschnitten")

    print("\nUnd erinnern kann es jetzt selbst unterscheiden")
    sys.path.insert(0, str(HIER / "werkstatt" / "werkzeuge"))
    import erinnern
    leer = ort / "leer.json"
    leer.write_text("[]", encoding="utf-8")
    pruefen("liste_fehlt() ist False bei leerer Datei",
            erinnern.liste_fehlt(str(leer)) is False)
    pruefen("und True bei fehlender", erinnern.liste_fehlt(str(ort / "weg.json")))
    pruefen("lesen() bleibt unveraendert - faellige() baut darauf",
            erinnern.lesen(str(leer)) == []
            and erinnern.lesen(str(ort / "weg.json")) == [])

    print("\nDie WACHE, weil der Hinweis im Prompt nicht reichte")
    # Gemessen am 13.09. um 01:10: Im Prompt stand, dass die Liste fehlt und
    # er es sagen soll. gpt-oss antwortete "Es liegen keine Termine vor."
    # Eine Regel im Systemtext ist eine Bitte, eine Wache davor ist eine
    # Zusage - derselbe Satz steht in wissen.mangel().
    import gespraech
    echte = HIER / "werkstatt"
    for frage in ("Habe ich Termine?", "Was steht heute an?",
                  "Wann muss ich zum Arzt?", "Habe ich etwas vorgemerkt?"):
        a = gespraech.dienst_antwort(frage, echte, {"state": "wach"}, None)
        pruefen(f"der Dienst antwortet selbst: {frage[:30]}",
                bool(a) and "fehlt" in str(a), str(a)[:54])
        # NICHT ueber ein verbotenes Teilwort pruefen: Der richtige Satz
        # enthaelt "keine Termine vorliegen" - negiert ("Es ist nicht so,
        # dass ..."). Die erste Fassung dieser Probe verbot genau das und
        # fiel an der richtigen Antwort durch. Geprueft wird, was der Satz
        # LEISTEN muss: Er nennt den Verlust und das Datum.
        pruefen("  er nennt den Verlust und wann er war",
                bool(a) and "verloren" in str(a)
                and "12. September" in str(a), str(a)[-52:])
    # Fragen ohne Terminbezug duerfen NICHT daran haengen.
    for frage in ("Wie spät ist es?", "Wer belegt den meisten Speicher?"):
        a = gespraech.dienst_antwort(frage, echte, {"state": "wach"}, None)
        pruefen(f"unberuehrt: {frage[:28]}",
                bool(a) and "Terminliste" not in str(a), str(a)[:44])

    print("\nAm ECHTEN Stand: was fehlt gerade?")
    fehlt = verlust.tragend_fehlt()
    print(f"       {[n for n, _ in fehlt]}")
    pruefen("mindestens Kernwissen und Terminliste fehlen heute",
            {"Kernwissen", "Terminliste"} <= {n for n, _ in fehlt},
            str([n for n, _ in fehlt]))
    echt = verlust.satz()
    pruefen("und der Satz steht bereit fuer jeden Prompt", echt != "")
finally:
    probenort.wegraeumen(ort)

print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
