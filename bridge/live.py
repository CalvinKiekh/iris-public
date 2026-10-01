"""Spot Claude Code sessions that are open in a terminal right now.

Why this is a guess and not a lookup: a session's id lives in the process
environment, and macOS hands out only a trimmed environment for other
people's processes - CLAUDE_CODE_SESSION_ID is not in it. The transcript is
not held open either (Claude Code appends and closes), so lsof finds nothing
to match against.

What is readable: the working directory of every running `claude`, and how
recently each transcript was written. Together that answers the question
that actually matters - "am I about to open a conversation twice?" - well
enough to warn about, as long as it is presented as a suspicion.
"""
import os
import subprocess
import time

# A conversation whose transcript was touched this recently is treated as
# still being driven by whoever has it open.
FRESH_SECONDS = 180


def terminal_cwds():
    """Working directories of interactive claude processes.

    Excludes our own children: those run with `-p` and a stream-json pipe,
    interactive ones do not.
    """
    try:
        out = subprocess.run(["ps", "-Ao", "pid=,command="],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return {}

    pids = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        pid, _, cmd = line.partition(" ")
        cmd = cmd.strip()
        base = os.path.basename(cmd.split()[0]) if cmd else ""
        if base != "claude":
            continue
        if "-p" in cmd.split() or "--input-format" in cmd:
            continue                     # a bridge-driven session, not a terminal
        if pid.isdigit():
            pids.append(pid)

    cwds = {}
    for pid in pids:
        try:
            r = subprocess.run(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"],
                               capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            continue
        for line in r.stdout.splitlines():
            if line.startswith("n"):
                cwds.setdefault(line[1:], []).append(pid)
                break
    return cwds


def annotate(sessions, project_path, cwds=None):
    """Mark conversations that are probably open elsewhere.

    Only the most recently written transcript of a directory that has a live
    terminal process is flagged - flagging every conversation in a busy
    project would make the warning worthless.
    """
    if cwds is None:
        cwds = terminal_cwds()
    live_here = cwds.get(project_path, [])
    now = time.time()
    flagged = False
    for s in sessions:
        fresh = (now - s.get("modified", 0)) < FRESH_SECONDS
        s["likely_open"] = bool(live_here) and fresh and not flagged
        if s["likely_open"]:
            flagged = True
    return sessions
