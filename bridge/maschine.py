"""Auf was fuer einem Rechner diese Arbeit entstanden ist.

Gebaut fuer die Uebergabe. Wer eine Sitzung vom Mac auf den PC oder den Pi
zieht, nimmt den Stand mit, aber nicht die Voraussetzungen: dass hier mit
`swift build` gebaut wurde und dort gar kein Swift liegt, dass hier ein
Apple-Chip rechnet und dort eine RTX 5080 steht, dass `make install` nach
/Applications schreibt, was es auf einem Pi nicht gibt.

Hier steht nur, was die Bruecke sicher weiss: die Maschine. Was tatsaechlich
gebaut wurde, was halbfertig ist und welcher Befehl auf dem Zielgeraet nicht
laufen wird, schreibt die Sitzung selbst beim Handoff in eine Datei - sie war
dabei, wir nicht.

Ein Versuch, das aus Makefiles und Skripten zu lesen, steht bewusst nicht
mehr hier. Er hat `MAKE` aus `$(MAKE)` als Programm gemeldet, Woerter aus
deutschen Kommentaren fuer Befehle gehalten und ausgerechnet swift,
xcodebuild und xcodegen uebersehen, weil die Bau-Dateien in Unterordnern
liegen. Raten sieht aus wie Wissen und ist keins.

Bewusst grob: Betriebssystem, Architektur, Kerne, Speicher. Keine
Seriennummern, keine Netznamen, nichts, was in einem Commit nichts verloren
haette.
"""
import os
import platform
import subprocess
import time

from . import config

_CACHE = {"stand": 0.0, "daten": None}
_TTL = 60
_TIMEOUT = 2


def _speicher_gb():
    try:
        n = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        return round(n / (1024 ** 3))
    except (ValueError, OSError, AttributeError):
        return 0


def _chip():
    """What is actually doing the work, in the words the vendor uses."""
    if platform.system() == "Darwin":
        try:
            r = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                               capture_output=True, text=True, timeout=_TIMEOUT)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    if platform.system() == "Linux":
        try:
            with open("/proc/cpuinfo") as fh:
                for zeile in fh:
                    if zeile.split(":")[0].strip() in ("model name", "Model"):
                        return zeile.split(":", 1)[1].strip()
        except OSError:
            pass
    return platform.processor() or platform.machine()


def _betriebssystem():
    s = platform.system()
    if s == "Darwin":
        return "macOS %s" % platform.mac_ver()[0]
    if s == "Linux":
        # Raspberry Pi OS and Ubuntu both answer here; the kernel string
        # alone would say "Linux 6.1" and nothing anybody can act on.
        try:
            with open("/etc/os-release") as fh:
                for zeile in fh:
                    if zeile.startswith("PRETTY_NAME="):
                        return zeile.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
        return "Linux %s" % platform.release()
    if s == "Windows":
        return "Windows %s" % platform.release()
    return s or "unbekannt"


def specs(frisch=False):
    """What this machine is, as far as it matters for picking work up."""
    jetzt = time.time()
    if not frisch and _CACHE["daten"] and jetzt - _CACHE["stand"] < _TTL:
        return _CACHE["daten"]
    daten = {
        "name": config.machine_name(),
        "os": _betriebssystem(),
        "arch": platform.machine(),
        "chip": _chip(),
        "kerne": os.cpu_count() or 0,
        "ram_gb": _speicher_gb(),
        "shell": os.path.basename(os.environ.get("SHELL", "")) or "",
    }
    _CACHE.update({"stand": jetzt, "daten": daten})
    return daten


def kurz(s=None):
    """One line naming the machine, for the order the session is given."""
    s = s or specs()
    teile = [s["os"], s["chip"]]
    if s["kerne"]:
        teile.append("%d Kerne" % s["kerne"])
    if s["ram_gb"]:
        teile.append("%d GB" % s["ram_gb"])
    return "%s (%s)" % (s["name"], ", ".join(t for t in teile if t))
