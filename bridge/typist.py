"""Typing a message into the terminal a Claude Code session runs in -
a Terminal.app tab on the Mac, a tmux pane anywhere (the Pi, a server).

A session that finished its turn sits at its prompt, and no hook fires there
until someone types. So iris types: the message goes into the tab as a paste
followed by Return, exactly as if it had been typed at the Mac. It stands in
the terminal as a normal prompt, Claude answers it, every hook runs as usual,
and the terminal and the phone show the same conversation.

Only into Terminal.app, only into the tab whose tty belongs to the session's
own claude process, and only while that process holds the foreground of its
terminal. A paste that reached a bare shell instead would run as a command,
and one that reached another program's input would be read by it - so every
condition is checked again right before each keystroke.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys

# Claude Code keeps one small file per running interactive process here:
# pid, session id, and whether it is busy or idle. The messaging socket it
# names is left alone - that one belongs to remote control.
SESSIONS_DIR = os.path.expanduser("~/.claude/sessions")

# Bracketed paste: the text arrives as one block, so a line break inside the
# message does not send it early. The Return comes from `do script` itself.
# The tab is looked up and checked in the same script that types, so there
# is no gap in which claude could have quit.
SCRIPT = r'''
on run argv
  set wanted to item 1 of argv
  set msg to item 2 of argv
  set how to item 3 of argv
  if application "Terminal" is not running then return "Terminal.app läuft nicht"
  tell application "Terminal"
    repeat with w in windows
      repeat with t in tabs of w
        if tty of t is wanted then
          if processes of t does not contain "claude" then return "Claude läuft in dem Tab nicht mehr"
          if how is "paste" then
            set e to ASCII character 27
            do script (e & "[200~" & msg & e & "[201~") in t
          else
            do script msg in t
          end if
          return "ok"
        end if
      end repeat
    end repeat
  end tell
  return "kein Tab in Terminal.app"
end run
'''

# Control characters would reach the terminal as keystrokes - an escape
# sequence could end the paste early and press keys of its own.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _ps(fields, *args, split=None):
    try:
        out = subprocess.run(["ps", "-o", fields, *args], capture_output=True,
                             text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    n = split if split is not None else fields.count(",")
    return [line.split(None, n) for line in out.splitlines() if line.strip()]


def _foreground(pgid, tpgid, tty):
    # macOS names terminals ttys003, Linux pts/3; "?" or "??" means none.
    return tty.strip("?") != "" and pgid == tpgid


def find_claude(pid):
    """The interactive claude process a hook ran under, walking up from the
    hook's parent: (pid, "/dev/ttysNNN"), or None.

    None as well for a claude without a terminal of its own (`claude -p`,
    an editor) and for one that is not in the foreground of its terminal -
    that is a run started from inside another session, and its tab belongs
    to someone else.
    """
    if os.name == "nt":
        return None                        # found through by_session instead
    rows = {}
    for r in _ps("pid=,ppid=,pgid=,tpgid=,tty=,comm=", "-A"):
        if len(r) == 6 and r[0].isdigit():
            rows[int(r[0])] = r
    for _ in range(12):
        r = rows.get(pid)
        if not r:
            return None
        if os.path.basename(r[5]) == "claude":
            return (pid, "/dev/" + r[4]) if _foreground(r[2], r[3], r[4]) else None
        pid = int(r[1])
    return None


def running():
    """session id -> what Claude Code says about its running process."""
    out = {}
    for path in glob.glob(os.path.join(SESSIONS_DIR, "*.json")):
        try:
            with open(path) as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        # Only what runs in a terminal. A session a bridge starts itself
        # (claude -p, stream-json) is recorded as "interactive" too - its
        # entrypoint "sdk-cli" is what tells it apart.
        if d.get("sessionId") and d.get("kind", "interactive") == "interactive" \
                and d.get("entrypoint", "cli") == "cli":
            out[d["sessionId"]] = d
    return out


def by_session(sid):
    """(pid, tty) of the live interactive claude holding this session, from
    Claude Code's own record - for sessions that have not sent a hook since
    the bridge started, which is every session that sits idle."""
    d = running().get(sid)
    if not d or not isinstance(d.get("pid"), int):
        return None
    if os.name == "nt":
        # On Windows the console the claude process runs in is the tab.
        return (d["pid"], f"con:{d['pid']}") if is_claude(d["pid"]) else None
    r = _ps("pgid=,tpgid=,tty=,comm=", "-p", str(d["pid"]))
    if not r or len(r[0]) != 4 or os.path.basename(r[0][3]) != "claude":
        return None
    return (d["pid"], "/dev/" + r[0][2]) if _foreground(*r[0][:3]) else None


def status(sid):
    """"idle" or "busy" as Claude Code itself records it, or None."""
    d = running().get(sid)
    return d.get("status") if d else None


def _windows_image(pid):
    """The image name of a running process on Windows ("claude.exe"), or None.
    Asked of the process itself - not tasklist, a program started for every
    look, and not os.kill, which on Windows ends the process."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                               wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    try:
        h = k32.OpenProcess(0x1000, False, int(pid))   # PROCESS_QUERY_LIMITED_INFORMATION
    except (ValueError, OverflowError):
        return None
    if not h:
        return None
    try:
        buf, n = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
        if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return None
        return os.path.basename(buf.value).lower()
    finally:
        k32.CloseHandle(h)


def is_claude(pid):
    if os.name == "nt":
        # No ps on Windows. Claude Code installed with npm runs as node.exe;
        # the pid comes from Claude Code's own record, so node is enough.
        return _windows_image(pid) in ("claude.exe", "node.exe")
    r = _ps("comm=", "-p", str(pid), split=0)
    return bool(r) and os.path.basename(r[0][0]) == "claude"


def alive(pid, tty):
    """Is this still the claude of that tab, in its foreground?"""
    if os.name == "nt":
        return tty == f"con:{pid}" and is_claude(pid)
    r = _ps("pgid=,tpgid=,tty=,comm=", "-p", str(pid))
    return (bool(r) and len(r[0]) == 4 and "/dev/" + r[0][2] == tty
            and os.path.basename(r[0][3]) == "claude"
            and _foreground(r[0][0], r[0][1], r[0][2]))


def clean(text):
    return _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def _tmux_pane(tty):
    """The tmux pane whose terminal is `tty`, if claude runs inside tmux."""
    if not tty:
        return None
    if not shutil.which("tmux"):
        return None
    try:
        out = subprocess.run(["tmux", "list-panes", "-a", "-F", "#{pane_tty} #{pane_id}"],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        t, _, pane = line.partition(" ")
        if t == tty:
            return pane
    return None


def _tmux(pane, text, how):
    """Same as the Terminal.app way, through tmux: a bracketed paste (-p),
    then Enter - or the raw key."""
    try:
        if how == "paste":
            subprocess.run(["tmux", "load-buffer", "-b", "iris", "-"], input=text,
                           text=True, check=True, timeout=5)
            subprocess.run(["tmux", "paste-buffer", "-p", "-d", "-b", "iris", "-t", pane],
                           check=True, timeout=5)
            subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"], check=True, timeout=5)
        else:
            subprocess.run(["tmux", "send-keys", "-t", pane, "C-c" if text == "\x03" else text],
                           check=True, timeout=5)
    except (OSError, subprocess.SubprocessError) as e:
        return f"tmux: {e}"
    return "ok"


_HISTORY = r'''
on run argv
  set wanted to item 1 of argv
  if application "Terminal" is not running then return "iris:kein-tab"
  tell application "Terminal"
    repeat with w in windows
      repeat with t in tabs of w
        if tty of t is wanted then return history of t
      end repeat
    end repeat
  end tell
  return "iris:kein-tab"
end run
'''


def screen_history(tty):
    """Everything the terminal of `tty` shows and still keeps in its
    scrollback, as plain text - or None when it is not a Terminal.app tab or
    a tmux pane. Terminal.app hands out ~500 KB in a fifth of a second."""
    # Ohne TTY gibt es nichts zu lesen - und `osascript` mit None in der
    # Befehlsliste wirft einen TypeError, der den ganzen Faden mitnimmt.
    # Danach liest niemand mehr den Bildschirm dieser Sitzung, und in der App
    # sieht sie aus, als sei sie stehengeblieben. Ein fehlender TTY ist aber
    # keine Ausnahme, sondern ein Zustand: eine Sitzung, deren Fenster zu ist.
    if not tty:
        return None
    pane = _tmux_pane(tty)
    try:
        if pane:
            r = subprocess.run(["tmux", "capture-pane", "-p", "-J", "-S", "-", "-t", pane],
                               capture_output=True, text=True, timeout=10)
        elif sys.platform == "darwin":
            r = subprocess.run(["osascript", "-", tty], input=_HISTORY,
                               capture_output=True, text=True, timeout=10)
        else:
            return None
    except (OSError, subprocess.SubprocessError):
        return None
    out = r.stdout
    if r.returncode != 0 or out.startswith("iris:kein-tab"):
        return None
    return out


# By index, not with "repeat with t in tabs": on such a loop variable
# "contents of t" is AppleScript's own operator and hands back the reference
# ("tab 1 of window id …"), not the text on screen.
_CONTENTS = r'''
on run argv
  set wanted to item 1 of argv
  if application "Terminal" is not running then return "iris:kein-tab"
  tell application "Terminal"
    repeat with w in windows
      repeat with i from 1 to count of tabs of w
        if tty of tab i of w is wanted then return contents of tab i of w
      end repeat
    end repeat
  end tell
  return "iris:kein-tab"
end run
'''

# What the status line says -> the permission mode it means.
_MODES = (("accept edits on", "acceptEdits"), ("plan mode on", "plan"),
          ("auto mode on", "auto"), ("manual mode on", "default"),
          ("bypass permissions on", "bypassPermissions"),
          ("don't ask on", "dontAsk"))


def _console(tty):
    """The pid whose Windows console is the "tab" `tty`, or None."""
    if not tty:
        return None
    if os.name == "nt" and tty and tty.startswith("con:") and tty[4:].isdigit():
        return int(tty[4:])
    return None


def _wincon(op, pid, steps=None):
    """One call of bridge.wincon in a process of its own (see there)."""
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", "-m", "bridge.wincon", op, str(pid)],
                           input=json.dumps(steps or []), capture_output=True,
                           encoding="utf-8", errors="replace", timeout=20,
                           cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return json.loads(r.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        return {"error": str(e)}


def _console_steps(text, how):
    """What the Terminal.app way sends, as console keys. There every call
    brings a Return along, and the special sequences work around it; a
    console takes the key itself - Esc is Esc."""
    special = {"\x1b[27u": [{"key": "esc"}], "\x1b[Z": [{"key": "tab", "shift": True}],
               "\x03": [{"key": "ctrl-c"}], "\x02": [{"key": "ctrl-b"}],
               "": [{"key": "enter"}]}
    if text in special:
        return special[text]
    # Lines as one bracketed paste: a Return between them would send early.
    body = f"\x1b[200~{text}\x1b[201~" if "\n" in text else text
    return [{"text": body}, {"wait": 0.15}, {"key": "enter"}]


def screen_now(tty):
    """What the terminal of `tty` shows right now - the visible part only."""
    if not tty:
        return None
    pid = _console(tty)
    if pid:
        r = _wincon("read", pid)
        return None if r.get("error") else "\n".join(r.get("lines") or [])
    pane = _tmux_pane(tty)
    try:
        if pane:
            r = subprocess.run(["tmux", "capture-pane", "-p", "-t", pane],
                               capture_output=True, text=True, timeout=5)
        elif sys.platform == "darwin":
            r = subprocess.run(["osascript", "-", tty], input=_CONTENTS,
                               capture_output=True, text=True, timeout=5)
        else:
            return None
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or r.stdout.startswith("iris:kein-tab"):
        return None
    return r.stdout


def mode_on_screen(text):
    """The permission mode the status line shows, or None."""
    for line in reversed((text or "").splitlines()):
        for words, mode in _MODES:
            if words in line:
                return mode
    return None


def input_empty(text):
    """Is the input line at the Mac empty? Text there - a draft, a
    suggestion - would be sent by the Return every keystroke brings along."""
    for line in reversed((text or "").splitlines()):
        if line.startswith("❯"):
            return line.strip() == "❯"
    return False


def shift_tab(tty):
    """One step through the permission modes, as Shift+Tab at the Mac."""
    if not tty:
        return None
    return _run(tty, "\x1b[Z", "raw")


def _run(tty, text, how):
    if not tty:
        return None
    pid = _console(tty)
    if pid:
        r = _wincon("keys", pid, _console_steps(text, how))
        return "ok" if r.get("ok") else "Konsole: " + str(r.get("error") or "keine Antwort")
    pane = _tmux_pane(tty)
    if pane:
        return _tmux(pane, text, how)
    if sys.platform != "darwin":
        return "kein tmux-Fenster und kein Terminal.app"
    try:
        r = subprocess.run(["osascript", "-", tty, text, how], input=SCRIPT,
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as e:
        return f"osascript: {e}"
    return r.stdout.strip() or r.stderr.strip() or "keine Antwort von Terminal.app"


def type_into(tty, text):
    """Type `text` into the tab on `tty` and press Return. "ok", or why not."""
    if not tty:
        return None
    return _run(tty, clean(text), "paste")


# The one place where iris types into a tab that has NO claude in it.
#
# Everywhere else the opposite is checked before each keystroke, and for a
# good reason: a paste that reaches a bare shell runs as a command. The
# exception exists for one move only - ending a session to update Claude
# Code and picking it up again in the same tab - and it is narrow on both
# sides. The command is composed here, never passed in; the session id is
# checked against the shape of a UUID; and the tab must be the one this
# session was in and must be sitting at a shell.
SCRIPT_SHELL = r'''
on run argv
  set wanted to item 1 of argv
  set cmd to item 2 of argv
  if application "Terminal" is not running then return "Terminal.app läuft nicht"
  tell application "Terminal"
    repeat with w in windows
      repeat with t in tabs of w
        if tty of t is wanted then
          if processes of t contains "claude" then return "In dem Tab läuft noch Claude"
          do script cmd in t
          return "ok"
        end if
      end repeat
    end repeat
  end tell
  return "kein Tab in Terminal.app"
end run
'''

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
                   r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def resume_in_tab(tty, session_id, binary="claude"):
    """`claude --resume <id>` in the tab on `tty`, which sits at a shell.

    The only command iris ever runs in a shell, and it is built here out of
    a checked id - nothing a caller passes can turn into something else.
    """
    if not tty:
        return None
    if not _UUID.match(session_id or ""):
        return "keine gültige Sitzungskennung"
    cmd = f"{binary} --resume {session_id}"
    pid = _console(tty)
    if pid:
        return "ok" if _wincon("keys", pid, [{"text": cmd}, {"wait": 0.15},
                                             {"key": "enter"}]).get("ok") \
            else "Konsole antwortet nicht"
    pane = _tmux_pane(tty)
    if pane:
        return _tmux(pane, cmd, "type")
    if sys.platform != "darwin":
        return "kein tmux-Fenster und kein Terminal.app"
    try:
        r = subprocess.run(["osascript", "-", tty, cmd], input=SCRIPT_SHELL,
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as e:
        return f"osascript: {e}"
    return r.stdout.strip() or r.stderr.strip() or "keine Antwort von Terminal.app"


def claude_gone(tty):
    """Does the tab on `tty` sit at a shell now - no claude in it?

    Asked before typing the resume, so a session that refused to quit is not
    typed over.
    """
    if sys.platform != "darwin" or _console(tty) or _tmux_pane(tty):
        # Elsewhere the process list of the pane answers this, not Terminal.
        return not any(os.path.basename(r[-1]) == "claude"
                       for r in _ps("tty=,comm=", "-A")
                       if len(r) == 2 and "/dev/" + r[0].strip() == tty)
    script = r'''
on run argv
  tell application "Terminal"
    repeat with w in windows
      repeat with t in tabs of w
        if tty of t is (item 1 of argv) then
          if processes of t contains "claude" then return "nein"
          return "ja"
        end if
      end repeat
    end repeat
  end tell
  return "kein Tab"
end run
'''
    try:
        r = subprocess.run(["osascript", "-", tty], input=script,
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.stdout.strip() == "ja"


def escape(tty):
    """Esc in the tab - what closes a view Claude Code opened (/status,
    /config, a list). Sent in the kitty keyboard protocol's form (CSI 27 u):
    a plain Esc followed by the Return `do script` adds reads as Alt+Return,
    but this one Claude Code takes as Esc, and the Return then meets an
    empty input and does nothing."""
    return _run(tty, "\x1b[27u", "raw")


def enter(tty):
    """Return alone - confirms what a view has selected."""
    return _run(tty, "", "raw")


def background(tty):
    """Ctrl+B in the tab - what sends a running command to the background at
    the Mac. Same road as Ctrl+C: the raw control character, no Return."""
    return _run(tty, "\x02", "raw")


def interrupt(tty):
    """Ctrl+C in the tab - what stops a running turn at the Mac.

    Esc would be the usual key, but `do script` always adds a Return, and Esc
    followed by Return reads as Alt+Return: the turn runs on. Ctrl+C at an
    idle prompt arms "press again to quit", so the caller sends it only to a
    turn that is running, and never twice in a row."""
    return _run(tty, "\x03", "raw")
