"""iris bridge - remote control for local Claude Code sessions."""
import argparse
import os
import signal
import sys
import threading
import time

from . import config, manager, server

if sys.platform == "win32":
    # The bridge runs as pythonw, without a console. Every console program it
    # starts - git, the claude of a session started from the phone, and the
    # hooks that one runs - would get a window of its own and flash up.
    # Started without a window they share an invisible console instead.
    import subprocess
    _popen_init = subprocess.Popen.__init__

    def _no_window(self, *args, **kwargs):
        if not kwargs.get("creationflags"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        _popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _no_window


def _selbsttest(servers, cfg):
    """DIE OBERFLAECHE MUSS DA SEIN, und wenn nicht, gehoert das gesagt.

    Auf dem PC fehlte `web/` vollstaendig - die Bruecke beantwortete `/` mit
    404, und die App lud auf iPhone und Mac gar nicht erst. Die API war dabei
    die ganze Zeit gesund, jeder /api/-Aufruf gab 200, also sah alles nach
    einem Fehler in der App aus. Gefunden hat es die PC-Seite erst nach
    Stunden, im Quervergleich der beiden Bruecken.

    Darum ruft die Bruecke hier ihr eigenes `/` auf. Nicht nachsehen, ob die
    Dateien daliegen - das beweist nur, dass etwas da ist, nicht dass es
    ausgeliefert wird. Ein Ausfall, den nur Calvin bemerkt, ist einer zu viel.
    """
    import urllib.error
    import urllib.request
    # Ueber Loopback, damit der Test nicht am Netz haengt.
    ziel = f"http://127.0.0.1:{servers[0].server_address[1]}/"
    for versuch in range(10):                  # der Server nimmt gerade erst an
        try:
            with urllib.request.urlopen(ziel, timeout=5) as f:
                code, groesse = f.status, len(f.read())
            break
        except urllib.error.HTTPError as exc:
            code, groesse = exc.code, 0
            break
        except OSError:
            time.sleep(0.5)
    else:
        print("  ACHTUNG: die Bruecke erreicht ihre eigene Oberflaeche nicht.",
              flush=True)
        return
    if code == 200 and groesse:
        print(f"  Oberflaeche /      -> 200, {groesse} Bytes", flush=True)
        return
    fehlt = [n for n, d in (("web", server.WEB_DIR), ("sim", server.SIM_DIR))
             if not os.path.isfile(os.path.join(d, "index.html"))]
    print(f"  ACHTUNG: / antwortet mit {code} - die App laedt so weder auf "
          f"dem iPhone noch auf dem Mac.", flush=True)
    if fehlt:
        print(f"  Es fehlt: {', '.join(n + '/index.html' for n in fehlt)} unter "
              f"{server.ROOT}. Beim Ausrollen mitkopieren "
              f"(tools/pc-ausrollen.sh nimmt bridge, web, sim, hooks und "
              f"run_bridge.py).", flush=True)


def main():
    ap = argparse.ArgumentParser(prog="iris", description=__doc__)
    ap.add_argument("--host", help="bind address (default: tailnet IP from config)")
    ap.add_argument("--port", type=int, help="bind port")
    ap.add_argument("--print-token", action="store_true",
                    help="print the access token and the connect URL, then exit")
    ap.add_argument("--new-token", action="store_true",
                    help="rotate the access token and exit")
    args = ap.parse_args()

    cfg = config.load()
    if args.host:
        cfg["host"] = args.host
    if args.port:
        cfg["port"] = args.port

    if args.new_token:
        import secrets
        cfg["token"] = secrets.token_urlsafe(32)
        config.save(cfg)
        print("Neues Token gesetzt.")
        args.print_token = True

    url = f"http://{cfg['host']}:{cfg['port']}/?token={cfg['token']}"
    if args.print_token:
        print(f"Token: {cfg['token']}")
        print(f"URL:   {url}")
        return 0

    try:
        mgr = manager.Manager(cfg)
    except RuntimeError as exc:
        print(f"iris: {exc}", file=sys.stderr)
        print("  Läuft schon eine Bridge?  make status", file=sys.stderr)
        return 2
    try:
        servers = server.serve(mgr, cfg)
    except server.PortInUse as exc:
        mgr.shutdown()
        print(f"iris: Port {exc.port} ist schon belegt.", file=sys.stderr)
        print(f"  Wer dort lauscht:  lsof -nP -iTCP:{exc.port} -sTCP:LISTEN",
              file=sys.stderr)
        print(f"  Anderer Port:      python3 -m bridge --port {exc.port + 1}",
              file=sys.stderr)
        return 2

    def shutdown(*_):
        # httpd.shutdown() waits for serve_forever to return, so calling it
        # from the signal handler - which runs *in* that thread - deadlocks.
        # Hand it to a separate thread instead.
        print("\niris: fahre herunter …")
        threading.Thread(target=_teardown, daemon=True).start()

    def _teardown():
        mgr.shutdown()
        for s in servers:
            s.shutdown()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()

    for s in servers:
        h, p_ = s.server_address[0], s.server_address[1]
        print(f"iris bridge lauscht auf http://{h}:{p_}")
    print(f"  Öffnen mit: {url}")
    threading.Thread(target=_selbsttest, args=(servers, cfg), daemon=True).start()
    if cfg["host"] in ("127.0.0.1", "localhost"):
        # Zwei verschiedene Lagen, die bisher denselben Satz bekamen. Auf dem
        # Pi ist 127.0.0.1 ausdruecklich verlangt (`--host`), und erreichbar
        # ist die Bruecke trotzdem: der Tailscale-Dienst des Rechners reicht
        # sie durch, im Container ist davon nichts zu sehen. Wer dann liest,
        # sie sei "nur lokal erreichbar", sucht den Fehler dort, wo keiner
        # ist. Also sagen, was gilt, und raten nur, wo wirklich geraten wird.
        if args.host:
            print("  Hinweis: an 127.0.0.1 gebunden, wie verlangt — von außen "
                  "nur, wenn etwas sie durchreicht (auf dem Pi: Tailscale).")
        else:
            print("  Hinweis: keine Tailscale-IP gefunden — erreichbar nur lokal.")
    try:
        servers[0].serve_forever()
    finally:
        mgr.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
