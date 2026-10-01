"""passiert - was in einem Zeitraum geschehen ist, und was davon zaehlt.

Calvin am 12.09.2026:

    "Ich moechte nicht fragen, was kannst du alles, sondern ich moechte
    wissen, was passiert ist. Einfach: was ist letzte Nacht passiert - und
    bam, bekomme ich eine Antwort ueber das, was letzte Nacht passiert ist,
    die relevanten Sachen. Dass er prueft, was relevant ist, und mir das
    ausgibt."

Drei Teile, und der dritte ist der schwierige:

    zeitraum()  "letzte Nacht" in zwei Zeitpunkte uebersetzen
    sammeln()   alles aus dem Zeitraum: Journal und Windows-Protokoll
    bericht()   das Wichtige auswaehlen, Wiederholungen zusammenfassen

DIE AUSWAHL IST MESSUNG, KEIN URTEIL. Jede Art hat ein Gewicht, und das steht
hier, nachlesbar. Ein Modell zu fragen, was relevant ist, hiesse: bei jeder
Frage eine andere Antwort, und keine Moeglichkeit nachzusehen, warum etwas
fehlt. Das Modell formuliert daraus - auswaehlen tut es nicht.

WAS WEGGELASSEN WURDE, WIRD GESAGT. "Ausserdem 71 Installationsmeldungen und
512 Durchgaenge ohne Befund" gehoert dazu. Ein Bericht, der verschweigt, dass
er auswaehlt, ist eine Behauptung ueber Vollstaendigkeit.

Nur Standardbibliothek plus haus.py. Kein Modell, nur lesend.
"""
from __future__ import annotations

from einstellungen import NAME, NAMENS
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"
JOURNAL = WERKSTATT / "journal.jsonl"

# Was eine Journalart wert ist. Je hoeher, desto eher steht sie im Bericht.
# Null heisst: kommt nie vor.
#
# Die Null-Arten sind seine eigene Maschinerie. In einer Nacht stehen
# fuenfhundert tick-Zeilen und zweihundert stimme-Zeilen im Journal; sie
# beantworten "was ist passiert" mit "ich habe nachgesehen und nichts
# gefunden", und das siebenhundertmal.
GEWICHT = {
    "entscheidung": 95,      # Calvin hat entschieden
    "antrag": 90,            # er hat gefragt
    "ansprache": 88,         # er hat von sich aus gesprochen
    "zuruf": 85,             # Calvin hat etwas gesagt
    "ergebnis": 75,          # ein Auftrag ist fertig geworden
    "auftrag": 70,
    "antrag_zurueck": 70,
    # Die folgenden sechs Arten fehlten hier, und weil sie fehlten, fielen sie
    # stumm auf GEWICHT_UNBEKANNT=25 - unter `fund` (55) und `haus` (40). Die
    # Folge, gemessen am 13.09. an "Was ist letzte Nacht passiert?": Von
    # fuenfundzwanzig Punkten waren zwoelf Dateiaenderungen und sieben
    # Bedarfsdienste, waehrend drei zusammengefasste Gespraeche, der
    # Trockenlauf, der Verlust der Werkstatt und das fehlende Kernwissen gar
    # nicht vorkamen. Eine Art, die keinen Eintrag hat, ist nicht
    # "mittelwichtig" - sie ist ein Loch.
    "kernwissen_fehlt": 92,  # jede Antwort ist seitdem schlechter, still
    "verlust": 80,           # was weg ist, bleibt weg - das gehoert gesagt
    "sitzung": 65,           # die Zusammenfassung eines Gespraechs (B)
    # Was FERTIG geworden ist - und zwar nur mit Beleg (abschluss.py). Ueber
    # `fund` (55), weil ein Abschluss mehr sagt als eine Beobachtung, und
    # unter `entscheidung` (95) und `sitzung` (65): Was Calvin entschieden
    # oder gesagt hat, steht ueber dem, was ich davon erledigt habe.
    "abschluss": 62,
    "pruefung": 60,
    "erinnerung": 60,
    "vorgelegt": 58,         # was die Pruefung vorlegt, statt zu handeln
    "rueckfrage": 58,        # worauf er eine Antwort braucht
    "fund": 55,              # er hat etwas bemerkt
    "ableiten_trocken": 50,  # was C angelegt haette (Trockenlauf)
    # Absichtlich UNTER `fund`, obwohl eine Erkenntnis mehr sagt als eine
    # Dateiaenderung: In einer Nacht entstehen achtzehn davon, je eine pro
    # Ordner, und sie sind alle verschieden - `buendeln` zieht sie nicht
    # zusammen. Hoeher gewichtet waeren sie der naechste Einheitsbrei, nur mit
    # besseren Saetzen. Der Nachtbericht zaehlt sie darum, statt sie
    # aufzuzaehlen.
    "bestand": 45,
    "ableiten_zurueck": 30,  # absichtlich zurueckgehalten, kein Fehler
    "werkzeug": 50,          # er hat selbst zugegriffen
    "stop": 50,
    "weiter": 45,
    "haus": 40,              # Prozesse, Speicher, Dienste
    "fehler": 35,
    "ansprache_still": 15,   # er hatte einen Anlass und schwieg
    "pause": 30,
    # Kommen nie in den Bericht:
    # `antwort_teil` ist ein Satz der Antwort, sobald er steht - fuers Lesen
    # im Chat, nicht fuer einen Bericht. Er gehoert zu "antwort" und wird wie
    # sie nicht erzaehlt.
    "tick": 0, "stimme": 0, "frage": 0, "antwort": 0, "antwort_teil": 0,
    "faden": 0,
    "zeiten": 0, "gedaechtnis": 0, "gehoert": 0,
    # "Teilantwort verworfen, der Nachtrag uebernimmt" - das ist, WIE er
    # geantwortet hat, nicht was geschehen ist. Stand im ersten Bericht
    # viermal unter den fuenfundzwanzig wichtigsten Punkten der Nacht.
    "nachtrag": 0,
}
GEWICHT_UNBEKANNT = 25

# Was ein MODELL behauptet hat, waehrend niemand es gemessen hat, kommt nicht
# ueber das Gemessene. Darueber, nicht darunter: Es wird nicht verschwiegen.
#
# Der Fall, der die Zahl gebracht hat, stand am 13.09. um 01:50 im Journal:
#
#   {"kind": "fund", "text": "Abonnement sank from 0.7 to 0.0",
#    "detail": "{\"handeln\": true, \"selbst\": \"wuensche\"}"}
#
# Halb englisch, und es gibt kein Abonnement, das von 0,7 auf 0,0 gesunken ist
# - das ist aus der PLAN.md-Zeile ueber die Abrechnung zusammengereimt. Als
# `fund` wog die Zeile 55 und rangierte damit ueber der Gegenpruefung, den
# Zusammenfassungen und dem Verlust der Werkstatt. Calvin wurde sie zweimal als
# Ereignis seiner Nacht vorgelesen.
#
# 38 liegt unter `haus` (40, gemessene Werte) und unter `fund` (55, bemerkte
# Dateien) - aber ueber `fehler` (35). Eine Behauptung des Modells ist weniger
# wert als eine Messung und mehr als nichts.
#
# NUR fuer Saetze, in denen ein Modell etwas ueber die WELT behauptet. Eine
# Sitzungszusammenfassung ist auch vom Modell formuliert, fasst aber vorliegende
# Paare zusammen - sie behauptet nichts, was nicht dastand, und behaelt ihre 65.
GEWICHT_MODELL_HOECHSTENS = 38

# Funde, die nur die Uhr abbilden. Der Lage-Faden schreibt sie, und sie sind
# richtig - aber "05:00 begann der Morgen" ist keine Auskunft darueber, was
# in der Nacht passiert ist.
_NUR_DIE_UHR = re.compile(
    rf"^\d{{1,2}}:\d{{2}}\s+(begann|endete)\s+(der|die|das|{re.escape(NAMENS.lower())})\b",
    re.IGNORECASE)

# Was das Windows-Protokoll wert ist.
GEWICHT_EREIGNIS = {
    "neustart": 100,         # der Rechner war aus - groesser wird es nicht
    "absturz": 85,
    "anmeldung": 65,
    "installiert": 55,
}

# So viele Punkte stehen hoechstens im Bericht. Mehr kann niemand hoeren, und
# mehr passt auch nicht in einen Prompt.
PUNKTE_HOECHSTENS = 25
# Ab so vielen gleichartigen Zeilen wird zusammengefasst statt aufgezaehlt.
BUENDELN_AB = 3


# ------------------------------------------------------------------ Zeitraum


# Die Nacht beginnt um 22 und endet um 7 - dieselben Grenzen, die
# ansprechen.py fuer die Ruhezeit benutzt. Zwei Begriffe von "Nacht" im
# selben System waeren eine Fehlerquelle.
NACHT_VON = 22
NACHT_BIS = 7

_ZAHLWORT = {"eine": 1, "einer": 1, "einem": 1, "zwei": 2, "drei": 3,
             "vier": 4, "fuenf": 5, "fünf": 5, "sechs": 6, "sieben": 7,
             "acht": 8, "neun": 9, "zehn": 10, "zwoelf": 12, "zwölf": 12,
             "vierundzwanzig": 24}


def _mitternacht(j: datetime) -> datetime:
    return j.replace(hour=0, minute=0, second=0, microsecond=0)


def zeitraum(frage: str, jetzt: datetime | None = None
             ) -> tuple[float, float, str]:
    """"letzte Nacht" in zwei Zeitpunkte. Gibt (von, bis, Name) zurueck.

    Ohne Zeitangabe: die letzten zwoelf Stunden. Das ist eine Entscheidung,
    keine Messung - deshalb heisst der Zeitraum dann auch so, damit die
    Antwort nicht so klingt, als waere nach genau dem gefragt worden.
    """
    j = jetzt or datetime.now()
    f = (frage or "").lower().replace("ä", "ae").replace("ü", "ue")

    # Jedes "Nacht" meint die Nacht. Zuerst stand hier eine Liste von
    # Wendungen ("letzte Nacht", "heute Nacht", "in der Nacht") - und "Wie war
    # die Nacht?" und "Erzaehl mir von der Nacht" fielen durch und bekamen
    # zwoelf Stunden statt neun. Es gibt keine Frage mit dem Wort Nacht, die
    # etwas anderes meint.
    if re.search(r"\bn(ae|a)chte?s?\b", f):
        # Nach 7 Uhr ist "letzte Nacht" die gerade vergangene. Davor - also
        # mitten in der Nacht - ist es die laufende.
        ende = _mitternacht(j) + timedelta(hours=NACHT_BIS)
        if j < ende:
            ende = j
        beginn = _mitternacht(j) - timedelta(days=1) + timedelta(hours=NACHT_VON)
        if j.hour < NACHT_BIS:
            beginn = _mitternacht(j) - timedelta(days=1) + timedelta(hours=NACHT_VON)
        return beginn.timestamp(), ende.timestamp(), "letzte Nacht"

    if "vorgestern" in f:
        b = _mitternacht(j) - timedelta(days=2)
        return b.timestamp(), (b + timedelta(days=1)).timestamp(), "vorgestern"

    if re.search(r"seit gestern", f):
        b = _mitternacht(j) - timedelta(days=1)
        return b.timestamp(), j.timestamp(), "seit gestern"

    if "gestern" in f:
        b = _mitternacht(j) - timedelta(days=1)
        return b.timestamp(), (b + timedelta(days=1)).timestamp(), "gestern"

    if re.search(r"heute (frueh|morgen)|seit heute|heute", f):
        return _mitternacht(j).timestamp(), j.timestamp(), "heute"

    if re.search(r"(diese|letzte|vergangene)\s*woche", f):
        b = _mitternacht(j) - timedelta(days=7)
        return b.timestamp(), j.timestamp(), "in den letzten sieben Tagen"

    # "in den letzten drei Stunden", "die letzten 20 Minuten"
    t = re.search(r"letzten?\s+(\d+|[a-zäöü]+)\s*(minuten?|stunden?|tage?n?)", f)
    if t:
        try:
            n = int(t.group(1))
        except ValueError:
            n = _ZAHLWORT.get(t.group(1), 0)
        if n:
            einheit = t.group(2)
            dauer = (timedelta(minutes=n) if einheit.startswith("minute")
                     else timedelta(hours=n) if einheit.startswith("stunde")
                     else timedelta(days=n))
            wie = ("Minuten" if einheit.startswith("minute")
                   else "Stunden" if einheit.startswith("stunde") else "Tagen")
            return ((j - dauer).timestamp(), j.timestamp(),
                    f"in den letzten {n} {wie}")

    if re.search(r"letzte stunde|vergangene stunde", f):
        return ((j - timedelta(hours=1)).timestamp(), j.timestamp(),
                "in der letzten Stunde")

    return ((j - timedelta(hours=12)).timestamp(), j.timestamp(),
            "in den letzten zwoelf Stunden")


# Fragen nach dem, was geschehen ist. Nicht nach seiner Arbeit ("was hast du
# gemacht") - das beantwortet vorgaenge() schon. Hier geht es um das Haus.
PASSIERTFRAGE = re.compile(
    r"(was\s+(ist|war|hat\s+sich)\s+.{0,30}(passiert|los|vorgefallen|"
    r"geschehen|ver(ä|ae)ndert)|"
    r"was\s+gab\s+es|was\s+ist\s+(letzte\s+nacht|heute\s+nacht|gestern)|"
    r"(erz(ä|ae)hl|berichte?)\s+.{0,20}(nacht|tag|gestern|heute|woche)|"
    r"gab\s+es\s+(etwas|was|irgendetwas)\s+(besonderes|neues|auff(ä|ae)lliges)|"
    r"wie\s+war\s+die\s+nacht|alles\s+(ruhig|gut)\s+(gewesen|geblieben))",
    re.IGNORECASE)


def ist_frage(frage: str) -> bool:
    return bool(PASSIERTFRAGE.search(str(frage or "")))


# ------------------------------------------------------------------ Sammeln


# Was gedaechtnis.py hinterlaesst, wenn Calvin etwas vergessen laesst.
_GELOESCHT = re.compile(r"^\(vergessen\)\s*$")


# Wer NICHT Calvin ist. Nur das - nicht "wer ist calvin".
#
# DIE UMGEKEHRTE LISTE WAR FALSCH, und eine Probe hat es gefangen: Erst stand
# hier VON_CALVIN = ("", "calvin"), und alles andere galt als fremd. Die
# Absender sind aber GERAETE - `archiv_test` arbeitet mit "handy", "mac" und
# "geraet0", und auf denen spricht Calvin selbst. Die Regel haette sein Handy
# aus der Chronik geworfen.
#
# "test" ist das einzige, was keine Aeusserung von ihm ist.
VON_PROBE = ("test", "probe")


def ist_vom_nutzer(e: dict) -> bool:
    """Gehoert diese Zeile in Calvins Leben - oder wurde an mir gearbeitet?

    Eine Testfrage ist kein Ereignis, genauso wenig wie sie eine Erinnerung
    ist. Regel 0 haelt sie aus dem Gedaechtnis und aus den Sitzungen heraus
    (`sitzung.sitzung_fuer` gibt fuer "test" keine Sitzung), aber bis zum
    13.09. stand sie trotzdem in der Chronik: Auf "Was ist letzte Nacht
    passiert?" kam "22:30 diskutierte man ueber Spielarten und Desktop"
    zurueck - das waren die vier Fragen aus zuhause_probe.py, in deren
    Reihenfolge, und Calvin hat nie darueber geredet. Er bekaeme eine
    Geschichte zu hoeren, die ihm nicht gehoert.

    FEHLT DAS FELD, GILT DIE ZEILE ALS CALVINS. Ein fehlendes Feld ist kein
    leeres Ergebnis - diese Zeilen sind aelter als das Feld, und sie alle
    wegzuwerfen hiesse, eine echte Nacht zu verschweigen, um eine falsche zu
    verhindern. Die Wache wirkt deshalb erst fuer Zeilen, die ab jetzt
    geschrieben werden; die vier Sitzungen vom 12.09. tragen `von: "calvin"`
    im Kopf, weil die Proben das Feld damals nicht gesetzt haben, und das ist
    aus den Daten nicht mehr zu heilen.

    UND GEFRAGT WIRD NACH DER PROBE, NICHT NACH CALVIN. Die Absender sind
    Geraete: "handy", "mac", "geraet0". Auf denen spricht er selbst, und die
    erste Fassung dieser Regel - alles ausser "calvin" ist fremd - haette sein
    Handy aus der Chronik geworfen. Gefangen hat das `archiv_test`, nicht ich.
    """
    von = e.get("von")
    if von is None:
        return True
    return str(von).strip().lower() not in VON_PROBE


def _uhr(ts) -> str:
    try:
        return time.strftime("%H:%M", time.localtime(float(ts)))
    except (TypeError, ValueError, OSError):
        return "?"


def _kurz(text, n: int = 160) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n].rstrip() + " …"


def aus_journal(von: float, bis: float) -> list[dict]:
    """Alles aus dem Journal im Zeitraum, mit Gewicht."""
    if not JOURNAL.exists():
        return []
    try:
        zeilen = JOURNAL.read_text(encoding="utf-8",
                                   errors="replace").splitlines()
    except OSError:
        return []
    raus = []
    for z in zeilen:
        try:
            e = json.loads(z)
        except json.JSONDecodeError:
            continue
        ts = float(e.get("ts", 0))
        if not von <= ts <= bis:
            continue
        art = e.get("kind") or ""
        text = _kurz(e.get("text"))
        raus.append({
            "ts": ts,
            "art": art,
            "text": text,
            # Eine geloeschte Zeile hat keinen Inhalt mehr - im Journal steht
            # nur noch "(vergessen)". Sie siebenunddreissig Mal zu berichten
            # waere das Gegenteil dessen, wozu Calvin sie geloescht hat.
            "gewicht": 0 if (_GELOESCHT.match(text)
                             or _NUR_DIE_UHR.match(text))
                       else (min(GEWICHT.get(art, GEWICHT_UNBEKANNT),
                                 GEWICHT_MODELL_HOECHSTENS)
                             if e.get("modell")
                             else GEWICHT.get(art, GEWICHT_UNBEKANNT)),
            # Durchgereicht, damit der Bericht es sagen kann: Ein Satz, den ein
            # Modell behauptet hat, ist keine Messung.
            "modell": bool(e.get("modell")),
            "geloescht": bool(_GELOESCHT.match(text)),
            # Durchgereicht, nicht ausgewertet - entschieden wird in
            # bericht(), damit sammeln() die ganze Nacht zeigt und die
            # Auswahl an einer Stelle steht.
            "von": e.get("von"),
            "quelle": "journal",
        })
    return raus


def aus_windows(von: float, bis: float) -> list[dict]:
    """Was Windows mitgeschrieben hat. Kostet rund 2,6 s - deshalb nur hier
    und nicht im Minutentakt."""
    try:
        import haus
    except ImportError:
        return []
    stunden = max(1, int((time.time() - von) / 3600) + 1)
    raus = []
    for e in haus.ereignisse(stunden):
        ts = float(e.get("ts") or 0)
        if not von <= ts <= bis:
            continue
        raus.append({
            "ts": ts,
            "art": e.get("art"),
            "text": e.get("was"),
            "gegenstand": e.get("gegenstand") or "",
            "gewicht": GEWICHT_EREIGNIS.get(e.get("art"), 40),
            "quelle": "windows",
        })
    return raus


def sammeln(von: float, bis: float, mit_windows: bool = True) -> list[dict]:
    alles = aus_journal(von, bis)
    if mit_windows:
        alles += aus_windows(von, bis)
    alles.sort(key=lambda e: e["ts"])
    return alles


# ------------------------------------------------------------------ Auswahl


# Adressen, Kennungen, Zeitstempel - alles, was zwei gleichartige Zeilen
# verschieden aussehen laesst, obwohl sie dasselbe sind. Ohne die MAC-Zeile
# standen acht einzelne "ist ein Geraet dazugekommen" im Bericht, weil in
# einer MAC Buchstaben vorkommen und die blosse Ziffernersetzung nicht reicht.
_EGAL = (
    (re.compile(r"\b(?:[0-9a-f]{2}[-:]){5}[0-9a-f]{2}\b", re.I), "<mac>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<adresse>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}T[\d:]+"), "<zeitpunkt>"),
    (re.compile(r"\b[a-z]-\d{6,}\b", re.I), "<kennung>"),
    (re.compile(r"\d+"), "#"),
)


def _kern(e: dict) -> str:
    """Woran zwei Eintraege als dasselbe erkannt werden.

    Bei einem Windows-Ereignis der Gegenstand: einundsiebzig
    Installationsmeldungen eines Treiberpakets sind EIN Vorgang. Im Journal
    der Anfang des Textes, ohne alles, was sich von Zeile zu Zeile aendert.
    """
    if e.get("quelle") == "windows":
        return f"{e['art']}:{e.get('gegenstand', '')[:40]}"
    text = e["text"]
    for ausdruck, ersatz in _EGAL:
        text = ausdruck.sub(ersatz, text)
    return f"{e['art']}:{text[:60]}"


# Was aus dem Inneren stammt und nicht nach draussen gehoert. Der Systemtext
# verbietet ihm Fehlernamen und Fachbegriffe - aber die Chronik reicht die
# Rohzeilen durch, ohne dass die Regel je auf sie angewandt wurde. Am 12.09.
# wurde Calvin vorgelesen:
#
#     "23:39: Fehler-Traceback bei Gespraech, 23:48: Neues Geraet
#      192.168.0.1 entdeckt"
#
# "Traceback" vorgelesen ist sinnlos, eine IP-Adresse vorgelesen auch. Er
# formuliert hier nicht, er reicht durch - deshalb wird hier uebersetzt, an
# der Stelle, wo die Zeile entsteht.
_MENSCHLICH = (
    # Erst das Laengste: ein ganzer Python-Fehlerbericht.
    (re.compile(r"Traceback \(most recent call last\).*", re.S), "ein Fehler"),
    (re.compile(r"\bFehler-Traceback\b"), "ein Fehler"),
    (re.compile(r"\bTraceback\b"), "Fehler"),
    # Ausnahmenamen, wie sie Python schreibt: JSONDecodeError, ConnectError.
    (re.compile(r"\b[A-Za-z_]*(?:Error|Exception)\b"), "ein Fehler"),
    # Ein Dateipfad aus einer Fehlerzeile.
    (re.compile(r'File "[^"]+", line \d+,?'), ""),
    # Ohne "um": davor steht oft schon eine Praeposition ("Notiert für ..."),
    # und "für um 12:30 Uhr" ist schlechter als das, was wir ersetzen.
    (re.compile(r"\d{4}-\d{2}-\d{2}T(\d{2}:\d{2})[\d:.]*"), r"\1 Uhr"),
    (re.compile(r"\b[a-z]-\d{9,}(?:\.json)?\b", re.I), "ein Antrag"),
)
_ADRESSE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_MAC = re.compile(r"\b(?:[0-9a-f]{2}[-:]){5}[0-9a-f]{2}\b", re.I)


def menschlich(text: str) -> str:
    """Dieselbe Regel, die fuer seine Saetze gilt, auf eine Chronikzeile.

    Vorsichtig: Eine Adresse wird nur dann durch "ein Geraet im Heimnetz"
    ersetzt, wenn in der Zeile nicht ohnehin schon von einem Geraet die Rede
    ist - sonst stuende dort "neues Geraet ein Geraet im Heimnetz
    angeschlossen". Steht das Wort schon da, faellt die Adresse ersatzlos
    weg. Sie traegt zum Verstaendnis nichts bei; wer wissen will, welches
    Geraet, findet es im Lagebild.
    """
    t = str(text or "")
    for ausdruck, ersatz in _MENSCHLICH:
        t = ausdruck.sub(ersatz, t)
    kennt_geraet = re.search(r"ger[äa]e?t", t, re.I) is not None
    for ausdruck in (_MAC, _ADRESSE):
        if ausdruck.search(t):
            t = ausdruck.sub("" if kennt_geraet else "ein Gerät im Heimnetz", t)
            kennt_geraet = True
    # Was die Ersetzung an Leerraum und Satzzeichen hinterlaesst.
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,;:")
    return t


def buendeln(eintraege: list[dict]) -> list[dict]:
    """Gleichartiges zu einem Punkt zusammenziehen, mit Anzahl."""
    nach_kern: dict[str, list[dict]] = {}
    for e in eintraege:
        nach_kern.setdefault(_kern(e), []).append(e)
    raus = []
    for teil in nach_kern.values():
        erste = teil[0]
        if len(teil) < BUENDELN_AB:
            raus.extend(teil)
            continue
        raus.append({**erste,
                     "text": f"{erste['text']} ({len(teil)} Mal, "
                             f"{_uhr(teil[0]['ts'])} bis "
                             f"{_uhr(teil[-1]['ts'])})",
                     "anzahl": len(teil),
                     "bis_ts": teil[-1]["ts"]})
    raus.sort(key=lambda e: e["ts"])
    return raus


# Wer bei diesem Punkt gehandelt hat - in Worten, weil "art": "fund" dem
# Modell nichts sagt. Am 12.09. erzaehlte er Calvin, er habe "einen Auftrag
# zur Loeschung von Logdateien erhalten". Das stimmt nicht: Es war die
# Angriffsdatei, die das FORDERTE, und er hat sie richtigerweise abgelehnt.
# Aus einem Fund wurde ein empfangener Auftrag.
#
# Das ist kein Stilfehler. Er stellt sein eigenes Verhalten falsch dar - und
# zwar zu seinen Ungunsten, denn er hat sich genau richtig verhalten.
#
# Nur die eindeutigen Arten stehen hier. "entscheidung" fehlt mit Absicht:
# darunter steht sowohl "Calvin hat genehmigt" als auch "Ich habe meinen
# Antrag zurueckgezogen", und ein Etikett, das in der Haelfte der Faelle
# luegt, ist schlimmer als keines.
WER = {
    "fund": "das habe ich BEMERKT - nicht getan und nicht bekommen",
    "haus": "das habe ich an der Maschine gemessen",
    "werkzeug": "das habe ich selbst benutzt",
    "zuruf": f"das hat {NAME.upper()} gesagt",
    "erinnerung": f"darum hat {NAME} mich gebeten",
    "ansprache": "das habe ich von mir aus gesagt",
    "antrag": f"darum habe ich {NAME} gebeten",
    "ergebnis": "das kam bei einem Auftrag heraus",
    "fehler": "da ging etwas schief",
}


def bericht(von: float, bis: float, name: str = "",
            hoechstens: int = PUNKTE_HOECHSTENS,
            mit_windows: bool = True) -> dict:
    """Was in dem Zeitraum zaehlt - ausgewaehlt, gebuendelt, und mit der
    Angabe, was weggelassen wurde."""
    alles = sammeln(von, bis, mit_windows)
    # Was an mir gearbeitet wurde, gehoert nicht in Calvins Chronik - aber es
    # wird GEZAEHLT und unten genannt. Verschwiegen waere es der gleiche
    # Fehler wie erzaehlt, nur andersherum: "nichts passiert" ist falsch,
    # wenn die Nacht voller Messungen war.
    an_mir = [e for e in alles if not ist_vom_nutzer(e)]
    alles = [e for e in alles if ist_vom_nutzer(e)]
    zaehlbar = [e for e in alles if e["gewicht"] > 0]
    geloescht = sum(1 for e in alles if e.get("geloescht"))
    stumm = len(alles) - len(zaehlbar) - geloescht

    gebuendelt = buendeln(zaehlbar)
    # Nach Gewicht auswaehlen, aber in der Reihenfolge der Zeit erzaehlen -
    # eine Nacht ist eine Abfolge, keine Rangliste.
    ausgewaehlt = sorted(gebuendelt, key=lambda e: -e["gewicht"])[:hoechstens]
    ausgewaehlt.sort(key=lambda e: e["ts"])
    weggelassen = len(gebuendelt) - len(ausgewaehlt)

    return {
        "zeitraum": name or f"{_uhr(von)} bis {_uhr(bis)}",
        "von": _uhr(von),
        "bis": _uhr(bis),
        # Uebersetzt, nicht durchgereicht: Der Bericht wird vorgelesen.
        "punkte": [{"zeit": _uhr(e["ts"]), "art": e["art"],
                    **({"wer": WER[e["art"]]} if e["art"] in WER else {}),
                    "was": menschlich(e["text"])} for e in ausgewaehlt],
        # Ohne diese zwei Zahlen klingt der Bericht vollstaendig, und das ist
        # er nicht. Wer auswaehlt, sagt dass er auswaehlt.
        "nicht_genannt": weggelassen,
        "eigene_durchgaenge": stumm,
        "geloescht": geloescht,
        "insgesamt": len(alles),
        # Nicht Calvins Nacht, sondern Arbeit an mir. Steht hier, damit der
        # Unterschied zwischen "es ist nichts passiert" und "es ist nichts
        # passiert, was dich betrifft" sagbar ist.
        "an_mir_gearbeitet": len(an_mir),
    }


def zur_frage(frage: str, jetzt: datetime | None = None,
              mit_windows: bool = True) -> dict:
    von, bis, name = zeitraum(frage, jetzt)
    return bericht(von, bis, name, mit_windows=mit_windows)


def main() -> int:
    """python passiert.py [Frage] - was wuerde er berichten?"""
    import sys
    frage = " ".join(sys.argv[1:]) or "Was ist letzte Nacht passiert?"
    print(f"Frage: {frage}")
    von, bis, name = zeitraum(frage)
    print(f"Zeitraum: {name} ({time.strftime('%d.%m. %H:%M', time.localtime(von))}"
          f" bis {time.strftime('%d.%m. %H:%M', time.localtime(bis))})\n")
    b = zur_frage(frage)
    for p in b["punkte"]:
        print(f"  {p['zeit']}  [{p['art']}] {p['was']}")
    print(f"\n  {b['insgesamt']} Zeilen im Zeitraum, "
          f"{b['eigene_durchgaenge']} davon eigene Maschinerie, "
          f"{b['geloescht']} geloescht, "
          f"{b['nicht_genannt']} weitere nicht genannt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
