#!/usr/bin/env python3 -S
"""The one program Claude Code runs for iris, on every hook of every session.

Because it runs in *every* session on this Mac, it has one rule above all:
it must never get in the way. So:
  - in sessions the bridge hosts itself it does nothing at all - the bridge
    already sees everything there through the stream
  - if iris is not running, loopback refuses at once and it lets go
  - any error at all ends in exit 0 with no output, which Claude Code reads
    as "carry on"
Only PreToolUse and PermissionRequest may wait, and only because the bridge
chose to hold them for an answer from the phone.

It starts twice per tool call, so start-up time is the whole cost. Hence a
bare socket instead of urllib: urllib.request alone takes ~90 ms to import,
and on macOS it asks the system for proxy settings on every request. With
`python -S` and a socket the hook stays around 45 ms.
"""
import json
import os
import socket
import sys

CONFIG = os.path.expanduser("~/.config/iris/config.json")

# Just under Claude Code's own 600 s ceiling for command hooks.
LONG_WAIT = 590
SHORT_WAIT = 3

# The two events the bridge may park while the phone decides.
HOLDS = ("PreToolUse", "PermissionRequest")


def main():
    if os.environ.get("IRIS_SESSION_KEY"):
        return                          # a session the bridge hosts itself
    # Bytes, decoded as UTF-8: on Windows sys.stdin would read Claude Code's
    # UTF-8 as cp1252 and garble every umlaut in the payload.
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    statusline = "--statusline" in sys.argv
    if statusline:
        # Run as Claude Code's status line: its input carries the plan's
        # limits (rate_limits) and the context in use. Passed on; nothing is
        # printed, so no status line appears.
        payload["hook_event_name"] = "StatusLine"
    with open(CONFIG) as fh:
        cfg = json.load(fh)
    token = cfg.get("token")
    if not token:
        return
    port = int(os.environ.get("IRIS_HOOK_PORT") or cfg.get("port", 8780))
    event = payload.get("hook_event_name", "")
    # Where this runs, so the bridge can find the session's terminal tab.
    payload["iris_ppid"] = os.getppid()

    body = json.dumps(payload).encode()
    head = ("POST /api/hooks HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            f"Authorization: Bearer {token}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n").encode()

    conn = socket.create_connection(("127.0.0.1", port), timeout=1)
    conn.settimeout(LONG_WAIT if event in HOLDS else SHORT_WAIT)
    try:
        conn.sendall(head + body)
        chunks = []
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        conn.close()

    status, _, rest = b"".join(chunks).partition(b"\r\n")
    if b" 200 " not in status + b" ":
        return
    answer = json.loads(rest.partition(b"\r\n\r\n")[2] or b"{}")
    out = answer.get("output")
    if out and not statusline:
        sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    try:
        main()
    except Exception:                   # noqa: BLE001 - never hold anything up
        pass
    sys.exit(0)
