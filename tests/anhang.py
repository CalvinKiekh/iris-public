"""Ein Foto aus der App: kommt es im Terminal an, und wird es abgeschickt?

    python3 -m tests.anhang

Die Bruecke tippt eine Nachricht als Klammer-Einfuegen in den Tab, und der
Return kommt bei Terminal.app unmittelbar hinterher - `do script` haengt ihn
immer an. Bei einem Bildpfad macht Claude Code daraus einen Anhang, und
waehrend es das tut, geht genau dieser Return verloren. Der Text steht dann
in der Eingabe und wurde nie abgeschickt.

Dafuer gibt es die Nachkontrolle: ist die Eingabe danach nicht leer, kommt
ein zweiter Return. Nur griff sie nicht, wenn Claude gerade arbeitete - dann
galt die Nachricht ungeprueft als zugestellt, weil waehrend eines Zugs
eingetippter Text normalerweise vom Zug uebernommen wird. Bei einem Anhang
stimmt das nicht: uebernommen wird nur, was abgeschickt wurde.

Geprueft wird ohne Terminal und ohne Claude, nur die Entscheidung dazwischen.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge import terminals, typist

# Geprueft wird die Entscheidung, nicht die Geduld. Im Betrieb wartet die
# Bruecke je Versuch drei Sekunden auf die leere Eingabe - hier reichen
# Millisekunden, die Logik ist dieselbe. Vorher kostete allein diese Datei
# mehrere Minuten je `make check`, der letzte Fall davon eine halbe.
terminals.ANHANG_FENSTER = 0.02
terminals.ANHANG_TAKT = 0.002
terminals.ANHANG_ANKUNFT = 0.04

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


class Tab:
    """Ein Terminal, das sich merkt, wie oft Return gedrueckt wurde.

    `leert_bei` zaehlt nur NACHGEDRUECKTE Returns. Den ersten haengt
    `do script` selbst an, und genau den frisst die Anhang-Kachel - er taucht
    hier also nie auf. 0 heisst: war schon abgeschickt. 1 heisst: ein
    Nachdruecker genuegt. 99 heisst: es hilft gar nichts.
    """

    def __init__(self, leert_bei=1, busy=False, erscheint_nach=0):
        self.returns = 0
        self.leert_bei = leert_bei
        self.busy = busy
        # Wie oft der Bildschirm gelesen wird, bevor das Eingefuegte
        # ueberhaupt dasteht. 0 = sofort. Genau hier lag der Wettlauf:
        # die leere Eingabe direkt nach dem Tippen heisst "noch nicht da",
        # nicht "abgeschickt".
        self.erscheint_nach = erscheint_nach
        self.blicke = 0

    @property
    def leer(self):
        self.blicke += 1
        if self.blicke <= self.erscheint_nach:
            return True                     # noch nichts angekommen
        return self.returns >= self.leert_bei


def stelle_um(tab):
    """typist durch den Papp-Tab ersetzen, im Original nichts anfassen."""
    echt = (typist.screen_now, typist.status, typist.input_empty, typist._run)

    def screen_now(tty):
        return "❯" if tab.leer else "❯ Anhang: /tmp/foto.png"

    # input_empty bleibt das Original - es liest genau diesen Text.

    def status(sid):
        return "busy" if tab.busy else "idle"

    def _run(tty, text, how):
        if text == "":
            tab.returns += 1
        return "ok"

    typist.screen_now = screen_now
    typist.status = status
    typist._run = _run
    return echt


def stelle_zurueck(echt):
    (typist.screen_now, typist.status, typist.input_empty, typist._run) = echt


class Sitzung:
    """Nur so viel von TerminalSession, wie die Nachkontrolle anfasst."""

    def __init__(self, tab):
        self.tty = "/dev/ttys999"
        self.claude_session_id = "sid"
        self.busy = tab.busy
        self.karten = []

    def _emit(self, card):
        self.karten.append(card)

    def on_change(self, *_):
        pass

    def _view_open(self):
        return False

    def pruefe_nach(self, mit_anhang, during_turn):
        terminals.TerminalSession._confirm_typed(
            self, 1, during_turn=during_turn, mit_anhang=mit_anhang)

    @property
    def zugestellt(self):
        return any(c.get("kind") == "delivered" for c in self.karten)

    @property
    def gemeckert(self):
        return any(c.get("kind") == "error" for c in self.karten)


def lauf(mit_anhang, during_turn, leert_bei, busy=False, erscheint_nach=0):
    tab = Tab(leert_bei=leert_bei, busy=busy, erscheint_nach=erscheint_nach)
    echt = stelle_um(tab)
    try:
        s = Sitzung(tab)
        s.pruefe_nach(mit_anhang, during_turn)
        return s, tab
    finally:
        stelle_zurueck(echt)


print("Ein Foto, waehrend Claude arbeitet")
# Der gemeldete Fall: die Kachel frisst den ersten Return, der Zug laeuft.
s, tab = lauf(mit_anhang=True, during_turn=True, leert_bei=1, busy=True)
pruefe(tab.returns >= 1, "es wird nachgedrueckt", f"{tab.returns} Return")
pruefe(s.zugestellt, "und gilt danach als zugestellt")
pruefe(not s.gemeckert, "ohne Fehlermeldung")

print("Ein Foto im Ruhezustand")
s, tab = lauf(mit_anhang=True, during_turn=False, leert_bei=1)
pruefe(tab.returns >= 1, "es wird nachgedrueckt", f"{tab.returns} Return")
pruefe(s.zugestellt, "und gilt danach als zugestellt")

print("Text ohne Anhang, waehrend Claude arbeitet")
# Hier darf NICHT nachgedrueckt werden: waehrend eines Zugs uebernimmt
# Claude Code eingetippten Text selbst, ein zweiter Return waere eine
# zweite Nachricht.
s, tab = lauf(mit_anhang=False, during_turn=True, leert_bei=99, busy=True)
pruefe(tab.returns == 0, "es wird nicht nachgedrueckt", f"{tab.returns} Return")
pruefe(s.zugestellt, "gilt trotzdem als zugestellt")

print("Text ohne Anhang im Ruhezustand, sofort abgeschickt")
s, tab = lauf(mit_anhang=False, during_turn=False, leert_bei=0)
pruefe(tab.returns == 0, "kein zusaetzlicher Return noetig", f"{tab.returns} Return")
pruefe(s.zugestellt, "zugestellt")

print("Ein grosses Foto, das lange braucht")
# Der gemessene Fall vom 23.09.: Claude Code liest ein 5-MB-Bild ein und
# nimmt den Return erst danach an. Zweimal druecken reichte nicht, und
# Calvin musste am Rechner selbst drueckten.
s, tab = lauf(mit_anhang=True, during_turn=True, leert_bei=5, busy=True)
pruefe(s.zugestellt, "wird nach mehrfachem Nachfassen doch zugestellt")
pruefe(tab.returns >= 5, "es wird so oft gedrueckt wie noetig", f"{tab.returns}")
pruefe(not s.gemeckert, "ohne Fehlermeldung")

print("Das Eingefuegte braucht einen Moment, bis es dasteht")
# Der gemessene Wettlauf vom 23.09.: sofort nach dem Tippen ist die
# Eingabe leer, weil noch nichts angekommen ist. Wer das fuer
# "abgeschickt" haelt, hoert auf, bevor er angefangen hat.
s, tab = lauf(mit_anhang=True, during_turn=True, leert_bei=1, busy=True,
              erscheint_nach=4)
pruefe(tab.returns >= 1, "es wird trotzdem nachgedrueckt", f"{tab.returns}")
pruefe(s.zugestellt, "und danach zugestellt")

print("Wirklich sofort weg")
# Bleibt die Eingabe die ganze Frist ueber leer, war es tatsaechlich
# abgeschickt - dann darf niemand nachdruecken.
s, tab = lauf(mit_anhang=True, during_turn=True, leert_bei=0, busy=True,
              erscheint_nach=999)
pruefe(tab.returns == 0, "kein Nachdruecker", f"{tab.returns}")
pruefe(s.zugestellt, "gilt als zugestellt")

print("Ein Foto, das sich gar nicht abschicken laesst")
# Auch der zweite Return hilft nicht: dann wird gesagt, was ist, statt
# Zustellung zu behaupten.
s, tab = lauf(mit_anhang=True, during_turn=True, leert_bei=999, busy=True)
pruefe(not s.zugestellt, "wird nicht als zugestellt gemeldet")
pruefe(tab.returns == terminals.ANHANG_VERSUCHE - 1,
       "es wird nicht endlos gedrueckt", f"{tab.returns}")
pruefe(s.gemeckert, "sondern als Fehler benannt")

print("Woran ein Anhang erkannt wird")
import re
erkennt = lambda t: bool(re.search(r"(?m)^Anhang: ", t))
pruefe(erkennt("Anhang: /tmp/foto.png"), "eine reine Anhangzeile")
pruefe(erkennt("Schau mal\n\nAnhang: /tmp/foto.png"), "Text mit Anhang darunter")
pruefe(not erkennt("Wir reden über den Anhang: der ist zu groß"),
       "das Wort mitten im Satz zaehlt nicht")

print()
print(f"{ok_count} ok, {len(fehler)} fehlgeschlagen")
sys.exit(1 if fehler else 0)
