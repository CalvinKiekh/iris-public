"""Testbruecken auf festen Ports - und die Gewissheit, dass wirklich sie antworten.

Belegt schon etwas den Port, startet die Testbruecke nicht, und der Test
spricht still mit dem, was dort laeuft. Am 29.09.2026 war das eine vergessene
Testbruecke vom 14.09.: zwei Wochen lang prueften die Rauchtests deren Code
statt des aktuellen - und liefen gruen, weil sie zufaellig dasselbe Token
hatte. Erst ein Lauf mit frischer Konfiguration fiel mit 401 auf.
"""
import socket
import subprocess


def muss_frei_sein(port):
    """Abbrechen, wenn auf dem Port schon jemand antwortet.

    Ein Verbindungsversuch, kein bind: der sieht auch einen Dienst, der auf
    allen Adressen horcht, und stolpert nicht ueber TIME_WAIT, wenn ein Test
    seine Bruecke absichtlich neu startet. Darum nur vor dem ersten Start.
    """
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
    except OSError:
        return
    try:
        wer = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        wer = ""
    raise SystemExit(f"Port {port} ist schon belegt - der Test wuerde gegen einen fremden "
                     f"Prozess pruefen statt gegen den Code hier.\n{wer}")


def muss_leben(proc, port):
    """Abbrechen, wenn die eigene Testbruecke den Start nicht ueberlebt hat."""
    if proc.poll() is not None:
        raise SystemExit(f"Die Testbruecke auf Port {port} ist beim Start gestorben "
                         f"(Rueckgabe {proc.returncode}).")
