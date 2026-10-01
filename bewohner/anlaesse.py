"""Anlaesse - woraus er von sich aus etwas zu sagen hat.

Der `ansprache`-Faden hatte bis heute genau eine Quelle: `selbst.befunde()`,
also Stoerungen an ihm selbst. Laeuft die Maschine sauber, hat er nichts zu
sagen - und so stand im ganzen Journal keine einzige `ansprache`-Zeile. Es lag
nicht an den Grenzen (`ansprechen.darf()` sagte durchweg ja) und nicht am Weg
(die Bruecke macht aus jeder `ansprache` eine Push). Es lag am Anlass.

Dieses Modul sammelt Anlaesse aus dem, was er ohnehin wahrnimmt:

    neu_gesehen   eine Datei, die er verstanden hat; ein Geraet, das vorher
                  nicht im Netz war
    fertig        etwas ist fertig geworden, das Calvin angestossen hat
    gelernt       er kann etwas Neues; oder ihm fehlt etwas, das nur Calvin
                  besorgen kann
    frage         ein Antrag liegt und niemand hat entschieden
    muster        etwas ueber Stunden oder Tage, das ohne ihn niemand sieht

WAS ER SAGT, steht hier nicht. Ein Anlass ist eine Messung mit Kontext; den
Satz formuliert er selbst. Hart verdrahtete Saetze waeren keine Ansprache,
sondern eine Meldung mit seinem Namen darunter.

Wie `selbst.py`: nur Messwerte, kein Modell, kein Netz, nur Standardbibliothek.
Das Messen darf das Gemessene nicht veraendern.

Der Zustand liegt in `werkstatt/anlaesse.json`. Er haelt zweierlei fest:
was schon BEKANNT ist (Geraete, Faehigkeiten - sonst waere nach jedem Neustart
alles neu) und was schon GESAGT ist (sonst erzaehlt er es wieder).
"""
from __future__ import annotations

from einstellungen import NAME, NAMENS, NUTZER
import json
import re
import time
from datetime import datetime
from pathlib import Path

HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"
JOURNAL = WERKSTATT / "journal.jsonl"
ANTRAEGE = WERKSTATT / "antraege"
LAGE = WERKSTATT / "lage.json"
PLATZVERLAUF = WERKSTATT / "platzverlauf.jsonl"
WUENSCHE = WERKSTATT / "WUENSCHE.md"
FAEHIGKEITEN = WERKSTATT / "faehigkeiten.json"
WERKZEUGE = WERKSTATT / "werkzeuge.json"
ZUSTAND = WERKSTATT / "anlaesse.json"

# So weit zurueck gilt etwas noch als frisch. Eine Stunde ist zu kurz - er
# denkt nur, wenn sich etwas ruehrt, und zwischen zwei Durchgaengen koennen
# zwanzig Minuten liegen. Ein halber Tag waere zu lang: was Calvin morgens
# angestossen hat, will er nicht abends gemeldet bekommen.
FRISCH_MIN = 120
# So lange nach einem Zuruf gilt ein Ergebnis als das, was Calvin angestossen
# hat. Laenger ist es Zufall.
ZURUF_FENSTER_MIN = 45
# Erst so lange danach ist ein unentschiedener Antrag eine Nachfrage wert.
ANTRAG_STILL_MIN = 60
# Ein Muster braucht Zeit und Groesse, sonst ist es Rauschen.
MUSTER_STUNDEN = 6.0
MUSTER_GB = 20.0
MUSTER_PUNKTE = 6
# So oft derselbe Fehler, bevor er ein Muster ist - und ueber so viele
# Stunden verteilt. Ohne die zweite Bedingung ist jeder einzelne Absturz, der
# sich in einer Minute achtzehnmal wiederholt, ein "Muster".
FEHLER_AB = 3
FEHLER_SPANNE_STUNDEN = 1.0
# So lange gilt ein einmal gesagter Anlass als erledigt. Danach darf dieselbe
# Sorte wieder vorkommen - ein Geraet, das nach Wochen wiederkommt, ist neu.
GESAGT_TAGE = 14

# Wonach zuerst gegriffen wird, wenn mehrere Anlaesse zugleich da sind. Eine
# offene Frage steht ueber allem: sie kostet Calvin nichts ausser einer
# Entscheidung, und ohne ihn geht es nicht weiter.
RANG = {"frage": 0, "haus": 1, "fertig": 2, "neu_gesehen": 3, "gelernt": 4,
        "muster": 5}


# ------------------------------------------------------------------ Zustand


def zustand_lesen() -> dict:
    try:
        d = json.loads(ZUSTAND.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    d.setdefault("bekannt", {})
    d.setdefault("gesagt", {})
    return d


def zustand_schreiben(d: dict) -> None:
    WERKSTATT.mkdir(parents=True, exist_ok=True)
    vorlaeufig = ZUSTAND.with_suffix(".json.tmp")
    vorlaeufig.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    vorlaeufig.replace(ZUSTAND)


def _bekannt(d: dict, gruppe: str, schluessel: list[str]) -> list[str]:
    """Was davon ist neu? Beim ALLERERSTEN Mal: nichts.

    Vierzehn Geraete und siebzehn Faehigkeiten auf einmal zu melden waere
    Laerm, kein Anlass - derselbe Grund, aus dem `wahrnehmung.ersteinlesen()`
    die vorhandenen Dateien stumm abhakt.
    """
    alt = d["bekannt"].get(gruppe)
    d["bekannt"][gruppe] = sorted(set(schluessel))
    if alt is None:
        return []
    return [s for s in schluessel if s not in set(alt)]


# ------------------------------------------------------------------ Quellen


def journalzeilen(minuten: int = FRISCH_MIN, hoechstens: int = 4000
                  ) -> list[dict]:
    """Die letzten Journalzeilen als Eintraege. Nur lesen."""
    if not JOURNAL.exists():
        return []
    grenze = time.time() - minuten * 60
    raus = []
    try:
        zeilen = JOURNAL.read_text(encoding="utf-8",
                                   errors="replace").splitlines()
    except OSError:
        return []
    for z in zeilen[-hoechstens:]:
        try:
            e = json.loads(z)
        except json.JSONDecodeError:
            continue
        if float(e.get("ts", 0)) >= grenze:
            raus.append(e)
    return raus


def _uhr(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M")
    except (ValueError, OSError, TypeError):
        return "?"


def _eine_zeile(text, hoechstens: int) -> str:
    """Zeilenumbrueche und Mehrfach-Leerzeichen raus.

    Ergebnisse aus der Bruecke sind ganze Markdown-Abschnitte, Fehler sind
    Tracebacks. Beides in einer Push-Nachricht ist unlesbar.
    """
    return " ".join(str(text or "").split())[:hoechstens]


def _alter_min(ts) -> int:
    try:
        return int((time.time() - float(ts)) / 60)
    except (ValueError, TypeError):
        return 0


def neu_gesehene_dateien(eintraege: list[dict]) -> list[dict]:
    """Dateien, die die Wahrnehmung verstanden hat.

    Nur solche, die es noch GIBT. Die Testspuren von heute Morgen
    (einkaufsliste.txt, wichtig.txt) waren beschrieben und Minuten spaeter
    geloescht - Calvin von einer Datei zu erzaehlen, die nicht mehr da ist,
    hilft ihm nicht und er kann nicht nachsehen.
    """
    raus = []
    for e in eintraege:
        if e.get("kind") != "fund" or not e.get("wahrnehmung"):
            continue
        pfad = e.get("datei") or ""
        if not pfad or not Path(pfad).exists():
            continue
        raus.append({
            "art": "neu_gesehen",
            "schluessel": f"datei:{pfad}",
            "ts": float(e.get("ts", 0)),
            "text": f"Ich habe um {_uhr(e.get('ts'))} eine Datei gelesen, die "
                    f"vorher nicht da war: {Path(pfad).name}. {e.get('text')}",
            "womit": {"pfad": pfad, "wann": _uhr(e.get("ts")),
                      "was_ich_verstanden_habe": e.get("text")},
        })
    return raus


def neue_geraete(d: dict) -> list[dict]:
    """Geraete im Heimnetz, die vorher nicht da waren.

    Aus `lage.json`, das der Lage-Faden ohnehin alle 30 s fortschreibt - hier
    wird nichts gescannt und nichts gepingt.
    """
    try:
        bild = json.loads(LAGE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    netz = bild.get("netz") or []
    # Nur was mehrfach hintereinander gesehen wurde. Die ARP-Tabelle laesst
    # Eintraege altern; ein einzelnes Aufblitzen ist kein neues Geraet.
    da = [g for g in netz if int(g.get("gesehen", 0)) >= 2 and g.get("mac")]
    neu = _bekannt(d, "geraete", [g["mac"] for g in da])
    nach_mac = {g["mac"]: g for g in da}
    raus = []
    for mac in neu:
        g = nach_mac[mac]
        name = g.get("name") or g.get("hostname") or ""
        wie = name or f"ohne Namen, Adresse {g.get('ip')}"
        raus.append({
            "art": "neu_gesehen",
            "schluessel": f"geraet:{mac}",
            "ts": float(g.get("seit") or time.time()),
            "text": f"Ein Geraet ist im Heimnetz, das vorher nicht da war: "
                    f"{wie} ({g.get('ip')}, {mac}).",
            "womit": {"name": name, "ip": g.get("ip"), "mac": mac,
                      "seit": _uhr(g.get("seit"))},
        })
    return raus


def fertig_geworden(eintraege: list[dict]) -> list[dict]:
    """Etwas ist fertig, das CALVIN angestossen hat - ungefragt melden.

    Ein Zuruf ist Calvins Anweisung. Was danach als `ergebnis` oder `pruefung`
    im Journal steht, geht auf ihn zurueck; er erfaehrt sonst nur, dass er
    etwas gesagt hat, nie, dass es durch ist.
    """
    zurufe = [e for e in eintraege if e.get("kind") == "zuruf"]
    if not zurufe:
        return []
    # Ein Zuruf zieht oft mehreres nach sich: Auftrag, Ergebnis, Pruefung.
    # Das ist EIN Vorgang und EINE Nachricht wert - sonst erzaehlt er
    # dieselbe Sache zweimal, nur mit anderem Wortlaut. Es zaehlt das
    # Letzte, was dabei herauskam.
    je_anstoss: dict[int, tuple[dict, dict]] = {}
    for e in eintraege:
        if e.get("kind") not in ("ergebnis", "pruefung"):
            continue
        ts = float(e.get("ts", 0))
        vorher = [z for z in zurufe
                  if 0 <= ts - float(z.get("ts", 0)) <= ZURUF_FENSTER_MIN * 60]
        if not vorher:
            continue
        anstoss = vorher[-1]
        je_anstoss[int(float(anstoss.get("ts", 0)))] = (anstoss, e)

    raus = []
    for anstoss, e in je_anstoss.values():
        ts = float(e.get("ts", 0))
        raus.append({
            "art": "fertig",
            "schluessel": f"fertig:{int(float(anstoss.get('ts', 0)))}",
            "ts": ts,
            # "CALVINS WORTE" muss dranstehen. Ohne die Kennzeichnung hat
            # gpt-oss das "ich" im Zitat fuer sich selbst genommen und
            # geantwortet "Ich habe die Datei um 10:17 geloescht" - geloescht
            # hatte sie Calvin. Eine erfundene Urheberschaft, und zwar in der
            # einen Zeile, die ungefiltert auf sein Handy geht.
            "text": f"Um {_uhr(anstoss.get('ts'))} sagte {NAME} ({NAMENS.upper()} "
                    f"WORTE, nicht meine): "
                    f"\"{_eine_zeile(anstoss.get('text'), 200)}\". Um "
                    f"{_uhr(ts)} war es durch, das kam dabei heraus: "
                    f"{_eine_zeile(e.get('text'), 300)}",
            "womit": {f"{NUTZER}_sagte_woertlich":
                          _eine_zeile(anstoss.get("text"), 300),
                      "wann_gesagt": _uhr(anstoss.get("ts")),
                      "ergebnis": _eine_zeile(e.get("text"), 400),
                      "wann_fertig": _uhr(ts),
                      "vor_minuten": _alter_min(ts)},
        })
    return raus


def _kann_namen(pfad: Path) -> list[str]:
    try:
        d = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [str(e["name"]) for e in (d if isinstance(d, list) else [])
            if isinstance(e, dict) and e.get("name")]


def _zweck(pfad: Path, name: str) -> str:
    try:
        d = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    for e in d if isinstance(d, list) else []:
        if isinstance(e, dict) and e.get("name") == name:
            return " ".join(str(e.get("zweck") or "").split())
    return ""


def neue_faehigkeiten(d: dict) -> list[dict]:
    """Er kann etwas, das er gestern noch nicht konnte.

    Das betrifft Calvin unmittelbar: Was der Bewohner selbst kann, muss Calvin
    nicht mehr anstossen.
    """
    paare = [(n, FAEHIGKEITEN) for n in _kann_namen(FAEHIGKEITEN)] + \
            [(n, WERKZEUGE) for n in _kann_namen(WERKZEUGE)]
    neu = _bekannt(d, "kann", [n for n, _ in paare])
    quelle = dict(paare)
    raus = []
    for name in neu:
        zweck = _zweck(quelle.get(name, FAEHIGKEITEN), name)
        raus.append({
            "art": "gelernt",
            "schluessel": f"kann:{name}",
            "ts": time.time(),
            "text": f"Ich kann etwas Neues: {name}. {zweck}",
            "womit": {"name": name, "zweck": zweck},
        })
    return raus


# "Es fehlt: Geraet", "Es fehlt: Geld", "Es fehlt: Recht" - genau das kann er
# sich NICHT selbst bauen lassen, und genau darueber entscheidet Calvin.
# "Es fehlt: Wissen" gehoert nicht hierher; das ist seine eigene Arbeit.
_FEHLT = re.compile(r"^\s*Es fehlt:\s*(Ger[aä]t|Geld|Recht)\b", re.IGNORECASE)


def wuensche_an_den_nutzer(d: dict) -> list[dict]:
    """Ein Wunsch, ueber den nur Calvin entscheiden kann.

    `wuensche.py` schreibt WUENSCHE.md ohnehin fort. Ein Wunsch nach Wissen
    ist keiner an Calvin - den kann er sich selbst bauen lassen. Ein Geraet,
    Geld oder ein Recht kann er nicht.
    """
    try:
        text = WUENSCHE.read_text(encoding="utf-8")
    except OSError:
        return []
    offen = []
    zeilen = text.splitlines()
    for i, z in enumerate(zeilen):
        t = _FEHLT.match(z)
        if not t:
            continue
        wunsch = ""
        for zurueck in range(i - 1, -1, -1):
            if zeilen[zurueck].strip():
                wunsch = zeilen[zurueck].strip()
                break
        if wunsch and not wunsch.startswith("#"):
            offen.append((wunsch, t.group(1)))
    neu = _bekannt(d, "wuensche", [w for w, _ in offen])
    art = dict(offen)
    return [{
        "art": "gelernt",
        "schluessel": f"wunsch:{w[:80]}",
        "ts": time.time(),
        "text": f"Mir ist aufgefallen, dass mir etwas fehlt, das ich mir "
                f"nicht selbst bauen kann - es fehlt {art.get(w, '')}: {w}",
        "womit": {"wunsch": w, "es_fehlt": art.get(w, ""),
                  f"nur_{NUTZER}": True},
    } for w in neu]


def im_haus(zustand: dict, stunden: int | None = None) -> list[dict]:
    """Was im Haus passiert ist: Abstuerze, Neustarts, neue Programme.

    Der Absturz von llama-server am 11.09. um 22:15 stand seit einem Tag im
    Windows-Ereignisprotokoll, und niemand hat ihn je gesehen. Genau dafuer
    ist das hier: Er wohnt in diesem Rechner - was darin passiert, ist ein
    Anlass, etwas zu sagen.

    Kostet rund 3 s durch das Ereignisprotokoll. Bei einem Durchgang alle
    fuenf Minuten ist das ein Prozent der Zeit.
    """
    try:
        import haus
    except ImportError:
        return []
    raus = []
    fenster = stunden if stunden is not None else max(1, FRISCH_MIN // 60)
    grenze = time.time() - fenster * 3600
    # Derselbe Gegenstand am selben Tag ist EIN Fall, nicht zwei Nachrichten.
    # llama-server ist am 11.09. um 17:19 und um 22:15 abgestuerzt - das ist
    # ein Satz ("zweimal, zuletzt um 22:15"), nicht zweimal derselbe Anruf.
    je_fall: dict[str, list[dict]] = {}
    try:
        for e in haus.ereignisse(fenster):
            if e.get("art") not in ("absturz", "neustart"):
                continue
            if float(e.get("ts") or 0) < grenze:
                continue
            tag = time.strftime("%Y-%m-%d", time.localtime(e["ts"]))
            je_fall.setdefault(
                f"haus:{e.get('gegenstand') or e.get('was')}:{tag}",
                []).append(e)
    except Exception:
        return []

    for schluessel, teil in je_fall.items():
        letzte_ = teil[-1]
        wie_oft = len(teil)
        raus.append({
            "art": "haus",
            "schluessel": schluessel,
            "ts": float(letzte_["ts"]),
            "text": (f"Um {_uhr(letzte_['ts'])}: {letzte_.get('was')}"
                     if wie_oft == 1
                     else f"{letzte_.get('was')} - {wie_oft} Mal, "
                          f"von {_uhr(teil[0]['ts'])} bis "
                          f"{_uhr(letzte_['ts'])}"),
            "womit": {"wann": _uhr(letzte_["ts"]), "was": letzte_.get("was"),
                      "gegenstand": letzte_.get("gegenstand"),
                      "wie_oft": wie_oft,
                      "windows_meldung": (letzte_.get("windows") or "")[:200]},
        })

    # Neu installiert oder entfernt. Beim allerersten Lauf werden die 121
    # vorhandenen Programme stumm abgehakt.
    try:
        jetzt_da = haus.programme()
    except Exception:
        jetzt_da = []
    if jetzt_da:
        namen = [f"{p.get('name')}|{p.get('fassung') or ''}" for p in jetzt_da]
        for neu in _bekannt(zustand, "programme", namen):
            name, _, fassung = neu.partition("|")
            raus.append({
                "art": "haus",
                "schluessel": f"programm:{neu}",
                "ts": time.time(),
                "text": f"Auf dem Rechner ist etwas dazugekommen, das vorher "
                        f"nicht da war: {name}"
                        + (f", Fassung {fassung}." if fassung else "."),
                "womit": {"programm": name, "fassung": fassung,
                          "neu_installiert": True},
            })
    return raus


def offene_antraege(jetzt: float | None = None) -> list[dict]:
    """Ein Antrag, den niemand entschieden hat - die Frage, die nur Calvin
    beantworten kann.

    Der Antrag selbst war schon eine Push. Dass er seit einer Stunde liegt,
    ist eine andere Nachricht: nicht "ich will etwas", sondern "es haengt".
    """
    jetzt = jetzt or time.time()
    raus = []
    if not ANTRAEGE.is_dir():
        return raus
    for p in sorted(ANTRAEGE.glob("a-*.json")):
        try:
            a = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if a.get("decided") or a.get("status") in ("zurueckgezogen",
                                                   "genehmigt", "abgelehnt"):
            continue
        wartet = (jetzt - float(a.get("ts", 0))) / 60.0
        if wartet < ANTRAG_STILL_MIN:
            continue
        raus.append({
            "art": "frage",
            "schluessel": f"antrag:{a.get('id')}",
            "ts": float(a.get("ts", 0)),
            "text": f"Mein Antrag \"{a.get('title')}\" liegt seit "
                    f"{round(wartet / 60, 1)} Stunden ohne Entscheidung.",
            "womit": {"antrag": a.get("title"), "grund": a.get("reason"),
                      "gestellt": _uhr(a.get("ts")),
                      "wartet_stunden": round(wartet / 60, 1)},
        })
    return raus


def platz_muster() -> list[dict]:
    """Der freie Platz ueber Stunden - ein Verlauf, den ausser ihm niemand
    mitschreibt."""
    if not PLATZVERLAUF.exists():
        return []
    punkte = []
    try:
        for z in PLATZVERLAUF.read_text(encoding="utf-8").splitlines()[-500:]:
            try:
                e = json.loads(z)
                punkte.append((datetime.fromisoformat(e["zeit"]),
                               float(e["frei_gb"])))
            except (ValueError, KeyError, json.JSONDecodeError):
                continue
    except OSError:
        return []
    if len(punkte) < MUSTER_PUNKTE:
        return []
    punkte.sort()
    stunden = (punkte[-1][0] - punkte[0][0]).total_seconds() / 3600.0
    if stunden < MUSTER_STUNDEN:
        return []
    weg = punkte[0][1] - punkte[-1][1]
    if abs(weg) < MUSTER_GB:
        return []
    richtung = "weniger" if weg > 0 else "mehr"
    # Der Schluessel traegt den Tag: hoechstens einmal taeglich, auch wenn der
    # Verlauf tagelang in dieselbe Richtung geht.
    tag = punkte[-1][0].strftime("%Y-%m-%d")
    return [{
        "art": "muster",
        "schluessel": f"platz:{richtung}:{tag}",
        "ts": time.time(),
        "text": f"In den letzten {round(stunden, 1)} Stunden ist auf C "
                f"{abs(round(weg))} GB {richtung} geworden - von "
                f"{round(punkte[0][1])} auf {round(punkte[-1][1])} GB frei.",
        "womit": {"stunden": round(stunden, 1), "von_gb": round(punkte[0][1]),
                  "auf_gb": round(punkte[-1][1]), "richtung": richtung},
    }]


def fehler_muster(eintraege: list[dict]) -> list[dict]:
    """Derselbe Fehler mehrfach - einzeln je unauffaellig, zusammen ein Muster.

    Er ist der Einzige, der das ganze Journal liest. Calvin sieht drei
    verstreute Fehlermeldungen nie als einen.
    """
    zaehler: dict[str, list[float]] = {}
    for e in eintraege:
        if e.get("kind") != "fehler":
            continue
        # Der Kopf der Meldung, ohne Zahlen und Kennungen - "Wahrnehmung:
        # ConnectError" statt der vollen Zeile.
        kern = re.sub(r"\d+", "#", _eine_zeile(e.get("text"), 400))[:60].strip()
        if kern:
            zaehler.setdefault(kern, []).append(float(e.get("ts", 0)))
    raus = []
    for kern, wann in zaehler.items():
        if len(wann) < FEHLER_AB:
            continue
        stunden = (max(wann) - min(wann)) / 3600.0
        # Achtzehn Fehler in einer Minute sind EIN Vorfall, kein Muster.
        # Gemessen am 11.09. um 23:39: ein abgestuerztes Gespraech, das sich
        # selbst wiederholte. Ein Muster ist es, wenn es wiederkommt.
        if stunden < FEHLER_SPANNE_STUNDEN:
            continue
        tag = datetime.fromtimestamp(max(wann)).strftime("%Y-%m-%d")
        raus.append({
            "art": "muster",
            "schluessel": f"fehler:{kern}:{tag}",
            "ts": max(wann),
            "text": f"Derselbe Fehler kam {len(wann)} Mal wieder, verteilt "
                    f"ueber {round(stunden, 1)} Stunden ({_uhr(min(wann))} "
                    f"bis {_uhr(max(wann))}): {kern}",
            "womit": {"fehler": kern, "wie_oft": len(wann),
                      "ueber_stunden": round(stunden, 1),
                      "von": _uhr(min(wann)), "bis": _uhr(max(wann))},
        })
    return raus


# ------------------------------------------------------------------ Sammeln


def sammeln(zustand: dict | None = None, speichern: bool = True) -> list[dict]:
    """Alle Anlaesse, ungefiltert. Schreibt den Zustand fort."""
    d = zustand if zustand is not None else zustand_lesen()
    frisch = journalzeilen(FRISCH_MIN)
    # Fehler ueber den ganzen Tag, nicht nur die frischen zwei Stunden - ein
    # Muster entsteht ueber Zeit.
    tag = journalzeilen(24 * 60)

    alle: list[dict] = []
    for teil in (neu_gesehene_dateien(frisch), neue_geraete(d),
                 fertig_geworden(frisch), neue_faehigkeiten(d),
                 wuensche_an_den_nutzer(d), offene_antraege(), platz_muster(),
                 fehler_muster(tag), im_haus(d)):
        alle.extend(teil)
    if speichern:
        zustand_schreiben(d)
    return alle


def offen(zustand: dict | None = None, speichern: bool = True) -> list[dict]:
    """Was er noch nicht gesagt hat, das Wichtigste zuerst."""
    d = zustand if zustand is not None else zustand_lesen()
    alle = sammeln(d, speichern=speichern)
    grenze = time.time() - GESAGT_TAGE * 86400
    gesagt = {k for k, ts in d["gesagt"].items() if float(ts) >= grenze}
    uebrig = [a for a in alle if a["schluessel"] not in gesagt]
    uebrig.sort(key=lambda a: (RANG.get(a["art"], 9), -a.get("ts", 0)))
    return uebrig


def vermerken(anlass: dict, zustand: dict | None = None) -> None:
    """Dieser Anlass ist erledigt - gesagt oder bewusst uebergangen."""
    d = zustand if zustand is not None else zustand_lesen()
    d["gesagt"][anlass["schluessel"]] = time.time()
    grenze = time.time() - GESAGT_TAGE * 86400
    d["gesagt"] = {k: ts for k, ts in d["gesagt"].items()
                   if float(ts) >= grenze}
    zustand_schreiben(d)


# ------------------------------------------------------------------ Ansehen


def main() -> int:
    """python anlaesse.py - was haette er gerade zu sagen?

    Aendert nichts: der Zustand wird gelesen, aber nicht fortgeschrieben.
    Sonst haekelte ein Blick von aussen die Anlaesse ab, ueber die er dann
    nicht mehr spricht.
    """
    d = zustand_lesen()
    erste = not ZUSTAND.exists()
    alle = offen(d, speichern=False)
    if erste:
        print("(noch kein Zustand - beim ersten echten Lauf werden Geraete,")
        print(" Faehigkeiten und Wuensche stumm abgehakt)")
    if not alle:
        print("Kein Anlass. Er schweigt zu Recht.")
        return 0
    print(f"{len(alle)} Anlaesse, wichtigster zuerst:\n")
    for a in alle:
        print(f"  [{a['art']}] {a['schluessel']}")
        print(f"    {a['text']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
