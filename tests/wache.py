"""Die Wache: sucht von aussen nach den Stoerungen, die uns in der Nacht zum
11./12.09. jeweils Stunden gekostet haben - und meldet sie, statt darauf zu
warten, dass jemand zufaellig hinsieht.

    python3 tests/wache.py            # einmal pruefen, Rueckgabe 1 bei Befund
    python3 tests/wache.py --dauer 8  # acht Stunden lang alle 5 Minuten

Geprueft wird je Bruecke (Mac und PC):
  - Bruecke erreichbar, und kann sie ueberhaupt pushen (Schluessel, Geraete)
  - Bewohner wach, Ollama da, Tempo, verwaiste Runner, ausgelagerter
    Grafikspeicher, eigener Takt (Rueckkopplung)
  - Fragen, die zu lange warten; Antraege, die zu lange offen sind
  - gehostete Sitzungen, die sehr lange arbeiten (haengende Freigabe)
  - Fehler im Journal der letzten Minuten
  - Kontingent ueber Calvins Grenze
"""
import argparse, json, os, socket, sys, time, urllib.error, urllib.request

GRENZEN = {"tempo_tok_s": 80, "ticks_je_minute": 20, "geteilt_mib": 2000,
           "frage_wartet_s": 120, "antrag_offen_s": 1800, "sitzung_busy_s": 1200,
           "fehler_je_10min": 3, "abo": 0.80, "eingang_liegt_s": 300}

# Wo der letzte Abo-Stand steht. Nur dadurch kann die Wache auch melden, dass
# das Fenster wieder frei ist - ein Timer muesste raten, wann es zurueckgeht,
# die Wache misst es. Mac und PC teilen ein Abo, aber jede Bruecke meldet
# ihren eigenen Stand; deshalb je Name eine Zeile.
ABO_STAND = os.path.expanduser("~/.config/iris/wache-abo.json")


def abo_merken(name, anteil):
    """Der vorige Anteil dieser Bruecke, und der neue wird festgehalten."""
    try:
        with open(ABO_STAND, encoding="utf-8") as f:
            alle = json.load(f)
    except (OSError, ValueError):
        alle = {}
    vorher = alle.get(name)
    alle[name] = anteil
    try:
        os.makedirs(os.path.dirname(ABO_STAND), exist_ok=True)
        with open(ABO_STAND, "w", encoding="utf-8") as f:
            json.dump(alle, f)
    except OSError:
        pass
    return vorher if isinstance(vorher, (int, float)) else None


def hole(basis, token, pfad, sekunden=15):
    """Einmal fragen - und bei einer KALTEN Leitung noch einmal.

    Tailscale laesst einen ungenutzten Pfad verfallen. Der erste Versuch nach
    einer halben Stunde Ruhe trifft auf einen Handschlag, der noch laeuft, und
    faellt durch; der zweite kommt in Millisekunden an. Genau das hat diese
    Wache am 13.09. um 18:41 und 19:09 als "Bruecke nicht erreichbar"
    gemeldet, waehrend curl im selben Moment in 14 ms eine 200 bekam.

    Ein Fehlalarm ist nicht harmlos: Eine Wache, die ohne Grund Alarm schlaegt,
    wird nicht mehr gelesen - und dann faellt der echte Ausfall auch nicht auf.
    Zweimal, nicht oefter: Ein Rechner, der wirklich aus ist, soll sich nicht
    hinter Wiederholungen verstecken koennen.
    """
    r = urllib.request.Request(basis + pfad, headers={"Authorization": "Bearer " + token})
    for versuch in (1, 2):
        try:
            with urllib.request.urlopen(r, timeout=sekunden) as f:
                return json.load(f)
        except (urllib.error.URLError, socket.timeout, OSError):
            if versuch == 2:
                raise
            time.sleep(0.5)


def journal_fehler(basis, token, minuten=10):
    """Fehlerzeilen der letzten Minuten - der Strom liefert den Rueckstand."""
    seit, fehler = time.time() - minuten * 60, 0
    r = urllib.request.Request(basis + "/api/resident/events?since=0",
                               headers={"Authorization": "Bearer " + token})
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=8) as f:
            for zeile in f:
                text = zeile.decode("utf-8", "replace").strip()
                if text.startswith("data:"):
                    try:
                        e = json.loads(text[5:])
                    except ValueError:
                        continue
                    if e.get("kind") == "fehler" and (e.get("ts") or 0) >= seit:
                        fehler += 1
                if time.time() - t0 > 5:
                    break
    except (urllib.error.URLError, socket.timeout, OSError):
        pass
    return fehler


def pruefe(name, basis, token):
    befunde = []
    try:
        gesund = hole(basis, token, "/api/health")
    except Exception as f:                                  # noqa: BLE001
        return [f"{name}: Bruecke nicht erreichbar ({type(f).__name__})"]
    if "push" in gesund and not gesund.get("push"):
        befunde.append(f"{name}: kann keine Push schicken - Schluessel oder Einstellungen fehlen")
    if gesund.get("devices") == 0:
        befunde.append(f"{name}: kein Geraet fuer Push angemeldet")

    try:
        sitzungen = hole(basis, token, "/api/sessions").get("sessions", [])
    except Exception:                                       # noqa: BLE001
        sitzungen = []
    for s in sitzungen:
        laeuft = time.time() - (s.get("started") or time.time())
        if not s.get("terminal") and s.get("busy") and laeuft > GRENZEN["sitzung_busy_s"]:
            befunde.append(f"{name}: gehostete Sitzung arbeitet seit {laeuft/60:.0f} min "
                           f"({(s.get('title') or s.get('key'))[:40]}) - haengt sie an einer Freigabe?")

    try:
        usage = hole(basis, token, "/api/usage")
        fuenf = (usage.get("five_hour") or {}).get("used")
        # Ein Stand, den niemand mehr fortschreibt, sagt nichts ueber jetzt.
        # Auf dem PC stand er zwei Stunden lang bei 40 Prozent, weil dort
        # keine Sitzung mehr lief, die Zahlen liefert - und sah aus wie eine
        # Messung.
        gemessen = usage.get("updated")
        alt = isinstance(gemessen, (int, float)) and time.time() - gemessen > 1800
        if alt:
            befunde.append(f"{name}: Abo-Stand ist {(time.time()-gemessen)/60:.0f} min alt "
                           f"({fuenf:.0%}) - hier laeuft keine Sitzung, die ihn meldet")
        elif isinstance(fuenf, (int, float)):
            vorher = abo_merken(name, fuenf)
            if fuenf > GRENZEN["abo"]:
                befunde.append(f"{name}: 5-Stunden-Limit bei {fuenf:.0%} - ueber der Grenze von {GRENZEN['abo']:.0%}")
            elif vorher is not None and vorher > GRENZEN["abo"]:
                # Das ist die Meldung, die den Timer ersetzt: Sie kommt, wenn
                # das Fenster wirklich frei ist, nicht wenn jemand es erwartet.
                befunde.append(f"{name}: Kontingent wieder frei - 5-Stunden-Limit bei "
                               f"{fuenf:.0%}, vorher {vorher:.0%}. Weiterarbeiten geht.")
    except Exception:                                       # noqa: BLE001
        pass

    if not gesund.get("resident"):
        return befunde                                      # hier wohnt keiner
    try:
        bewohner = hole(basis, token, "/api/resident")["resident"]
    except Exception as f:                                  # noqa: BLE001
        return befunde + [f"{name}: Bewohner nicht lesbar ({type(f).__name__})"]
    if not bewohner.get("alive"):
        befunde.append(f"{name}: Bewohner meldet sich nicht (Zustand {bewohner.get('state')})")
    for w in (bewohner.get("conversation") or {}).get("waiting", []):
        wartet = time.time() - (w.get("ts") or time.time())
        if wartet > GRENZEN["frage_wartet_s"]:
            befunde.append(f"{name}: Frage wartet seit {wartet:.0f} s ({w.get('von')})")
    for a in bewohner.get("requests", []):
        if a.get("status") == "offen":
            offen = time.time() - (a.get("ts") or time.time())
            if offen > GRENZEN["antrag_offen_s"]:
                befunde.append(f"{name}: Antrag offen seit {offen/60:.0f} min - {(a.get('title') or '')[:60]}")

    try:
        selbst = ((hole(basis, token, "/api/resident/self").get("lage") or {}).get("selbst")) or {}
    except Exception:                                       # noqa: BLE001
        selbst = {}
    if selbst:
        tempo = selbst.get("tempo_tok_s")
        if isinstance(tempo, (int, float)) and tempo < GRENZEN["tempo_tok_s"]:
            befunde.append(f"{name}: gpt-oss nur {tempo:.0f} tok/s - ausgelagerter Grafikspeicher?")
        if selbst.get("ollama") is False:
            befunde.append(f"{name}: Ollama antwortet nicht")
        if (selbst.get("waisen") or 0) > 0:
            befunde.append(f"{name}: {selbst['waisen']} verwaiste llama-server belegen die Karte")
        takt = selbst.get("ticks_je_minute")
        if isinstance(takt, (int, float)) and takt > GRENZEN["ticks_je_minute"]:
            befunde.append(f"{name}: {takt:.0f} Blicke je Minute - weckt er sich selbst?")
        for g in selbst.get("gpu") or []:
            if (g.get("geteilt") or 0) > GRENZEN["geteilt_mib"] and "llama" in (g.get("name") or ""):
                befunde.append(f"{name}: {g['name']} liegt mit {g['geteilt']} MiB im geteilten Speicher")

    try:
        eingang = hole(basis, token, "/api/resident/self").get("eingang") or []
    except Exception:                                       # noqa: BLE001
        eingang = []
    # Nur was er wirklich nicht beschrieben hat: die Beschreibung steht als
    # Erinnerung der Art "datei" oder als Fund im Journal - sonst meldet die
    # Wache jede alte Datei, auch die laengst gesehene (12.09.2026).
    beschrieben = ""
    try:
        beschrieben = json.dumps(hole(basis, token, "/api/resident/memory?art=datei&limit=100"),
                                 ensure_ascii=False)
    except Exception:                                       # noqa: BLE001
        pass
    for f in eingang:
        liegt = time.time() - (f.get("mtime") or time.time())
        datei = (f.get("path") or "").split("/")[-1]
        if liegt > GRENZEN["eingang_liegt_s"] and datei and datei not in beschrieben:
            befunde.append(f"{name}: {f.get('path')} liegt seit {liegt/60:.0f} min im Eingang, "
                           f"ohne dass er es beschrieben hat - sieht er noch hin?")

    fehler = journal_fehler(basis, token)
    if fehler > GRENZEN["fehler_je_10min"]:
        befunde.append(f"{name}: {fehler} Fehler im Journal der letzten 10 Minuten")
    return befunde


def faeden(host):
    """Ein gestorbener Faden im Bewohner bleibt sonst stumm: er tickt weiter
    und sieht doch nichts (12.09.2026, wahrnehmung ohne `import re`)."""
    import subprocess
    # Nur ein Absturz, der NACH dem letzten Start des Fadens steht - sonst
    # meldet die Wache stundenlang einen Fehler, der laengst behoben ist.
    ps = ('$l = Get-Content -Encoding UTF8 -Tail 600 "$env:USERPROFILE\\mcp-test\\werkstatt\\bewohner.log"; '
          '$start = ($l | Select-String -Pattern "\\[faden\\] .* laeuft|\\[faden\\] .* läuft" | '
          'Select-Object -Last 1).LineNumber; if (-not $start) { $start = 0 }; '
          '($l | Select-String -Pattern "Exception in thread" | '
          'Where-Object { $_.LineNumber -gt $start } | Select-Object -Last 3 | '
          'ForEach-Object { $_.Line.Trim() }) -join "; "')
    try:
        aus = subprocess.run(["ssh", "-o", "ConnectTimeout=10", host, ps],
                             capture_output=True, text=True, timeout=40).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return []
    return [f"PC: gestorbener Faden im Bewohner - {aus[:160]}"] if "Exception in thread" in aus else []


def _sekunden(etime):
    """[[tt-]hh:]mm:ss, wie ps es auf dem Mac schreibt."""
    tage = 0
    if "-" in etime:
        kopf, etime = etime.split("-", 1)
        tage = int(kopf)
    teile = [int(x) for x in etime.split(":")]
    while len(teile) < 3:
        teile.insert(0, 0)
    return tage * 86400 + teile[0] * 3600 + teile[1] * 60 + teile[2]


def nicht_im_betrieb(host=None):
    """Committet heisst nicht in Betrieb.

    Ein langlebiger Python-Prozess laedt seine Module beim Start; danach
    aendert kein Commit etwas. Am 12.09.2026 lief die Mac-Bruecke seit 00:49
    mit zehn ungeladenen Commits (darunter der Limit-Fix), der Bewohner seit
    12:59 mit sieben, und eine Reparatur der Sprechform lag 29 Minuten
    committet herum, ohne zu wirken. Jedes Mal fiel es nur auf, weil jemand
    von Hand die Prozess-Startzeit gegen die Commit-Zeit hielt. Also tut das
    hier die Wache.
    """
    import subprocess
    aus = []
    hier = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        # Die Bruecke ueber den PORT suchen, nicht ueber den Prozessnamen: die
        # Proben starten eigene Bruecken (8775-8779), und pgrep findet die
        # zuerst. Am 12.09. meldete die Wache daraufhin eine Bruecke von 16:28
        # als veraltet, waehrend die echte seit 17:53 lief - ein Fehlalarm aus
        # genau der Pruefung, die Fehlalarme verhindern soll.
        port = 8780
        try:
            cfg = json.load(open(os.path.expanduser("~/.config/iris/config.json"),
                                 encoding="utf-8-sig"))
            port = int(cfg.get("port") or 8780)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        pids = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                              capture_output=True, text=True, timeout=10).stdout.split()
        if pids:
            et = subprocess.run(["ps", "-p", pids[0], "-o", "etime="],
                                capture_output=True, text=True, timeout=10).stdout.strip()
            seit = time.time() - _sekunden(et)
            ct = subprocess.run(["git", "-C", hier, "log", "-1", "--format=%ct", "--", "bridge/"],
                                capture_output=True, text=True, timeout=15).stdout.strip()
            if ct and float(ct) > seit:
                aus.append("Mac: die Bruecke laeuft seit %s, der letzte Commit an bridge/ ist "
                           "juenger (%s) - bis zum Neustart wirkt er nicht"
                           % (time.strftime("%H:%M", time.localtime(seit)),
                              time.strftime("%H:%M", time.localtime(float(ct)))))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    if not host:
        return aus
    ps = ('$p = Get-CimInstance Win32_Process -Filter "Name like \'%python%\'" | '
          'Where-Object { $_.CommandLine -like "*bewohner.py*" } | '
          'Sort-Object CreationDate | Select-Object -First 1; '
          'if ($p) { [int]((Get-Date) - $p.CreationDate).TotalSeconds } else { -1 }; '
          # Die DATEI auf der Platte entscheidet, nicht der Commit. Der Code
          # wird eingespielt, der Bewohner neu gestartet, und erst danach
          # committet - dann ist der Commit juenger als der Prozess, obwohl
          # genau dieser Code laeuft. Das meldete die Wache am 13.09. um
          # 19:56 als Rueckstand, und ein Alarm ohne Grund wird bald nicht
          # mehr gelesen.
          'cd $env:USERPROFILE\\mcp-test; '
          '[int](Get-ChildItem *.py | Sort-Object LastWriteTime -Descending | '
          'Select-Object -First 1 | ForEach-Object { '
          '(Get-Date $_.LastWriteTime -UFormat %s) })')
    try:
        roh = subprocess.run(["ssh", "-o", "ConnectTimeout=10", host, ps],
                             capture_output=True, text=True, timeout=40).stdout.split()
        if len(roh) >= 2 and int(roh[0]) >= 0:
            seit = time.time() - int(roh[0])
            if float(roh[1]) > seit:
                aus.append("PC: der Bewohner laeuft seit %s, eine Datei seines Codes "
                           "ist juenger (%s) - bis zum Neustart wirkt sie nicht"
                           % (time.strftime("%H:%M", time.localtime(seit)),
                              time.strftime("%H:%M", time.localtime(float(roh[1])))))
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    return aus


def bruecken():
    """Mac aus der eigenen Konfiguration, PC aus der Umgebung."""
    aus = []
    try:
        cfg = json.load(open(os.path.expanduser("~/.config/iris/config.json"), encoding="utf-8-sig"))
        aus.append(("Mac", f"http://127.0.0.1:{cfg.get('port', 8780)}", cfg["token"]))
    except (OSError, ValueError, KeyError):
        pass
    if os.environ.get("PC_URL") and os.environ.get("PC_TOKEN"):
        aus.append(("PC", os.environ["PC_URL"].rstrip("/"), os.environ["PC_TOKEN"]))
    return aus


def einmal():
    alle = []
    for name, basis, token in bruecken():
        alle += pruefe(name, basis, token)
        if name == "PC" and os.environ.get("PC_HOST"):
            alle += faeden(os.environ["PC_HOST"])
    alle += nicht_im_betrieb(os.environ.get("PC_HOST"))
    stempel = time.strftime("%H:%M")
    if alle:
        for b in alle:
            print(f"{stempel}  ACHTUNG  {b}", flush=True)
    else:
        print(f"{stempel}  alles ruhig", flush=True)
    return alle


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dauer", type=float, default=0, help="Stunden im Abstand von 5 Minuten")
    args = p.parse_args()
    ende = time.time() + args.dauer * 3600
    schlimm = einmal()
    while time.time() < ende:
        time.sleep(300)
        schlimm = einmal()
    sys.exit(1 if schlimm else 0)
