"""Startet die Bruecke ohne Konsolenfenster: setzt den Pfad, arbeitet aus
diesem Ordner und haelt ihre Ausgabe in bridge.log daneben."""
import os
import runpy
import sys

here = os.path.dirname(os.path.abspath(__file__))
os.chdir(here)
sys.path.insert(0, here)

# DAS LOG UMWAELZEN, bevor es unbrauchbar wird.
#
# Es war am 13.09. 5,9 MB gross und bestand fast nur aus Tracebacks: 1686
# ConnectionResetError und 931 ConnectionAbortedError - beide harmlos, der
# Klient geht weg - und dazwischen die sieben AttributeError, auf die es
# ankam. In sechs Megabyte findet die niemand.
#
# Eine Sicherung, mehr nicht: Was zweimal umgewaelzt wurde, war ohnehin nie
# wieder gefragt.
pfad = os.path.join(here, "bridge.log")
try:
    if os.path.getsize(pfad) > 2 * 1024 * 1024:
        alt = pfad + ".1"
        if os.path.exists(alt):
            os.remove(alt)
        os.replace(pfad, alt)
except OSError:
    pass

log = open(pfad, "a", buffering=1, encoding="utf-8")
sys.stdout = sys.stderr = log
sys.argv = ["bridge"]
runpy.run_module("bridge", run_name="__main__")
