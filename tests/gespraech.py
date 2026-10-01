"""Die Gespraechspruefung: stellt dem Bewohner die Fragen, die Calvin stellt,
und bewertet die Antworten nach den Fehlern, die er am 12.09. selbst gefunden
hat - damit sie das naechste Mal hier auffallen und nicht auf seinem Telefon.

    python3 tests/gespraech.py              gegen den PC
    python3 tests/gespraech.py --schnell    nur die Haelfte der Fragen

Geprueft wird je Antwort:
  - passt sie zur Frage (eine Zeitfrage will eine Uhrzeit, keine Kerne)
  - Wortbrueche aus dem Satzschnitt ("beob achtet", "1202 Mi" + "B geteilt")
  - Platzhalter, die nie herausgehen duerfen ("Geraet X", "seit ?")
  - Kennungen statt Sachen ("a-1789201052"), ISO-Zeitstempel
  - vorgelesene Form: Doppelpunkt am Ende, Aufzaehlung, Ueberlaenge
  - Maschinentexte, die als Antwort nichts verloren haben

Fachbegriffe gelten NICHT als Fehler - Calvin versteht sie und will sie.
Was zaehlt, ist die gesprochene Form: eine Adresse oder ein Fehlername klingt
vorgelesen sinnlos, auch wenn er ihn liest.
"""
import argparse, json, re, sys, time, urllib.error, urllib.request

# Jede Probe: die Frage, und woran man erkennt, dass die Antwort dazu passt.
PROBEN = [
    ("Wie spät ist es?",            r"\d{1,2}[:.]\d{2}|\bUhr\b",     "eine Uhrzeit"),
    ("Welcher Tag ist heute?",      r"Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag",
                                                                      "ein Wochentag"),
    ("Wie viel Arbeitsspeicher ist frei?", r"\d+[.,]?\d*\s*(GB|Gigabyte)", "eine Speichergroesse"),
    ("Wie lange läuft der Rechner schon?", r"\b(Tag|Tagen|Stunde|Stunden|Minute)\b", "eine Dauer"),
    ("Was ist letzte Nacht passiert?", r"\d{1,2}:\d{2}|heute nacht|in der nacht", "etwas aus der Nacht"),
    # Kein \w+ mehr: "Keine Geraete." erfuellte das und ging als Auskunft durch,
    # waehrend netz.py vierzehn Geraete fand (12.09.). Verlangt wird ein Name
    # oder eine Anzahl - eine Fehlanzeige muss auffallen, nicht bestehen.
    ("Wer ist im Heimnetz?",        r"\d+\s*(Ger[äa]te?|St[üu]ck)|fritz|iPhone|Mac|repeater|"
                                    r"\b(zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|elf|"
                                    r"zwölf|dreizehn|vierzehn)\b",
                                                                      "Geräte oder eine Anzahl"),
    ("Was kannst du?",              r"\b(kann|merke|sehe|lese|höre|melde)\b", "etwas, das er kann"),
    ("Wie geht es dir?",            r"\b(gut|ruhig|wach|müde|bereit|nichts)\b", "eine Befindlichkeit"),
    ("Wie heißt meine Tochter?",    r"Lena|Marie",                       "der Name der Tochter"),
    ("Wer belegt den meisten Speicher?", r"\b\w+\b",                   "ein Programm"),
    ("Schnurpsel wrgl bitte?",      r"verstehe.{0,20}nicht|nicht verstanden|noch einmal|"
                                    r"wiederhol|präziser|genauer|meinst du",
                                                                       "eine Rueckfrage"),
]

# Was in einer Antwort nie stehen darf, mit dem Namen des Fehlers.
VERBOTEN = [
    (r"Gerät X|Geraet X|\bGerät Y\b",        "Platzhalter statt Gegenstand"),
    (r"seit \?|,\s*\?\.",                     "Fragezeichen als Platzhalter"),
    (r"\b[a-z]-\d{10,}",                      "Kennung statt Sache"),
    (r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}",        "Maschinenzeitstempel"),
    (r":\s*$",                                "endet auf Doppelpunkt"),
    (r"\b(unterbrochen|zweiter Versuch|Antwort unlesbar|Warmlauf)\b",
                                              "Maschinentext als Antwort"),
]


def hole(basis, token, pfad, last=None, sekunden=90):
    daten = json.dumps(last).encode() if last is not None else None
    r = urllib.request.Request(basis + pfad, data=daten,
                               headers={"Authorization": "Bearer " + token,
                                        "Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=sekunden) as f:
        return json.load(f)


def teile_der_antwort(basis, token, gid):
    """Die Sprechteile einer Antwort, in der Reihenfolge - daran zeigen sich
    die Wortbrueche, die im zusammengesetzten Text unsichtbar sind."""
    strom = hole(basis, token, "/api/resident?_=%d" % time.time())
    return [e for e in (strom.get("resident") or {}).get("waiting", []) if e]


# Woerter, an denen ein Teil enden DARF: zusammengesetzt ergeben sie Deutsch.
# Ohne diese Ausnahme meldet die Probe jede Teilung an einer Wortgrenze als
# Bruch - "beschreibe in" + "einem Satz" ist keiner, "beob" + "achtet" schon.
_KLEINE_WOERTER = {
    "in", "im", "an", "am", "auf", "aus", "bei", "bis", "das", "dem", "den",
    "der", "des", "die", "ein", "eine", "einem", "einen", "einer", "für",
    "hat", "ist", "mit", "nach", "seit", "und", "von", "vom", "vor", "was",
    "wer", "wie", "wo", "zu", "zum", "zur", "über", "unter", "als", "auch",
}


def wortbruch(teile):
    """Endet ein Teil MITTEN IM WORT und laeuft der naechste klein weiter?

    Nicht jede Teilung an einer Wortgrenze ist ein Bruch: Der Bewohner
    schneidet in Sprechteile, und "... beschreibe in" + "einem Satz" ergibt
    zusammengesetzt korrektes Deutsch. Gemeldet wird nur, wenn das letzte
    Stueck des einen Teils kein Wort ist, das fuer sich stehen kann -
    "beob" + "achtet" ist der Fall, um den es geht.
    """
    for a, b in zip(teile, teile[1:]):
        if not a or not b:
            continue
        if not (a[-1].isalnum() and b[0].isalnum() and b[0].islower()):
            continue
        letztes = a.split()[-1].strip(".,;:!?").lower() if a.split() else ""
        # Ein vollstaendiges Wort am Ende ist in Ordnung; ein Bruchstueck nicht.
        if letztes in _KLEINE_WOERTER or len(letztes) > 3:
            continue
        return f"{a[-12:]!r} + {b[:12]!r}"
    return None


def pruefe_antwort(frage, antwort, erwartet, was):
    """Gibt die Liste der Maengel zurueck - leer heisst sauber."""
    maengel = []
    if not antwort.strip():
        return ["keine Antwort"]
    if not re.search(erwartet, antwort, re.IGNORECASE):
        maengel.append(f"passt nicht zur Frage (erwartet: {was})")
    for rx, name in VERBOTEN:
        if re.search(rx, antwort):
            maengel.append(name)
    # Vorgelesen: Saetze unter zwoelf Woertern, keine langen Aufzaehlungen.
    for satz in re.split(r"(?<=[.!?])\s+", antwort):
        if len(satz.split()) > 16:
            maengel.append(f"Satz zu lang ({len(satz.split())} Wörter)")
            break
    if antwort.count(",") >= 5:
        maengel.append("Aufzählung statt Satz")
    if re.search(r"\b\w+\s+\w{1,3}\b(?=[,.]|$)", antwort) and "  " in antwort:
        maengel.append("verdächtige Wortlücke")
    return maengel


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=None, help="Bruecke des PCs, sonst IRIS_PC_URL aus rechner.env")
    p.add_argument("--token", default="")
    p.add_argument("--schnell", action="store_true")
    p.add_argument("--warten", type=int, default=22, help="Sekunden je Antwort")
    a = p.parse_args()
    try:
        from tests.rechner import brauche
    except ImportError:
        from rechner import brauche
    a.url = a.url or brauche("IRIS_PC_URL", "die Adresse der Bruecke des PCs")
    token = a.token or __import__("os").environ.get("PC_TOKEN", "")
    if not token:
        print("Kein Token - PC_TOKEN setzen oder --token geben.")
        return 2

    proben = PROBEN[::2] if a.schnell else PROBEN
    seit = time.time()
    gestellt = []
    print(f"{len(proben)} Fragen, {a.warten} s Bedenkzeit je Antwort\n")

    for frage, erwartet, was in proben:
        try:
            hole(a.url, token, "/api/resident/talk", {"text": frage})
        except Exception as e:                                  # noqa: BLE001
            print(f"  {frage!r}: nicht zugestellt ({type(e).__name__})")
            continue
        gestellt.append((frage, erwartet, was))
        time.sleep(a.warten)
    # Nach der LETZTEN Frage noch einmal warten: sonst wird das Journal
    # gelesen, bevor die letzte Antwort darin steht, und die Probe meldet
    # "keine Antwort" fuer eine Antwort, die es gibt. Am 12.09. ist genau das
    # bei "Schnurpsel wrgl bitte?" passiert - und die Antwort war schlecht,
    # was ohne diese Zeile unbemerkt geblieben waere.
    if gestellt:
        time.sleep(a.warten)

    # Die Antworten stehen im Journal auf dem PC, mit ihrer Frage davor. Die
    # Bruecke hat dafuer keine Route - fuer eine Pruefung ist der direkte Weg
    # ohnehin ehrlicher: gelesen wird, was wirklich dort steht.
    import subprocess
    # PowerShell schickt nicht von sich aus UTF-8; ohne die erste Zeile kommen
    # Umlaute als kaputte Bytes an und das Auslesen bricht ab.
    # -Encoding UTF8 ist NICHT optional: ohne das liest Get-Content die Datei
    # als CP1252 und gibt sie als UTF-8 wieder aus - doppelt kodiert. Der
    # Abgleich ueber den Fragetext scheitert dann an genau den Fragen mit
    # Umlaut ("Wie spaet ist es?"), und der Pruefstand meldet "keine Antwort",
    # wo eine steht. Gemessen am 12.09.: drei von elf, alle mit Umlaut.
    befehl = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
              "Get-Content -Encoding UTF8 "
              "\"$env:USERPROFILE\\mcp-test\\werkstatt\\journal.jsonl\" -Tail 400")
    roh = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", brauche("IRIS_PC", "der SSH-Name des PCs"), befehl],
        capture_output=True, timeout=120).stdout.decode("utf-8", "replace")
    zeilen = []
    for z in roh.splitlines():
        try:
            zeilen.append(json.loads(z))
        except ValueError:
            pass

    # Frage, Antwort und die Sprechteile gehoeren zusammen. Die antwort-Zeile
    # traegt nur den ERSTEN Teil (Befund vom 12.09.) - wer nur sie liest,
    # meldet "keine Antwort", wo eine steht. Also aus beidem zusammensetzen.
    fragen, antworten, teile = {}, {}, {}
    for z in zeilen:
        if z.get("ts", 0) < seit:
            continue
        gid = z.get("id")
        if z.get("kind") == "frage" and gid:
            fragen[gid] = z.get("text") or ""
        elif z.get("kind") == "antwort" and gid:
            antworten[gid] = z.get("text") or ""
        elif z.get("kind") == "stimme" and gid and z.get("part") is not None:
            teile.setdefault(gid, []).append((z.get("part") or 0, z.get("text") or ""))

    # Seit a7e41fd und dd10660 traegt die antwort-Zeile den vollen Text. Die
    # Sprechteile werden hier NICHT mehr zusammengesetzt: Wer das tut, repariert
    # die Wortbrueche im Pruefstand und misst danach seine eigene Kruecke statt
    # der Reparatur. Fehlt die Antwort, soll das auffallen.
    paare, brueche = {}, {}
    for gid, frage in fragen.items():
        paare[frage] = antworten.get(gid, "")
        stuecke = [t for _, t in sorted(teile.get(gid, []))]
        bruch = wortbruch(stuecke)
        if bruch:
            brueche[frage] = bruch

    schlecht = 0
    for frage, erwartet, was in gestellt:
        antwort = paare.get(frage, "")
        maengel = pruefe_antwort(frage, antwort, erwartet, was)
        if frage in brueche:
            maengel.append(f"Wortbruch zwischen Sprechteilen: {brueche[frage]}")
        zeichen = "ok  " if not maengel else "FEHL"
        print(f"  {zeichen} {frage}")
        print(f"       {antwort[:150] or '(nichts)'}")
        for m in maengel:
            print(f"       -> {m}")
        if maengel:
            schlecht += 1

    print(f"\n{len(gestellt) - schlecht} von {len(gestellt)} sauber")
    return 1 if schlecht else 0


if __name__ == "__main__":
    sys.exit(main())
