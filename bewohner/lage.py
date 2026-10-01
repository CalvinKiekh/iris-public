"""Lagebild — was gerade ist, ohne ein Modell zu fragen.

Uhrzeit, Tagesphase, Arbeitszeit, Rechner, Geraete im Heimnetz, wann Calvin
zuletzt gesprochen hat. Alles Messwerte. Ein Sprachmodell ist keine Uhr und
kein Netzwerkscanner - solche Fakten gehoeren eingesetzt, nicht erfragt.

Geschrieben wird nach `werkstatt\\lage.json`, laufend von einem eigenen Faden.
Aenderungen sind Ereignisse: ein Geraet kommt, ein Geraet geht.

Nur lesend. Es wird gepingt und die ARP-Tabelle gelesen, sonst nichts.
"""
from __future__ import annotations

from einstellungen import NAMENS
import json
import re
import shutil
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path

HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"
LAGE_DATEI = WERKSTATT / "lage.json"

TAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
        "Samstag", "Sonntag")


def _ohne_fenster(befehl: list[str], frist: int = 20) -> str:
    try:
        r = subprocess.run(befehl, capture_output=True, text=True, timeout=frist,
                           encoding="utf-8", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def tagesphase(j: datetime) -> str:
    h = j.hour
    if h < 5:
        return "Nacht"
    if h < 10:
        return "Morgen"
    if h < 13:
        return "Vormittag"
    if h < 17:
        return "Nachmittag"
    if h < 22:
        return "Abend"
    return "Nacht"


def ortszeit() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:
        return datetime.now().astimezone()


NAMEN_DATEI = WERKSTATT / "geraete.json"


def namen() -> dict:
    """mac -> Name. Pflegt Calvin in der App. Nichts wird erfunden."""
    try:
        return json.loads(NAMEN_DATEI.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def nenne(g: dict) -> str:
    """Wie ein Gerät heißt - Name, sonst Hostname, sonst die Adresse."""
    return g.get("name") or g.get("hostname") or f"das Gerät {g.get('ip')}"


def _hostname(ip: str) -> str:
    """Reverse-DNS, ohne das Netz abzutasten - fragt nur den Namensdienst."""
    try:
        return socket.gethostbyaddr(ip)[0].split(".")[0]
    except (OSError, socket.herror, socket.gaierror):
        return ""


def geraete() -> list[dict]:
    """Wer ist im Heimnetz? Aus der ARP-Tabelle - nur lesen, nichts anfassen.

    Die Tabelle zeigt, mit wem dieser Rechner zuletzt gesprochen hat. Das ist
    kein vollstaendiger Scan des Netzes, aber es genuegt, um zu sehen, ob ein
    bekanntes Geraet da ist oder fehlt - und es klopft an keine fremde Tuer.
    """
    roh = _ohne_fenster(["arp", "-a"], 20)
    gefunden = []
    for zeile in roh.splitlines():
        t = re.match(r"\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})\s+(\w+)",
                     zeile)
        if not t:
            continue
        adresse, mac, art = t.group(1), t.group(2).lower(), t.group(3).lower()
        # Rundruf- und Mehrfachadressen sind keine Geraete.
        if art != "dynamisch" and art != "dynamic":
            continue
        if adresse.endswith(".255") or mac.startswith(("ff-", "01-00-5e")):
            continue
        gefunden.append({"ip": adresse, "mac": mac})

    # Namen dazu: erst Calvins Liste, dann Reverse-DNS. Kein aktiver Scan.
    bekannt = namen()
    vorher = {g["mac"]: g for g in (lesen().get("netz") or [])}
    for g in gefunden:
        alt = vorher.get(g["mac"], {})
        g["name"] = bekannt.get(g["mac"], "")
        g["hostname"] = alt.get("hostname") or _hostname(g["ip"])
        g["seit"] = alt.get("seit") or time.time()
        g["gesehen"] = int(alt.get("gesehen", 0)) + 1
        g["fehlt"] = 0
        g["war_weg"] = bool(alt.get("fehlt", 0) >= FEHLT_BIS_WEG)

    # Wer diesmal fehlt, wird nicht sofort gestrichen - nur hochgezaehlt.
    da = {g["mac"] for g in gefunden}
    for mac, alt in vorher.items():
        if mac in da:
            continue
        alt = dict(alt)
        alt["fehlt"] = int(alt.get("fehlt", 0)) + 1
        alt["gesehen"] = 0
        if alt["fehlt"] < FEHLT_BIS_WEG:
            gefunden.append(alt)      # gilt noch als anwesend
    return sorted(gefunden, key=lambda g: g["mac"])


def rechner() -> dict:
    gesamt, benutzt, frei = shutil.disk_usage("C:\\")
    return {"platte_frei_gb": frei // 1024 ** 3,
            "platte_gesamt_gb": gesamt // 1024 ** 3,
            "name": socket.gethostname()}


def selbstbild() -> dict:
    """Die Messwerte über sich selbst gehören ins Lagebild - er soll sehen
    können, wie es ihm geht, wie er sieht, wie viel Platz frei ist."""
    try:
        import selbst
        b = selbst.lagebild()
        return {"tempo_tok_s": b.get("tempo"), "ollama": b.get("ollama"),
                "waisen": len(b.get("waisen") or []),
                "ticks_je_minute": b.get("ticks_je_minute"),
                "gpu": b.get("gpu") or []}
    except Exception:
        return {}


def lesen() -> dict:
    try:
        return json.loads(LAGE_DATEI.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def bauen(regeln_arbeitszeit=None, zuletzt_gesprochen: float | None = None) -> dict:
    j = ortszeit()
    return {
        "ts": time.time(),
        "uhrzeit": j.strftime("%H:%M"),
        "wochentag": TAGE[j.weekday()],
        "datum": j.strftime("%d.%m.%Y"),
        "tagesphase": tagesphase(j),
        "arbeitszeit": bool(regeln_arbeitszeit) if regeln_arbeitszeit is not None
                       else None,
        "rechner": rechner(),
        # Vertragsgemäß: "netz" und "calvin_zuletzt" als Zeitpunkt.
        "netz": geraete(),
        "nutzer_zuletzt": zuletzt_gesprochen,
        "selbst": selbstbild(),
    }


def schreiben(bild: dict) -> None:
    WERKSTATT.mkdir(parents=True, exist_ok=True)
    vorlaeufig = LAGE_DATEI.with_suffix(".json.tmp")
    vorlaeufig.write_text(json.dumps(bild, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    vorlaeufig.replace(LAGE_DATEI)


# Erst nach so vielen Messungen in Folge gilt ein Gerät als weg bzw. als neu.
# Die ARP-Tabelle laesst Eintraege altern: Ein Handy "verschwindet" und ist
# zwei Minuten spaeter wieder da, ohne dass jemand das Haus verlassen haette.
# Ohne diese Schwelle fuellt das Heimnetz das Gedaechtnis mit Rauschen.
FEHLT_BIS_WEG = 3


def unterschiede(alt: dict, neu: dict) -> list[str]:
    """Was hat sich geaendert? Nur Dinge, die ein Ereignis wert sind.

    Uhrzeit aendert sich staendig - das ist kein Ereignis. Ein Geraet, das
    wirklich kommt oder geht, schon. "Wirklich" heisst: mehrere Messungen
    lang, nicht ein einzelnes Aussetzen der ARP-Tabelle.

    Die Ankunft war bis zum 12.09.2026 unerreichbar. Sie verlangte

        mac not in alte and gesehen >= DA_BIS_NEU and war_weg

    und das sind drei Bedingungen, von denen keine zwei zugleich wahr werden
    koennen: Wer gerade auftaucht, hat gesehen == 1; beim zweiten Mal steht er
    schon in alte. Und war_weg war immer False, weil geraete() einen Eintrag
    wegwirft, sobald fehlt >= FEHLT_BIS_WEG - ein gespeicherter Eintrag
    erreicht diesen Wert nie, und ein zurueckkehrendes Geraet findet gar
    keinen alten mehr vor. In 1603 Journalzeilen stand deshalb kein einziges
    Geraet.

    Die Entprellung steckt bereits in "mac not in alte": Ein Geraet faellt
    erst nach drei Fehlmessungen aus der Liste, ein einzelnes Aussetzen der
    ARP-Tabelle laesst es drin. Die zwei Zusatzbedingungen haben die Schwelle
    nicht verschaerft, sondern abgeschaltet.

    Was gefehlt hat, ist der erste Blick: Ohne Vorgaenger ist jedes Geraet
    "neu" und er meldete beim ersten Start das ganze Haus. Dieselbe Regel wie
    Beobachter.letzter is None - der erste Blick stellt fest, er vergleicht
    nicht.

    Erstmals-gesehen und Rueckkehr kann er NICHT unterscheiden: Von einem
    Geraet, das lange weg war, ist kein Eintrag mehr da. Darum "aufgetaucht"
    und nicht "wieder da" - das waere eine Behauptung ueber ein Vorher, das
    er nicht mehr hat.
    """
    raus = []
    # "netz" ZUERST, und das war ein echter Fehler im Betrieb: Hier stand nur
    # `alt.get("geraete")`, waehrend bauen() das Feld als "netz" schreibt
    # (siehe dort, "Vertragsgemaess"). Damit sah unterschiede() IMMER zwei
    # leere Listen und konnte weder eine Ankunft noch einen Abschied melden.
    #
    # Aufgefallen ist es erst am 12.09., und zwar an lage_test.py - der Teil
    # war seit derselben Umbenennung tot und hat sein Scheitern als "Bewohner
    # laeuft nicht?" wegerklaert.
    #
    # geraete_test.py hat die Luecke NICHT gefunden, weil es seine Lagebilder
    # selbst baut und dabei denselben falschen Namen benutzt wie diese
    # Funktion. Der Test prueft die Logik, nie den Weg - derselbe Fehler wie
    # bei kann_test.py, das monatelang einen Aufruf mass, den es im Betrieb
    # nicht gibt.
    #
    # Und die Folge stand schon im Kopf von geraete_test.py, ohne dass jemand
    # sie mit dieser Zeile verbunden hat: "Calvin nennt 'ein Geraet im Netz,
    # das vorher nicht da war' als Redeanlass. In 1603 Journalzeilen stand nie
    # eines." Dort wurde eine Bedingung repariert; die Ursache war der Name.
    #
    # "geraete" bleibt als Rueckfall, damit ein gespeichertes Lagebild aus der
    # Zeit vor der Umbenennung noch gelesen wird.
    def _geraete(bild: dict) -> list:
        g = bild.get("netz")
        return g if g is not None else (bild.get("geraete") or [])

    alte = {g["mac"]: g for g in _geraete(alt)}
    neue = {g["mac"]: g for g in _geraete(neu)}
    wann = neu.get("uhrzeit", "")

    # Der erste Blick zaehlt nicht - sonst ist beim Start das ganze Haus neu.
    if alte:
        for mac, g in neue.items():
            if mac not in alte:
                raus.append(f"{wann} ist {nenne(g)} im Netz aufgetaucht")
    for mac, g in alte.items():
        if mac not in neue and g.get("fehlt", 0) >= FEHLT_BIS_WEG:
            raus.append(f"{wann} ist {nenne(g)} nicht mehr da")

    if alt.get("tagesphase") and alt["tagesphase"] != neu.get("tagesphase"):
        raus.append(f"{wann} begann der {neu['tagesphase']}")
    if alt.get("arbeitszeit") is not None and \
            alt["arbeitszeit"] != neu.get("arbeitszeit"):
        raus.append(f"{wann} " + (f"begann {NAMENS} Arbeitszeit"
                                  if neu.get("arbeitszeit")
                                  else f"endete {NAMENS} Arbeitszeit"))
    return raus


# ------------------------------------------------------------ Dienstantworten


# DERSELBE DEFEKT WIE IN wissen._VERGAENGLICH, und er ist teuer bezahlt.
#
# Hier stand `(im|am)\s*(netz|wlan)`. Nach "im" musste unmittelbar "netz"
# folgen - "Wer ist im HEIMNETZ?" traf also nicht, und genau so fragt Calvin.
# Die Frage fiel durch und landete beim Modell, und das Modell erfand:
#
#   16:24  "Ich sehe vierzehn Geraete im Heimnetz, darunter PC, Drucker,
#           Tablet und Smartphone."     <- die Anzahl stimmte, die Namen nicht.
#                                          Echt sind fritz, iPhonevonCalvin,
#                                          Schlafzimmer, Mac, repeater...
#   17:2x  "Keine Geraete."             <- dieselbe Luecke, anderer Erfindung
#
# Beide Antworten waren erfunden; die erste sah nur richtig aus. Am 12.09.
# habe ich dieselbe Luecke in wissen.py geschlossen ("kannte nur 'im netz',
# nicht 'im Heimnetz'") und NICHT nachgesehen, ob sie woanders auch steht.
# Sie stand hier.
#
# Umlaute doppelt, wie bei HAUSFRAGE in gespraech.py: Die Frage kommt aus der
# Spracherkennung, und die schreibt mal "Geräte" und mal "Geraete".
NETZFRAGE = re.compile(
    r"(wer\s*ist\s*(gerade\s*)?(im|am)\s*(heim)?(netz(werk)?|wlan)|"
    r"wer\s*ist\s*(alles\s*)?(online|da)\b|"
    r"welche\s*ger(ä|ae)te|wie\s*viele\s*ger(ä|ae)te|"
    r"was\s*ist\s*(alles\s*)?im\s*(heim)?netz(werk)?|"
    r"ger(ä|ae)te\s*im\s*(heim)?netz(werk)?|"
    r"ist\s*(mein|das)\s*handy)", re.IGNORECASE)


def netz_antwort(frage: str) -> str | None:
    """Beantwortet Netzfragen aus dem Lagebild - ohne Modell, ohne Scan."""
    if not NETZFRAGE.search(frage):
        return None
    bild = lesen()
    g = bild.get("netz") or []
    if not g:
        return "Ich sehe gerade kein anderes Gerät im Netz."
    mit_namen = [nenne(x) for x in g if x.get("name") or x.get("hostname")]
    if not mit_namen:
        return f"{len(g)} Geräte sind im Netz, keines davon kenne ich beim Namen."
    if len(g) == len(mit_namen):
        return f"Im Netz sind {aufzaehlen_kurz(mit_namen)}."
    return (f"{len(g)} Geräte sind im Netz, darunter "
            f"{aufzaehlen_kurz(mit_namen)}.")


def aufzaehlen_kurz(namen_liste: list[str], hoechstens: int = 4) -> str:
    n = namen_liste[:hoechstens]
    rest = len(namen_liste) - len(n)
    text = ", ".join(n[:-1]) + f" und {n[-1]}" if len(n) > 1 else n[0]
    return f"{text} und {rest} weitere" if rest > 0 else text
