"""Was in der Nacht geschehen ist - in dreissig Sekunden lesbar.

    python -X utf8 nacht.py

Vier Zeilen und eine Liste, nicht mehr. Es liest das Journal, nicht das
Gedaechtnis: Was D getan hat, steht als `pruefung` und `vorgelegt` drin, und
was C angelegt HAETTE, als `ableiten_trocken`.

DARUM GEHT ES HEUTE NACHT: C laeuft im Trockenlauf (ABLEITEN_SCHARF ist aus).
Jede Zeile `ableiten_trocken` ist ein Termin oder ein Fakt, den er angelegt
haette. Daran ist zu entscheiden, ob der Schalter scharf darf - und diese
Entscheidung trifft Calvin.
"""
from __future__ import annotations

from einstellungen import NAME
import json
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
JOURNAL = HIER / "werkstatt" / "journal.jsonl"

# Was als "die Nacht" gilt. Von 22 Uhr bis zum Aufruf - der Rueckblick nimmt
# 24 Stunden, hier reicht der Abend davor.
STUNDEN = 12.0


def zeilen(seit: float) -> list[dict]:
    if not JOURNAL.exists():
        return []
    heraus = []
    for z in JOURNAL.read_text(encoding="utf-8", errors="replace").splitlines():
        if not z.strip():
            continue
        try:
            e = json.loads(z)
        except ValueError:
            continue
        if float(e.get("ts") or 0) >= seit:
            heraus.append(e)
    return heraus


def _uhr(e: dict) -> str:
    return time.strftime("%H:%M", time.localtime(float(e.get("ts") or 0)))


# Was in einer Nacht zaehlt. Diese Liste IST die Auswahl, und der gedruckte
# Bericht und die gesprochene Antwort lesen beide daraus - sonst stehen zwei
# Begriffe von "wichtig" im System, und gemessen am 13.09. waren es zwei:
# hier standen Pruefung, Trockenlauf und Zusammenfassungen, waehrend
# passiert.py dieselbe Nacht mit zwoelf Dateiaenderungen und einem
# Bedarfsdienst beantwortete, weil diese Arten in seiner Gewichtstabelle
# fehlten und stumm auf GEWICHT_UNBEKANNT fielen.
ARTEN = ("abschluss", "pruefung", "vorgelegt", "rueckfrage",
         "ableiten_trocken", "ableiten_zurueck", "sitzung", "bestand",
         "fehler", "kernwissen_fehlt", "verlust")


def geteilt(stunden: float = STUNDEN,
            jetzt: float | None = None) -> tuple[dict, dict]:
    """(Calvins Nacht, was an mir gearbeitet wurde) - beide nach Arten.

    Die Trennung ist der Befund vom 13.09., 04:22: Auf "Was ist letzte Nacht
    passiert?" kam "22:30 diskutierte man ueber Spielarten und Desktop"
    zurueck. Das waren die vier Fragen aus zuhause_probe.py, in deren
    Reihenfolge - Calvin hat nie darueber geredet. Er bekam eine Geschichte zu
    hoeren, die ihm nicht gehoert.

    Gezaehlt wird die zweite Haelfte trotzdem. Sie zu verschweigen waere der
    gleiche Fehler andersherum: "es ist nichts passiert" ist falsch, wenn die
    Nacht voller Messungen war.
    """
    import passiert
    jetzt = time.time() if jetzt is None else jetzt
    alle = zeilen(jetzt - stunden * 3600)
    seine = {a: [] for a in ARTEN}
    an_mir = {a: [] for a in ARTEN}
    for e in alle:
        art = e.get("kind")
        if art in seine:
            (seine if passiert.ist_vom_nutzer(e) else an_mir)[art].append(e)
    return seine, an_mir


def gruppen(stunden: float = STUNDEN, jetzt: float | None = None) -> dict:
    """Calvins Nacht nach Arten sortiert - eine Liste je Art aus ARTEN.

    Getrennt von main(), damit nicht nur der Ausdruck, sondern auch die
    gesprochene Antwort daraus lesen kann. Jede Art aus ARTEN kommt vor, auch
    leer: "die Pruefung ist nicht gelaufen" ist eine Auskunft, und sie
    verschwindet, wenn fehlende Arten gar nicht auftauchen.
    """
    return geteilt(stunden, jetzt)[0]


def saetze(stunden: float = STUNDEN,
           jetzt: float | None = None) -> tuple[list[str], int]:
    """Die Nacht als reine ANGABEN, ohne Anleitung - plus: wie viel war an mir.

    Getrennt von fuer_prompt(), weil die Anleitung nur fuer EINEN Leser gilt.
    Der Rueckblick bekam zuerst den ganzen Block samt "Berichte daraus und
    zaehle KEINE Dateiaenderungen auf" als Rohbild - zwei Auftraege in einem
    Prompt, und gpt-oss lieferte `{"gebaut": []}` zurueck. Eine Angabe ist
    keine Anweisung; wer beides mischt, bekommt nichts.
    """
    jetzt = time.time() if jetzt is None else jetzt
    g, an_mir = geteilt(stunden, jetzt)
    fremd = sum(len(v) for v in an_mir.values())
    z = _angaben(g, fremd, jetzt)
    return z, fremd


def fuer_prompt(stunden: float = STUNDEN, jetzt: float | None = None,
                hoechstens: int = 1800) -> str:
    """Die Nacht in einem Block, den ein Prompt tragen kann.

    Calvins Satz war: "was ist letzte Nacht passiert - und bam, bekomme ich
    eine Antwort. Dass er prueft, was relevant ist." Geprueft wird hier, nicht
    vom Modell: Was hier steht, steht in ARTEN, und was nicht darin steht,
    kommt nicht vor. Das Modell formuliert.

    Gemessen am 13.09. antwortete er stattdessen mit einer Zeitstempelliste -
    "beschreibungen.json wurde geaendert", "MoNotificationUx kommt und geht" -
    und die Pruefung um 02:03, drei zusammengefasste Gespraeche und der
    Trockenlauf fehlten ganz.
    """
    jetzt = time.time() if jetzt is None else jetzt
    g, an_mir = geteilt(stunden, jetzt)
    fremd = sum(len(v) for v in an_mir.values())

    # Bestand die Nacht NUR aus Arbeit an mir, ist die ehrliche Antwort nicht
    # eine Erzaehlung daraus. Das ist ein Unterschied, den nur er kennen kann:
    # "es ist nichts passiert" waere falsch, und "du hast ueber Spielarten
    # diskutiert" waere eine fremde Geschichte. Beides vermeidet nur der Satz,
    # der den Unterschied nennt.
    if fremd and not any(g.values()):
        return (f"In dieser Nacht ist nichts passiert, was {NAME} betrifft - "
                f"es wurde an MIR gearbeitet: {fremd} Zeilen aus Messungen "
                f"und Proben. Sage genau das, in einem Satz, und erzaehle "
                f"die Messungen NICHT als seine Nacht. Er hat nicht mit mir "
                f"geredet, und er hat nichts entschieden.")[:hoechstens]

    z = _angaben(g, fremd, jetzt)
    kopf = ("Das ist die Auswahl aus der Nacht - geprueft, nicht das ganze "
            "Journal. Berichte daraus und zaehle KEINE Dateiaenderungen und "
            "keine Dienste auf; was hier nicht steht, war nicht wichtig.")
    return (kopf + "\n" + "\n".join(z))[:hoechstens]


def _angaben(g: dict, fremd: int, jetzt: float) -> list[str]:
    """Die Angaben selbst - eine Zeile je Sache, ohne Anleitung."""
    z: list[str] = []
    # ZUERST, was fertig geworden ist. Das Journal sagt sonst nur, was auffiel
    # - und eine Nacht, in der etwas fertig wurde, klingt dann wie eine, in
    # der nur etwas aufgefallen ist. Der Beleg steht in der Zeile: ohne ihn
    # ist ein Abschluss eine Behauptung, die ein Modell jederzeit selbst
    # bilden kann.
    if g.get("abschluss"):
        import abschluss as _abschluss
        z.append("Fertig geworden ist:")
        for zeile in _abschluss.saetze(g["abschluss"]):
            z.append(f"  {zeile}")
    if g["pruefung"]:
        letzte = g["pruefung"][-1]
        # Die Uhrzeiten ALLE nennen, nicht die Anzahl plus die letzte. Aus
        # "lief 2 Mal, zuletzt 02:03" machte gpt-oss "zwei Ueberpruefungen um
        # 02:03" - eine Zahl neben einer Uhrzeit wird zu einer Zahl VON
        # Uhrzeiten. Stehen beide Zeiten da, ist daraus nichts zu machen.
        wann = ", ".join(_uhr(e) for e in g["pruefung"])
        z.append(f"Die naechtliche Gegenpruefung lief um {wann}. "
                 f"Zuletzt, um {_uhr(letzte)}: {letzte.get('text')}")
    else:
        z.append("Die naechtliche Gegenpruefung ist NICHT gelaufen - sie ist "
                 "ab 2 Uhr faellig. Das ist selbst ein Befund.")

    for e in g["vorgelegt"]:
        z.append(f"{_uhr(e)} vorgelegt: {str(e.get('text'))[:140]}")
    for e in g["rueckfrage"]:
        z.append(f"{_uhr(e)} ich brauche eine Antwort auf: "
                 f"{str(e.get('text'))[:140]}")

    if g["ableiten_trocken"]:
        z.append(f"Im Trockenlauf haette ich {len(g['ableiten_trocken'])} "
                 f"Satz/Saetze angelegt - angelegt ist keiner:")
        for e in g["ableiten_trocken"]:
            satz = str(e.get("text") or "")
            satz = satz[14:].strip(" -") if satz.startswith("WUERDE anlegen") else satz
            z.append(f"  {_uhr(e)} {satz[:130]}")
    if g["ableiten_zurueck"]:
        z.append(f"{len(g['ableiten_zurueck'])} Satz/Saetze habe ich "
                 f"zurueckgehalten - absichtlich, das ist kein Fehler.")

    if g["sitzung"]:
        z.append(f"{len(g['sitzung'])} Gespraeche habe ich zusammengefasst:")
        for e in g["sitzung"]:
            z.append(f"  {_uhr(e)} {str(e.get('text'))[:130]}")

    # Der Verlust gehoert in JEDE Nachtauskunft, solange er gilt: Eine Probe
    # hat am 12.09. gegen 21:00 die Werkstatt geloescht, und was die
    # Spiegelung nicht zurueckbrachte, fehlt weiter.
    if g["verlust"]:
        z.append(f"Aus dem Verlust vom 12.09.: "
                 f"{str(g['verlust'][-1].get('text'))[:200]}")
    if g["kernwissen_fehlt"]:
        z.append("Mein Kernwissen (ERINNERUNG.md) fehlt seitdem und geht in "
                 "keinen Prompt mehr mit - ich kann es nicht wiederherstellen, "
                 "nur melden.")

    if g["bestand"]:
        z.append(f"{len(g['bestand'])} Erkenntnisse ueber den Rechner kamen "
                 f"dazu.")
    if g["fehler"]:
        letzter = max(float(e.get("ts") or 0) for e in g["fehler"])
        z.append(f"{len(g['fehler'])} Fehler, der letzte vor "
                 f"{(jetzt - letzter) / 3600:.1f} Stunden.")

    # Auch wenn BEIDES da war, wird die zweite Haelfte genannt - aber als das,
    # was sie ist, und nicht als Teil seiner Nacht.
    if fremd:
        z.append(f"Daneben wurde an mir gearbeitet ({fremd} Zeilen aus "
                 f"Messungen und Proben). Das gehoert NICHT zu seiner Nacht - "
                 f"nenne es nur, wenn er danach fragt.")
    return z


def _trockenzeile(e: dict) -> None:
    """Ein Satz, den C anlegen wuerde - mit der Herkunft daneben.

    Getrennt von main(), damit die Herkunftszeile einzeln pruefbar ist. Sie
    ist es, woran Calvin ueber ABLEITEN_SCHARF entscheidet, und sie hat sich
    schon einmal geirrt.
    """
    # "WUERDE anlegen - termin: ... (am 13.09. 10:00)"
    satz = str(e.get("text") or "")
    satz = satz[14:] if satz.startswith("WUERDE anlegen") else satz
    print(f"\n  {_uhr(e)}  {satz}")
    woraus = str(e.get("woraus") or "")
    wort = str(e.get("wann_wort") or "")
    # DREI Faelle, nicht zwei. "Keine Frage gefunden" und "es gab keine Frage"
    # sehen in der Zeile gleich aus und heissen das Gegenteil: das eine ist
    # ein Mangel der Zuordnung, das andere ihr richtiges Ergebnis. Ein
    # Dateifund kommt aus einer Ansprache, die `ableitbar()` mit Absicht
    # wegwirft - ihm eine Frage zu suchen waere sinnlos, und "nicht
    # zuordenbar" daneben sieht wie ein Fehler aus, wo keiner ist.
    #
    # Und fehlt `woraus_art` ganz, ist die Zeile aelter als das Feld. Dann
    # weiss der Bericht es nicht und sagt das. Ein fehlendes Feld ist kein
    # leeres Ergebnis - die beiden Zeilen vom 12.09. hat er genau so als
    # Fehler gemeldet, und es war keiner.
    art = str(e.get("woraus_art") or "")
    if woraus:
        print(f"          aus: \"{woraus[:62]}\"")
    elif art == "zusammenfassung":
        print("          aus: einer Beobachtung, nicht aus einem Gespraech")
        print("               (die Sitzung hatte keine brauchbare Frage)")
    elif art:
        print("          aus: (die Frage liess sich nicht zuordnen)")
    else:
        print("          aus: (unbekannt - diese Zeile ist aelter als das")
        print("               Feld; der Wortlaut steht in der Sitzung)")
    if wort:
        print(f"          das Zeitwort war: \"{wort}\"")


def main() -> int:
    stunden = STUNDEN
    if "--stunden" in sys.argv:
        stunden = float(sys.argv[sys.argv.index("--stunden") + 1])
    jetzt = time.time()
    g = gruppen(stunden, jetzt)
    pruefungen = g["pruefung"]
    vorgelegt = g["vorgelegt"]
    trocken = g["ableiten_trocken"]
    zurueck = g["ableiten_zurueck"]
    rueckfragen = g["rueckfrage"]
    sitzungen = g["sitzung"]
    bestand = g["bestand"]
    fehler = g["fehler"]

    breit = 72
    print("=" * breit)
    print(f"DIE NACHT  -  {time.strftime('%a %d.%m., %H:%M', time.localtime(jetzt))}"
          f"   (die letzten {stunden:g} Stunden)")
    print("=" * breit)

    if not pruefungen:
        print("\nDie Pruefung ist NICHT gelaufen. Sie ist ab 2 Uhr faellig,")
        print("einmal je Nacht - laeuft der Bewohner durch, steht hier morgen")
        print("frueh eine Zeile. Steht sie auch dann nicht da, hat der Faden")
        print("ein Problem, und das waere der erste Befund.")
    else:
        for e in pruefungen:
            print(f"\n{_uhr(e)}  {e.get('text')}")

    print(f"\nWAS C ANGELEGT HAETTE  ({len(trocken)})")
    print("  Jeder Satz mit der Frage, aus der er stammt. C laeuft im")
    print("  Trockenlauf - nichts davon steht im Gedaechtnis.")
    if not trocken:
        print("\n  nichts - keine Sitzung hatte etwas, das bleiben soll")
    for e in trocken:
        _trockenzeile(e)
    if trocken:
        print("\n  Das ist die Entscheidung: Stehen die Saetze oben richtig da,")
        print("  kann ABLEITEN_SCHARF=1 gesetzt werden - dann entstehen sie")
        print("  wirklich. Steht einer falsch, bleibt der Schalter aus, und")
        print("  der Satz sagt, woran es liegt.")

    if rueckfragen:
        print(f"\nWORAUF ER EINE ANTWORT BRAUCHT  ({len(rueckfragen)})")
        for e in rueckfragen:
            print(f"  {str(e.get('text'))[:66]}")

    if vorgelegt:
        print(f"\nWAS DIE PRUEFUNG VORLEGT  ({len(vorgelegt)})")
        for e in vorgelegt:
            print(f"  {str(e.get('text'))[:66]}")

    if zurueck:
        print(f"\nZURUECKGEHALTEN  ({len(zurueck)})  - absichtlich, kein Fehler")
        for e in zurueck[:6]:
            print(f"  {str(e.get('text'))[:66]}")
        if len(zurueck) > 6:
            print(f"  ... und {len(zurueck) - 6} weitere")

    print(f"\nSONST  -  {len(sitzungen)} Gespraeche zusammengefasst, "
          f"{len(bestand)} Erkenntnisse ueber den Rechner, "
          f"{len(fehler)} Fehler")
    if fehler:
        # Das ALTER gehoert daneben. Vierzehn Fehler sehen schlimm aus; vierzehn
        # Fehler aus einer Stunde, die acht Stunden her ist, sind Geschichte.
        # Ohne diese Zeile muesste Calvin die Zeitstempel selbst vergleichen.
        letzter = max(float(e.get("ts") or 0) for e in fehler)
        alter_h = (jetzt - letzter) / 3600
        stunden = {_uhr(e)[:2] for e in fehler}
        print(f"  der letzte vor {alter_h:.1f} Stunden, alle aus "
              f"{len(stunden)} Stunde{'n' if len(stunden) != 1 else ''} "
              f"({', '.join(sorted(stunden))} Uhr)")
        if alter_h > 2:
            print("  -> nichts Laufendes. Sie stehen hier, weil das Fenster "
                  "so weit zurueckreicht.")
        for e in fehler[-3:]:
            print(f"  {_uhr(e)}  {str(e.get('text'))[:60]}")

    print("=" * breit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
