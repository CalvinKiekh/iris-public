"""A message to the phones iris knows, as a push - "the new version is on,
open the app once". Installing works with the phone locked; only starting
the app needs it unlocked, so this is how the phone learns it is time.

    python3 tools/notify.py "Neue Version ist drauf" ["App einmal neu öffnen"]
    python3 tools/notify.py --dry ...     # only list the phones
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bridge import config, push  # noqa: E402


def main(argv):
    dry = "--dry" in argv
    words = [a for a in argv if a != "--dry"]
    if not words:
        print(__doc__.strip())
        return 2
    push.configure(config.load(), away=lambda: True)
    phones = [d.get("name") or d["token"][:8] for d in push.devices()]
    if dry or not push.configured():
        print("Telefone:", ", ".join(phones) or "keine",
              "" if push.configured() else "(Push nicht eingerichtet)")
        return 0 if push.configured() else 1
    alert = {"title": "iris", "body": words[0]}
    if len(words) > 1:
        alert = {"title": "iris", "subtitle": words[0], "body": words[1]}
    for r in push.deliver({"aps": {"alert": alert, "sound": "default"},
                           "iris": {"kind": "notice"}}):
        print(f"{r['device']}: {r['status']} {r['reason'] or ''}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
