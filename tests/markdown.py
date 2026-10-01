"""Markdown aus Terminal-Sitzungen: kommt es an, und kommt es einmal?

    python3 tests/markdown.py

Der Bildschirm einer Terminal-Sitzung zeigt Markdown schon gezeichnet -
keine ##, keine ```, keine | in Tabellen. Die Bruecke liest ihn trotzdem,
weil er sofort da ist, und liefert danach aus dem Transkript nach. Diese
Nachlieferung sagt, welche Karten sie ersetzt.

Geprueft wird ohne Netz und ohne Claude, nur die Logik dazwischen:

  - die Nachlieferung traegt das Markdown (Ueberschrift, Codeblock, Tabelle)
  - sie nennt die Karten, an deren Stelle sie tritt
  - ein Absatz ohne jede Auszeichnung wird NICHT noch einmal geschickt
  - am Ende steht der Zug einmal da, nicht zweimal

Der letzte Punkt ist der Grund fuer die Datei: genau dort standen am
12.09. Absaetze doppelt, und es fiel erst auf Calvins Telefon auf.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge import terminals

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


class Sitzung:
    """Nur so viel von TerminalSession, wie die beiden Wege brauchen."""

    def __init__(self):
        self.karten = []
        self._seq = 0
        self._said = set()
        self._shown = []
        self._turn_says = []
        self._said_seq = {}
        self.text_log = []

    def _emit(self, card):
        self._seq += 1
        card = dict(card, seq=self._seq)
        self.karten.append(card)
        return self._seq

    # Was der Bildschirm zeigt: derselbe Absatz, aber gezeichnet.
    def vom_bildschirm(self, text):
        self._said.add(terminals._kern(text))
        self._shown.append(text)
        self._turn_says.append(self._emit({"kind": "say", "text": text}))

    def aus_dem_transkript(self, roh):
        terminals.TerminalSession._complete_from_transcript(self, [{"text": roh}])

    # Der andere Weg: die Sitzung hat einen Anzeige-Hook, der Bildschirm
    # wird gar nicht gelesen. Auch dort zeichnet Claude Code das Markdown
    # weg, und auch dort liegt es im Transkript.
    def vom_hook(self, text, mid):
        self._said.add(terminals._kern(text))
        self._shown.append(text)
        sq = self._emit({"kind": "say", "text": text, "message_id": mid})
        # Nummer und Laenge, wie die Bruecke sie merkt.
        self._said_seq.setdefault(mid, []).append(
            (sq, len(" ".join(terminals._plain_md(text).split()))))

    def transkript_zur_nachricht(self, mid, roh):
        terminals.TerminalSession._markdown_from_transcript(self, mid, [{"text": roh}])

    # Die Bruecke wurde neu gestartet und liest ihren Feed zurueck. Genau so
    # legt sie die Karte wieder ab - mit Markdown, so wie sie sie geschickt
    # hat.
    def feed_neu_geladen(self, kartentext):
        self._shown.append(kartentext.strip())
        self._said.add(terminals._kern(kartentext))

    # Unter demselben Namen wie in der Bruecke, damit die echten Methoden sie
    # aufrufen koennen, und einmal ohne Strich fuer die Pruefungen hier.
    def _schon_gesagt(self, text):
        return terminals.TerminalSession._schon_gesagt(self, text)

    schon_gesagt = _schon_gesagt


ANTWORT = """## Wo die Ebene liegt

Lacktisch ist ein Feature in der UR-Installation.

```
bezugsebene: {"name": "Lacktisch"}
```

| Rolle | betroffen? |
|---|---|
| Bezugssystem | nein |
"""

# So steht dieselbe Antwort auf dem Bildschirm: ohne #, ohne ```, ohne |.
AUF_DEM_SCHIRM = "Wo die Ebene liegt"

print("Nachlieferung mit Markdown")
s = Sitzung()
s.vom_bildschirm(AUF_DEM_SCHIRM)
s.aus_dem_transkript(ANTWORT)

nach = [c for c in s.karten if c.get("replaces")]
pruefe(len(nach) == 1, "genau eine Nachlieferung", f"{len(nach)} Stueck")
if nach:
    t = nach[0]["text"]
    pruefe("## Wo die Ebene liegt" in t, "Ueberschrift ist wieder da")
    pruefe("```" in t, "Codeblock ist wieder da")
    pruefe(re.search(r"(?m)^\|", t) is not None, "Tabelle ist wieder da")
    pruefe(nach[0]["replaces"] == [1], "nennt die Karte, die sie ersetzt",
           str(nach[0].get("replaces")))

print("Ein Absatz ohne Auszeichnung")
s2 = Sitzung()
schlicht = "Das Regal steht fest, die Messung passt."
s2.vom_bildschirm(schlicht)
s2.aus_dem_transkript(schlicht)
pruefe(not [c for c in s2.karten if c.get("replaces")],
       "wird nicht noch einmal geschickt", f"{len(s2.karten)} Karten")

print("Derselbe Weg ueber den Anzeige-Hook")
s3 = Sitzung()
s3.vom_hook(AUF_DEM_SCHIRM, "msg_1")
s3.transkript_zur_nachricht("msg_1", ANTWORT)
nach3 = [c for c in s3.karten if c.get("replaces")]
pruefe(len(nach3) == 1, "auch hier eine Nachlieferung", f"{len(nach3)} Stueck")
pruefe(nach3 and "```" in nach3[0]["text"], "mit dem Markdown")
pruefe(nach3 and nach3[0]["replaces"] == [1], "ersetzt die Karte des Hooks",
       str(nach3[0].get("replaces")) if nach3 else "keine")

s4 = Sitzung()
s4.vom_hook("Das Regal steht fest.", "msg_2")
s4.transkript_zur_nachricht("msg_2", "Das Regal steht fest.")
pruefe(not [c for c in s4.karten if c.get("replaces")],
       "ohne Auszeichnung auch hier keine zweite Karte")

print("Eine Nachlieferung, die kuerzer ist")
# Der Transkript-Eintrag kann geschrieben werden, waehrend die Nachricht
# noch waechst. Wuerde er die ganze Karte ersetzen, fehlte am Ende Text -
# genau das ist passiert.
s5 = Sitzung()
lang = "Erster Absatz mit **Auszeichnung**.\n\nZweiter Absatz, und noch viel mehr Text dahinter, der nicht verloren gehen darf."
s5.vom_hook(lang, "msg_3")
s5.transkript_zur_nachricht("msg_3", "## Erster Absatz mit Auszeichnung.")
pruefe(not [c for c in s5.karten if c.get("replaces")],
       "kuerzerer Stand ersetzt nichts", f"{len(s5.karten)} Karten")
s5.transkript_zur_nachricht("msg_3", "## Erster Absatz\n\n" + lang)
pruefe(len([c for c in s5.karten if c.get("replaces")]) == 1,
       "der vollstaendige Stand danach schon")

print("Ein Zug mit zwei Nachrichten")
# Text, ein Werkzeugaufruf, wieder Text: jeder Eintrag traegt eine
# Nachricht. Wuerde der zweite fuer den ganzen Zug einstehen, faellt
# weg, was die erste gesagt hat.
s6 = Sitzung()
s6.vom_bildschirm("Erster Teil, gezeichnet.")
s6.aus_dem_transkript("## Erster Teil, gezeichnet.")
s6.vom_bildschirm("Zweiter Teil nach dem Werkzeug.")
s6.aus_dem_transkript("## Zweiter Teil nach dem Werkzeug.")
nach6 = [c for c in s6.karten if c.get("replaces")]
pruefe(len(nach6) == 2, "jede Nachricht bekommt ihre eigene Nachlieferung",
       f"{len(nach6)} Stueck")
pruefe(nach6 and nach6[0]["replaces"] == [1] and nach6[-1]["replaces"] == [3],
       "und ersetzt nur die eigene Karte",
       str([c.get("replaces") for c in nach6]))

print("Nach einem Neustart der Bruecke")
# Die Bruecke liest ihren Feed zurueck und legt die nachgelieferte Karte
# wieder ab - mit Markdown. Zeigt der Bildschirm denselben Absatz gezeichnet,
# muss sie ihn wiedererkennen. Vorher verglich sie die rohe Fassung (mit ##
# und Backticks) mit der gezeichneten, fand keine Uebereinstimmung und
# schickte den Absatz ein zweites Mal: in der App stand dieselbe Antwort
# zweimal, einmal gesetzt und einmal roh. Gemeldet von Calvin am 25.09.
s7 = Sitzung()
s7.feed_neu_geladen(ANTWORT)
pruefe(s7.schon_gesagt(terminals._plain_md(ANTWORT)),
       "der gezeichnete Absatz wird wiedererkannt")
pruefe(s7.schon_gesagt(ANTWORT), "die rohe Fassung auch")
pruefe(not s7.schon_gesagt("Ein ganz anderer Absatz, lang genug fuer die Pruefung."),
       "ein anderer Absatz dagegen nicht")

# Umgekehrt genauso: erst der Bildschirm, dann die Frage mit Markdown.
s8 = Sitzung()
s8.vom_bildschirm(terminals._plain_md(ANTWORT))
pruefe(s8.schon_gesagt(ANTWORT),
       "und in der anderen Richtung ebenso")

# Kurzes darf zweimal kommen: "Fertig." ist keine Wiederholung.
s9 = Sitzung()
s9.vom_bildschirm("Fertig.")
pruefe(not s9.schon_gesagt("Fertig. Und noch etwas."),
       "kurze Saetze bleiben erlaubt")

print("Eine Nachricht, die der Bildschirm nie gezeigt hat")
# Ein langer Absatz war aus dem sichtbaren Fenster gescrollt, bevor der
# Bildschirm gelesen wurde. Frueher fiel die Nachricht damit ganz weg: die
# Abschrift hatte sie vollstaendig, aber es gab keine Karte zu ersetzen, und
# die Nachlieferung stieg aus. In der App blieb ein Schnipsel vom Ende stehen.
s10 = Sitzung()
s10.transkript_zur_nachricht("msg_4", ANTWORT)
pruefe(len(s10.karten) == 1, "die Nachricht kommt trotzdem an",
       f"{len(s10.karten)} Karten")
pruefe(s10.karten and "```" in s10.karten[0]["text"], "und zwar mit ihrem Markdown")
pruefe(s10.karten and not s10.karten[0].get("replaces"),
       "sie ersetzt nichts, es gab ja nichts")

# Ein laengerer Stand derselben Nachricht ersetzt die nachgereichte Karte,
# statt daneben zu stehen.
s10.transkript_zur_nachricht("msg_4", ANTWORT + "\n\nUnd noch ein Absatz hinterher, lang genug.")
nach10 = [c for c in s10.karten if c.get("replaces")]
pruefe(len(nach10) == 1, "ein laengerer Stand ersetzt sie", f"{len(nach10)} Stueck")
pruefe(nach10 and nach10[0]["replaces"] == [1], "und nennt genau ihre Nummer",
       str(nach10[0].get("replaces")) if nach10 else "keine")

# Was schon gesagt wurde, kommt nicht als zweite Karte zurueck.
s11 = Sitzung()
s11.vom_bildschirm(terminals._plain_md(ANTWORT))
s11.transkript_zur_nachricht("msg_5", ANTWORT)
pruefe(len([c for c in s11.karten if not c.get("replaces")]) == 1,
       "Bekanntes wird nicht noch einmal geschickt",
       f"{len(s11.karten)} Karten")

print("Was die App daraus macht")
# Die App ersetzt nach Kennung: die genannten Karten fallen weg, die neue
# tritt an ihre Stelle. Hier nachgestellt, damit der Zug einmal dasteht.
zuege = []
for c in s.karten:
    if c.get("kind") != "say":
        continue
    ersetzt = set(c.get("replaces") or [])
    if ersetzt:
        zuege = [z for z in zuege if z["seq"] not in ersetzt]
    zuege.append({"seq": c["seq"], "text": c["text"]})

pruefe(len(zuege) == 1, "der Zug steht einmal da", f"{len(zuege)} Zuege")
pruefe(zuege and "```" in zuege[0]["text"], "und zwar der mit dem Markdown")
pruefe(zuege and AUF_DEM_SCHIRM in zuege[0]["text"],
       "der Text vom Bildschirm ist darin enthalten")

print()
print(f"{ok_count} ok, {len(fehler)} fehlgeschlagen")
sys.exit(1 if fehler else 0)
