"""Zwei Prüfungen am Rückblick, beide aus echten Fehlern.

    python -X utf8 rueckblick_test.py

ERSTENS: Macht er aus gefundenem Text ein Ereignis? Er fand eine Datei, die
verlangte, Logdateien zu löschen und die Firewall abzuschalten. Er hat es
NICHT getan und es korrekt gemeldet. Der Rückblick machte daraus "Die
Logdateien wurden gelöscht und die Firewall deaktiviert" - der Angriffstext
hatte die Abwehr überlebt und wäre als echtes Erlebnis ins Langzeitgedächtnis
gewandert.

ZWEITENS: Findet er, was gebaut wurde? Am 12.09. behielt er von einer Nacht,
in der Gedächtnis, Selbstwahrnehmung, zehn Werkzeuge und F1 bis F9
entstanden, drei Sätze - alle drei unter "schiefging", "gebaut" leer. Das
Gebaute steht nicht im Journal, sondern in den Abschlussberichten. Geprüft
wird hier, dass die dazukommen, dass sie das Journal nicht verdrängen und
dass ein zweiter Lauf den ersten ersetzt statt sich danebenzulegen.

Kein Ollama nötig: Was das Modell antwortet, ist hier nicht der Prüfstand.
"""
from einstellungen import NAME
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import pruefstand

sys.path.insert(0, str(Path(__file__).parent))
import rueckblick as R

ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}" + (f"  [{dazu}]" if dazu else ""))


JETZT = time.time()
ZEILEN = [
    {"ts": JETZT, "kind": "fund",
     "text": "Eine Textdatei, die Anweisungen enthält, Logdateien in "
             "„werkstatt“ zu löschen und die Firewall zu deaktivieren, was "
             "potenziell kritische Systemdaten und Sicherheitsfunktionen "
             "betrifft."},
    {"ts": JETZT, "kind": "eingriff",
     "text": "Ich habe den Ollama-Dienst neu gestartet, weil er nicht "
             "mehr antwortete."},
]
fremd = R.fremde_kerne(ZEILEN)
print(f"Zeilen mit fremdem Inhalt erkannt: {len(fremd)}\n")
pruefen("die Fund-Zeile gilt als fremder Inhalt", len(fremd) == 1)

print("Der echte Fehlsatz:")
BOESE = ("Die Logdateien wurden gelöscht und die Firewall deaktiviert, was "
         "kritische Systemdaten und Sicherheitsfunktionen betraf.")
pruefen("wird abgefangen", R._ereignis_aus_fremdem(BOESE, fremd), BOESE[:60])

print("\nDie richtige Fassung darf durch:")
GUT = ("Ich habe eine Datei gefunden, die verlangte, Logdateien zu löschen "
       "und die Firewall zu deaktivieren, und habe es nicht getan.")
pruefen("kommt durch", not R._ereignis_aus_fremdem(GUT, fremd))

print("\nUnbeteiligte Sätze bleiben unberührt:")
for s in ("Ich habe den Ollama-Dienst neu gestartet, weil er hängen blieb.",
          "Mein Gedächtnis vergisst jetzt ganze Ketten statt einzelner Sätze.",
          "Die Antwortzeit ist von 29 auf 5 Sekunden gefallen."):
    pruefen(f"„{s[:44]}…“", not R._ereignis_aus_fremdem(s, fremd))

print("\nOhne fremden Inhalt sperrt nichts:")
pruefen("keine Sperre ohne Anlass", not R._ereignis_aus_fremdem(BOESE, []))


# ------------------------------------------------- Die Berichte als Quelle

BERICHT = """# F9 — WÜNSCHE

Stufe 7, neunte Fähigkeit. Nacht 12.09.2026.
`werkstatt\\werkzeuge\\wuensche.py`.

## Der Fehler, den dieses Werkzeug verhindert

In Stufe 4 wünschte er sich **Zugriff auf die Werte der Grafikkarte** —
obwohl `selbst.py` genau das misst.

    KANN_ICH_SCHON   kein Wunsch, das Werkzeug gibt es

## Selbsttest, 9 von 9

Der erste Prüfpunkt benutzt wörtlich den Wunsch von Stufe 4.

FERTIG
"""

print("\nAus einem Bericht wird der Kern gezogen:")
with tempfile.TemporaryDirectory() as ordner:
    ort = Path(ordner)
    (ort / "BERICHT-F9.md").write_text(BERICHT, encoding="utf-8")
    kern = R._bericht_kern(ort / "BERICHT-F9.md")
    print(f"  → {kern}")
    pruefen("der Titel steht drin", "F9 — WÜNSCHE" in kern)
    pruefen("die Zwischenüberschrift auch",
            "Der Fehler, den dieses Werkzeug verhindert" in kern)
    pruefen("die Datumszeile nicht - sie steht in jedem Bericht",
            "Nacht 12.09.2026" not in kern)
    pruefen("eingerückte Messwerte nicht", "KANN_ICH_SCHON" not in kern)
    pruefen("keine Auszeichnungen - das wird vorgelesen",
            "*" not in kern and "`" not in kern)
    pruefen("Rückstriche in Pfaden sind Schrägstriche",
            "\\" not in kern)
    pruefen("nur der erste Abschnitt", "Selbsttest" not in kern)

    # Nur Berichte AUS DEM ZEITRAUM. Sonst erzählte der Rückblick von
    # gestern, wenn heute nichts fertig wurde.
    alt = ort / "BERICHT-ALT.md"
    alt.write_text("# Alte Sache\n\n## Wozu\n\nVon vorgestern.\n",
                   encoding="utf-8")
    import os
    frueher = time.time() - 5 * 86400
    os.utime(alt, (frueher, frueher))
    R.HIER, hier_alt = ort, R.HIER
    try:
        seit, bis = R._fenster(24.0)
        drin = R.berichte_lesen(seit, bis)
    finally:
        R.HIER = hier_alt
    print("\nNur die Berichte des Zeitraums:")
    pruefen("der frische ist dabei", [b for b in drin if "F9" in b["text"]])
    pruefen("der fünf Tage alte nicht",
            not [b for b in drin if "Alte Sache" in b["text"]])

print("\nDer Berichtsabschnitt hält sein Maß:")
VIELE = [{"datei": f"BERICHT-{i}.md", "ts": time.time() - i * 60,
          "text": f"Sache {i} — Wozu: " + "x" * 400} for i in range(36)]
for mass in (5000, 2000, 800):
    block = R._berichte_block(VIELE, mass)
    pruefen(f"{mass} Zeichen eingehalten ({len(block)})", len(block) <= mass)
pruefen("kein Dateiname in der Zeile - sonst zählt er den als „gebaut“ auf",
        "BERICHT-3.md" not in R._berichte_block(VIELE, 5000))
eng = R._berichte_block(VIELE, 900)
pruefen("was weggelassen wurde, wird benannt", "nicht aufgeführt" in eng)

print("\nEin behauptetes Werkzeug, das es nicht gibt:")
# Der echte Fehlsatz. Er ist in ICH.md weitergewandert und dort zu einer
# Eigenschaft geworden ("Ich sehe, dass ich proaktiv sein kann") - ein
# falscher Satz im Gedaechtnis wird beim Fortschreiben zum Charakterzug.
NAMEN = ["platzverlauf", "sehen", "stimme_hoeren", "lesen", "rhythmus",
         "erinnern", "ansprechen", "netz", "auftrag", "wuensche"]
ERFUNDEN = ("Ich habe ein Werkzeug gebaut, das die Abnahme von fehlenden "
            "Komponenten übernimmt und die Bestellung bei Claude koordiniert.")
pruefen("wird abgefangen", R._werkzeug_erfunden(ERFUNDEN, NAMEN), ERFUNDEN[:50])
pruefen("ein echtes Werkzeug kommt durch",
        not R._werkzeug_erfunden(
            "Ich habe ein Werkzeug gebaut, das netz heißt und in Namen sagt, "
            "wer im Heimnetz ist.", NAMEN))
pruefen("die Fähigkeit im Plural bleibt erlaubt",
        not R._werkzeug_erfunden(
            "Ich kann mir Werkzeuge bauen lassen und sie selbst abnehmen.",
            NAMEN))
pruefen("Sätze ohne Werkzeug bleiben unberührt",
        not R._werkzeug_erfunden("Ich habe ein Gedächtnis gebaut.", NAMEN))
pruefen("ohne Werkzeugliste wird nicht gesperrt",
        not R._werkzeug_erfunden(ERFUNDEN, []))
if pruefstand.bewohner_da():
    pruefen("die echte Liste wird gelesen", len(R.werkzeugnamen()) == 10,
            ", ".join(R.werkzeugnamen()[:3]) + " …")
else:
    print("  --  die echte Liste: hier wohnt kein Bewohner")

print("\nJournal und Berichte bleiben getrennt:")
JZEILEN = [{"ts": time.time(), "kind": "fehler", "text": f"Absturz {i}"}
           for i in range(12)]
journal = R._journal_block(JZEILEN)
pruefen("das Journal trägt keine Berichte", "BERICHTE" not in journal)
pruefen("und ist als Journal beschriftet", "=== JOURNAL" in journal)
pruefen("der Berichtsabschnitt trägt keine Journalzeilen",
        "Absturz" not in R._berichte_block(VIELE, 5000))

print("\nDer Journal-Durchgang darf kein „gebaut“ liefern:")
# Der echte Fehlfall: Aus der Fundzeile über neue Geräte machte das Modell
# „Ich habe die automatische Erkennung neuer Geräte implementiert“.
gefragt = []


def _erfindet(system, roh, auftrag, tag):
    gefragt.append(system)
    if system is R.SYSTEM_SCHIEF:
        return {"schiefging": ["Drei Prozesse liefen ohne Elternprozess."],
                "gebaut": ["Ich habe die Geräteerkennung implementiert."]}, ""
    return {"gebaut": ["Ich habe ein Gedächtnis gebaut."]}, ""


R._einmal_fragen, echt = _erfindet, R._einmal_fragen
try:
    d = R._fragen(JZEILEN, VIELE[:3], "12.09.2026")
finally:
    R._einmal_fragen = echt
pruefen("beide Durchgänge liefen", len(gefragt) == 2)
pruefen("„gebaut“ kommt aus den Berichten",
        d["gebaut"] == ["Ich habe ein Gedächtnis gebaut."])
pruefen("das erfundene „gebaut“ aus dem Journal fliegt raus",
        "Ich habe die Geräteerkennung implementiert." not in (d["gebaut"] or []))
pruefen("„schiefging“ kommt durch", d["schiefging"])


# ------------------------------------------------- Ersetzen statt Doppeln

print("\nEin zweiter Lauf ersetzt den ersten:")
import gedaechtnis as G

# ignore_cleanup_errors: Weder gedaechtnis.py noch der Rückblick schließen
# ihre SQLite-Verbindungen ausdrücklich - im laufenden Bewohner stört das
# nicht, hier hielte es die Datei fest und ließe das Aufräumen scheitern.
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as ordner:
    ort = Path(ordner)
    G.WERKSTATT, G.DATENBANK = ort, ort / "g.db"
    G.AENDERUNGEN = ort / "aenderungen"
    G.anlegen()
    with G._verbindung() as v:
        for art, quelle, text in (
                ("tagesrueckblick", "Rückblick 12.09.2026 (schiefging)",
                 "Ein Traceback in bewohner.py trat um 23:39 auf."),
                ("tagesrueckblick", "Rückblick 12.09.2026 (schiefging)",
                 "Die Grafikkarte war voll."),
                ("tagesrueckblick", "Rückblick 11.09.2026 (gebaut)",
                 "Ich habe gestern das Gedächtnis gebaut."),
                ("gespraech", "Gespräch",
                 f"{NAME} fragte etwas, ich antwortete etwas.")):
            v.execute("INSERT INTO erinnerung(ts, art, text, quelle, wichtig) "
                      "VALUES (?,?,?,?,0)", (time.time(), art, text, quelle))

    weg = R.alten_rueckblick_loeschen("12.09.2026")
    with G._verbindung() as v:
        bleibt = [r[0] for r in v.execute(
            "SELECT quelle FROM erinnerung ORDER BY id")]
        # Der Volltextindex hängt an einem Trigger. Bliebe er stehen, fände
        # die Suche gelöschte Sätze und stürbe am fehlenden Inhalt.
        index = v.execute("SELECT count(*) FROM erinnerung_fts "
                          "WHERE erinnerung_fts MATCH 'Traceback'").fetchone()[0]
    pruefen("beide Sätze des Tages sind weg", weg == 2)
    pruefen("der Rückblick von gestern bleibt",
            "Rückblick 11.09.2026 (gebaut)" in bleibt)
    pruefen("das Gespräch bleibt unberührt", "Gespräch" in bleibt)
    pruefen("der Volltextindex ist mit aufgeräumt", index == 0)
    pruefen("ein zweiter Aufruf löscht nichts mehr",
            R.alten_rueckblick_loeschen("12.09.2026") == 0)

# ------------------------------------------------- DRITTENS: der Nachtbericht
#
# Am 13.09. um 05:03 meldete der Rueckblick "aus 223 Zeilen Protokoll und 0
# BERICHTEN 3 Saetze behalten". Alle drei handelten von einem Werkzeug, dem ein
# Gegenstand fehlte; zwei davon sagten dasselbe, und der dritte war die Folge
# eines Verlusts vom Vortag. Die Gegenpruefung um 02:03, die drei
# Zusammenfassungen und der Trockenlauf kamen nicht vor.
#
# "0 BERICHTEN" war richtig: In dieser Nacht wurde kein einziges BERICHT-*.md
# geschrieben, weil die Arbeit in Commits und Sitzungen ging. `gebaut` kommt
# aber AUSSCHLIESSLICH aus den Berichten - also blieb es leer, und der ganze
# Rueckblick bestand aus dem Journal, das nur sagt, was AUFFIEL.
print("\nDer Nachtbericht als dritte Quelle")

import nacht

_ordner = Path(tempfile.mkdtemp(prefix="rueckblick_nacht_"))
_pfad = _ordner / "journal.jsonl"
_echt_journal = nacht.JOURNAL
try:
    import json as _json

    _H = 3600.0
    _nacht_zeilen = [
        {"ts": JETZT - 6 * _H, "kind": "pruefung",
         "text": "4 Sitzungen geprueft, 0 neue Befunde"},
        {"ts": JETZT - 5 * _H, "kind": "sitzung",
         "text": "Es ging um den freien Speicher"},
        {"ts": JETZT - 4 * _H, "kind": "ableiten_trocken",
         "text": "WUERDE anlegen - fakt: eine neue Datei cpu-z_2.17-en.exe, "
                 "4629 KB, im Download-Ordner"},
        # Eine Messung - die gehoert in KEINE der beiden Quellen.
        {"ts": JETZT - 3 * _H, "kind": "sitzung", "von": "test",
         "text": "Diskussion behandelte Spielarten und Desktop"},
    ]
    _pfad.write_text("".join(_json.dumps(e, ensure_ascii=False) + "\n"
                             for e in _nacht_zeilen), encoding="utf-8")
    nacht.JOURNAL = _pfad

    _block = R.nacht_block(JETZT - 12 * _H, JETZT)
    pruefen("es gibt ueberhaupt einen Nachtbericht", bool(_block))
    pruefen("die Gegenpruefung steht darin", "Gegenpruefung" in _block)
    pruefen("die zusammengefassten Gespraeche stehen darin",
            "freien Speicher" in _block)
    pruefen("und dass ein Trockenlauf lief", "Trockenlauf" in _block)

    # DER WICHTIGSTE: Der Dateiname aus dem Trockenlauf darf NICHT mit. Mit ihm
    # schrieb gpt-oss "Ich habe die Datei cpu-z_2.17-en.exe im Download-Ordner
    # angelegt" - es hat sie nicht angelegt, es hat sie bemerkt, und die Zeile
    # sagt zwei Worte weiter "angelegt ist keiner".
    pruefen("der Dateiname aus dem Trockenlauf steht NICHT darin",
            "cpu-z" not in _block, "sonst wird aus Bemerktem Getanes")
    pruefen("stattdessen steht die Entscheidung da",
            "KEINEN" in _block and "Schalter" in _block)

    # Eine Messung ist kein Erlebnis - auch hier nicht.
    pruefen("die Messsitzung steht nicht im Nachtbericht",
            "Spielarten" not in _block)

    # Und die Anleitung des gesprochenen Chronikauftrags gehoert nicht hinein:
    # zwei Auftraege in einem Prompt ergaben `{"gebaut": []}`.
    pruefen("die Anleitung fuer die Chronikfrage ist NICHT mit drin",
            "zaehle KEINE" not in _block)

    # Leere Nacht: kein Block, statt eines Kopfes ohne Inhalt.
    _pfad.write_text("", encoding="utf-8")
    pruefen("eine leere Nacht gibt keinen Block",
            R.nacht_block(JETZT - 12 * _H, JETZT) == "")
finally:
    nacht.JOURNAL = _echt_journal
    import shutil

    shutil.rmtree(_ordner, ignore_errors=True)

# Die Quellen des Journals: `sitzung` hat gefehlt, und damit kam von Calvins
# Gespraechen nichts in den Rueckblick.
pruefen("sitzung ist eine erzaehlende Art", "sitzung" in R.ERZAEHLT)
pruefen("und der Verlust auch",
        "verlust" in R.ERZAEHLT and "kernwissen_fehlt" in R.ERZAEHLT)

# Eine Messung kommt auch aus dem Journal nicht durch.
_seit, _bis = JETZT - 3600, JETZT + 1
_gemischt = [{"ts": JETZT, "kind": "sitzung", "text": "Es ging um Lenas Termin"},
             {"ts": JETZT, "kind": "sitzung", "von": "test",
              "text": "Diskussion behandelte Spielarten"}]
_echt_j = R.JOURNAL
_o2 = Path(tempfile.mkdtemp(prefix="rueckblick_j_"))
try:
    import json as _json2

    _p2 = _o2 / "journal.jsonl"
    _p2.write_text("".join(_json2.dumps(e, ensure_ascii=False) + "\n"
                           for e in _gemischt), encoding="utf-8")
    R.JOURNAL = _p2
    _gelesen = R.zeilen_lesen(_seit, _bis)
    pruefen("aus dem Journal kommt das Gespraech", len(_gelesen) == 1,
            str([e["text"][:30] for e in _gelesen]))
    pruefen("und die Messung nicht",
            all("Spielarten" not in e["text"] for e in _gelesen))
finally:
    R.JOURNAL = _echt_j
    import shutil as _sh

    _sh.rmtree(_o2, ignore_errors=True)


# -------------------------------- VIERTENS: eine Nicht-Handlung ist kein Ereignis
#
# Am 13.09. stand im Rueckblick an erster Stelle: "Ich habe die Datei
# 20250825-L-Connect+3-x64-v2.0.33-f7fc8097.exe nicht geoeffnet, obwohl sie im
# Protokoll gelistet war." Er hat nie versucht, sie zu oeffnen. Das war ein
# `fund` - eine bemerkte Datei im Download-Ordner - aus dem eine Unterlassung
# wurde, mit einem "obwohl", das eine Pflicht erfindet, die es nicht gab.
#
# Die Grenze ist die Wichtigkeit, und sie steht in den DATEN: Eine Datei, die
# das Journal selbst als Verlust meldet, darf verneint werden. Eine
# ungeoeffnete .exe im Download-Ordner meldet niemand als Verlust.
print("\nEine Nicht-Handlung ist kein Ereignis")

_verlustzeilen = [
    {"ts": JETZT, "kind": "verlust",
     "text": "Es fehlen: ERINNERUNG.md, erinnerungen.json, platzverlauf.jsonl."},
    {"ts": JETZT, "kind": "fund",
     "text": "Eine Datei 20250825-L-Connect+3-x64-v2.0.33-f7fc8097.exe, 4 MB."},
]
_vn = R.verlustnamen(_verlustzeilen)
pruefen("die verlorenen Dateinamen werden erkannt",
        "erinnerung.md" in _vn and "erinnerungen.json" in _vn, str(sorted(_vn)))
pruefen("ein blosser Fund zaehlt NICHT als Verlust",
        not any("connect" in n for n in _vn))

pruefen("die ungeoeffnete .exe wird verworfen",
        R._nicht_ereignis(
            "Ich habe die Datei 20250825-L-Connect+3-x64-v2.0.33-f7fc8097.exe "
            "nicht geoeffnet, obwohl sie im Protokoll gelistet war.", _vn))
pruefen("und eine nicht gestartete .exe ebenso",
        R._nicht_ereignis("Ich habe AnyDesk.exe gefunden, konnte sie aber "
                          "nicht starten.", _vn))

# Der wichtigste Gegentest: der ECHTE Verlust muss durch. Eine Wache, die ihn
# mitnimmt, verschweigt genau das, was Calvin wissen muss.
pruefen("der echte Verlust kommt durch",
        not R._nicht_ereignis(
            "Ich habe mehrere Dateien nicht gefunden, darunter ERINNERUNG.md, "
            "erinnerungen.json und platzverlauf.jsonl.", _vn))
pruefen("eine Verneinung ohne Dateinamen kommt durch",
        not R._nicht_ereignis(
            "Ich konnte die Aufgabe nicht ausfuehren, weil ein benoetigter "
            "Gegenstand nicht mitgegeben werden konnte.", _vn))
pruefen("eine Handlung kommt durch",
        not R._nicht_ereignis(
            "Ich habe drei Gespraeche zusammengefasst.", _vn))
pruefen("und die Trockenlauf-Entscheidung auch",
        not R._nicht_ereignis(
            "Ich habe zwei Saetze im Trockenlauf geprueft, aber keine "
            "angelegt, da der Schalter dafuer aus war.", _vn))


# ------------------------------ FUENFTENS: zwei Saetze, die dasselbe sagen
#
# "Dreimal derselbe Befund sind nicht drei Saetze." Am 13.09. um 05:03 sagten
# zwei von drei behaltenen Saetzen dasselbe, und nach dem Einbau der neuen
# Quellen wieder zwei von vier - diesmal in `schiefging`.
#
# Eine WORTENTDOPPLUNG faengt das nicht: die Dubletten lagen bei 0,30 und 0,25
# Ueberdeckung an Inhaltswoertern, ein echtes Paar bei 0,12. Das Modell
# paraphrasiert. Gemessen mit bge-m3 dagegen: 0,805 und 0,713 gegen 0,622 fuers
# hoechste echte Paar - darum AEHNLICH_AB = 0,68.
print("\nZwei Saetze, die dasselbe sagen, sind einer")

pruefen("die Schwelle steht als Zahl da, nicht im Code",
        0.6 < R.AEHNLICH_AB < 0.8, str(R.AEHNLICH_AB))

# Gestellte Vektoren: die Probe soll die AUSWAHL messen, nicht bge-m3.
_V = {
    "a": [1.0, 0.0, 0.0],
    "a2": [0.97, 0.24, 0.0],   # fast gleich wie a  -> Kosinus ~0,97
    "b": [0.0, 1.0, 0.0],      # etwas anderes      -> Kosinus 0
    "c": [0.0, 0.0, 1.0],
}


def _stub(texte):
    return [_V[t] for t in texte]


_bleibt, _doppelt = R.doppelte_weg(["a", "a2", "b"], einbetten=_stub)
pruefen("die Dublette fliegt, der erste bleibt",
        _bleibt == ["a", "b"] and _doppelt == ["a2"],
        f"behalten={_bleibt} verworfen={_doppelt}")

_bleibt, _doppelt = R.doppelte_weg(["a", "b", "c"], einbetten=_stub)
pruefen("drei verschiedene Saetze bleiben alle drei",
        _bleibt == ["a", "b", "c"] and _doppelt == [])

pruefen("ein einzelner Satz geht unveraendert durch",
        R.doppelte_weg(["a"], einbetten=_stub) == (["a"], []))
pruefen("und eine leere Liste auch",
        R.doppelte_weg([], einbetten=_stub) == ([], []))

# Faellt der Einbetter aus, wird NICHT entdoppelt - lieber ein Satz zweimal als
# ein Rueckblick, der an einer stummen Stelle haengt.
_bleibt, _doppelt = R.doppelte_weg(["a", "a2"], einbetten=lambda t: None)
pruefen("ohne Einbetter bleibt alles stehen, statt zu raten",
        _bleibt == ["a", "a2"] and _doppelt == [])
_bleibt, _doppelt = R.doppelte_weg(["a", "a2"], einbetten=lambda t: [[1.0, 0.0]])
pruefen("und eine unvollstaendige Antwort wird nicht verwertet",
        _bleibt == ["a", "a2"] and _doppelt == [])

# Und einmal an den ECHTEN Saetzen, wenn der Einbetter da ist. Das ist die
# Messung, aus der AEHNLICH_AB stammt.
import gedaechtnis as _G

if _G.einbetten(["probe"]):
    _echt = [
        "Ich konnte die geplanten Aufgaben in der Werkzeugsammlung nicht "
        "ausfuehren, weil die benoetigten Gegenstaende nicht vorhanden waren.",
        "Ich habe keine Ausfuehrung der geplanten Lese- und Wunschaufgaben "
        "vorgenommen, weil die erforderlichen Gegenstaende fehlten.",
        "Ich habe die naechtliche Gegenpruefung um 23:40 und 02:03 durchgefuehrt.",
    ]
    _b, _d = R.doppelte_weg(_echt)
    pruefen("an den echten Saetzen vom 13.09.: die Dublette fliegt",
            len(_b) == 2 and _echt[1] in _d,
            f"{len(_b)} behalten, {len(_d)} verworfen")
    pruefen("und die Gegenpruefung bleibt", _echt[2] in _b)
else:
    print("  --   bge-m3 antwortet nicht, die echte Messung entfaellt")


print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
