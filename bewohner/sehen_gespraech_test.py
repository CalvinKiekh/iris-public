"""Wird auf eine Bildschirmfrage das WERKZEUG genommen - oder geraten?

Der Mangel, den der Mac am 12.09. um 16:46:15 gemessen hat:

    F: Was ist gerade auf dem Bildschirm zu sehen?
    A: Kein Bildschirminhalt.                        (nach 2,6 s)

Kein Werkzeug lief. Im Gespraech gab es gar keinen Weg zu einem: gespraech.py
importierte genau ein Werkzeug, stimme_hoeren, und nur fuer Aufnahmen. Der
Satz "Kein Bildschirminhalt." steht in keiner Datei des Projekts - das Modell
hat ihn erfunden, und er klang wie ein Messergebnis.

    python -X utf8 sehen_gespraech_test.py          nur die Logik
    python -X utf8 sehen_gespraech_test.py --echt   dazu ein echter Blick

Ohne --echt wird das Sehmodell NICHT belegt: `blick` ist einspritzbar.
"""
from __future__ import annotations

from einstellungen import NAMENS
import sys
from pathlib import Path

import pruefstand
pruefstand.werkzeuge_einbinden()

import gespraech

HIER = Path(__file__).resolve().parent
GESAMT = 0
FEHLER = 0


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def probe_erkennung() -> None:
    print("\nwelche Frage nach dem Bildschirm fragt")
    sieht = [
        "Was ist gerade auf dem Bildschirm zu sehen?",   # der echte Fall
        "Was ist auf dem Monitor?",
        "Was siehst du?",
        "Was siehst du gerade?",
        "Schau mal auf den Bildschirm",
        "Sieh auf meinen Monitor",
        "Beschreib mir den Bildschirm",
        "Welche Fenster sind auf dem Bildschirm offen?",
        "Wer ist auf dem Bildschirm zu sehen?",
    ]
    for f in sieht:
        pruefe(gespraech.BILDSCHIRMFRAGE.search(f)
               and not gespraech._NUR_GEFRAGT.search(f),
               "sieht nach: %r" % f)

    # Faehigkeitsfragen: Da geht es um das Koennen, nicht um den Inhalt - und
    # ein Blick kostet zehn Sekunden, ohne die Frage zu beantworten.
    nur_gefragt = [
        "Kannst du den Bildschirm sehen?",
        "Könntest du den Bildschirm beschreiben?",
        "Wie siehst du den Bildschirm?",
    ]
    for f in nur_gefragt:
        pruefe(gespraech.bildschirm_antwort(f, HIER / "werkstatt",
                                            blick=lambda: "SOLLTE NICHT")
               is None,
               "sieht NICHT nach, das fragt nach der Faehigkeit: %r" % f)

    # HIER STAND EINE PRUEFUNG, die wieder weg ist: "Kein Bildschirminhalt."
    # darf in keiner Quelldatei stehen - damit war belegt, dass das Modell den
    # Satz erfunden und nicht abgeschrieben hat. Sie hat sofort angeschlagen,
    # und zwar auf den Kommentar in gespraech.py, der den Vorfall beschreibt.
    #
    # Ein Pruefstein, der bricht, sobald man den Fehler dokumentiert, den er
    # bewacht, ist ein schlechter Pruefstein. Der Befund war eine einmalige
    # Diagnose (nachgesehen am 12.09.: der Satz stand in keiner Datei), kein
    # Zustand, der sich halten muss.

    # Und was gar nichts mit dem Bildschirm zu tun hat.
    for f in ("Wie spät ist es?", "Wer ist im Heimnetz?",
              "Wie viel Platz ist frei?", "Wie heißt meine Tochter?"):
        pruefe(not gespraech.BILDSCHIRMFRAGE.search(f),
               "kein Bildschirm: %r" % f)


def probe_werkzeug_wird_genommen() -> None:
    print("\ndas Werkzeug wird genommen, nicht das Modell")
    frage = "Was ist gerade auf dem Bildschirm zu sehen?"
    gerufen = []

    def falscher_blick() -> str:
        gerufen.append(True)
        return "Ein Editor mit Python-Code, daneben ein Browser."

    satz, gelungen = gespraech.bildschirm_antwort(
        frage, HIER / "werkstatt", blick=falscher_blick)
    pruefe(gerufen, "blick() wurde aufgerufen")
    pruefe(satz == "Ein Editor mit Python-Code, daneben ein Browser.",
           "und sein Satz geht ungeaendert in die Antwort: %r" % satz)
    pruefe(gelungen is True, "als gelungen gemeldet")

    # Der Fehlschlag darf nicht wie ein Inhalt klingen - und er darf im
    # Journal nicht als gelungen stehen.
    sys.path.insert(0, str(HIER / "werkstatt" / "werkzeuge"))
    import sehen
    s2, g2 = gespraech.bildschirm_antwort(
        frage, HIER / "werkstatt", blick=lambda: sehen.NICHT_AUFGENOMMEN)
    pruefe("nicht aufnehmen" in s2,
           "ein Fehlschlag wird als Fehlschlag gemeldet: %r" % s2)
    pruefe(g2 is False,
           "und NICHT als gelungen - sonst luegt die Werkzeugzeile")

    # Und der erfundene Satz des Modells darf nie wieder entstehen: Er kommt
    # nicht mehr vor, weil die Frage das Modell nicht mehr erreicht.
    def krachender_blick() -> str:
        raise RuntimeError("kaputt")

    s3, g3 = gespraech.bildschirm_antwort(frage, HIER / "werkstatt",
                                          blick=krachender_blick)
    pruefe("gescheitert" in s3,
           "auch ein Absturz wird benannt, nicht verschwiegen: %r" % s3)
    pruefe(g3 is False, "und ebenfalls nicht als gelungen")
    pruefe("Kein Bildschirminhalt" not in s3,
           "und nie mit dem erfundenen Satz von 16:46")


def probe_journalzeile() -> None:
    """Der Nachweis, den der Mac benutzt hat: die Werkzeugzeile im Journal."""
    print("\ndie Werkzeugzeile, an der man es nachlesen kann")
    zeilen = []
    a = gespraech.dienst_antwort(
        "Was ist gerade auf dem Bildschirm zu sehen?", HIER / "werkstatt",
        {"state": "wach"}, None,
        journal=lambda art, text, **k: zeilen.append((art, text, k)))
    # Ohne Einspritzung nimmt dienst_antwort das echte Werkzeug - das darf in
    # der Logikprobe nicht laufen. Deshalb nur pruefen, WENN etwas kam.
    if a is None:
        pruefe(True, "kein Blick moeglich - Werkzeug nicht erreichbar "
                     "(in dieser Umgebung in Ordnung)")
        return
    werkzeug = [z for z in zeilen if z[0] == "werkzeug"]
    pruefe(werkzeug, "eine Zeile der Art 'werkzeug' steht im Journal")
    if werkzeug:
        _, text, k = werkzeug[0]
        pruefe(k.get("werkzeug") == "sehen",
               "mit dem Namen: %s" % k.get("werkzeug"))
        pruefe("seconds" in k, "und mit der Dauer: %s s" % k.get("seconds"))
        # NICHT "gelungen ist True": In einer nicht-interaktiven Sitzung
        # schlaegt die Aufnahme zu Recht fehl. Gepruft wird, dass die Marke
        # zum Satz PASST - eine Zeile, die Erfolg meldet und einen
        # Fehlschlag enthaelt, waere genau der Fehler dieses Mangels.
        sys.path.insert(0, str(HIER / "werkstatt" / "werkzeuge"))
        import sehen
        gescheitert = sehen.NICHT_AUFGENOMMEN in a or "gescheitert" in a
        pruefe(k.get("gelungen") is not gescheitert,
               "und die Marke passt zum Satz (gelungen=%s, Fehlschlag=%s)"
               % (k.get("gelungen"), gescheitert))
        print("      Satz war: %s" % a[:90])


def probe_leeres_bild() -> None:
    """Die Aufnahme selbst: erkennt sie ein leeres Bild?"""
    print("\nein leeres Bild ist keine Aufnahme")
    sys.path.insert(0, str(HIER / "werkstatt" / "werkzeuge"))
    try:
        import sehen
    except Exception as f:
        pruefe(False, "sehen.py nicht ladbar: %s" % f)
        return

    schwarz = [bytes(3 * 64) for _ in range(64)]
    verschiedene, dunkel, hell = sehen._farbspanne(schwarz)
    pruefe(verschiedene == 1 and dunkel == 0 and hell == 0,
           "ein schwarzes Bild hat eine Farbe (%d)" % verschiedene)
    pruefe(verschiedene < sehen.FARBEN_MINDESTENS,
           "und faellt damit unter die Grenze - Aufnahme gilt als gescheitert")

    bunt = [bytes((x * 7 + y * 3) % 256 for x in range(192))
            for y in range(64)]
    v2, _, _ = sehen._farbspanne(bunt)
    pruefe(v2 >= sehen.FARBEN_MINDESTENS,
           "ein Bild mit Inhalt kommt durch (%d Farben)" % v2)


def echt() -> None:
    print("\n" + "=" * 66)
    print("Ein echter Blick - das kostet rund zehn Sekunden")
    print("=" * 66)
    import time
    sys.path.insert(0, str(HIER / "werkstatt" / "werkzeuge"))
    import sehen
    t0 = time.time()
    satz = sehen.blick()
    dauer = time.time() - t0
    print("  %.1f s: %s" % (dauer, satz))
    pruefe(len(satz) > 15, "es kam ein Satz")
    pruefe("Kein Bildschirminhalt" not in satz,
           "und nicht der erfundene Satz von 16:46")
    if "nicht aufnehmen" in satz:
        print("      HINWEIS: Die Aufnahme kam leer zurueck. In DIESER "
              "Umgebung\n"
              "      (nicht-interaktive Sitzung) ist das zu erwarten - der "
              "Bewohner\n"
              f"      laeuft in {NAMENS} Sitzung und hat um 11:12 echten "
              "Inhalt gesehen.")


if __name__ == "__main__":
    print("Probe Bildschirmfrage im Gespraech")
    probe_erkennung()
    probe_werkzeug_wird_genommen()
    probe_journalzeile()
    probe_leeres_bild()
    if "--echt" in sys.argv:
        echt()
    print("\n%d von %d bestanden" % (GESAMT - FEHLER, GESAMT))
    raise SystemExit(1 if FEHLER else 0)
