"""Ein Zustand, den niemand fortschreibt, gilt nicht als lebendig.

Am 12.09.2026 um 10:04 starb der Bewohner - sein Startbefehl hing an einer
SSH-Sitzung und ging mit ihr. bewohner.json blieb liegen, mit state "wach"
und einem Zeitstempel von 10:04:11. /api/resident las "state" und meldete
anderthalb Minuten lang "wach". Nach aussen sah der Ausfall aus wie Betrieb.

Diese Probe haelt fest, was seitdem gilt: Wer einen Zustand liest, liest sein
Alter mit. Ein fehlender oder alter Zeitstempel heisst nicht "wach".

    python lebendig_test.py
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import bewohner

gesamt = 0
fehler = 0


def pruefe(bedingung: bool, was: str) -> None:
    global gesamt, fehler
    gesamt += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        fehler += 1


def datei(inhalt) -> Path:
    p = Path(tempfile.mkdtemp()) / "bewohner.json"
    if inhalt is not None:
        p.write_text(json.dumps(inhalt, ensure_ascii=False), encoding="utf-8")
    return p


def main() -> int:
    print("Probe Lebendigkeit")
    jetzt = 1_789_200_000.0
    grenze = bewohner.TOT_NACH_S

    # Der Fall vom 10:04, nachgestellt: frischer Zustand, dann derselbe
    # Zustand anderthalb Minuten spaeter, ohne dass jemand ihn anfasst.
    zustand = {"state": "wach", "pid": 56192, "updated": jetzt,
               "last_check": jetzt, "puls_s": 20.0, "tot_nach_s": grenze,
               "gueltig_bis": jetzt + grenze}
    p = datei(zustand)

    d = bewohner.zustand_lesen(p, jetzt_=jetzt + 1)
    pruefe(d["lebt"] and d["state"] == "wach", "frisch fortgeschrieben: wach")

    d = bewohner.zustand_lesen(p, jetzt_=jetzt + 90)
    pruefe(not d["lebt"], "90 s ohne Fortschreibung: nicht mehr lebendig")
    pruefe(d["state"] == "tot",
           "und es steht auch so da, nicht \"wach\": %r" % d["state"])
    pruefe(d["state_roh"] == "wach", "was in der Datei stand, bleibt lesbar")
    pruefe(d["alter_s"] == 90.0, "das Alter steht dabei: %s s" % d["alter_s"])
    pruefe("wach" in d["warum"] and "90" in d["warum"],
           "und ein Satz, der den Irrtum erklaert")

    # Genau an der Grenze noch lebendig, eine Sekunde darueber nicht mehr.
    pruefe(bewohner.zustand_lesen(p, jetzt_=jetzt + grenze)["lebt"],
           "genau %.0f s alt: noch lebendig" % grenze)
    pruefe(not bewohner.zustand_lesen(p, jetzt_=jetzt + grenze + 1)["lebt"],
           "%.0f s alt: tot" % (grenze + 1))

    # Zwei Zyklen, wie der Mac es verlangt hat - nicht mehr.
    pruefe(grenze <= 3 * bewohner.PULS_ZUSTAND_S,
           "die Grenze liegt bei zwei Pulsen, nicht bei zehn (%.0f s bei "
           "Puls %.0f s)" % (grenze, bewohner.PULS_ZUSTAND_S))
    pruefe(grenze < 90,
           "und faengt den Fall vom 10:04 (90 s) sicher ab")

    # Ein Zustand ohne Zeitstempel ist kein Zustand.
    d = bewohner.zustand_lesen(datei({"state": "wach", "pid": 1}),
                               jetzt_=jetzt)
    pruefe(not d["lebt"] and d["state"] == "unbekannt",
           "ohne Zeitstempel: unbekannt, nicht wach")

    # Fehlt die Datei, ist die ehrliche Antwort "ich weiss es nicht".
    d = bewohner.zustand_lesen(Path(tempfile.mkdtemp()) / "fehlt.json",
                               jetzt_=jetzt)
    pruefe(not d["lebt"] and d["state"] == "unbekannt",
           "keine Datei: unbekannt")
    d = bewohner.zustand_lesen(datei("kaputt"), jetzt_=jetzt)
    pruefe(not d["lebt"] and d["state"] == "unbekannt", "kein Objekt: unbekannt")
    p2 = datei(None)
    p2.write_text("{kein json", encoding="utf-8")
    pruefe(bewohner.zustand_lesen(p2, jetzt_=jetzt)["state"] == "unbekannt",
           "unlesbar: unbekannt")

    # Eine alte Fassung ohne tot_nach_s wird trotzdem geprueft - sonst waere
    # der eine Zustand, der die Regel nicht kennt, von ihr ausgenommen.
    d = bewohner.zustand_lesen(
        datei({"state": "denkt", "updated": jetzt}), jetzt_=jetzt + 300)
    pruefe(not d["lebt"] and d["state"] == "tot",
           "alte Fassung ohne tot_nach_s: die eingebaute Grenze gilt")

    # last_check genuegt, wenn updated fehlt.
    d = bewohner.zustand_lesen(
        datei({"state": "wach", "last_check": jetzt}), jetzt_=jetzt + 5)
    pruefe(d["lebt"], "last_check zaehlt, wenn updated fehlt")

    # Und die Kurzform.
    pruefe(bewohner.lebt(p) in (True, False), "lebt() antwortet mit ja/nein")

    # Der laufende Bewohner, falls er laeuft: die Probe darf ihn nicht
    # fuer tot erklaeren, waehrend er denkt.
    echt = bewohner.zustand_lesen()
    print("  --  echter Zustand jetzt: %s (%s)"
          % (echt.get("state"), echt.get("warum")))

    print("%d von %d bestanden" % (gesamt - fehler, gesamt))
    return 1 if fehler else 0


if __name__ == "__main__":
    raise SystemExit(main())
