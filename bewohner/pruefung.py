"""D - die naechtliche Gegenpruefung. Sie legt vor, statt zu handeln.

    python -X utf8 pruefung.py              Trockenlauf: nur zeigen
    python -X utf8 pruefung.py --echt       korrigiert, was eindeutig ist
    python -X utf8 pruefung.py --jetzt      ohne auf die Stunde zu warten

WARUM EIN EIGENER FADEN UND NICHT AM RUECKBLICK: Der Rueckblick laeuft ab 5
Uhr (rueckblick.STUNDE_AB). Calvin nennt 2 bis 3 Uhr. Drei Stunden sind kein
Rundungsfehler.

DREI STUFEN, UND NUR DIE ERSTE GESCHIEHT VON SELBST (D.4):

  1  selbst korrigieren, wo es eindeutig ist und nichts verlorengeht:
     liegengebliebene Zusammenfassung nachholen, Dublette ueberholen,
     abgelaufenen Termin als verpasst markieren
  2  zurueckhalten und VORLEGEN, wo es um Inhalt geht: Widersprueche,
     Verdacht auf vergessene Termine, Fakten, die er selbst fuer falsch haelt.
     EIN Redeanlass am Morgen, nicht fuenf Pushes um drei Uhr nachts
  3  nichts loeschen. Nie. `ersetzt_durch` haelt die Geschichte, und die Suche
     ueberspringt Ueberholtes von allein

FUENF VON SECHS PRUEFUNGEN KOSTEN KEIN MODELL. Das ist Absicht: Was ohne
Modell geht, soll ohne Modell gehen - dann ist nachlesbar, WARUM etwas
beanstandet wurde, und die Nacht haengt nicht an einer Leitung.

DAS FENSTER (B8 des Mac): die letzten 26 Stunden ODER alles, was noch
`geprueft: null` traegt. Die 26 Stunden allein sind ein Leck - war der Bewohner
zwei Tage aus, fielen Sitzungen fuer immer heraus. Marken anlegen und nicht
auswerten ist schlimmer als keine Marken: Es sieht nach Vollstaendigkeit aus.
Gedeckelt auf PRUEFUNG_JE_NACHT, damit ein Rueckstand von zwei Wochen nicht
eine Nacht lang das Modell belegt; der Rest bleibt null und kommt morgen dran,
und das Journal nennt den Rueckstand.

EIN VORGELEGTER BEFUND KOMMT NICHT WIEDER, bis sich sein Gegenstand aendert
(B7). "Ich war gestern beim Arzt" enthaelt ein Zeitwort und ist kein Termin -
es wird also nie angelegt, bleibt also jede Nacht ein Verdacht und waere jeden
Morgen neu vorgelegt. Eine Pruefung, die jeden Morgen dasselbe meldet, wird
abgeschaltet, und dann prueft nichts mehr. Die Marke haengt darum am
GEGENSTAND (Sitzung und Stelle), nicht am Wortlaut des vorgelegten Satzes -
sonst gilt derselbe Verdacht als neu, sobald das Modell ihn anders formuliert.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"
MARKE = WERKSTATT / "_pruefung_zuletzt"
ZUSTAND = WERKSTATT / "pruefung.json"

# Das Fenster der Nacht, einmal je Tag. Calvin nennt 2 bis 3 Uhr.
#
# ES BRAUCHT BEIDE GRENZEN, und das hat der Nachtbericht sofort gezeigt: Mit
# `if stunde < STUNDE_AB: return False` allein war sie von 2 Uhr bis Mitternacht
# faellig - gelaufen ist sie darum um 23:40, nicht in der Nacht. Beim
# Rueckblick ist dasselbe Muster richtig, weil er eine MORGEN-Aufgabe ist ("ab
# 5 Uhr"); eine Nachtaufgabe braucht ein Ende.
#
# Oben bei 5: dort faengt der Rueckblick an, und zwei Modellaufrufe zur
# gleichen Zeit waeren zwei, die aufeinander warten.
STUNDE_AB = 2
STUNDE_BIS = 5
# Und so lange gilt ein Lauf als "heute schon gewesen".
ABSTAND_S = 20 * 3600

# Das Fenster. 26 Stunden, damit ein Gespraech von 23:40 zum Tag davor gehoert
# und nicht bei Mitternacht zerteilt wird.
FENSTER_H = 26
# Hoechstens so viele Sitzungen je Nacht. Die Zahl ist eine erste Setzung und
# wird nach der ersten Nacht MIT Rueckstand messbar - dann steht sie hier mit
# einer Begruendung statt mit einer Schaetzung.
PRUEFUNG_JE_NACHT = 12

# Ab dieser Ueberdeckung gelten zwei Fakten als dasselbe. Dieselbe Schwelle wie
# gedaechtnis.UEBERDECKUNG, und aus demselben Grund an einer Stelle geholt.
try:
    import gedaechtnis
    DUBLETTE_AB = gedaechtnis.UEBERDECKUNG
except Exception:                                      # pragma: no cover
    DUBLETTE_AB = 0.85


def faellig(jetzt: float | None = None) -> bool:
    """Einmal je Nacht, und erst wenn die Stunde da ist.

    Dieselbe Bauart wie rueckblick.faellig() - damit ein Neustart um 2:30 sie
    nicht zweimal laufen laesst.
    """
    jetzt = time.time() if jetzt is None else jetzt
    if not (STUNDE_AB <= time.localtime(jetzt).tm_hour < STUNDE_BIS):
        return False
    try:
        return (jetzt - float(MARKE.read_text(encoding="utf-8").strip())
                ) > ABSTAND_S
    except (OSError, ValueError):
        return True


def _marke_setzen(jetzt: float) -> None:
    WERKSTATT.mkdir(parents=True, exist_ok=True)
    MARKE.write_text(str(jetzt), encoding="utf-8")


# ------------------------------------------------------- Was schon vorlag


def _zustand() -> dict:
    try:
        return json.loads(ZUSTAND.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _zustand_schreiben(d: dict) -> None:
    WERKSTATT.mkdir(parents=True, exist_ok=True)
    t = ZUSTAND.with_suffix(".json.tmp")
    t.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(t, ZUSTAND)


def gegenstand(befund: dict) -> str:
    """Woran ein Befund haengt - NICHT an seinem Wortlaut.

    Haengt die Marke am Satz, gilt derselbe Verdacht als neu, sobald das Modell
    ihn anders formuliert, und die Pruefung konvergiert nie. Dasselbe Problem
    hat rueckblick._kurz() schon einmal geloest.
    """
    return f"{befund.get('art')}:{befund.get('sid') or ''}:{befund.get('woran') or ''}"


# -------------------------------------------------- Pruefungen ohne Modell


def _zahlen(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", str(text or "")))


def liegengeblieben(koepfe: list[dict]) -> list[dict]:
    """Marken, die offen stehen: geschlossen ohne Zusammenfassung, oder
    zusammengefasst ohne Ableitung (D.2.1). Ohne Modell erkennbar."""
    heraus = []
    for k in koepfe:
        if not k.get("geschlossen"):
            continue
        if k.get("zusammenfassung") is None:
            heraus.append({"art": "ohne_zusammenfassung", "sid": k["id"],
                           "woran": "zusammenfassung",
                           "text": f"Sitzung {k['id']} ist geschlossen, aber "
                                   f"nicht zusammengefasst."})
        elif k.get("abgeleitet") is None:
            heraus.append({"art": "ohne_ableitung", "sid": k["id"],
                           "woran": "abgeleitet",
                           "text": f"Sitzung {k['id']} ist zusammengefasst, "
                                   f"aber nichts daraus abgeleitet."})
    return heraus


def dubletten(fakten: list[dict]) -> list[dict]:
    """Zwei Fakten, deren Text sich stark gleicht. Die JUENGERE wird ueberholt,
    nicht die aeltere - die aeltere hat die Geschichte."""
    import gedaechtnis
    heraus = []
    nach_alter = sorted(fakten, key=lambda f: f["id"])
    for i, alt in enumerate(nach_alter):
        kern = gedaechtnis._inhaltswoerter(alt["text"])
        if not kern:
            continue
        for jung in nach_alter[i + 1:]:
            if jung.get("_weg"):
                continue
            if gedaechtnis.traegt_weiter(kern, jung["text"]):
                jung["_weg"] = True
                heraus.append({"art": "dublette", "sid": "",
                               "woran": f"{alt['id']}<{jung['id']}",
                               "alt": alt["id"], "jung": jung["id"],
                               "text": f"{jung['id']} sagt dasselbe wie "
                                       f"{alt['id']}: {jung['text'][:70]}"})
    return heraus


def abgelaufene_termine(erinnerungen: list[dict],
                        jetzt: float) -> list[dict]:
    """`wann` in der Vergangenheit und nie gemeldet. Als verpasst markieren,
    nicht loeschen - Calvin soll sehen, was er verpasst hat."""
    heraus = []
    for e in erinnerungen:
        # `wann` ist ein ISO-Text, kein Zeitstempel - so schreibt erinnern es.
        try:
            wann = datetime.fromisoformat(str(e.get("wann"))).timestamp()
        except (TypeError, ValueError):
            continue
        # "nie gemeldet" heisst `not erledigt`: faellige() setzt die Marke,
        # sobald es den Termin EINMAL gemeldet hat. Steht sie nicht, war der
        # Prozess zu der Zeit aus.
        if wann >= jetzt or e.get("erledigt"):
            continue
        heraus.append({"art": "verpasst", "sid": "",
                       "woran": str(e.get("id") or e.get("wann")),
                       "id": e.get("id"), "wann": e.get("wann"),
                       "text": f"Der Termin \"{str(e.get('text'))[:54]}\" war "
                               f"am {datetime.fromtimestamp(wann):%d.%m. %H:%M}"
                               f" und wurde nie gemeldet."})
    return heraus


def fakten_mit_mangel(fakten: list[dict], wortlaute: dict) -> list[dict]:
    """mangel() NACHTRAEGLICH angewandt, und die erfundene Zahl dazu.

    Beides ohne Modell: Ein Fakt ueber ihn selbst ("Ich kann den Bildschirm
    sehen") und eine Zahl, die im Wortlaut der Sitzung nicht vorkommt.
    """
    import wissen
    heraus = []
    for f in fakten:
        quelle = wortlaute.get(f.get("quelle") or "", "")
        grund = wissen.mangel(f["text"], quelle or f["text"])
        if grund and "Zahlen" not in grund:
            heraus.append({"art": "fakt_mangelhaft", "sid": "",
                           "woran": str(f["id"]), "id": f["id"],
                           "text": f"{f['id']}: {grund} - {f['text'][:60]}"})
            continue
        if quelle:
            erfunden = _zahlen(f["text"]) - _zahlen(quelle)
            if erfunden:
                heraus.append({"art": "zahl_erfunden", "sid": "",
                               "woran": str(f["id"]), "id": f["id"],
                               "text": f"{f['id']} nennt "
                                       f"{sorted(erfunden)}, was im Wortlaut "
                                       f"nicht steht: {f['text'][:54]}"})
    return heraus


def termin_verdacht(koepfe: list[dict], paare_von, hat_termin) -> list[dict]:
    """Ein Zeitwort im Wortlaut, aber kein Termin aus dieser Sitzung (D.2.3).

    VERDACHT, nicht Befund: "Ich war gestern beim Arzt" enthaelt ein Zeitwort
    und ist kein Termin. Darum wird er vorgelegt und nicht angelegt - und darum
    braucht er die Marke `vorgelegt`, sonst kommt er jede Nacht wieder.
    """
    import zeitwort
    heraus = []
    for k in koepfe:
        if hat_termin(k["id"]):
            continue
        for i, p in enumerate(paare_von(k["id"])):
            # NUR Calvins Seite. Ein Termin ist etwas, das ER nennt - und der
            # erste Trockenlauf hat genau daran einen Fehlalarm geliefert:
            # "Ich habe eine neue Datei cpu-z_2.17-en.exe, 4629 KB, am 21:06
            # Uhr im Download-Ordner gefunden" ist SEIN eigener Satz, und das
            # "am 21:06 Uhr" darin ein Zeitpunkt in einem Bericht, kein
            # Termin. Eine Ansprache hat `frage: null` und faellt damit von
            # allein heraus.
            text = str(p.get("frage") or "")
            if not text or not zeitwort.findet(text):
                continue
            bezug = datetime.fromtimestamp(p.get("ts") or time.time())
            wann, grund = zeitwort.aufloesen(text, bezug)
            if wann is None:
                # "gestern" ist kein vergessener Termin, sondern keiner.
                continue
            heraus.append({
                "art": "termin_verdacht", "sid": k["id"], "woran": f"paar{i}",
                "text": f"In Sitzung {k['id']} steht ein Zeitwort "
                        f"({wann:%d.%m. %H:%M}), aber kein Termin wurde "
                        f"angelegt: {text[:58]}"})
            break
    return heraus


# ----------------------------------------------------------------- Durchgang


def _sitzungen_im_fenster(jetzt: float, deckel: int) -> tuple[list[dict], int]:
    """Die letzten FENSTER_H Stunden ODER alles mit `geprueft: null` (B8)."""
    import sitzung
    alle = sitzung.lesen()
    seit = jetzt - FENSTER_H * 3600
    dran = [k for k in alle
            if k.get("geprueft") is None
            or (k.get("geschlossen") or 0) >= seit]
    dran.sort(key=lambda k: k.get("begonnen") or 0)
    rueckstand = max(0, len(dran) - deckel)
    return dran[:deckel], rueckstand


def durchgang(jetzt: float | None = None, scharf: bool = False,
              journal=None, deckel: int | None = None) -> dict:
    """Einmal pruefen. Korrigiert nur, was eindeutig ist; der Rest wird
    vorgelegt."""
    import sitzung
    jetzt = time.time() if jetzt is None else jetzt
    deckel = PRUEFUNG_JE_NACHT if deckel is None else deckel

    # ZUERST offene Sitzungen schliessen. Um 2 Uhr ist jede Sitzung mit
    # `letzte_frage` aelter als RUHE_MIN zu Ende, auch wenn der Faden aus B
    # sie verpasst hat.
    geschlossen = 0
    while True:
        kopf = sitzung.faellig(jetzt)
        if kopf is None:
            break
        sitzung.schliessen(kopf["id"], jetzt)
        geschlossen += 1
        if geschlossen > 50:
            break

    koepfe, rueckstand = _sitzungen_im_fenster(jetzt, deckel)
    wortlaute = {f"Sitzung {k['id']}": " ".join(
        " ".join(str(p.get(s) or "") for s in ("frage", "antwort"))
        for p in sitzung.paare(k["id"])) for k in koepfe}

    fakten, erinnerungen = _langzeit_lesen()

    befunde: list[dict] = []
    befunde += liegengeblieben(koepfe)
    befunde += dubletten(fakten)
    befunde += abgelaufene_termine(erinnerungen, jetzt)
    befunde += fakten_mit_mangel(fakten, wortlaute)
    befunde += termin_verdacht(
        koepfe, lambda sid: sitzung.paare(sid),
        lambda sid: any(str(e.get("quelle") or "").endswith(sid)
                        for e in erinnerungen))

    # Was schon vorlag, kommt nicht wieder (B7).
    z = _zustand()
    gesehen = dict(z.get("vorgelegt") or {})
    neu = [b for b in befunde if gegenstand(b) not in gesehen]
    schon = len(befunde) - len(neu)

    # Stufe 1: selbst korrigieren, wo es eindeutig ist.
    getan = {"nachgeholt": 0, "ueberholt": 0, "verpasst": 0}
    if scharf:
        getan = _korrigieren(neu, journal)

    # Stufe 2: der Rest wird VORGELEGT - einer, nicht fuenf.
    vorzulegen = [b for b in neu if b["art"] in (
        "termin_verdacht", "fakt_mangelhaft", "zahl_erfunden")]
    if scharf:
        for b in neu:
            gesehen[gegenstand(b)] = jetzt
        z["vorgelegt"] = gesehen
        z["zuletzt"] = jetzt
        _zustand_schreiben(z)
        for k in koepfe:
            sitzung.marke_setzen(k["id"], "geprueft", jetzt)

    bericht = {"geprueft": len(koepfe), "geschlossen": geschlossen,
               "rueckstand": rueckstand, "befunde": len(befunde),
               "neu": len(neu), "schon_vorgelegt": schon,
               "vorzulegen": [b["text"] for b in vorzulegen],
               "scharf": bool(scharf), **getan}

    if journal:
        # Die Zahlen gehoeren ins Journal. Ohne sie merkt niemand, wenn die
        # Pruefung aufhoert zu wirken - derselbe Grund, aus dem passiert.py
        # sagt, dass es ausgewaehlt hat.
        journal("pruefung",
                f"{bericht['geprueft']} Sitzungen geprueft, "
                f"{geschlossen} nachtraeglich geschlossen, "
                f"{bericht['neu']} neue Befunde "
                f"({schon} lagen schon vor), "
                f"{getan['nachgeholt']} nachgeholt, "
                f"{getan['ueberholt']} ueberholt, "
                f"{getan['verpasst']} als verpasst markiert"
                + (f", Rueckstand {rueckstand}" if rueckstand else ""),
                nicht_erinnern=True)
        for b in vorzulegen:
            journal("vorgelegt", b["text"], nicht_erinnern=True)
    return bericht


def _langzeit_lesen() -> tuple[list[dict], list[dict]]:
    """Fakten aus dem Gedaechtnis, Termine aus erinnern."""
    fakten: list[dict] = []
    try:
        import gedaechtnis
        with gedaechtnis._verbindung() as v:
            fakten = [{"id": int(i), "text": str(t), "quelle": str(q or "")}
                      for i, t, q in v.execute(
                          "SELECT id, text, quelle FROM erinnerung "
                          "WHERE art='fakt' AND ersetzt_durch IS NULL "
                          "ORDER BY id")]
    except Exception:
        pass
    erinnerungen: list[dict] = []
    try:
        erinnerungen = list(_erinnern().lesen())
    except Exception:
        pass
    return fakten, erinnerungen


def _erinnern():
    """Das Werkzeug erinnern - es liegt in werkstatt/werkzeuge, nicht hier."""
    pfad = str(WERKSTATT / "werkzeuge")
    if pfad not in sys.path:
        sys.path.insert(0, pfad)
    import erinnern
    return erinnern


def _korrigieren(befunde: list[dict], journal) -> dict:
    """Stufe 1 - und NUR sie geschieht von selbst."""
    getan = {"nachgeholt": 0, "ueberholt": 0, "verpasst": 0}
    for b in befunde:
        try:
            if b["art"] == "ohne_zusammenfassung":
                import archiv
                archiv.abschliessen(b["sid"], journal=journal)
                getan["nachgeholt"] += 1
            elif b["art"] == "dublette":
                import gedaechtnis
                with gedaechtnis._sperre, gedaechtnis._verbindung() as v:
                    v.execute("UPDATE erinnerung SET ersetzt_durch=? "
                              "WHERE id=? AND ersetzt_durch IS NULL",
                              (b["alt"], b["jung"]))
                getan["ueberholt"] += 1
            elif b["art"] == "verpasst":
                # Als verpasst MARKIEREN, nicht loeschen - Calvin soll sehen,
                # was er verpasst hat. erinnern hat dafuer keine eigene
                # Funktion; die Liste ist die Schnittstelle.
                erinnern = _erinnern()
                liste = erinnern.lesen()
                for e in liste:
                    if (e.get("id") == b.get("id")
                            and str(e.get("wann")) == str(b.get("wann"))):
                        e["erledigt"] = True
                        e["verpasst"] = True
                        erinnern.schreiben(liste)
                        getan["verpasst"] += 1
                        break
        except Exception as f:
            if journal:
                journal("fehler",
                        f"Pruefung {b['art']}: {type(f).__name__}",
                        nicht_erinnern=True)
    return getan


def main() -> int:
    scharf = "--echt" in sys.argv
    jetzt = time.time()
    if not ("--jetzt" in sys.argv or faellig(jetzt)):
        print(f"nicht faellig (ab {STUNDE_AB} Uhr, einmal je Nacht).")
        return 0
    b = durchgang(jetzt, scharf=scharf)
    print(json.dumps(b, ensure_ascii=False, indent=1))
    if scharf:
        _marke_setzen(jetzt)
    else:
        print("\nTrockenlauf - nichts korrigiert, nichts vermerkt. "
              "Mit --echt wirklich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
