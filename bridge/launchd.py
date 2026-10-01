"""Install the bridge as a macOS LaunchAgent so it survives a reboot."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _label():
    """Wie der Agent bei launchd heisst: IRIS_BUNDLE aus apple.env.

    Aus derselben Datei wie die Apps, damit es nur eine Stelle gibt. Das Label
    darf sich nach der Installation nie aendern: ein neues legt einen ZWEITEN
    Agenten an, der alte laeuft weiter, und zwei Bruecken streiten um den
    Port. Ohne apple.env - ein Rechner ohne eigene Apps - ein fester Name.
    """
    try:
        with open(os.path.join(ROOT, "apple.env"), encoding="utf-8") as fh:
            for zeile in fh:
                schluessel, _, wert = zeile.strip().partition("=")
                if schluessel == "IRIS_BUNDLE" and wert.strip():
                    return wert.strip()
    except OSError:
        pass
    return "iris.bruecke"


LABEL = _label()
PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")
LOG = os.path.expanduser("~/Library/Logs/iris.log")

TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array><string>{python}</string><string>-m</string><string>bridge</string></array>
  <key>WorkingDirectory</key><string>{root}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>{path}</string></dict>
</dict></plist>
"""


def install():
    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    with open(PLIST, "w") as fh:
        fh.write(TEMPLATE.format(
            label=LABEL, python=sys.executable, root=ROOT, log=LOG,
            path=os.environ.get("PATH", "/usr/bin:/bin")))
    subprocess.run(["launchctl", "unload", PLIST],
                   capture_output=True)          # ignore "not loaded"
    r = subprocess.run(["launchctl", "load", PLIST], capture_output=True, text=True)
    if r.returncode:
        print("launchctl load fehlgeschlagen:", r.stderr.strip())
        return 1
    print(f"iris läuft jetzt als LaunchAgent ({LABEL}).")
    print(f"Logs: {LOG}")
    return 0


def uninstall():
    subprocess.run(["launchctl", "unload", PLIST], capture_output=True)
    if os.path.exists(PLIST):
        os.unlink(PLIST)
    print("LaunchAgent entfernt.")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "install"
    sys.exit(install() if cmd == "install" else uninstall())
