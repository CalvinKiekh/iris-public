"""Probe fuer zeitwort.py - jeder Pruefstein aus Anhang 2.

    python -X utf8 zeitwort_test.py

ALLES GEGEN EIN FESTES JETZT: Samstag, 12.09.2026, 14:00. Eine Probe, die
`time.time()` benutzt, misst die Uhr mit und fehlt irgendwann nachts um halb
drei, ohne dass jemand weiss warum - und hier waere das besonders teuer, weil
ein falsches Datum Calvin nachts weckt.
"""
from __future__ import annotations

from einstellungen import NAMENS
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import zeitwort

GESAMT = 0
FEHLER = 0

# Samstag, 12.09.2026, 14:00 - dasselbe Jetzt wie in Anhang 2.
JETZT = datetime(2026, 9, 12, 14, 0)


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def d(text: str) -> str:
    """Was aufloesen() liefert, kurz und vergleichbar."""
    wann, grund = zeitwort.aufloesen(text, JETZT)
    if wann is None:
        return f"(None, {grund!r})"
    return wann.strftime("%d.%m. %H:%M")


def gleich(eingabe: str, erwartet: str, warum: str = "") -> None:
    hat = d(eingabe)
    pruefe(hat == erwartet,
           "%-26r -> %-18s %s" % (eingabe, hat,
                                  "" if hat == erwartet
                                  else "ERWARTET " + erwartet)
           + (f"   ({warum})" if warum and hat == erwartet else ""))


def probe_anhang2() -> None:
    print("\nAnhang 2, Zeile fuer Zeile - Samstag 12.09.2026, 14:00")
    gleich("morgen", "13.09. 09:00", "Standardstunde")
    gleich("morgen um 9", "13.09. 09:00", "Uhrzeit schlaegt Standard")
    gleich("morgen früh", "13.09. 08:00", "Tageszeitwort")
    gleich("heute Abend", "12.09. 19:00")
    gleich("übermorgen", "14.09. 09:00")
    gleich("Dienstag", "15.09. 09:00", "der naechste, nicht der vergangene")
    gleich("Samstag", "19.09. 09:00", "heute ist Samstag -> der naechste")
    gleich("nächste Woche", "14.09. 09:00", "Woche = ihr Anfang, Montag")
    gleich("in drei Tagen", "15.09. 14:00", "behaelt die Uhrzeit")
    gleich("in einer Stunde", "12.09. 15:00")
    gleich("am 14.", "14.09. 09:00", "Monat ergaenzt")
    gleich("am 14.9.", "14.09. 09:00")
    gleich("am 14. September", "14.09. 09:00")
    gleich("am 3.", "(None, 'unklar')", "Monat offen -> Rueckfrage")
    gleich("gestern", "(None, 'kein_termin')", "keine Rueckfrage")
    gleich("vorgestern", "(None, 'kein_termin')")
    gleich("bald", "(None, 'unklar')")
    gleich("demnächst", "(None, 'unklar')")
    gleich("irgendwann", "(None, 'unklar')")
    gleich("Guten Morgen", "(None, 'nichts')", "ein Gruss ist kein Zeitwort")
    gleich("nächsten Dienstag", "15.09. 09:00", "wie 'Dienstag'")
    gleich("Mo", "14.09. 09:00", "die Spracherkennung kuerzt")
    gleich("Di", "15.09. 09:00")

    print("\nund was KEINE Uhrzeit ist und es nicht werden darf")
    for satz in ("Er hat 14 Tage Urlaub", "Das dauert 3 Stunden"):
        pruefe(zeitwort.findet(satz) is False,
               "findet(%r) == False" % satz)
        wann, grund = zeitwort.aufloesen(satz, JETZT)
        pruefe(wann is None and grund == "nichts",
               "  und aufloesen() gibt (None, 'nichts'): (%s, %r)"
               % (wann, grund))

    print("\nfindet() - woran D.2 vergessene Termine vermutet")
    for satz in ("morgen", "am 14.", "in drei Tagen", "heute Abend",
                 "nächste Woche", "Dienstag", "bald", "gestern", "um 18 Uhr"):
        pruefe(zeitwort.findet(satz) is True, "findet(%r)" % satz)
    for satz in ("Guten Morgen", "Er hat 14 Tage Urlaub",
                 "Das dauert 3 Stunden", "Wie geht es dir?",
                 "Wer belegt den meisten Speicher?", ""):
        pruefe(zeitwort.findet(satz) is False, "NICHT findet(%r)" % satz)


def probe_im_satz() -> None:
    print("\nIm ganzen Satz, nicht nur als einzelnes Wort")
    gleich("morgen mit Lena zum Kinderarzt", "13.09. 09:00",
           f"{NAMENS} Pruefstein aus dem Plan")
    gleich("Ich muss morgen früh um zehn beim Arzt sein", "13.09. 10:00",
           "die Uhrzeit schlaegt das Tageszeitwort")
    gleich("Erinnere mich am 14. September um 8:30", "14.09. 08:30")
    gleich("Wir treffen uns nächsten Dienstag um 19 Uhr", "15.09. 19:00")
    gleich("In drei Tagen ist der Termin", "15.09. 14:00")
    gleich("Kannst du mich in 20 Minuten erinnern", "12.09. 14:20")


def probe_fallen() -> None:
    print("\nDie Fallen, die ausdruecklich festgelegt sind")

    # Der Bezugspunkt ist die AEUSSERUNG. Um 23:50 gesagt, um 00:05
    # ausgewertet: "morgen" ist der 13., nicht der 14.
    spaet = datetime(2026, 9, 12, 23, 50)
    wann, _ = zeitwort.aufloesen("morgen", spaet)
    pruefe(wann is not None and wann.day == 13,
           "um 23:50 gesagt: 'morgen' ist der 13., nicht der 14.: %s"
           % (wann and wann.strftime("%d.%m. %H:%M")))
    # Und dasselbe Wort, fuenfzehn Minuten spaeter GESAGT, ist der 14.
    nach_mitternacht = datetime(2026, 9, 13, 0, 5)
    wann, _ = zeitwort.aufloesen("morgen", nach_mitternacht)
    pruefe(wann is not None and wann.day == 14,
           "um 00:05 gesagt: 'morgen' ist der 14.: %s"
           % (wann and wann.strftime("%d.%m. %H:%M")))

    # bezug ist Pflicht - ein datetime.now() als Standard waere der Fehler,
    # den C.2 ausschliesst.
    fehlt = False
    try:
        zeitwort.aufloesen("morgen")      # type: ignore[call-arg]
    except TypeError:
        fehlt = True
    pruefe(fehlt, "aufloesen() ohne bezug ist ein Fehler, keine Annahme")

    # Jeder Wochentag, an jedem Wochentag: nie heute, immer 1 bis 7 Tage vor.
    alle_gut = True
    for tag in range(7):
        b = datetime(2026, 9, 7 + tag, 14, 0)       # 07.09. ist ein Montag
        for name in ("montag", "dienstag", "mittwoch", "donnerstag",
                     "freitag", "samstag", "sonntag"):
            wann, grund = zeitwort.aufloesen(name, b)
            if wann is None or not (1 <= (wann.date() - b.date()).days <= 7):
                alle_gut = False
                print(f"      {name} am {b:%a %d.%m} -> {wann}")
    pruefe(alle_gut,
           "49 Paare aus Wochentag und Bezugstag: immer 1 bis 7 Tage vor")

    # Ein Datum ohne Jahr in der Vergangenheit: naechstes Jahr, nicht geraten.
    wann, grund = zeitwort.aufloesen("am 3. Januar", JETZT)
    pruefe(wann is not None and wann.year == 2027 and wann.month == 1,
           "'am 3. Januar' im September -> Januar 2027: %s"
           % (wann and wann.strftime("%d.%m.%Y")))

    # Ein Datum, das es nicht gibt, ist nicht "unklar" - es ist falsch gehoert.
    wann, grund = zeitwort.aufloesen("am 31.2.", JETZT)
    pruefe(wann is None and grund == "unklar",
           "'am 31.2.' gibt es nicht -> Rueckfrage: (%s, %r)" % (wann, grund))

    # Monate sind ungleich lang - "in zwei Monaten" wird nicht geraten.
    wann, grund = zeitwort.aufloesen("in zwei Monaten", JETZT)
    pruefe(wann is None and grund == "unklar",
           "'in zwei Monaten' wird nicht auf 60 Tage geraten: (%s, %r)"
           % (wann, grund))

    # Nur eine Uhrzeit: heute, wenn sie noch kommt - sonst morgen.
    gleich("um 18 Uhr", "12.09. 18:00", "kommt heute noch")
    gleich("um 9 Uhr", "13.09. 09:00", "9 Uhr ist vorbei -> morgen")
    gleich("abends", "12.09. 19:00")
    gleich("morgens", "13.09. 08:00", "8 Uhr ist vorbei -> morgen")


def probe_zahlwort() -> None:
    print("\nZahlwoerter - eine Liste, nicht zwei")
    for wort, zahl in (("drei", 3), ("zwölf", 12), ("zwoelf", 12),
                       ("einundzwanzig", 21), ("vierundsechzig", 64),
                       ("7", 7), ("hundert", 100)):
        pruefe(zeitwort.zahl_aus(wort) == zahl,
               "zahl_aus(%r) == %d: %s" % (wort, zahl,
                                           zeitwort.zahl_aus(wort)))
    pruefe(zeitwort.zahl_aus("morgen") is None, "zahl_aus('morgen') is None")

    # bestand.py benutzt dieselbe Liste. Stand sie zweimal da, liefen die
    # beiden auseinander.
    import bestand
    pruefe(bestand.zahlen_ausgeschrieben is zeitwort.zahlen_ausgeschrieben
           or 23 in bestand.zahlen_ausgeschrieben("dreiundzwanzig Dateien"),
           "bestand.py findet 'dreiundzwanzig' weiterhin")
    pruefe(bestand.ZAHLWORT is zeitwort.ZAHLWORT,
           "und es ist DIESELBE Liste, keine Kopie")


def main() -> int:
    probe_anhang2()
    probe_im_satz()
    probe_fallen()
    probe_zahlwort()
    print("\n%d Proben, %d Fehler" % (GESAMT, FEHLER))
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
