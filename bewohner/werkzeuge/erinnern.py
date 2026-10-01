"""erinnern - Calvin zur rechten Zeit an etwas erinnern.

    python erinnern.py --merken "Text" --wann "2026-09-12 18:30"
    python erinnern.py --merken "Text" --in 90        (in 90 Minuten)
    python erinnern.py --faellig                     was jetzt dran ist
    python erinnern.py --liste                       was ansteht
    python erinnern.py --selbsttest

Sein Gedaechtnis haelt fest, was WAR. Dieses Werkzeug haelt fest, was SEIN
SOLL - und meldet es, wenn es soweit ist. Ohne das kann er sich alles merken
und trotzdem nie von selbst daran denken.

Faellige Erinnerungen erscheinen als Zeile `erinnerung` im Journal; die
Bruecke schickt sie als Push an Calvin.

Pfade haengen am Ort dieser Datei. Nur Standardbibliothek, kein Netz.
"""

import argparse
import datetime
import json
import os
import sys

WERKZEUG_ORDNER = os.path.dirname(os.path.abspath(__file__))
WERKSTATT_ORDNER = os.path.dirname(WERKZEUG_ORDNER)
# Der Bau liegt eine Ebene ueber der Werkstatt. Gebraucht wird von dort nur
# `probenort` - der Riegel in schreiben(). Ist er nicht erreichbar, laeuft das
# Werkzeug weiter: Es soll auch allein benutzbar bleiben.
if os.path.dirname(WERKSTATT_ORDNER) not in sys.path:
    sys.path.append(os.path.dirname(WERKSTATT_ORDNER))
DATEI = os.path.join(WERKSTATT_ORDNER, "erinnerungen.json")

# So lange nach der Zeit gilt eine Erinnerung noch als faellig; danach ist sie
# verpasst und wird einmal als solche gemeldet.
KULANZ_MIN = 120


def in_werkstatt(pfad):
    ziel = os.path.abspath(pfad)
    wurzel = os.path.abspath(WERKSTATT_ORDNER)
    try:
        return os.path.commonpath([ziel, wurzel]) == wurzel
    except ValueError:
        return False


def liste_fehlt(datei=DATEI):
    """Fehlt die Datei ganz - oder ist sie nur leer?

    DER UNTERSCHIED IST EINE ANTWORT. `lesen()` gibt in beiden Faellen eine
    leere Liste zurueck, und damit antwortet er auf "habe ich Termine?" mit
    "nein" - auch dann, wenn die Liste verlorengegangen ist. Eine leere Liste
    heisst "nichts vorgemerkt", eine fehlende Datei heisst "was du mir genannt
    hast, ist weg". Das Zweite muss er sagen koennen.

    Genau so ist erinnerungen.json am 12.09. gegen 21 Uhr verschwunden, und
    niemand hat es gemerkt: Es sah aus wie ein Normalzustand.

    `lesen()` bleibt absichtlich wie es war - faellige() und offene() bauen
    darauf, und eine geaenderte Rueckgabe waere ein Umbau mitten in der Nacht.
    Wer den Unterschied braucht, fragt hier.
    """
    return not os.path.isfile(datei)


def lesen(datei=DATEI):
    """Die Liste. Fehlt die Datei, kommt [] - siehe liste_fehlt()."""
    if not os.path.isfile(datei):
        return []
    try:
        with open(datei, "r", encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    return d if isinstance(d, list) else []


def schreiben(liste, datei=DATEI):
    if not in_werkstatt(datei):
        raise ValueError("Die Liste muss in der Werkstatt liegen: %s" % datei)
    # DERSELBE RIEGEL WIE IM GEDAECHTNIS, und er hat hier genauso gefehlt. Am
    # 13.09. um 12:12 hat ableiten_test.py einen echten Termin angelegt -
    # "Calvin geht mit Lena zum Arzt", 09:00, aus einer Sitzung, die es nie
    # gab. `gedaechtnis.merken` war da schon abgesichert, dieser Weg nicht:
    # `archiv.anwenden` legt einen Termin ueber erinnern.merken an, und in dem
    # Augenblick, in dem das Ableiten scharf wurde, stand die Tuer offen.
    #
    # Der Riegel gehoert an die Stelle, die schreibt - nicht in jede Probe.
    try:
        import probenort
        probenort.schreiben_pruefen(datei, "erinnern.schreiben")
    except ImportError:
        pass
    tmp = datei + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False, indent=2)
    os.replace(tmp, datei)


def zeit_lesen(text):
    """Versteht '2026-09-12 18:30', '18:30' (heute oder morgen) und ISO."""
    text = (text or "").strip()
    jetzt = datetime.datetime.now()
    for muster in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                   "%d.%m.%Y %H:%M", "%d.%m. %H:%M"):
        try:
            wann = datetime.datetime.strptime(text, muster)
            if wann.year == 1900:
                wann = wann.replace(year=jetzt.year)
            return wann
        except ValueError:
            continue
    try:
        stunde, minute = text.split(":")
        wann = jetzt.replace(hour=int(stunde), minute=int(minute),
                             second=0, microsecond=0)
        # Schon vorbei? Dann ist morgen gemeint.
        if wann <= jetzt:
            wann += datetime.timedelta(days=1)
        return wann
    except (ValueError, AttributeError):
        return None


def merken(text, wann=None, in_minuten=None, datei=DATEI):
    """Legt eine Erinnerung an. Gibt sie zurueck."""
    text = " ".join(str(text).split())
    if not text:
        raise ValueError("Ohne Text keine Erinnerung.")
    if in_minuten is not None:
        zeitpunkt = datetime.datetime.now() + datetime.timedelta(
            minutes=float(in_minuten))
    else:
        zeitpunkt = zeit_lesen(wann)
    if zeitpunkt is None:
        raise ValueError("Zeitpunkt nicht verstanden: %r" % wann)

    liste = lesen(datei)
    eintrag = {
        "id": "e-%d" % int(datetime.datetime.now().timestamp() * 1000),
        "text": text,
        "wann": zeitpunkt.isoformat(timespec="seconds"),
        "angelegt": datetime.datetime.now().isoformat(timespec="seconds"),
        "erledigt": False,
        "verpasst": False,
    }
    liste.append(eintrag)
    schreiben(liste, datei)
    return eintrag


def faellige(datei=DATEI, jetzt=None):
    """Was ist jetzt dran? Markiert es zugleich als erledigt.

    Verpasste (laenger als die Kulanz her) werden einmal als solche gemeldet,
    damit sie nicht still verschwinden.
    """
    jetzt = jetzt or datetime.datetime.now()
    liste = lesen(datei)
    raus = []
    geaendert = False
    for e in liste:
        if e.get("erledigt"):
            continue
        try:
            wann = datetime.datetime.fromisoformat(e["wann"])
        except (KeyError, ValueError):
            continue
        if wann > jetzt:
            continue
        verspaetung = (jetzt - wann).total_seconds() / 60.0
        e["erledigt"] = True
        e["verpasst"] = verspaetung > KULANZ_MIN
        geaendert = True
        raus.append(dict(e, verspaetung_min=round(verspaetung)))
    if geaendert:
        schreiben(liste, datei)
    return raus


def offene(datei=DATEI):
    liste = [e for e in lesen(datei) if not e.get("erledigt")]
    liste.sort(key=lambda e: e.get("wann", ""))
    return liste


def satz(e):
    """Wie er es sagen wuerde."""
    if e.get("verpasst"):
        return ("Ich hätte dich früher erinnern sollen: %s. Das war vor %d "
                "Minuten." % (e["text"], e.get("verspaetung_min", 0)))
    return "Du wolltest an etwas erinnert werden: %s." % e["text"]


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest():
    print("Selbsttest erinnern")
    gesamt = 0
    fehler = 0

    def pruefe(bedingung, was):
        nonlocal gesamt, fehler
        gesamt += 1
        print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
        if not bedingung:
            fehler += 1

    ordner = os.path.join(WERKSTATT_ORDNER, "_erinnern_selbsttest")
    if not os.path.isdir(ordner):
        os.makedirs(ordner)
    probe = os.path.join(ordner, "liste.json")
    if os.path.isfile(probe):
        open(probe, "w", encoding="utf-8").close()

    try:
        jetzt = datetime.datetime.now()

        # Eine in der Zukunft, eine gerade faellig, eine laengst verpasst.
        merken("Mülltonne rausstellen", in_minuten=120, datei=probe)
        merken("Kaffee aufsetzen", in_minuten=-1, datei=probe)
        merken("Paket abholen", in_minuten=-300, datei=probe)

        pruefe(len(lesen(probe)) == 3, "drei Erinnerungen angelegt")
        pruefe(len(offene(probe)) == 3, "alle drei offen")

        dran = faellige(probe, jetzt)
        texte = [e["text"] for e in dran]
        pruefe(len(dran) == 2, "zwei sind fällig: %s" % texte)
        pruefe("Mülltonne rausstellen" not in texte,
               "die künftige ist NICHT dabei")

        verpasst = [e for e in dran if e.get("verpasst")]
        pruefe(len(verpasst) == 1 and verpasst[0]["text"] == "Paket abholen",
               "die alte gilt als verpasst")

        pruefe(len(offene(probe)) == 1, "danach ist nur noch eine offen")
        pruefe(not faellige(probe, jetzt),
               "dieselbe wird nicht zweimal gemeldet")

        s = satz(verpasst[0])
        pruefe("früher erinnern sollen" in s, "verpasste klingt anders: %s"
               % s[:70])

        # Zeitangaben verstehen.
        morgen = zeit_lesen("07:30")
        pruefe(morgen is not None and morgen > jetzt,
               "Uhrzeit ohne Datum liegt in der Zukunft: %s" % morgen)
        fest = zeit_lesen("2026-12-24 18:00")
        pruefe(fest is not None and fest.month == 12 and fest.day == 24,
               "festes Datum verstanden: %s" % fest)
        pruefe(zeit_lesen("übermorgen irgendwann") is None,
               "Unverständliches wird abgelehnt")
    finally:
        if os.path.isfile(probe):
            open(probe, "w", encoding="utf-8").close()

    print("%d von %d bestanden" % (gesamt - fehler, gesamt))
    return 1 if fehler else 0


def main():
    p = argparse.ArgumentParser(description="Zur rechten Zeit erinnern.")
    p.add_argument("--merken", help="Text der Erinnerung")
    p.add_argument("--wann", help="Zeitpunkt, etwa '18:30' oder '2026-09-12 18:30'")
    p.add_argument("--in", dest="in_minuten", type=float, help="in N Minuten")
    p.add_argument("--faellig", action="store_true", help="was jetzt dran ist")
    p.add_argument("--liste", action="store_true", help="was ansteht")
    p.add_argument("--selbsttest", action="store_true")
    a = p.parse_args()

    if a.selbsttest:
        return selbsttest()

    if a.merken:
        try:
            e = merken(a.merken, wann=a.wann, in_minuten=a.in_minuten)
        except ValueError as f:
            print(f)
            return 1
        print("Gemerkt für %s: %s" % (e["wann"], e["text"]))
        return 0

    if a.faellig:
        dran = faellige()
        if not dran:
            print("Jetzt ist nichts dran.")
        for e in dran:
            print(satz(e))
        return 0

    if a.liste:
        liste = offene()
        if not liste:
            print("Es steht nichts an.")
        for e in liste:
            print("  %s  %s" % (e["wann"], e["text"]))
        return 0

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
