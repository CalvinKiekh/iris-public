"""Register the inventory MCP server with Claude Code.

Writes into ~/.claude/settings.json under mcpServers, keeping a backup
first - a broken settings file stops Claude Code from starting.
"""
import json
import os
import shutil
import sys
import time

SETTINGS = os.path.expanduser("~/.claude/settings.json")
SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "mcp_inventory_server.py")
NAME = "iris-inventory"


def install():
    entry = {"command": sys.executable, "args": [SERVER]}
    data = {}
    if os.path.exists(SETTINGS):
        try:
            with open(SETTINGS) as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"settings.json nicht lesbar: {exc}", file=sys.stderr)
            return 1
        backup = f"{SETTINGS}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
        shutil.copy2(SETTINGS, backup)
        print(f"Sicherung: {backup}")

    servers = data.setdefault("mcpServers", {})
    if servers.get(NAME) == entry:
        print(f"{NAME} ist bereits eingetragen.")
        return 0
    servers[NAME] = entry

    tmp = SETTINGS + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, SETTINGS)
    print(f"{NAME} eingetragen. Claude Code neu starten, dann stehen die "
          f"Werkzeuge bereit.")
    return 0


def uninstall():
    if not os.path.exists(SETTINGS):
        return 0
    with open(SETTINGS) as fh:
        data = json.load(fh)
    if data.get("mcpServers", {}).pop(NAME, None) is None:
        print("war nicht eingetragen")
        return 0
    if not data["mcpServers"]:
        data.pop("mcpServers")
    with open(SETTINGS, "w") as fh:
        json.dump(data, fh, indent=2)
    print(f"{NAME} entfernt.")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "install"
    sys.exit(install() if cmd == "install" else uninstall())
