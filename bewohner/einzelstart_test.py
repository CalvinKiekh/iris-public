"""Zwei Bewohner zugleich - der Wettlauf um bewohner.pid.

NICHT die Ursache des Push-Sturms vom 12.09. - die war das rmtree in
archiv_test.py, das die echte werkstatt geloescht hat (74b51b5). Beim Suchen
danach sah es lange so aus: um 20:55:06 liefen zwei Prozesse auf bewohner.py,
um 21:18:49 wieder zwei. Gemessen ist es aber EIN Bewohner. Das venv in
tts-test liegt auf dem Store-Python (pyvenv.cfg: home = ...WindowsApps...),
und dessen pythonw.exe im venv ist ein Umleiter: Er startet den echten
Auslegers als Kindprozess und wartet. Geprueft mit einem Schlaefer-Skript -
zwei Prozesse, aber nur der Kindprozess fuehrt Python aus. Die Sperre nennt
darum zu Recht den Kindprozess.

Was dieser Test prueft, ist trotzdem ein echter Fehler - nur ein schlafender.
Die Luecke sass zwischen zwei Zeilen:

    fd = os.open(sperre, O_CREAT | O_EXCL | O_WRONLY)   # Datei ist LEER
    f.write(str(os.getpid()))                           # PID erst jetzt

Wer die leere Datei traf, las "", `int("")` scheiterte, alt wurde 0 - und 0
galt als "gehoert niemandem". Er loeschte die Sperre des Ersten und nahm sie
selbst. Beide liefen.

Dieser Test spielt genau dieses Fenster nach, ohne einen Bewohner zu starten.

    python -X utf8 einzelstart_test.py
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pruefstand
pruefstand.braucht_windows()

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
import bewohner

ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}"
          + (f"  [{dazu}]" if dazu else ""))


probe = HIER / "werkstatt" / "_einzelstart_probe"
probe.mkdir(parents=True, exist_ok=True)
sperre = probe / "bewohner.pid"

# Die echte werkstatt bleibt unberuehrt - der laufende Bewohner haelt dort
# seine eigene Sperre, und die darf dieser Test nicht anfassen.
echt = bewohner.WERKSTATT
bewohner.WERKSTATT = probe


def aufraeumen():
    sperre.unlink(missing_ok=True)


# ------------------------------------------------- 1. Das nachgespielte Fenster
print("\nDas Fenster: Sperre liegt da, ist aber noch leer")
aufraeumen()
sperre.write_bytes(b"")          # genau der Zustand nach O_EXCL, vor write
pruefen("die Sperre ist da und leer",
        sperre.exists() and sperre.read_bytes() == b"")

# Der Zweite darf sie jetzt NICHT an sich nehmen. Frueher tat er genau das.
ende = {}


def zweiter():
    try:
        bewohner.einzelstart_sichern()
        ende["art"] = "durchgelassen"
    except SystemExit as f:
        ende["art"] = "abgewiesen"
        ende["grund"] = str(f)


t = threading.Thread(target=zweiter, daemon=True)
t.start()

# Waehrend er wartet, schreibt der Erste seine PID fertig - so wie im Betrieb.
time.sleep(0.6)
noch_offen = t.is_alive()
sperre.write_text("424242", encoding="utf-8")   # eine PID, die nicht lebt
t.join(timeout=8)

pruefen("der Zweite wartet, statt die leere Sperre zu nehmen", noch_offen,
        "er hat nicht sofort zugegriffen")
pruefen("er entscheidet erst, als die PID wirklich drinsteht",
        ende.get("art") is not None, str(ende))
# 424242 lebt nicht - also darf er uebernehmen. Das ist richtig.
pruefen("eine TOTE PID darf er uebernehmen",
        ende.get("art") == "durchgelassen", str(ende))
pruefen("und die Sperre nennt danach ihn",
        sperre.read_text(encoding="utf-8").strip() == str(os.getpid()),
        sperre.read_text(encoding="utf-8").strip())


# ------------------------------------------ 2. Eine LEBENDE PID haelt ihn raus
print("\nEine lebende Sperre weist ab")
aufraeumen()
fremd = subprocess.Popen([sys.executable, "-c",
                          "import time; time.sleep(30)"],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
try:
    sperre.write_text(str(fremd.pid), encoding="utf-8")
    raus = None
    try:
        bewohner.einzelstart_sichern()
    except SystemExit as f:
        raus = str(f)
    pruefen("ein lebender Bewohner weist den Zweiten ab", raus is not None,
            str(raus))
    pruefen("und die Begruendung nennt seine PID",
            raus is not None and str(fremd.pid) in raus, str(raus))
    pruefen("die Sperre bleibt unberuehrt",
            sperre.read_text(encoding="utf-8").strip() == str(fremd.pid))
finally:
    fremd.kill()
    fremd.wait(timeout=10)


# ------------------------------------- 3. Eine dauerhaft leere Sperre ist Schrott
print("\nEine Sperre, die leer BLEIBT, stammt von einem Abbruch")
aufraeumen()
sperre.write_bytes(b"")
begonnen = time.monotonic()
bewohner.einzelstart_sichern()
gebraucht = time.monotonic() - begonnen
pruefen("nach der Frist nimmt er die verwaiste Sperre doch",
        sperre.read_text(encoding="utf-8").strip() == str(os.getpid()),
        sperre.read_text(encoding="utf-8").strip())
pruefen(f"er hat dafuer gewartet, nicht zugegriffen "
        f"(>= {bewohner.FRIST_LEER_S} s)",
        gebraucht >= bewohner.FRIST_LEER_S, f"{gebraucht:.2f} s")


# ------------------------------------------- 4. Freies Feld, eigene PID zweimal
print("\nFreies Feld, und der eigene Start zaehlt nicht doppelt")
aufraeumen()
bewohner.einzelstart_sichern()
pruefen("auf freiem Feld nimmt er die Sperre",
        sperre.read_text(encoding="utf-8").strip() == str(os.getpid()))
bewohner.einzelstart_sichern()      # derselbe Prozess noch einmal
pruefen("derselbe Prozess weist sich nicht selbst ab",
        sperre.read_text(encoding="utf-8").strip() == str(os.getpid()))


# --------------------------------- 5. Unlesbar ist kein Freibrief
print("\nUnlesbar heisst nicht herrenlos")
aufraeumen()
sperre.write_text("kein PID sondern Muell", encoding="utf-8")
raus = None
try:
    bewohner.einzelstart_sichern()
except SystemExit as f:
    raus = str(f)
pruefen("eine unlesbare Sperre laesst ihn NICHT durch", raus is not None,
        str(raus))
pruefen("lieber stehen bleiben als zu zweit laufen",
        raus is not None and "unlesbar" in raus.lower(), str(raus))


bewohner.WERKSTATT = echt
aufraeumen()
probe.rmdir()
print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
