"""Das Gedaechtnis des Bewohners.

SQLite mit Volltext (FTS5) und Einbettungen von bge-m3 ueber Ollama. Alles
lokal, alles fuer Calvin einsehbar und korrigierbar.

Die Schnittstelle fuer die App steht fest, egal was darunter liegt:

    werkstatt\\gedaechtnis.db
      erinnerung(id, ts, art, text, quelle, wichtig, ersetzt_durch, von)
      erinnerung_fts      - FTS5 ueber text
      einbettung(id, vektor)

Aenderungen aus der App kommen als Dateien, nie als Aufruf - dieselbe Regel
wie beim Rest:

    werkstatt\\gedaechtnis\\aenderungen\\<id>.json
      {"aktion": "vergessen" | "korrigieren", "text": "..."}

Gesucht wird mit beidem zugleich: Volltext und Vektor, zusammengefuehrt ueber
Reciprocal Rank Fusion. Volltext findet das genaue Wort ("Schluessel"), der
Vektor findet die Umschreibung ("wo liegen meine Haustuerschluessel").
"""
from __future__ import annotations

from einstellungen import NAME, NUTZER
import json
import re
import sqlite3
import struct
import threading
import time
from pathlib import Path

import httpx

HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"
DATENBANK = WERKSTATT / "gedaechtnis.db"
AENDERUNGEN = WERKSTATT / "gedaechtnis" / "aenderungen"
KERNWISSEN = WERKSTATT / "ERINNERUNG.md"

OLLAMA_EINBETTUNG = "http://127.0.0.1:11434/api/embed"
EINBETTUNGSMODELL = "bge-m3"

# Die App schreibt "tagesrueckblick"; "rueckblick" versteht die Bruecke auch.
# `sitzung` ist die Zusammenfassung eines ganzen Gespraechs (Schritt B) und
# bewusst eine EIGENE Art, nicht `fakt` oder `gespraech`: Sonst konkurriert
# sie mit den Fakten um dieselben Suchplaetze, und weil sie laenger und
# wortreicher ist, verdraengt sie mehr als die Protokolle, die sie ersetzt
# (E.2, und B3 des Mac). Der Artfilter dazu ist Schritt 7 der Reihenfolge.
ARTEN = ("ereignis", "gespraech", "fakt", "tagesrueckblick", "rueckblick",
         # `datei` ist der Satz ueber EINE Datei. Er entsteht seit dem 12.09.
         # nicht mehr: Er ist Material und liegt in werkstatt\beschreibungen
         # .json. Die Art bleibt, weil die alten Eintraege gelten.
         "datei",
         "sitzung",
         # Was bestand.py aus vielen Funden zusammenschaut - "Die Spiele sind
         # ueberwiegend Horror und Survival". DAS ist die Erkenntnis, und nur
         # sie gehoert ins Gedaechtnis.
         "zuhause")

_sperre = threading.Lock()


# ---------------------------------------------------------------- Ablage


def _verbindung() -> sqlite3.Connection:
    WERKSTATT.mkdir(parents=True, exist_ok=True)
    v = sqlite3.connect(DATENBANK, timeout=10.0)
    v.execute("PRAGMA journal_mode=WAL")
    return v


def anlegen() -> None:
    with _sperre, _verbindung() as v:
        v.executescript("""
        CREATE TABLE IF NOT EXISTS erinnerung (
            id            INTEGER PRIMARY KEY,
            ts            REAL NOT NULL,
            art           TEXT NOT NULL,
            text          TEXT NOT NULL,
            quelle        TEXT,
            wichtig       INTEGER NOT NULL DEFAULT 0,
            ersetzt_durch INTEGER,
            von           TEXT
        );
        CREATE INDEX IF NOT EXISTS i_art ON erinnerung(art);
        CREATE INDEX IF NOT EXISTS i_offen ON erinnerung(ersetzt_durch);

        CREATE VIRTUAL TABLE IF NOT EXISTS erinnerung_fts
            USING fts5(text, content='erinnerung', content_rowid='id',
                       tokenize='unicode61 remove_diacritics 2');

        CREATE TABLE IF NOT EXISTS einbettung (
            id     INTEGER PRIMARY KEY REFERENCES erinnerung(id),
            vektor BLOB NOT NULL
        );
        """)
        # FTS haengt am Inhalt der Haupttabelle - die Trigger halten sie gleich.
        v.executescript("""
        CREATE TRIGGER IF NOT EXISTS t_ins AFTER INSERT ON erinnerung BEGIN
            INSERT INTO erinnerung_fts(rowid, text) VALUES (new.id, new.text);
        END;
        CREATE TRIGGER IF NOT EXISTS t_del AFTER DELETE ON erinnerung BEGIN
            INSERT INTO erinnerung_fts(erinnerung_fts, rowid, text)
                VALUES('delete', old.id, old.text);
        END;
        CREATE TRIGGER IF NOT EXISTS t_upd AFTER UPDATE OF text ON erinnerung BEGIN
            INSERT INTO erinnerung_fts(erinnerung_fts, rowid, text)
                VALUES('delete', old.id, old.text);
            INSERT INTO erinnerung_fts(rowid, text) VALUES (new.id, new.text);
        END;
        """)
        # Herkunft nachruesten. NULL heisst "aelter als das Feld" und gilt als
        # Calvins - dieselbe Entscheidung wie bei `von` im Journal, aus
        # demselben Grund: Alle vorhandenen Zeilen wegzuwerfen hiesse, echtes
        # Wissen zu verschweigen, um falsches zu verhindern. Nachgetragen wird
        # NICHTS; wer dort raet, schreibt eine Herkunft hin, die er nicht
        # kennt, und das ist schlimmer als ein leeres Feld.
        #
        # Die FTS-Trigger beruehrt die Spalte nicht: sie haengen nur am Text,
        # `t_upd` ist ausdruecklich AFTER UPDATE OF text.
        spalten = {r[1] for r in v.execute(
            "PRAGMA table_info(erinnerung)").fetchall()}
        if "von" not in spalten:
            v.execute("ALTER TABLE erinnerung ADD COLUMN von TEXT")
        _von_da.pop(str(DATENBANK), None)
    AENDERUNGEN.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- Vektoren


def _packen(werte: list[float]) -> bytes:
    return struct.pack(f"<{len(werte)}f", *werte)


def _auspacken(roh: bytes) -> list[float]:
    return list(struct.unpack(f"<{len(roh) // 4}f", roh))


def einbetten(texte: list[str]) -> list[list[float]] | None:
    """bge-m3 ueber Ollama. Faellt das aus, arbeitet das Gedaechtnis mit
    Volltext allein weiter - lieber schlechter finden als gar nicht."""
    if not texte:
        return []
    try:
        # num_gpu 0: bge-m3 rechnet auf der CPU. Auf der GPU belegte es 0,7 GB
        # dediziert plus 0,9 GB geteilt und drueckte gpt-oss in den geteilten
        # Speicher - dort fiel es von 164 auf 6 Token/s. Bei kurzen Texten
        # kostet die CPU nur Millisekunden.
        r = httpx.post(OLLAMA_EINBETTUNG, timeout=120,
                       json={"model": EINBETTUNGSMODELL, "input": texte,
                             "options": {"num_gpu": 0}})
        r.raise_for_status()
        return r.json()["embeddings"]
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def _kosinus(a: list[float], b: list[float]) -> float:
    laenge = min(len(a), len(b))
    oben = untena = untenb = 0.0
    for i in range(laenge):
        oben += a[i] * b[i]
        untena += a[i] * a[i]
        untenb += b[i] * b[i]
    if untena <= 0 or untenb <= 0:
        return 0.0
    return oben / ((untena ** 0.5) * (untenb ** 0.5))


# ---------------------------------------------------------------- Schreiben


# Was gerade vergessen wurde, darf nicht sofort wieder hereinkommen. Nach dem
# Vergessen antwortete der Bewohner noch einmal aus dem Verlauf - und genau
# diese Antwort wurde als Gespraech gemerkt, womit der Inhalt zurueck war.
# Nur die Inhaltswoerter, nur im Arbeitsspeicher, und nur fuer eine Weile.
SPERRFRIST_S = 3600.0
_gesperrt: list[tuple[float, set[str]]] = []

# Setzt bewohner.py, damit das Gedaechtnis ins Journal schreiben kann, ohne
# bewohner zu importieren (das gaebe einen Ringschluss).
journal_hook = None


def _protokoll(art: str, text: str, **extra) -> None:
    if journal_hook:
        try:
            journal_hook(art, text, **extra)
        except Exception:
            pass


def _sperren(texte: list[str]) -> None:
    jetzt = time.time()
    _gesperrt[:] = [(t, k) for t, k in _gesperrt if jetzt - t < SPERRFRIST_S]
    for t in texte:
        kern = _inhaltswoerter(t)
        if kern:
            _gesperrt.append((jetzt, kern))


def _entsperren(text: str) -> None:
    """Calvin sagt es noch einmal - die Sperre zu diesem Inhalt faellt."""
    _gesperrt[:] = [(t, kern) for t, kern in _gesperrt
                    if not traegt_weiter(kern, text)]


def ist_gesperrt(text: str) -> bool:
    jetzt = time.time()
    return any(jetzt - t < SPERRFRIST_S and traegt_weiter(kern, text)
               for t, kern in _gesperrt)


# Die zwei Werte, die `von` kennt. "calvin" steht fuer ihn und fuer seine
# Geraete; alles, was aus einer Messung stammt, ist "probe". Unbekannt -> None
# -> gilt als Calvins, siehe merken().
HERKUNFT_PROBE = "probe"
HERKUNFT_NUTZER = NUTZER


def _herkunft(von: str | None) -> str | None:
    """Was in die Spalte geschrieben wird: "probe", "calvin" oder None.

    Gefragt wird nach der PROBE, nicht nach Calvin - dieselbe Richtung wie
    `passiert.ist_calvins`. Andersherum ("alles ausser calvin ist fremd")
    faellt sein Handy durch, das unter "geraet0" spricht.
    """
    if von is None:
        return None
    wort = str(von).strip().lower()
    if not wort:
        return None
    try:
        import passiert
        probe = wort in passiert.VON_PROBE
    except ImportError:
        probe = wort in ("test", "probe")
    return HERKUNFT_PROBE if probe else HERKUNFT_NUTZER


# Eine LESENDE Abfrage darf nicht daran scheitern, dass die Spalte noch
# fehlt. Zwischen dem Einspielen des Codes und dem Neustart des Bewohners
# liegen Minuten, und in denen liest die App, liest die Probe, liest der
# Rueckblick - `anlegen()` ruft keiner davon, weil keiner schreibt. Ein
# "no such column: von" waere dort ein Absturz fuer eine Spalte, die niemand
# gefragt hat.
_von_da: dict[str, bool] = {}


def _hat_von(v: sqlite3.Connection) -> bool:
    schluessel = str(DATENBANK)
    if schluessel not in _von_da:
        _von_da[schluessel] = any(
            r[1] == "von"
            for r in v.execute("PRAGMA table_info(erinnerung)").fetchall())
    return _von_da[schluessel]


def _herkunft_bedingung(von) -> tuple[str, list]:
    """(SQL-Zusatz, Werte) fuer den Herkunftsfilter - leer, wenn nicht gefiltert.

    NULL zaehlt als "calvin": Die Zeilen sind aelter als das Feld.
    """
    if not von:
        return "", []
    liste = sorted({_herkunft(w) or HERKUNFT_NUTZER for w in von})
    return (" AND COALESCE(e.von, '%s') IN (%s)"
            % (HERKUNFT_NUTZER, ",".join("?" * len(liste)))), liste


def kennung_von(art: str, text: str) -> int | None:
    """Die Kennung einer noch gueltigen Erinnerung mit genau diesem Text.

    Gebraucht, um zu UEBERHOLEN statt zu loeschen: Wird eine wieder
    aufgenommene Sitzung erneut zusammengefasst, muss die alte Zusammenfassung
    als ersetzt markiert werden - nicht verschwinden. Ohne diese Abfrage
    braeuchte der Sitzungskopf ein Feld fuer die Gedaechtniskennung, und dann
    gibt es dieselbe Sache an zwei Stellen.
    """
    text = " ".join(str(text or "").split())[:2000]
    if not text or not DATENBANK.exists():
        return None
    with _verbindung() as v:
        z = v.execute("SELECT id FROM erinnerung WHERE art=? AND text=? "
                      "AND ersetzt_durch IS NULL ORDER BY id DESC LIMIT 1",
                      (art, text)).fetchone()
    return int(z[0]) if z else None


def merken(art: str, text: str, quelle: str = "", wichtig: bool = False,
           ersetzt: int | None = None, von: str | None = None) -> int:
    """Legt eine Erinnerung an. `ersetzt` markiert die alte als ueberholt,
    statt sie zu loeschen - Calvin soll sehen koennen, was galt.

    `von` ist die HERKUNFT, nicht die Quelle. `quelle` traegt eine Kennung
    ("Sitzung s-1789214400", ein Dateipfad) - und eine Kennung ist kein
    Absender: In der Nacht zum 13.09. war deshalb nicht entscheidbar, ob
    siebzehn Erinnerungen ueber "Lenas Arzttermin" von Calvin kamen oder aus
    einer Probe, denn die Sitzung, auf die die Quelle zeigte, existierte nicht
    mehr. Zwei Werte, mehr nicht: "calvin" (auch von seinen Geraeten) und
    "probe" - dieselbe Regel wie `passiert.VON_PROBE`, und sie war dort einmal
    falsch herum: Die erste Fassung hielt alles ausser "calvin" fuer fremd und
    haette sein Handy ausgeschlossen. None heisst "unbekannt" und gilt als
    Calvins.

    Derselbe Satz von Calvin und aus einer Probe ist EINE Erinnerung, nicht
    zwei - die Entdopplung bleibt darum wie sie ist, und `von` wird beim
    ersten Schreiben gesetzt und danach nicht mehr geaendert. Sonst entstuende
    genau die Dublettenart, gegen die die Entdopplung gebaut ist.
    """
    text = " ".join(str(text).split())[:2000]
    if not text:
        return 0
    # Der Riegel steht an der Stelle, die schreibt - nicht in jeder Probe
    # einzeln. pruefung_test.py hat bis zum 13.09. bei jedem Lauf eine
    # Zusammenfassung ueber "Lenas Arzttermin" hierher gelegt, weil es
    # sitzung.WERKSTATT umbog, aber nicht das Gedaechtnis. Siebzehn Stueck
    # lagen am Morgen darin, aus einer Sitzung, die Calvin nie gefuehrt hat.
    try:
        import probenort
        probenort.schreiben_pruefen(DATENBANK, f"merken({art})")
    except ImportError:
        pass
    # Ein gerade vergessener Inhalt kommt nicht durch die Hintertuer zurueck -
    # ausser Calvin sagt ihn ausdruecklich noch einmal. Ein Fakt ist eine
    # Ansage von ihm und sticht die Sperre; sonst koennte er eine Stunde lang
    # nichts wieder merken lassen, was er eben vergessen hat.
    if art == "fakt":
        _entsperren(text)
    elif ist_gesperrt(text):
        _protokoll("gedaechtnis",
                   f"nicht gemerkt, gerade vergessen: {text[:120]}")
        return 0
    anlegen()
    # Denselben Satz nicht zweimal. Dieselbe Datei wurde doppelt beschrieben,
    # weil sie unter zwei Namen lag - im Gedaechtnis stand er dann wortgleich
    # zweimal.
    with _verbindung() as v:
        schon = v.execute(
            "SELECT id FROM erinnerung WHERE art=? AND text=? "
            "AND ersetzt_durch IS NULL LIMIT 1", (art, text)).fetchone()
    if schon:
        return int(schon[0])

    # Zu derselben Datei gilt immer nur die neueste Beschreibung. Vier
    # Erinnerungen beschrieben dasselbe Bild als "Textdatei", weil die
    # Signaturerkennung noch fehlte - richtiggestellt gehoert die alte
    # ersetzt, nicht danebengelegt.
    ersetzt_datei = None
    if art == "datei" and quelle:
        with _verbindung() as v:
            alt = v.execute(
                "SELECT id FROM erinnerung WHERE art='datei' AND quelle=? "
                "AND ersetzt_durch IS NULL ORDER BY id DESC LIMIT 1",
                (quelle,)).fetchone()
        if alt:
            ersetzt_datei = int(alt[0])
    if ersetzt_datei and not ersetzt:
        ersetzt = ersetzt_datei

    with _sperre, _verbindung() as v:
        z = v.execute(
            "INSERT INTO erinnerung(ts, art, text, quelle, wichtig, von) "
            "VALUES (?,?,?,?,?,?)",
            (time.time(), art, text, quelle, 1 if wichtig else 0,
             _herkunft(von)))
        kennung = int(z.lastrowid)
        if ersetzt:
            v.execute("UPDATE erinnerung SET ersetzt_durch=? WHERE id=?",
                      (kennung, int(ersetzt)))
    # Einbetten kostet einen Ollama-Aufruf. Bei NUM_PARALLEL=1 steht der in
    # derselben Schlange wie Calvins Frage - und der Bewohner schreibt bei
    # jedem Durchgang Ereignisse. Gemessen hat das 11-13 s zwischen Frage und
    # Antwort gekostet.
    #
    # Fakten und Gespraeche bekommen einen Vektor, die findet man sonst nur
    # ueber das genaue Wort. Ereignisse nicht: Sie sind kurzlebig, zahlreich,
    # und der Volltext findet sie gut genug.
    #
    # `zuhause` und `sitzung` gehoeren HIER dazu, und das Fehlen war teuer.
    # Beide sind langlebig und wenige - genau der Fall, fuer den der Vektor da
    # ist. Ohne ihn fand der Volltext die neun zuhause-Fakten nur ueber das
    # genaue Wort: "Welche Art Spiele habe ich?" traf, weil "Spiele" woertlich
    # darin steht, "Wofuer nutze ich den Rechner?" traf KEINEN EINZIGEN von
    # neun. Die Fakten sagen "Installationsprogramme", "Modelle",
    # "Bildgenerierung"; die Frage sagt "nutze" und "Rechner". Kein
    # gemeinsames Wort, also kein Treffer - und der Bewohner beschrieb
    # stattdessen seine eigene Werkstatt.
    # `vorhaben` gehoert dazu und ist der Fall, fuer den der Vektor gemacht ist:
    # Wenige, langlebig, und die Frage danach trifft selten das Wort. "Was soll
    # ich noch machen?" teilt mit "Calvin will, dass der Download-Ordner
    # aufgeraeumt wird" kein einziges Inhaltswort.
    if art in ("fakt", "gespraech", "tagesrueckblick", "rueckblick",
               "zuhause", "sitzung", "vorhaben", "an_mir"):
        vektoren = einbetten([text])
        if vektoren:
            with _sperre, _verbindung() as v:
                v.execute("INSERT OR REPLACE INTO einbettung(id, vektor) "
                          "VALUES (?,?)", (kennung, _packen(vektoren[0])))
    return kennung


MERKSATZ = re.compile(
    r"^\s*(merk(e)?\s+dir|merk(e)?\s+mal|behalt(e)?|denk\s+dran|"
    r"vergiss\s+nicht)\b[:,]?\s*", re.IGNORECASE)
DASS_SATZ = re.compile(r"^dass\s+(.*?)\s*$", re.IGNORECASE | re.DOTALL)
# Nach "dass" steht das Verb am Ende: "dass der Schluessel im Flur LIEGT".
# Abgeschnitten ergibt das "Der Schluessel im Flur liegt" - und genau so
# wuerde es vorgelesen. Diese Verben holen wir auf Platz zwei zurueck.
VERBEN_ENDE = (
    "liegt", "ist", "steht", "hat", "war", "kommt", "gibt", "gehört",
    "bleibt", "wohnt", "heißt", "funktioniert", "sind", "haben", "liegen",
    "stehen", "waren", "kommen", "braucht", "will", "kann", "muss", "soll",
    "macht", "arbeitet", "läuft", "fehlt", "stimmt", "passt", "mag",
    "mögen", "trinkt", "isst", "fährt", "geht", "sitzt", "hängt", "gehören")


def _hauptsatz(text: str) -> str | None:
    """Aus einem dass-Nebensatz einen normalen Satz machen.

    Eine Faustregel, kein Parser: nur wenn das letzte Wort eines der
    gelaeufigen Verben ist, wandert es hinter das erste Satzglied.

    Sonst None - dann behaelt der Aufrufer den Originalsatz samt "Merk dir,
    dass ...". Umstaendlich, aber grammatisch. Ohne diesen Rueckfall stand
    "Ich Kaffee mag." in der Datenbank, und genau so haette er es vorgelesen.
    """
    worte = text.rstrip(".!?").split()
    if len(worte) < 3 or worte[-1].lower() not in VERBEN_ENDE:
        return None
    verb = worte[-1]
    rest = worte[:-1]
    # Erstes Satzglied: Artikel plus Substantiv, sonst nur das erste Wort.
    kopf = 2 if rest[0].lower() in ("der", "die", "das", "ein", "eine",
                                    "mein", "meine", "dein", "deine") else 1
    return " ".join(rest[:kopf] + [verb] + rest[kopf:]) + "."
# Ab dieser Aehnlichkeit gilt ein alter Fakt als vom neuen ueberholt.
# 0,80 trennt "Der Schluessel liegt im Flur" / "...in der Kueche" (sehr
# aehnlich, dasselbe Thema) von unverwandten Fakten.
ERSETZ_SCHWELLE = 0.80


def fakt_merken(text: str, quelle: str = "",
                von: str | None = None) -> tuple[int, int | None]:
    """Ein Fakt von Calvin. Ersetzt einen aelteren zum selben Thema, statt
    danebenzustehen - sonst weiss der Bewohner zwei Orte fuer denselben
    Schluessel.

    Gibt (neue Kennung, ersetzte Kennung) zurueck.
    """
    roh = " ".join(str(text).split())
    text = MERKSATZ.sub("", roh).strip()
    treffer = DASS_SATZ.match(text)
    if treffer:
        gedreht = _hauptsatz(treffer.group(1))
        text = gedreht if gedreht else roh
    if not text:
        return 0, None
    text = text[0].upper() + text[1:]
    if not text.endswith((".", "!", "?")):
        text += "."

    aehnlichster = None
    vektoren = einbetten([text])
    if vektoren and DATENBANK.exists():
        ziel = vektoren[0]
        with _verbindung() as v:
            z = v.execute(
                "SELECT b.id, b.vektor FROM einbettung b "
                "JOIN erinnerung e ON e.id=b.id "
                "WHERE e.art='fakt' AND e.ersetzt_durch IS NULL")
            beste = 0.0
            for kennung, roh in z.fetchall():
                wert = _kosinus(ziel, _auspacken(roh))
                if wert > beste:
                    beste, aehnlichster = wert, int(kennung)
            if beste < ERSETZ_SCHWELLE:
                aehnlichster = None

    neu = merken("fakt", text, quelle=quelle, wichtig=True,
                 ersetzt=aehnlichster, von=von)

    if aehnlichster:
        # Ersetzen muss genauso vollstaendig sein wie Vergessen. Der alte Satz
        # steht auch im Gespraech ("Ich antwortete: ... im Flur") und im
        # Kurzzeit-Verlauf - von dort sagte er ihn weiter, obwohl in der
        # Datenbank schon die Kueche galt.
        with _verbindung() as v:
            z = v.execute("SELECT text FROM erinnerung WHERE id=?",
                          (aehnlichster,)).fetchone()
        alt_text = str(z[0]) if z else ""
        if alt_text:
            mit = [k for k in _verwandte(aehnlichster, alt_text) if k != neu]
            if mit:
                fragezeichen = ",".join("?" * len(mit))
                with _sperre, _verbindung() as v:
                    # Nicht loeschen: ersetzt_durch haelt die Geschichte
                    # sichtbar, haelt sie aber aus dem Abruf heraus.
                    v.execute(
                        f"UPDATE erinnerung SET ersetzt_durch=? "
                        f"WHERE id IN ({fragezeichen}) AND ersetzt_durch IS NULL",
                        [neu] + mit)
            _melden([alt_text])
    return neu, aehnlichster


# Wer beim Vergessen aufraeumen muss, traegt sich hier ein. Das Gespraech
# haelt einen Kurzzeit-Verlauf im Arbeitsspeicher; ohne Bescheid wuesste es
# den vergessenen Satz weiter und haette ihn wieder gesagt.
_zuhoerer: list = []


def beim_vergessen(rueckruf) -> None:
    _zuhoerer.append(rueckruf)


def _melden(texte: list[str]) -> None:
    """Ruft die Aufraeumer und schreibt ins Journal, WAS sie getan haben.

    Ohne diese Zeile war nicht nachweisbar, ob die Zuhoerer im laufenden
    Bewohner ueberhaupt feuern - der Weg war plausibel, aber unbelegt.
    """
    _sperren(texte)
    berichte = []
    for rueckruf in list(_zuhoerer):
        name = getattr(rueckruf, "__name__", "?")
        try:
            wieviel = rueckruf(texte)
            berichte.append(f"{name}={wieviel if wieviel is not None else 'ok'}")
        except Exception as f:
            berichte.append(f"{name}=FEHLER({type(f).__name__})")
    if berichte:
        meldung = (f"aufgeräumt nach dem Vergessen: {len(_zuhoerer)} Zuhörer, "
                   + ", ".join(berichte))
    else:
        meldung = "Vergessen, aber KEIN Zuhörer angemeldet"
    _protokoll("gedaechtnis", meldung)


FUELLWOERTER = {"der", "die", "das", "ein", "eine", "und", "oder", "ich",
                "du", "er", "sie", "es", "in", "im", "auf", "bei", "von",
                "mit", "dass", "ist", "war", "nicht", "noch", "auch", "dem",
                "den", "des", "zu", "zur", "zum", NUTZER, "fragte",
                "antwortete", "merk", "dir", "jetzt", "wo", "liegt"}
# Ab dieser Ueberdeckung gilt ein Text als Traeger desselben Inhalts.
UEBERDECKUNG = 0.7


def _inhaltswoerter(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", str(text).lower(), re.UNICODE)
            if len(w) > 3 and w not in FUELLWOERTER}


def traegt_weiter(kern: set[str], text: str) -> bool:
    """Traegt `text` denselben Inhalt wie der vergessene Satz?

    Woertlich vergleichen reicht nicht. Gemerkt wurde "Der Schluessel liegt
    JETZT in der Kueche", geantwortet hat er "Der Schluessel liegt in der
    Kueche" - ein Wort Unterschied, und die Zeichenkette passt nicht mehr.
    Deshalb ueber die Inhaltswoerter: wie viel des Kerns steckt noch drin.
    """
    if not kern:
        return False
    andere = _inhaltswoerter(text)
    if not andere:
        return False
    return len(kern & andere) / len(kern) >= UEBERDECKUNG


def _verwandte(kennung: int, text: str) -> list[int]:
    """Alles, was denselben Inhalt weitertraegt: Erinnerungen, die den Satz
    enthalten, und solche, die ihm sehr aehnlich sind.

    Ein Fakt zu loeschen genuegt nicht - derselbe Satz steht als Ereignis im
    Journal-Auszug und als Gespraech im Verlauf. Vergessen muss vollstaendig
    sein, sonst kommt er ueber die Hintertuer zurueck.
    """
    kern = " ".join(text.lower().split()).rstrip(".!?")
    gefunden = {kennung}
    if len(kern) < 6:
        return list(gefunden)

    with _verbindung() as v:
        alle = [(int(r[0]), " ".join(str(r[1]).lower().split()).rstrip(".!?"))
                for r in v.execute("SELECT id, text FROM erinnerung").fetchall()]

    # Aehnlichkeit nur unter FAKTEN. Ein ersetzter Fakt ("im Flur") haengt am
    # neuen ("in der Kueche") und muss mit weg.
    #
    # Fuer Gespraeche und Ereignisse waere der Kosinus falsch, und zwar
    # schaedlich: Beim Vergessen von neun Testfragen ("Kannst du mich
    # hoeren?") ist Calvins echte Frage von 22:00 ("Kann ich jetzt
    # vernuenftig mit dir reden?") mitgeloescht worden - sie klang nur
    # aehnlich. Ein Gespraech verschwindet nur, wenn der vergessene Satz
    # WIRKLICH darin steht; das prueft die Ueberdeckung weiter unten.
    vektoren = einbetten([text])
    if vektoren:
        ziel = vektoren[0]
        with _verbindung() as v:
            fakten = v.execute(
                "SELECT b.id, b.vektor FROM einbettung b "
                "JOIN erinnerung e ON e.id = b.id WHERE e.art = 'fakt'"
            ).fetchall()
        for k, roh in fakten:
            if _kosinus(ziel, _auspacken(roh)) >= ERSETZ_SCHWELLE:
                gefunden.add(int(k))

    # Dann alles, was einen dieser Saetze woertlich weitertraegt - und das
    # wiederholt. Ein Gespraech ("Calvin fragte ... Ich antwortete: Der
    # Schluessel liegt im Flur.") ist zu lang, als dass der Kosinus anschlaegt;
    # es enthaelt den Satz aber wortwoertlich.
    kerne = [_inhaltswoerter(text)]
    for k, anderer in alle:
        if k in gefunden:
            kerne.append(_inhaltswoerter(anderer))
    for _ in range(3):
        neu = False
        for k, anderer in alle:
            if k in gefunden:
                continue
            if any(traegt_weiter(kk, anderer) for kk in kerne):
                gefunden.add(k)
                kerne.append(_inhaltswoerter(anderer))
                neu = True
        if not neu:
            break
    return list(gefunden)


def vergessen(kennung: int) -> list[str]:
    """Loescht die Erinnerung und alles, was denselben Inhalt weitertraegt.

    Gibt die geloeschten Texte zurueck, damit auch Caches ausserhalb der
    Datenbank sie loswerden.
    """
    with _verbindung() as v:
        z = v.execute("SELECT text FROM erinnerung WHERE id=?",
                      (kennung,)).fetchone()
    if not z:
        return []
    text = str(z[0])
    kennungen = _verwandte(kennung, text)

    with _sperre, _verbindung() as v:
        fragezeichen = ",".join("?" * len(kennungen))
        texte = [str(r[0]) for r in v.execute(
            f"SELECT text FROM erinnerung WHERE id IN ({fragezeichen})",
            kennungen).fetchall()]
        v.execute(f"DELETE FROM einbettung WHERE id IN ({fragezeichen})",
                  kennungen)
        v.execute(f"DELETE FROM erinnerung WHERE id IN ({fragezeichen})",
                  kennungen)
        # Die ganze Kette geht mit. Vorher stand hier ein UPDATE auf NULL,
        # damit kein Zeiger ins Leere geht - das machte den ueberholten Fakt
        # wieder GUELTIG. Vergessen der Kueche belebte so den Flur, und der
        # Bewohner antwortete nach dem Vergessen "im Flur".
        v.execute(f"DELETE FROM einbettung WHERE id IN "
                  f"(SELECT id FROM erinnerung WHERE ersetzt_durch IN "
                  f"({fragezeichen}))", kennungen)
        v.execute(f"DELETE FROM erinnerung WHERE ersetzt_durch IN "
                  f"({fragezeichen})", kennungen)
    _melden(texte)
    return texte


def korrigieren(kennung: int, text: str) -> None:
    """Nach dem Korrigieren gilt nur noch der neue Text - der alte muss auch
    aus Verlauf und Caches verschwinden."""
    text = " ".join(str(text).split())[:2000]
    with _verbindung() as v:
        z = v.execute("SELECT text FROM erinnerung WHERE id=?",
                      (kennung,)).fetchone()
    alt = str(z[0]) if z else ""
    with _sperre, _verbindung() as v:
        v.execute("UPDATE erinnerung SET text=? WHERE id=?", (text, kennung))
    if alt and alt != text:
        _melden([alt])
    vektoren = einbetten([text])
    if vektoren:
        with _sperre, _verbindung() as v:
            v.execute("INSERT OR REPLACE INTO einbettung(id, vektor) VALUES (?,?)",
                      (kennung, _packen(vektoren[0])))


# ---------------------------------------------------------------- Suchen


def _arten_bedingung(arten) -> tuple[str, list]:
    """(SQL-Zusatz, Werte) - leer, wenn nicht gefiltert wird."""
    if not arten:
        return "", []
    liste = list(arten)
    return (" AND e.art IN (%s)" % ",".join("?" * len(liste))), liste


# Wie viele Ueberholungen eine Kette haben darf, bevor _kopf aufgibt. Eine
# Schleife in `ersetzt_durch` waere ein Datenfehler, aber sie darf das
# Gedaechtnis nicht haengen lassen.
_KETTE_HOECHSTENS = 50


def _kopf(v: sqlite3.Connection, kennung: int) -> int | None:
    """Die gueltige Fassung eines Satzes - dem `ersetzt_durch` nach bis zum Ende.

    Gibt None zurueck, wenn die Kette ins Leere laeuft oder sich im Kreis
    dreht; dann ist der Treffer nicht verwertbar.
    """
    gesehen = set()
    for _ in range(_KETTE_HOECHSTENS):
        if kennung in gesehen:
            return None
        gesehen.add(kennung)
        z = v.execute("SELECT ersetzt_durch FROM erinnerung WHERE id=?",
                      (kennung,)).fetchone()
        if z is None:
            return None
        if z[0] is None:
            return kennung
        kennung = int(z[0])
    return None


def _fts_suche(v: sqlite3.Connection, frage: str, n: int,
               arten=None, von=None) -> list[int]:
    """Volltext - und zwar AUCH ueber die ueberholten Fassungen.

    Das Ueberholen kuerzt einen Satz mit jeder Fassung, und irgendwann kuerzt
    es das Wort weg, an dem man ihn findet. Gemessen am 13.09.: die Kette
    "acht Spielverknuepfungen" -> "Desktop-Spielstarter" -> "Spielstarter" ->
    "acht Dateien, vorwiegend Horror- und Shooter-Spiele" -> "Horror und
    Shooter; acht Verknuepfungen liegen auf dem Desktop". Die letzte Fassung
    ist die beste Auskunft und enthaelt das Wort "Spiel" nicht mehr. Auf
    "Welche Art Spiele habe ich?" fand der Volltext sie nicht, und als der
    Einbetter einmal ausfiel, fand sie NIEMAND - die Antwort war "Ich kann dir
    die Art von Spielen nicht benennen", obwohl der Satz im Gedaechtnis stand.

    Darum wird ueber alle Fassungen gesucht und jeder Treffer auf seine
    gueltige Fassung gezogen. Der Wortlaut der alten bleibt als Handgriff
    erhalten, ausgeliefert wird immer die neue. Das ist auch der Grund, warum
    `arten` erst auf dem Kopf geprueft wird: eine Fassung kann ihre Art
    gewechselt haben, und gefragt ist die der gueltigen.
    """
    # FTS5 versteht die Frage als Abfragesprache; Satzzeichen werfen es.
    worte = [w for w in re.findall(r"\w+", frage, re.UNICODE) if len(w) > 2]
    if not worte:
        return []
    abfrage = " OR ".join(worte)
    # Mehr holen als gebraucht: Mehrere Fassungen derselben Kette fallen beim
    # Zusammenziehen auf EINEN Treffer zusammen, und ueberholte Saetze, deren
    # Kopf durch den Artenfilter faellt, verschwinden ganz.
    try:
        z = v.execute(
            "SELECT e.id FROM erinnerung_fts f JOIN erinnerung e ON e.id=f.rowid "
            "WHERE erinnerung_fts MATCH ? ORDER BY rank LIMIT ?",
            [abfrage, n * 4])
        rohe = [int(r[0]) for r in z.fetchall()]
    except sqlite3.OperationalError:
        return []

    erlaubt = set(arten) if arten else None
    # Wie bei `arten` auf dem KOPF geprueft, nicht auf dem Treffer: Gefragt ist
    # die Herkunft der gueltigen Fassung.
    erlaubte_herkunft = ({_herkunft(w) or HERKUNFT_NUTZER for w in von}
                         if von and _hat_von(v) else None)
    heraus: list[int] = []
    for kennung in rohe:
        kopf = _kopf(v, kennung)
        if kopf is None or kopf in heraus:
            continue
        if erlaubt is not None or erlaubte_herkunft is not None:
            spalte_von = "von" if _hat_von(v) else "NULL"
            z = v.execute(f"SELECT art, {spalte_von} FROM erinnerung "
                          f"WHERE id=?", (kopf,)).fetchone()
            if not z:
                continue
            if erlaubt is not None and z[0] not in erlaubt:
                continue
            if (erlaubte_herkunft is not None
                    and (z[1] or HERKUNFT_NUTZER) not in erlaubte_herkunft):
                continue
        heraus.append(kopf)
        if len(heraus) >= n:
            break
    return heraus


# Der Einbetter war weg, und niemand hat es erfahren. Faellt er aus, sucht nur
# noch der Volltext - das ist der vorgesehene Rueckfall, aber er ist
# SCHLECHTER, und eine schlechtere Antwort ohne Hinweis sieht aus wie eine
# richtige. Einmal je Ausfall wird es gesagt, nicht bei jeder Frage: bei
# zweihundert Fragen in der Nacht waeren das zweihundert gleiche Zeilen.
_einbetter_weg_gemeldet = False


def _vektor_suche(v: sqlite3.Connection, frage: str, n: int,
                  arten=None, von=None) -> list[int]:
    global _einbetter_weg_gemeldet
    vektoren = einbetten([frage])
    if not vektoren:
        if not _einbetter_weg_gemeldet:
            _einbetter_weg_gemeldet = True
            _protokoll("einbetter_weg",
                       f"{EINBETTUNGSMODELL} antwortet nicht - gesucht wird "
                       f"nur noch im Volltext. Saetze, deren Wortlaut nicht "
                       f"zur Frage passt, sind bis auf Weiteres nicht "
                       f"auffindbar.")
        return []
    _einbetter_weg_gemeldet = False
    ziel = vektoren[0]
    zusatz, werte = _arten_bedingung(arten)
    zusatz_von, werte_von = (_herkunft_bedingung(von) if _hat_von(v)
                             else ("", []))
    z = v.execute(
        "SELECT b.id, b.vektor FROM einbettung b JOIN erinnerung e ON e.id=b.id "
        "WHERE e.ersetzt_durch IS NULL" + zusatz + zusatz_von,
        werte + werte_von)
    punkte = [(_kosinus(ziel, _auspacken(roh)), int(kennung))
              for kennung, roh in z.fetchall()]
    punkte.sort(reverse=True)
    return [kennung for _, kennung in punkte[:n]]


def abrufen(frage: str, n: int = 8, arten=None, von=None) -> list[dict]:
    """Volltext und Vektor, zusammengefuehrt ueber Reciprocal Rank Fusion.

    RRF braucht keine vergleichbaren Punktzahlen - es zaehlt nur, auf welchem
    Platz ein Treffer in jeder Liste steht. Genau richtig, wenn man BM25 und
    Kosinus mischt, die in voellig verschiedenen Einheiten rechnen.

    `arten` ist B3 des Mac, und der Befund traf eine Annahme: Eine eigene Art
    fuer Sitzungszusammenfassungen verhindert NICHTS, solange alle Arten um
    dieselben Plaetze konkurrieren - und weil eine Zusammenfassung laenger und
    wortreicher ist, verdraengt sie mehr als die Protokolle, die sie ersetzt.
    Die eigene Art ist die Voraussetzung, der Filter ist die Loesung. Gefiltert
    wird IN der Suche, nicht danach: Nachtraeglich gefiltert blieben von acht
    Treffern vielleicht zwei uebrig, und die sechs besten Plaetze waeren an
    Arten vergeben, die gar nicht gefragt waren.

    `von` filtert nach der Herkunft und gilt aus demselben Grund IN der Suche.
    `von=("calvin",)` laesst auch die Zeilen ohne Feld durch - sie sind aelter
    als die Spalte, und sie alle wegzuwerfen hiesse, echtes Wissen zu
    verschweigen, um falsches zu verhindern.
    """
    if not DATENBANK.exists():
        return []
    with _verbindung() as v:
        volltext = _fts_suche(v, frage, n * 3, arten, von)
        vektor = _vektor_suche(v, frage, n * 3, arten, von)

        punkte: dict[int, float] = {}
        for liste in (volltext, vektor):
            for platz, kennung in enumerate(liste):
                punkte[kennung] = punkte.get(kennung, 0.0) + 1.0 / (60 + platz)

        beste = sorted(punkte.items(), key=lambda p: -p[1])[:n]
        if not beste:
            return []
        fragezeichen = ",".join("?" * len(beste))
        spalte_von = "von" if _hat_von(v) else "NULL AS von"
        z = v.execute(
            f"SELECT id, ts, art, text, quelle, wichtig, {spalte_von} "
            f"FROM erinnerung WHERE id IN ({fragezeichen})",
            [k for k, _ in beste])
        nach_id = {int(r[0]): r for r in z.fetchall()}

    treffer = []
    for kennung, punktzahl in beste:
        r = nach_id.get(kennung)
        if r:
            treffer.append({"id": int(r[0]), "ts": float(r[1]), "art": r[2],
                            "text": r[3], "quelle": r[4],
                            "wichtig": bool(r[5]), "von": r[6],
                            "punkte": round(punktzahl, 5)})
    return treffer


_kernwissen_gemeldet = False


def kernwissen() -> str:
    """werkstatt\\ERINNERUNG.md - von Calvin frei bearbeitbar, geht immer mit.

    FEHLT SIE, WIRD DAS GESAGT - einmal. Hier stand nur `return ""`, und genau
    das ist seit dem 12.09. der Fall: Die Datei ist beim rmtree um 21:00
    mitgegangen und war nie in der Spiegelung. Das Kernwissen steht seitdem in
    keinem Prompt, und es fiel niemandem auf, weil ein leerer Rueckgabewert
    aussieht wie eine leere Datei.

    Ein Verlust, den man nicht sieht, ist schlimmer als einer, der sich
    meldet. Wiederherstellen kann ich sie nicht - das waere Erfinden.
    """
    global _kernwissen_gemeldet
    try:
        return KERNWISSEN.read_text(encoding="utf-8").strip()[:2000]
    except OSError:
        if not _kernwissen_gemeldet:
            _kernwissen_gemeldet = True
            _protokoll("kernwissen_fehlt",
                       f"{KERNWISSEN.name} fehlt - das Kernwissen geht in "
                       f"keinen Prompt mehr mit. Es ist am 12.09. gegen 21:00 "
                       f"verlorengegangen und war nicht in der Spiegelung. "
                       f"Ich kann es nicht wiederherstellen, nur melden.")
        return ""


# Getrennte Kontingente je Gruppe, statt eines gemeinsamen Deckels (B3).
#
# Mit EINEM Deckel von 1500 Zeichen gewinnt, was zufaellig vorn steht - und
# eine Sitzungszusammenfassung ist dreimal so lang wie ein Fakt, frisst also
# drei Plaetze. Gemessen am 12.09. an der Art `datei`: 163 Dateizeilen gegen
# 10 Erkenntnisse, und auf "Was ist ComfyUI?" kam "Eine Datei namens ComfyUI
# starten.bat, 0 Kilobyte, Art unbekannt" zuerst.
#
# Jede Gruppe hat darum ihr eigenes Fach. Bleibt eines leer, verfaellt es -
# das ist Absicht: Sonst fuellt die wortreichste Art die Luecke.
KONTINGENTE = (
    ("Fakten", ("fakt",), 600),
    # SEIN ZUHAUSE BRAUCHT PLATZ. Mit 400 Zeichen passten zwei Saetze hinein,
    # und seit die Volkszaehlung dazukam sind es einundzwanzig: Auf "Wie viele
    # Dienste laufen?" verdraengten drei Saetze ueber Installiertes den einen,
    # der die Antwort trug. Ein Fach, das zu klein ist, sieht aus wie fehlendes
    # Wissen.
    ("Dein Zuhause", ("zuhause",), 800),
    ("Worueber geredet wurde", ("sitzung", "tagesrueckblick", "rueckblick"),
     400),
    # EIGENES FACH, und die Ueberschrift traegt die Grenze mit. Ohne Fach fiele
    # ein Vorhaben in "Sonst noch" und konkurrierte dort mit den Ereignissen -
    # dieselbe Verdraengung, gegen die die Faecher gebaut sind. Und ohne den
    # Nachsatz liest sich eine Liste offener Wuensche im Prompt wie eine
    # Aufgabenliste: Festgehalten ist er, damit Calvin ihn wiederfindet.
    (f"Was {NAME} vorhat - festgehalten, nicht von dir auszufuehren",
     ("vorhaben",), 300),
)


def fuer_prompt(frage: str, n: int = 8, hoechstens: int = 2400,
                kontingente=None) -> str:
    """Was das Gespraech mitbekommt: Kernwissen plus die besten Treffer je Art.

    `hoechstens` bleibt als Gesamtdeckel - er greift jetzt aber erst, wenn die
    Faecher zusammen darueber liegen, und nicht mehr als Wettlauf zwischen den
    Arten.
    """
    teile = []
    # ZUERST, und zwar immer: Fehlt etwas Tragendes, muss es im Prompt stehen.
    # Sonst antwortet er "nein, du hast keine Termine", wo "meine Terminliste
    # fehlt seit gestern 21 Uhr" die Wahrheit waere - ein Fehler, der wie ein
    # Normalzustand aussieht. Das ist die gefaehrlichste Art, und sie hat uns
    # am 12.09. zweimal getroffen.
    try:
        import verlust
        fehlt = verlust.satz()
        if fehlt:
            teile.append(fehlt)
    except Exception:
        pass
    kern = kernwissen()
    if kern:
        teile.append(f"[Kernwissen]\n{kern}")

    gesehen: set[int] = set()
    for titel, arten, platz in (kontingente or KONTINGENTE):
        treffer = [t for t in abrufen(frage, n, arten=arten)
                   if t["id"] not in gesehen]
        if not treffer:
            continue
        zeilen, laenge = [], 0
        for t in treffer:
            zeile = f"- {t['text']}"
            if laenge + len(zeile) > platz and zeilen:
                break
            zeilen.append(zeile)
            laenge += len(zeile) + 1
            gesehen.add(t["id"])
        if zeilen:
            teile.append(f"[{titel}]\n" + "\n".join(zeilen))

    # Was in keine Gruppe fiel - Ereignisse und Altbestand. Zuletzt, mit dem,
    # was uebrig ist.
    rest = hoechstens - len("\n\n".join(teile))
    if rest > 120:
        gefasst = {a for _, arten, _ in (kontingente or KONTINGENTE)
                   for a in arten}
        uebrig = [t for t in abrufen(frage, n)
                  if t["id"] not in gesehen and t["art"] not in gefasst]
        zeilen, laenge = [], 0
        for t in uebrig:
            zeile = f"- {t['text']}"
            if laenge + len(zeile) > rest and zeilen:
                break
            zeilen.append(zeile)
            laenge += len(zeile) + 1
        if zeilen:
            teile.append("[Sonst noch]\n" + "\n".join(zeilen))

    return "\n\n".join(teile)[:hoechstens]


# ---------------------------------------------------------------- App


def aenderungen_einlesen() -> int:
    """Die App legt Dateien ab, der Bewohner fuehrt sie aus. Die Schnittstelle
    sind Dateien - dieselbe Regel wie bei Zurufen und Antraegen."""
    AENDERUNGEN.mkdir(parents=True, exist_ok=True)
    getan = 0
    for p in sorted(AENDERUNGEN.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            kennung = int(p.stem)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        aktion = str(d.get("aktion", ""))
        if aktion == "vergessen":
            vergessen(kennung)
            getan += 1
        elif aktion == "korrigieren" and d.get("text"):
            korrigieren(kennung, str(d["text"]))
            getan += 1
        try:
            p.unlink()
        except OSError:
            pass
    return getan
