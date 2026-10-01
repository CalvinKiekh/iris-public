"""Eine saubere Kopie von iris zum Weitergeben - ohne Verlauf, ohne ein Leben.

    python3 tools/uebergabe.py [ziel]        Vorgabe: ../iris-uebergabe

Warum eine erzeugte Kopie und nicht das Repo: im Verlauf steht alles, was je
eingecheckt war - auch das Gedaechtnis des Bewohners, das seit dem 12.09.2026
als Sicherung mitlaeuft. Geloeschte Dateien bleiben dort lesbar. Weitergegeben
wird darum nur der Dateistand von HEAD, und aus dem:

1. Weggelassen, was nicht iris ist, sondern jemandes Leben (WEG unten).
2. Geschwaerzt, was in Texten steht: Namen, Adressen, Geraete - aus
   `schwaerzen.json` in der Wurzel. Die Datei ist nicht im Git, und das ist
   der Punkt: eine Liste mit dem Namen eines Kindes darf nicht in genau der
   Kopie landen, aus der sie ihn entfernen soll. Vorlage:
   schwaerzen.beispiel.json.
3. Berichtet, was danach noch an Persoenlichem uebrig ist - zum Durchsehen,
   bevor die Kopie irgendwohin geht. Das Skript entscheidet das nicht allein.
"""
import json
import os
import re
import subprocess
import sys
import tarfile
import io

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Nicht iris, sondern Aufzeichnungen aus einem Leben: das Gedaechtnis des
# Bewohners und seine Gespraeche, sein Selbstbild, seine Notizen, die
# Entwicklungstagebuecher mit Zuhause und Familie, und die persoenliche
# Arbeitsweise fuer Claude in diesem Repo.
WEG = [
    "bewohner/sicherung",
    "bewohner/selbst",
    "bewohner/docs",
    "docs/BEFUNDE.md",
    "docs/PLAN.md",
    ".claude",
]

# Erzeugte Entwurfs-Buendel: je rund 2,5 MB, fast gleich, mit eingebetteten
# Schriften - zusammen mehr als die Haelfte des Archivs. Gebaut wird aus
# design/ nichts; der Code nennt die kleinen Quellen (*.dc.html) nur als
# Herkunft eines Entwurfs, und die bleiben drin.
WEG_MUSTER = ["design/iris-*.html", "design/*/iris-*.html"]

BINAER = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".icns", ".car", ".ttf", ".otf",
          ".woff", ".woff2", ".db", ".sqlite", ".wav", ".mp3", ".m4a", ".pdf", ".zip")


def main():
    ziel = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(WURZEL, "..", "iris-uebergabe"))
    if os.path.exists(ziel):
        sys.exit(f"{ziel} gibt es schon - erst loeschen oder ein anderes Ziel nennen.")
    try:
        ersetzen = json.load(open(os.path.join(WURZEL, "schwaerzen.json"), encoding="utf-8"))
    except FileNotFoundError:
        sys.exit("schwaerzen.json fehlt - Vorlage: schwaerzen.beispiel.json. Ohne sie wuerde "
                 "nichts geschwaerzt, und das soll nicht aus Versehen passieren.")

    # 0. Nur eingecheckte Dateien, nur ihr Stand - kein .git, kein Verlauf.
    offen = subprocess.run(["git", "status", "--porcelain"], cwd=WURZEL, capture_output=True, text=True).stdout
    if offen.strip():
        print("Hinweis: nicht eingecheckte Aenderungen gehen NICHT mit - es zaehlt HEAD.")
    roh = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=WURZEL, capture_output=True, check=True).stdout
    os.makedirs(ziel)
    with tarfile.open(fileobj=io.BytesIO(roh)) as tar:
        tar.extractall(ziel, filter="data")

    # 1. Weglassen.
    import glob
    for muster in WEG_MUSTER:
        for p in glob.glob(os.path.join(ziel, muster)):
            os.remove(p)
    for weg in WEG:
        p = os.path.join(ziel, weg)
        if os.path.isdir(p):
            subprocess.run(["rm", "-rf", p], check=True)
        elif os.path.exists(p):
            os.remove(p)

    # 2. Schwaerzen. Laengere Ausdruecke zuerst, damit ein Genitiv nicht als Name + "s" zerfaellt.
    regeln = [(re.compile(r"(?<![\w.])" + re.escape(alt) + r"(?![\w])"), neu)
              for alt, neu in sorted(ersetzen.get("ersetzen", {}).items(), key=lambda x: -len(x[0]))]
    geaendert = 0
    for d, _, fs in os.walk(ziel):
        for f in fs:
            if f.lower().endswith(BINAER):
                continue
            p = os.path.join(d, f)
            try:
                t = open(p, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            neu = t
            for muster, ersatz in regeln:
                neu = muster.sub(ersatz, neu)
            if neu != t:
                open(p, "w", encoding="utf-8").write(neu)
                geaendert += 1

    # 3. Berichten.
    melden = [re.compile(m, re.I) for m in ersetzen.get("melden", [])]
    rest = {}
    for d, _, fs in os.walk(ziel):
        for f in fs:
            if f.lower().endswith(BINAER):
                continue
            p = os.path.join(d, f)
            try:
                t = open(p, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            n = 0
            for m in melden:
                for x in m.finditer(t):
                    # Mitten in eingebetteten Daten (Base64 fuer Schriften und
                    # Bilder in design/) ist ein Treffer Zufall: drei passende
                    # Buchstaben in einer Datenzeile sind kein Name. (Hier steht
                    # bewusst kein Beispiel - das Schwaerzen ersetzte es sonst in
                    # genau dieser Datei.) Ohne diese Ausnahme meldete jede Uebergabe 35
                    # falsche Stellen - und ein Bericht, der immer anschlaegt,
                    # wird irgendwann nicht mehr gelesen, auch beim echten Fund.
                    umfeld = t[max(0, x.start() - 8):x.end() + 8]
                    if len(umfeld) >= x.end() - x.start() + 12 and re.fullmatch(r"[A-Za-z0-9+/=]+", umfeld):
                        continue
                    n += 1
            if n:
                rest[os.path.relpath(p, ziel)] = n
    print(f"Kopie: {ziel}")
    print(f"  weggelassen: {', '.join(WEG + WEG_MUSTER)}")
    print(f"  geschwaerzt in {geaendert} Dateien")
    if rest:
        print(f"  noch gemeldet ({sum(rest.values())} Stellen, meist Kommentare - bitte durchsehen):")
        for p, n in sorted(rest.items(), key=lambda x: -x[1])[:20]:
            print(f"    {n:4}  {p}")
    else:
        print("  nichts mehr gemeldet")


if __name__ == "__main__":
    main()
