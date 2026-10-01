"""Unix-socket broker that parks permission requests until a client answers.

The MCP permission server (one child process per Claude session) connects
here and blocks. We hand the request to the owning session, which surfaces it
as an `ask` card. When a client answers, we unblock the socket.
"""
import json
import os
import socket
import threading
import uuid

from . import config


class PendingRequest:
    def __init__(self, req_id, session_key, tool_name, tool_input, conn):
        self.id = req_id
        self.session_key = session_key
        self.tool_name = tool_name
        self.tool_input = tool_input
        self._conn = conn
        self._answered = threading.Event()

    def answer(self, allow, message="", updated_input=None):
        """Send the decision back to the waiting MCP server. Idempotent."""
        if self._answered.is_set():
            return False
        payload = ({"behavior": "allow", "updatedInput": updated_input or self.tool_input}
                   if allow else
                   {"behavior": "deny", "message": message or "Vom Client abgelehnt"})
        try:
            self._conn.sendall((json.dumps(payload) + "\n").encode())
        except OSError:
            pass
        finally:
            self._answered.set()
            try:
                self._conn.close()
            except OSError:
                pass
        return True

    @property
    def answered(self):
        return self._answered.is_set()


class PermissionBroker:
    def __init__(self, socket_path, on_request):
        self.socket_path = socket_path
        self.on_request = on_request          # called with a PendingRequest
        self.pending = {}                     # req_id -> PendingRequest
        self._lock = threading.Lock()
        self._srv = None
        self._stop = threading.Event()

    def start(self):
        tcp = config.tcp_address(self.socket_path)
        if tcp:
            # Windows: loopback TCP. A port in use means another bridge owns
            # it - the same refusal as for a live Unix socket.
            self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self._srv.bind(tcp)
            except OSError:
                self._srv.close()
                raise RuntimeError(f"{self.socket_path} gehört einer laufenden Bridge") from None
            self._srv.listen(16)
            threading.Thread(target=self._accept_loop, daemon=True).start()
            return
        if os.path.exists(self.socket_path):
            # Only clear a stale socket. A live one means another bridge owns
            # this port, and stealing it would strand its pending requests.
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.settimeout(0.5)
            try:
                probe.connect(self.socket_path)
                probe.close()
                raise RuntimeError(
                    f"{self.socket_path} gehört einer laufenden Bridge")
            except (ConnectionRefusedError, OSError):
                pass
            finally:
                try:
                    probe.close()
                except OSError:
                    pass
            os.unlink(self.socket_path)
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(self.socket_path)
        os.chmod(self.socket_path, 0o600)
        self._srv.listen(16)
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._srv.accept()
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        try:
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    conn.close()
                    return
                buf += chunk
            req = json.loads(buf.decode())
        except (OSError, json.JSONDecodeError):
            try:
                conn.close()
            except OSError:
                pass
            return

        pending = PendingRequest(
            req.get("id") or str(uuid.uuid4()),
            req.get("session_key", ""),
            req.get("tool_name", "?"),
            req.get("tool_input") or {},
            conn,
        )
        with self._lock:
            self.pending[pending.id] = pending
        try:
            self.on_request(pending)
        except Exception as exc:  # noqa: BLE001 - never strand the caller
            pending.answer(False, f"iris: {exc}")

    def get(self, req_id):
        with self._lock:
            return self.pending.get(req_id)

    def drop(self, req_id):
        with self._lock:
            self.pending.pop(req_id, None)

    def deny_session(self, session_key, message="Session beendet"):
        """Release anything still waiting when a session dies."""
        with self._lock:
            items = [p for p in self.pending.values() if p.session_key == session_key]
        for p in items:
            p.answer(False, message)
            self.drop(p.id)

    def stop(self):
        self._stop.set()
        with self._lock:
            items = list(self.pending.values())
        for p in items:
            p.answer(False, "iris: Bridge wird beendet")
        if self._srv:
            try:
                self._srv.close()
            except OSError:
                pass
        if not config.tcp_address(self.socket_path) and os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass
