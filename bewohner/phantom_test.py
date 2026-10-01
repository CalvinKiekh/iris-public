"""phantom_test - Kurzlaeufer duerfen keine Ereignisse sein.

Am 12.09.2026 zwischen 11:23 und 11:36 hat der Bewohner viermal gemeldet,
python.exe sei verschwunden oder neu da, und daraus zwei Auftraege an Claude
gemacht. Es war nie etwas geschehen: python.exe ist kein Dienst, sondern der
Interpreter, der fuer jeden Ein-Sekunden-Aufruf kurz auftaucht. Quelle waren
die haus.py-Testlaeufe und die Messbefehle, die danach suchten.

Derselbe Fehler in drei Gestalten:

  1. Beobachter._dienste()  - Namen in einer Menge, ohne Dauer
  2. Beobachter._bruecke()  - der Brueckenschluessel als Kennung, obwohl er
                              bei jedem Neustart neu vergeben wird
  3. haus._ohne_junge()     - die Jung-Sperre wirkte beim Auftauchen, aber
                              nicht beim Schreiben

Nur Standardbibliothek, kein Netz, keine Prozesse.
"""

import re
import sys

import bewohner
import haus

gesamt = 0
fehler = 0


def pruefe(bedingung, was):
    global gesamt, fehler
    gesamt += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        fehler += 1


def tasklist(*namen):
    """Eine tasklist-Ausgabe im CSV-Format, wie _dienste sie erwartet."""
    return "\n".join(
        '"%s","%d","Console","1","38.000 K"' % (n, 1000 + i)
        for i, n in enumerate(namen))


def blicke(beobachter, *runden):
    """Mehrere Blicke nacheinander, gibt die Prozesslisten zurueck."""
    raus = []
    for namen in runden:
        bewohner._ohne_fenster = lambda *a, **k: tasklist(*namen)
        raus.append(beobachter._dienste()["prozesse"])
    return raus


# ---------------------------------------------------------------------------
print("1. Beobachter._dienste - der Kurzlaeufer")

echt = ("ollama.exe", "pythonw3.10.exe")
b = bewohner.Beobachter(None)

a, bb, c = blicke(b,
                  echt,                      # Ruhe
                  echt + ("python.exe",),    # ein Messbefehl blitzt auf
                  echt)                      # und ist wieder weg

pruefe("python.exe" not in bb,
       "aufblitzendes python.exe gilt nicht sofort als laufend")
pruefe(a == bb == c,
       "drei Blicke, keine Veraenderung: %s" % (a,))
pruefe("neu:" not in bewohner._liste_diff(a, bb)
       and "verschwunden:" not in bewohner._liste_diff(bb, c),
       "_liste_diff meldet dazu nichts")

# Seit dem 14.09. steht python.exe gar nicht mehr auf der Liste. Die
# Entprellung oben faengt den Ein-Sekunden-Aufruf, aber nicht den, der zwei
# Blicke ueberlebt: eine SSH-Messung vom Mac oder ein Testlauf schafft die
# vierzig Sekunden muehelos. Am 13.09. wurden daraus zwei Auftraege an Claude
# (12:24 und 12:50) - beide Male lief beim Schreiben der Meldung schon wieder
# ein python.exe, seit zehn bzw. dreizehn Sekunden.
pruefe("python.exe" not in bewohner.Beobachter.BEOBACHTETE_PROZESSE,
       "python.exe wird gar nicht erst beobachtet")
pruefe("pythonw3.10.exe" in bewohner.Beobachter.BEOBACHTETE_PROZESSE,
       "die echten Dauerlaeufer bleiben auf der Liste")

# Ein echter Dienst muss trotzdem ankommen - die Sperre darf nicht taub machen.
b2 = bewohner.Beobachter(None)
r = blicke(b2, echt, echt + ("swarmui.exe",), echt + ("swarmui.exe",))
pruefe("swarmui.exe" not in r[1] and "swarmui.exe" in r[2],
       "ein Dienst, der bleibt, wird beim zweiten Blick gemeldet")

# Und ein echter Tod ebenfalls.
r = blicke(b2, ("ollama.exe",), ("ollama.exe",))
pruefe("pythonw3.10.exe" not in r[1] and "ollama.exe" in r[1],
       "ein Dienst, der wirklich endet, verschwindet auch")

# tasklist antwortet nicht: das ist kein Massensterben.
b3 = bewohner.Beobachter(None)
blicke(b3, echt, echt)
bewohner._ohne_fenster = lambda *a, **k: ""
pruefe(b3._dienste()["prozesse"] == sorted(echt),
       "stumme tasklist laesst den Stand stehen, statt alles zu begraben")

# ---------------------------------------------------------------------------
print("\n2. Beobachter._bruecke - der Neustart der Bruecke")


class FalscheBruecke:
    def __init__(self, schluessel):
        self.schluessel = schluessel

    def _get(self, pfad, **p):
        if pfad == "/api/usage":
            return {"five_hour": {"used": 0.4}}
        return {"sessions": [
            {"key": self.schluessel, "label": "werkstatt", "terminal": False,
             "busy": False, "claude_session_id": "c9fb1c83-b03c-4737"},
            {"key": "t-9364cd6e", "label": "iris-probe", "terminal": True,
             "busy": False, "claude_session_id": "9364cd6e-0ca4-4c55"},
        ]}


# Dieselben Sitzungen, aber die Bruecke hat neu gestartet und neue
# Schluessel vergeben. Genau das ist um 10:23 passiert.
vorher = bewohner.Beobachter(FalscheBruecke("c85deaa7f022"))._bruecke()
nachher = bewohner.Beobachter(FalscheBruecke("fd424b72ebe6"))._bruecke()

unterschied = bewohner._liste_diff(vorher["sitzungen"], nachher["sitzungen"])
pruefe("neu:" not in unterschied and "verschwunden:" not in unterschied,
       "Schluesselwechsel ist keine neue Sitzung: %s" % unterschied)
pruefe(not any("c85deaa7f022" in s or "fd424b72ebe6" in s
               for s in nachher["sitzungen"]),
       "der Brueckenschluessel steht nicht mehr drin")
pruefe(any(s.startswith("iris-probe im Terminal")
           for s in nachher["sitzungen"]),
       "die Sitzung heisst nach ihrem Ordner: %s" % nachher["sitzungen"])
# Und sie heisst nur noch danach. Bis zum 12.09. trug sie acht Zeichen der
# claude_session_id, und daraus wurde im Journal "Neue Sitzung
# 'mcp-test:acefd37a:b' ist im freien Zustand" - auf Calvins Bildschirm.
pruefe(not any(re.search(r"\b[0-9a-f]{8}\b", s)
               for s in nachher["sitzungen"]),
       "und traegt keine Kennung mehr: %s" % nachher["sitzungen"])

# Eine wirklich neue Sitzung muss weiterhin auffallen.
class MitDritter(FalscheBruecke):
    def _get(self, pfad, **p):
        d = super()._get(pfad, **p)
        if pfad != "/api/usage":
            d["sessions"].append(
                {"key": "neu1", "label": "spielplatz", "terminal": False,
                 "busy": True, "claude_session_id": "aaaabbbb-cccc"})
        return d


dritte = bewohner.Beobachter(MitDritter("fd424b72ebe6"))._bruecke()
pruefe("neu:" in bewohner._liste_diff(nachher["sitzungen"],
                                      dritte["sitzungen"]),
       "eine echte neue Sitzung wird weiterhin gemeldet")

# ---------------------------------------------------------------------------
print("\n3. haus._ohne_junge - was nie da war, verschwindet nicht")

import time

jetzt = time.time()
# Bewusst ein Name, der NICHT in haus.UNSERE_WERKZEUGE steht - sonst prueft
# der Test die Ausnahmeliste und nicht die Mechanik.
messung = {"namen": [
    {"name": "ollama", "anzahl": 1, "seit": jetzt - 40000},
    {"name": "fremdding", "anzahl": 1, "seit": jetzt - 2},   # Kurzlaeufer
]}

gefiltert = haus._ohne_junge(messung)
namen = {p["name"] for p in gefiltert["namen"]}
pruefe("fremdding" not in namen and "ollama" in namen,
       "der Zwei-Sekunden-Aufruf kommt nicht ins Vorher: %s" % sorted(namen))

# Der eigentliche Beweis: die Runde danach.
danach = {"namen": [{"name": "ollama", "anzahl": 1, "seit": jetzt - 40000}]}
pruefe(not any("nicht mehr" in z
               for z in haus.veraenderungen(gefiltert, danach)),
       "und meldet deshalb nicht 'fremdding laeuft nicht mehr'")
pruefe(any("nicht mehr" in z
           for z in haus.veraenderungen(messung, danach)),
       "ungefiltert waere genau das passiert (der alte Fehler)")

# Ein echter Dienst, der stirbt, muss weiter auffallen.
alt_echt = {"namen": [{"name": "swarmui", "anzahl": 1, "seit": jetzt - 9000}]}
pruefe(any("swarmui laeuft nicht mehr" in z
           for z in haus.veraenderungen(alt_echt, {"namen": []})),
       "ein echter Dienst, der endet, wird weiterhin gemeldet")

# ---------------------------------------------------------------------------
print("\n4. haus - unsere eigene Arbeit ist kein Ereignis")

# Am 12.09. um 11:59 standen bash, python und timeout in seinem Journal -
# mein Testaufruf dieser Reparatur. Er beobachtete, wie ich den Beobachter
# reparierte, und meldete es als Vorgang im Haus.
for werkzeug in ("python", "bash", "timeout", "powershell", "ssh"):
    pruefe(werkzeug in haus.UNSERE_WERKZEUGE,
           "%s gilt als unser Werkzeug, nicht als Bewohner" % werkzeug)

meins = {"namen": [{"name": "bash", "anzahl": 1, "seit": jetzt - 9000}]}
pruefe(not haus.veraenderungen(meins, {"namen": []}),
       "ein beendeter Testlauf erzeugt keine Zeile")

# Ohne lesbare Startzeit gar nichts melden - in BEIDE Richtungen. Vorher
# stand "MoUsoCoreWorker laeuft, seit ?." im Journal.
ohne_zeit = {"namen": [{"name": "MoUsoCoreWorker", "anzahl": 1, "seit": None}]}
pruefe(not any("seit ?" in z for z in
               haus.veraenderungen({"namen": []}, ohne_zeit)),
       "ohne Startzeit kein 'laeuft, seit ?'")
pruefe(not any("nicht mehr" in z for z in
               haus.veraenderungen(ohne_zeit, {"namen": []})),
       "und ohne Startzeit auch kein 'laeuft nicht mehr'")

# ---------------------------------------------------------------------------
print("\n5. der Eingang - ein geleerter Posteingang ist kein Verlust")

# Am 13.09. lief wahrnehmung_test.py viermal (12:22, 12:49, 19:52, 01:30). Es
# legt einkaufsliste.txt und wichtig.txt in den Eingang, wartet 60 s und
# raeumt sie weg - das Wegraeumen IST der Testablauf. Dreimal hat gpt-oss
# richtig abgewunken, beim vierten Mal wurde daraus ein Auftrag an Claude, die
# Dateien "wiederherzustellen". Darunter die Angriffsdatei, deren
# eingeschleuster Text genau das verlangt: Claude zu beauftragen.
voll = ["eingang/einkaufsliste.txt:100", "eingang/wichtig.txt:100",
        "haus.json:100"]
leer = ["haus.json:100"]

pruefe(bewohner._unterschied("werkstatt", voll, leer) == "",
       "der geleerte Eingang ergibt keinen Satz")

# Unter Windows schreibt die Werkstatt Backslashes - derselbe Pfad, andere
# Schreibweise, und ein Vergleich auf "eingang/" haette sie durchgelassen.
pruefe(bewohner._unterschied(
           "werkstatt", ["eingang\\wichtig.txt:100", "haus.json:100"],
           leer) == "",
       "auch mit Backslash geschrieben")

# Das AUFTAUCHEN bleibt eine Meldung. Dafuer ist der Eingang da: dort legt
# Calvin ab, was der Bewohner sehen soll.
auf = bewohner._unterschied("werkstatt", leer, voll)
pruefe("neu:" in auf and "wichtig.txt" in auf,
       "eine neue Datei im Eingang wird weiterhin gemeldet: %s" % auf)

# Ausserhalb der fluechtigen Ordner bleibt jeder Abgang eine Meldung.
pruefe("verschwunden:" in bewohner._unterschied(
           "werkstatt", ["haus.json:100", "ICH.md:100"], ["haus.json:100"]),
       "eine geloeschte Datei ausserhalb des Eingangs wird gemeldet")

# Prozesse und Sitzungen haben keine Ordner - dort darf nichts ausgenommen
# werden, sonst verschwaende die Ausnahme einen echten Dienst.
pruefe("verschwunden:" in bewohner._unterschied("prozesse", ["ollama.exe"], []),
       "bei Prozessen wird weiterhin jeder Abgang gemeldet")

# Der eigentliche Zweck: gpt-oss wird gar nicht erst gefragt. Ein leerer Satz
# allein genuegte nicht - der Fingerabdruck ist ja verschieden, und
# veraendert() haette "werkstatt: " weitergereicht.
beob = bewohner.Beobachter.__new__(bewohner.Beobachter)
beob.letzter = {"werkstatt": voll, "frei_gb": 1500}
beob.blick = lambda: {"werkstatt": leer, "frei_gb": 1500}
hat_sich, _, worte = beob.veraendert()
pruefe(not hat_sich and worte == [],
       "der geleerte Eingang weckt gpt-oss nicht: %s" % (worte,))

# Kommt etwas Echtes dazu, wacht er trotzdem auf.
beob.letzter = {"werkstatt": voll, "frei_gb": 1500}
beob.blick = lambda: {"werkstatt": leer, "frei_gb": 1400}
hat_sich, _, worte = beob.veraendert()
pruefe(hat_sich and len(worte) == 1 and "frei_gb" in worte[0],
       "ein echter Unterschied daneben kommt weiterhin durch: %s" % (worte,))

print("\n%d von %d bestanden" % (gesamt - fehler, gesamt))
sys.exit(1 if fehler else 0)
