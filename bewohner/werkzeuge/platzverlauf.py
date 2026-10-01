"""platzverlauf - haelt den freien Platz auf C fest und meldet den Trend.

    python platzverlauf.py               Messwert anhaengen, Trend ausgeben
    python platzverlauf.py --selbsttest  prueft sich selbst, 0 bei Erfolg

Die Pfade haengen am Ort dieser Datei, nicht am Arbeitsverzeichnis: das
Werkzeug liegt in werkstatt/werkzeuge/, geschrieben wird nach
werkstatt/platzverlauf.jsonl - egal, von wo aus es aufgerufen wird.

Nur Standardbibliothek, kein Netz, keine fremden Programme.
"""

import argparse
import datetime
import json
import os
import shutil
import sys
import tempfile

# Ort der Datei als Anker - sonst schriebe ein Aufruf aus einem fremden
# Arbeitsverzeichnis heraus ausserhalb der Werkstatt.
WERKZEUG_ORDNER = os.path.dirname(os.path.abspath(__file__))
WERKSTATT_ORDNER = os.path.dirname(WERKZEUG_ORDNER)
VERLAUFSDATEI = os.path.join(WERKSTATT_ORDNER, "platzverlauf.jsonl")

# Laufwerk, dessen freier Platz beobachtet wird.
BEOBACHTETES_LAUFWERK = "C:\\"

# Wie viele Eintraege am Ende der Datei den Trend bilden.
STANDARD_FENSTER = 5

# Unterhalb dieser Veraenderung (in Gigabyte) gilt der Platz als gleichbleibend.
GLEICHHEITS_SCHWELLE_GB = 0.5

BYTE_JE_GIGABYTE = 1024 ** 3


def liegt_in_werkstatt(pfad):
    """Prueft, ob ein Pfad innerhalb der Werkstatt liegt - Schutz vor Ausreissern."""
    ziel = os.path.abspath(pfad)
    wurzel = os.path.abspath(WERKSTATT_ORDNER)
    try:
        return os.path.commonpath([ziel, wurzel]) == wurzel
    except ValueError:
        # Verschiedene Laufwerke lassen sich gar nicht erst vergleichen.
        return False


def freie_gigabyte(laufwerk=BEOBACHTETES_LAUFWERK):
    """Liefert den freien Platz des Laufwerks in Gigabyte, auf drei Stellen gerundet."""
    belegung = shutil.disk_usage(laufwerk)
    return round(belegung.free / BYTE_JE_GIGABYTE, 3)


def jetzt_als_zeitstempel():
    """Ortszeit als ISO-Zeitstempel auf Sekunden genau."""
    return datetime.datetime.now().isoformat(timespec="seconds")


def eintrag_anhaengen(gigabyte, zeitstempel=None, verlaufsdatei=VERLAUFSDATEI):
    """Haengt eine Messung als JSON-Zeile an die Verlaufsdatei an und gibt sie zurueck."""
    if not liegt_in_werkstatt(verlaufsdatei):
        raise ValueError("Die Verlaufsdatei muss innerhalb der Werkstatt liegen: %s" % verlaufsdatei)

    eintrag = {
        "zeit": zeitstempel or jetzt_als_zeitstempel(),
        "frei_gb": gigabyte,
    }
    ordner = os.path.dirname(verlaufsdatei)
    if ordner and not os.path.isdir(ordner):
        os.makedirs(ordner)
    with open(verlaufsdatei, "a", encoding="utf-8") as datei:
        datei.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
    return eintrag


def eintraege_lesen(verlaufsdatei=VERLAUFSDATEI, anzahl=None):
    """Liest die Verlaufsdatei; kaputte oder fremde Zeilen werden still uebergangen.

    Mit anzahl werden nur die letzten n brauchbaren Eintraege geliefert.
    """
    if not os.path.isfile(verlaufsdatei):
        return []

    eintraege = []
    with open(verlaufsdatei, "r", encoding="utf-8") as datei:
        for zeile in datei:
            zeile = zeile.strip()
            if not zeile:
                continue
            try:
                eintrag = json.loads(zeile)
            except ValueError:
                continue
            if not isinstance(eintrag, dict):
                continue
            if "frei_gb" not in eintrag:
                continue
            wert = eintrag["frei_gb"]
            if isinstance(wert, bool) or not isinstance(wert, (int, float)):
                continue
            if "zeit" not in eintrag:
                # Altbestand einer frueheren Fassung: Unix-Zeit im Feld "ts".
                roh = eintrag.get("ts")
                if isinstance(roh, bool) or not isinstance(roh, (int, float)):
                    continue
                eintrag = dict(eintrag)
                eintrag["zeit"] = datetime.datetime.fromtimestamp(roh).isoformat(timespec="seconds")
            eintraege.append(eintrag)

    if anzahl is not None and anzahl > 0:
        return eintraege[-anzahl:]
    return eintraege


def trend_bestimmen(eintraege, schwelle_gb=GLEICHHEITS_SCHWELLE_GB):
    """Vergleicht den aeltesten mit dem juengsten Eintrag des Fensters.

    Liefert ein Paar aus Befund ("faellt", "steigt", "gleich", "unbekannt")
    und der Veraenderung in Gigabyte.
    """
    if len(eintraege) < 2:
        return "unbekannt", 0.0

    veraenderung = round(eintraege[-1]["frei_gb"] - eintraege[0]["frei_gb"], 3)
    if veraenderung <= -schwelle_gb:
        return "faellt", veraenderung
    if veraenderung >= schwelle_gb:
        return "steigt", veraenderung
    return "gleich", veraenderung


def bericht_bauen(eintraege, befund, veraenderung):
    """Baut den Text, der beim Aufruf ohne Argumente ausgegeben wird."""
    if not eintraege:
        return "Noch keine Eintraege im Verlauf."

    juengster = eintraege[-1]
    zeilen = ["Frei auf %s: %.2f GB (%s)" % (
        BEOBACHTETES_LAUFWERK, juengster["frei_gb"], juengster["zeit"])]

    if befund == "unbekannt":
        zeilen.append("Trend: noch unbekannt - dafuer braucht es mindestens zwei Eintraege.")
    else:
        wortlaut = {
            "faellt": "Der Platz faellt",
            "steigt": "Der Platz steigt",
            "gleich": "Der Platz bleibt gleich",
        }[befund]
        zeilen.append("Trend ueber %d Eintraege (%s bis %s): %s (%+.2f GB)" % (
            len(eintraege),
            eintraege[0]["zeit"],
            juengster["zeit"],
            wortlaut,
            veraenderung,
        ))

    zeilen.append("Letzte Messungen:")
    for eintrag in eintraege:
        zeilen.append("  %s  %8.2f GB" % (eintrag["zeit"], eintrag["frei_gb"]))
    return "\n".join(zeilen)


def messen_und_berichten(fenster=STANDARD_FENSTER, verlaufsdatei=VERLAUFSDATEI, messen=True):
    """Normalbetrieb: messen, anhaengen, Trend der letzten Eintraege ausgeben."""
    if messen:
        eintrag_anhaengen(freie_gigabyte(), verlaufsdatei=verlaufsdatei)
    eintraege = eintraege_lesen(verlaufsdatei, anzahl=fenster)
    befund, veraenderung = trend_bestimmen(eintraege)
    return bericht_bauen(eintraege, befund, veraenderung)


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

class Pruefprotokoll:
    """Kleiner Pruefhelfer, damit der Selbsttest ohne Fremdbibliothek auskommt."""

    def __init__(self):
        self.gesamt = 0
        self.fehlschlaege = []

    def pruefe(self, bedingung, beschreibung):
        self.gesamt += 1
        if bedingung:
            print("  ok   %s" % beschreibung)
        else:
            print("  FEHL %s" % beschreibung)
            self.fehlschlaege.append(beschreibung)


def selbsttest():
    """Prueft die eigentliche Arbeit: messen, schreiben, lesen, Trend erkennen.

    Arbeitet in einem Wegwerf-Ordner *innerhalb* der Werkstatt, damit die Regel
    "schreibt nichts ausserhalb der Werkstatt" auch waehrend des Tests gilt -
    und zwar unabhaengig vom Arbeitsverzeichnis des Aufrufers.
    """
    protokoll = Pruefprotokoll()
    print("Selbsttest platzverlauf")

    # 1. Die Messung liefert eine brauchbare Zahl.
    gemessen = freie_gigabyte()
    protokoll.pruefe(isinstance(gemessen, float), "Messung liefert eine Kommazahl")
    protokoll.pruefe(gemessen > 0, "Messung ist groesser als null (%.2f GB)" % gemessen)

    # 2. Der Pfadschutz greift in beide Richtungen.
    protokoll.pruefe(liegt_in_werkstatt(VERLAUFSDATEI), "Verlaufsdatei liegt in der Werkstatt")
    protokoll.pruefe(not liegt_in_werkstatt(os.path.join(WERKSTATT_ORDNER, "..", "ausserhalb.jsonl")),
                     "Pfad ausserhalb der Werkstatt wird abgelehnt")

    testordner = tempfile.mkdtemp(prefix="platzverlauf-test-", dir=WERKSTATT_ORDNER)
    try:
        testdatei = os.path.join(testordner, "verlauf.jsonl")

        # 3. Ein leerer Verlauf stuerzt nicht ab.
        protokoll.pruefe(eintraege_lesen(testdatei) == [], "Leerer Verlauf liefert leere Liste")
        protokoll.pruefe(trend_bestimmen([]) == ("unbekannt", 0.0), "Ohne Eintraege ist der Trend unbekannt")

        # 4. Schreiben und Lesen passen zusammen.
        eintrag_anhaengen(100.0, zeitstempel="2026-01-01T10:00:00", verlaufsdatei=testdatei)
        eintrag_anhaengen(97.5, zeitstempel="2026-01-01T11:00:00", verlaufsdatei=testdatei)
        gelesen = eintraege_lesen(testdatei)
        protokoll.pruefe(len(gelesen) == 2, "Zwei geschriebene Eintraege werden gelesen")
        protokoll.pruefe(gelesen[0]["frei_gb"] == 100.0 and gelesen[1]["zeit"] == "2026-01-01T11:00:00",
                         "Inhalt der Eintraege bleibt erhalten")

        # 5. Kaputte Zeilen werden uebergangen, gute bleiben.
        with open(testdatei, "a", encoding="utf-8") as datei:
            datei.write("das ist kein json\n")
            datei.write("\n")
            datei.write('{"zeit": "2026-01-01T11:30:00"}\n')  # frei_gb fehlt
        protokoll.pruefe(len(eintraege_lesen(testdatei)) == 2, "Kaputte Zeilen werden uebergangen")

        # 5b. Altbestand mit Unix-Zeit ("ts") wird uebernommen, nicht verworfen.
        altdatei = os.path.join(testordner, "alt.jsonl")
        with open(altdatei, "a", encoding="utf-8") as datei:
            datei.write('{"ts": 1789164872.0, "frei_gb": 1540}\n')
        alt = eintraege_lesen(altdatei)
        protokoll.pruefe(len(alt) == 1 and alt[0]["frei_gb"] == 1540,
                         "Altbestand im ts-Format wird gelesen")
        protokoll.pruefe(bool(alt) and alt[0]["zeit"].startswith("2026-"),
                         "Unix-Zeit wird in einen Zeitstempel uebersetzt")

        # 6. Fallender Platz.
        eintrag_anhaengen(94.0, zeitstempel="2026-01-01T12:00:00", verlaufsdatei=testdatei)
        befund, veraenderung = trend_bestimmen(eintraege_lesen(testdatei))
        protokoll.pruefe(befund == "faellt", "Fallender Platz wird als 'faellt' erkannt")
        protokoll.pruefe(veraenderung == -6.0, "Veraenderung wird richtig berechnet (%.2f)" % veraenderung)

        # 7. Steigender Platz.
        steigend = [
            {"zeit": "2026-01-02T10:00:00", "frei_gb": 50.0},
            {"zeit": "2026-01-02T11:00:00", "frei_gb": 58.25},
        ]
        protokoll.pruefe(trend_bestimmen(steigend)[0] == "steigt", "Steigender Platz wird als 'steigt' erkannt")

        # 8. Kleine Schwankung unter der Schwelle gilt als gleichbleibend.
        gleichbleibend = [
            {"zeit": "2026-01-03T10:00:00", "frei_gb": 50.0},
            {"zeit": "2026-01-03T11:00:00", "frei_gb": 50.2},
            {"zeit": "2026-01-03T12:00:00", "frei_gb": 49.9},
        ]
        protokoll.pruefe(trend_bestimmen(gleichbleibend)[0] == "gleich", "Kleine Schwankung gilt als 'gleich'")

        # 9. Ein einzelner Eintrag ergibt keinen Trend.
        protokoll.pruefe(trend_bestimmen([{"zeit": "x", "frei_gb": 1.0}])[0] == "unbekannt",
                         "Ein einzelner Eintrag ergibt keinen Trend")

        # 10. Das Fenster begrenzt wirklich auf die letzten Eintraege.
        letzte_zwei = eintraege_lesen(testdatei, anzahl=2)
        protokoll.pruefe(len(letzte_zwei) == 2 and letzte_zwei[-1]["frei_gb"] == 94.0,
                         "Fenster liefert die letzten Eintraege")

        # 11. Schreiben ausserhalb der Werkstatt wird verweigert.
        verbotener_pfad = os.path.join(WERKSTATT_ORDNER, "..", "verboten.jsonl")
        try:
            eintrag_anhaengen(1.0, verlaufsdatei=verbotener_pfad)
            verweigert = False
        except ValueError:
            verweigert = True
        protokoll.pruefe(verweigert, "Schreiben ausserhalb der Werkstatt wird verweigert")
        protokoll.pruefe(not os.path.exists(os.path.abspath(verbotener_pfad)),
                         "Es entstand keine Datei ausserhalb der Werkstatt")

        # 12. Der ganze Ablauf laeuft durch und liefert einen lesbaren Bericht.
        bericht = messen_und_berichten(fenster=3, verlaufsdatei=testdatei)
        protokoll.pruefe("Frei auf" in bericht and "Trend" in bericht,
                         "Bericht enthaelt Messwert und Trend")
        protokoll.pruefe(len(eintraege_lesen(testdatei)) == 4,
                         "Normalbetrieb haengt genau einen Eintrag an")

        # 13. Nur-Lesen misst nicht und schreibt nichts.
        messen_und_berichten(fenster=3, verlaufsdatei=testdatei, messen=False)
        protokoll.pruefe(len(eintraege_lesen(testdatei)) == 4, "Nur-Lesen haengt nichts an")

    finally:
        shutil.rmtree(testordner, ignore_errors=True)

    # 14. Der Test raeumt hinter sich auf und laesst nichts liegen.
    protokoll.pruefe(not os.path.isdir(testordner), "Testordner wurde wieder aufgeraeumt")

    if protokoll.fehlschlaege:
        print("Selbsttest fehlgeschlagen: %d von %d Pruefungen" % (
            len(protokoll.fehlschlaege), protokoll.gesamt))
        return 1

    print("Selbsttest bestanden: %d Pruefungen." % protokoll.gesamt)
    return 0


def hauptprogramm(argumente=None):
    zerleger = argparse.ArgumentParser(
        prog="platzverlauf",
        description="Haelt den freien Platz auf %s fest und meldet den Trend." % BEOBACHTETES_LAUFWERK,
    )
    zerleger.add_argument("--selbsttest", action="store_true",
                          help="prueft das Werkzeug und gibt 0 zurueck, wenn alles stimmt")
    zerleger.add_argument("--fenster", type=int, default=STANDARD_FENSTER,
                          help="wie viele der letzten Eintraege den Trend bilden (Standard: %d)" % STANDARD_FENSTER)
    zerleger.add_argument("--nur-lesen", action="store_true",
                          help="nichts messen, nur den vorhandenen Verlauf auswerten")
    gewaehlt = zerleger.parse_args(argumente)

    if gewaehlt.selbsttest:
        return selbsttest()

    if gewaehlt.fenster < 2:
        print("Das Fenster braucht mindestens zwei Eintraege.", file=sys.stderr)
        return 2

    print(messen_und_berichten(fenster=gewaehlt.fenster, messen=not gewaehlt.nur_lesen))
    return 0


if __name__ == "__main__":
    sys.exit(hauptprogramm())
