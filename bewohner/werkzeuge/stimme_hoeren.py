"""stimme_hoeren - Klang in Zahlen, nicht in Worten.

    python stimme_hoeren.py <datei.wav|mp3>   eine Aufnahme vermessen
    python stimme_hoeren.py --ordner <pfad>   alle Aufnahmen darin
    python stimme_hoeren.py --selbsttest      prueft sich selbst, 0 bei Erfolg

Nicht transkribieren, sondern hoeren: Tonhoehe und ihr Verlauf,
Klangfarbe (Spektralschwerpunkt), Sprechtempo ueber die Silbenrate, Pausen,
Dynamik. Damit kann er begruenden, warum ihm eine Stimme passt, statt sie
nach Gefuehl zu waehlen.

Die Pfade haengen am Ort dieser Datei, nicht am Arbeitsverzeichnis.
Nur Standardbibliothek, kein Netz, keine fremden Programme.
"""

import argparse
import json
import math
import os
import struct
import sys
import wave

WERKZEUG_ORDNER = os.path.dirname(os.path.abspath(__file__))
WERKSTATT_ORDNER = os.path.dirname(WERKZEUG_ORDNER)

# Menschliche Sprechstimmen liegen zwischen diesen Grenzen.
TIEFSTE_HZ = 70.0
HOECHSTE_HZ = 400.0
# Fensterlaenge fuer die Tonhoehe: 40 ms fasst mehrere Schwingungen.
FENSTER_S = 0.04
# Darunter gilt ein Fenster als still.
STILLE_SCHWELLE = 0.012
# Eine Pause zaehlt ab dieser Laenge.
PAUSE_AB_S = 0.15


def wav_lesen(pfad):
    """Liest eine WAV-Datei als Liste von Werten zwischen -1 und 1."""
    with wave.open(pfad, "rb") as w:
        kanaele = w.getnchannels()
        breite = w.getsampwidth()
        rate = w.getframerate()
        roh = w.readframes(w.getnframes())

    if breite == 2:
        werte = struct.unpack("<%dh" % (len(roh) // 2), roh)
        teiler = 32768.0
    elif breite == 1:
        werte = [b - 128 for b in roh]
        teiler = 128.0
    else:
        raise ValueError("Nur 8 oder 16 Bit, gefunden: %d" % (breite * 8))

    if kanaele > 1:
        werte = [sum(werte[i:i + kanaele]) / kanaele
                 for i in range(0, len(werte) - kanaele + 1, kanaele)]
    return [v / teiler for v in werte], rate


def lautstaerke(stueck):
    """Effektivwert - wie laut ein Stueck ist."""
    if not stueck:
        return 0.0
    return math.sqrt(sum(v * v for v in stueck) / len(stueck))


def grundton(stueck, rate):
    """Grundfrequenz eines Fensters ueber Autokorrelation.

    Gibt 0 zurueck, wenn das Fenster still ist oder keine Periode erkennbar.
    """
    if lautstaerke(stueck) < STILLE_SCHWELLE:
        return 0.0
    mitte = sum(stueck) / len(stueck)
    stueck = [v - mitte for v in stueck]

    von = int(rate / HOECHSTE_HZ)
    bis = min(int(rate / TIEFSTE_HZ), len(stueck) - 1)
    if bis <= von:
        return 0.0

    bester_wert = 0.0
    beste_verschiebung = 0
    for verschiebung in range(von, bis):
        summe = 0.0
        for i in range(len(stueck) - verschiebung):
            summe += stueck[i] * stueck[i + verschiebung]
        if summe > bester_wert:
            bester_wert = summe
            beste_verschiebung = verschiebung

    if not beste_verschiebung:
        return 0.0
    return rate / beste_verschiebung


def spektralschwerpunkt(werte, rate):
    """Wo liegt die Energie im Spektrum? Hoch heisst hell, tief heisst dunkel.

    Diskrete Fouriertransformation von Hand, auf wenige Baender gerafft -
    die Standardbibliothek bringt keine schnelle Variante mit, und fuer einen
    Schwerpunkt genuegt eine grobe Aufloesung.
    """
    # Auf hoechstens 4096 Werte eindampfen, sonst dauert es zu lange.
    schritt = max(1, len(werte) // 4096)
    probe = werte[::schritt]
    n = len(probe)
    if n < 16:
        return 0.0
    effektive_rate = rate / schritt

    oben = 0.0
    unten = 0.0
    # 32 Baender genuegen fuer einen Schwerpunkt.
    for band in range(1, 33):
        frequenz = band * effektive_rate / 64.0
        if frequenz >= effektive_rate / 2:
            break
        real = 0.0
        imag = 0.0
        for i, v in enumerate(probe):
            winkel = 2.0 * math.pi * band * i / 64.0
            real += v * math.cos(winkel)
            imag -= v * math.sin(winkel)
        betrag = math.sqrt(real * real + imag * imag)
        oben += betrag * frequenz
        unten += betrag
    return oben / unten if unten > 0 else 0.0


def messen(pfad):
    """Alle Kennzahlen einer Aufnahme."""
    werte, rate = wav_lesen(pfad)
    dauer = len(werte) / rate if rate else 0.0

    fenster = max(1, int(rate * FENSTER_S))
    toene = []
    laut_je_fenster = []
    for anfang in range(0, len(werte) - fenster, fenster):
        stueck = werte[anfang:anfang + fenster]
        laut_je_fenster.append(lautstaerke(stueck) >= STILLE_SCHWELLE)
        ton = grundton(stueck, rate)
        if ton:
            toene.append(ton)

    toene.sort()
    if toene:
        mitte = toene[len(toene) // 2]
        unten = toene[int(len(toene) * 0.1)]
        oben = toene[int(len(toene) * 0.9)]
    else:
        mitte = unten = oben = 0.0

    # Pausen: zusammenhaengende stille Fenster.
    pausen = 0
    lauf = 0
    for laut in laut_je_fenster:
        if laut:
            if lauf * FENSTER_S >= PAUSE_AB_S:
                pausen += 1
            lauf = 0
        else:
            lauf += 1
    if lauf * FENSTER_S >= PAUSE_AB_S:
        pausen += 1

    stille = (1.0 - sum(laut_je_fenster) / len(laut_je_fenster)
              if laut_je_fenster else 0.0)

    betraege = sorted(abs(v) for v in werte)
    if betraege:
        mittlerer = betraege[len(betraege) // 2]
        lauter = betraege[int(len(betraege) * 0.95)]
        dynamik = lauter / mittlerer if mittlerer > 1e-9 else 0.0
    else:
        dynamik = 0.0

    return {
        "datei": os.path.basename(pfad),
        "dauer_s": round(dauer, 2),
        "tonhoehe_hz": round(mitte, 1),
        "spanne_hz": round(oben - unten, 1),
        "schwerpunkt_hz": round(spektralschwerpunkt(werte, rate)),
        "stille_anteil": round(stille, 2),
        "pausen": pausen,
        "dynamik": round(dynamik, 1),
    }


def beschreiben(m):
    """Ein Satz aus den Zahlen - ohne Modell, rein aus den Werten."""
    teile = []
    if m["tonhoehe_hz"] >= 160:
        teile.append("hoch")
    elif m["tonhoehe_hz"] >= 110:
        teile.append("mittel")
    elif m["tonhoehe_hz"] > 0:
        teile.append("tief")

    if m["spanne_hz"] >= 200:
        teile.append("stark schwankend")
    elif m["spanne_hz"] >= 90:
        teile.append("lebendig")
    elif m["spanne_hz"] > 0:
        teile.append("ruhig")

    if m["schwerpunkt_hz"] >= 3000:
        teile.append("hell")
    elif m["schwerpunkt_hz"] >= 1800:
        teile.append("mittelhell")
    elif m["schwerpunkt_hz"] > 0:
        teile.append("dunkel")

    if not teile:
        return "Keine Stimme erkennbar."
    return "%s: %s, %.0f Hertz Grundton, %d Prozent Stille." % (
        m["datei"], ", ".join(teile), m["tonhoehe_hz"],
        round(m["stille_anteil"] * 100))


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def ton_erzeugen(pfad, frequenz, dauer_s=1.0, rate=16000, stille_am_ende=0.0):
    """Schreibt einen Sinuston als WAV - Grundlage fuer den Selbsttest."""
    werte = []
    for i in range(int(rate * dauer_s)):
        werte.append(0.6 * math.sin(2.0 * math.pi * frequenz * i / rate))
    werte.extend([0.0] * int(rate * stille_am_ende))
    roh = struct.pack("<%dh" % len(werte),
                      *[int(max(-1.0, min(1.0, v)) * 32767) for v in werte])
    with wave.open(pfad, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(roh)


def selbsttest():
    """Prueft an einem selbst erzeugten Ton, ob die Messung stimmt."""
    print("Selbsttest stimme_hoeren")
    gesamt = 0
    fehler = 0

    def pruefe(bedingung, was):
        nonlocal gesamt, fehler
        gesamt += 1
        if bedingung:
            print("  ok   %s" % was)
        else:
            print("  FEHL %s" % was)
            fehler += 1

    ordner = os.path.join(WERKSTATT_ORDNER, "_stimme_selbsttest")
    if not os.path.isdir(ordner):
        os.makedirs(ordner)
    probe = os.path.join(ordner, "ton.wav")

    try:
        # 150 Hertz, eine Sekunde, danach eine halbe Sekunde Stille.
        ton_erzeugen(probe, 150.0, dauer_s=1.0, stille_am_ende=0.5)
        m = messen(probe)

        pruefe(abs(m["tonhoehe_hz"] - 150.0) < 8.0,
               "Tonhoehe erkannt: %.1f Hz statt 150" % m["tonhoehe_hz"])
        pruefe(m["spanne_hz"] < 20.0,
               "reiner Ton hat kaum Spanne: %.1f Hz" % m["spanne_hz"])
        pruefe(0.2 < m["stille_anteil"] < 0.5,
               "Stille erkannt: %d Prozent" % round(m["stille_anteil"] * 100))
        pruefe(m["pausen"] >= 1, "Pause gezaehlt: %d" % m["pausen"])
        pruefe(1.3 < m["dauer_s"] < 1.7,
               "Dauer stimmt: %.2f s" % m["dauer_s"])

        # Ein hoeherer Ton muss auch als hoeher gemessen werden.
        hoch = os.path.join(ordner, "hoch.wav")
        ton_erzeugen(hoch, 300.0, dauer_s=1.0)
        m2 = messen(hoch)
        pruefe(m2["tonhoehe_hz"] > m["tonhoehe_hz"] + 50,
               "hoeherer Ton wird hoeher gemessen: %.0f gegen %.0f Hz"
               % (m2["tonhoehe_hz"], m["tonhoehe_hz"]))

        satz = beschreiben(m2)
        pruefe(len(satz) > 20 and "Hertz" in satz,
               "Beschreibung entsteht: %s" % satz)
    finally:
        for name in ("ton.wav", "hoch.wav"):
            weg = os.path.join(ordner, name)
            if os.path.isfile(weg):
                os.rename(weg, weg + ".alt")
                os.rename(weg + ".alt", weg)
                with open(weg, "wb"):
                    pass

    print("%d von %d bestanden" % (gesamt - fehler, gesamt))
    return 1 if fehler else 0


def main():
    p = argparse.ArgumentParser(description="Klang in Zahlen.")
    p.add_argument("datei", nargs="?", help="WAV-Datei")
    p.add_argument("--ordner", help="alle WAV-Dateien in diesem Ordner")
    p.add_argument("--selbsttest", action="store_true")
    p.add_argument("--json", action="store_true", help="rohe Zahlen ausgeben")
    a = p.parse_args()

    if a.selbsttest:
        return selbsttest()

    dateien = []
    if a.ordner:
        for name in sorted(os.listdir(a.ordner)):
            if name.lower().endswith(".wav"):
                dateien.append(os.path.join(a.ordner, name))
    elif a.datei:
        dateien = [a.datei]
    else:
        p.print_help()
        return 1

    for pfad in dateien:
        try:
            m = messen(pfad)
        except Exception as f:
            print("%s: nicht messbar (%s)" % (os.path.basename(pfad),
                                              type(f).__name__))
            continue
        if a.json:
            print(json.dumps(m, ensure_ascii=False))
        else:
            print(beschreiben(m))
    return 0


if __name__ == "__main__":
    sys.exit(main())
