"""Put iris' hooks into ~/.claude/settings.json - and take them out again.

These hooks fire in every Claude Code session on this Mac, which is the
point: that is how a session running in a terminal reports itself to iris.
It is also why this is careful:
  - hooks that are already there are never touched
  - every write keeps a timestamped backup first
  - the result is parsed before it replaces the original
  - installing twice changes nothing
The hook program lets everything through at once when iris is not running,
so a stopped bridge never holds up a terminal.
"""
import json
import os
import shutil
import sys
import time

from . import configs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "hooks", "iris_hook.py")
SETTINGS = os.path.expanduser("~/.claude/settings.json")

# Timeout in seconds, and whether Claude Code may run the hook without
# waiting for it. PreToolUse may wait for the phone, up to Claude Code's own
# ceiling for command hooks. MessageDisplay fires while text appears on
# screen; waiting for it would slow down the writing, so it runs detached.
EVENTS = {
    "SessionStart": (10, False),
    "UserPromptSubmit": (10, False),
    # Fires before Claude Code's own permission prompt - and, going by its
    # own `consultPermissionRequestHooksForUnpromptableAsk`, also where it
    # cannot prompt at all. That is the one place iris used to go blind: in
    # auto mode it holds nothing (NO_HOLD_MODES), so when auto mode did stop
    # and want a human, nothing reached the phone and the request surfaced
    # wherever else Calvin happened to be signed in. Reported 27.09.
    "PermissionRequest": (600, False),
    "PreToolUse": (600, False),
    "PostToolUse": (10, False),
    "PostToolUseFailure": (10, False),
    "MessageDisplay": (5, True),
    "SubagentStart": (10, False),
    "SubagentStop": (10, False),
    "Stop": (10, False),
    "SessionEnd": (5, False),
}


# The launcher sits beside the config, outside ~/Documents. Documents is
# TCC-protected: lose the terminal's permission for it and Claude Code cannot
# even open the hook, which fails before the hook's own "never get in the
# way" can apply - every prompt in every session was refused. The launcher
# runs the real hook when it can read it, and otherwise lets go quietly.
LAUNCHER = os.path.expanduser("~/.config/iris/hook.sh")

# A shell script, and /bin/sh is always there. The settings used to name one
# python by its full path; a Homebrew upgrade that retires that version would
# leave a hook that cannot start - and a hook that cannot start refuses every
# prompt of every session. This one looks for an interpreter, and if it finds
# none it ends quietly.
LAUNCHER_SOURCE = """#!/bin/sh
# Starts iris' hook, and never stands in the way. Written by
# `make install-hooks`; do not edit.
#
# It lives outside ~/Documents on purpose: macOS guards that folder, and
# without the permission the terminal cannot open the hook at all - which
# blocked every prompt in every session until the permission came back.
# Neither a missing hook nor a missing python may do that again, so every
# way out of here ends in 0.
ECHT='{pfad}'
[ -r "$ECHT" ] || exit 0
for PY in {pythons}; do
    [ -x "$PY" ] || continue
    "$PY" -S "$ECHT" "$@"
    exit 0
done
exit 0
"""


def write_launcher():
    """Puts the launcher next to the config, pointing at this checkout."""
    os.makedirs(os.path.dirname(LAUNCHER), exist_ok=True)
    # The one running now first, then the usual places. Whichever exists at
    # the time the hook fires is used.
    kandidaten = [sys.executable, "/opt/homebrew/bin/python3",
                  "/usr/local/bin/python3", "/usr/bin/python3"]
    gesehen, pythons = set(), []
    for k in kandidaten:
        if k and k not in gesehen:
            gesehen.add(k)
            pythons.append(k)
    quelle = LAUNCHER_SOURCE.format(pfad=HOOK, pythons=" ".join(pythons))
    try:
        if open(LAUNCHER).read() == quelle:
            return LAUNCHER
    except OSError:
        pass
    tmp = LAUNCHER + ".neu"
    with open(tmp, "w") as fh:
        fh.write(quelle)
    os.chmod(tmp, 0o755)
    os.replace(tmp, LAUNCHER)
    return LAUNCHER


def command():
    """The line Claude Code runs for every hook."""
    if os.name == "nt":
        # Claude Code on Windows runs hooks through Git Bash: a backslash
        # would be eaten, a path with spaces split. Forward slashes, quoted -
        # and the python on the PATH, not the Store's folder under
        # "Program Files".
        # No TCC on Windows, and no /bin/sh: the hook is named directly.
        exe = shutil.which("python") or sys.executable
        return f'"{exe.replace(os.sep, "/")}" -S "{HOOK.replace(os.sep, "/")}"'
    # /bin/sh rather than the launcher itself: an executable bit that got
    # lost would be one more way to fail.
    return f"/bin/sh {write_launcher()}"


def statusline():
    """The status line: the same program, passing on what Claude Code hands a
    status line - the plan's limits, which reach no hook."""
    return {"type": "command", "command": command() + " --statusline", "padding": 0}


def _ours(h):
    """Ours by any of its names.

    This used to match the hook in the checkout only. When the entry became
    the launcher instead, an installed entry no longer counted as ours:
    installing again did not replace it but put a second one beside it, and
    an entry left over from an older layout stayed for good. Everything under
    ~/.config/iris named hook.* counts, whatever it is written in."""
    cmd = (str(h.get("command", "")) if isinstance(h, dict) else "").replace(os.sep, "/")
    marken = (HOOK.replace(os.sep, "/"),
              os.path.dirname(LAUNCHER).replace(os.sep, "/") + "/hook.")
    return any(m in cmd for m in marken)


def _group(event):
    timeout, detached = EVENTS[event]
    hook = {"type": "command", "command": command(), "timeout": timeout}
    if detached:
        hook["async"] = True
    return {"hooks": [hook]}


def hook_settings():
    """Only the hooks section - for a project-level settings file in tests."""
    return {"hooks": {ev: [_group(ev)] for ev in EVENTS}}


def _load():
    if not os.path.exists(SETTINGS):
        return {}
    with open(SETTINGS) as fh:
        return json.load(fh)


def _strip(settings):
    """Remove our entries and nothing else; drop what becomes empty."""
    hooks = settings.get("hooks") or {}
    for ev in list(hooks):
        groups = []
        for g in hooks[ev] or []:
            inner = [h for h in (g.get("hooks") or []) if not _ours(h)]
            if inner:
                groups.append({**g, "hooks": inner})
        if groups:
            hooks[ev] = groups
        else:
            del hooks[ev]
    if hooks:
        settings["hooks"] = hooks
    else:
        settings.pop("hooks", None)
    if _ours(settings.get("statusLine")):
        settings.pop("statusLine")
    return settings


def _write(settings):
    text = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
    json.loads(text)                       # never write what will not parse
    backup = ""
    mode = 0o644
    if os.path.exists(SETTINGS):
        os.makedirs(configs.BACKUP_DIR, exist_ok=True)
        backup = os.path.join(configs.BACKUP_DIR, time.strftime(
            "%Y%m%d-%H%M%S") + "-claude-settings.json")
        shutil.copy2(SETTINGS, backup)
        mode = os.stat(SETTINGS).st_mode & 0o777
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    tmp = SETTINGS + ".iris.tmp"
    with open(tmp, "w") as fh:
        fh.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, SETTINGS)
    return backup


def installed_events():
    try:
        s = _load()
    except (OSError, ValueError):
        return set()
    have = {ev for ev, groups in (s.get("hooks") or {}).items()
            for g in groups or [] for h in g.get("hooks") or [] if _ours(h)}
    if _ours(s.get("statusLine")):
        have.add("StatusLine")
    return have


def install():
    s = _strip(_load())
    hooks = s.setdefault("hooks", {})
    for ev in EVENTS:
        hooks.setdefault(ev, []).append(_group(ev))
    # Only where no status line is set: one of the user's stays as it is.
    if not s.get("statusLine"):
        s["statusLine"] = statusline()
    return _write(s)


def uninstall():
    """Entry first, file after - never the other way round: a settings entry
    pointing at a launcher that is gone refuses every prompt of every
    session, and there is no way back from inside Claude Code."""
    backup = _write(_strip(_load()))
    try:
        os.remove(LAUNCHER)
    except OSError:
        pass
    return backup


def main(argv):
    what = argv[1] if len(argv) > 1 else "status"
    if what == "install":
        backup = install()
        print(f"Hooks eingetragen: {', '.join(EVENTS)}")
        print(f"  in {SETTINGS}")
        if backup:
            print(f"  Sicherung: {backup}")
        print("  Gilt für jede Claude-Code-Sitzung, auch bereits laufende.")
        return 0
    if what == "uninstall":
        backup = uninstall()
        print("Hooks von iris entfernt; andere Hooks bleiben.")
        if backup:
            print(f"  Sicherung: {backup}")
        return 0
    have = installed_events()
    if not have:
        print("nicht eingetragen")
    else:
        missing = set(EVENTS) - have
        print("eingetragen: " + ", ".join(sorted(have)))
        if missing:
            print("fehlt: " + ", ".join(sorted(missing)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
