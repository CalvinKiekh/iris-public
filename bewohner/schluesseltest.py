"""Der Schluessel-Test aus AUFTRAG-IRIS.md - fuenf Schritte.

    python schluesseltest.py

1. "Merk dir, dass der Schluessel im Flur liegt."  -> Fakt angelegt
2. Neustart (neuer Prozess, nichts im Speicher)    -> "Im Flur."
3. "Der Schluessel liegt jetzt in der Kueche."     -> alter Fakt ersetzt,
                                                      nicht doppelt
4. Aus der App "vergessen"                         -> er weiss es nicht mehr
5. Zeiten: Abruf unter 100 ms

Der Test laeuft gegen die Schnittstelle, nicht gegen die Innereien - er gilt
deshalb fuer jeden Unterbau gleichermassen.
"""
from einstellungen import NAME
import subprocess
import sys
import time
from pathlib import Path

import pruefstand
# Steps 1-4 write into his real memory, and step 2 restarts a process
# that finds it by its own path - there is nothing to bend here.
pruefstand.braucht_bewohner()

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))

import gedaechtnis as g   # noqa: E402

FRAGE = "Wo liegt der Schlüssel?"


def zeile(nr: str, text: str, ok: bool | None = None) -> None:
    marke = "" if ok is None else ("  [ok]" if ok else "  [FEHLER]")
    print(f"{nr}  {text}{marke}")


def treffer_text(treffer: list[dict]) -> str:
    return " | ".join(t["text"] for t in treffer[:3]) or "(nichts)"


def schritt1() -> int:
    kennung = g.merken("fakt", "Der Schlüssel liegt im Flur.",
                       quelle=f"Zuruf von {NAME}", wichtig=True)
    zeile("1.", f"gemerkt als Fakt #{kennung}", kennung > 0)
    return kennung


def schritt2() -> bool:
    """Neuer Prozess - beweist, dass nichts im Speicher haengt."""
    code = (
        "import sys, time; sys.path.insert(0, r'%s'); import gedaechtnis as g; "
        "t0=time.perf_counter(); tr=g.abrufen(%r); "
        "print(round((time.perf_counter()-t0)*1000,1)); "
        "print(tr[0]['text'] if tr else '')" % (HIER, FRAGE))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=300)
    zeilen = [z for z in r.stdout.splitlines() if z.strip()]
    if len(zeilen) < 2:
        zeile("2.", f"Abruf im neuen Prozess gescheitert: "
                    f"{(r.stderr or '')[-200:]}", False)
        return False
    ms, text = zeilen[0], zeilen[1]
    ok = "flur" in text.lower()
    zeile("2.", f"neuer Prozess, Antwort: „{text}“ ({ms} ms)", ok)
    return ok


def schritt3(alt: int) -> bool:
    neu = g.merken("fakt", "Der Schlüssel liegt jetzt in der Küche.",
                   quelle=f"Zuruf von {NAME}", wichtig=True, ersetzt=alt)
    treffer = g.abrufen(FRAGE)
    texte = [t["text"].lower() for t in treffer]
    hat_kueche = any("küche" in t for t in texte)
    hat_flur = any("flur" in t for t in texte)
    ok = hat_kueche and not hat_flur
    zeile("3.", f"nach Ersetzen: {treffer_text(treffer)}", ok)
    if hat_flur:
        print("      der alte Fakt steht noch daneben - ersetzt_durch greift nicht")
    return ok, neu


def schritt4(kennung: int) -> bool:
    g.AENDERUNGEN.mkdir(parents=True, exist_ok=True)
    (g.AENDERUNGEN / f"{kennung}.json").write_text(
        '{"aktion": "vergessen"}', encoding="utf-8")
    getan = g.aenderungen_einlesen()
    treffer = g.abrufen(FRAGE)
    texte = [t["text"].lower() for t in treffer]
    ok = getan == 1 and not any("küche" in t or "flur" in t for t in texte)
    zeile("4.", f"nach „vergessen“: {treffer_text(treffer)}", ok)
    return ok


def schritt5() -> bool:
    zeiten = []
    for _ in range(5):
        t0 = time.perf_counter()
        g.abrufen(FRAGE)
        zeiten.append((time.perf_counter() - t0) * 1000)
    mittel = sum(zeiten) / len(zeiten)
    ok = mittel < 100
    zeile("5.", f"Abruf im Mittel {mittel:.1f} ms "
                f"(min {min(zeiten):.1f}, max {max(zeiten):.1f})", ok)
    return ok


def main() -> None:
    g.anlegen()
    # Sauber anfangen: alte Schluessel-Fakten aus frueheren Laeufen weg.
    with g._verbindung() as v:
        alt = [int(r[0]) for r in v.execute(
            "SELECT id FROM erinnerung WHERE text LIKE '%chlüssel%'").fetchall()]
    for k in alt:
        g.vergessen(k)
    if alt:
        print(f"({len(alt)} Fakten aus früheren Läufen entfernt)\n")

    ergebnisse = []
    erste = schritt1()
    ergebnisse.append(erste > 0)
    ergebnisse.append(schritt2())
    ok3, zweite = schritt3(erste)
    ergebnisse.append(ok3)
    ergebnisse.append(schritt4(zweite))
    ergebnisse.append(schritt5())

    bestanden = sum(1 for e in ergebnisse if e)
    print(f"\n{bestanden} von 5 bestanden")
    sys.exit(0 if bestanden == 5 else 1)


if __name__ == "__main__":
    main()
