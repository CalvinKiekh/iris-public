"""ansprechen - von sich aus etwas sagen, aber nicht zur Unzeit.

    python ansprechen.py --pruefen "Text"   darf das jetzt raus?
    python ansprechen.py --dringend "Text"  auch nachts
    python ansprechen.py --selbsttest

Bisher hat er nur geantwortet. Von sich aus zu sprechen ist etwas anderes:
Es kostet Calvin Aufmerksamkeit, ob er will oder nicht. Deshalb entscheidet
dieses Werkzeug nicht, WAS er sagt, sondern OB er es jetzt sagen darf.

Drei Regeln:
  - Nachts (22 bis 7 Uhr) nur bei echten Stoerungen.
  - Waehrend der Arbeitszeit nur, was nicht warten kann.
  - Hoechstens eine Ansprache je Stunde, wenn sie nicht dringend ist -
    sonst wird aus Aufmerksamkeit Laerm.

Pfade haengen am Ort dieser Datei. Nur Standardbibliothek, kein Netz.
"""

from einstellungen import NAME
import argparse
import datetime
import json
import os
import sys

WERKZEUG_ORDNER = os.path.dirname(os.path.abspath(__file__))
WERKSTATT_ORDNER = os.path.dirname(WERKZEUG_ORDNER)
VERLAUF = os.path.join(WERKSTATT_ORDNER, "ansprachen.jsonl")
REGELN = os.path.join(WERKSTATT_ORDNER, "regeln.json")
LAGE = os.path.join(WERKSTATT_ORDNER, "lage.json")

RUHE_VON = 22
RUHE_BIS = 7
# So lange nach einer Ansprache bleibt er still, wenn es nicht dringend ist.
ABSTAND_MIN = 60


def in_werkstatt(pfad):
    ziel = os.path.abspath(pfad)
    wurzel = os.path.abspath(WERKSTATT_ORDNER)
    try:
        return os.path.commonpath([ziel, wurzel]) == wurzel
    except ValueError:
        return False


def _lesen(pfad):
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def ist_ruhezeit(jetzt=None):
    jetzt = jetzt or datetime.datetime.now()
    return jetzt.hour >= RUHE_VON or jetzt.hour < RUHE_BIS


def ist_arbeitszeit(jetzt=None):
    """Aus regeln.json - dieselbe Quelle wie die Bremse."""
    jetzt = jetzt or datetime.datetime.now()
    regeln = _lesen(REGELN).get("arbeitszeit") or {}
    tage = regeln.get("tage") or []
    kurz = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")[jetzt.weekday()]
    if kurz not in tage:
        return False
    try:
        von_s, von_m = (int(x) for x in str(regeln.get("von", "07:00")).split(":"))
        bis_s, bis_m = (int(x) for x in str(regeln.get("bis", "16:00")).split(":"))
    except ValueError:
        return False
    minute = jetzt.hour * 60 + jetzt.minute
    return von_s * 60 + von_m <= minute < bis_s * 60 + bis_m


def letzte(verlauf=VERLAUF):
    """Wann hat er zuletzt von sich aus gesprochen?"""
    if not os.path.isfile(verlauf):
        return None
    letzte_zeit = None
    with open(verlauf, "r", encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if not zeile:
                continue
            try:
                e = json.loads(zeile)
                letzte_zeit = datetime.datetime.fromisoformat(e["zeit"])
            except (ValueError, KeyError):
                continue
    return letzte_zeit


def darf(text, dringend=False, jetzt=None, verlauf=VERLAUF):
    """Darf das jetzt raus? Gibt (ja/nein, Begruendung) zurueck."""
    jetzt = jetzt or datetime.datetime.now()
    if not str(text).strip():
        return False, "ohne Text keine Ansprache"

    if ist_ruhezeit(jetzt) and not dringend:
        return False, ("es ist Ruhezeit (%d bis %d Uhr) und das kann warten"
                       % (RUHE_VON, RUHE_BIS))

    if ist_arbeitszeit(jetzt) and not dringend:
        return False, f"{NAME} arbeitet und das kann warten"

    if not dringend:
        zuletzt = letzte(verlauf)
        if zuletzt is not None:
            her = (jetzt - zuletzt).total_seconds() / 60.0
            if her < ABSTAND_MIN:
                return False, ("vor %d Minuten habe ich schon etwas gesagt"
                               % round(her))
    return True, "dringend" if dringend else "passt"


def vermerken(text, dringend=False, jetzt=None, verlauf=VERLAUF):
    """Haelt fest, dass gesprochen wurde - Grundlage fuer den Abstand."""
    if not in_werkstatt(verlauf):
        raise ValueError("Der Verlauf muss in der Werkstatt liegen.")
    jetzt = jetzt or datetime.datetime.now()
    with open(verlauf, "a", encoding="utf-8") as f:
        f.write(json.dumps({"zeit": jetzt.isoformat(timespec="seconds"),
                            "text": " ".join(str(text).split())[:300],
                            "dringend": bool(dringend)},
                           ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest():
    print("Selbsttest ansprechen")
    gesamt = 0
    fehler = 0

    def pruefe(bedingung, was):
        nonlocal gesamt, fehler
        gesamt += 1
        print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
        if not bedingung:
            fehler += 1

    ordner = os.path.join(WERKSTATT_ORDNER, "_ansprechen_selbsttest")
    if not os.path.isdir(ordner):
        os.makedirs(ordner)
    probe = os.path.join(ordner, "verlauf.jsonl")
    if os.path.isfile(probe):
        open(probe, "w", encoding="utf-8").close()

    try:
        nacht = datetime.datetime(2026, 9, 12, 3, 0)
        abend = datetime.datetime(2026, 9, 12, 19, 0)

        ja, grund = darf("Die Platte läuft voll.", jetzt=nacht, verlauf=probe)
        pruefe(not ja and "Ruhezeit" in grund,
               "nachts schweigt er: %s" % grund)

        ja, grund = darf("Die Platte ist voll.", dringend=True, jetzt=nacht,
                         verlauf=probe)
        pruefe(ja, "bei einer echten Störung spricht er auch nachts")

        ja, grund = darf("Nur so nebenbei.", jetzt=abend, verlauf=probe)
        pruefe(ja, "abends darf er: %s" % grund)

        vermerken("Nur so nebenbei.", jetzt=abend, verlauf=probe)
        ja, grund = darf("Und noch etwas.",
                         jetzt=abend + datetime.timedelta(minutes=10),
                         verlauf=probe)
        pruefe(not ja and "schon etwas gesagt" in grund,
               "kurz danach schweigt er: %s" % grund)

        ja, _ = darf("Und noch etwas.",
                     jetzt=abend + datetime.timedelta(minutes=90),
                     verlauf=probe)
        pruefe(ja, "nach einer Stunde wieder")

        ja, _ = darf("Dringend!", dringend=True,
                     jetzt=abend + datetime.timedelta(minutes=10),
                     verlauf=probe)
        pruefe(ja, "Dringendes hält der Abstand nicht auf")

        ja, grund = darf("", jetzt=abend, verlauf=probe)
        pruefe(not ja, "ohne Text keine Ansprache")

        pruefe(ist_ruhezeit(datetime.datetime(2026, 9, 12, 23, 30)),
               "23:30 ist Ruhezeit")
        pruefe(not ist_ruhezeit(datetime.datetime(2026, 9, 12, 12, 0)),
               "12:00 ist keine Ruhezeit")
    finally:
        if os.path.isfile(probe):
            open(probe, "w", encoding="utf-8").close()

    print("%d von %d bestanden" % (gesamt - fehler, gesamt))
    return 1 if fehler else 0


def main():
    p = argparse.ArgumentParser(description="Von sich aus sprechen.")
    p.add_argument("--pruefen", help="Darf dieser Text jetzt raus?")
    p.add_argument("--dringend", help="Text, der auch nachts raus darf")
    p.add_argument("--selbsttest", action="store_true")
    a = p.parse_args()

    if a.selbsttest:
        return selbsttest()

    text = a.dringend or a.pruefen
    if not text:
        p.print_help()
        return 1
    ja, grund = darf(text, dringend=bool(a.dringend))
    print("%s - %s" % ("ja" if ja else "nein", grund))
    return 0 if ja else 2


if __name__ == "__main__":
    sys.exit(main())
