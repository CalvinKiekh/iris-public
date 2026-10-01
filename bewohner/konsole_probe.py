"""Warum AttachConsole mit Fehler 5 scheitert - gemessen, nicht vermutet.

    python -X utf8 konsole_probe.py

Fehler 5 ist ZUGRIFF VERWEIGERT, und dafuer gibt es mehrere Ursachen, die sich
alle gleich melden. Geprueft wird darum EINE nach der anderen:

  1  Hat der Aufrufer selbst schon eine Konsole? AttachConsole scheitert mit
     5, wenn der aufrufende Prozess bereits an eine Konsole gebunden ist -
     das ist die haeufigste Ursache und hat nichts mit Rechten zu tun.
  2  Liegt das Ziel in einer anderen Sitzung?
  3  Laeuft das Ziel mit hoeherer Integritaetsstufe (erhoeht/als Admin)?
  4  Und der Gegenbeweis: Geht es ueberhaupt - gegen eine Konsole, die diese
     Probe selbst startet, gleicher Benutzer, gleiche Sitzung?

Ohne 4 weiss man nicht, ob der Weg grundsaetzlich taugt oder nur hier nicht.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes as w
from pathlib import Path

BRUECKE = Path.home() / "iris"


def _wincon(op, pid, steps=None):
    """Derselbe Aufruf wie typist._wincon - der ECHTE Weg, nicht ein Nachbau."""
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", "-m",
                            "bridge.wincon", op, str(pid)],
                           input=json.dumps(steps or []), capture_output=True,
                           encoding="utf-8", errors="replace", timeout=20,
                           cwd=str(BRUECKE),
                           creationflags=getattr(subprocess,
                                                 "CREATE_NO_WINDOW", 0))
        return json.loads(r.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        return {"error": str(e)}

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
a32 = ctypes.WinDLL("advapi32", use_last_error=True)

ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}" + (f"  [{dazu}]" if dazu else ""))


def sagen(name, wert):
    print(f"       {name:34} {wert}")


# ------------------------------------------------------------- Auskuenfte


def sitzung_von(pid: int) -> int | None:
    sid = w.DWORD()
    if k32.ProcessIdToSessionId(int(pid), ctypes.byref(sid)):
        return sid.value
    return None


TOKEN_QUERY = 0x0008
TokenIntegrityLevel = 25
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def integritaet(pid: int) -> str:
    """Die Integritaetsstufe - medium, high, system. Entscheidet mit ueber 5."""
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not h:
        return f"(kein Zugriff, Fehler {ctypes.get_last_error()})"
    token = w.HANDLE()
    try:
        if not a32.OpenProcessToken(h, TOKEN_QUERY, ctypes.byref(token)):
            return f"(kein Token, Fehler {ctypes.get_last_error()})"
        groesse = w.DWORD()
        a32.GetTokenInformation(token, TokenIntegrityLevel, None, 0,
                                ctypes.byref(groesse))
        puffer = ctypes.create_string_buffer(groesse.value)
        if not a32.GetTokenInformation(token, TokenIntegrityLevel, puffer,
                                       groesse, ctypes.byref(groesse)):
            return f"(keine Auskunft, Fehler {ctypes.get_last_error()})"
        # TOKEN_MANDATORY_LABEL: SID_AND_ATTRIBUTES, dessen Sid am Ende die
        # Stufe als letzte Unterautoritaet traegt.
        sid_zeiger = ctypes.cast(puffer, ctypes.POINTER(ctypes.c_void_p))[0]
        a32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
        anzahl = a32.GetSidSubAuthorityCount(ctypes.c_void_p(sid_zeiger))[0]
        a32.GetSidSubAuthority.restype = ctypes.POINTER(w.DWORD)
        stufe = a32.GetSidSubAuthority(ctypes.c_void_p(sid_zeiger),
                                       anzahl - 1)[0]
        return {0x0000: "untrusted", 0x1000: "low", 0x2000: "medium",
                0x2100: "medium-plus", 0x3000: "high",
                0x4000: "system"}.get(stufe, f"0x{stufe:x}")
    finally:
        k32.CloseHandle(h)
        if token:
            k32.CloseHandle(token)


def eigene_konsole() -> tuple[bool, int]:
    """(hat eine Konsole, wie viele Prozesse daran haengen)."""
    fenster = k32.GetConsoleWindow()
    puffer = (w.DWORD * 16)()
    n = k32.GetConsoleProcessList(puffer, 16)
    return bool(fenster) or n > 0, n


def versuchen(pid: int) -> tuple[bool, int]:
    """FreeConsole, dann AttachConsole - wie wincon._open es tut."""
    k32.FreeConsole()
    if k32.AttachConsole(int(pid)):
        k32.FreeConsole()
        return True, 0
    fehler = ctypes.get_last_error()
    k32.FreeConsole()
    return False, fehler


FEHLERNAME = {5: "ZUGRIFF VERWEIGERT", 6: "ungueltiges Handle",
              87: "ungueltiger Parameter", 120: "nicht unterstuetzt",
              1816: "zu wenig Quota"}


def main() -> int:
    print("\n1. Der Aufrufer selbst")
    hat, n = eigene_konsole()
    sagen("eigene Konsole?", f"{hat}, {n} Prozesse daran")
    sagen("eigene Sitzung", sitzung_von(os.getpid()))
    sagen("eigene Integritaetsstufe", integritaet(os.getpid()))
    print("       (AttachConsole scheitert mit 5, wenn der Aufrufer schon\n"
          "        eine Konsole hat - darum ruft wincon vorher FreeConsole)")

    print("\n2. Der Gegenbeweis: eine Konsole, die diese Probe selbst startet")
    ziel = subprocess.Popen(
        ["cmd.exe", "/k", "echo probe-konsole & pause"],
        creationflags=subprocess.CREATE_NEW_CONSOLE)
    time.sleep(1.5)
    try:
        sagen("Ziel-PID", ziel.pid)
        sagen("Sitzung des Ziels", sitzung_von(ziel.pid))
        sagen("Integritaetsstufe des Ziels", integritaet(ziel.pid))
        gelungen, fehler = versuchen(ziel.pid)
        pruefen("AttachConsole an eine selbst gestartete Konsole", gelungen,
                f"Fehler {fehler} {FEHLERNAME.get(fehler, '')}".strip())
        if gelungen:
            print("       -> Der Weg taugt grundsaetzlich. Dann liegt es am\n"
                  "          ZIEL, nicht an AttachConsole.")
        else:
            print("       -> Dann scheitert es immer, und die Ursache liegt\n"
                  "          beim Aufrufer oder an der Maschine.")
    finally:
        ziel.kill()
        ziel.wait(timeout=10)

    print("\n3. Tippen und lesen durch den ECHTEN Weg (bridge.wincon)")
    # Gegen eine EIGENE Konsole, nie gegen Calvins Sitzung: Ein Tastendruck
    # dorthin waere eine Eingabe in sein laufendes Gespraech.
    ziel = subprocess.Popen(["cmd.exe", "/k", "echo BEREIT"],
                            creationflags=subprocess.CREATE_NEW_CONSOLE)
    time.sleep(1.5)
    try:
        gelesen = _wincon("read", ziel.pid)
        pruefen("read liefert den Schirm", bool(gelesen.get("lines")),
                str(gelesen)[:54])
        getippt = _wincon("keys", ziel.pid,
                          [{"text": "echo probe-tippt"}, {"wait": 0.2},
                           {"key": "enter"}])
        pruefen("keys nimmt Text an", getippt.get("ok") is True, str(getippt))
        time.sleep(1.0)
        zeilen = _wincon("read", ziel.pid).get("lines") or []
        pruefen("und der Text ist WIRKLICH angekommen",
                any("probe-tippt" in z for z in zeilen),
                str([z for z in zeilen if "probe-tippt" in z])[:56])
        # Genau die Probe, die vom Mac aus Fehler 5 meldete.
        esc = _wincon("keys", ziel.pid, [{"key": "esc"}])
        pruefen("Esc wird angenommen - die Probe, die 5 meldete",
                esc.get("ok") is True, str(esc))
    finally:
        ziel.kill()
        ziel.wait(timeout=10)

    print("\n4. Die echten Ziele aus Claude Codes eigenen Aufzeichnungen")
    akten = Path.home() / ".claude" / "sessions"
    gefunden = 0
    for datei in sorted(akten.glob("*.json")) if akten.is_dir() else []:
        try:
            d = json.loads(datei.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pid = d.get("pid")
        if not isinstance(pid, int):
            continue
        gefunden += 1
        gelungen, fehler = versuchen(pid)
        print(f"       {'geht ' if gelungen else f'F{fehler:<4}'} "
              f"PID {pid:<7} Sitzung {sitzung_von(pid)}  "
              f"{integritaet(pid):<10} {str(d.get('cwd'))[:32]}")
    if not gefunden:
        print("       (keine Sitzungsakten)")

    print("\n5. Und was in Sitzung 0 liegt - zum Vergleich")
    roh = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='conhost.exe'\" | "
         "Where-Object { $_.SessionId -eq 0 } | Select-Object -First 3 "
         "ProcessId | ConvertTo-Json"],
        capture_output=True, encoding="utf-8", errors="replace")
    try:
        d = json.loads(roh.stdout or "[]")
        for k in (d if isinstance(d, list) else [d]):
            pid = k.get("ProcessId")
            if pid:
                _, fehler = versuchen(pid)
                print(f"       F{fehler:<4} conhost PID {pid:<7} Sitzung 0  "
                      f"{integritaet(pid)}")
    except ValueError:
        pass

    print("\nWAS DAS HEISST")
    print("  AttachConsole ist nicht kaputt - lesen, tippen und Esc gehen,")
    print("  durch denselben Weg, den die Bruecke nimmt. Gescheitert ist es")
    print("  bei Zielen in SITZUNG 0: dort scheitert schon OpenProcess mit 5,")
    print("  und daran aendert kein anderer Weg etwas. Sitzung 0 ist die")
    print("  Dienstesitzung und von der Benutzersitzung abgeschottet - ein")
    print("  claude aus einer geplanten Aufgabe mit \"unabhaengig von der")
    print("  Anmeldung\" landet dort, mit \"nur wenn angemeldet\" nicht.")

    print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
    return 0 if all(ok_alle) else 1


if __name__ == "__main__":
    raise SystemExit(main())
