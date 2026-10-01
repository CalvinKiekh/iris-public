"""Was FERTIG geworden ist - die Art, die dem Journal gefehlt hat.

Punkt 1 aus SKIZZE-UMBAUTEN.md, von Calvin am 13.09. freigegeben.

DAS PROBLEM IN EINEM SATZ: Das Journal sagt, was auffiel - nicht, was getan
wurde. Darum hat jede Stelle, die "was habe ich getan" braucht, sich eine
eigene Quelle gebaut: `nacht.ARTEN` liest ueber das Journal, der Rueckblick
liest BERICHT-*.md, und wenn keine da sind, `nacht.geteilt()`. Was in einer
Entwicklungsnacht fertig wurde, kannte KEINE der drei - es stand in Commits.
Der Rueckblick vom 13.09. erzaehlte darum drei von sechs Punkten der Nacht.

EIN ABSCHLUSS OHNE BELEG IST EINE BEHAUPTUNG, und davon hat der Bau genug.
Darum ist `belegt_durch` Pflicht und nicht Zierde: eine Probe, ein Commit,
eine Messung, eine Datei mit Zahlen darin. Wer nichts vorzuweisen hat, hat
nichts abgeschlossen - dann gehoert die Zeile nicht ins Journal.

    abschluss.schreiben(journal,
                        "Die Bestandsaufnahme ist durch",
                        woran="Bestandsaufnahme",
                        belegt_durch="bestand.json: 1841 Dateien, 18 Gruppen")

DIE ICH-FORM IST DIE GRENZE. Was hier steht, hat ER getan. Was an ihm gebaut
wurde, steht nicht hier - dafuer gibt es `an_mir()`, und die beiden werden nie
vermischt. `nacht.geteilt()` macht denselben Schnitt seit 2996955, aus
demselben Grund: Sonst erzaehlt er Calvin eine Geschichte, die ihm nicht
gehoert.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

HIER = Path(__file__).parent

# Hoechstens so viele Abschluesse in einer Auskunft - JE QUELLE, nicht
# gemeinsam. Der Fehler waere sonst derselbe wie bei `bestand`: Achtzehn
# Erkenntnisse je Nacht verdraengten alles andere, bis sie absichtlich unter
# `fund` gewichtet wurden. Eine Entwicklungsnacht liefert neun Commits, und
# die duerfen nicht die drei Saetze verdraengen, die von IHM handeln.
JE_QUELLE_MAX = 6

# Wie weit zurueck der Commit-Leser sieht, wenn niemand etwas anderes sagt.
STUNDEN = 12.0


def schreiben(journal, text: str, woran: str, belegt_durch: str) -> bool:
    """Eine Abschlusszeile - oder gar keine.

    Gibt zurueck, ob geschrieben wurde. Fehlt der Beleg, wird NICHT
    geschrieben und auch nichts stattdessen: Eine Zeile "fertig, weiss aber
    nicht wodurch" ist genau die Behauptung, gegen die die Art gebaut ist.
    """
    text = " ".join(str(text or "").split())
    woran = " ".join(str(woran or "").split())
    belegt_durch = " ".join(str(belegt_durch or "").split())
    if not (journal and text and belegt_durch):
        return False
    journal("abschluss", text[:300], woran=woran[:80],
            belegt_durch=belegt_durch[:200])
    return True


def _lesbar(zeile: str) -> str:
    """Ein Commit-Betreff, wie er dasteht - ohne Praefix, ohne Verschoenerung."""
    return " ".join(str(zeile or "").split())


def an_mir(stunden: float = STUNDEN, jetzt: float | None = None,
           hoechstens: int = JE_QUELLE_MAX, ordner: Path | None = None,
           lauf=None) -> list[dict]:
    """Was an MIR gebaut wurde - aus den Commits, nicht aus dem Journal.

    Das ist die vierte Zeile aus der Tabelle in SKIZZE-UMBAUTEN.md, und sie
    ist der Grund fuer den ganzen Umbau. Die Commit-Betreffe sind hier ohnehin
    ganze Saetze ("Eine Art ohne Gewicht ist kein Mittelwert - sie ist ein
    Loch"), es gibt keinen Schreibweg zu vergessen, und der Beleg ist der
    Hash.

    KEINE ICH-FORM. Diese Saetze gehoeren nicht ihm: Calvin und ich haben das
    gebaut, nicht er. Wer sie in die Ich-Form setzt, verschiebt die Grenze -
    `SYSTEM_GEBAUT` hat gegen genau das schon einen Absatz, und ein echter
    Fehlsatz steht darin. Darum tragen sie hier ein eigenes Feld und werden
    getrennt ausgewiesen.

    `lauf` ist der Aufruf von git als Parameter - ohne ihn misst eine Probe
    das echte Repository, und das sieht an jedem Tag anders aus.
    """
    jetzt = time.time() if jetzt is None else jetzt
    seit = time.strftime("%Y-%m-%dT%H:%M:%S",
                         time.localtime(jetzt - stunden * 3600))
    befehl = ["git", "log", f"--since={seit}", "--no-merges",
              "--format=%h\x1f%ct\x1f%s"]
    try:
        roh = (lauf or _git)(befehl, ordner or HIER)
    except Exception:
        # Kein git, kein Repository, kein Netz - das ist kein Fehler des
        # Bewohners. Dann gibt es diese Quelle heute eben nicht.
        return []

    heraus: list[dict] = []
    for zeile in str(roh).splitlines():
        teile = zeile.split("\x1f")
        if len(teile) != 3:
            continue
        hash_, ts, betreff = teile
        betreff = _lesbar(betreff)
        if not betreff:
            continue
        try:
            wann = float(ts)
        except ValueError:
            continue
        heraus.append({"hash": hash_.strip(), "ts": wann, "text": betreff,
                       "belegt_durch": f"Commit {hash_.strip()}"})
    heraus.sort(key=lambda e: -e["ts"])
    return heraus[:hoechstens]


def _git(befehl: list[str], ordner: Path) -> str:
    z = subprocess.run(befehl, cwd=str(ordner), capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       timeout=20)
    if z.returncode != 0:
        raise RuntimeError(z.stderr.strip()[:200] or "git hat nicht geliefert")
    return z.stdout


def saetze(eintraege: list[dict], hoechstens: int = JE_QUELLE_MAX) -> list[str]:
    """Abschlusszeilen als Text, mit dem Beleg daneben.

    Der Beleg gehoert MIT in die Zeile, nicht nur in die Datei. Er ist der
    Unterschied zwischen "ich habe die Gegenpruefung laufen lassen" und
    demselben Satz, den ein Modell auch dann bilden kann, wenn nichts lief.
    """
    heraus = []
    for e in eintraege[:hoechstens]:
        text = " ".join(str(e.get("text") or "").split())
        if not text:
            continue
        beleg = " ".join(str(e.get("belegt_durch") or "").split())
        uhr = ""
        try:
            uhr = time.strftime("%H:%M", time.localtime(float(e.get("ts") or 0)))
        except (TypeError, ValueError, OSError):
            pass
        heraus.append(f"{uhr + ' ' if uhr else ''}{text}"
                      + (f" [belegt durch {beleg}]" if beleg else ""))
    return heraus


def main() -> int:
    """python abschluss.py - was in den letzten Stunden an mir gebaut wurde."""
    for e in an_mir(hoechstens=20):
        print(f"  {time.strftime('%d.%m. %H:%M', time.localtime(e['ts']))}  "
              f"{e['text']}  ({e['belegt_durch']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
