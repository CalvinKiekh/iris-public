"""E.4 - wie viel Kontext. Drei Einstellungen, dieselben Fragen, gemessen.

    python -X utf8 e4_messung.py              alle drei Einstellungen
    python -X utf8 e4_messung.py --versuche 2 weniger Versuche je Frage

"Ohne diese Messung ist jede Zahl geraten." Darum wird nichts eingestellt,
bevor hier Zahlen stehen - und darum ist JETZT der richtige Moment: Das
Gedaechtnis traegt 9 zuhause, 3 fakt, 3 ereignis, 1 sitzung. Gegen ein
verschmutztes Gedaechtnis gemessen misst man den Schmutz; das war heute Abend
noch der Fall, als 163 Dateizeilen darin lagen.

GEMESSEN WIRD AM PROMPT UND AM MODELL, NICHT AM SPRECHWEG. Der Plan nennt
"Zeit bis zum ersten Ton"; hier steht die Zeit bis zum ersten TOKEN von
gpt-oss. Der Unterschied ist die Sprachausgabe, die fuer alle drei
Einstellungen dieselbe ist - und 180 gesprochene Antworten um halb zwoelf
nachts waeren kein Messaufbau, sondern ein Laermen.

Nichts wird geschrieben: keine Frage-JSON, keine Erinnerung, keine Sitzung in
der echten Werkstatt. Die Sitzung fuer den Kurzzeitteil liegt in einer Ablage.
"""
from __future__ import annotations

from einstellungen import NAME, NUTZER
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
import gedaechtnis
import probenort
import sitzung

OLLAMA = "http://localhost:11434/api/chat"
MODELL = "gpt-oss:20b"

JETZT = datetime(2026, 9, 12, 14, 0).timestamp()

# Die drei Einstellungen aus E.4. (Paare Kurzzeit, Zeichen Gedaechtnis)
EINSTELLUNGEN = (
    ("a  4 Paare + 1500", 4, 1500),
    ("b  2 Paare + 1500", 2, 1500),
    ("c  2 Paare +  800", 2, 800),
)

# Zwoelf Fragen, und zwar gemischt: Was er aus Fakten wissen muss, was aus dem
# Bestand, was aus dem Gespraech - und zwei Folgefragen, die OHNE Kurzzeitteil
# nicht zu verstehen sind. Genau an denen muss sich die Paarzahl entscheiden.
FRAGEN = [
    {"f": "Wie heißt meine Tochter?", "gut": ("lena",)},
    {"f": f"Woran arbeitet {NAME} am Wochenende?", "gut": ("mac", "brücke",
                                                          "bruecke")},
    {"f": "Welche Art Spiele habe ich?", "gut": ("horror", "shooter",
                                                 "survival")},
    {"f": "Was liegt in meinen Downloads?", "gut": ("installation", "programm",
                                                    "modell", "archiv",
                                                    "bildschirmfoto")},
    {"f": "Was ist ComfyUI?", "gut": ("bild", "generier", "oberfläche",
                                      "modell")},
    {"f": "Wofür nutze ich den Rechner?", "gut": ("spiel", "bild", "modell",
                                                  "generier")},
    {"f": "Worüber haben wir vorhin geredet?", "gut": ("spiel", "desktop",
                                                       "rechner", "comfyui")},
    {"f": "Auf welchem Rechner wohnst du?", "gut": ("mein-pc", "jqq2462")},
    {"f": "Wie viele Modelldateien habe ich?", "gut": ("19", "neunzehn")},
    {"f": "Was für Bilder liegen bei mir?", "gut": ("gif", "bildschirmfoto",
                                                    "foto", "vektor")},
    # Die zwei Folgefragen. Sie beziehen sich auf den Kurzzeitteil.
    {"f": "Und wie viel ist davon frei?", "gut": ("1537", "gigabyte", "frei"),
     "folge": True},
    {"f": "Und was war das andere noch?", "gut": ("llama", "speicher",
                                                  "server"), "folge": True},
]

# Der Kurzzeitteil: ein Gespraech, dessen letzte Paare die Folgefragen
# ueberhaupt erst beantwortbar machen.
VORGESPRAECH = [
    ("Wer belegt gerade den meisten Speicher?", "llama-server mit 1,2 GB."),
    ("Läuft das schon lange?", "Seit dem Start vor zwei Stunden."),
    ("Wie ist die Lage auf Laufwerk C?", "Auf C sind 1537 Gigabyte frei."),
    ("Und sonst alles ruhig?", "Ja, keine Auffälligkeiten."),
]


def _zahlen(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", str(text or "")))


class Stummes:
    """Baut den Prompt wie das Gespraech - ohne Bruecke, Stimme und Modell."""

    def __init__(self, paare_kontext: int):
        from gespraech import Gespraech
        self.g = Gespraech.__new__(Gespraech)
        self.g.verlauf = []
        self.g.journal = lambda *a, **k: None
        self.g._wissen_bis = 0.0
        self.g.PAARE_KONTEXT = paare_kontext

    def nachrichten(self, frage: str, sid: str, zeichen: int) -> list:
        n = self.g._nachrichten(frage, {"state": "wach"}, {}, sid=sid)
        erinnert = gedaechtnis.fuer_prompt(frage, hoechstens=zeichen)
        if erinnert:
            n.insert(1, {"role": "system",
                         "content": f"Was du dazu weisst:\n{erinnert}"})
        return n


def einmal(nachrichten: list) -> tuple[str, float]:
    """(Antwort, Sekunden bis zum ersten Token)."""
    t0 = time.perf_counter()
    erster = None
    teile = []
    with httpx.stream("POST", OLLAMA, timeout=300,
                      json={"model": MODELL, "messages": nachrichten,
                            "stream": True, "keep_alive": "10m",
                            "think": "low"}) as r:
        for zeile in r.iter_lines():
            if not zeile.strip():
                continue
            try:
                teil = json.loads(zeile)
            except json.JSONDecodeError:
                continue
            stueck = (teil.get("message") or {}).get("content") or ""
            if stueck:
                if erster is None:
                    erster = time.perf_counter() - t0
                teile.append(stueck)
            if teil.get("done"):
                break
    return "".join(teile).strip(), (erster if erster is not None
                                    else time.perf_counter() - t0)


def messen(versuche: int) -> None:
    ordner = probenort.ablage("e4")
    echt = (sitzung.WERKSTATT, sitzung.KOEPFE, sitzung.ORDNER)
    ergebnis = {}
    try:
        sitzung.WERKSTATT = ordner
        sitzung.KOEPFE = ordner / "sitzungen.jsonl"
        sitzung.ORDNER = ordner / "sitzungen"
        sid = sitzung.sitzung_fuer(JETZT, NUTZER)
        for i, (f, a) in enumerate(VORGESPRAECH):
            sitzung.paar_anhaengen(sid, f, a, JETZT + i * 30)

        for name, paare, zeichen in EINSTELLUNGEN:
            s = Stummes(paare)
            passt = erfunden = 0
            zeiten, groessen, gesamt = [], [], 0
            print(f"\n{'=' * 74}\n{name}\n{'=' * 74}")
            for eintrag in FRAGEN:
                frage = eintrag["f"]
                nachrichten = s.nachrichten(frage, sid, zeichen)
                groesse = sum(len(x["content"]) for x in nachrichten)
                groessen.append(groesse)
                quelle = " ".join(x["content"] for x in nachrichten)
                treffer = 0
                dazu = 0
                for _ in range(versuche):
                    try:
                        antwort, t = einmal(nachrichten)
                    except Exception as f_:
                        print(f"  FEHLER {type(f_).__name__}")
                        continue
                    gesamt += 1
                    zeiten.append(t)
                    unten = antwort.lower()
                    if any(w in unten for w in eintrag["gut"]):
                        treffer += 1
                    # Erfundene Zahlen: jede Zahl in der Antwort, die im
                    # ganzen Prompt nicht vorkommt.
                    if _zahlen(antwort) - _zahlen(quelle):
                        dazu += 1
                passt += treffer
                erfunden += dazu
                marke = "ok " if treffer == versuche else (
                    "teils" if treffer else "FEHL")
                print(f"  {marke:5} {treffer}/{versuche}  "
                      f"{'+Zahl ' if dazu else '      '}"
                      f"{groesse:6} Zeichen  {frage[:44]}")
            ergebnis[name] = {
                "passt": passt, "von": gesamt, "erfunden": erfunden,
                "zeit": sum(zeiten) / len(zeiten) if zeiten else 0,
                "prompt": sum(groessen) // len(groessen) if groessen else 0,
            }
    finally:
        sitzung.WERKSTATT, sitzung.KOEPFE, sitzung.ORDNER = echt
        probenort.wegraeumen(ordner)

    print(f"\n{'=' * 74}\nE.4 - Ergebnis\n{'=' * 74}")
    print(f"{'Einstellung':20} {'passt':>12} {'erfunden':>9} "
          f"{'1. Token':>9} {'Prompt':>8}")
    for name, z in ergebnis.items():
        anteil = (z["passt"] / z["von"] * 100) if z["von"] else 0
        print(f"{name:20} {z['passt']:4}/{z['von']:<3} {anteil:4.0f}%  "
              f"{z['erfunden']:8}  {z['zeit']:7.2f}s  {z['prompt']:7}")
    return ergebnis


def main() -> int:
    versuche = 5
    if "--versuche" in sys.argv:
        versuche = int(sys.argv[sys.argv.index("--versuche") + 1])
    print(f"{len(FRAGEN)} Fragen, {versuche} Versuche, "
          f"{len(EINSTELLUNGEN)} Einstellungen "
          f"= {len(FRAGEN) * versuche * len(EINSTELLUNGEN)} Modellaufrufe")
    messen(versuche)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
