"""Claude Code aktualisieren, ohne die Terminals zu verlieren.

    python3 -m tests.aktualisieren

Der Ablauf ist zerstoererisch: er beendet jede Sitzung. Deshalb wird er hier
ohne Terminal, ohne brew und ohne Claude geprueft - nur die Entscheidungen
dazwischen, und vor allem die Faelle, in denen etwas schiefgeht.

Was zaehlt:

  - eine arbeitende Sitzung wird nicht angefasst
  - laesst sich eine nicht beenden, wird NICHT aktualisiert (lieber gar
    nicht als halb, und kein Tab wird ueberschrieben)
  - scheitert brew, kommen die Sitzungen trotzdem zurueck - sonst waere der
    Preis eines fehlgeschlagenen Updates ein leerer Schreibtisch
  - was nicht zurueckkommt, steht mit seinem Befehl im Ergebnis
  - die Sitzungskennung bleibt dieselbe, sonst waere der Verlauf weg
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge import aktualisieren, typist

ok_count = 0
fehler = []


def pruefe(bedingung, was, dazu=""):
    global ok_count
    if bedingung:
        ok_count += 1
        print(f"  ok   {was}")
    else:
        fehler.append(was)
        print(f"  FAIL {was}" + (f" ({dazu})" if dazu else ""))


SID_A = "11111111-2222-3333-4444-555555555555"
SID_B = "66666666-7777-8888-9999-aaaaaaaaaaaa"


class Tab:
    """Ein Terminal-Tab, der weiss, ob Claude darin laeuft."""

    def __init__(self, tty, sid, laeuft=True, beendet_sich=True, kommt_zurueck=True):
        self.tty, self.sid = tty, sid
        self.laeuft = laeuft
        self.beendet_sich = beendet_sich
        self.kommt_zurueck = kommt_zurueck
        self.befehle = []


class Sitzung:
    def __init__(self, tab, busy=False, titel="Sitzung", agent=False):
        self.tab = tab
        self.tty, self.claude_session_id = tab.tty, tab.sid
        self.key = "t-" + tab.sid
        self.busy = busy
        self.exited = False
        self.title = titel
        self.cwd = "/tmp"
        # Ein Agent aus /fork laeuft nebenher weiter, waehrend der Zug
        # selbst fertig ist - genau der Fall, der untaetig aussieht.
        self.background = ({"a1": {"id": "a1", "type": "agent", "status": "running"}}
                           if agent else {})

    def label(self):
        return self.title


class Verwalter:
    def __init__(self, sitzungen):
        class T:
            pass
        self.terminals = T()
        self.terminals.sessions = {s.key: s for s in sitzungen}


def stelle_um(tabs, brew_code=0):
    """typist und brew durch Attrappen ersetzen."""
    echt = (typist.type_into, typist.claude_gone, typist.resume_in_tab,
            aktualisieren._brew, aktualisieren.installiert)
    nach_tty = {t.tty: t for t in tabs}

    def type_into(tty, text):
        tab = nach_tty[tty]
        tab.befehle.append(text)
        if text == "/exit" and tab.beendet_sich:
            tab.laeuft = False
        return "ok"

    def claude_gone(tty):
        return not nach_tty[tty].laeuft

    def resume_in_tab(tty, sid, binary="claude"):
        tab = nach_tty[tty]
        tab.befehle.append(f"claude --resume {sid}")
        if tab.kommt_zurueck:
            tab.laeuft = True
        return "ok"

    stand = {"n": 0}

    def _brew(*args, **kw):
        stand["n"] += 1
        return (brew_code, "" if brew_code == 0 else "brew ist gestolpert")

    def installiert():
        return {"pfad": "/opt/homebrew/bin/claude", "art": "brew",
                "version": "2.1.280" if stand["n"] else "2.1.263"}

    typist.type_into, typist.claude_gone, typist.resume_in_tab = \
        type_into, claude_gone, resume_in_tab
    aktualisieren._brew, aktualisieren.installiert = _brew, installiert
    return echt


def stelle_zurueck(echt):
    (typist.type_into, typist.claude_gone, typist.resume_in_tab,
     aktualisieren._brew, aktualisieren.installiert) = echt


def lauf(tabs, sitzungen, brew_code=0):
    echt = stelle_um(tabs, brew_code)
    # Warten kostet im Test nur Zeit - die Attrappen antworten sofort.
    alt = (aktualisieren.ENDE_WARTEN, aktualisieren.START_WARTEN)
    aktualisieren.ENDE_WARTEN = aktualisieren.START_WARTEN = 0
    try:
        return aktualisieren.lauf(Verwalter(sitzungen))
    finally:
        aktualisieren.ENDE_WARTEN, aktualisieren.START_WARTEN = alt
        stelle_zurueck(echt)


print("Der gewöhnliche Fall: zwei Sitzungen, alles geht gut")
a, b = Tab("/dev/ttys001", SID_A), Tab("/dev/ttys002", SID_B)
r = lauf([a, b], [Sitzung(a), Sitzung(b)])
pruefe(r["ok"], "gelingt", str(r.get("grund")))
pruefe(r["aktualisiert"] and r["vorher"] == "2.1.263" and r["nachher"] == "2.1.280",
       "die Fassung hat sich geändert", f"{r.get('vorher')} -> {r.get('nachher')}")
pruefe(a.befehle == ["/exit", f"claude --resume {SID_A}"],
       "erst beenden, dann mit derselben Kennung zurück", str(a.befehle))
pruefe(a.laeuft and b.laeuft, "beide laufen wieder")

print("Eine Sitzung arbeitet gerade")
a, b = Tab("/dev/ttys001", SID_A), Tab("/dev/ttys002", SID_B)
r = lauf([a, b], [Sitzung(a, busy=True), Sitzung(b)])
pruefe(a.befehle == [], "sie wird nicht angefasst", str(a.befehle))
pruefe(a.laeuft, "und läuft unberührt weiter")
pruefe(len(r["sitzungen"]) == 1, "nur die andere wird behandelt")

print("Eine Sitzung hat einen Agenten aus /fork laufen")
# Sie sieht untaetig aus - der Zug ist fertig -, aber /exit wuerde den
# Agenten toeten, der vielleicht eine halbe Stunde gerechnet hat.
a, b = Tab("/dev/ttys001", SID_A), Tab("/dev/ttys002", SID_B)
r = lauf([a, b], [Sitzung(a, agent=True, titel="Mit Agent"), Sitzung(b)])
pruefe(a.befehle == [], "sie wird nicht angefasst", str(a.befehle))
pruefe(a.laeuft, "der Agent überlebt")
pruefe(len(r["sitzungen"]) == 1, "nur die andere wird behandelt")

print("Eine Sitzung lässt sich nicht beenden")
# Dann wird NICHT aktualisiert: ein Tab, in dem noch Claude läuft, würde
# sonst mit einem Shell-Befehl überschrieben.
a = Tab("/dev/ttys001", SID_A, beendet_sich=False)
b = Tab("/dev/ttys002", SID_B)
r = lauf([a, b], [Sitzung(a, titel="Hängt"), Sitzung(b)])
pruefe(not r["ok"], "bricht ab", str(r.get("grund")))
pruefe(r.get("haengen") == ["Hängt"], "nennt die Sitzung beim Namen",
       str(r.get("haengen")))
pruefe("2.1.263" not in str(r.get("nachher", "")), "brew lief gar nicht erst")
pruefe(not any("resume" in c for c in a.befehle + b.befehle),
       "und niemand wurde überschrieben", str(a.befehle + b.befehle))

print("brew scheitert")
a = Tab("/dev/ttys001", SID_A)
r = lauf([a], [Sitzung(a)], brew_code=1)
pruefe(not r["ok"], "wird als Fehlschlag gemeldet")
pruefe("brew" in r["grund"], "mit der Ursache", r["grund"][:40])
pruefe(a.laeuft, "die Sitzung ist trotzdem zurück")
pruefe(f"claude --resume {SID_A}" in a.befehle, "mit ihrer Kennung")

print("Eine Sitzung kommt nicht zurück")
a = Tab("/dev/ttys001", SID_A, kommt_zurueck=False)
b = Tab("/dev/ttys002", SID_B)
r = lauf([a, b], [Sitzung(a, titel="Verloren"), Sitzung(b)])
pruefe(not r["ok"], "wird als Fehlschlag gemeldet")
pruefe(len(r["von_hand"]) == 1 and r["von_hand"][0]["titel"] == "Verloren",
       "nennt sie", str(r.get("von_hand")))
pruefe(r["von_hand"][0]["befehl"] == f"claude --resume {SID_A}",
       "mit dem Befehl zum Abtippen", str(r["von_hand"][0]))
pruefe(b.laeuft, "die andere ist trotzdem zurück")

print("Was gar nicht erst getippt wird")
pruefe(typist.resume_in_tab("/dev/ttys001", "kein-uuid") != "ok",
       "eine Kennung, die keine UUID ist")
pruefe(typist.resume_in_tab("/dev/ttys001", "") != "ok", "eine leere Kennung")
pruefe(typist.resume_in_tab("/dev/ttys001", SID_A + "; rm -rf /") != "ok",
       "eine Kennung mit angehängtem Befehl")

print()
print(f"{ok_count} ok, {len(fehler)} fehlgeschlagen")
sys.exit(1 if fehler else 0)
