"""rhythmus - Muster im Tages- und Wochenlauf erkennen.

    python rhythmus.py               Messwert anhaengen, Muster ausgeben
    python rhythmus.py --frage       nur ausgeben, nichts anhaengen
    python rhythmus.py --selbsttest  prueft sich selbst, 0 bei Erfolg

Das Lagebild sagt, was JETZT ist. Dieses Werkzeug sammelt es und sagt, was
UEBLICH ist: wann Calvin meist da ist, wann der Rechner ruht, welche Geraete
zu welcher Zeit im Netz sind.

Ohne diese Geschichte kann er nicht wissen, ob "das iPhone ist weg" normal
ist (nachts) oder auffaellig (mittags). Erst der Rhythmus macht aus einer
Beobachtung eine Abweichung.

Pfade haengen am Ort dieser Datei. Nur Standardbibliothek, kein Netz.
"""

import argparse
import datetime
import json
import os
import sys

# einstellungen.py lives with his code: two levels up in the workshop
# (werkstatt/werkzeuge/), one level up in the repo (bewohner/werkzeuge/).
# A tool runs as a process of its own, so it has to look.
_hier = os.path.dirname(os.path.abspath(__file__))
for _ort in (os.path.dirname(os.path.dirname(_hier)), os.path.dirname(_hier)):
    if os.path.isfile(os.path.join(_ort, "einstellungen.py")):
        if _ort not in sys.path:
            sys.path.insert(0, _ort)
        break
from einstellungen import NAME  # noqa: E402

WERKZEUG_ORDNER = os.path.dirname(os.path.abspath(__file__))
WERKSTATT_ORDNER = os.path.dirname(WERKZEUG_ORDNER)
LAGE_DATEI = os.path.join(WERKSTATT_ORDNER, "lage.json")
VERLAUF = os.path.join(WERKSTATT_ORDNER, "rhythmus.jsonl")

# So viele Tage zurueck werden ausgewertet.
TAGE_ZURUECK = 14
# Ab so vielen Beobachtungen je Stunde gilt eine Aussage als belastbar.
BELASTBAR_AB = 3

WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
              "Samstag", "Sonntag")


def in_werkstatt(pfad):
    ziel = os.path.abspath(pfad)
    wurzel = os.path.abspath(WERKSTATT_ORDNER)
    try:
        return os.path.commonpath([ziel, wurzel]) == wurzel
    except ValueError:
        return False


def lage_lesen():
    try:
        with open(LAGE_DATEI, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def anhaengen(bild=None, verlauf=VERLAUF):
    """Einen Messwert festhalten: Stunde, Wochentag, wer im Netz ist."""
    if not in_werkstatt(verlauf):
        raise ValueError("Der Verlauf muss in der Werkstatt liegen: %s"
                         % verlauf)
    bild = bild if bild is not None else lage_lesen()
    jetzt = datetime.datetime.now()
    eintrag = {
        "zeit": jetzt.isoformat(timespec="seconds"),
        "stunde": jetzt.hour,
        "wochentag": jetzt.weekday(),
        "geraete": len(bild.get("netz") or []),
        "namen": sorted(g.get("name") or g.get("hostname") or ""
                        for g in (bild.get("netz") or []))[:20],
        "nutzer_zuletzt": bild.get("nutzer_zuletzt"),
        "platte_frei_gb": (bild.get("rechner") or {}).get("platte_frei_gb"),
    }
    with open(verlauf, "a", encoding="utf-8") as f:
        f.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
    return eintrag


def lesen(verlauf=VERLAUF, tage=TAGE_ZURUECK):
    if not os.path.isfile(verlauf):
        return []
    grenze = datetime.datetime.now() - datetime.timedelta(days=tage)
    raus = []
    with open(verlauf, "r", encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if not zeile:
                continue
            try:
                e = json.loads(zeile)
            except ValueError:
                continue
            if not isinstance(e, dict) or "stunde" not in e:
                continue
            try:
                wann = datetime.datetime.fromisoformat(e["zeit"])
            except (KeyError, ValueError):
                continue
            if wann >= grenze:
                raus.append(e)
    return raus


def muster(eintraege):
    """Was ist ueblich? Gibt ein Woerterbuch mit Befunden zurueck."""
    if not eintraege:
        return {}

    je_stunde = {}
    for e in eintraege:
        je_stunde.setdefault(e["stunde"], []).append(e)

    # Wann ist Calvin meist erreichbar? Als "da" gilt, wenn sein letztes Wort
    # weniger als zwei Stunden her ist.
    wach = {}
    for stunde, liste in je_stunde.items():
        da = 0
        for e in liste:
            zuletzt = e.get("nutzer_zuletzt")
            if not zuletzt:
                continue
            try:
                wann = datetime.datetime.fromisoformat(e["zeit"]).timestamp()
            except (KeyError, ValueError):
                continue
            if wann - float(zuletzt) < 7200:
                da += 1
        if len(liste) >= BELASTBAR_AB:
            wach[stunde] = da / len(liste)

    # Wie viele Geraete sind je Stunde ueblich?
    geraete = {}
    for stunde, liste in je_stunde.items():
        if len(liste) >= BELASTBAR_AB:
            zahlen = sorted(e.get("geraete", 0) for e in liste)
            geraete[stunde] = zahlen[len(zahlen) // 2]

    return {"beobachtungen": len(eintraege),
            "stunden_belastbar": len(geraete),
            "wach_je_stunde": wach,
            "geraete_je_stunde": geraete}


def abweichung(bild, m):
    """Weicht die Lage gerade vom Ueblichen ab? Satz oder None."""
    if not m or not m.get("geraete_je_stunde"):
        return None
    stunde = datetime.datetime.now().hour
    ueblich = m["geraete_je_stunde"].get(stunde)
    if ueblich is None:
        return None
    jetzt = len(bild.get("netz") or [])
    if abs(jetzt - ueblich) < 3:
        return None
    richtung = "mehr" if jetzt > ueblich else "weniger"
    return ("Um diese Zeit sind sonst %d Geräte im Netz, jetzt sind es %d - "
            "%s als üblich." % (ueblich, jetzt, richtung))


def bericht(eintraege, bild=None):
    m = muster(eintraege)
    if not m:
        return "Noch keine Beobachtungen im Verlauf."
    if not m["stunden_belastbar"]:
        return ("%d Beobachtungen gesammelt, aber noch keine Stunde oft genug "
                "gesehen - ich brauche mehr Tage." % m["beobachtungen"])

    zeilen = ["%d Beobachtungen, %d Stunden belastbar."
              % (m["beobachtungen"], m["stunden_belastbar"])]

    wach = [(s, a) for s, a in m["wach_je_stunde"].items() if a >= 0.5]
    if wach:
        wach.sort()
        zeilen.append(f"{NAME} ist meist erreichbar zwischen %d und %d Uhr."
                      % (wach[0][0], wach[-1][0] + 1))

    g = sorted(m["geraete_je_stunde"].items())
    if g:
        wenigste = min(g, key=lambda p: p[1])
        meiste = max(g, key=lambda p: p[1])
        zeilen.append("Im Netz sind um %d Uhr am wenigsten Geräte (%d), um "
                      "%d Uhr am meisten (%d)."
                      % (wenigste[0], wenigste[1], meiste[0], meiste[1]))

    if bild is not None:
        satz = abweichung(bild, m)
        if satz:
            zeilen.append(satz)
    return " ".join(zeilen)


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest():
    print("Selbsttest rhythmus")
    gesamt = 0
    fehler = 0

    def pruefe(bedingung, was):
        nonlocal gesamt, fehler
        gesamt += 1
        print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
        if not bedingung:
            fehler += 1

    ordner = os.path.join(WERKSTATT_ORDNER, "_rhythmus_selbsttest")
    if not os.path.isdir(ordner):
        os.makedirs(ordner)
    probe = os.path.join(ordner, "verlauf.jsonl")
    with open(probe, "w", encoding="utf-8"):
        pass

    try:
        # Sieben Tage lang: nachts drei Geraete, mittags zwölf, Calvin
        # mittags erreichbar, nachts nicht.
        jetzt = datetime.datetime.now()
        with open(probe, "a", encoding="utf-8") as f:
            for tag in range(7):
                for stunde in (3, 13):
                    wann = (jetzt - datetime.timedelta(days=tag)).replace(
                        hour=stunde, minute=0, second=0, microsecond=0)
                    mittags = stunde == 13
                    f.write(json.dumps({
                        "zeit": wann.isoformat(timespec="seconds"),
                        "stunde": stunde,
                        "wochentag": wann.weekday(),
                        "geraete": 12 if mittags else 3,
                        "namen": [],
                        "nutzer_zuletzt": (wann.timestamp() - 600
                                           if mittags else
                                           wann.timestamp() - 40000),
                        "platte_frei_gb": 1500,
                    }, ensure_ascii=False) + "\n")

        eintraege = lesen(probe)
        pruefe(len(eintraege) == 14, "14 Beobachtungen gelesen: %d"
               % len(eintraege))

        m = muster(eintraege)
        pruefe(m["geraete_je_stunde"].get(3) == 3,
               "nachts drei Geräte erkannt: %s" % m["geraete_je_stunde"].get(3))
        pruefe(m["geraete_je_stunde"].get(13) == 12,
               "mittags zwölf Geräte erkannt: %s"
               % m["geraete_je_stunde"].get(13))
        pruefe(m["wach_je_stunde"].get(13, 0) > 0.9,
               f"{NAME} ist mittags erreichbar: %.0f Prozent"
               % (m["wach_je_stunde"].get(13, 0) * 100))
        pruefe(m["wach_je_stunde"].get(3, 1) < 0.1,
               "nachts nicht: %.0f Prozent"
               % (m["wach_je_stunde"].get(3, 1) * 100))

        # Eine Lage, die deutlich abweicht, muss auffallen.
        stunde = datetime.datetime.now().hour
        kuenstlich = {"netz": [{"name": "x"}] * 40}
        m2 = dict(m)
        m2["geraete_je_stunde"] = {stunde: 4}
        satz = abweichung(kuenstlich, m2)
        pruefe(satz is not None and "mehr als üblich" in satz,
               "Abweichung erkannt: %s" % satz)

        # Und eine unauffaellige Lage darf NICHT melden.
        m3 = dict(m)
        m3["geraete_je_stunde"] = {stunde: 5}
        pruefe(abweichung({"netz": [{"name": "x"}] * 6}, m3) is None,
               "normale Lage meldet nichts")

        text = bericht(eintraege)
        pruefe("Beobachtungen" in text and len(text) > 40,
               "Bericht entsteht: %s" % text[:90])
    finally:
        if os.path.isfile(probe):
            with open(probe, "w", encoding="utf-8"):
                pass

    print("%d von %d bestanden" % (gesamt - fehler, gesamt))
    return 1 if fehler else 0


def main():
    p = argparse.ArgumentParser(description="Muster im Tageslauf.")
    p.add_argument("--frage", action="store_true",
                   help="nur ausgeben, nichts anhaengen")
    p.add_argument("--selbsttest", action="store_true")
    a = p.parse_args()

    if a.selbsttest:
        return selbsttest()

    bild = lage_lesen()
    if not a.frage:
        anhaengen(bild)
    print(bericht(lesen(), bild))
    return 0


if __name__ == "__main__":
    sys.exit(main())
