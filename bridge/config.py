"""Configuration and paths for the iris bridge."""
import json
import os
import secrets
import shutil
import sys

HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(HOME, ".config", "iris")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CLAUDE_PROJECTS = os.path.join(HOME, ".claude", "projects")

# AF_UNIX paths are capped near 104 bytes on macOS, so keep this short.
# One socket per port: two bridges must never share it, or the permission
# requests of the older one arrive at a bridge that does not know the
# session and get denied.
def permission_socket(port):
    """Where the permission helper reaches the bridge. A Unix socket where
    there is one; on Windows, which has none for Python, a TCP port on
    loopback - reachable from this machine only."""
    if os.name == "nt":
        return f"tcp:127.0.0.1:{int(port) + 1}"
    return f"/tmp/iris-{int(port)}.sock"


def tcp_address(addr):
    """("127.0.0.1", 8781) for a "tcp:host:port" address, else None."""
    if not addr.startswith("tcp:"):
        return None
    host, _, port = addr[4:].rpartition(":")
    return host, int(port)

DEFAULTS = {
    "host": "",              # filled on first run: the tailscale IP
    "port": 8780,
    "token": "",             # filled on first run
    "default_permission_mode": "manual",
    "idle_timeout_seconds": 3600,
    "max_sessions": 8,
}


def _tailscale_ip():
    """Best-effort lookup of this machine's tailnet IP."""
    candidates = [
        shutil.which("tailscale"),
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
        "/usr/local/bin/tailscale",
    ]
    for exe in candidates:
        if not exe or not os.path.exists(exe):
            continue
        try:
            import subprocess
            out = subprocess.run([exe, "ip", "-4"], capture_output=True,
                                 text=True, timeout=5)
            ip = out.stdout.strip().splitlines()
            if ip:
                return ip[0].strip()
        except Exception:  # noqa: BLE001
            continue
    return ""


def load():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as fh:
                cfg.update(json.load(fh))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"iris: config unreadable ({exc}), using defaults", file=sys.stderr)

    dirty = False
    if not cfg.get("token"):
        cfg["token"] = secrets.token_urlsafe(32)
        dirty = True
    if not cfg.get("host"):
        # Bind to the tailnet address when we can find it, never 0.0.0.0.
        cfg["host"] = _tailscale_ip() or "127.0.0.1"
        dirty = True
    if not (cfg.get("nutzer") or {}).get("name"):
        # Written in on the first run, like the token: visible and editable
        # in the file rather than guessed afresh each time.
        cfg["nutzer"] = {**(cfg.get("nutzer") or {}), "name": _anzeigename()}
        dirty = True
    if dirty:
        save(cfg)
    return cfg


def save(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(cfg, fh, indent=2)
    os.chmod(tmp, 0o600)          # the token lives here
    os.replace(tmp, CONFIG_PATH)


def _anzeigename():
    """First guess at the name of whoever uses this machine.

    The first name the operating system has for the account - on a Mac that
    is the full name from the user record, elsewhere the login name. Only a
    starting point: it is written into the config on the first run so it can
    be corrected there, and a container account called "iris" is exactly the
    case where it must be.
    """
    try:
        import pwd
        voll = (pwd.getpwuid(os.getuid()).pw_gecos or "").split(",")[0].strip()
        if voll:
            return voll.split()[0]
    except (ImportError, KeyError):
        pass
    name = os.environ.get("USERNAME") or os.environ.get("USER") or "Nutzer"
    return name[:1].upper() + name[1:]


def nutzer():
    """Who iris works for, by first name.

    This is function, not decoration: the name stands in the prompts that
    tell a model whom it serves ("only X decides", "what X sees on the
    phone"). Until 28.09.2026 it was written into the code, so handing iris
    to anyone else meant their assistant believing someone else was in
    charge.
    """
    try:
        name = (load().get("nutzer") or {}).get("name")
    except Exception:                  # noqa: BLE001 - a name is not worth failing over
        name = None
    return name or _anzeigename()


def genitiv(name):
    """German genitive of a first name: Calvins, but Hans' and Max'."""
    return name + ("\u2019" if name[-1:].lower() in "s\u00dfxz" else "s")


def machine_name():
    """What this computer is called on the phone, which can know several:
    "name" in the config, or the host name without its domain."""
    import socket
    try:
        name = load().get("name")
    except Exception:                  # noqa: BLE001 - a name is not worth failing over
        name = None
    return name or socket.gethostname().split(".")[0]


def read_json(path):
    """A JSON file of ours. On Windows the bridge wrote cp1252 before it ran
    in UTF-8 mode, so an older file is read that way once more."""
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", "replace")
    return json.loads(text)
