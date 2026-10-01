"""Owns the live sessions and the shared permission broker."""
import os
import threading
import time
import uuid

from . import config, heartbeat, inventory, permissions, push, session as session_mod, terminals, power, wachen


class Manager:
    def __init__(self, cfg):
        self.cfg = cfg
        self.sessions = {}                 # key -> Session
        self._lock = threading.Lock()
        self.socket_path = config.permission_socket(cfg["port"])
        self.broker = permissions.PermissionBroker(
            self.socket_path, self._on_permission)
        self.broker.start()
        # Sessions running in a terminal, reported by hooks. They share the
        # key space and the card format with the ones hosted here.
        self.terminals = terminals.Registry()
        push.configure(cfg, away=lambda: self.terminals.away)
        # Wie eine Wache ihren Vorarbeiter erreicht. Das Modul selbst kennt
        # weder Sitzungen noch Registry - es bekommt nur diesen einen Griff.
        wachen.configure(self._wecke)
        power.start()
        threading.Thread(target=self._reaper, daemon=True).start()

    def _wecke(self, key, text):
        """Dem Vorarbeiter einen Auftrag in die Sitzung legen.

        Nur für Sitzungen, die die Brücke selbst führt: eine Terminal-Sitzung
        müsste man in ein Fenster tippen, und ein Vorarbeiter, dessen Auftrag
        in einer Eingabezeile stehen bleibt, ist keiner.
        """
        s = self.sessions.get(key)
        if not s or s.exited:
            return False
        ok, _ = s.send(text)
        return bool(ok)

    def _on_permission(self, pending):
        s = self.sessions.get(pending.session_key)
        if not s or s.exited:
            pending.answer(False, "iris: Session unbekannt")
            self.broker.drop(pending.id)
            return
        s.offer_permission(pending)

    def create(self, cwd, *, model=None, permission_mode=None, resume=None,
               fork=False, rolle=""):
        cwd = os.path.abspath(os.path.expanduser(cwd))
        if not os.path.isdir(cwd):
            return None, f"Verzeichnis existiert nicht: {cwd}"
        with self._lock:
            # Abschrift, siehe terminals.Registry.list: nebenlaeufige
            # Aenderungen brechen eine laufende Aufzaehlung ab.
            live = [s for s in list(self.sessions.values()) if not s.exited]
            if len(live) >= self.cfg.get("max_sessions", 8):
                return None, "Zu viele offene Sessions"
            key = uuid.uuid4().hex[:12]
            s = session_mod.Session(
                key, cwd, self.broker, self.socket_path,
                model=model,
                permission_mode=permission_mode or self.cfg["default_permission_mode"],
                resume=resume, fork=fork, rolle=rolle)
            self.sessions[key] = s
        if not s.start():
            return None, s.exit_reason
        return s, ""

    def get(self, key):
        return self.sessions.get(key) or self.terminals.get(key)

    def list(self):
        rows = [s.describe() for s in list(self.sessions.values())]
        rows += self.terminals.list()
        return sorted(rows, key=lambda r: r["last_active"], reverse=True)

    def close(self, key, reason="Vom Nutzer beendet"):
        s = self.sessions.get(key)
        if not s:
            return False
        cwd = s.cwd
        s.stop(reason)
        # A session almost always changed something here; re-reading one
        # project costs under a second and keeps the inventory current
        # without ever running a full sweep in the foreground.
        threading.Thread(target=inventory.refresh_project, args=(cwd,),
                         daemon=True).start()
        return True

    def _reaper(self):
        """Drop sessions that exited a while ago; stop idle ones."""
        while True:
            time.sleep(60)
            # A service that stopped reporting is only noticed by looking,
            # so this rides along with the session reaper.
            try:
                heartbeat.sweep()
                self.terminals.reap()
            except Exception:              # noqa: BLE001
                pass
            timeout = self.cfg.get("idle_timeout_seconds", 3600)
            now = time.time()
            for key, s in list(self.sessions.items()):
                if s.exited and now - s.last_active > 900:
                    self.sessions.pop(key, None)
                elif not s.exited and not s.busy and timeout \
                        and now - s.last_active > timeout:
                    s.stop("Wegen Inaktivität beendet")

    def shutdown(self):
        for s in list(self.sessions.values()):
            if not s.exited:
                s.stop("Bridge wird beendet")
        self.terminals.shutdown()
        self.broker.stop()
