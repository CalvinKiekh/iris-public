"""Archivieren statt Protokollieren - Schritt B aus PLAN-SITZUNGEN.md.

    python archiv.py            die letzten Zusammenfassungen
    python archiv.py --jetzt    die faellige Sitzung sofort abschliessen
    python archiv_test.py       die Probe

Hier wird das Modell gefragt, und das ist der ganze Unterschied zu
sitzung.py. Deshalb steht es in einer eigenen Datei: Die Zuordnung einer
Frage darf nie auf ein Modell warten, der Abschluss darf es.

WAS SICH AENDERT. Bisher wurde jedes Frage/Antwort-Paar, das `wissen.lohnt()`
ueberstand, als rohe Mitschrift ins Gedaechtnis gelegt - "Calvin fragte: ...
Ich antwortete: ...". Davon lagen heute Morgen 43 Stueck da, und auf
"Was machen wir am Wochenende?" lieferte die Suche 1500 Zeichen, obenan
"Calvin fragte: Was kannst du?". Die Suche war nie kaputt. Sie fand nur, was
wir hineingelegt haben.

Statt der Mitschrift gibt es jetzt EINE Zusammenfassung je Sitzung, als
eigene Art `sitzung`. Calvins Wort dazu: "ein paar Saetze, was besprochen
wurde."

WAS HINEINGEHOERT ist nicht der Ablauf, sondern der Gegenstand:

    nein   Calvin fragte nach dem Speicher, ich antwortete.
    ja     Es ging um den freien Speicher und um Lenas Arzttermin.

Derselbe Unterschied wie beim `wer`-Feld in passiert.py. Die Wache dagegen
gibt es schon: `wissen.mangel()` haelt Saetze zurueck, die das Gespraech
nacherzaehlen - hier mit der Laengengrenze der Zusammenfassung statt der des
Fakts, sonst waere jede Zusammenfassung "eine Erzaehlung, kein Fakt".

UND WAS NICHT MELDENSWERT WAR, GEHOERT AUCH NICHT HINEIN. Eine Sitzung aus
lauter Zustandsfragen wird nicht zusammengefasst: `wissen.lohnt()` entscheidet
das schon heute, und bleibt nichts uebrig, wird das Modell gar nicht erst
gefragt. Zehn "Wie spaet ist es?" am Tag kosten dann nichts.
"""
from __future__ import annotations

from einstellungen import NAME, NAMENS
import json
import os
import re
import time
from datetime import datetime

import httpx

import sitzung
import wissen
import zeitwort

OLLAMA = "http://localhost:11434/api/chat"
MODELL = "gpt-oss:20b"

# Calvin: "ein paar Saetze". Das sind vier bis fuenf.
ZUSAMMENFASSUNG_ZEICHEN_MAX = 600
# Mehr Paare traegt kein Prompt, und eine Sitzung mit 200 Paaren hat ohnehin
# mehrere Themen (Anhang 3). Dann lieber die letzten - dieselbe Zahl wie beim
# Fakten-Auszug, und aus demselben Grund an einer Stelle.
PAARE_HOECHSTENS = wissen.PAARE_HOECHSTENS

# C - Ableiten. SCHARF, seit Calvin am 13.09. entschieden hat:
# "er darf alles aus dem Gespraech ziehen, nur halt ohne meine Zustimmung
# nichts umbauen."
#
# Vorher war der Trockenlauf die Voreinstellung, und der Grund dafuer gilt
# weiter: Ein vergessener Termin ist aergerlich, ein erfundener weckt Calvin um
# drei Uhr nachts. Die Bremse dagegen ist jetzt eine andere - nicht mehr "legt
# nichts an", sondern die Wachen, die jeder Satz einzeln passieren muss:
# `wissen.mangel`, `bekannt()`, und bei einem Termin ein aufloesbares Datum.
#
#   ABLEITEN_SCHARF=0  in der Umgebung -> zurueck in den Trockenlauf
#
# Die Richtung ist umgedreht, die Eigenschaft nicht: Ein Schalter, den man im
# Zweifel zurueckziehen will, bleibt ohne Codeaenderung erreichbar.
ABLEITEN_SCHARF = os.environ.get("ABLEITEN_SCHARF", "1").strip().lower() \
    not in ("0", "aus", "nein", "false")

# Was abgeleitet werden darf. "vorhaben" ist Calvins Entscheidung vom 13.09.
# und die heikelste Art im Feld: Bis dahin wurde ein erkannter Auftrag
# zurueckgehalten und gemeldet, weil ein selbst erteilter Auftrag eine Handlung
# ohne Auftrag waere. Das bleibt wahr - ZIEHEN und TUN sind aber zweierlei.
# Festgehalten wird er ab jetzt als Wissen ("Calvin will, dass ..."), und
# `anwenden()` legt ihn ins Gedaechtnis, NICHT in die Auftragsschlange. Es gibt
# keinen Weg von dieser Art zu einer Ausfuehrung, und das ist die Zusage.
ARTEN_ABLEITBAR = ("termin", "fakt", "vorliebe", "vorhaben")

# Das Modell kennt das Wort "auftrag" aus dem Prompt und aus der Welt. Was es
# so nennt, ist ein Vorhaben - festhalten ja, ausfuehren nie.
ARTEN_GLEICH = {"auftrag": "vorhaben", "wunsch": "vorhaben",
                "aufgabe": "vorhaben", "praeferenz": "vorliebe",
                "praferenz": "vorliebe"}

SYSTEM = f"""Du fasst ein Gespraech zusammen, das zu Ende ist.

Du bekommst Fragen von {NAME} und deine Antworten darauf. Schreibe in ein paar
Saetzen, WORUEBER gesprochen wurde - nicht, wer was gefragt hat.

    nein  {NAME} fragte nach dem freien Speicher, ich habe geantwortet.
    nein  Zuerst ging es um X, dann fragte er nach Y.
    ja    Es ging um den freien Speicher und um Lenas Termin beim Kinderarzt.
    ja    {NAME} hat ueberlegt, ob die Bruecke zum Mac ueber Tailscale laeuft.

Nenne die Gegenstaende, nicht den Ablauf. Erfinde nichts und nenne keine Zahl,
die im Gespraech nicht steht. Was nicht besprochen wurde, kommt nicht hinein.

Hoechstens %(max)d Zeichen, auf Deutsch, ohne Aufzaehlungszeichen.

Antworte ausschliesslich als JSON:

{{"zusammenfassung": "Es ging um ..."}}
"""


def _fragen(nachrichten: list) -> dict:
    """Der Modellaufruf, wenn keiner mitgegeben wurde."""
    r = httpx.post(OLLAMA, timeout=120,
                   json={"model": MODELL, "messages": nachrichten,
                         "stream": False, "format": "json", "think": "low"})
    return json.loads(r.json()["message"]["content"])


def brauchbar(paare: list[dict]) -> list[dict]:
    """Die Paare, aus denen etwas werden kann.

    `wissen.lohnt()` urteilt ueber die FRAGE - und eine Ansprache hat keine.
    Sie faellt damit durch, obwohl sie der Grund ist, aus dem die Sitzung
    ueberhaupt existiert (B9 des Mac): Wenn ER anfaengt, traegt das erste Paar
    den Anlass und `frage: null`. Ohne diese Zeile waere die Zusammenfassung
    einer Ansprache leer, und die Sitzung saehe aus wie eine, in der nichts
    gesagt wurde.
    """
    return [p for p in paare
            if p.get("frage") is None or wissen.lohnt(p)]


def _text(paare: list[dict]) -> str:
    zeilen = []
    for p in paare:
        frage = " ".join(str(p.get("frage") or "").split())
        antwort = " ".join(str(p.get("antwort") or "").split())
        if frage:
            zeilen.append(f"{NAME}: {frage}\nDu: {antwort}")
        else:
            # Eine Ansprache steht ohne Frage da, und das muss im Prompt zu
            # sehen sein: "Du: ..." allein liest sich wie eine Antwort auf
            # eine Frage, die es nie gab.
            zeilen.append(f"Du, von dir aus: {antwort}")
    return "\n".join(zeilen)


def zusammenfassen(paare: list[dict],
                   fragen=None) -> tuple[str, list[str]]:
    """Ein paar Saetze, worueber geredet wurde - und was zurueckgehalten wurde.

    Drei Rueckgaben sind zu unterscheiden, und die Marke in sitzungen.jsonl
    haengt davon ab:

        ("Es ging um ...", [])   es gibt eine Zusammenfassung
        ("", ["nichts ..."])     nichts zu sagen, das Modell wurde nicht
                                 gefragt -> Marke "" setzen, fertig
        ("", ["nicht ..."])      das Modell hat nicht geantwortet -> Marke
                                 bleibt null, die Nacht holt es nach

    `fragen` ist der Modellaufruf als Parameter - wie in `wissen.auszug()`,
    und aus demselben Grund: Sonst misst eine Probe einen Aufruf, den es im
    Betrieb nicht gibt. Genau dieser Fehler hat heute frueh kann_test.py
    "bestanden" melden lassen fuer Antworten, die Calvin nie zu hoeren bekam.
    """
    gut = brauchbar(paare)
    if not gut:
        return "", ["nichts, was morgen noch gilt - Modell nicht gefragt"]

    text = _text(gut[-PAARE_HOECHSTENS:])
    nachrichten = [
        {"role": "system",
         "content": SYSTEM % {"max": ZUSAMMENFASSUNG_ZEICHEN_MAX}},
        {"role": "user", "content": text[:4000]}]
    try:
        antwort = (fragen or _fragen)(nachrichten)
    except Exception as f:
        return "", [f"nicht zusammengefasst ({type(f).__name__})"]
    if not isinstance(antwort, dict):
        return "", ["Antwort war kein Objekt"]

    satz = " ".join(str(antwort.get("zusammenfassung") or "").split())
    if not satz:
        return "", ["Modell hatte nichts zu sagen"]
    # Dieselbe Wache wie beim Fakt, mit der Laenge der Zusammenfassung. Sie
    # faengt das Nacherzaehlen ("Calvin fragte ...") und erfundene Zahlen.
    warum = wissen.mangel(satz, text,
                          zeichen_max=ZUSAMMENFASSUNG_ZEICHEN_MAX)
    if warum:
        return "", [f"{warum}: {satz[:90]}"]
    return satz[:ZUSAMMENFASSUNG_ZEICHEN_MAX], []


SYSTEM_ABLEITEN = f"""Aus einem beendeten Gespraech soll festgehalten werden,
was BLEIBT. Du bekommst die Zusammenfassung und den Wortlaut.

Festgehalten wird, was NEU ist. Nicht alles, was gesagt wurde.

Vier Arten, mehr nicht:

  termin    etwas, das zu einem Zeitpunkt ansteht und an das erinnert werden
            soll. Schreibe das Zeitwort WOERTLICH so in "wann", wie {NAME} es
            gesagt hat: "morgen", "am 14.", "naechsten Dienstag", "morgen
            frueh um zehn". Rechne NICHT selbst und erfinde kein Datum.
  fakt      etwas Dauerhaftes ueber {NAMENS} Welt: wer jemand ist, wie etwas
            heisst, wo etwas liegt.
  vorliebe  was {NAME} will oder nicht will: "keine Push nach 22 Uhr".
  vorhaben  etwas, das er getan haben will: "Kannst du das mal aufraeumen".
            Du HAELTST es fest, damit es nicht verlorengeht. Du fuehrst es
            NICHT aus und faengst nicht damit an - dafuer braucht es seine
            Zustimmung, und die gibt er selbst. Schreibe es als das, was es
            ist: "{NAME} will, dass der Download-Ordner aufgeraeumt wird".

WAS NICHT:
  KEINE Zustandsfragen. Die Uhrzeit, der freie Speicher, wer im Netz ist: Das
  ist morgen falsch.
  KEINE Zahl, die nicht im Gespraech steht.
  NICHTS ueber dich selbst - keine Saetze darueber, was du kannst oder getan
  hast.
  Steht nichts Neues drin, gib eine leere Liste. Das ist eine richtige
  Antwort, keine Luecke.

Jeder Text ist EIN schlichter Satz, der allein verstaendlich ist. Nicht
"morgen zum Arzt", sondern "{NAME} geht mit Lena zum Kinderarzt".

Antworte als JSON:
{{"sachen": [{{"art": "termin", "text": "...", "wann": "morgen"}},
            {{"art": "fakt", "text": "..."}}]}}"""


def ableitbar(paare: list[dict]) -> list[dict]:
    """Strenger als brauchbar() - und zwar aus zwei gemessenen Gruenden.

    brauchbar() sammelt, woraus eine ZUSAMMENFASSUNG werden kann. Was ein FAKT
    werden darf, ist weniger. Der Nachtbericht vom 12.09. hat beides gezeigt,
    und beide Male haette C Muell angelegt:

      "916 MB sind ungefaehr 0,92 GB, 914 MB etwa 0,91 GB."
        Die Frage dazu war "Und wie viel ist das in Gigabyte?" - und die laesst
        `lohnt()` durch, weil sie kein Zustandswort enthaelt. Sie IST aber eine
        Zustandsfrage, geerbt von der davor ("Wer belegt den meisten
        Speicher?"), die lohnt() richtig abweist. Eine Folgefrage auf eine
        verworfene Frage ist selbst verworfen: Taugt das, worauf sie sich
        bezieht, nicht zum Behalten, taugt seine Umrechnung auch nicht.

      "eine neue Datei cpu-z_2.17-en.exe, 4629 KB, im Download-Ordner"
        Das ist eine ANSPRACHE - `frage is None`. brauchbar() behaelt sie mit
        Absicht (B9), denn sie traegt den Anlass der Sitzung. Aber ihr Inhalt
        ist ein FUND, und ein Fund ist Material, kein Wissen - genau die Regel,
        um die bestand.py gebaut ist. Sie darf die Sitzung eroeffnen und
        zusammengefasst werden; einen Fakt gibt sie nicht her.
    """
    heraus = []
    vorher_verworfen = False
    for p in paare:
        if p.get("frage") is None:
            # Eine Ansprache: kein Fakt daraus. Und sie setzt den Bezug nicht,
            # also bleibt `vorher_verworfen`, wie es war.
            continue
        if not wissen.lohnt(p):
            vorher_verworfen = True
            continue
        if vorher_verworfen and _ist_folgefrage(str(p.get("frage") or "")):
            # Sie bezieht sich auf das Verworfene. Mit ihr faellt die Kette
            # weiter - "und in Gigabyte?" und danach "und auf Laufwerk D?".
            continue
        vorher_verworfen = False
        heraus.append(p)
    return heraus


# Woran eine Folgefrage zu erkennen ist: Sie hat kein eigenes Thema, sondern
# haengt an der Frage davor. "Und wie viel ist das in Gigabyte?"
FOLGEFRAGE = re.compile(
    r"^\s*(und|aber|also|ok(ay)?)\b|\b(das|dem|davon|daran|dazu|dort|"
    r"derselbe|dieselbe)\b", re.IGNORECASE)


def _ist_folgefrage(frage: str) -> bool:
    return bool(FOLGEFRAGE.search(frage))


def _bekannt_pruefer():
    """Steht das schon im Gedaechtnis? (C.1)

    Nicht woertlich - ueber die Inhaltswoerter. "Lena ist Calvins Tochter" und
    "Calvins Tochter heisst Lena Marie" sind derselbe Inhalt in anderen Worten,
    und genau das ist Calvins Beispiel: Dass Lena existiert, steht schon da -
    NEU ist der Termin.
    """
    import gedaechtnis

    def bekannt(text: str) -> str:
        kern = gedaechtnis._inhaltswoerter(text)
        if not kern:
            return ""
        for t in gedaechtnis.abrufen(text, 6):
            if gedaechtnis.traegt_weiter(kern, str(t.get("text") or "")):
                return str(t.get("text") or "")
        return ""
    return bekannt


def ableiten(zusammenfassung: str, paare: list[dict], bezug: datetime,
             fragen=None, bekannt=None) -> tuple[list[dict], list[str]]:
    """Was aus einem Gespraech bleiben soll - ohne es anzulegen.

    Gibt (sachen, zurueckgehalten) zurueck. Jede Sache traegt:

        art   termin | fakt | vorliebe
        text  der Satz, der ins Gedaechtnis oder in die Erinnerung geht
        wann  bei einem Termin: der aufgeloeste Zeitpunkt, oder None
        wann_wort  was Calvin gesagt hat ("morgen frueh")
        grund bei wann=None: "unklar", "kein_termin" oder "nichts"

    `bezug` ist der Zeitpunkt der AEUSSERUNG, nicht der der Auswertung - das
    ist die Bedingung, unter der "morgen" ueberhaupt aufloesbar ist (C.2).
    Pflichtparameter, aus demselben Grund wie dort.

    Angelegt wird hier NICHTS. Das tut anwenden(), und nur wenn scharf.
    """
    brauchbare = ableitbar(paare)
    if not brauchbare and not zusammenfassung:
        return [], ["nichts Brauchbares im Gespraech"]

    quelle = _text(brauchbare)
    auftrag = (f"Zusammenfassung: {zusammenfassung}\n\nWortlaut:\n{quelle}"
               if zusammenfassung else f"Wortlaut:\n{quelle}")
    stelle = fragen or _fragen
    try:
        antwort = stelle([{"role": "system", "content": SYSTEM_ABLEITEN},
                          {"role": "user", "content": auftrag}])
    except Exception as f:
        # BREIT gefangen, genau wie in zusammenfassen() - und aus demselben
        # Grund. Eine engere Liste (httpx.HTTPError, ValueError, ...) liess
        # einen RuntimeError durch, und damit waere der Abschlussfaden an einem
        # stolpernden Modell gestorben, statt die Marke auf null zu lassen.
        # Die Nacht holt es dann nach (Anhang 3).
        return [], [f"nicht abgeleitet ({type(f).__name__})"]

    roh = (antwort or {}).get("sachen")
    if not isinstance(roh, list):
        return [], ["Modell ohne Liste"]

    bekannt = bekannt or _bekannt_pruefer()
    sachen, zurueck = [], []
    for eintrag in roh[:12]:
        if not isinstance(eintrag, dict):
            continue
        art = str(eintrag.get("art") or "").strip().lower()
        text = " ".join(str(eintrag.get("text") or "").split())
        if not text:
            continue

        art = ARTEN_GLEICH.get(art, art)
        if art not in ARTEN_ABLEITBAR:
            zurueck.append(f"unbekannte Art {art!r}: {text[:60]}")
            continue

        grund = wissen.mangel(text, quelle)
        if grund:
            zurueck.append(f"{art}: {grund} - {text[:60]}")
            continue

        # C.1: Festgehalten wird, was NEU ist.
        schon = bekannt(text)
        if schon:
            zurueck.append(f"{art} steht schon da: {schon[:60]}")
            continue

        sache = {"art": art, "text": text, "wann": None, "wann_wort": "",
                 "grund": "", "woraus": _woraus(text, brauchbare)}
        # WARUM keine Frage danebensteht, ist nicht dasselbe wie DASS keine
        # danebensteht. Ohne brauchbare Paare hat das Modell nur die
        # Zusammenfassung gesehen - dann GIBT es keine Frage, und "nicht
        # zuordenbar" waere eine Fehlermeldung fuer etwas, das kein Fehler
        # ist. Der Nachtbericht unterscheidet beides nur, wenn es hier
        # entschieden wird; er selbst kann es nicht mehr wissen.
        sache["woraus_art"] = ("frage" if sache["woraus"]
                               else "zusammenfassung" if not brauchbare
                               else "unklar")
        if art == "termin":
            wort = " ".join(str(eintrag.get("wann") or "").split())
            sache["wann_wort"] = wort
            # Das Zeitwort kann auch im Satz stehen, wenn "wann" fehlt.
            wann, warum = zeitwort.aufloesen(wort or text, bezug)
            # DIE UHRZEIT STEHT OFT IM TEXT, NICHT IN "wann". Gemessen mit
            # gpt-oss an Calvins eigenem Satz: Auf "morgen mit Lena zum
            # Kinderarzt, um zehn" kam wann="morgen" und der Text "... um
            # zehn". Aufgeloest ergab das 09:00 - die Standardstunde, nicht
            # die genannte. Ein Termin eine Stunde zu frueh weckt Calvin eine
            # Stunde zu frueh.
            #
            # Nur die UHRZEIT wird nachgeholt, nicht der Tag: Ein zweites
            # Tageswort aus dem Satz koennte dem ersten widersprechen, und
            # dann waere geraten, welches gilt.
            if wann is not None and wort and not zeitwort.uhrzeit_aus(wort):
                uhr = zeitwort.uhrzeit_aus(text)
                if uhr:
                    wann = wann.replace(hour=uhr[0], minute=uhr[1], second=0,
                                        microsecond=0)
            sache["wann"], sache["grund"] = wann, warum
            if wann is None:
                # NICHT anlegen. Ein falscher Termin weckt Calvin um drei.
                zurueck.append(
                    f"Termin ohne Datum ({warum}): {text[:54]}"
                    + (f" [{wort}]" if wort else ""))
                sache["offen"] = True
        sachen.append(sache)
    return sachen, zurueck


# Eine Zahl ab drei Stellen ist ein Anker. `_inhaltswoerter` wirft sie weg -
# es behaelt nur, was laenger als drei Zeichen ist, und genau drei haben "916"
# und "914". Gemessen am Nachtbericht vom 13.09.: Der Kern von "916 MB sind
# ungefaehr 0,92 GB, 914 MB etwa 0,91 GB." war {sind, ungefaehr, etwa} - die
# Zuordnung gelang ueber "sind", nicht ueber die Zahlen. Bei "914 MB frei"
# bleibt {frei}, bei "916 MB" gar nichts, und dann findet sie nie etwas.
#
# Nur HIER, nicht in `_inhaltswoerter` selbst: Daran haengen das Vergessen,
# `bekannt()` und die Pruefung. Was zwei Saetze als denselben Inhalt gelten
# laesst, ist eine andere Frage als die, woher ein Satz stammt.
ZAHL = re.compile(r"\d{3,}")


def _anker(text: str) -> set[str]:
    import gedaechtnis
    return gedaechtnis._inhaltswoerter(text) | set(ZAHL.findall(str(text)))


def _woraus(text: str, paare: list[dict]) -> str:
    """Die Frage, aus der dieser Satz stammt - oder "".

    Ueber die Inhaltswoerter und die Zahlen, nicht woertlich: Das Modell
    formuliert um, und ein Textvergleich faende nie etwas. Gebraucht wird sie
    fuer den Nachtbericht - Calvin entscheidet ueber ABLEITEN_SCHARF, und
    dafuer muss neben dem Satz stehen, WORAUS er stammt.

    Verglichen wird gegen Frage UND Antwort: Der abgeleitete Satz ist meist
    eine Umformulierung der ANTWORT, die Frage allein teilt oft kein Wort mit
    ihm ("Und wie viel ist das in Gigabyte?").
    """
    try:
        kern = _anker(text)
    except Exception:
        return ""
    if not kern:
        return ""
    beste, bestes_mass = "", 0.0
    for p in paare:
        frage = " ".join(str(p.get("frage") or "").split())
        if not frage:
            continue
        zusammen = f"{frage} {p.get('antwort') or ''}"
        try:
            andere = _anker(zusammen)
        except Exception:
            continue
        if not andere:
            continue
        mass = len(kern & andere) / len(kern)
        if mass > bestes_mass:
            beste, bestes_mass = frage, mass
    # Unter einem Drittel Ueberdeckung ist es geraten, nicht gefunden.
    return beste if bestes_mass >= 0.34 else ""


def rueckfragen(sachen: list[dict]) -> list[str]:
    """Woraus ein Redeanlass wird - und woraus ausdruecklich keiner.

    "am 3." am 12. ist eine Terminabsicht mit offenem Monat: Rueckfrage, denn
    umgangssprachlich ist meist der naechste Dritte gemeint - und "meist" ist
    kein Grund, einen Termin zu erfinden. "gestern" dagegen will nichts
    vormerken; eine Rueckfrage waere albern (C.5, B10).
    """
    heraus = []
    for s in sachen:
        if s.get("art") != "termin" or s.get("wann") is not None:
            continue
        if s.get("grund") in ("unklar", "nichts"):
            wort = s.get("wann_wort") or ""
            heraus.append(
                f"Du hast {s['text'][:70]} erwaehnt"
                + (f' - "{wort}" habe ich nicht als Datum verstanden.'
                   if wort else " - ein Datum habe ich nicht verstanden."))
    return heraus


def anwenden(sachen: list[dict], scharf: bool | None = None, merken=None,
             vormerken=None, journal=None, von: str | None = None) -> dict:
    """Die abgeleiteten Sachen anlegen - oder im Trockenlauf nur melden.

    `merken` und `vormerken` sind Parameter, damit die Probe nicht ins echte
    Gedaechtnis und nicht in die echten Erinnerungen schreibt.

    `von` ist die Herkunft der Sitzung und geht an jeder geschriebenen Zeile
    mit. Ohne sie waere spaeter nicht mehr zu erkennen, ob ein abgeleiteter
    Satz aus Calvins Gespraech stammt oder aus einer Messung - genau die Luecke,
    die in der Nacht zum 13.09. bei siebzehn Erinnerungen nicht zu schliessen
    war.

    EIN VORHABEN WIRD HIER FESTGEHALTEN, NICHT AUSGEFUEHRT. Es geht ins
    Gedaechtnis wie ein Fakt und beruehrt weder `kann` noch `anlaesse` noch die
    Auftragsschlange. Es gibt von dieser Stelle keinen Weg zu einer Handlung,
    und das ist die Bedingung, unter der die Art ueberhaupt abgeleitet werden
    darf.
    """
    scharf = ABLEITEN_SCHARF if scharf is None else scharf
    bericht = {"scharf": bool(scharf), "termine": 0, "fakten": 0,
               "vorlieben": 0, "vorhaben": 0, "nur_gemeldet": 0, "fehler": []}

    for s in sachen:
        art, text = s["art"], s["text"]
        if art == "termin" and s.get("wann") is None:
            continue                      # gehoert in rueckfragen(), nicht her
        if not scharf:
            bericht["nur_gemeldet"] += 1
            if journal:
                wann = s.get("wann")
                # DIE FRAGE GEHOERT MIT, und zwar in der Zeile selbst. Calvin
                # soll am Morgen entscheiden, ob ABLEITEN_SCHARF darf - und das
                # kann er nur, wenn er neben dem Satz sieht, WORAUS er stammt.
                # "WUERDE anlegen - fakt: 916 MB sind 0,92 GB" allein sieht wie
                # ein Modellfehler aus; mit "aus: Und wie viel ist das in
                # Gigabyte?" daneben ist es nachvollziehbar.
                journal("ableiten_trocken",
                        f"WUERDE anlegen - {art}: {text}"
                        + (f" (am {wann:%d.%m. %H:%M})" if wann else ""),
                        nicht_erinnern=True, sache=art,
                        woraus=s.get("woraus") or "",
                        woraus_art=s.get("woraus_art") or "unklar",
                        wann_wort=s.get("wann_wort") or "")
            continue

        try:
            if art == "termin":
                if vormerken is None:
                    import sys
                    from pathlib import Path
                    sys.path.insert(0, str(
                        Path(__file__).parent / "werkstatt" / "werkzeuge"))
                    import erinnern
                    erinnern.merken(text,
                                    wann=s["wann"].strftime("%Y-%m-%d %H:%M"))
                else:
                    vormerken(text, s["wann"])
                bericht["termine"] += 1
            else:
                wichtig = art == "vorliebe"
                # Ein Vorhaben bekommt eine EIGENE Art im Gedaechtnis. Als
                # "fakt" abgelegt waere es ununterscheidbar von dem, was ist -
                # und "Calvin will, dass aufgeraeumt wird" ist kein Zustand,
                # sondern ein offener Wunsch. Die eigene Art ist auch die
                # Voraussetzung dafuer, dass er sie gezielt abfragen kann.
                ziel_art = "vorhaben" if art == "vorhaben" else "fakt"
                if merken is None:
                    import gedaechtnis
                    gedaechtnis.merken(ziel_art, text, quelle="abgeleitet",
                                       wichtig=wichtig, von=von)
                else:
                    merken(ziel_art, text, wichtig)
                if art == "vorhaben":
                    bericht["vorhaben"] += 1
                else:
                    bericht["vorlieben" if wichtig else "fakten"] += 1
        except Exception as f:
            bericht["fehler"].append(f"{art}: {type(f).__name__}")
    return bericht


def abschliessen(sid: str, jetzt: float | None = None, fragen=None,
                 merken=None, journal=None, merken_sache=None,
                 vormerken=None) -> dict:
    """Eine Sitzung schliessen, zusammenfassen, ins Gedaechtnis legen.

    Die Reihenfolge ist nicht beliebig: Die Marke `geschlossen` wird VOR der
    Arbeit gesetzt (Anhang 3). Sie ist der Anspruch auf die Sitzung - setzte
    sie erst, wer fertig ist, griffen zwei Faeden dieselbe Sitzung und es
    entstuenden zwei Zusammenfassungen.

    `merken` und `journal` sind Parameter, damit die Probe nicht ins echte
    Gedaechtnis schreibt. Zweimal ist an genau dieser Stelle heute schon eine
    Probe ins Echte gelaufen.

    `merken_sache` und `vormerken` sind dasselbe fuer den ABGELEITETEN Teil,
    und sie haben gefehlt. `merken` deckt nur die Zusammenfassung; was
    `anwenden()` anlegt, ging bis zum 13.09. ungefragt ins Echte - im
    Trockenlauf fiel das nicht auf, weil dort nichts angelegt wurde. Beim
    ersten scharfen Probenlauf stand um 12:12 ein erfundener Arzttermin in
    erinnerungen.json. Die eigenen Signaturen sind Absicht: `merken` gehoert
    zur Sitzung (art, text, sid), `merken_sache` zur Sache (art, text,
    wichtig).
    """
    jetzt = time.time() if jetzt is None else jetzt
    kopf = sitzung.kopf(sid) or {}
    vorige = kopf.get("zusammenfassung")
    sitzung.schliessen(sid, jetzt)

    paare = sitzung.paare(sid)
    satz, zurueck = zusammenfassen(paare, fragen=fragen)
    bericht = {"id": sid, "paare": len(paare), "zusammenfassung": satz,
               "zurueckgehalten": zurueck, "gemerkt": 0}

    # Eine Sitzung, die nicht Calvins ist, bekommt KEINE Erinnerung. Regel 0
    # haelt Testfragen schon aus den Sitzungen heraus, aber die Erinnerung
    # selbst traegt keine Herkunft: die Tabelle `erinnerung` hat kein `von`,
    # und `quelle` sagt nur "Sitzung s-...". Was hier einmal hineinkommt, ist
    # spaeter nicht mehr als Messung zu erkennen - der Rueckblick erzaehlte
    # darum am 13.09. "die Diskussion ueber Spielarten" als Calvins Gespraech.
    # Der Riegel gehoert an die Stelle, die schreibt.
    import passiert

    if satz and not passiert.ist_vom_nutzer(kopf):
        bericht["nicht_gemerkt"] = f"von {kopf.get('von')!r}, keine Erinnerung"
        if journal:
            journal("sitzung_fremd",
                    f"{sid}: zusammengefasst, aber NICHT gemerkt - die "
                    f"Sitzung ist von {kopf.get('von')!r}, nicht von {NAME}.",
                    id=sid, von=kopf.get("von"), nicht_erinnern=True)
        sitzung.marke_setzen(sid, "zusammenfassung", satz)
        return bericht

    if satz:
        if merken is None:
            import gedaechtnis
            # Wird eine wieder aufgenommene Sitzung erneut geschlossen, gibt
            # es die alte Zusammenfassung schon im Gedaechtnis. Sie wird
            # UEBERHOLT, nicht geloescht - Calvins Regel, und dieselbe, die
            # F.1 auf die 43 Protokolle angewandt hat.
            alt = (gedaechtnis.kennung_von("sitzung", vorige)
                   if vorige else None)
            bericht["gemerkt"] = gedaechtnis.merken(
                "sitzung", satz, quelle=f"Sitzung {sid}", ersetzt=alt,
                von=kopf.get("von"))
            bericht["ueberholt"] = alt
        else:
            bericht["gemerkt"] = merken("sitzung", satz, sid) or 0
        sitzung.marke_setzen(sid, "zusammenfassung", satz)
    elif zurueck and zurueck[0].startswith("nichts"):
        # Eine Sitzung aus lauter "Wie spaet ist es?" ist fertig bearbeitet,
        # nicht liegengeblieben. Die leere Marke sagt genau das - sonst holt
        # die Nacht sie jede Nacht wieder und fragt jedes Mal das Modell.
        sitzung.marke_setzen(sid, "zusammenfassung", "")
    # Sonst bleibt die Marke auf null: Das Modell hat nicht geantwortet, und
    # die naechtliche Gegenpruefung holt es nach (Anhang 3).

    # `von` MUSS mit. Ohne dieses Feld kann die Chronik nicht unterscheiden,
    # ob ein Gespraech Calvins war oder eine Messung - und am 13.09. erzaehlte
    # sie ihm die vier Fragen aus zuhause_probe.py als seine Nacht: "22:30
    # diskutierte man ueber Spielarten und Desktop". Der Absender steht im
    # Kopf, oben gelesen; er kam nur nie bis hierher.
    if journal:
        woher = kopf.get("von")
        if satz:
            journal("sitzung", satz, id=sid, paare=bericht["paare"],
                    von=woher)
        else:
            journal("sitzung_still",
                    f"{sid}: {zurueck[0] if zurueck else 'nichts'}",
                    id=sid, paare=bericht["paare"], nicht_erinnern=True,
                    von=woher)

    # C: Ableiten. Der Bezugspunkt ist die AEUSSERUNG - die letzte Frage der
    # Sitzung, nicht `jetzt`. Sonst waere "morgen", um 23:50 gesagt und um
    # 00:05 ausgewertet, der falsche Tag (C.2).
    # `satz` ausdruecklich mitgeben, NICHT aus `kopf` holen: Der Kopf ist oben
    # gelesen worden, vor marke_setzen() - darin stand die Zusammenfassung des
    # VORIGEN Abschlusses, meist None. C hat darum von Anfang an ohne
    # Zusammenfassung abgeleitet, nur mit dem Wortlaut. Aufgefallen ist es
    # erst, als ableitbar() strenger wurde und eine Sitzung aus lauter
    # Ansprachen gar keinen Modellaufruf mehr ausloeste.
    bericht["abgeleitet"] = _ableiten_fuer(sid, kopf, paare, fragen, journal,
                                          zusammenfassung=satz,
                                          merken=merken_sache,
                                          vormerken=vormerken)
    return bericht


def _ableiten_fuer(sid: str, kopf: dict, paare: list[dict], fragen,
                   journal, zusammenfassung: str = "", merken=None,
                   vormerken=None) -> dict:
    """Der C-Teil von abschliessen() - getrennt, damit er einzeln pruefbar ist.

    Laeuft NICHT erneut, wenn die Marke `abgeleitet` schon steht: Ein zweiter
    Durchgang ueber dieselbe Sitzung kostet sonst einen Modellaufruf und legte
    im scharfen Betrieb denselben Termin zweimal an.
    """
    if kopf.get("abgeleitet") is not None:
        return {"uebersprungen": "schon abgeleitet"}
    if not paare:
        sitzung.marke_setzen(sid, "abgeleitet", "")
        return {"uebersprungen": "kein Wortlaut"}

    letzte = max((p.get("ts") or 0) for p in paare) or time.time()
    bezug = datetime.fromtimestamp(letzte)

    sachen, zurueck = ableiten(zusammenfassung or "", paare, bezug,
                               fragen=fragen)
    fragen_offen = rueckfragen(sachen)
    angewandt = anwenden(sachen, journal=journal, von=kopf.get("von"),
                         merken=merken, vormerken=vormerken)

    if journal:
        for grund in zurueck:
            journal("ableiten_zurueck", grund, id=sid, nicht_erinnern=True)
        for frage in fragen_offen:
            # Als REDEANLASS, nicht als Push. Eine Sache, die nur Calvin
            # entscheiden kann, wird gefragt - nicht geraten (C.5).
            journal("rueckfrage", frage, id=sid, nicht_erinnern=True)

    # Die Marke traegt, WAS abgeleitet wurde - nicht nur, dass es lief. Im
    # Trockenlauf steht dort "trocken: N", damit danach nachzulesen ist, was
    # der scharfe Betrieb getan haette.
    marke = ("trocken: %d" % angewandt["nur_gemeldet"]
             if not angewandt["scharf"]
             else "%d Termine, %d Fakten, %d Vorlieben, %d Vorhaben"
                  % (angewandt["termine"], angewandt["fakten"],
                     angewandt["vorlieben"], angewandt["vorhaben"]))
    sitzung.marke_setzen(sid, "abgeleitet", marke)
    return {"sachen": len(sachen), "zurueckgehalten": zurueck,
            "rueckfragen": fragen_offen, **angewandt}


def durchgang(jetzt: float | None = None, fragen=None, merken=None,
              journal=None, merken_sache=None, vormerken=None) -> dict | None:
    """HOECHSTENS EINE faellige Sitzung - die aelteste. Sonst None.

    Eine, nicht alle (B11 des Mac): Nach einem Ausfall liegen mehrere da, und
    sie hintereinander zusammenzufassen waeren mehrere Modellaufrufe am
    Stueck, waehrend Calvin vielleicht gerade redet. Der Faden sieht jede
    Minute nach; der Rest kommt beim naechsten Mal.
    """
    jetzt = time.time() if jetzt is None else jetzt
    kopf = sitzung.faellig(jetzt)
    if kopf is None:
        return None
    return abschliessen(kopf["id"], jetzt, fragen=fragen, merken=merken,
                        journal=journal, merken_sache=merken_sache,
                        vormerken=vormerken)


def main() -> int:
    import sys
    # --jetzt greift in den laufenden Betrieb: Der Abschlussfaden des Bewohners
    # tut jede Minute dasselbe, und zwei Prozesse, die dieselbe Sitzung
    # schliessen, fragen das Modell zweimal. `geschlossen` verhindert, dass
    # daraus zwei Zusammenfassungen werden, aber nicht, dass es zwei Aufrufe
    # kostet. Zum Messen gedacht, nicht fuer den Betrieb.
    if "--jetzt" in sys.argv:
        b = durchgang()
        print(json.dumps(b, ensure_ascii=False, indent=1) if b
              else "keine faellige Sitzung.")
        return 0
    for k in sitzung.lesen()[-20:]:
        z = k.get("zusammenfassung")
        marke = "offen" if not k.get("geschlossen") else (
            "ohne Zusammenfassung" if z is None else
            "nichts zu sagen" if z == "" else z)
        print("%s  %2d Paare  %s" % (k.get("id"), k.get("paare") or 0, marke))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
