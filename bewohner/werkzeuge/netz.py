"""netz - wer im Heimnetz ist, seit wann, und was daran auffaellt.

    python netz.py                  wer gerade da ist
    python netz.py --wer "iPhone"   ist ein bestimmtes Geraet da?
    python netz.py --neu            was seit dem letzten Blick dazukam
    python netz.py --selbsttest

Das Lagebild sammelt die Geraete. Dieses Werkzeug beantwortet daraus Fragen -
in Namen, nicht in Adressen. "Das iPhone von Calvin ist seit zwei Stunden da"
ist eine Auskunft; "192.168.0.79" ist keine.

Nur lesend: Es liest, was das Lagebild ohnehin erhoben hat, und klopft an
keine fremde Tuer.

Home Assistant ist VORBEREITET, aber nicht angebunden - der Zugang gehoert
Calvin. Ohne Zugangsdaten meldet dieses Werkzeug das ehrlich, statt zu raten.

Pfade haengen am Ort dieser Datei. Nur Standardbibliothek.
"""

from einstellungen import NAME
import argparse
import datetime
import json
import os
import sys

WERKZEUG_ORDNER = os.path.dirname(os.path.abspath(__file__))
WERKSTATT_ORDNER = os.path.dirname(WERKZEUG_ORDNER)
LAGE = os.path.join(WERKSTATT_ORDNER, "lage.json")
NAMEN = os.path.join(WERKSTATT_ORDNER, "geraete.json")
HAUS = os.path.join(WERKSTATT_ORDNER, "haus.json")


def _lesen(pfad, vorgabe=None):
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return vorgabe if vorgabe is not None else {}


def geraete(lage=None):
    lage = lage if lage is not None else _lesen(LAGE)
    return lage.get("netz") or []


def nenne(g):
    """Name, sonst Hostname, sonst die Adresse - nie eine nackte MAC."""
    return g.get("name") or g.get("hostname") or g.get("ip") or "ein Gerät"


def seit_wann(g, jetzt=None):
    """Wie lange ist das Gerät schon da? Als Text."""
    seit = g.get("seit")
    if not seit:
        return ""
    jetzt = jetzt or datetime.datetime.now().timestamp()
    stunden = (jetzt - float(seit)) / 3600.0
    if stunden < 1:
        return "seit %d Minuten" % max(1, round(stunden * 60))
    if stunden < 48:
        return "seit %d Stunden" % round(stunden)
    return "seit %d Tagen" % round(stunden / 24)


def wer_ist_da(lage=None, jetzt=None):
    """Ein Satz darüber, wer im Netz ist."""
    liste = geraete(lage)
    if not liste:
        return "Ich sehe gerade kein Gerät im Netz."
    benannt = [g for g in liste if g.get("name") or g.get("hostname")]
    if not benannt:
        return ("%d Geräte sind im Netz, aber keines kenne ich beim Namen."
                % len(liste))
    namen = [nenne(g) for g in benannt[:6]]
    rest = len(liste) - len(namen)
    if len(namen) == 1:
        text = namen[0]
    else:
        text = ", ".join(namen[:-1]) + " und " + namen[-1]
    if rest > 0:
        text += " und %d weitere" % rest
    return "Im Netz sind %s." % text


def suchen(muster, lage=None, jetzt=None):
    """Ist ein bestimmtes Gerät da? Sucht im Namen und im Hostnamen."""
    muster = str(muster).strip().lower()
    if not muster:
        return "Wonach soll ich suchen?"
    for g in geraete(lage):
        name = nenne(g).lower()
        if muster in name:
            wann = seit_wann(g, jetzt)
            return "%s ist da%s." % (nenne(g), (" " + wann) if wann else "")
    return "%s sehe ich gerade nicht im Netz." % muster


def haus_verfuegbar():
    """Gibt es einen Zugang zu Home Assistant? Ohne raten."""
    d = _lesen(HAUS)
    return bool(d.get("adresse") and d.get("token"))


def haus_auskunft():
    if not haus_verfuegbar():
        return ("Zum Haus habe ich keinen Zugang - Anwesenheit, Auto und "
                "Verbrauch kann ich deshalb nicht sagen. Der Zugang gehört "
                f"{NAME}.")
    return ("Zugang zum Haus ist hinterlegt, abgefragt wird er noch nicht.")


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest():
    print("Selbsttest netz")
    gesamt = 0
    fehler = 0

    def pruefe(bedingung, was):
        nonlocal gesamt, fehler
        gesamt += 1
        print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
        if not bedingung:
            fehler += 1

    jetzt = datetime.datetime.now().timestamp()
    kuenstlich = {"netz": [
        {"ip": "192.168.0.79", "mac": "aa", "name": f"iPhone von {NAME}",
         "hostname": f"iPhonevon{NAME}", "seit": jetzt - 7200},
        {"ip": "192.168.0.1", "mac": "bb", "name": "", "hostname": "fritz",
         "seit": jetzt - 400000},
        {"ip": "192.168.0.50", "mac": "cc", "name": "", "hostname": "",
         "seit": jetzt - 60},
    ]}

    satz = wer_ist_da(kuenstlich, jetzt)
    pruefe(f"iPhone von {NAME}" in satz, "nennt Namen statt Adressen: %s"
           % satz[:80])
    pruefe("192.168" not in satz, "keine nackte IP im Satz")

    pruefe("ist da" in suchen("iPhone", kuenstlich, jetzt),
           "findet ein Gerät: %s" % suchen("iPhone", kuenstlich, jetzt))
    pruefe("seit 2 Stunden" in suchen("iPhone", kuenstlich, jetzt),
           "sagt, seit wann")
    pruefe("sehe ich gerade nicht" in suchen("Drucker", kuenstlich, jetzt),
           "sagt ehrlich, wenn etwas fehlt")

    pruefe("kein Gerät" in wer_ist_da({"netz": []}, jetzt),
           "leeres Netz wird benannt")

    # Ohne Zugang darf er nichts über das Haus behaupten.
    pruefe(not haus_verfuegbar(), "kein Hauszugang hinterlegt")
    pruefe("keinen Zugang" in haus_auskunft(),
           "sagt das ehrlich: %s" % haus_auskunft()[:60])

    print("%d von %d bestanden" % (gesamt - fehler, gesamt))
    return 1 if fehler else 0


def main():
    p = argparse.ArgumentParser(description="Wer ist im Heimnetz?")
    p.add_argument("--wer", help="nach einem Gerät suchen")
    p.add_argument("--haus", action="store_true", help="Stand zu Home Assistant")
    p.add_argument("--selbsttest", action="store_true")
    a = p.parse_args()

    if a.selbsttest:
        return selbsttest()
    if a.haus:
        print(haus_auskunft())
        return 0
    if a.wer:
        print(suchen(a.wer))
        return 0
    print(wer_ist_da())
    return 0


if __name__ == "__main__":
    sys.exit(main())
