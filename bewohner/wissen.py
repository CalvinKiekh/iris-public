"""wissen - aus Gespraechen wird Wissen, statt Mitschrift.

Calvin am 12.09.: *"Ist es sinnig, nur einen Chat zu haben? Waere ein Rolling
Kontext nicht besser? Analyse der Gespraeche, Extraktion von Wissen im
Background?"*

Gemessen, bevor gebaut wurde:

    rollender Kontext   gibt es: die letzten vier Paare (gespraech.py:670)
    im Gedaechtnis      gespraech 43, ereignis 47, tagesrueckblick 10
    extrahiertes Wissen 0 - die Art "fakt" stand in ARTEN und war leer

Der rollende Kontext war also nie das Problem. Das Problem ist, dass alles
GLEICH aufbewahrt wird. Im Gedaechtnis stand woertlich:

    "Calvin fragte: Wie viel Arbeitsspeicher ist frei?
     Ich antwortete: Von 61.6 GB Arbeitsspeicher sind 38.6 GB frei."

Ein Messwert, der eine Sekunde lang stimmte. Daneben "Schnurpsel wrgl bitte?"
aus einer Probe. Dass "Wie heisst meine Tochter?" heute funktioniert, liegt an
der Volltextsuche ueber diese Zeilen - das traegt bei 43 Zeilen und kippt bei
viertausend, weil dann zwischen der Tochter und der Frage hundert Messwerte
liegen.

Was hier passiert:

    episode()      Ein Gespraech ist zu Ende, wenn eine Weile nichts kam.
                   Reine Zeitrechnung, kein Modell.
    lohnt()        Welche Paare ueberhaupt Wissen tragen koennen. Reine
                   Messung: ein Messwert, eine Uhrzeit, eine Probe nicht.
    auszug()       Das Modell zieht Saetze heraus, die MORGEN NOCH GELTEN.
    mangel()       Die Wache davor. Was sie nicht durchlaesst, wird nicht
                   gemerkt - lieber nichts als etwas Erfundenes.

Der Auszug laeuft LOKAL ueber gpt-oss, nicht ueber Claude. Drei Gruende: er
muss ohne Bruecke funktionieren, er kostet nichts, und der Grundsatz aus
sehen.py gilt hier genauso - das Gespraech verlaesst den Rechner nicht.
"""
from __future__ import annotations

from einstellungen import NAME, NAMENS
import json
import re

# Nur Standardbibliothek plus httpx - wie selbst.py und anlaesse.py.
import httpx

# Die beiden Erkenner fuer vergaengliche Fragen. Beide sind reine Muster ohne
# Dateizugriff beim Laden und holen nichts aus wissen oder gespraech zurueck -
# kein Kreis, nachgesehen.
import kann
import passiert

OLLAMA = "http://localhost:11434/api/chat"
MODELL = "gpt-oss:20b"

# So lange muss Ruhe sein, bevor ein Gespraech als beendet gilt. Kuerzer, und
# eine Denkpause mitten im Gespraech wuerde es zerschneiden; laenger, und das
# Wissen kommt erst Stunden spaeter an.
RUHE_S = 8 * 60
# Mehr Paare als das traegt kein Auszug - und ein Gespraech, das laenger ist,
# hat ohnehin mehrere Themen. Dann lieber die letzten.
PAARE_HOECHSTENS = 12
# Ein Fakt, der laenger ist, ist eine Erzaehlung. Vorgelesen wird er auch.
FAKT_ZEICHEN_MAX = 180
FAKTEN_HOECHSTENS = 4


# Fragen, deren Antwort morgen falsch ist. Sie sind der Grund, aus dem das
# Gedaechtnis heute voll Messwerte steht.
#
# Der Apostroph steht als Klasse da, nicht als '. Die Spracherkennung liefert
# den typografischen ’, und daran ist "Wie geht’s dir?" am 12.09. vorbeigekommen
# und liegt seither im Gedaechtnis - derselbe Satz, andere Schreibweise.
_VERGAENGLICH = re.compile(
    r"wie\s+(sp(ä|ae)t|viel\s+(platz|speicher|ram|cpu)|warm|lange\s+l(ä|ae)uft)|"
    r"welcher\s+tag|wie\s+geht(['’´`]?s| es)|"
    # "im netz" kannte das Muster, "im Heimnetz" nicht - und genau so fragt
    # Calvin. Zweimal durchgekommen.
    r"wer\s+(belegt|ist\s+(im\s+(heim)?netz(werk)?|online))|"
    r"was\s+(l(ä|ae)uft|ist\s+(gerade|jetzt))|"
    # Es gab gar kein Muster dafuer. Eine Statusauskunft ist in einer Stunde
    # eine andere.
    r"wie\s+(ist|steht\s+es\s+(um|mit))\s+(dein|der|deinem)\b|"
    # Seine eigene Arbeit: beantwortet passiert.vorgaenge() und ist morgen
    # eine andere Antwort. passiert.ist_frage() laesst das absichtlich durch,
    # weil es dort um das Haus geht, nicht um ihn.
    #
    # Die Fuellung dazwischen ist BELIEBIG, nicht aus einer Liste. Erst stand
    # hier `(alles\s+|denn\s+|so\s+)*`, und daran ist am 12.09. um 16:47
    # "Was hast du in der letzten Stunde gemacht?" vorbeigekommen und liegt
    # als Protokoll 117 im Gedaechtnis - dieselbe Frage, andere Worte. Wer
    # eine Wortliste pflegt, pflegt die Luecken mit.
    r"was\s+hast\s+du\b[^?.!]{0,40}?\bgemacht|"
    # "Was hast du heute getan/gearbeitet/erledigt" ist dieselbe Frage.
    r"was\s+hast\s+du\b[^?.!]{0,40}?\b(getan|gearbeitet|erledigt|"
    r"geschafft|angestellt)|"
    r"frei\??$", re.IGNORECASE)

# Proben und Selbsttests. "Kannst du mich hoeren" lag neunmal im Gedaechtnis.
_PROBE = re.compile(
    r"schnurpsel|testfrage|kannst du mich h(ö|oe)ren|^test\b|probe\s?lauf",
    re.IGNORECASE)


def lohnt(paar: dict) -> bool:
    """Kann aus diesem Paar ueberhaupt etwas werden, das morgen noch gilt?

    Reine Messung an der FRAGE, nicht an der Antwort. Wer nach der Uhrzeit
    fragt, bekommt keine Auskunft ueber sich - und die Antwort ist um
    Mitternacht falsch.

    DREI KLASSEN, nicht eine. Zuerst kannte diese Funktion nur Zustandsfragen,
    und am Gedaechtnis nachgezaehlt kamen dadurch 21 von 43 Protokollen durch,
    von denen die wenigsten etwas wert waren: achtmal "Was ist letzte Nacht
    passiert?", fuenfmal "Was kannst du?". Beide sind genauso vergaenglich wie
    ein Messwert - die Antwort auf die Nacht ist morgen eine andere, und was er
    kann, steht ohnehin in kann.py und wird von dort gelesen.

    Die Erkenner dafuer gibt es schon; hier werden sie nur gefragt. Eigene
    Muster daneben zu stellen hiesse, zwei Listen gleich zu halten - und die
    eine verfaellt, sobald jemand die andere erweitert.
    """
    frage = str(paar.get("frage") or "").strip()
    antwort = str(paar.get("antwort") or "").strip()
    if len(frage) < 4 or len(antwort) < 4:
        return False
    if _PROBE.search(frage):
        return False
    if _VERGAENGLICH.search(frage):
        return False
    if passiert.ist_frage(frage):          # Chronik: gilt nur fuer diese Nacht
        return False
    if kann.ist_faehigkeitsfrage(frage):   # Faehigkeiten: stehen in kann.py
        return False
    return True


def episode(paare: list[dict], jetzt: float, ruhe_s: float = RUHE_S) -> list[dict]:
    """Die Paare eines abgeschlossenen Gespraechs - oder nichts.

    Abgeschlossen heisst: seit dem letzten Paar ist Ruhe. Waehrend Calvin
    noch redet, wird nichts ausgewertet; sonst zoege der Auszug aus der
    Haelfte eines Gedankens einen Fakt.
    """
    mit_zeit = [p for p in paare if p.get("ts")]
    if not mit_zeit:
        return []
    if jetzt - float(mit_zeit[-1]["ts"]) < ruhe_s:
        return []
    return mit_zeit[-PAARE_HOECHSTENS:]


SYSTEM = f"""Aus einem Gespraech ziehst du heraus, was MORGEN NOCH GILT.

Du bekommst Fragen von {NAME} und deine Antworten darauf. Die meisten davon
sind nichts wert: eine Uhrzeit, ein Messwert, eine Ruecksprache. Das ist der
Normalfall, und dann sagst du das.

Ein Fakt ist ein Satz, der

- ueber {NAME.upper()} oder seine Welt etwas aussagt, nicht ueber dich,
- allein stehen kann, ohne das Gespraech daneben,
- morgen noch stimmt.

    ja    {NAMENS} Tochter heisst Lena Marie.
    ja    {NAME} arbeitet am Wochenende an der Bruecke zum Mac.
    nein  {NAME} hat nach dem freien Arbeitsspeicher gefragt.
    nein  Es waren 38,6 GB frei.
    nein  Ich kann den Bildschirm beschreiben.

Erfinde nichts. Steht es nicht im Gespraech, gibt es es nicht. Nenne keine
Zahl, die dort nicht steht. Im Zweifel weglassen - ein falscher Fakt bleibt
und wird spaeter als Wahrheit erzaehlt.

Antworte ausschliesslich als JSON:

{{"fakten": []}}
{{"fakten": ["{NAMENS} Tochter heisst Lena Marie."]}}

Hoechstens vier. Jeder unter 180 Zeichen, auf Deutsch, in der dritten Person.
"""


def _zahlen(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", str(text or "")))


# Saetze ueber ihn selbst statt ueber Calvin. Sie sind der haeufigste
# Fehlgriff: Er kennt seine Faehigkeiten und erzaehlt sie, wenn ihm nichts
# einfaellt - genau wie bei "Wie geht's dir".
_UEBER_SICH = re.compile(
    r"^(ich|er)\s+(kann|habe|bin|sehe|messe|entscheide|erinnere)\b|"
    r"^der (bewohner|assistent)\b", re.IGNORECASE)

# Ein Fakt, der die Frage nacherzaehlt, statt etwas zu behalten.
_NACHERZAEHLT = re.compile(
    r"\b(fragte|hat gefragt|wollte wissen|antwortete|hat geantwortet)\b",
    re.IGNORECASE)


def mangel(satz: str, quelle: str,
           zeichen_max: int = FAKT_ZEICHEN_MAX) -> str | None:
    """Warum dieser Fakt nicht ins Gedaechtnis darf - oder None.

    `zeichen_max` ist ein Parameter, weil archiv.py dieselbe Wache fuer die
    Zusammenfassung braucht (B.3) - nur mit deren Laenge. Mit 180 Zeichen
    waere jede Zusammenfassung "eine Erzaehlung, kein Fakt"; ein zweiter
    Waechter daneben waere zwei Listen, die gleich zu halten sind, und die
    eine verfaellt, sobald jemand die andere erweitert.

    Dieselbe Bauart wie antrag_mangel() und ansprache_mangel(): Eine Regel im
    Systemtext ist eine Bitte, eine Wache davor ist eine Zusage. Und hier
    wiegt es schwerer als bei beiden - ein Antrag wird abgelehnt und eine
    Ansprache verhallt, aber ein falscher Fakt BLEIBT und wird spaeter als
    Wahrheit erzaehlt.
    """
    s = " ".join(str(satz or "").split())
    if len(s) < 10:
        return "zu kurz, um etwas zu bedeuten"
    if len(s) > zeichen_max:
        return "eine Erzaehlung, kein Fakt"
    if _UEBER_SICH.match(s):
        return f"ueber sich selbst, nicht ueber {NAMENS} Welt"
    if _NACHERZAEHLT.search(s):
        return "erzaehlt das Gespraech nach, statt etwas zu behalten"
    # Jede Zahl im Fakt muss im Gespraech vorkommen. Das ist die Wache gegen
    # erfundene Messwerte - und die fing am 12.09. schon einmal etwas, als er
    # aus einem Beleg "iPhone von Calvin, fritz und ein weiterer" machte.
    erfunden = _zahlen(s) - _zahlen(quelle)
    if erfunden:
        return f"nennt Zahlen, die im Gespraech nicht stehen: {sorted(erfunden)}"
    return None


def _gespraechstext(paare: list[dict]) -> str:
    return "\n".join(
        f"{NAME}: {' '.join(str(p.get('frage') or '').split())}\n"
        f"Du: {' '.join(str(p.get('antwort') or '').split())}"
        for p in paare)


def auszug(paare: list[dict], fragen=None) -> tuple[list[str], list[str]]:
    """Die Fakten aus diesen Paaren, und was die Wache zurueckgehalten hat.

    `fragen` ist der Modellaufruf; ohne ihn geht es an gpt-oss. Als Parameter,
    damit die Probe messen kann, ohne das Modell zu belegen - und damit sie
    nicht denselben Fehler macht wie kann_test.py, das monatelang einen
    Aufruf mass, den es im Betrieb nicht gibt.
    """
    brauchbar = [p for p in paare if lohnt(p)]
    if not brauchbar:
        return [], []
    text = _gespraechstext(brauchbar)
    nachrichten = [{"role": "system", "content": SYSTEM},
                   {"role": "user", "content": text[:4000]}]
    try:
        if fragen is not None:
            antwort = fragen(nachrichten)
        else:
            r = httpx.post(OLLAMA, timeout=120,
                           json={"model": MODELL, "messages": nachrichten,
                                 "stream": False, "format": "json",
                                 "think": "low"})
            antwort = json.loads(r.json()["message"]["content"])
    except Exception as f:
        return [], [f"nicht ausgewertet ({type(f).__name__})"]
    if not isinstance(antwort, dict):
        return [], ["Antwort war kein Objekt"]

    gut, zurueck = [], []
    for satz in (antwort.get("fakten") or [])[:FAKTEN_HOECHSTENS]:
        s = " ".join(str(satz).split())
        warum = mangel(s, text)
        if warum:
            zurueck.append(f"{warum}: {s[:90]}")
        else:
            gut.append(s)
    return gut, zurueck


def aus_gespraech(paare: list[dict], jetzt: float, merken=None,
                  journal=None, fragen=None) -> int:
    """Der ganze Weg: Episode zu Ende? Dann auswerten und merken.

    Gibt zurueck, wie viele Fakten gemerkt wurden. `merken` und `journal`
    sind Parameter, damit die Probe nicht ins echte Gedaechtnis schreibt -
    zweimal ist an genau dieser Stelle heute schon eine Probe ins Echte
    gelaufen.
    """
    dran = episode(paare, jetzt)
    if not dran:
        return 0
    fakten, zurueck = auszug(dran, fragen=fragen)
    if journal is not None:
        for warum in zurueck:
            journal("gedaechtnis", f"Fakt zurueckgehalten: {warum}",
                    nicht_erinnern=True)
    if merken is None:
        import gedaechtnis
        merken = lambda t: gedaechtnis.merken("fakt", t, quelle="Gespräch")
    gemerkt = 0
    for satz in fakten:
        if merken(satz):
            gemerkt += 1
            if journal is not None:
                journal("gedaechtnis", f"Gemerkt: {satz}", nicht_erinnern=True)
    return gemerkt


def main() -> int:
    """python wissen.py - was wuerde aus den letzten Gespraechen gezogen?

    Schreibt nichts. Nur lesen und zeigen.
    """
    import sqlite3
    import sys
    from pathlib import Path
    db = Path(__file__).parent / "werkstatt" / "gedaechtnis.db"
    if not db.exists():
        print("kein Gedaechtnis")
        return 1
    v = sqlite3.connect(str(db))
    zeilen = [r[0] for r in v.execute(
        "SELECT text FROM erinnerung WHERE art='gespraech' "
        "ORDER BY rowid DESC LIMIT 12")]
    paare = []
    for z in reversed(zeilen):
        t = re.split(r"\s*Ich antwortete:\s*", z.replace(f"{NAME} fragte:", "", 1), 1)
        if len(t) == 2:
            paare.append({"frage": t[0].strip(), "antwort": t[1].strip(),
                          "ts": 1})
    print(f"{len(paare)} Paare aus dem Gedaechtnis, davon lohnend:")
    for p in paare:
        print(f"  {'ja ' if lohnt(p) else 'nein'}  {p['frage'][:66]}")
    if "--echt" not in sys.argv:
        print("\n(mit --echt wird gpt-oss gefragt)")
        return 0
    fakten, zurueck = auszug(paare)
    print("\nFakten:")
    for s in fakten or ["  (keine)"]:
        print(f"  + {s}")
    for s in zurueck:
        print(f"  - {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
