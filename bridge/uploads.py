"""Files sent from the phone: photos, screenshots, documents.

They land outside every project - in ~/.config/iris/uploads/<session>/ - so
nothing turns up in a git status. A message names them by path; a session
the bridge hosts gets images inline as well, a terminal session reads them
itself with the Read tool.
"""
import os
import re
import time

from . import config

ROOT = os.path.join(config.CONFIG_DIR, "uploads")
MAX_BYTES = 25 * 1024 * 1024
# What Claude takes as an image. Anything else is attached by path only.
IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")


def _safe(name):
    name = os.path.basename(name or "").strip() or "anhang"
    name = re.sub(r"[^\w.\- äöüÄÖÜß()]", "_", name)
    return name[:80]


def save(session_key, name, data, media_type):
    """Store one upload. Returns its description, or an error."""
    if not data:
        return {"error": "leere Datei"}
    if len(data) > MAX_BYTES:
        return {"error": f"größer als {MAX_BYTES // (1024 * 1024)} MB"}
    folder = os.path.join(ROOT, re.sub(r"[^\w\-]", "_", session_key))
    os.makedirs(folder, mode=0o700, exist_ok=True)
    path = os.path.join(folder, time.strftime("%Y%m%d-%H%M%S-") + _safe(name))
    with open(path, "wb") as fh:
        fh.write(data)
    os.chmod(path, 0o600)
    return {"path": path, "name": _safe(name), "size": len(data),
            "media_type": media_type or "application/octet-stream"}


def resolve(paths):
    """Only files from the upload folder are attached - a client cannot make
    a message point Claude at anything else on the Mac."""
    out = []
    root = os.path.realpath(ROOT)
    for p in paths or []:
        real = os.path.realpath(str(p))
        if real.startswith(root + os.sep) and os.path.isfile(real):
            out.append(real)
    return out


def media_type(path):
    ext = os.path.splitext(path)[1].lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp"}.get(ext, "application/octet-stream")


def describe(path):
    return {"name": os.path.basename(path).split("-", 2)[-1], "path": path,
            "media_type": media_type(path)}


def mention(paths):
    """The lines a message carries for its attachments."""
    return "\n".join(f"Anhang: {p}" for p in paths)
