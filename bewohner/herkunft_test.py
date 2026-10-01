"""Probe fuer das Herkunftsfeld an der Erinnerung.

    python -X utf8 herkunft_test.py

In der Nacht zum 13.09. lagen siebzehn Erinnerungen ueber "Lenas Arzttermin"
im Gedaechtnis, und es war NICHT ENTSCHEIDBAR, ob sie von Calvin kamen oder
aus pruefung_test.py: `quelle` trug nur "Sitzung s-1789214400", und die
Sitzung, auf die sie zeigte, existierte nicht mehr. Eine Kennung ist kein
Absender.

Gemessen wird beides: dass die Spalte entsteht, wo sie noch fehlt (ohne die
vorhandenen Zeilen anzufassen), und dass der Filter die alten Zeilen NICHT
wegwirft - sie sind aelter als das Feld und gelten als Calvins.
"""
from __future__ import annotations

from einstellungen import NAME, NAMENS, NUTZER
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import probenort

GESAMT = 0
FEHLER = 0


def lies(db: Path, sql: str, werte=()):
    """Lesen und die Verbindung WIRKLICH schliessen.

    `with sqlite3.connect(...)` beendet nur die Transaktion. Unter Windows
    haelt die offene Verbindung die Datei fest, und das Wegraeumen der Probe
    scheitert mit WinError 32.
    """
    v = sqlite3.connect(db)
    try:
        return v.execute(sql, werte).fetchall()
    finally:
        v.close()


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def frisches_gedaechtnis(ort: Path):
    """gedaechtnis mit umgebogener Ablage - und ohne Einbetter.

    Der Einbetter braucht Ollama. Eine Probe, die davon abhaengt, misst an
    einem Tag etwas anderes als am naechsten.
    """
    import gedaechtnis
    gedaechtnis.WERKSTATT = ort
    gedaechtnis.DATENBANK = ort / "gedaechtnis.db"
    gedaechtnis.AENDERUNGEN = ort / "aenderungen"
    gedaechtnis.einbetten = lambda texte: None
    gedaechtnis._einbetter_weg_gemeldet = True
    return gedaechtnis


def probe_spalte_entsteht() -> None:
    print("\nDie Spalte entsteht, wo sie fehlt")
    ort = probenort.ablage("herkunft")
    try:
        # Eine Datenbank im alten Schema - ohne `von`, mit einer Zeile darin.
        db = ort / "gedaechtnis.db"
        v = sqlite3.connect(db)
        try:
            v.executescript(f"""
            CREATE TABLE erinnerung (
                id INTEGER PRIMARY KEY, ts REAL NOT NULL, art TEXT NOT NULL,
                text TEXT NOT NULL, quelle TEXT,
                wichtig INTEGER NOT NULL DEFAULT 0, ersetzt_durch INTEGER);
            INSERT INTO erinnerung(ts, art, text, quelle)
                VALUES (1000.0, 'fakt', '{NAMENS} Tochter heisst Lena Marie',
                        'Gespraech');
            """)
            v.commit()
        finally:
            v.close()
        g = frisches_gedaechtnis(ort)
        g.anlegen()
        spalten = [r[1] for r in lies(db, "PRAGMA table_info(erinnerung)")]
        alt = lies(db, "SELECT text, von FROM erinnerung WHERE id=1")[0]
        pruefe("von" in spalten, "die Spalte `von` ist da")
        pruefe(alt[0] == f"{NAMENS} Tochter heisst Lena Marie",
               "die vorhandene Zeile steht unveraendert da")
        pruefe(alt[1] is None,
               "und ihre Herkunft ist leer - nicht geraten, nicht nachgetragen")

        # Zweimal anlegen() darf nicht stolpern.
        g.anlegen()
        pruefe(True, "anlegen() ein zweites Mal wirft nicht")
    finally:
        probenort.wegraeumen(ort)


def probe_herkunft_wird_geschrieben() -> None:
    print("\nWer etwas sagt, steht daneben")
    ort = probenort.ablage("herkunft")
    try:
        g = frisches_gedaechtnis(ort)
        g.merken("fakt", "Der Rechner heisst DESKTOP-JQQ2462", von=NUTZER)
        g.merken("fakt", "Die Probe hat einen Termin erfunden", von="test")
        g.merken("fakt", "Ohne Angabe gemerkt")
        zeilen = dict(lies(ort / "gedaechtnis.db",
                           "SELECT text, von FROM erinnerung"))
        pruefe(zeilen["Der Rechner heisst DESKTOP-JQQ2462"] == NUTZER,
               f"{NAMENS} Satz traegt '{NUTZER}'")
        pruefe(zeilen["Die Probe hat einen Termin erfunden"] == "probe",
               "der Satz aus der Probe traegt 'probe'")
        pruefe(zeilen["Ohne Angabe gemerkt"] is None,
               "ohne Angabe bleibt das Feld leer")

        # Gefragt wird nach der PROBE, nicht nach Calvin: sein Handy spricht
        # unter "geraet0" und darf nicht durchfallen.
        g.merken("fakt", "Vom Handy aus gesagt", von="geraet0")
        handy = lies(ort / "gedaechtnis.db",
                     "SELECT von FROM erinnerung WHERE text=?",
                     ("Vom Handy aus gesagt",))[0][0]
        pruefe(handy == NUTZER, f"sein Handy gilt als {NAME}, nicht als fremd")
    finally:
        probenort.wegraeumen(ort)


def probe_filter() -> None:
    print("\nDer Filter wirft die alten Zeilen nicht weg")
    ort = probenort.ablage("herkunft")
    try:
        g = frisches_gedaechtnis(ort)
        g.merken("fakt", "Lena geht in die Kita Regenbogen", von=NUTZER)
        g.merken("fakt", "Lena hat einen erfundenen Arzttermin", von="test")
        g.merken("fakt", f"Lena ist {NAMENS} Tochter")      # ohne Feld

        alle = g.abrufen("Lena", 10)
        nur_nutzer = g.abrufen("Lena", 10, von=(NUTZER,))
        nur_probe = g.abrufen("Lena", 10, von=("probe",))
        texte = lambda tr: {t["text"] for t in tr}

        pruefe(len(alle) == 3, "ohne Filter kommen alle drei (%d)" % len(alle))
        pruefe("Lena hat einen erfundenen Arzttermin" not in texte(nur_nutzer),
               "der Satz aus der Probe faellt heraus")
        pruefe("Lena geht in die Kita Regenbogen" in texte(nur_nutzer),
               f"{NAMENS} Satz bleibt")
        pruefe(f"Lena ist {NAMENS} Tochter" in texte(nur_nutzer),
               "und der Satz OHNE Feld bleibt auch - er ist aelter als die "
               "Spalte")
        pruefe(texte(nur_probe) == {"Lena hat einen erfundenen Arzttermin"},
               "nach der Probe gefragt kommt genau der eine Satz")
        pruefe(all("von" in t for t in alle),
               "jeder Treffer traegt seine Herkunft nach aussen")
    finally:
        probenort.wegraeumen(ort)


def probe_entdopplung_unveraendert() -> None:
    print("\nDerselbe Satz bleibt EINE Erinnerung")
    ort = probenort.ablage("herkunft")
    try:
        g = frisches_gedaechtnis(ort)
        erste = g.merken("fakt", "Lena mag Erdbeeren", von=NUTZER)
        zweite = g.merken("fakt", "Lena mag Erdbeeren", von="test")
        pruefe(erste == zweite,
               "zweimal derselbe Satz gibt dieselbe Kennung (%d/%d)"
               % (erste, zweite))
        zeilen = lies(
            ort / "gedaechtnis.db",
            "SELECT von FROM erinnerung WHERE text='Lena mag Erdbeeren'")
        pruefe(len(zeilen) == 1, "und nur eine Zeile in der Tabelle")
        pruefe(zeilen[0][0] == NUTZER,
               "die Herkunft bleibt die des ersten Schreibens")
    finally:
        probenort.wegraeumen(ort)


def probe_volltext_ohne_vektor() -> None:
    print("\nAuch wenn nur der Volltext sucht")
    ort = probenort.ablage("herkunft")
    try:
        g = frisches_gedaechtnis(ort)
        g.merken("zuhause", "Auf dem Desktop liegen acht Spielverknuepfungen",
                 von="test")
        g.merken("zuhause", "Im Downloads-Ordner liegen Installationsdateien",
                 von=NUTZER)
        treffer = g.abrufen("Desktop Spielverknuepfungen", 5, von=(NUTZER,))
        pruefe(all("Spielverknuepfungen" not in t["text"] for t in treffer),
               "der Probensatz kommt auch im Volltext nicht durch")
        pruefe(g.abrufen("Installationsdateien", 5, von=(NUTZER,)),
               f"{NAMENS} Satz kommt im Volltext durch")
    finally:
        probenort.wegraeumen(ort)


def probe_riegel_am_termin() -> None:
    """Der zweite Schreibweg - und der, der am 13.09. offen stand.

    `gedaechtnis.merken` war abgesichert, `erinnern.schreiben` nicht. In dem
    Augenblick, in dem das Ableiten scharf wurde, hat der erste Probenlauf
    einen echten Termin angelegt: "Calvin geht mit Lena zum Arzt", 09:00, aus
    einer Sitzung, die es nie gab.
    """
    print("\nEine Probe kann keinen echten Termin anlegen")
    sys.path.insert(0, str(Path(__file__).parent / "werkstatt" / "werkzeuge"))
    import erinnern
    echt = Path(erinnern.DATEI)
    vorher = erinnern.lesen()
    try:
        erinnern.schreiben(vorher + [{"id": "e-probe", "text": "erfunden"}])
        pruefe(False, "durchgelassen - der Riegel fehlt")
    except probenort.Verweigert:
        pruefe(True, "abgewiesen, mit Grund")
    except Exception as f:
        pruefe(False, "falscher Fehler: %s" % type(f).__name__)
    pruefe(erinnern.lesen() == vorher,
           "und die echte Liste ist unveraendert (%d Eintraege)"
           % len(erinnern.lesen()))
    pruefe(echt.name == "erinnerungen.json", "gemessen am echten Pfad")

    # In einem Probenordner darf sie sehr wohl schreiben.
    ort = probenort.ablage("termin")
    try:
        ziel = ort / "erinnerungen.json"
        erinnern.WERKSTATT_ORDNER = str(ort)
        erinnern.schreiben([{"id": "e-1", "text": "im Probenordner"}],
                           datei=str(ziel))
        pruefe(erinnern.lesen(str(ziel))[0]["text"] == "im Probenordner",
               "im Probenordner schreibt sie ungehindert")
    finally:
        probenort.wegraeumen(ort)


def main() -> int:
    probe_spalte_entsteht()
    probe_herkunft_wird_geschrieben()
    probe_filter()
    probe_entdopplung_unveraendert()
    probe_volltext_ohne_vektor()
    probe_riegel_am_termin()
    print("\n%d Proben, %d Fehler" % (GESAMT, FEHLER))
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
