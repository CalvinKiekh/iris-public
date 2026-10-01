"""Eingreifen bei Ollama - das eine Recht, das Calvin erteilt hat.

Antrag a-1789194236, genehmigt am 12.09.2026 um 08:24.

Erlaubt ist GENAU ZWEIERLEI:
  - den Ollama-Dienst neu starten, wenn er nicht antwortet
  - verwaiste llama-server beenden, die die Grafikkarte belegen

Sonst nichts. Keine anderen Prozesse, keine geplanten Aufgaben, keine
Systemeinstellungen. Dieses Modul liegt bewusst NICHT in werkstatt\\werkzeuge:
Die Abnahme dort verbietet das Beenden von Prozessen, und das zu Recht. Was
hier steht, ist kein selbstgebautes Werkzeug, sondern ein erteiltes Recht -
und es ist genau so eng geschnitten wie der Antrag.

Fuenf Regeln, alle aus Calvins Genehmigung:
  1. Erst messen, dann eingreifen.
  2. Hoechstens einmal alle zehn Minuten.
  3. Jede Nutzung ins Journal und ins Gedaechtnis.
  4. Nach dem Eingriff pruefen, ob es geholfen hat.
  5. Zweimal hintereinander erfolglos -> aufhoeren und melden.
"""
from __future__ import annotations

from einstellungen import NAME
import os
import subprocess
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
OLLAMA_APP = Path(os.environ.get("LOCALAPPDATA", "")) / \
    "Programs" / "Ollama" / "ollama app.exe"

# Regel 2: Abstand zwischen zwei Eingriffen.
ABSTAND_S = 600.0
# Regel 5: So oft darf es erfolglos bleiben, dann ist Schluss.
FEHLVERSUCHE_MAX = 2

_zuletzt = 0.0
_erfolglos = 0
_gesperrt = False


def _ohne_fenster(befehl: list[str], frist: int = 60) -> str:
    try:
        r = subprocess.run(befehl, capture_output=True, text=True,
                           timeout=frist, encoding="utf-8", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def lage() -> dict:
    """Regel 1: erst messen. Was ist wirklich los?"""
    import selbst
    b = selbst.lagebild()
    return {"ollama": b.get("ollama"), "tempo": b.get("tempo"),
            "waisen": b.get("waisen") or []}


def noetig(b: dict) -> str | None:
    """Gibt den Grund zurueck, wenn ein Eingriff angezeigt ist - sonst None.

    Ein fehlender Messwert ist KEIN Befund. Er heisst "ich weiss es nicht",
    und dann wird nicht eingegriffen - erst messen, dann eingreifen, so steht
    es in RECHT-OLLAMA.md.

    Am 12.09. hat der Mac noetig() ein leeres Lagebild uebergeben, weil er
    selbst.bild() aufrief statt selbst.lagebild(). Die Antwort war "Ollama
    antwortet nicht", und darf() gab den Eingriff frei: Ein Tippfehler haette
    genuegt, um den Dienst neu zu starten, mit dem er denkt - mitten im
    Durchgang, in dem er es beschliesst. Im Betrieb ist es nie passiert, weil
    der Faden ein echtes Bild bekommt. Eine Kante, die nur deshalb nicht
    schneidet, weil niemand hingefasst hat, gehoert trotzdem weg.
    """
    if not isinstance(b, dict) or "ollama" not in b:
        return None
    if b.get("ollama") is None:
        return None
    if not b.get("ollama"):
        return "Ollama antwortet nicht"
    if b.get("waisen"):
        return (f"{len(b['waisen'])} verwaiste llama-server belegen die "
                f"Grafikkarte")
    tempo = b.get("tempo")
    if tempo is not None and tempo < 30:
        return f"gpt-oss schafft nur {tempo} Token je Sekunde"
    return None


def darf(jetzt: float | None = None) -> tuple[bool, str]:
    """Regeln 2 und 5: Abstand halten, und nach zwei Fehlschlaegen aufhoeren."""
    jetzt = jetzt if jetzt is not None else time.time()
    if _gesperrt:
        return False, ("ich habe es zweimal versucht und es hat nicht "
                       f"geholfen - jetzt ist {NAME} dran")
    her = jetzt - _zuletzt
    if _zuletzt and her < ABSTAND_S:
        return False, f"vor {int(her)} Sekunden habe ich schon eingegriffen"
    return True, "erlaubt"


def waisen_beenden(pids: list[int]) -> list[int]:
    """Beendet AUSSCHLIESSLICH die uebergebenen llama-server.

    Vor dem Beenden wird jede Kennung noch einmal auf den Namen geprueft -
    eine Liste von Zahlen ist kein Freibrief, und eine veraltete Kennung
    koennte inzwischen einem fremden Prozess gehoeren.
    """
    beendet = []
    for pid in pids:
        name = _ohne_fenster([
            "powershell", "-NoProfile", "-Command",
            f"(Get-Process -Id {int(pid)} -EA SilentlyContinue).ProcessName"
        ], 20).strip().lower()
        if "llama" not in name:
            continue                      # nicht unser Prozess - Finger weg
        _ohne_fenster(["taskkill", "/PID", str(int(pid)), "/F"], 30)
        beendet.append(int(pid))
    return beendet


def ollama_starten() -> bool:
    if not OLLAMA_APP.is_file():
        return False
    try:
        subprocess.Popen([str(OLLAMA_APP)],
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def eingreifen(journal=None, trocken: bool = False) -> dict:
    """Der ganze Ablauf: messen, entscheiden, handeln, nachpruefen, melden."""
    global _zuletzt, _erfolglos, _gesperrt

    def sagen(art: str, text: str, **extra) -> None:
        if journal:
            journal(art, text, **extra)
        else:
            print(f"  [{art}] {text}")

    vorher = lage()
    grund = noetig(vorher)
    if not grund:
        return {"getan": False, "grund": "nichts zu tun", "lage": vorher}

    erlaubt, warum = darf()
    if not erlaubt:
        return {"getan": False, "grund": warum, "lage": vorher}

    if trocken:
        return {"getan": False, "grund": f"Trockenlauf - ich würde jetzt "
                                         f"eingreifen, weil {grund}",
                "lage": vorher, "wuerde": True}

    sagen("eingriff", f"Ich greife ein, weil {grund}. {NAME} hat mir das mit "
                      f"Antrag a-1789194236 erlaubt.", grund=grund)
    _zuletzt = time.time()

    getan = []
    if vorher["waisen"]:
        beendet = waisen_beenden(vorher["waisen"])
        getan.append(f"{len(beendet)} verwaiste llama-server beendet")
    if not vorher["ollama"]:
        getan.append("Ollama neu gestartet" if ollama_starten()
                     else "Ollama ließ sich nicht starten")

    # Regel 4: nachsehen, ob es geholfen hat.
    time.sleep(20)
    nachher = lage()
    geholfen = noetig(nachher) is None

    if geholfen:
        _erfolglos = 0
        text = (f"Das hat geholfen: {', '.join(getan)}. Ollama antwortet "
                f"wieder" + (f" mit {nachher['tempo']} Token je Sekunde."
                             if nachher.get("tempo") else "."))
    else:
        _erfolglos += 1
        text = (f"Das hat nicht geholfen: {', '.join(getan)}. "
                f"{noetig(nachher)}.")
        if _erfolglos >= FEHLVERSUCHE_MAX:
            _gesperrt = True
            sagen("fund", f"Ich habe zweimal versucht, Ollama wieder zum "
                          f"Laufen zu bringen, und es hat nicht geholfen. "
                          f"{noetig(nachher)}. Ich höre auf, es weiter zu "
                          f"versuchen - da muss jemand nachsehen.",
                  eingriff=True)

    sagen("eingriff", text, geholfen=geholfen)
    try:
        import gedaechtnis
        gedaechtnis.merken("ereignis", text, quelle="Eingriff")
    except Exception:
        pass
    return {"getan": True, "geholfen": geholfen, "was": getan,
            "vorher": vorher, "nachher": nachher}


if __name__ == "__main__":
    sys.path.insert(0, str(HIER))
    trocken = "--trocken" in sys.argv or "--selbsttest" in sys.argv
    b = lage()
    print(f"Ollama: {b['ollama']}, Tempo: {b['tempo']}, "
          f"Waisen: {b['waisen'] or 'keine'}")
    grund = noetig(b)
    print(f"Eingriff nötig: {grund or 'nein'}")
    erlaubt, warum = darf()
    print(f"Dürfte ich: {'ja' if erlaubt else 'nein'} - {warum}")
    if trocken:
        print("\nTrockenlauf - es wird nichts angefasst.")
        print(eingreifen(trocken=True))
