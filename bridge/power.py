"""Whether the Mac runs on its power supply.

Unplugged, it goes to sleep after a while (as set up in its energy
settings), and every session on it stops with it - a phone would only find
out by silence. So the phone hears it the moment the cable comes out, while
the Mac can still speak, and again when it is back.
"""
import re
import subprocess
import sys
import threading
import time

from . import push

EVERY = 20

# What the last look found - for /api/health.
state = {"source": None, "percent": None, "since": None}


def read():
    """("ac" | "battery", percent) - or None where there is no pmset."""
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.run(["pmset", "-g", "ps"], capture_output=True, text=True,
                             timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    source = "ac" if "AC Power" in out else "battery" if "Battery Power" in out else None
    m = re.search(r"(\d+)%", out)
    return (source, int(m.group(1)) if m else None) if source else None


def _say(source, percent):
    if source == "battery":
        alert = {"title": "iris", "subtitle": "Mac läuft auf Akku",
                 "body": (f"Das Stromkabel ist ab ({percent} %). Im Akkubetrieb geht der Mac "
                          "bald schlafen – laufende Sitzungen halten dann an.")}
        push.send({"aps": {"alert": alert, "sound": "default"},
                   "iris": {"kind": "power", "source": source}})
    else:
        alert = {"title": "iris", "subtitle": "Mac wieder am Strom",
                 "body": "Die Sitzungen können weiterlaufen."}
        push.send({"aps": {"alert": alert}, "iris": {"kind": "power", "source": source}})


def _loop():
    while True:
        found = read()
        if found:
            source, percent = found
            before = state["source"]
            state.update(source=source, percent=percent)
            if before and source != before:
                state["since"] = time.time()
                _say(source, percent)
        time.sleep(EVERY)


def start():
    threading.Thread(target=_loop, name="power", daemon=True).start()
