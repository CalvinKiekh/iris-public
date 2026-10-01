"""Probe fuer die Satztrennung in gespraech.py - der Fehler, den Calvin HOERT.

    python sprechteil_test.py

Am 12.09. um 12:03 kam aus dem Strom:

    Teil 1  "22:15: Llama-Server abgestuerzt, 23:33: Speicher-Fehler mit 1202 Mi"
    Teil 2  "B geteilt, 23:39: Fehler-Traceback bei Gespraech, ..."

    Teil 1  "...23:39: Traceback, 23"
    Teil 2  ":48: Neues Geraet entdeckt, 23:55: Einkaufsliste gefunden."

Vorgelesen wird daraus ein abgehackter Satz und danach ein sinnloses "B".
Ein Sprechteil darf nur zwischen Woertern enden - notfalls wird er laenger.

Es wird nichts geschrieben, kein Modell gefragt, keine Datei angelegt: der
Strom wird nachgestellt, wie ihn Ollama liefert.
"""
from __future__ import annotations

import json
import sys
import threading

import gespraech
from gespraech import Gespraech

GESAMT = 0
FEHLER = 0


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


class StromAttrappe:
    """Gibt einen Text stueckweise zurueck, wie Ollama es tut.

    Die Stueckelung ist der Kern: Der Fehler trat nur auf, weil der Puffer in
    dem Moment, in dem geschnitten wurde, zufaellig gerade so weit war.
    """

    def __init__(self, stuecke: list[str]) -> None:
        self.stuecke = stuecke

    def iter_lines(self):
        for s in self.stuecke:
            yield json.dumps({"message": {"content": s}})
        yield json.dumps({"message": {"content": ""}, "done": True})

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def teile(stuecke: list[str], mit_volltext: bool = False):
    """Was der Strom aus diesen Stuecken als Sprechteile macht."""
    echt = gespraech.httpx.stream
    gespraech.httpx.stream = lambda *a, **k: StromAttrappe(stuecke)
    try:
        g = Gespraech.__new__(Gespraech)
        g._abbruch = threading.Event()
        g.erstes_token = None
        ziel: list[str] = []
        voll: list[str] = []
        g._antwort_stroemen([], ziel, threading.Event(), volltext=voll)
        return (ziel, voll[0] if voll else "") if mit_volltext else ziel
    finally:
        gespraech.httpx.stream = echt


def _worte(text: str) -> list[str]:
    return " ".join(str(text).split()).split(" ")


def zerschnitten(gesprochen: list[str], quelle: list[str]) -> list[str]:
    """Welche Woerter hat die Trennung zerrissen?

    Der erste Anlauf dieser Probe verglich nur die Nahtstelle: endet Teil A
    auf einem Buchstaben und beginnt Teil B mit einem, sei ein Wort
    zerrissen. Das ist falsch - zwischen "Llama-Server" und "abgestuerzt"
    stand im Original ein Leerzeichen, und beide sind ganze Woerter. Die
    Probe meldete FEHL fuer richtiges Verhalten.

    Nachrechenbar ist nur der Vergleich mit dem Original: Setzt man die
    Sprechteile wieder zusammen, muss dieselbe Wortfolge herauskommen. Faellt
    ein Schnitt ins Wort, steht dort "1202 Mi B geteilt" statt "1202 MiB
    geteilt" - ein Wort mehr, und zwei, die es nicht gibt.
    """
    soll = _worte("".join(quelle))
    ist = _worte(" ".join(gesprochen))
    return [f"{a!r} statt {b!r}" for a, b in zip(ist, soll) if a != b] \
        or ([f"{len(ist)} Woerter statt {len(soll)}"] if len(ist) != len(soll)
            else [])


# Die Chronik von 12:03, wortgetreu - und mit der Stueckelung, die den
# Fehler WIRKLICH ausloest. Das war nicht die erste Vermutung:
#
# Ein "\r\n" wird oben zu zwei Leerzeichen, wo `" ".join(woerter[:8])` nur
# eines setzt. Das verschiebt den Zeichenindex um eins - und genau um eins
# rechnete die alte Formel mit ihrem "+ 1" ohnehin zu weit. EIN Umbruch hob
# sich also auf, und die Probe blieb gruen, obwohl der Fehler im Code stand.
# Erst ZWEI Umbrueche vor dem achten Wort verschieben so weit, dass der
# Schnitt ins Wort faellt.
#
# Gegen den alten Code ergibt das hier woertlich, was Calvin gehoert hat:
#   Teil 1  "... Speicher-Fehler mit 1202 Mi"
#   Teil 2  "B geteilt, 23:39: Traceback, ..."
CHRONIK = [
    "22:15: Llama-Server abgestuerzt,\r\n", "23:33: Speicher-Fehler\r\n",
    "mit 1202 MiB geteilt,", " 23:39: Traceback, 23:48: Neues Geraet.",
]


QUELLE_KOMMA = ["Ich sehe, ", "wer im Heimnetz ist und seit wann. ",
                "Ich erinnere an Termine."]
QUELLE_LANG = ["Ich habe heute sehr viele Dinge im Heimnetz "
               "beobachtet und gemessen ohne Punkt"]


def probe_chronik() -> None:
    print("\ndie Chronik von 12:03 - kein Teil endet mitten im Wort")
    t = teile(CHRONIK)
    for i, s in enumerate(t, 1):
        print("    %d. %s" % (i, s))
    schlimm = zerschnitten(t, CHRONIK)
    pruefe(not schlimm,
           "keine zerrissenen Woerter%s"
           % ("" if not schlimm else ": " + str(schlimm)))
    ganz = " ".join(t)
    pruefe("1202 MiB" in ganz,
           "\"1202 MiB\" steht zusammen, nicht als \"1202 Mi\" und \"B\": %s"
           % ganz[:80])
    pruefe("23:48" in ganz,
           "und die Uhrzeit 23:48 ist nicht zerrissen")


# Stuecke in Tokengroesse, wie das Modell sie wirklich schickt - mitten im
# Wort. Diese drei Faelle stammen aus dem Journal von 13:01, also NACH der
# ersten Reparatur: sie hat nur den verrutschten Zeichenindex behoben, nicht
# den Schnitt am Pufferende.
TOKENWEISE = {
    "Entschuldigung": (
        ["Entschuld", "igung", ", aber ich verstehe", " die Frage nicht.",
         " Kannst du sie bitte präziser formulieren?"],
        "Entschuldigung"),
    "Llama-Server": (
        ["22:15", ": Llama", "‑Server", " abgestürzt.",
         " 23:33: Speicher‑Fehler, 1202 MiB geteilt."],
        "Llama‑Server"),
    "Rhythmus": (
        ["Ich kann Platzverlauf, Sehen, Stimme hören, Lesen, Rhythm",
         "us, Erinnern, Netz."],
        "Rhythmus"),
}


def probe_tokenweise() -> None:
    print("\ntokenweise gestueckelt - der Fall von 13:01")
    for name, (stuecke, muss_zusammen) in TOKENWEISE.items():
        t = teile(stuecke)
        schlimm = zerschnitten(t, stuecke)
        pruefe(not schlimm, "%s bleibt heil%s"
               % (name, "" if not schlimm else ": " + str(schlimm[:2])))
        pruefe(any(muss_zusammen in s for s in t),
               "%r steht in EINEM Teil: %s" % (muss_zusammen, t[:2]))


def probe_acht_woerter_sind_acht() -> None:
    print("\nacht Woerter sind acht Woerter, nicht acht Stuecke")
    g = Gespraech
    # Der Fehler in der ersten Reparatur: `(?:\s*\S+){8}` passt auf jedes
    # Wort mit acht Zeichen, weil \S+ zuruecksetzen darf.
    pruefe(not g.ACHT_WOERTER.match("Entschuld"),
           "ein einzelnes langes Wort sind KEINE acht Woerter")
    pruefe(not g.ACHT_WOERTER.match("Arbeitsspeicherauslastung"),
           "auch ein sehr langes nicht")
    treffer = g.ACHT_WOERTER.match("eins zwei drei vier fuenf sechs sieben "
                                   "acht neun")
    pruefe(treffer and treffer.group().split() == ["eins", "zwei", "drei",
                                                   "vier", "fuenf", "sechs",
                                                   "sieben", "acht"],
           "acht echte Woerter schon: %r" % (treffer and treffer.group()))
    pruefe(not g.ACHT_WOERTER.match("eins zwei drei vier fuenf sechs sieben"),
           "sieben sind zu wenig")


def probe_pufferende() -> None:
    print("\nam Pufferende wird nicht geschnitten, wenn ein Wort offen ist")
    g = Gespraech
    pruefe(not g._ganzes_wort("Entschuld", 9),
           "ein Puffer, der auf einem Buchstaben endet, ist offen")
    pruefe(not g._ganzes_wort("22:15: Llama", 12),
           "auch wenn davor eine Uhrzeit steht")
    pruefe(g._ganzes_wort("Er kam.", 7),
           "auf einem Satzzeichen ist er zu Ende")
    pruefe(g._ganzes_wort("Ja, er kam. ", 12),
           "auf Leerraum auch")
    pruefe(not g._ganzes_wort("Llama‑Server", 5),
           "und der Bindestrich haelt das Wort zusammen")


def probe_volltext() -> None:
    """Was gemerkt und gelesen wird, kommt ungeteilt - nicht zurueckgerechnet.

    Der Mac hat am 12.09. im Gedaechtnis "Entschuld igung" und "Llama -Server"
    gefunden und in seiner App eine Regel dagegen gebaut: endet links
    alphanumerisch und beginnt rechts klein, dann ohne Leerzeichen. Die Regel
    repariert genau diese zwei Faelle und zerstoert dafuer jeden regulaeren
    Acht-Woerter-Schnitt - aus "... im Heimnetz" + "beobachtet und gemessen"
    wird "Heimnetzbeobachtet".

    Raten muss aber niemand: Der ungeteilte Text liegt im Strom ohnehin vor.
    """
    print("\nder Volltext wird nicht aus Sprechteilen zurueckgerechnet")

    def mac_regel(teile_):
        raus = teile_[0] if teile_ else ""
        for t in teile_[1:]:
            if raus and t and raus[-1].isalnum() and t[0].islower() \
                    and t[0].isalnum():
                raus += t
            else:
                raus += " " + t
        return raus

    for name, (stuecke, _) in TOKENWEISE.items():
        t, voll = teile(stuecke, mit_volltext=True)
        soll = " ".join("".join(stuecke).split())
        pruefe(voll == soll, "%s: der Volltext ist der Originaltext" % name)

    # Und der Fall, den die Regel des Mac kaputtmacht.
    stuecke = ["Ich habe heute sehr viele Dinge im Heimnetz",
               " beobachtet und gemessen."]
    t, voll = teile(stuecke, mit_volltext=True)
    pruefe(len(t) >= 2, "der Acht-Woerter-Schnitt greift: %s" % t)
    pruefe("Heimnetz beobachtet" in voll,
           "der Volltext haelt die Woerter auseinander: %r" % voll[-40:])
    pruefe("Heimnetzbeobachtet" in mac_regel(t),
           "waehrend die Zusammensetz-Regel sie verklebt - genau deshalb "
           "wird nicht zusammengesetzt: %r" % mac_regel(t)[-40:])


def probe_haelt_zusammen() -> None:
    """Ein Bindestrich am Pufferende heisst "es kommt noch etwas".

    Calvin am 12.09.: "Das muss man auf jeden Fall machen." Gemeint war die
    Regel des Mac, Teile ohne Leerzeichen zusammenzusetzen. Die Regel selbst
    ist gefaehrlich (siehe probe_volltext), aber der Mangel dahinter war echt
    und hatte NOCH eine Quelle: Endete der Puffer auf einem Bindestrich oder
    Schraegstrich, galt der Schnitt als sicher, weil das Zeichen kein
    Buchstabe ist. Der Sprechteil endete auf dem Strich, und wer die Teile
    mit Leerzeichen zusammensetzt, bekam "werkstatt/ eingang/datei.txt".
    """
    print("\nBindestrich und Schraegstrich halten ein Wort zusammen")
    faelle = {
        "Bindestrich": (["Ich sehe hier den grossen wichtigen Llama-",
                         "Server im Speicher."], "Llama-Server"),
        "Schraegstrich": (["Der Pfad lautet eingang und dann weiter "
                           "werkstatt/", "eingang/datei.txt"],
                          "werkstatt/eingang"),
        "Apostroph": (["Er fragte mich neulich einmal ganz direkt wie's",
                       " denn so laeuft."], "wie's"),
    }
    for name, (stuecke, muss_zusammen) in faelle.items():
        t, voll = teile(stuecke, mit_volltext=True)
        zusammengesetzt = " ".join(t)
        pruefe(muss_zusammen in zusammengesetzt,
               "%s: %r bleibt auch beim Zusammensetzen heil: %r"
               % (name, muss_zusammen, zusammengesetzt[-46:]))
        pruefe(muss_zusammen in voll,
               "%s: und im Volltext ohnehin" % name)


def probe_uhrzeit_ist_kein_satzzeichen() -> None:
    print("\nein Doppelpunkt zwischen Ziffern ist eine Uhrzeit")
    pruefe(not gespraech.Gespraech.FRUEH.search("Um 23:48 kam etwas"),
           "in \"23:48\" wird nicht geschnitten")
    pruefe(bool(gespraech.Gespraech.FRUEH.search("Es ist so: er kam")),
           "nach einem echten Doppelpunkt schon")
    pruefe(bool(gespraech.Gespraech.FRUEH.search("Ja, er kam")),
           "und nach einem Komma auch")
    # Der Fall aus dem Journal: der zweite Doppelpunkt steht hinter einer
    # Ziffer und leitet keinen Satzteil ein.
    pruefe(not gespraech.Gespraech.FRUEH.match("22:15: Llama"),
           "\"22:15: \" ist kein Schnittpunkt am Anfang")


def probe_wortgrenze() -> None:
    print("\ndie letzte Sicherung: _ganzes_wort")
    g = Gespraech
    pruefe(not g._ganzes_wort("1202 MiB geteilt", 6),
           "zwischen \"Mi\" und \"B\" wird nicht geschnitten")
    pruefe(g._ganzes_wort("1202 MiB geteilt", 4),
           "zwischen \"1202\" und \" MiB\" schon")
    pruefe(g._ganzes_wort("Er kam.", 7), "am Ende des Puffers immer")
    pruefe(g._ganzes_wort("Ja, er kam", 3),
           "und hinter einem Komma auch")


def probe_frueher_schnitt_bleibt() -> None:
    print("\nder fruehe Schnitt bleibt - er hat den ersten Ton halbiert")
    t = teile(QUELLE_KOMMA)
    pruefe(len(t) >= 2, "es wird ueberhaupt frueh geteilt: %s" % t)
    pruefe(t[0].startswith("Ich sehe"),
           "und der erste Brocken kommt am Komma: %r" % t[0])
    pruefe(not zerschnitten(t, QUELLE_KOMMA), "ohne ein Wort zu zerreissen")

    # Ein langer Satz ohne Satzzeichen: dann greift der Acht-Woerter-Schnitt.
    lang = teile(QUELLE_LANG)
    pruefe(len(lang) >= 2 and len(lang[0].split()) >= 8,
           "nach acht Woertern auch ohne Satzzeichen: %s" % lang)
    pruefe(not zerschnitten(lang, QUELLE_LANG),
           "und ebenfalls an einer Wortgrenze: %s"
           % zerschnitten(lang, QUELLE_LANG))


def main() -> int:
    print("Probe Sprechteile")
    probe_chronik()
    probe_tokenweise()
    probe_acht_woerter_sind_acht()
    probe_pufferende()
    probe_volltext()
    probe_haelt_zusammen()
    probe_uhrzeit_ist_kein_satzzeichen()
    probe_wortgrenze()
    probe_frueher_schnitt_bleibt()
    print("\n%d von %d bestanden" % (GESAMT - FEHLER, GESAMT))
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
