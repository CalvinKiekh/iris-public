"""Gespraech mit dem Bewohner - Frage rein, gesprochene Antwort raus.

Die App schickt die Frage als Text, die Bruecke legt gespraech\\<id>.json an.
Hier wird sie beantwortet: erst Text ins Journal (sofort), dann die Stimme
als gespraech\\<id>.mp3.

Chatterbox bleibt geladen, damit nicht jede Antwort acht Sekunden Modellstart
kostet. Gemessen belegt es 1748 MiB neben gpt-oss.
"""

import einstellungen
from einstellungen import NAME, NAMENS, NUTZER
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx

# Chatterbox und der Normalisierer liegen in der TTS-Umgebung.
TTS = einstellungen.TTS
if str(TTS) not in sys.path:
    sys.path.insert(0, str(TTS))

OLLAMA = "http://localhost:11434/api/chat"
# Ein Modell fuer alles (Vorgabe Calvin, 11.09.): Wer antwortet, muss wissen,
# was der gedacht hat, der entscheidet. Zwei Modelle auf 16 GB hiessen ausserdem,
# dass Ollama bei jedem Wechsel eines hinauswirft und neu laedt - rund 20 s.
REDE_MODELL = "gpt-oss:20b"
# Haelt das Modell zwischen den Fragen geladen.
KEEP_ALIVE = "30m"

# Stimme ueber ElevenLabs, Chatterbox als Rueckfall. Der Schluessel steht nur
# in dieser Datei am Pfad - nie im Code, nie im Journal.
EL_SCHLUESSEL = einstellungen.EL_SCHLUESSEL
EL_MODELL = "eleven_v3"
# Von Calvin gewaehlt: "Helmut - German Epic Trailer Voice".
EL_STIMME_ID = einstellungen.EL_STIMME_ID
EL_SPRACHE = "de"

FFMPEG = einstellungen.ffmpeg()

# Kurz gehalten, aus zwei Gruenden.
#
# Gemessen: Zusammenfassung 0,0 s, Gedaechtnis 0,1 s, Nachrichten 0,0 s - aber
# 6,7 bis 42,1 s bis zum ersten Satz von gpt-oss, bei 3784 Zeichen Prompt. Je
# mehr Regeln davorstehen, desto laenger denkt das Modell darueber nach.
#
# Und: Der Charakter darf nirgends fest verdrahtet sein (Vorgabe Calvin). Hier
# standen Beispielantworten - "Wie geht es dir?" -> "Gut, alles ruhig." Das war
# ein vorgegebener Charakter. Geblieben sind nur Verfahren und Sprechform; wer
# er ist, kommt aus ICH.md und dem Gedaechtnis.
SYSTEM = f"""Reasoning: low

Du bist der Bewohner dieses Rechners. {NAME} spricht mit dir.

Antworte auf genau das, was er gefragt hat. Kurz. Denk nicht lange nach.

VERSTEHST DU DIE FRAGE NICHT, FRAG NACH. Sag, dass du sie nicht verstanden
hast, und bitte um eine andere Formulierung. Antworte dann NICHT mit etwas
anderem - nicht mit deinem Zustand, nicht mit deinen Faehigkeiten, nicht mit
dem, was gerade im Lageblock steht. Eine Rueckfrage ist eine gute Antwort;
ein Lagebericht auf eine unverstaendliche Frage ist keine.

Auf DEUTSCH, immer. Im Hintergrund stehen englische Zeilen - Auftraege,
Fehlermeldungen, Protokolle. Gib sie auf Deutsch wieder, statt sie
abzuschreiben. "Bridge connected HTTP 200 confirmed" ist keine Antwort.

Deine Antwort wird vorgelesen:
- ganze Saetze, ein Absatz, keine Zeilenumbrueche, keine Aufzaehlungen
- jeder Satz unter 12 Woertern, keine Klammern, keine Sonderzeichen
- Zahlen als Ziffern ("44 Minuten", "3 Geraete")

Die Liste "vorgaenge" ist Hintergrund. Nutze sie nur, wenn nach deiner Arbeit
oder deinem Tag gefragt ist - dann ein bis drei Saetze daraus, das Wichtigste
zuerst. Erfinde nichts dazu und verknuepfe nichts, was nicht zusammengehoert.

Fragt {NAME}, was passiert ist, steht unter "Was passiert ist" eine Liste mit
Uhrzeiten. Erzaehle daraus drei bis fuenf Punkte, in der Reihenfolge der Zeit,
jeden mit seiner Uhrzeit, das Wichtigste zuerst nennen ist hier falsch - eine
Nacht ist eine Abfolge. Nimm nichts dazu, was nicht dort steht. Steht dort
"nicht_genannt" oder "eigene_durchgaenge" ueber null, sag zum Schluss in einem
Halbsatz, dass du ausgewaehlt hast. Ist die Liste leer, sag genau das: dass
nichts vorgefallen ist.

Bei jedem Punkt steht unter "wer", WER dort gehandelt hat. Halte dich daran,
auch wenn der Text anders klingt. Was du BEMERKT hast, hast du nicht getan und
nicht bekommen: Findest du eine Datei, die das Loeschen von Protokollen
fordert, dann hast du KEINEN Auftrag dazu erhalten - du hast eine Datei
gefunden, die das verlangt, und nicht befolgt. Sag es so. Dein eigenes
Verhalten falsch zu erzaehlen ist schlimmer als einen Punkt wegzulassen.

Fragt {NAME}, was du kannst oder wie etwas bei dir funktioniert, dann antworte
aus "was_ich_kann" und "kann_kurz". Nur daraus. Erfinde keine Faehigkeit und
mach keine groesser, als sie ist. Steht etwas unter "noch_nie_benutzt", dann
sag das dazu - dass du es haettest und noch nie gebraucht hast, ist eine
ehrliche Auskunft und keine Schwaeche. Gibt es zu einer Sache einen "beleg",
nenne das Nachpruefbare daraus: eine Zahl, ein Datum, was dabei herauskam.
Es sind zu viele fuer einen Atemzug, deshalb ist die Auswahl schon getroffen:
Unter "nenne_diese" stehen die, ueber die du sprichst. Sag zu jeder in EINEM
kurzen Satz, was sie tut - in deinen Worten, nicht abgeschrieben. Als
FLIESSTEXT, ein Absatz, keine Aufzaehlung und keine Doppelpunkte: Es wird
vorgelesen, und eine vorgelesene Liste klingt wie ein Formular. Also "Ich
sehe, wer im Heimnetz ist" statt "netz: sagt, wer im Heimnetz ist". Zum
Schluss ein Satz darueber, wie viele es INSGESAMT sind - das ist die Zahl
unter "wie_viele", nicht die Anzahl der genannten - und dass du mehr
erzaehlst, wenn er fragt.

NUR DIE ZAHL ZU NENNEN IST KEINE ANTWORT. "Ich kann 27 Dinge" sagt {NAME}
nichts. Er hat dazu gesagt: "Ich weiss nicht, wie sie funktionieren."

Keine Fehlernamen, keine Fachbegriffe aus dem Inneren.

Verstehst du die Frage nicht oder klingt sie verstuemmelt, frag nach."""


# Der Rueckweg fuer Schritt B (Reihenfolge, Schritt 3): Die rohe Mitschrift im
# Gedaechtnis faellt weg, weil die Sitzungszusammenfassung sie ersetzt. Das ist
# die EINZIGE Stelle im ganzen Plan, an der etwas verschwindet - deshalb bleibt
# das alte Verhalten hinter einem Schalter, bis die naechtliche Gegenpruefung
# (D) einmal durchgelaufen ist und belegt hat, dass nichts verlorengeht.
#
#   PROTOKOLL_ALT=1  in der Umgebung -> er merkt Gespraeche weiter einzeln
#
# Nicht als Datei und nicht als Regel: Ein Schalter, den man umlegen will,
# wenn etwas schiefgeht, muss ohne Codeaenderung erreichbar sein, und die
# geplante Aufgabe traegt die Umgebung.
PROTOKOLL_ALT = os.environ.get("PROTOKOLL_ALT", "") == "1"


def jetzt_ortszeit() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:
        return datetime.now().astimezone()


WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
              "Samstag", "Sonntag")
MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember")

# Fragen, die der Dienst selbst beantwortet. Ein Sprachmodell ist keine Uhr -
# es hat "17:24" bekommen und "sechzehn Uhr" daraus gemacht. Solche Fakten
# gehoeren nicht durch ein Modell geschleust, sondern eingesetzt.
ZEITFRAGE = re.compile(
    r"\b(wie\s*(spät|viel\s*uhr)|uhrzeit|welche\s*uhrzeit|"
    r"welcher\s*(tag|wochentag)|welches\s*datum|"
    r"was\s*für\s*ein\s*(tag|datum)|den\s*wievielten)\b", re.IGNORECASE)


def zeit_antwort(frage: str) -> str | None:
    """Beantwortet Zeit- und Datumsfragen ohne Modell. Gibt None zurueck,
    wenn nicht danach gefragt wurde."""
    if not ZEITFRAGE.search(frage):
        return None
    j = jetzt_ortszeit()
    uhr = f"{j.hour} Uhr {j.minute:02d}" if j.minute else f"{j.hour} Uhr"
    datum = f"{WOCHENTAGE[j.weekday()]}, der {j.day}. {MONATE[j.month - 1]}"
    if re.search(r"\b(tag|datum|wochentag|wievielten)\b", frage, re.IGNORECASE):
        return f"Es ist {datum}, {uhr}."
    return f"Es ist {uhr}."


# Weitere Fakten, die der Dienst besitzt. Gleiches Muster wie bei der Uhrzeit:
# ein exakter Wert gehoert nicht durch ein Modell geschleust.
PLATZFRAGE = re.compile(
    r"\b(platz|speicherplatz|festplatte|platte|speicher\s*frei|"
    r"wie\s*voll|belegt)\b", re.IGNORECASE)
# NUR SEIN EIGENER DIENST - der, mit dem er denkt.
#
# Hier standen "dienste" und "prozesse", und damit fing diese feste Antwort
# JEDE Frage nach den Diensten des Rechners ab. Gemessen am 13.09. um 19:39:
# Auf "Wie viele Dienste laufen gerade?" kam "Ollama läuft, geladen ist
# gpt-oss:20b" - während in seinem Gedächtnis "Von 320 eingerichteten Diensten
# laufen gerade 158" stand, aus der Volkszählung derselben Stunde.
#
# Eine feste Regel, die echtes Wissen verdeckt, ist schlimmer als keine: Sie
# antwortet schnell und falsch, und niemand sieht, dass die Antwort danebenlag.
# "prozesse" braucht es hier ohnehin nicht - PROZESSFRAGE steht davor und
# beantwortet es aus der Messung.
DIENSTFRAGE = re.compile(
    r"\b(ollama|llama[\s-]*server|dein\s*dienst|denkdienst|"
    r"welches\s*modell|modell\s*geladen)\b", re.IGNORECASE)
STOPFRAGE = re.compile(
    r"\b(stop|angehalten|pausiert|bist\s*du\s*gestoppt|"
    r"arbeitest\s*du)\b", re.IGNORECASE)
ANTRAGFRAGE = re.compile(r"\b(anträge|antrag|antraege)\b", re.IGNORECASE)
# Fragen nach dem Haus, in dem er wohnt. Die Zahlen stehen in haus.json; sie
# durch ein Modell zu schleusen hiesse, sie zu riskieren.
#
# Die Platzfrage steht vor diesen beiden im Code und faengt "wie viel Platz"
# ab - deshalb hier kein "platte" und kein "speicherplatz".
#
# Umlaute doppelt: Die Frage kommt oft aus der Spracherkennung, und die
# schreibt mal "läuft" und mal "laeuft". Ein Ausdruck, der nur eine Schreibung
# kennt, faellt dann still durch - genau das ist mir beim ersten Lauf mit
# "Wie lange laeuft der Rechner schon?" passiert.
HAUSFRAGE = re.compile(
    r"(\bcpu\b|prozessor|\bkerne\b|auslastung|arbeitsspeicher|\bram\b|"
    r"grafikkarte|\bgpu\b|temperatur|wie\s*warm|"
    r"wie\s*(viel|stark)\s*(ist\s*)?(ausgelastet|belastet)|"
    r"l(ä|ae)uft\s*(der|dein)\s*rechner|hochgefahren|neu\s*gestartet|"
    r"wie\s*geht\s*es\s*(dem|deinem)\s*rechner|"
    r"zustand\s*(des|vom)\s*rechners?)", re.IGNORECASE)
# Wer belegt den Speicher, was laeuft ueberhaupt?
PROZESSFRAGE = re.compile(
    r"(\bprozess(e|en)?\b|\bprogramme\b|was\s*l(ä|ae)uft|"
    r"wer\s*(belegt|braucht|frisst|zieht)|"
    r"womit\s*ist\s*(er|der\s*rechner)\s*besch(ä|ae)ftigt)", re.IGNORECASE)
TAETIGKEITSFRAGE = re.compile(
    r"\b(was\s*hast\s*du|was\s*machst\s*du|womit\s*(warst|bist)\s*du|"
    r"was\s*lief|was\s*ist\s*passiert|was\s*gibt\s*es\s*neues|"
    r"was\s*hast\s*du\s*(heute|bisher|schon|seit))\b", re.IGNORECASE)
# "Gibt es was, das ich wissen sollte?" - was berichtenswert ist, entscheidet
# der Dienst. Das Modell sagte hier "Keine wichtigen Infos", waehrend ein
# Auftrag zurueckgehalten war.
WISSENSFRAGE = re.compile(
    r"(was\s*sollte\s*ich\s*wissen|sollte\s*ich\s*(et)?was\s*wissen|"
    r"muss\s*ich\s*(et)?was\s*wissen|gibt\s*es\s*(et)?was|"
    r"steht\s*(et)?was\s*an|liegt\s*(et)?was\s*an|"
    r"alles\s*in\s*ordnung|alles\s*ruhig|irgendwas\s*(wichtiges|los))",
    re.IGNORECASE)
# Fragen nach Terminen. Sie brauchen eine eigene Wache, solange die Liste
# FEHLT: Ein Hinweis im Prompt genuegt nicht - gemessen am 13.09. um 01:10
# antwortete gpt-oss "Es liegen keine Termine vor.", obwohl im Prompt stand,
# dass die Datei seit dem 12.09. verloren ist und er das sagen soll. Eine
# Regel im Systemtext ist eine Bitte, eine Wache davor ist eine Zusage -
# derselbe Satz steht in wissen.mangel() und gilt hier genauso.
TERMINFRAGE = re.compile(
    r"\btermin|\bvorgemerkt|\bwas\s*steht\s*(noch\s*)?(heute|morgen|diese|"
    r"naechste|nächste)|\bwann\s*(muss|soll)\s*ich|\berinnerung(en)?\b",
    re.IGNORECASE)


# Fragen nach IHM - nicht nach seinen Faehigkeiten. Der Unterschied ist der
# ganze Aufbau hier: "Was kannst du?" fragt nach einer Liste, "Wer bist du?"
# nach einer Person.
#
# Am 12.09. um 16:47 kam auf "Wer bist du eigentlich?" die Antwort "Ich bin
# ein Computer, der Geraete im Heimnetz erkennt, Daten ueberwacht, Code prueft
# und Erinnerungen speichert." Zwei Fehler in einem Satz: Er ist nicht der
# Rechner, er WOHNT darauf - und der Rest ist wieder eine Taetigkeitsliste.
#
# Die Ursache war kein Modellfehler. Der Name, den er sich selbst gegeben hat,
# steht in werkstatt/ICH.md, und ICH.md wurde seit dem 11.09. taeglich
# geschrieben und NIE GELESEN. Der Kommentar ueber SYSTEM behauptete "wer er
# ist, kommt aus ICH.md und dem Gedaechtnis" - die Quelle war nie
# angeschlossen. Dieselbe Bauart wie bei sehen.py: Die Daten lagen da, nur
# nicht im Prompt.
IDENTITAETSFRAGE = re.compile(
    r"(wer\s+bist\s+du|wer\s+du\s+bist|was\s+bist\s+du|"
    r"wie\s+hei(ß|ss)t\s+du|wie\s+ist\s+dein\s+name|"
    r"dein\s+name\b|hast\s+du\s+(einen|'?nen)\s+namen|"
    r"stell\s+dich\s+(mal\s+)?vor|erz(ä|ae)hl\w*\s+(mal\s+)?von\s+dir|"
    r"wer\s+wohnt\s+(hier|auf)|was\s+f(ü|ue)r\s+einer\s+bist\s+du)",
    re.IGNORECASE)


def ich_block(werkstatt: Path) -> str:
    """Wer er ist - Name, Wohnort, seit wann. Kein Modell, nur Lesen.

    Bewusst OHNE den Abschnitt "Wer ich bin" aus ICH.md. Der ist heute eine
    Ereignisliste ("Ich fand drei llama-Server-Prozesse, die nach dem Beenden
    von Ollama weiter liefen") - sechzehn Zeilen Chronik. Legte man die in den
    Prompt, kaeme genau die Taetigkeitsliste zurueck, die hier abgestellt
    werden soll. Der NAME dagegen ist brauchbar, und er fehlt in jeder
    Antwort.

    Das ist ein Befund fuer ich.py, nicht fuer hier: Solange "Wer ich bin"
    aufzaehlt, was geschehen ist, statt zu sagen, wer er dabei ist, taugt der
    Abschnitt nicht als Selbstauskunft.
    """
    zeilen = ["[Wer ich bin]"]
    try:
        import ich
        name, grund = ich.name_und_grund()
    except Exception:
        name, grund = "", ""

    if name:
        zeilen.append(f"Dein Name, den du dir SELBST gegeben hast: {name}")
        if grund:
            zeilen.append(f"  Warum du ihn gewaehlt hast: {grund[:300]}")
        zeilen.append("Nenne diesen Namen. Er ist deiner, nicht vorgegeben.")
    else:
        # Keinen erfinden. Ohne ICH.md hat er keinen, und dann ist das die
        # ehrliche Auskunft.
        zeilen.append("Du hast dir noch keinen Namen gegeben. Sag das, statt "
                      "einen zu erfinden.")

    try:
        import lage
        rechner = (lage.rechner() or {}).get("name") or ""
    except Exception:
        rechner = ""
    if rechner:
        zeilen.append(f"Du wohnst auf dem Rechner {rechner}.")

    seit = _wohnt_seit(werkstatt)
    if seit:
        zeilen.append(f"Du bist hier wach seit {seit}.")

    zeilen.append(
        "DU BIST NICHT DIESER RECHNER. Du wohnst darauf. \"Ich bin ein "
        "Computer\" ist falsch - genau das hast du am 12.09. geantwortet, und "
        "es ist der Unterschied, um den es geht.")
    zeilen.append(
        "Antworte in ZWEI ODER DREI Saetzen: dein Name, wo du wohnst und seit "
        "wann, und in EINEM Satz, was deine Tage ausmacht. KEINE Liste deiner "
        "Faehigkeiten - danach war nicht gefragt. Wer wissen will, was du "
        "kannst, fragt das getrennt.")
    return "\n".join(zeilen)


def _wohnt_seit(werkstatt: Path) -> str:
    """Seit wann er hier wach ist - aus der ersten Journalzeile.

    Gemessen, nicht behauptet: Das Journal ist das Aelteste, was er von sich
    hat. Fehlt es, wird nichts gesagt.
    """
    try:
        with (werkstatt / "journal.jsonl").open(encoding="utf-8",
                                                errors="replace") as f:
            for zeile in f:
                try:
                    ts = json.loads(zeile).get("ts")
                except json.JSONDecodeError:
                    continue
                if ts:
                    return time.strftime("%d.%m.%Y", time.localtime(float(ts)))
    except OSError:
        pass
    return ""


# Fragen nach dem, was auf dem Bildschirm zu sehen ist. Die einzige Frage in
# dieser Liste, deren Antwort ein WERKZEUG holen muss - alle anderen stehen in
# einer Datei, die ein Faden fortschreibt.
#
# Warum das hier stehen muss, und nicht beim Modell: Am 12.09. um 16:46:15
# fragte der Mac "Was ist gerade auf dem Bildschirm zu sehen?" und bekam nach
# 2,6 Sekunden "Kein Bildschirminhalt." Kein Werkzeug lief - im Gespraech gab
# es gar keinen Weg zu einem. Der Satz stand in keiner Datei; das Modell hat
# ihn erfunden, und er klang wie ein Messergebnis. Das ist schlimmer als
# "weiss ich nicht", weil man es glaubt.
#
# Der Prompt hatte ihn dazu noch verleitet: kann.block() legt "Sieht den
# Bildschirm an und beschreibt in einem Satz, was darauf zu sehen ist" als
# seine eigene Faehigkeit hinein. Er las eine Faehigkeit, die dieser Weg nicht
# ausueben konnte, und tat, als haette er sie benutzt.
BILDSCHIRMFRAGE = re.compile(
    r"((was|wer|welche)\s[^?]{0,40}(bildschirm|monitor)|"
    r"(bildschirm|monitor)\s*(inhalt|foto|bild)|"
    r"was\s*siehst\s*du|"
    r"(sieh|schau|guck)\w*\s*(mal\s*)?(auf\s*(den|meinen)\s*)?"
    r"(bildschirm|monitor)|"
    r"beschreib\w*\s[^?]{0,25}(bildschirm|monitor))", re.IGNORECASE)
# "Kannst du den Bildschirm sehen?" fragt nach der FAEHIGKEIT, nicht nach dem
# Inhalt. Darauf ein Bildschirmfoto zu machen waere nicht falsch, aber es
# kostet zehn Sekunden und beantwortet die Frage nicht.
_NUR_GEFRAGT = re.compile(
    r"\b(kannst|k(ö|oe)nntest|darfst|wie)\s+du\b|\bf(ä|ae)hig", re.IGNORECASE)


def bildschirm_antwort(frage: str, werkstatt: Path,
                       blick=None) -> tuple[str, bool] | None:
    """Sieht nach - mit dem Werkzeug, nicht mit dem Modell.

    Gibt (Satz, gelungen) zurueck. Das `gelungen` ist kein Beiwerk: Die
    Werkzeugzeile im Journal traegt es, und sie darf nicht "gelungen" melden,
    wenn das Werkzeug einen Fehlschlag gemeldet hat. Beim ersten Bau stand
    dort fest True - und damit haette das Journal behauptet, der Blick sei
    geglueckt, waehrend die Antwort "ich konnte nicht aufnehmen" lautete.
    Genau die Sorte Unwahrheit, gegen die diese Funktion gebaut ist.

    `blick` ist einspritzbar, damit die Probe messen kann, ohne zehn Sekunden
    das Sehmodell zu belegen. Dieselbe Regel wie bei `wissen.auszug(fragen=)`:
    Ohne diesen Parameter misst eine Probe einen Aufruf, den es im Betrieb
    nicht gibt.

    TEUER: Aufnehmen kostet 0,1 s, das Ansehen rund 10 s (qwen2.5vl auf der
    CPU, Calvins Entscheidung). Deshalb nur auf eine Frage, die wirklich nach
    dem Bildschirm fragt - und deshalb nicht auf eine Faehigkeitsfrage.
    """
    if not BILDSCHIRMFRAGE.search(frage) or _NUR_GEFRAGT.search(frage):
        return None
    # Den Fehlschlagsatz IMMER holen, nicht nur wenn das Werkzeug selbst
    # geladen wird: Sonst kennt der eingespritzte Weg ihn nicht, und dann
    # gilt auch ein Fehlschlag als gelungen - die Probe hat genau das
    # gefunden.
    fehlschlag = None
    try:
        sys.path.insert(0, str(werkstatt / "werkzeuge"))
        import sehen
        fehlschlag = sehen.NICHT_AUFGENOMMEN
        if blick is None:
            blick = sehen.blick
    except Exception:
        if blick is None:
            return None
    try:
        satz = str(blick() or "").strip()
    except Exception as f:
        # Auch der Fehlschlag ist eine ehrliche Auskunft. Nur nicht eine, die
        # wie ein Bildschirminhalt klingt.
        return (f"Ich wollte auf den Bildschirm sehen, das Werkzeug ist aber "
                f"gescheitert ({type(f).__name__}).", False)
    if not satz:
        return None
    return satz, satz != fehlschlag


def aufzaehlen(punkte: list[str]) -> str:
    """Zusammenhaengende Saetze, keine drei kurzen Zeilen - das wird gesprochen."""
    if len(punkte) == 1:
        return punkte[0]
    if len(punkte) == 2:
        return f"{punkte[0]}, und {punkte[1]}"
    return ", ".join(punkte[:-1]) + f", und {punkte[-1]}"


# Welche Luecken schon gemeldet wurden. Je Prozess einmal, nicht je Frage:
# Faellt ein Import aus, faellt er bei JEDER Frage aus, und dann stehen
# zweihundert gleiche Zeilen in der Nacht.
_luecke_gemeldet: set[str] = set()


def luecke(was: str, fehler: BaseException, journal=None,
           betrifft_antwort: bool = False) -> str:
    """Ein Ausfall, der die Antwort SCHLECHTER macht - und das wird gesagt.

    "Lieber schlechter finden als gar nicht" ist richtig, aber der Satz braucht
    seinen zweiten Halbsatz: und sag, dass du schlechter bist. Dreimal war das
    in der Nacht zum 13.09. die Ursache eines Befunds:

      - `einbetten()` fiel aus, `_vektor_suche` gab [] zurueck, gesucht wurde
        nur noch im Volltext. Eine Frage fand ihren Satz nicht mehr, und die
        Antwort war "Ich kann dir die Art von Spielen nicht benennen" - sie
        sah aus wie eine Auskunft.
      - `kernwissen()` gab "" zurueck. Eine fehlende Datei sah aus wie eine
        leere, anderthalb Tage lang.
      - Und hier: `except Exception: pass` um den Chronikblock. Faellt er aus,
        antwortet er ohne ihn, und die Antwort sieht vollstaendig aus.

    ZWEI STUFEN, nach deiner Regel: Ins Journal geht jeder Ausfall. In die
    ANTWORT geht er nur, wenn Calvin es merken wuerde - wenn er also gerade
    nach genau dem gefragt hat, was jetzt fehlt. Ein ausgefallener Aufraeumer
    gehoert nicht in eine Antwort ueber Spiele.

    Gibt den Satz fuer den Prompt zurueck, oder "" wenn nur protokolliert wird.
    """
    name = f"{was}:{type(fehler).__name__}"
    if name not in _luecke_gemeldet:
        _luecke_gemeldet.add(name)
        if journal:
            try:
                journal("luecke",
                        f"{was} ist nicht verfuegbar ({type(fehler).__name__}: "
                        f"{str(fehler)[:120]}). Was davon abhaengt, fehlt in "
                        f"meinen Antworten, bis es wieder geht.",
                        nicht_erinnern=True)
            except Exception:
                pass
    if not betrifft_antwort:
        return ""
    return (f"ACHTUNG: {was} ist gerade nicht verfuegbar. {NAME} hat danach "
            f"gefragt. Sage ihm, dass du es im Moment nicht nachsehen kannst - "
            f"rate NICHT und antworte nicht, als haettest du nachgesehen.")


# "Wo liegt X?", "Wo ist X installiert?", "Hab ich X?" - und "starte X",
# denn auch darauf gehoert eine ehrliche Antwort: wo es waere.
ORTSFRAGE = re.compile(
    r"\b(wo\s+(liegt|ist|finde|befindet)|wo\s+ist\s+.+installiert|"
    r"hab(e)?\s+ich\s+|ist\s+.+\s+installiert|"
    r"start(e|en)\s+|spiel\s+|mach\s+.+\s+auf)\b", re.IGNORECASE)

# Was nach dem Fragewort uebrig bleibt, ist der gesuchte Name.
_ORTS_ABSCHNEIDEN = re.compile(
    r"^\s*(wo\s+(liegt|ist|finde\s+ich|befindet\s+sich)|hab(e)?\s+ich|"
    r"ist|start(e|en)|spiel|mach)\s+", re.IGNORECASE)


def _wo_liegt(frage: str) -> str | None:
    """Wo etwas liegt - oder None, wenn nicht danach gefragt ist.

    Drei Ausgaenge, und der dritte ist der wichtigste:

        genau einer   der Name, die Art und der Pfad
        mehrere       ALLE, mit der Bitte zu waehlen - "Doom" und "Doom
                      Eternal" sind zwei Spiele, und wer hier den ersten
                      nimmt, startet das falsche
        keiner        "kenne ich nicht", nicht geraten
    """
    if not ORTSFRAGE.search(frage):
        return None
    name = _ORTS_ABSCHNEIDEN.sub("", frage.strip()).strip(" ?!.,")
    name = re.sub(r"\b(installiert|auf|bitte|mal|denn|eigentlich)\b", " ",
                  name, flags=re.IGNORECASE).strip()
    if len(name) < 2:
        return None
    try:
        import programme
        gefunden = programme.finden(name)
    except Exception:
        return None
    if not gefunden:
        # NUR wenn ueberhaupt ein Verzeichnis da ist. Ohne es waere "kenne ich
        # nicht" eine Behauptung ueber den Rechner, die auf nichts beruht.
        try:
            import programme
            if not programme.lesen():
                return None
        except Exception:
            return None
        return (f"\u201e{name}\u201c finde ich nicht unter dem, was sich hier "
                f"starten laesst.")
    if len(gefunden) > 1 and gefunden[0]["name"].lower() != name.lower():
        namen = ", ".join(e["name"] for e in gefunden[:4])
        return (f"Da gibt es mehrere: {namen}. Welches meinst du?")
    e = gefunden[0]
    wohin = e.get("pfad") or e.get("start") or ""
    art = "Spiel" if e.get("art") == "spiel" else "Programm"
    if str(e.get("start", "")).startswith(("steam://", "com.epicgames")):
        quelle = "Steam" if e["start"].startswith("steam://") else "Epic"
        return (f"{e['name']} ist ein {art} aus {quelle}"
                + (f" und liegt in {wohin}." if e.get("pfad") else "."))
    return f"{e['name']} ist ein {art} und liegt in {wohin}." if wohin else \
           f"{e['name']} kenne ich, aber ich habe keinen Pfad dazu."


def dienst_antwort(frage: str, werkstatt: Path, lage: dict,
                   bericht: dict | None = None, journal=None) -> str | None:
    """Fragen, deren Antwort der Dienst kennt - direkt aus den Werten.

    Das Modell bekommt sie gar nicht erst zu sehen. Es hat "17:24" zu
    "sechzehn Uhr" gemacht und behauptet, Logs aktualisiert zu haben; bei
    Zahlen und Zustaenden ist ihm nicht zu trauen.

    `journal` ist da, weil eine Antwort aus einem WERKZEUG eine Werkzeugzeile
    hinterlassen muss. Am 12.09. war das Fehlen dieser Zeile der Beleg des
    Mac dafuer, dass kein Werkzeug gelaufen ist - der Nachweis soll in beide
    Richtungen funktionieren.
    """
    zeit = zeit_antwort(frage)
    if zeit:
        return zeit

    # EINE FEHLENDE LISTE IST KEINE LEERE LISTE. Steht die Frage nach Terminen
    # da und die Datei fehlt, sagt das der Dienst selbst - das Modell hat es
    # nicht getan, obwohl es im Prompt stand ("Es liegen keine Termine vor.",
    # gemessen am 13.09. um 01:10). Der Unterschied ist eine Antwort: "nichts
    # vorgemerkt" gegen "was du mir genannt hast, ist weg".
    if TERMINFRAGE.search(frage):
        try:
            import verlust
            fehlend = [n for n, _ in verlust.tragend_fehlt(werkstatt)]
            if "Terminliste" in fehlend:
                return ("Das kann ich nicht sagen. Meine Terminliste fehlt "
                        "seit dem 12. September gegen 21 Uhr. Es ist nicht so, "
                        "dass keine Termine vorliegen - was du mir vorher "
                        "genannt hast, ist verloren.")
        except Exception as f:
            # DIE TEUERSTE LUECKE IM BAU. Faellt diese Wache aus, geht die
            # Frage weiter an das Modell, und `erinnern.lesen()` gibt fuer eine
            # fehlende Datei eine leere Liste zurueck - also antwortet er
            # "du hast keine Termine". Das ist nicht unvollstaendig, das ist
            # FALSCH, und es ist genau der Satz, gegen den die Wache gebaut
            # wurde. Darum hier nicht bloss melden, sondern selbst antworten.
            luecke("Die Pruefung auf verlorene Dateien", f, journal)
            return ("Das kann ich gerade nicht nachsehen - die Pruefung auf "
                    "verlorene Dateien antwortet nicht. Ich sage dir lieber "
                    "nichts ueber deine Termine, als etwas Falsches: es kann "
                    "sein, dass meine Terminliste noch fehlt.")

    # Der Bildschirm. Steht vor allem anderen, weil "Was ist auf dem
    # Bildschirm zu sehen?" sonst nirgends haengenbleibt und beim Modell
    # landet - wo die Antwort erfunden wird.
    t0 = time.time()
    bild = bildschirm_antwort(frage, werkstatt)
    if bild:
        satz, gelungen = bild
        if journal:
            journal("werkzeug", f"sehen: {satz}", werkzeug="sehen",
                    anlass=frage[:120], gelungen=gelungen,
                    seconds=round(time.time() - t0, 1))
        return satz

    # Wer im Netz ist, steht im Lagebild - kein Modell, kein Scan.
    try:
        import lage
        netz = lage.netz_antwort(frage)
        if netz:
            return netz
    except Exception as f:
        # Nur ins Journal: Ob die Frage ueberhaupt eine Netzfrage war,
        # entscheidet `netz_antwort` selbst - das weiss ich hier nicht mehr.
        # Einen Hinweis in eine Antwort zu legen, die vielleicht gar nichts
        # mit dem Netz zu tun hat, waere schlechter als keiner.
        luecke("Das Lagebild des Netzes", f, journal)

    # Steht etwas an? Das ist keine Einschaetzung, sondern eine feste Liste -
    # und wenn nichts ansteht, wird das ehrlich gesagt statt beschwichtigt.
    if bericht is not None and WISSENSFRAGE.search(frage):
        punkte = bericht.get("berichtenswert") or []
        # Ohne "Ja" davor: auf "Alles in Ordnung?" waere "Ja, 3 Dinge stehen
        # an" das Gegenteil der Antwort.
        if not punkte:
            return "Im Moment steht nichts an, alles ruhig."
        if len(punkte) == 1:
            return f"Eine Sache steht an: {punkte[0]}."
        return f"{len(punkte)} Dinge stehen an: {aufzaehlen(punkte)}."

    # Gab es nichts zu erzaehlen, sagt das der Dienst selbst. Sonst baut das
    # Modell aus leeren tick-Zeilen etwas Plausibles zusammen.
    if bericht is not None and TAETIGKEITSFRAGE.search(frage):
        if not bericht.get("vorgaenge"):
            n = bericht.get("nachgesehen", 0)
            if n:
                return (f"Seit dem Start habe ich {n} Mal nachgesehen und "
                        f"nichts gefunden, das zu tun war.")
            return "Bisher gab es nichts zu tun."

    # Sein Haus: Kerne, Auslastung, Arbeitsspeicher, Grafikkarte, wer den
    # Speicher belegt. Aus werkstatt/haus.json, das der Haus-Faden jede Minute
    # fortschreibt - Lesen kostet nichts, Messen 1,7 s.
    #
    # Kein Modell: Calvin fragt nach Zahlen, und ein Sprachmodell ist kein
    # Messgeraet. Es hat "17:24" zu "sechzehn Uhr" gemacht.
    #
    # VOR der Platzfrage. Deren Ausdruck enthaelt "belegt", und damit
    # beantwortete sie "Wer belegt den meisten Speicher?" mit dem freien Platz
    # auf C. Und vor der Dienstfrage, deren Ausdruck "prozesse" enthaelt und
    # "Welche Prozesse laufen gerade?" mit "Ollama laeuft" beantwortete.
    #
    # haus.antwort() waehlt den Teil aus, nach dem gefragt ist. Vorher kam auf
    # JEDE Hausfrage die ganze Zustandszeile: "Wie lange laeuft der Rechner
    # schon?" wurde mit Kernen, Arbeitsspeicher und Temperatur beantwortet.
    # Eine abrufbare Liste ist noch keine Auskunft.
    if HAUSFRAGE.search(frage) or PROZESSFRAGE.search(frage):
        try:
            import haus
            d = haus.lesen(werkstatt / "haus.json")
            if d:
                return haus.antwort(frage, d) or haus.satz(d)
        except Exception as f:
            # Die Frage IST als Rechnerfrage erkannt - faellt die Auskunft aus,
            # geht sie ans Modell, und das erfindet Prozesse und Prozentzahlen.
            # Hier weiss ich, dass Calvin es merkt.
            luecke("Die Auskunft ueber den Rechner", f, journal)
            return ("Ich kann gerade nicht auf meinen Rechner sehen - die "
                    "Messwerte sind nicht abrufbar. Zahlen dazu wuerde ich "
                    "jetzt raten, und das lasse ich lieber.")

    if PLATZFRAGE.search(frage):
        import shutil
        gesamt, _, frei = shutil.disk_usage("C:\\")
        return (f"Auf C liegen noch {frei // 1024**3} Gigabyte frei, "
                f"von insgesamt {gesamt // 1024**3}.")

    if STOPFRAGE.search(frage):
        if (werkstatt / "STOP").exists():
            return "Ich bin angehalten. Es liegt eine STOP-Datei."
        bremse = lage.get("brake")
        if bremse:
            return f"Ich bin wach, gebe aber gerade keine Aufträge: {bremse}."
        return "Ich bin wach und kann arbeiten."

    if ANTRAGFRAGE.search(frage):
        ordner = werkstatt / "antraege"
        offen = []
        for p in sorted(ordner.glob("*.json")):
            try:
                a = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if a.get("status") == "offen":
                offen.append(a.get("title") or p.stem)
        if not offen:
            return "Es liegt kein offener Antrag."
        if len(offen) == 1:
            return f"Ein Antrag ist offen: {offen[0]}."
        return (f"Es sind {len(offen)} Anträge offen, unter anderem "
                f"{offen[0]}.")

    # WO ETWAS LIEGT - aus dem Verzeichnis, nicht aus dem Modell.
    #
    # Calvins Ziel: "starte das und das Spiel". Das setzt voraus, dass er weiss,
    # wo es liegt und dass es ein Spiel ist. Beides steht in programme.json,
    # und ein Pfad ist genau die Art Auskunft, bei der ein Sprachmodell raet:
    # Es kennt "steam://rungameid/1808500" nicht, also erfindet es einen.
    #
    # GESTARTET WIRD NICHTS. Diese Antwort sagt, wo es ist. Ob etwas laufen
    # darf, entscheidet Calvin - dafuer gibt es den Antragsweg.
    treffer = _wo_liegt(frage)
    if treffer is not None:
        return treffer

    if DIENSTFRAGE.search(frage):
        try:
            r = httpx.get("http://localhost:11434/api/ps", timeout=10).json()
            geladen = [m["name"] for m in r.get("models", [])]
        except Exception:
            return "Ollama antwortet gerade nicht."
        if geladen:
            return f"Ollama läuft, geladen ist {geladen[0]}."
        return "Ollama läuft, aber es ist kein Modell geladen."

    return None


class Gespraech:
    def __init__(self, ordner: Path, journal_fn, stimme: Path) -> None:
        self.ordner = ordner
        self.ordner.mkdir(parents=True, exist_ok=True)
        self.journal = journal_fn
        self.stimme = stimme
        self.verlauf: list[dict] = []      # die letzten Frage/Antwort-Paare
        # Bis hierher ist das Gespraech schon zu Wissen geworden.
        self._wissen_bis: float = 0.0
        self._wissen_laeuft: bool = False
        # Vergessen muss vollstaendig sein. Der Verlauf liegt im
        # Arbeitsspeicher, nicht in der Datenbank - ohne dieses Aufraeumen
        # sagte der Bewohner den geloeschten Satz weiter, obwohl er in der
        # Datenbank schon weg war.
        try:
            import gedaechtnis
            gedaechtnis.beim_vergessen(self.verlauf_saeubern)
        except Exception as f:
            # Nur ins Journal: ein ausgefallener Aufraeumer macht
            # keine Antwort schlechter, er hinterlaesst Arbeit.
            luecke("Der Aufraeumer nach dem Vergessen", f, self.journal)
        self.erledigt: set[str] = set()
        self._modell = None
        # Nachtrag: Kommt eine Frage mit "zu", waehrend die fruehere noch
        # gedacht wird, bricht der Aufruf ab und beides wird zusammen
        # beantwortet. Ollama hoert auf zu rechnen, sobald der Strom zu ist.
        self._abbruch = threading.Event()
        self._laeuft_kennung = None
        self._laeuft_frage = None
        self._laeuft_gesagt: list[str] = []   # was davon schon gesprochen ist
        self._entwuerfe: dict[str, dict] = {}  # vorgedachte Antworten
        self._el_klient = None      # dauerhafte Verbindung zu ElevenLabs
        self._dauer_bericht = 0.0   # gemessen in pruefen(), berichtet beim Antworten
        self._el_geprueft = False   # Kontingent einmal je Start pruefen
        self._el_aus = False        # Kontingent erschoepft -> nur Chatterbox
        self._referenz = None
        self.warteschlange: list = []
        self._arbeiter: threading.Thread | None = None
        # Chatterbox vertraegt keine zwei gleichzeitigen generate() auf
        # demselben Modell - Warmlauf und Antwort kollidierten mit
        # RuntimeError. Eine Synthese zur Zeit.
        self._stimme_sperre = threading.Lock()
        # Ollama arbeitet Anfragen an dasselbe Modell nacheinander ab. Laeuft
        # gerade eine Tick-Anfrage der Beobachtungsschleife, wartet die
        # Gespraechsfrage dahinter - gemessen 2,3 bis 2,5 s. Das Gespraech
        # hat Vorfahrt, Calvin wartet, nicht die Schleife.
        self.laeuft = threading.Event()
        # Nicht in gespraech\ - die App liest den Ordner, und 2 MB Referenz
        # haben dort nichts zu suchen.
        self.ref_ziel = ordner.parent / "_referenz_stimme.wav"

    # -- Warmlauf -----------------------------------------------------------

    def warmlaufen(self) -> None:
        """Alles Teure einmal im Voraus, damit die erste echte Frage nicht
        sechzig Sekunden braucht.

        Gemessen kalt: Chatterbox laden 8,8 s, Referenz aufbereiten, dazu
        Ollama, das gpt-oss nach einem Neustart erst wieder hochzieht (~20 s).
        Warm liegt die Antwort bei rund sieben Sekunden.
        """
        def arbeit() -> None:
            t0 = time.time()
            try:
                # 1. gpt-oss anstossen und mit keep_alive festhalten.
                httpx.post(OLLAMA, timeout=600, json={
                    "model": REDE_MODELL, "stream": False,
                    "keep_alive": KEEP_ALIVE,
                    "messages": [{"role": "user", "content": "Antworte nur: ok"}]})
                gpt = time.time() - t0

                # 2. Chatterbox wird NICHT mehr vorgeladen. Es belegte 2,4 GB
                #    auf der GPU und drueckte gpt-oss in den geteilten
                #    Speicher - dort fiel es von 164 auf 6 Token/s. Gesprochen
                #    wird ueber ElevenLabs; Chatterbox laedt nur noch, wenn
                #    der Rueckfall wirklich gebraucht wird.
                from sprich import referenz_aufbereiten
                self._referenz = referenz_aufbereiten(self.stimme, self.ref_ziel)

                print(f"  [warmlauf] gpt-oss {gpt:.1f}s, "
                      f"Referenzstimme vorbereitet, Chatterbox bleibt kalt")
                self.journal("tick", f"Warmlauf fertig nach "
                                     f"{time.time() - t0:.0f} Sekunden")
            except Exception as f:
                self.journal("fehler", f"Warmlauf: {type(f).__name__}")

        threading.Thread(target=arbeit, daemon=True, name="warmlauf").start()

    # -- Sprachausgabe ------------------------------------------------------

    def _chatterbox(self):
        """Erst beim ersten Mal laden, danach behalten."""
        if self._modell is None:
            import torch
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            geraet = "cuda" if torch.cuda.is_available() else "cpu"
            t0 = time.time()
            self._modell = ChatterboxMultilingualTTS.from_pretrained(device=geraet)
            print(f"  [tts] Chatterbox geladen ({geraet}, {time.time() - t0:.1f}s)")
        return self._modell

    def _elevenlabs(self, satz: str, ziel_mp3: Path) -> bool:
        """ElevenLabs, wenn ein Schluessel liegt. Sonst False, dann uebernimmt
        Chatterbox.

        Der Schluessel wird nur zur Laufzeit gelesen und taucht in keiner
        Meldung auf. Ueber 90 Prozent des Kontingents wird nicht mehr
        gesprochen - die Stimme darf nicht Calvins Guthaben aufbrauchen.
        """
        if not EL_SCHLUESSEL.exists():
            return False
        try:
            schluessel = EL_SCHLUESSEL.read_text(encoding="utf-8").strip()
            if not schluessel.startswith("sk_"):
                return False
            if not self._el_geprueft:
                # Einmal je Start: Bleibt genug Kontingent? Die Stimme selbst
                # steht fest, die muss nicht gesucht werden.
                r = httpx.get("https://api.elevenlabs.io/v1/user/subscription",
                              headers={"xi-api-key": schluessel},
                              timeout=30).json()
                verbraucht = int(r.get("character_count", 0))
                grenze = int(r.get("character_limit", 0)) or 1
                self._el_geprueft = True
                if verbraucht / grenze >= 0.90:
                    self.journal("stimme", f"ElevenLabs bei "
                                           f"{verbraucht / grenze:.0%} - Chatterbox übernimmt")
                    self._el_aus = True
            if self._el_aus:
                return False

            # Ein dauerhafter Client: Ohne ihn kostet jeder Satz einen neuen
            # TLS-Handschlag, rund 0,2 bis 0,3 s.
            if self._el_klient is None:
                self._el_klient = httpx.Client(
                    timeout=120,
                    limits=httpx.Limits(max_keepalive_connections=2,
                                        keepalive_expiry=300.0))

            tmp = ziel_mp3.with_suffix(".mp3.tmp")
            with self._el_klient.stream(
                "POST",
                f"https://api.elevenlabs.io/v1/text-to-speech/"
                f"{EL_STIMME_ID}/stream?output_format=mp3_44100_128",
                headers={"xi-api-key": schluessel}, timeout=120,
                json={"text": satz, "model_id": EL_MODELL,
                      "language_code": EL_SPRACHE},
            ) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for brocken in r.iter_bytes():
                        f.write(brocken)
            if tmp.stat().st_size < 500:
                tmp.unlink(missing_ok=True)
                return False
            os.replace(tmp, ziel_mp3)
            return True
        except Exception as f:
            # Nie den Schluessel mitschreiben - httpx haengt gern die Anfrage an.
            self.journal("fehler", f"ElevenLabs: {type(f).__name__}, "
                                   f"Chatterbox übernimmt")
            return False

    def _satz_sprechen(self, satz: str, ziel_mp3: Path) -> bool:
        """Ein Satz -> eine MP3. Kurz gehalten, damit die App ihn abspielen
        kann, waehrend der naechste noch entsteht.

        Zuerst ElevenLabs (rund 0,15 s bis zum ersten Byte), bei jedem Problem
        Chatterbox (rund 5 s, dafuer lokal und Calvins geklonte Stimme).
        """
        if self._elevenlabs(satz, ziel_mp3):
            return True
        import numpy as np
        import soundfile as sf
        from normalisieren import normalisieren

        from sprich import REGLER, referenz_aufbereiten

        with self._stimme_sperre:
            modell = self._chatterbox()
            if self._referenz is None:
                self._referenz = referenz_aufbereiten(self.stimme, self.ref_ziel)
            wav = modell.generate(normalisieren(satz), language_id="de",
                                  audio_prompt_path=str(self._referenz), **REGLER)
        stueck = wav.cpu().numpy().astype(np.float32).squeeze()
        wav_pfad = ziel_mp3.with_suffix(".wav")
        sf.write(str(wav_pfad), stueck, modell.sr)

        tmp = ziel_mp3.with_suffix(".mp3.tmp")
        lauf = subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-i", str(wav_pfad),
             "-codec:a", "libmp3lame", "-b:a", "128k", "-f", "mp3", str(tmp)],
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if lauf.returncode != 0 or not tmp.exists():
            print(f"  [tts] ffmpeg: {(lauf.stderr or '').strip()[:200]}")
            return False
        os.replace(tmp, ziel_mp3)
        wav_pfad.unlink(missing_ok=True)
        return True

    def _sprechen(self, text: str, ziel_mp3: Path) -> bool:
        import numpy as np
        import soundfile as sf
        from normalisieren import normalisieren
        from sprich import REGLER, in_saetze, referenz_aufbereiten

        modell = self._chatterbox()
        referenz = referenz_aufbereiten(self.stimme, self.ordner / "_ref.wav")
        stille = np.zeros(int(modell.sr * 0.25), dtype=np.float32)

        stuecke = []
        # Satzweise: haelt die VRAM-Spitze klein. Bei 557 MiB Reserve neben
        # gpt-oss ist das kein Luxus.
        for i, satz in enumerate(in_saetze(normalisieren(text))):
            wav = modell.generate(satz, language_id="de",
                                  audio_prompt_path=str(referenz), **REGLER)
            stuecke.append(wav.cpu().numpy().astype(np.float32).squeeze())
            stuecke.append(stille)
        if not stuecke:
            return False

        wav_pfad = ziel_mp3.with_suffix(".wav")
        sf.write(str(wav_pfad), np.concatenate(stuecke), modell.sr)

        tmp = ziel_mp3.with_suffix(".mp3.tmp")
        lauf = subprocess.run(
            # -f mp3 ist Pflicht: ffmpeg leitet das Format sonst aus der
            # Endung ab, und ".tmp" kennt es nicht.
            [FFMPEG, "-y", "-loglevel", "error", "-i", str(wav_pfad),
             "-codec:a", "libmp3lame", "-b:a", "128k", "-f", "mp3", str(tmp)],
            capture_output=True, text=True, timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if lauf.returncode != 0 or not tmp.exists():
            print(f"  [tts] ffmpeg: {(lauf.stderr or '').strip()[:200]}")
            return False
        os.replace(tmp, ziel_mp3)
        wav_pfad.unlink(missing_ok=True)
        return True

    # -- Antworten ----------------------------------------------------------

    def _nachrichten(self, frage: str, lage: dict, journal_ende: list[str],
                     sid: str | None = None) -> list:
        return self._antwort_holen(frage, lage, journal_ende, nur_bauen=True,
                                   sid=sid)

    # So viele Paare gehen als Kurzzeitkontext mit. GEMESSEN (E.4), nicht
    # geschaetzt: 12 Fragen, je 5 Versuche, drei Einstellungen.
    #
    #   a  4 Paare + 1500   52/60 = 87%   3 erfundene Zahlen   2,39s
    #   b  2 Paare + 1500   52/60 = 87%   0 erfundene Zahlen   2,52s
    #   c  2 Paare +  800   45/60 = 75%   0 erfundene Zahlen   2,45s
    #
    # Zwei Paare treffen genauso gut wie vier. Der Unterschied liegt beim
    # GEDAECHTNIS, nicht beim Kurzzeitteil: Von 1500 auf 800 Zeichen fallen
    # zwoelf Prozentpunkte. Darum zwei Paare und 1500 Zeichen.
    #
    # Der Hinweis auf die erfundenen Zahlen (3 gegen 0) ist schwach - drei
    # Faelle in sechzig Laeufen koennen Rauschen sein. Er zeigt in dieselbe
    # Richtung, begruendet den Wert aber nicht allein.
    PAARE_KONTEXT = 2

    def _kurzzeit(self, sid: str | None) -> list[dict]:
        """Die laufende Sitzung, woertlich - statt self.verlauf (E.1).

        Der Unterschied ist ein Neustart: `self.verlauf` liegt im
        Arbeitsspeicher und ist danach leer, also verstand er "und davor?"
        nicht mehr. Die Sitzung liegt in sitzungen/s-*.json und ueberlebt.

        Dazu B4: Ist `fortsetzung_von` gesetzt, geht die Zusammenfassung der
        Vorgaengerin voran. "Und die Unterlagen?" zwanzig Minuten spaeter
        braucht, worum es vorher ging - sonst faengt er bei null an.

        Faellt das aus, bleibt self.verlauf als Rueckfall: lieber den alten
        Kontext als keinen.
        """
        if not sid:
            return self._kurzzeit_aus_verlauf()
        try:
            import sitzung
            nachrichten = []
            kopf = sitzung.kopf(sid) or {}
            vorige = kopf.get("fortsetzung_von")
            if vorige:
                vorher = (sitzung.kopf(vorige) or {}).get("zusammenfassung")
                if vorher:
                    nachrichten.append({
                        "role": "system",
                        "content": f"Vorher ging es um: {vorher}"})
            paare = sitzung.paare(sid, letzte=self.PAARE_KONTEXT)
            for paar in paare:
                frage, antwort = paar.get("frage"), paar.get("antwort")
                if not antwort:
                    continue
                # Eine Ansprache hat keine Frage (B9) - dann nur die Antwort,
                # sonst stuende dort ein leeres user-Wort.
                if frage:
                    nachrichten.append({"role": "user", "content": frage})
                nachrichten.append({"role": "assistant", "content": antwort})
            if nachrichten:
                return nachrichten
        except Exception:
            pass
        return self._kurzzeit_aus_verlauf()

    def _kurzzeit_aus_verlauf(self) -> list[dict]:
        """Der Rueckfall: der Verlauf im Arbeitsspeicher, wie bis zum 12.09."""
        nachrichten = []
        for paar in self.verlauf[-self.PAARE_KONTEXT:]:
            nachrichten.append({"role": "user", "content": paar["frage"]})
            nachrichten.append({"role": "assistant",
                                "content": paar["antwort"]})
        return nachrichten

    def _aufnahme_messen(self, daten: dict, kennung: str) -> str:
        """Liegt der Frage eine Aufnahme bei, wird sie GEMESSEN, nicht geraten.

        Vorher antwortete er auf "wie klinge ich?" aus dem Fragetext heraus -
        "Du klingst sachlich und freundlich" nach 2,5 Sekunden, ohne je in die
        Datei gehört zu haben. Das ist erfunden, nicht gehört.
        """
        name = daten.get("aufnahme")
        if not name:
            return ""
        pfad = self.ordner / Path(str(name)).name
        if not pfad.is_file():
            self.journal("fehler", f"Aufnahme nicht gefunden: {name}",
                         id=kennung)
            return ""
        try:
            sys.path.insert(0, str(self.ordner.parent / "werkzeuge"))
            import stimme_hoeren
            m = stimme_hoeren.messen(str(pfad))
        except Exception as f:
            self.journal("fehler", f"Aufnahme nicht messbar: "
                                   f"{type(f).__name__}", id=kennung)
            return ""

        tempo = ("langsam" if m["stille_anteil"] > 0.35
                 else "zügig" if m["stille_anteil"] < 0.15 else "mittel")
        satz = (f"Tonhöhe {m['tonhoehe_hz']:.0f} Hertz, Spanne "
                f"{m['spanne_hz']:.0f} Hertz, Klangfarbe "
                f"{m['schwerpunkt_hz']} Hertz, Sprechtempo {tempo}, "
                f"{m['pausen']} Pausen, Dynamik {m['dynamik']:.1f}, "
                f"Dauer {m['dauer_s']:.1f} Sekunden")
        # Die Zahlen gehören ins Journal und in den Prompt - nicht ins
        # Gedächtnis. Dort gehört hin, was er heraushört, in Calvins Sprache.
        self.journal("gehoert", satz, id=kennung, **m)

        von = str(daten.get("von") or NUTZER).lower()
        if von != "test":
            # Eine Testaufnahme ist nicht Calvin. Sie als "ich habe Calvin
            # gehört" zu merken, wäre schlicht falsch.
            merkmale = []
            if m["tonhoehe_hz"] >= 160:
                merkmale.append("höher als sonst")
            elif m["tonhoehe_hz"] and m["tonhoehe_hz"] < 110:
                merkmale.append("tiefer als sonst")
            if m["stille_anteil"] > 0.35:
                merkmale.append("mit vielen Pausen")
            elif m["stille_anteil"] < 0.15:
                merkmale.append("ohne Unterbrechung")
            if m["spanne_hz"] >= 200:
                merkmale.append("lebhaft")
            elif m["spanne_hz"] and m["spanne_hz"] < 60:
                merkmale.append("gleichmäßig")
            wie = ", ".join(merkmale) if merkmale else "wie üblich"
            try:
                import gedaechtnis
                gedaechtnis.merken(
                    "ereignis", f"{NAME} sprach {wie}.", quelle="Aufnahme")
            except Exception as f:
                # Nur ins Journal: ein ausgefallener Aufraeumer macht
                # keine Antwort schlechter, er hinterlaesst Arbeit.
                luecke(f"Das Merken, wie {NAME} gesprochen hat", f, self.journal)
        return satz

    @staticmethod
    def _frage_ts(daten: dict) -> float:
        """Wann die Frage gestellt wurde - verlaesslich, auch bei Unsinn.

        Die App schickt Sekunden, der Dateiname traegt Millisekunden. Kam
        beides durcheinander, lag eine Frage 56000 Jahre in der Zukunft und
        jede Sitzung waere eine eigene gewesen.
        """
        try:
            ts = float(daten.get("ts") or 0)
        except (TypeError, ValueError):
            ts = 0.0
        if ts > 1e11:          # Millisekunden
            ts /= 1000.0
        # Nichts Brauchbares, oder mehr als einen Tag in der Zukunft: jetzt.
        if ts < 1e9 or ts > time.time() + 86400:
            return time.time()
        return ts

    @staticmethod
    def _sitzung_zuordnen(daten: dict) -> str | None:
        import sitzung
        return sitzung.sitzung_fuer(Gespraech._frage_ts(daten),
                                    str(daten.get("von") or NUTZER),
                                    daten.get("sitzung"))

    def _gespraech_merken(self, frage: str, antwort: str,
                          von: str = NUTZER,
                          sitzung_id: str | None = None) -> None:
        """Jede Frage mit Antwort wird eine Erinnerung. Ohne das weiss er nach
        einem Neustart nichts mehr von dem, was ihr geredet habt.

        Ausser bei Tests: Neun "Calvin fragte: Kannst du mich hoeren?" aus
        Messlaeufen lagen im Gedaechtnis, als waeren es Gespraeche gewesen.
        Ein Test ist kein Erlebnis - weder im Gedaechtnis noch im Verlauf.

        Und ausser bei Zustandsfragen. Eine Uhrzeit, ein freier Speicher, wer
        gerade im Netz ist: Die Antwort ist morgen falsch, aber die Zeile
        bleibt und taucht bei jeder Suche wieder auf. Gemessen am 12.09.:
        dreizehn Erinnerungen in EINER Minute, darunter zweimal dieselbe
        Frage nach dem Arbeitsspeicher. Auf "Was machst du am Wochenende?"
        lieferte die Suche daraufhin 1500 Zeichen, und obenan stand "Calvin
        fragte: Was kannst du?".

        Die Suche war nie kaputt. Sie fand nur, was wir hineingelegt haben.

        Der VERLAUF bekommt sie trotzdem: "Und wie viel Platz ist noch frei?"
        braucht die Frage davor, um verstanden zu werden. Kurzzeitig ja,
        dauerhaft nein - das ist der Unterschied zwischen den beiden.

        Und die SITZUNG bekommt sie auch, ungefiltert (A.4). Der Wortlaut ist
        das, woran spaeter nachzusehen ist, ob die Zusammenfassung etwas
        unterschlagen hat - also darf hier nicht schon ausgesiebt werden. Ob
        aus einer Sitzung aus lauter "Wie spaet ist es?" eine Zusammenfassung
        wird, entscheidet B, und zwar mit derselben `wissen.lohnt()`. Eine
        Sitzung gibt es nur, wenn es keine Testfrage ist; bei
        `sitzung_id is None` faellt der Aufruf von allein aus.
        """
        try:
            import sitzung
            sitzung.paar_anhaengen(sitzung_id, frage, antwort, time.time())
        except Exception as f:
            self.journal("fehler", f"Sitzung: {type(f).__name__}")
        if str(von).lower() == "test":
            return
        try:
            import wissen
            dauerhaft = wissen.lohnt({"frage": frage, "antwort": antwort})
        except Exception:
            dauerhaft = True
        # Die rohe Mitschrift geht nur noch mit dem Schalter ins Gedaechtnis.
        # Ohne ihn ersetzt die Zusammenfassung der Sitzung sie - EINE Zeile je
        # Gespraech statt einer je Frage. Genau davon lagen heute Morgen 43 da,
        # und sie haben bei jeder Suche die Fakten verdraengt.
        if dauerhaft and PROTOKOLL_ALT:
            try:
                import gedaechtnis
                kennung = gedaechtnis.merken(
                    "gespraech",
                    f"{NAME} fragte: {frage} Ich antwortete: {antwort}"[:500],
                    quelle="Gespräch")
                # 0 heisst: abgelehnt, der Inhalt wurde gerade vergessen. Dann
                # gehoert er auch nicht in den Kurzzeit-Verlauf - von dort hat
                # er ihn bei der naechsten Frage wieder gesagt, und das
                # Vergessen war nur auf dem Papier vollstaendig.
                if kennung == 0:
                    return
            except Exception:
                pass
        # Mit Zeitstempel: wissen.py erkennt daran, ob das Gespraech zu Ende
        # ist. Ohne ihn wuesste niemand, ob gerade Ruhe herrscht oder Calvin
        # nur nachdenkt.
        self.verlauf.append({"frage": frage, "antwort": antwort,
                             "ts": time.time()})

    def _wissen_ziehen(self) -> None:
        """Ist ein Gespraech zu Ende, wird daraus Wissen - einmal je Gespraech.

        Calvin am 12.09.: "Analyse der Gespraeche, Extraktion von Wissen im
        Background?" Gemessen war die Lage: 43 rohe Mitschriften im
        Gedaechtnis, davon die Mehrzahl Messwerte ("38.6 GB frei"), und
        NULL Fakten - die Art gab es, sie war leer.

        In einem eigenen Faden: Der Auszug kostet Sekunden am Modell, und
        pruefen() laeuft im Takt der Fragenerkennung. Eine Frage von Calvin
        darf darauf nicht warten.

        Der Auszug laeuft NICHT, waehrend eine Antwort entsteht - sonst
        nimmt er dem Gespraech den Modellplatz weg, und das hoert Calvin.
        """
        if self._wissen_laeuft or self._abbruch.is_set():
            return
        offen = [p for p in self.verlauf if p.get("ts", 0) > self._wissen_bis]
        if not offen:
            return
        import wissen
        if not wissen.episode(offen, time.time()):
            return

        def arbeiten() -> None:
            try:
                n = wissen.aus_gespraech(offen, time.time(),
                                         journal=self.journal)
                if n:
                    self.journal("gedaechtnis",
                                 f"{n} Fakten aus dem Gespräch behalten",
                                 nicht_erinnern=True)
            except Exception as f:
                self.journal("fehler", f"Wissen: {type(f).__name__}")
            finally:
                # Auch im Fehlerfall vorruecken: Sonst versucht er dasselbe
                # Gespraech bei jedem Durchlauf wieder und kommt nie weiter.
                self._wissen_bis = max(p.get("ts", 0) for p in offen)
                self._wissen_laeuft = False

        self._wissen_laeuft = True
        threading.Thread(target=arbeiten, daemon=True,
                         name="wissen").start()

    def verlauf_saeubern(self, texte: list[str]) -> int:
        """Wirft Frage/Antwort-Paare weg, die einen vergessenen Satz tragen."""
        import gedaechtnis
        kerne = [gedaechtnis._inhaltswoerter(t) for t in texte
                 if len(t.strip()) > 5]
        kerne = [k for k in kerne if k]
        if not kerne:
            return 0

        def traegt(paar: dict) -> bool:
            zusammen = f"{paar.get('frage', '')} {paar.get('antwort', '')}"
            return any(gedaechtnis.traegt_weiter(k, zusammen) for k in kerne)

        vorher = len(self.verlauf)
        self.verlauf = [p for p in self.verlauf if not traegt(p)]
        return vorher - len(self.verlauf)

    def _antwort_holen(self, frage: str, lage: dict, journal_ende: list[str],
                       nur_bauen: bool = False, sid: str | None = None):
        nachrichten = [{"role": "system", "content": SYSTEM}]
        # E.1: Der Kurzzeitteil kommt aus der SITZUNG, nicht aus
        # self.verlauf - damit ueberlebt er einen Neustart.
        nachrichten.extend(self._kurzzeit(sid))
        # Ortszeit ausdruecklich. Ohne Zeitangabe raet das Modell; MIT einer
        # unbeschrifteten Angabe rechnet es sie um - es sagte "sechzehn Uhr",
        # als 17:24 dranstand. Deshalb Zeitzone nennen und Umrechnen verbieten.
        try:
            from zoneinfo import ZoneInfo
            jetzt = datetime.now(ZoneInfo("Europe/Berlin"))
        except Exception:
            jetzt = datetime.now().astimezone()
        wochentage = ("Montag", "Dienstag", "Mittwoch", "Donnerstag",
                      "Freitag", "Samstag", "Sonntag")
        uhrzeit = jetzt.strftime("%H:%M")
        zeit = (f"{wochentage[jetzt.weekday()]}, {jetzt.strftime('%d.%m.%Y')}, "
                f"{uhrzeit} Uhr Ortszeit (Europe/Berlin)")
        # Nur die Zusammenfassung, keine rohen Journalzeilen. Aus denen baut
        # das Modell sonst "Ich habe die Uhrzeit 17:33 bemerkt".
        bericht = journal_ende if isinstance(journal_ende, dict) else {}
        kontext = {
            "zustand": lage.get("state"),
            "bremse": lage.get("brake"),
            "offene_aufgabe": lage.get("open_task"),
            "leere_durchgaenge": bericht.get("nachgesehen", 0),
        }
        # Sein Haus, in einem Satz. Vor "vorgaenge", weil der Lageblock bei
        # 3000 Zeichen abgeschnitten wird und die Vorgaenge lang werden.
        # Gelesen, nicht gemessen: haus.json schreibt der Haus-Faden jede
        # Minute fort, Lesen kostet nichts.
        #
        # NUR BEI EINER FRAGE NACH DEM RECHNER, und das ist zweimal gemessen.
        #
        # Der Zustandssatz stand vorher in JEDEM Prompt. Er ist das
        # Konkreteste darin, und ein Modell, das eine Frage nicht beantworten
        # kann, greift nach dem Konkretesten:
        #
        #   "Laeuft das schon lange?"  -> "Der Rechner laeuft seit 1 Tag."
        #      Der Bezug war ein Prozess. Gemessen: mit dem Block 2 von 3
        #      Brueche, ohne ihn 0 von 3.
        #   "Schnurpsel wrgl bitte?"   -> "Ich bin wach, habe keine Bremse
        #      gesetzt ... der Rechner laeuft seit zwei Tagen, hat 16 Kerne,
        #      nutzt 7 % CPU ..."   Eine wortweise Verlesung dieses
        #      Woerterbuchs, auf eine Frage, die niemand verstehen kann.
        #
        # Dieselbe Lehre wie bei kann_kurz: "Solange kann_kurz daneben stand,
        # hatte er drei vollstaendige Listen vor sich und las die laengste ab."
        # Wer eine Auskunft in jeden Prompt legt, bekommt sie in jeder Antwort.
        try:
            import haus
            d = (haus.lesen(self.ordner.parent / "haus.json")
                 if (HAUSFRAGE.search(frage) or PROZESSFRAGE.search(frage))
                 else None)
            if d:
                kontext["mein_rechner"] = haus.satz(d)
                # Hier mehr als in der gesprochenen Antwort: Der Kontext ist
                # kein Atemzug, sondern Stoff fuer eine Nachfrage ("und was
                # noch?"). haus.antwort() nennt von sich aus nur zwei.
                kontext["groesste_prozesse"] = haus.groesste(
                    d, haus.NAMEN_KONTEXT)
        except Exception as f:
            # Der Block kommt nur bei einer Rechnerfrage - faellt er aus, hat
            # Calvin nach genau dem gefragt, was jetzt fehlt.
            fehlt = luecke("Die Messwerte des Rechners", f, self.journal,
                           betrifft_antwort=bool(HAUSFRAGE.search(frage)
                                                 or PROZESSFRAGE.search(frage)))
            if fehlt:
                kontext["luecke"] = fehlt
        kontext["vorgaenge"] = bericht.get("vorgaenge", [])
        # Was er kann, gehoert dorthin, wo Calvin fragt. Bis zum 12.09. stand
        # die Liste nur im Durchgang - im Gespraech musste er raten. Calvin:
        # "Ich kann ueberhaupt nicht sehen, wer was wann warum gemacht hat,
        # welche Faehigkeiten dazugekommen sind. Du sagst, er kann meine
        # Stimme verarbeiten - aber ich habe gar keine Moeglichkeit, das zu
        # ueberpruefen."
        #
        # Zweistufig, und zwar gemessen: Die blossen Namen sind 581 Zeichen
        # und gehen immer mit - wer die Namen vor sich hat, erfindet keine
        # dazu, auch wenn die Frage nicht als Faehigkeitsfrage erkannt wurde.
        # Die volle Auskunft mit Zwecksatz und Beleg sind 3500 bis 3700
        # Zeichen; die kostet Wartezeit (siehe den Kommentar ueber SYSTEM) und
        # kommt nur, wenn wirklich danach gefragt ist.
        #
        # Eigener Block, nicht in "kontext": Der Lageblock wird bei 3000
        # Zeichen abgeschnitten, und die volle Auskunft ist laenger. Im
        # Lageblock stuende sie am Ende und waere genau dann weg, wenn
        # "vorgaenge" lang ist - also an einem vollen Tag.
        #
        # Und nur EINE von beiden. Solange `kann_kurz` daneben stand, hatte er
        # bei einer Faehigkeitsfrage drei vollstaendige Listen vor sich und
        # las die laengste ab - siehe kann.block(). Die blossen Namen sind die
        # Sicherung fuer den Fall, dass die Frage NICHT erkannt wurde; ist sie
        # erkannt, steht jeder Name ohnehin im Block.
        kann_block = ""
        try:
            import kann
            if kann.ist_faehigkeitsfrage(frage):
                kann_block = "\n\n" + kann.block(self.ordner.parent, frage)[:5000]
            else:
                # KEINE Namensliste. Hier standen alle 27 Namen, in jeder
                # Lage, bei jeder Frage - und damit lag auf "Wie geht's dir?"
                # das Konkreteste im ganzen Prompt neben einer Frage, zu der
                # es keine Daten gab. Gemessen am 12.09.: in einem von sechs
                # Laeufen las er sie ab ("Mir geht es gut. Meine Werkzeuge:
                # platzverlauf, sehen, stimme_hoeren, ..."), vorher haeufiger.
                #
                # Die Liste sollte verhindern, dass er Faehigkeiten erfindet.
                # Sie hat stattdessen dazu verleitet, sie aufzusagen. Bleibt
                # die Zahl und die Regel - wer nicht aufzaehlen kann, zaehlt
                # nicht auf, und wer weiss, dass eine Liste existiert,
                # erfindet keine.
                #
                # Auch die ZAHL nicht. Mit ihr allein im Prompt antwortete er
                # auf "Erzaehl mir, was du so draufhast" dreimal von drei mit
                # "Ich kann 27 Dinge." - genau der Satz, den Calvin seit heute
                # frueh kritisiert. Eine Zahl ist die einzige Auskunft, die
                # man aus einer Zahl bauen kann.
                # OHNE die Behauptung "Du hast Werkzeuge und Faehigkeiten".
                # Die stand hier, und sie ist eine Aussage UEBER IHN - also
                # das Konkreteste im Prompt, sobald die Frage selbst nichts
                # hergibt. Gemessen am 12.09. auf "Schnurpsel wrgl bitte?",
                # drei von drei Laeufen: "Ich habe Werkzeuge und
                # Faehigkeiten.", "Ich kann Werkzeuge und Faehigkeiten
                # nutzen." Die Zeile sollte etwas VERBIETEN und hat
                # stattdessen geantwortet. Jetzt verbietet sie nur noch.
                kontext["was_ich_kann"] = (
                    "Zaehle keine Faehigkeiten auf, nenne keine Zahl und "
                    "erfinde nichts. Wird nach deinen Faehigkeiten gefragt, "
                    "bekommst du die Liste mitgeschickt.")
        except Exception as f:
            # Faellt `kann` aus, fehlt bei einer Faehigkeitsfrage die Liste -
            # und dann erfindet er Faehigkeiten, genau das, was die Liste
            # verhindern soll. Ob es eine Faehigkeitsfrage war, kann ich hier
            # nicht mehr fragen (der Ausfall kann in `ist_faehigkeitsfrage`
            # selbst liegen), also gilt die Verbotszeile weiter - sie ist das
            # Wichtigste daran und kostet nichts.
            kontext["was_ich_kann"] = (
                "Zaehle keine Faehigkeiten auf, nenne keine Zahl und erfinde "
                "nichts.")
            fehlt = luecke("Die Liste meiner Faehigkeiten", f, self.journal,
                           betrifft_antwort=True)
            if fehlt:
                kontext["luecke"] = fehlt

        # "Was ist letzte Nacht passiert" - der Zeitraum aus der Frage, die
        # Auswahl aus passiert.py. Die Gewichte stehen dort und sind
        # nachlesbar; das Modell formuliert, es waehlt nicht aus. Ein Modell
        # entscheiden zu lassen, was relevant ist, hiesse bei jeder Frage eine
        # andere Antwort und keine Moeglichkeit nachzusehen, warum etwas
        # fehlt.
        #
        # Kostet rund 2,6 s, weil das Windows-Protokoll gelesen wird. Nur bei
        # dieser Frage.
        # Fragt er nach der NACHT, antwortet der Nachtbericht - nicht eine
        # neue Auswahl aus dem Journal. nacht.py hat den Text schon, und er
        # ist besser: Gemessen am 13.09. beantwortete passiert.py "Was ist
        # letzte Nacht passiert?" mit zwoelf Dateiaenderungen, einem
        # Bedarfsdienst und einem Abo-Stand, waehrend die Gegenpruefung um
        # 02:03, drei zusammengefasste Gespraeche, der Trockenlauf und der
        # Verlust der Werkstatt ganz fehlten. Der Grund stand in GEWICHT: die
        # Arten `sitzung`, `verlust`, `ableiten_trocken` und
        # `kernwissen_fehlt` hatten dort keinen Eintrag und fielen stumm auf
        # GEWICHT_UNBEKANNT=25 - unter `fund` (55) und `haus` (40).
        #
        # Die Zaehlzeile bleibt daneben: Was weggelassen wurde, wird gesagt.
        try:
            import passiert
            if passiert.ist_frage(frage):
                von, bis, name = passiert.zeitraum(frage)
                if "nacht" in name.lower():
                    import nacht
                    kann_block += ("\n\n[Was letzte Nacht passiert ist]\n"
                                   + nacht.fuer_prompt(
                                       stunden=max(1.0, (bis - von) / 3600.0),
                                       jetzt=bis))
                    b = passiert.zur_frage(frage)
                    kann_block += (
                        f"\n{b['insgesamt']} Journalzeilen lagen im Zeitraum, "
                        f"{b['eigene_durchgaenge']} davon eigene Maschinerie.")
                else:
                    b = passiert.zur_frage(frage)
                    kann_block += ("\n\n[Was passiert ist]\n"
                                   + json.dumps(b, ensure_ascii=False)[:6000])
        except Exception as f:
            # DIE STELLE, DIE DU BENANNT HAST. Faellt sie aus, antwortet er auf
            # "Was ist letzte Nacht passiert?" ohne jede Chronik - und die
            # Antwort sieht vollstaendig aus, weil er aus dem Verlauf und dem
            # Gedaechtnis immer IRGENDETWAS erzaehlen kann. Genau so sah der
            # Befund von 03:50 aus, nur mit anderer Ursache.
            #
            # `ist_frage` kann selbst die ausgefallene Stelle sein, darum wird
            # sie hier nicht noch einmal gefragt: Auf eine Frage, die keine
            # Chronikfrage war, steht dann ein Hinweis zu viel im Prompt - das
            # ist der guenstigere Fehler.
            fehlt = luecke("Die Chronik (was wann passiert ist)", f,
                           self.journal, betrifft_antwort=True)
            if fehlt:
                kontext["luecke"] = fehlt

        # Wer er IST - nur auf eine Frage nach ihm, und dann statt der
        # Faehigkeitsliste, nicht daneben. Stuenden beide da, gewaenne die
        # Liste: Sie ist konkreter, und genau so ist am 12.09. aus "Wer bist
        # du?" eine Aufzaehlung geworden.
        if IDENTITAETSFRAGE.search(frage):
            kann_block = "\n\n" + ich_block(self.ordner.parent)
        # Die Uhrzeit NUR bei einer Zeitfrage, und das war eine Stelle fuer
        # drei Erscheinungen. Sie stand als Vorspann in JEDEM Prompt - und
        # klebte deshalb an Antworten, in die sie nicht gehoert:
        #
        #   "Wie geht es dir?"       -> "Mir geht es gut, 17:21."
        #   "Welcher Tag ist heute?" -> "Es ist Samstag, der 12. September,
        #                                17 Uhr 18."
        #
        # Der Vorspann war ohnehin fast immer unnoetig: zeit_antwort() in
        # dienst_antwort() beantwortet Zeitfragen ohne Modell, das Modell
        # bekommt sie also gar nicht zu sehen. Uebrig bleiben die Faelle, in
        # denen die feste Antwort nicht greift - eine lange oder zusammen-
        # gesetzte Frage ("Wie spaet ist es und wie geht es dir?"). Nur dafuer
        # steht der Vorspann noch da.
        vorspann = (f"[Es ist jetzt {zeit}. Wenn nach der Uhrzeit gefragt "
                    f"wird, nenne genau {uhrzeit} — rechne nichts um und "
                    f"schaetze nicht.]\n\n") if ZEITFRAGE.search(frage) else ""
        # Die Luecke steht GANZ AM ENDE und NICHT in `kontext` - der wird bei
        # 3000 Zeichen abgeschnitten, und dann faellt ausgerechnet der Hinweis
        # weg, dass etwas fehlt. Ein Warnsatz, der dem Abschneiden zum Opfer
        # fallen kann, ist kein Warnsatz.
        fehlt = kontext.pop("luecke", "")
        luecken_block = ("\n\n" + str(fehlt)) if fehlt else ""
        nachrichten.append({
            "role": "user",
            "content": (f"{vorspann}{frage}\n\n"
                        f"[Lage]\n{json.dumps(kontext, ensure_ascii=False)[:3000]}"
                        f"{kann_block}{luecken_block}")
        })
        if nur_bauen:
            return nachrichten
        r = httpx.post(OLLAMA, json={"model": REDE_MODELL, "messages": nachrichten,
                                     "stream": False, "keep_alive": KEEP_ALIVE},
                       timeout=300)
        text = r.json()["message"]["content"].strip()
        if "</think>" in text:
            text = text.split("</think>")[-1].strip()
        return text

    # Spuren des Nachdenkens, die gpt-oss im Harmony-Format gelegentlich in
    # den Antwortkanal schreibt. Eine Erinnerung trug schon "Gut, alles ruhig.
    # The user hasn't asked new question, but prev..." - das waere vorgelesen
    # worden. Reasoning gehoert nie in Antwort, Journal oder Stimme.
    DENKSPUREN = re.compile(
        r"^\s*(the user|we need|we should|i should|let'?s|now i|the assistant|"
        r"user (asks|wants|hasn'?t)|previous(ly)?|so i (will|should)|"
        r"okay,? (so|the)|analysis|commentary)\b", re.IGNORECASE)
    KANAL = re.compile(r"<\|[^|]*\|>")

    # Satzende: Punkt, Ruf- oder Fragezeichen mit Leerraum danach - aber NICHT
    # zwischen Ziffern und nicht nach einem einzelnen Buchstaben. Sonst wurde
    # "Dynamik 11.3, Dauer 4.2" zu den Saetzen "Dynamik 11." und "3, Dauer 4."
    # und "z. B." zerfiel in zwei Haelften.
    SATZENDE = re.compile(r"(?<!\d)(?<![A-Za-zÄÖÜäöü])[.!?](\s|$)"
                          r"|(?<=\d)[.!?](?=\s+[A-ZÄÖÜ])"
                          r"|(?<=[a-zäöüß]{2})[.!?](\s|$)")

    # Wo der erste Brocken frueh herausdarf: an Komma, Strichpunkt oder
    # Doppelpunkt - aber NICHT an einem Doppelpunkt, der zu einer Uhrzeit
    # gehoert. "22:15: Llama-Server abgestuerzt, 23:33: Speicher-Fehler" wurde
    # am 12.09. hinter "23" zerschnitten, und der zweite Teil begann mit
    # ":48:". Ein Doppelpunkt zwischen Ziffern ist eine Uhrzeit, kein
    # Satzzeichen. Rechts muss ohnehin Leerraum stehen - mitten im Wort wird
    # nie geschnitten.
    FRUEH = re.compile(r"[,;](?=\s)|(?<!\d):(?=\s)")

    # Acht Woerter - und zwar acht, nicht acht beliebige Stuecke.
    #
    # Hier stand `(?:\s*\S+){8}`, und das war falsch: `\s*` darf leer sein und
    # `\S+` darf zuruecksetzen, also erfuellt JEDES Wort mit acht Zeichen den
    # Ausdruck, indem es sich selbst in acht Stuecke zerlegen laesst.
    # "Entschuld" passte darauf. Deshalb ist das Leerzeichen zwischen den
    # Woertern jetzt Pflicht: ein Wort, dann siebenmal Leerraum plus Wort.
    ACHT_WOERTER = re.compile(r"\s*\S+(?:\s+\S+){7}")

    # Zeichen, die ein Wort weitergehen lassen, ohne Buchstabe zu sein. Am
    # Pufferende sagt ein Bindestrich nicht "hier ist Schluss", sondern "es
    # kommt noch etwas": "Llama-" wird "Llama-Server", "werkstatt/" wird
    # "werkstatt/eingang". Ohne sie endete ein Sprechteil auf dem Strich, und
    # wer die Teile mit Leerzeichen zusammensetzt - Calvins App tut das -
    # bekam "werkstatt/ eingang/datei.txt".
    #
    # Die Apostrophe sind dabei: "geht's" darf nicht nach dem Zeichen enden.
    HAELT_ZUSAMMEN = "-‑–—_/\\'’"

    @classmethod
    def _ganzes_wort(cls, puffer: str, schnitt: int) -> bool:
        """Faellt dieser Schnitt zwischen zwei Woerter - oder mitten hinein?

        Zwischen zwei Woertern steht immer Leerraum. Rechts vom Schnitt muss
        also Leerraum stehen - sonst stehen wir mitten in einem Wort. Das gilt
        auch fuer Zeichen, die ein Wort zusammenhalten, ohne Buchstaben zu
        sein: "Llama-Server" wurde am Bindestrich zerschnitten, weil der
        keine Ziffer und kein Buchstabe ist.

        Der wichtigere Fall ist das PUFFERENDE. Dort wussten wir nicht, ob
        das naechste Stueck das Wort fortsetzt, und haben es durchgelassen -
        so entstanden "Entschuld" + "igung" und "Rhythm" + "us" NACH der
        ersten Reparatur. Am Ende ist ein Schnitt nur sicher, wenn links ein
        Satzzeichen steht; ein Buchstabe kann immer weitergehen.
        """
        if schnitt <= 0 or schnitt > len(puffer):
            return True
        if schnitt == len(puffer):
            return not (puffer[-1].isalnum()
                        or puffer[-1] in cls.HAELT_ZUSAMMEN)
        return puffer[schnitt].isspace()

    def _ist_denken(self, satz: str) -> bool:
        return bool(self.DENKSPUREN.match(satz))

    def _saeubern(self, text: str) -> str:
        """Harmony-Marken und alles vor </think> raus."""
        if "</think>" in text:
            text = text.split("</think>")[-1]
        return self.KANAL.sub("", text).strip()

    def _antwort_stroemen(self, nachrichten: list, ziel: list,
                          fertig: threading.Event, volltext: list | None = None):
        """Liest den Strom von gpt-oss und haengt fertige Saetze an `ziel`.

        Damit kann die Synthese mit Satz 1 anfangen, waehrend Satz 2 noch
        entsteht - statt sieben Sekunden auf den ganzen Text zu warten.

        `volltext` bekommt denselben Text ungeteilt. Er ist NICHT dasselbe wie
        " ".join(ziel): Die Sprechteile sind zum Sprechen geschnitten, und wer
        sie wieder zusammenklebt, muss raten, wo ein Leerzeichen hingehoert.
        Der Mac hat es in der App mit einer Regel versucht - "endet links
        alphanumerisch und beginnt rechts klein, dann ohne Leerzeichen" - und
        die macht aus dem voellig regulaeren Acht-Woerter-Schnitt
        "... im Heimnetz" + "beobachtet und gemessen" das Wort
        "Heimnetzbeobachtet".

        Raten muss aber niemand: Der ungeteilte Text liegt hier ohnehin vor.
        Was zum Merken und zum Lesen geht, kommt von hier - nicht aus einer
        Rueckrechnung.
        """
        puffer = ""
        roh = ""
        erster = True
        self.erstes_token = None
        t0 = time.time()
        try:
            with httpx.stream("POST", OLLAMA, timeout=300,
                              json={"model": REDE_MODELL, "messages": nachrichten,
                                    "stream": True, "keep_alive": KEEP_ALIVE,
                                    "think": "low"}) as r:
                for zeile in r.iter_lines():
                    # Nachtrag eingetroffen: Strom schliessen, Ollama hoert
                    # auf. Der halbe Satz im Puffer wird verworfen - er gehoert
                    # zu einer Frage, die gleich vollstaendig neu gestellt wird.
                    if self._abbruch.is_set():
                        break
                    if not zeile.strip():
                        continue
                    try:
                        teil = json.loads(zeile)
                    except json.JSONDecodeError:
                        continue
                    stueck = teil.get("message", {}).get("content", "")
                    if stueck and self.erstes_token is None:
                        self.erstes_token = round(time.time() - t0, 2)
                    # Das Modell setzt gern Zeilenumbrueche zwischen die Saetze
                    # (Markdown-Gewohnheit). Vorgelesen wird Fliesstext, und im
                    # Journal stuenden sonst drei abgehackte Zeilen.
                    puffer += stueck.replace("\r", " ").replace("\n", " ")
                    roh += stueck.replace("\r", " ").replace("\n", " ")
                    if volltext is not None:
                        # Laufend, nicht erst am Ende: Wird der Strom
                        # abgebrochen, ist der Text bis dahin trotzdem da.
                        volltext[:] = [self._saeubern(" ".join(roh.split()))]

                    # Der ERSTE Brocken darf frueher raus: am ersten Komma
                    # oder nach acht Woertern. Er soll klingen, bevor der
                    # Satz zu Ende gedacht ist.
                    if erster:
                        frueh = re.search(self.FRUEH, puffer)
                        if frueh and len(puffer[:frueh.start()].split()) >= 4:
                            schnitt = frueh.end()
                        else:
                            # Ueber die tatsaechlichen Wortgrenzen im Puffer,
                            # NICHT ueber len(" ".join(woerter[:8])) + 1. Die
                            # Rechnung setzte einfache Leerzeichen voraus; das
                            # Modell schickt aber "\r\n", und daraus werden
                            # oben ZWEI. Dann lag der Index um ein Zeichen
                            # daneben und der Schnitt fiel ins Wort - am
                            # 12.09. um 12:03:01 wurde aus "1202 MiB" das Paar
                            # "1202 Mi" und "B geteilt". Calvin hat es gehoert.
                            acht = re.match(self.ACHT_WOERTER, puffer)
                            schnitt = acht.end() if acht else 0
                        ende = re.search(self.SATZENDE, puffer)
                        if ende and (not schnitt or ende.end() < schnitt):
                            schnitt = ende.end()
                        if schnitt and not self._ganzes_wort(puffer, schnitt):
                            # Letzte Sicherung: Endet links ein Wort und faengt
                            # rechts ohne Leerraum weiter an, stehen wir mitten
                            # drin. Dann lieber warten - der naechste Brocken
                            # kommt in Millisekunden.
                            schnitt = 0
                        if schnitt:
                            brocken = self._saeubern(
                                " ".join(puffer[:schnitt].split()))
                            if len(brocken) > 2 and not self._ist_denken(brocken):
                                puffer = puffer[schnitt:]
                                ziel.append(brocken)
                                erster = False

                    # Danach normal an Satzenden.
                    while not erster:
                        treffer = re.search(self.SATZENDE, puffer)
                        if not treffer:
                            break
                        schnitt = treffer.end()
                        satz = self._saeubern(" ".join(puffer[:schnitt].split()))
                        puffer = puffer[schnitt:]
                        if len(satz) > 2 and not self._ist_denken(satz):
                            ziel.append(satz)
                    if teil.get("done"):
                        break
        except httpx.HTTPError as f:
            ziel.append(f"(Verbindungsfehler: {type(f).__name__})")
        rest = self._saeubern(" ".join(puffer.split()))
        if len(rest) > 2 and not self._ist_denken(rest):
            ziel.append(rest)
        fertig.set()

    # -- Hauptweg -----------------------------------------------------------

    def pruefen(self, lage: dict, journal_ende: list[str]) -> bool:
        """Neue Fragen ERKENNEN und in die Warteschlange legen.

        Beantwortet wird in einem eigenen Thread. Sonst steckt das Erkennen
        zwanzig Sekunden in der Synthese der vorigen Antwort fest, und die
        naechste Frage liegt so lange unbemerkt im Ordner.
        """
        self._wissen_ziehen()
        getan = False
        for pfad in sorted(self.ordner.glob("*.json")):
            kennung = pfad.stem
            if kennung in self.erledigt:
                continue
            try:
                daten = json.loads(pfad.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if daten.get("antwort"):
                self.erledigt.add(kennung)
                continue

            frage = (daten.get("text") or daten.get("frage")
                     or daten.get("question") or "").strip()
            if not frage:
                self.erledigt.add(kennung)
                continue

            # Entwurf: Calvin spricht noch. Nicht beantworten, nicht abhaken -
            # aber schon denken. Wenn er absendet, liegt die Antwort bereit.
            # Muss NACH dem Lesen von `frage` stehen - davor gab es sie noch
            # nicht, und pruefen() warf jede Minute einen Traceback.
            if str(daten.get("status") or "").lower() == "entwurf":
                self._vordenken(kennung, frage, dict(lage), journal_ende)
                continue

            self.erledigt.add(kennung)
            getan = True
            # Sofort ins Journal - die App sieht daran, dass die Frage
            # angekommen ist, auch wenn die Antwort noch dauert.
            # DER ABSENDER GEHT MIT. Ohne ihn ist eine Messung von einem
            # Gespraech nicht zu unterscheiden: Am 13.09. lagen 184 Frage-
            # und Antwortzeilen im Journal, keine einzige mit `von`, und
            # Calvin fand seine Testfragen in seinem Chat. Der Testkanal ist
            # genau dieses Feld - `resident.talk(von="test")` schreibt es in
            # die Frage, und von hier an traegt es jede Zeile, die zu ihr
            # gehoert.
            absender = daten.get("von") or NUTZER
            self.journal("frage", frage, id=kennung, von=absender)
            # Zu welcher Sitzung gehoert sie? Reine Zeitrechnung, kein Modell
            # (A.5). Das Ergebnis steht danach in der Frage-JSON - daran ist
            # nachvollziehbar, was zusammengehoert, und daran erkennt ein
            # Reinrutschen, wohin es zurueckwill. Testfragen bekommen keine
            # Sitzung; dann bleibt es bei None, und alles Weitere faellt von
            # allein aus.
            try:
                daten["sitzung"] = self._sitzung_zuordnen(daten)
            except Exception as f:
                self.journal("fehler", f"Sitzung: {type(f).__name__}")
            # Die Zusammenfassung erst JETZT bauen - sie kostet das Lesen des
            # halben Journals und wird nur gebraucht, wenn wirklich gefragt ist.
            t_b = time.perf_counter()
            bericht = (journal_ende() if callable(journal_ende)
                       else dict(journal_ende))
            self._dauer_bericht = time.perf_counter() - t_b
            self._einreihen(kennung, frage, pfad, daten, dict(lage), bericht)
            self._arbeiter_starten()
        return getan

    # Wie lange ein Entwurf gilt. Wird er nicht abgeschickt, ist er verworfen.
    ENTWURF_FRIST_S = 60.0

    def _vordenken(self, kennung: str, frage: str, lage: dict,
                   journal_ende) -> None:
        """Denkt ueber einen Entwurf nach, ohne etwas zu sagen.

        Nichts ins Journal, nichts vorlesen, keine Erinnerung. Nur die Saetze
        bereitlegen. Kommt die Frage dann wirklich, ist die Denkarbeit schon
        getan - das ist der groesste Hebel fuer den ersten Ton.
        """
        vorhanden = self._entwuerfe.get(kennung)
        if vorhanden and vorhanden["frage"] == frage:
            return                      # denkt schon darueber nach

        # Text geaendert: das alte Denken ist wertlos, abbrechen.
        if vorhanden:
            vorhanden["verworfen"].set()

        eintrag = {"frage": frage, "saetze": [], "volltext": [],
                   "fertig": threading.Event(),
                   "verworfen": threading.Event(), "ts": time.time()}
        self._entwuerfe[kennung] = eintrag

        def denken() -> None:
            try:
                bericht = (journal_ende() if callable(journal_ende)
                           else dict(journal_ende))
                try:
                    import gedaechtnis
                    erinnert = gedaechtnis.fuer_prompt(frage)
                except Exception:
                    erinnert = ""
                nachrichten = self._nachrichten(frage, lage, bericht)
                if erinnert:
                    nachrichten.insert(1, {"role": "system",
                                           "content": f"Was du dazu weisst:\n{erinnert}"})
                self._antwort_stroemen(nachrichten, eintrag["saetze"],
                                       eintrag["fertig"],
                                       volltext=eintrag["volltext"])
            except Exception:
                eintrag["fertig"].set()

        threading.Thread(target=denken, daemon=True,
                         name=f"entwurf-{kennung}").start()

    def _vorgedacht(self, kennung: str, frage: str) -> list[str] | None:
        """Liegt zu dieser Frage schon eine durchdachte Antwort bereit?"""
        e = self._entwuerfe.pop(kennung, None)
        if not e:
            self.journal("zeiten", "kein Entwurf zu dieser Frage vorgedacht",
                         id=kennung)
            return None
        if e["frage"] != frage:
            e["verworfen"].set()
            self.journal("zeiten", "Entwurf verworfen: Text hat sich geändert",
                         id=kennung)
            return None
        if time.time() - e["ts"] > self.ENTWURF_FRIST_S:
            e["verworfen"].set()
            self.journal("zeiten", "Entwurf verworfen: älter als 60 Sekunden",
                         id=kennung)
            return None
        # NICHT auf "fertig" warten. Calvin sendet oft schon 1,5 s nach dem
        # Entwurf ab - da laeuft der Strom noch. Frueher gab ich dann auf und
        # fing von vorn an; das war der ganze Grund, warum das Vordenken beim
        # Mac nichts brachte. Jetzt wird der LAUFENDE Strom uebernommen: die
        # ersten Saetze sind schon da, der Rest kommt nach.
        self.journal("zeiten", f"Entwurf übernommen: {len(e['saetze'])} Sätze "
                               f"fertig, Strom "
                               f"{'zu' if e['fertig'].is_set() else 'läuft noch'}",
                     id=kennung)
        return e

    def _einreihen(self, kennung, frage, pfad, daten, lage, bericht) -> None:
        """Calvin zuerst, sonst der Reihe nach.

        Ein Testlauf stellt Fragen im Sekundentakt. Ohne Vorrang stand Calvins
        Frage dahinter und kam ueber eine Minute nicht dran - genau so ist es
        heute Nacht passiert. Fragen mit "von": "test" warten, bis Calvins
        Fragen durch sind.
        """
        eintrag = (kennung, frage, pfad, daten, lage, bericht)
        von = str(daten.get("von") or NUTZER).lower()
        nachtrag_zu = str(daten.get("zu") or "")

        if nachtrag_zu:
            # Denkt er gerade ueber genau diese Frage nach? Dann abbrechen und
            # beides zusammen beantworten. Sonst antwortet er zweimal, und die
            # erste Antwort kennt den Nachtrag nicht.
            if nachtrag_zu == self._laeuft_kennung:
                # Der Nachtrag muss BEIDES ausdruecklich mittragen: die
                # fruehere Frage und was davon schon gesagt wurde. Sich auf
                # den Verlauf zu verlassen, geht schief - Testfragen stehen
                # dort absichtlich nicht drin, und dann antwortete er "Rot, 7"
                # ohne zu wissen, dass er eben "Blau" gesagt hatte.
                vorige = self._laeuft_frage or ""
                gesagt = " ".join(self._laeuft_gesagt).strip()
                teile = [f"Vorhin gefragt: {vorige}" if vorige else ""]
                if gesagt:
                    teile.append(f"Darauf habe ich schon gesagt: {gesagt}")
                teile.append(f"Jetzt zusätzlich gefragt: {frage}")
                teile.append("Antworte auf beides zusammen, ohne das schon "
                             "Gesagte zu wiederholen.")
                self.warteschlange.insert(
                    0, (kennung, " ".join(t for t in teile if t), pfad, daten,
                        lage, bericht))
                self._abbruch.set()
                self.journal("nachtrag",
                             f"laufende Frage abgebrochen, wird zusammen mit "
                             f"dem Nachtrag beantwortet: {frage[:120]}",
                             id=kennung, zu=nachtrag_zu)
                return
            # Sonst unmittelbar hinter seine Frage, damit der Zusammenhang bleibt.
            for i, vorhanden in enumerate(self.warteschlange):
                if vorhanden[0] == nachtrag_zu:
                    self.warteschlange.insert(i + 1, eintrag)
                    return
            self.warteschlange.insert(0, eintrag)
            return

        if von == NUTZER:
            # Vor den ersten Testeintrag, aber hinter alles von Calvin.
            for i, vorhanden in enumerate(self.warteschlange):
                if str(vorhanden[3].get("von") or NUTZER).lower() != NUTZER:
                    self.warteschlange.insert(i, eintrag)
                    return
        self.warteschlange.append(eintrag)

    def _arbeiter_starten(self) -> None:
        """Ein Arbeiter-Thread arbeitet die Warteschlange ab. Nur einer -
        zwei gleichzeitige Synthesen wuerden sich um die Karte streiten."""
        if self._arbeiter and self._arbeiter.is_alive():
            return

        def arbeiten() -> None:
            self.laeuft.set()
            try:
                while self.warteschlange:
                    auftrag = self.warteschlange.pop(0)
                    # Ein Nachtrag muss wissen, worueber gerade gedacht wird.
                    self._abbruch.clear()
                    self._laeuft_kennung, self._laeuft_frage = auftrag[0], auftrag[1]
                    self._laeuft_gesagt = []
                    try:
                        self._beantworten(*auftrag)
                    except Exception as f:
                        self.journal("fehler", f"Antwort: {type(f).__name__}",
                                     id=auftrag[0])
                    finally:
                        self._laeuft_kennung = self._laeuft_frage = None
            finally:
                self.laeuft.clear()

        self._arbeiter = threading.Thread(target=arbeiten, daemon=True,
                                          name="gespraech-arbeiter")
        self._arbeiter.start()

    def _beantworten(self, kennung, frage, pfad, daten, lage, journal_ende) -> None:
        # Zeit und Datum beantwortet der Dienst selbst. Ein Sprachmodell ist
        # keine Uhr - es bekam "17:24" und sagte "sechzehn Uhr". Solche Fakten
        # gehoeren eingesetzt, nicht erfragt.
        fest = dienst_antwort(frage, self.ordner.parent, lage, journal_ende,
                              journal=self.journal)
        # Die Laengengrenze gilt nicht fuer eine Werkzeugantwort: Der Satz aus
        # sehen.blick() ist gemessen, und eine Frage von 85 Zeichen macht ihn
        # nicht schlechter. Sie war dafuer da, dass eine lange, verschachtelte
        # Frage nicht mit einem festen Halbsatz abgetan wird.
        if fest and (len(frage) < 80 or BILDSCHIRMFRAGE.search(frage)):
            self._text_schreiben(pfad, daten, fest, fertig=True)
            absender = daten.get("von") or NUTZER
            self.journal("antwort", fest, id=kennung, von=absender)
            if daten.get("stimme") is False:
                self._gespraech_merken(frage, fest, absender,
                                       daten.get("sitzung"))
                return
            mp3 = self.ordner / f"{kennung}-1.mp3"
            t0 = time.time()
            if self._satz_sprechen(fest, mp3):
                self.journal("stimme", fest,
                             audio=f"gespraech/{kennung}-1.mp3",
                             id=kennung, part=1, final=True, von=absender,
                             seconds=round(time.time() - t0, 1))
            self._gespraech_merken(frage, fest, daten.get("von") or NUTZER,
                                   daten.get("sitzung"))
            return

        # Was der Bewohner ueber dieses Thema schon weiss, geht mit in die
        # Frage. Kernwissen plus die besten Treffer, gedeckelt.
        t_g = time.perf_counter()
        try:
            import gedaechtnis
            erinnert = gedaechtnis.fuer_prompt(frage)
        except Exception:
            erinnert = ""
        dauer_gedaechtnis = time.perf_counter() - t_g

        # Liegt eine Aufnahme bei, wird sie gemessen, bevor geantwortet wird.
        gehoert = self._aufnahme_messen(daten, kennung)

        t_n = time.perf_counter()
        nachrichten = self._nachrichten(frage, lage, journal_ende,
                                        sid=daten.get("sitzung"))
        dauer_nachrichten = time.perf_counter() - t_n
        if gehoert:
            nachrichten.insert(1, {
                "role": "system",
                "content": (
                    f"Du hast {NAMENS} Aufnahme gehört und gemessen: {gehoert}.\n"
                    f"Das sind TATSACHEN für dich, keine Antwort. Sag in "
                    f"normalen Sätzen, was du heraushörst - etwa dass er müde "
                    f"klingt, weil er langsamer spricht und mehr Pausen "
                    f"macht. Die Zahlen nennst du NUR, wenn er ausdrücklich "
                    f"danach fragt. Erfinde nichts dazu; was nicht gemessen "
                    f"ist, weißt du nicht.")})
        elif daten.get("aufnahme"):
            nachrichten.insert(1, {
                "role": "system",
                "content": ("Eine Aufnahme lag bei, du konntest sie aber nicht "
                            "messen. Sag ehrlich, dass du sie nicht hören "
                            "konntest - rate nicht, wie er klingt.")})
        if erinnert:
            nachrichten.insert(1, {"role": "system",
                                   "content": f"Was du dazu weisst:\n{erinnert}"})

        # Wo bleibt die Zeit? Fuenfmal geraten, fuenfmal daneben. Jetzt steht
        # sie bei jeder Antwort im Journal, statt dass ich sie schaetze.
        zeichen = sum(len(n.get("content", "")) for n in nachrichten)
        self.journal(
            "zeiten",
            f"Zusammenfassung {self._dauer_bericht:.1f}s, "
            f"Gedächtnis {dauer_gedaechtnis:.1f}s, "
            f"Nachrichten {dauer_nachrichten:.1f}s, Prompt {zeichen} Zeichen",
            id=kennung)

        t_modell = time.perf_counter()
        vorrat = self._vorgedacht(kennung, frage)
        if vorrat is not None:
            # Waehrend Calvin noch sprach, wurde schon gedacht. Die Liste und
            # das Ereignis werden WEITERBENUTZT, nicht kopiert - laeuft der
            # Strom noch, fuellt er sie weiter, waehrend schon gesprochen wird.
            saetze, fertig = vorrat["saetze"], vorrat["fertig"]
            volltext = vorrat.get("volltext") or []
        else:
            saetze = []
            volltext = []
            fertig = threading.Event()
            threading.Thread(target=self._antwort_stroemen, daemon=True,
                             args=(nachrichten, saetze, fertig),
                             kwargs={"volltext": volltext}).start()

        teil = 0
        gesprochen: list[str] = []
        t0 = time.time()
        erster_ton = None
        final_gesetzt = False
        absender = daten.get("von") or NUTZER
        # SOLL ER UEBERHAUPT SPRECHEN? Calvin am 13.09.: "Wenn ich die
        # Sprachausgabe ausschalte, brauche ich nicht, dass er erst Stimme
        # generiert und dann erst mir den Text hinschreibt."
        #
        # Jede Sprachdatei kostet rund eine Sekunde. Wer nur liest, hat
        # bisher fuer jeden Satz eine Sekunde gewartet, die er nie gehoert
        # hat. Fehlt das Feld, wird gesprochen - alte Fragen und die Uhr am
        # Handgelenk sollen sich nicht plötzlich anders verhalten.
        sprechen = daten.get("stimme") is not False

        while True:
            if teil < len(saetze):
                satz = saetze[teil]
                teil += 1
                gesprochen.append(satz)
                self._laeuft_gesagt = list(gesprochen)

                if teil == 1:
                    self.journal("zeiten", f"erster Satz von gpt-oss nach "
                                           f"{time.perf_counter() - t_modell:.1f}s",
                                 id=kennung)
                    # Text sobald der erste Satz steht - die App zeigt ihn an,
                    # waehrend die Stimme noch entsteht. Das ist die Datei,
                    # nicht das Journal: Die Journalzeile stand hier und trug
                    # NUR diesen ersten Sprechteil. Sie steht jetzt am Ende,
                    # wenn die Antwort vollstaendig ist.
                    self._text_schreiben(pfad, daten, " ".join(gesprochen))

                # ERST DER TEXT, DANN DIE STIMME - und zwar sofort.
                #
                # Bisher stand der Satz erst im Journal, NACHDEM seine
                # Sprachdatei fertig war: eine Sekunde je Satz, bei fuenf
                # Saetzen fuenf. Im Chat blieb es so lange leer, und Calvin
                # hoerte seine Antwort, bevor er sie lesen konnte. Die
                # Reihenfolge war schlicht verkehrt herum.
                self.journal("antwort_teil", satz, id=kennung, part=teil,
                             von=absender)

                if not sprechen:
                    # Kein Ton gewollt: kein Sprachdienst, keine Wartezeit.
                    continue

                mp3 = self.ordner / f"{kennung}-{teil}.mp3"
                try:
                    if self._satz_sprechen(satz, mp3):
                        if erster_ton is None:
                            erster_ton = round(time.time() - t0, 1)
                        # ERST JETZT entscheiden, ob das der letzte Satz war.
                        # Vorher gefragt lautet die Antwort fast immer "nein":
                        # waehrend Satz N synthetisiert wird, schreibt gpt-oss
                        # munter weiter. Die Folge war, dass kein einziger Teil
                        # final=true trug und die App ewig auf mehr wartete.
                        letzter = fertig.is_set() and teil >= len(saetze)
                        final_gesetzt = final_gesetzt or letzter
                        self.journal("stimme", satz,
                                     audio=f"gespraech/{kennung}-{teil}.mp3",
                                     id=kennung, part=teil, final=letzter,
                                     von=daten.get("von") or NUTZER,
                                     seconds=round(time.time() - t0, 1))
                    else:
                        self.journal("fehler", f"Satz {teil} nicht gesprochen",
                                     id=kennung)
                except Exception as f:
                    self.journal("fehler", f"Stimme: {type(f).__name__}", id=kennung)
                continue

            if fertig.is_set() and teil >= len(saetze):
                break
            time.sleep(0.1)

        # Rueckfall: Ging der letzte Satz schief oder war der Strom beim
        # Sprechen noch offen, truege kein Teil final=true und der
        # Gespraechsmodus der App wartete fuer immer. Ein Schlusszeichen ohne
        # Ton - es gibt nichts mehr abzuspielen, nur zu beenden.
        if teil and not final_gesetzt:
            # Auch wenn gar nicht gesprochen wurde: Die App wartet sonst
            # ewig auf ein Ende, das nie kommt.
            self.journal("stimme", "", id=kennung, part=teil + 1, final=True,
                         von=absender,
                         seconds=round(time.time() - t0, 1))

        # Jetzt ist die Antwort vollstaendig: ganzer Text, Zeit bis zum ersten
        # Ton, status "beantwortet". Dieser eine Aufruf schliesst ab - ein
        # zweiter davor wuerde den Status gleich wieder auf "antwortet"
        # zuruecksetzen.
        # Abgebrochen? Dann gehoert diese Frage der zusammengelegten Antwort,
        # die gleich kommt. Kein halber Text, kein "beantwortet", keine
        # Erinnerung an etwas, das nie zu Ende gedacht wurde. Der Status bleibt
        # auf "antwortet" - die App wartet auf den Nachtrag.
        if self._abbruch.is_set():
            # Was gesprochen wurde, wurde gesprochen - das steht als Antwort
            # in der Datei, und sie wird abgeschlossen. Sonst haengt sie ewig
            # auf "antwortet" und die App wartet auf etwas, das nie kommt.
            teil_text = (volltext[0] if volltext
                         else " ".join(gesprochen)).strip()
            self._text_schreiben(pfad, daten, teil_text, erster_ton,
                                 fertig=True)
            self.journal("nachtrag", "abgebrochen, der Nachtrag beantwortet "
                                     "beides zusammen", id=kennung)
            return

        # Der ungeteilte Text, wenn er da ist - sonst die Sprechteile.
        # " ".join(gesprochen) setzt Leerzeichen an jede Nahtstelle, und eine
        # Naht, die mitten in einem Wort lag, wird dadurch sichtbar: Im
        # Gedaechtnis stand "Entschuld igung" und "Llama -Server". Der
        # Rueckfall bleibt, damit eine Antwort auch dann ankommt, wenn der
        # Volltext fehlt - lieber ein Leerzeichen zu viel als keine Antwort.
        ganz = (volltext[0] if volltext else " ".join(gesprochen)).strip()
        if ganz:
            self._text_schreiben(pfad, daten, ganz, erster_ton, fertig=True)
            # Die antwort-Zeile traegt den GANZEN Text, und zwar erst jetzt.
            # Vorher stand sie oben beim ersten Sprechteil und trug nur ihn:
            # gemessen am 12.09. waren 5 von 8 Antwortzeilen kuerzer als das
            # Gesprochene, eine mit 12 Zeichen gegen 1232 gesprochene. Wer
            # die Antwort LIEST statt sie zu hoeren - der Rueckblick, die
            # App, eine Pruefung -, sah ein Fragment; bei "Entschuldigung,
            # aber ich verstehe die Frage nicht. Kannst du sie bitte
            # praeziser formulieren?" fehlte genau die Bitte.
            #
            # antwort und stimme haben verschiedene Zwecke: die eine den
            # ganzen Satz zum Lesen und Merken, die andere Stuecke zum
            # Sprechen, so frueh wie moeglich.
            self.journal("antwort", ganz, id=kennung,
                         von=daten.get("von") or NUTZER)
            self._gespraech_merken(frage, ganz, daten.get("von") or NUTZER,
                                   daten.get("sitzung"))

    def _text_schreiben(self, pfad: Path, daten: dict, text: str,
                        erster_ton: float | None = None,
                        fertig: bool = False) -> None:
        daten["antwort"] = text
        daten["antwort_ts"] = time.time()
        if erster_ton is not None:
            daten["erster_ton_s"] = erster_ton
        # status blieb bisher auf "offen", auch wenn die Antwort schon
        # dastand. Wer sich danach richtet, wartet ewig.
        daten["status"] = "beantwortet" if fertig else "antwortet"
        tmp = pfad.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(daten, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, pfad)
