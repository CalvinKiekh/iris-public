"""Runs every probe of the resident and says what came of each.

    python -X utf8 pruefen.py              all of them
    python -X utf8 pruefen.py kann haus    only those whose name starts so

Three outcomes, kept apart:

    ok    passed
    --    skipped: it needs what this machine does not have - the resident
          himself, a tool he was given, the model, or Windows (pruefstand.py)
    FAIL  failed, crashed or ran past the time limit

The exit code is 1 as soon as one fails; skipping is not failing. Where no
resident lives, most probes still run - they bend every path into a
throwaway folder - and the ones that need him say so.

Not run here:
    *_messung.py         measurements without a verdict: they print numbers
                         to compare, and a number is not passed or failed
    schluesseltest_app.py  goes through the bridge to a real resident on the
                         PC and restarts him - only ever by hand

One more thing is checked after each probe: where no resident lives, the
workshop next to the code must not exist afterwards either. A probe that
creates it has written into the place that is the real one on his machine.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pruefstand

HIER = Path(__file__).resolve().parent
ZEIT = 900        # a probe that asks the model many times takes minutes


def proben(anfaenge: list[str]) -> list[Path]:
    alle = sorted(set(HIER.glob("*_test.py")) | set(HIER.glob("*_gegentest.py"))
                  | {HIER / "schluesseltest.py"})
    if anfaenge:
        alle = [p for p in alle if p.name.startswith(tuple(anfaenge))]
    return alle


def main() -> int:
    liste = proben(sys.argv[1:])
    if not liste:
        print("keine Probe passt")
        return 1
    ohne_bewohner = not pruefstand.WERKSTATT.exists()
    zahl = {"ok": 0, "--": 0, "FAIL": 0}
    fehlgeschlagen = []
    for p in liste:
        start = time.time()
        try:
            lauf = subprocess.run([sys.executable, "-X", "utf8", p.name], cwd=HIER,
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=ZEIT)
            code, ausgabe = lauf.returncode, lauf.stdout + lauf.stderr
        except subprocess.TimeoutExpired:
            code, ausgabe = None, f"nach {ZEIT} s abgebrochen"
        dauer = time.time() - start
        if code == 0:
            marke, grund = "ok", ""
        elif code == pruefstand.UEBERSPRUNGEN:
            marke = "--"
            grund = next((z.split("uebersprungen:", 1)[1].strip()
                          for z in ausgabe.splitlines() if "uebersprungen:" in z), "")
        else:
            marke = "FAIL"
            zeilen = [z.strip() for z in ausgabe.splitlines() if z.strip()]
            grund = zeilen[-1] if zeilen else f"Rueckgabe {code}"
        if ohne_bewohner and pruefstand.WERKSTATT.exists():
            marke, grund = "FAIL", "hat eine Werkstatt angelegt, wo kein Bewohner wohnt"
        zahl[marke] += 1
        if marke == "FAIL":
            fehlgeschlagen.append((p.name, ausgabe))
        print(f"  {marke:4} {p.name:30} {dauer:5.1f} s  {grund[:90]}", flush=True)
        if marke == "FAIL" and ohne_bewohner and pruefstand.WERKSTATT.exists():
            break       # every probe after it would run against the wrong place

    for name, ausgabe in fehlgeschlagen:
        print(f"\n--- {name} ---")
        print("\n".join(ausgabe.splitlines()[-15:]))
    print(f"\n{zahl['ok']} bestanden, {zahl['--']} uebersprungen, "
          f"{zahl['FAIL']} fehlgeschlagen")
    return 1 if zahl["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
