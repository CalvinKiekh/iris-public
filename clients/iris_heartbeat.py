"""iris heartbeat — copy this file into any project that should report in.

The contract, in full:

    every N seconds a service POSTs to  /api/heartbeat  with

        name      what this service is        required  "bev-stitch"
        host      which machine it runs on    required  "pi-head"
        status    "ok" | "warn" | "error"     default   "ok"
        detail    anything worth seeing       optional  {"queue": 3}
        version   git sha, tag, whatever      optional  "1.4.2"
        interval  how often it will report    default   60

Rules that make the dashboard trustworthy:

  - `status` is the service's own judgement, not a guess by iris. Report
    "warn" while degraded and "error" when the job is not being done.
    A service that cannot do its work but keeps saying "ok" is worse than
    one that stops reporting.
  - `interval` is a promise. Miss it by 2.5x and the service is shown as
    missing, which is the one state a service cannot report about itself.
  - `detail` is free-form and shown as-is. Keep it to a handful of numbers
    a person can read at a glance.

Usage — a background thread that stops caring if iris is unreachable:

    from iris_heartbeat import Heartbeat
    hb = Heartbeat("bev-stitch", host="pi-head")
    hb.start()
    ...
    hb.status("warn", queue=len(pending))    # whenever something changes

Or one shot, e.g. from cron:

    Heartbeat("nightly-backup", host="nas").once(status="ok", files=1204)

Configuration comes from the environment so the same file works everywhere:

    IRIS_URL     the bridge, e.g. http://100.x.y.z:8780 (make ingest-token)
    IRIS_TOKEN   the ingest token (make ingest-token)
    IRIS_HOST    default host name, else the machine's hostname
"""
import json
import os
import sys
import socket
import threading
import time
import urllib.error
import urllib.request

# No default: the bridge is somebody's machine, and a guessed address sends
# a service's heartbeat to the wrong person. `make ingest-token` prints both.
DEFAULT_URL = os.environ.get("IRIS_URL", "")
DEFAULT_TOKEN = os.environ.get("IRIS_TOKEN", "")
DEFAULT_HOST = os.environ.get("IRIS_HOST") or socket.gethostname().split(".")[0]


class Heartbeat:
    def __init__(self, name, *, host=None, url=None, token=None,
                 interval=60, version="", on_error=None):
        self.name = name
        self.host = host or DEFAULT_HOST
        base = (url or DEFAULT_URL).rstrip("/")
        self.url = base + "/api/heartbeat" if base else ""
        self._ohne_ziel_gemeldet = False
        self.token = token or DEFAULT_TOKEN
        self.interval = interval
        self.version = version
        self.on_error = on_error          # called with the exception, or None
        self._status = "ok"
        self._detail = {}
        self._stop = threading.Event()
        self._thread = None

    # ---- what the service says about itself ----

    def status(self, status="ok", **detail):
        """Set the current state. Sent with the next beat, and right away."""
        self._status = status
        self._detail = detail
        self.once(status=status, **detail)

    def ok(self, **detail):
        self.status("ok", **detail)

    def warn(self, **detail):
        self.status("warn", **detail)

    def error(self, **detail):
        self.status("error", **detail)

    # ---- sending ----

    def once(self, status=None, **detail):
        """Send a single heartbeat. Never raises - a monitoring call must
        not be able to take down the thing it monitors."""
        payload = {
            "name": self.name, "host": self.host,
            "status": status or self._status,
            "detail": detail or self._detail,
            "version": self.version, "interval": self.interval,
        }
        if not self.url:
            # Never disturb the host program - but do not stay silent either:
            # a heartbeat that never leaves looks like a service that is fine.
            if not self._ohne_ziel_gemeldet:
                self._ohne_ziel_gemeldet = True
                fehler = RuntimeError("iris heartbeat: IRIS_URL fehlt - "
                                      "Adresse und Token liefert `make ingest-token`")
                print(fehler, file=sys.stderr)
                if self.on_error:
                    try:
                        self.on_error(fehler)
                    except Exception:       # noqa: BLE001
                        pass
            return False
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + self.token},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                r.read()
            return True
        except Exception as exc:            # noqa: BLE001 - by design
            if self.on_error:
                try:
                    self.on_error(exc)
                except Exception:           # noqa: BLE001
                    pass
            return False

    # ---- background operation ----

    def start(self):
        if self._thread:
            return self
        self._stop.clear()

        def loop():
            while not self._stop.is_set():
                self.once()
                self._stop.wait(self.interval)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        return self

    def stop(self, final_status="gestoppt"):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        # A clean shutdown says so, instead of just going quiet - that is
        # the difference between "someone turned it off" and "it crashed".
        self.once(status=final_status)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop("error" if exc[0] else "gestoppt")
        return False


if __name__ == "__main__":
    import sys
    hb = Heartbeat(sys.argv[1] if len(sys.argv) > 1 else "test")
    print("gesendet:", hb.once(status="ok", note="Selbsttest"))
