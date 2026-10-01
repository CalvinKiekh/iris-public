"""Sieht er seine Fähigkeiten, und darf er selbst zugreifen?

    python -X utf8 werkzeug_test.py

Der Befund, der dazu geführt hat: Er hatte zehn geprüfte Werkzeuge und
siebzehn Fähigkeiten, und keine davon kam in seinem Kopf vor. ZUSTAENDIGKEIT
nannte kein einziges Werkzeug - das einzige Vorkommen war ein Verbot. Was er
bei jedem Durchgang sah, war {veraendert, lage, offene_aufgabe,
anweisungen_von_calvin}. Und seine einzige Handlungsform war: EINEN Auftrag an
Claude formulieren. Im ganzen Journal stand keine Zeile über einen
Werkzeugaufruf; es gab nicht einmal eine Art dafür.

Deshalb wünschte er sich Dinge, die er längst hatte. Das war kein Denkfehler
von ihm - er konnte es nicht wissen.

Kein Ollama nötig: Ob das Modell gut wählt, steht hier nicht zur Prüfung.
Geprüft wird, dass es ihm vorliegt und dass der Griff ankommt.
"""
from einstellungen import NUTZER
import json
import sys
import time
from pathlib import Path

import pruefstand
pruefstand.braucht_bewohner("werkzeuge.json")

sys.path.insert(0, str(Path(__file__).parent))
import bewohner as B

ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}" + (f"  [{dazu}]" if dazu else ""))


print("Er sieht, was er kann:")
kann = B.was_ich_kann()
roh = json.dumps(kann, ensure_ascii=False)
werkzeuge = kann["werkzeuge_zum_aufrufen"]
eingebaut = kann["in_mir_eingebaut"]
pruefen("die zehn Werkzeuge stehen drin", len(werkzeuge) == 10, str(len(werkzeuge)))
pruefen("das Eingebaute auch", len(eingebaut) >= 15, str(len(eingebaut)))
pruefen("vollständig, nichts abgeschnitten", "… und weitere" not in eingebaut)
pruefen(f"hält das Prompt-Maß ({len(roh)})", len(roh) <= B.KANN_ZEICHEN_MAX)
pruefen("jede Zeile trägt Name und Zweck",
        all(": " in z for z in werkzeuge))
# Der Name muss WOERTLICH aufrufbar sein - danach greift er.
import werkzeuge as W
echte = set(W.verzeichnis_lesen())
pruefen("die Namen sind die echten, nicht umbenannt",
        {z.split(":")[0] for z in werkzeuge} == echte)
pruefen("kein Beleg und kein Aufruf im Blick - das wäre Prompt ohne Nutzen",
        "geprueft" not in roh and "python werkzeuge/" not in roh)

print("\nDie Liste liegt beim Denken vor:")
# Nicht der Blick allein - der ganze Text, den er bekommt.
lage = {"veraendert": ["x"], "lage": {}, "offene_aufgabe": None,
        "was_ich_kann": B.was_ich_kann(), f"anweisungen_von_{NUTZER}": []}
pruefen("was_ich_kann steht im Blick", "was_ich_kann" in lage)
pruefen("und übersteht die 6000-Zeichen-Grenze des Blicks",
        "platzverlauf" in json.dumps(lage, ensure_ascii=False)[:6000])
pruefen("der Systemtext nennt die vierte Form", '"selbst"' in B.ZUSTAENDIGKEIT)
pruefen("und sagt, dass sie zuerst geprüft wird",
        "SIEH ZUERST NACH" in B.ZUSTAENDIGKEIT)
pruefen("und dass ein Werkzeug kein Eingriff ist",
        "kein Eingriff ins System" in B.ZUSTAENDIGKEIT)

print("\nDer Griff landet im Journal:")
zeilen = []
B.journal, echt_journal = (lambda k, t, **e: zeilen.append((k, t, e))), B.journal
try:
    gelungen = B.werkzeug_benutzen("platzverlauf", "Platz auf C gefallen")
    unbekannt = B.werkzeug_benutzen("bestellwerkzeug", "gibt es nicht")
finally:
    B.journal = echt_journal

pruefen("ein Aufruf schreibt genau eine Zeile", len(zeilen) == 2)
art, text, extra = zeilen[0]
pruefen("die Art heißt werkzeug", art == "werkzeug", art)
pruefen("der Name steht dabei", extra.get("werkzeug") == "platzverlauf")
pruefen("der Anlass auch - warum ist später mehr wert als was",
        extra.get("anlass") == "Platz auf C gefallen")
pruefen("und das Ergebnis", len(text) > len("platzverlauf: "), text[:60])
pruefen("gelungen wird vermerkt", extra.get("gelungen") is gelungen)

art2, text2, extra2 = zeilen[1]
pruefen("ein erfundenes Werkzeug läuft NICHT", not unbekannt)
pruefen("wird aber trotzdem geschrieben, nicht verschluckt",
        art2 == "werkzeug" and "nicht im Verzeichnis" in text2)

print("\nDer Rückblick und das Gedächtnis kennen die neue Art:")
import rueckblick as R
pruefen("der Rückblick erzählt von Werkzeugen", "werkzeug" in R.ERZAEHLT)
pruefen("und sie ist es wert, erinnert zu werden",
        "werkzeug" in B.GEDAECHTNIS_ARTEN)

print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
