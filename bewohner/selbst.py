"""Selbstwahrnehmung — der Bewohner misst sich selbst, ohne Modell.

Alles hier sind Messwerte, keine Einschaetzungen. Kein gpt-oss, kein Rechnen
auf der GPU — sonst veraendert das Messen das Gemessene.

Die vier Stoerungen dieser Nacht haetten ihm auffallen muessen:

    Ollama war aus                      -> erreichbar?
    vier verwaiste llama-server         -> Waisen zaehlen
    gpt-oss im geteilten Speicher       -> GETEILT je Prozess
    Rueckkopplung gedaechtnis.db        -> Ticks je Minute

Wird eine Grenze gerissen, gibt es einen `fund` mit Zahl und Vermutung.
Beheben ausserhalb der Werkstatt ist ein Antrag, kein Alleingang.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import httpx

HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"
JOURNAL = WERKSTATT / "journal.jsonl"

OLLAMA = "http://127.0.0.1:11434"
MODELL = "gpt-oss:20b"

# Grenzen. Darunter beziehungsweise darueber stimmt etwas nicht.
TEMPO_MINDESTENS = 80.0        # Token/s; normal sind 120-165
GETEILT_HOECHSTENS = 200       # MiB ausgelagert je Prozess
TICKS_HOECHSTENS = 6.0         # je Minute; mehr heisst Rueckkopplung


def _ohne_fenster(befehl: list[str], frist: int = 30) -> str:
    try:
        r = subprocess.run(befehl, capture_output=True, text=True,
                           timeout=frist, encoding="utf-8", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


# ---------------------------------------------------------------- Messungen


def ollama_da() -> bool:
    try:
        httpx.get(f"{OLLAMA}/api/version", timeout=5).raise_for_status()
        return True
    except httpx.HTTPError:
        return False


def gpu_speicher() -> list[dict]:
    """Dediziert UND geteilt je Prozess.

    Der geteilte Anteil ist der wichtige: Ollamas /api/ps meldet ihn nicht und
    sagt "ganz GPU", waehrend gpt-oss in Wahrheit 1,7 GB im Hauptspeicher
    liegen hatte und auf 6 Token/s fiel. Die Windows-Leistungsindikatoren
    kennen den Unterschied.
    """
    ps = ("Get-Counter '\\GPU Process Memory(*)\\Dedicated Usage',"
          "'\\GPU Process Memory(*)\\Shared Usage' -EA SilentlyContinue | "
          "ForEach-Object { $_.CounterSamples } | "
          "Where-Object { $_.CookedValue -gt 52428800 } | "
          "ForEach-Object { '{0}|{1}|{2:N0}' -f $_.Path, $_.InstanceName, "
          "($_.CookedValue/1MB) }")
    roh = _ohne_fenster(["powershell", "-NoProfile", "-Command", ps], 40)

    je_prozess: dict[str, dict] = {}
    for zeile in roh.splitlines():
        teile = zeile.strip().split("|")
        if len(teile) != 3:
            continue
        pfad, name, wert = teile
        try:
            mib = int(wert.replace(".", "").replace(",", "").replace(" ", ""))
        except ValueError:
            continue
        eintrag = je_prozess.setdefault(name, {"name": name, "dediziert": 0,
                                               "geteilt": 0})
        if "shared" in pfad.lower():
            eintrag["geteilt"] = mib
        else:
            eintrag["dediziert"] = mib
    # Die Indikatoren heissen "pid_49208_luid_0x...". Das ist kein Befund, den
    # Calvin lesen will - also den Prozessnamen dazuholen.
    for e in je_prozess.values():
        e["pid"] = None
        teile = e["name"].split("_")
        if len(teile) > 1 and teile[0] == "pid" and teile[1].isdigit():
            e["pid"] = int(teile[1])
    kennungen = [str(e["pid"]) for e in je_prozess.values() if e["pid"]]
    namen = {}
    if kennungen:
        ps2 = (f"Get-Process -Id {','.join(kennungen)} -EA SilentlyContinue | "
               f"ForEach-Object {{ '{{0}}|{{1}}' -f $_.Id, $_.ProcessName }}")
        for zeile in _ohne_fenster(["powershell", "-NoProfile", "-Command",
                                    ps2], 20).splitlines():
            t = zeile.strip().split("|")
            if len(t) == 2 and t[0].isdigit():
                namen[int(t[0])] = t[1]
    for e in je_prozess.values():
        e["name"] = namen.get(e["pid"], e["name"][:24])

    return sorted(je_prozess.values(),
                  key=lambda e: -(e["dediziert"] + e["geteilt"]))


def waisen() -> list[int]:
    """llama-server ohne lebenden Elternprozess.

    Ollama startet je Modell einen llama-server. Beendet man Ollama hart,
    bleiben sie liegen, belegen die GPU weiter und niemand raeumt sie auf -
    heute Nacht waren es vier.
    """
    # NUR llama-server.exe. "ollama app.exe" ist die Tray-Anwendung; dass ihr
    # Elternprozess weg ist, ist voellig normal - ich habe daraus dreimal
    # einen falschen Antrag an Calvin gemacht.
    ps = ("Get-CimInstance Win32_Process -Filter "
          "\"Name = 'llama-server.exe'\" | "
          "ForEach-Object { '{0}|{1}' -f $_.ProcessId, $_.ParentProcessId }")
    roh = _ohne_fenster(["powershell", "-NoProfile", "-Command", ps], 30)

    # Eine Waise ist ein llama-server, dessen Elternprozess kein lebendes
    # ollama.exe (mehr) ist.
    eltern_ps = ("Get-Process -Id {0} -EA SilentlyContinue | "
                 "ForEach-Object {{ $_.ProcessName }}")
    gefunden = []
    for zeile in roh.splitlines():
        teile = zeile.strip().split("|")
        if len(teile) != 2:
            continue
        try:
            kind, eltern = int(teile[0]), int(teile[1])
        except ValueError:
            continue
        name = _ohne_fenster(["powershell", "-NoProfile", "-Command",
                              eltern_ps.format(eltern)], 15).strip().lower()
        if "ollama" not in name:
            gefunden.append(kind)
    return gefunden


def tempo() -> float | None:
    """Token je Sekunde. Ein winziger Prompt, damit die Messung nichts kostet."""
    try:
        r = httpx.post(f"{OLLAMA}/api/chat", timeout=120, json={
            "model": MODELL, "stream": False, "keep_alive": "30m",
            "think": "low",
            "messages": [{"role": "user", "content": "Sag nur: ok"}]})
        d = r.json()
        n = int(d.get("eval_count", 0))
        s = float(d.get("eval_duration", 0)) / 1e9
        return round(n / s, 1) if s > 0 and n else None
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def ticks_je_minute(minuten: int = 10) -> float:
    """Wie oft hat er in den letzten Minuten nachgesehen?

    Bei jedem Tick fragt er gpt-oss. Mehr als sechs je Minute heisst, dass er
    auf seine eigenen Spuren reagiert - genau die Rueckkopplung, die
    gedaechtnis.db ausgeloest hat.
    """
    if not JOURNAL.exists():
        return 0.0
    grenze = time.time() - minuten * 60
    n = 0
    try:
        for z in JOURNAL.read_text(encoding="utf-8").splitlines()[-2000:]:
            try:
                e = json.loads(z)
            except json.JSONDecodeError:
                continue
            if e.get("kind") == "tick" and float(e.get("ts", 0)) >= grenze:
                n += 1
    except OSError:
        return 0.0
    return round(n / minuten, 1)


# ---------------------------------------------------------------- Urteil


def lagebild() -> dict:
    """Alle Messwerte auf einmal. Reine Zahlen, keine Deutung."""
    da = ollama_da()
    return {
        "ollama": da,
        "tempo": tempo() if da else None,
        "gpu": gpu_speicher(),
        "waisen": waisen(),
        "ticks_je_minute": ticks_je_minute(),
        "ts": time.time(),
    }


def befunde(bild: dict | None = None) -> list[dict]:
    """Was davon ist der Rede wert? Jeder Befund mit Zahl und Vermutung."""
    b = bild if bild is not None else lagebild()
    raus = []

    if not b["ollama"]:
        raus.append({
            "text": "Ollama antwortet nicht. Ohne den Dienst kann ich weder "
                    "denken noch entscheiden.",
            "vermutung": "Der Dienst ist beendet oder hängt.",
            "ausserhalb": True})
        return raus

    # Geteilter Speicher ALLEIN ist kein Befund. Bei freier Grafikkarte sind
    # ein bis zwei Gigabyte Host-Puffer normal - ich habe daraus einen Alarm
    # gemacht, den es nicht gab. Gemeldet wird erst, wenn das Tempo faellt;
    # der geteilte Speicher ist dann die Erklaerung, nicht der Befund.
    tempo_ist = b.get("tempo")
    if tempo_ist is not None and tempo_ist < TEMPO_MINDESTENS:
        ausgelagert = max((p["geteilt"] for p in b["gpu"]), default=0)
        if ausgelagert > GETEILT_HOECHSTENS:
            grund = (f"Ein Teil des Modells liegt im geteilten Speicher "
                     f"({ausgelagert} MiB) - dort rechnet es um ein "
                     f"Vielfaches langsamer.")
        else:
            grund = ("Die Grafikkarte ist frei, die Ursache liegt woanders - "
                     "vielleicht rechnet etwas anderes mit.")
        raus.append({
            "text": f"gpt-oss schafft nur {tempo_ist} Token je Sekunde, "
                    f"normal sind über {TEMPO_MINDESTENS:.0f}.",
            "vermutung": grund,
            "ausserhalb": False})

    if b["waisen"]:
        raus.append({
            "text": f"{len(b['waisen'])} llama-server laufen ohne "
                    f"Elternprozess weiter (PIDs {', '.join(str(p) for p in b['waisen'])}).",
            "vermutung": "Ollama wurde beendet, ohne seine Runner "
                         "mitzunehmen; sie belegen weiter die Grafikkarte.",
            "ausserhalb": True})

    if b["ticks_je_minute"] > TICKS_HOECHSTENS:
        raus.append({
            "text": f"Ich sehe {b['ticks_je_minute']} Mal je Minute nach, "
                    f"höchstens {TICKS_HOECHSTENS:.0f} wären normal.",
            "vermutung": "Ich reagiere auf meine eigenen Spuren - eine Datei, "
                         "die ich selbst schreibe, zählt als Veränderung.",
            "ausserhalb": False})

    return raus
