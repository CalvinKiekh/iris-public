"""Names given to sessions from the phone or the Mac - kept by the bridge, so
every device shows the same, and winning over any title Claude Code or iris
made up. Keyed by Claude's session id where there is one: a session that is
resumed or picked up again keeps its name.
"""
import json
import os
import threading

from . import config

# Beside the terminal state, so a test bridge with its own state keeps its
# own names too.
PATH = os.path.join(os.path.dirname(os.environ.get("IRIS_TERMINALS_PATH")
                                    or os.path.join(config.CONFIG_DIR, "terminals.json")),
                    "names.json")
_lock = threading.Lock()


def _load():
    try:
        with open(PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def key_of(session):
    return getattr(session, "claude_session_id", None) or session.key


def get(session):
    return _load().get(key_of(session), "")


def put(session, name):
    """Sets the name; an empty one gives the automatic title back."""
    name = " ".join((name or "").split())[:80]
    with _lock:
        data = _load()
        if name:
            data[key_of(session)] = name
        else:
            data.pop(key_of(session), None)
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, PATH)
    return name
