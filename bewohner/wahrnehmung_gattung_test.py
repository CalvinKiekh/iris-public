"""Gattung, Groesse und Lernlauf - ohne Modell, ohne laufenden Bewohner.

Drei Fehler vom 12.09., alle aus dem Push-Sturm um 21:03:

  1. ersteinlesen() zaehlte nur und schrieb nichts. Ohne gesehen.json war
     darum jede Datei auf Desktop und Downloads "neu" - ueber hundert Funde,
     eine Mitteilung je Datei.
  2. .url, .lnk und .bat fielen auf "Art unbekannt", obwohl bestimmbar.
  3. `groesse // 1024` machte aus 300 Byte "0 Kilobyte".

    python -X utf8 wahrnehmung_gattung_test.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import probenort
import wahrnehmung

ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}"
          + (f"  [{dazu}]" if dazu else ""))


ort = probenort.ablage("gattung")


# ---------------------------------------------------------------- 1. Groesse
print("\nGroesse - 0 Kilobyte ist schlicht falsch")

for bytes_, erwartet in [(0, "0 Byte"), (1, "1 Byte"), (300, "300 Byte"),
                         (1023, "1023 Byte"), (1024, "1 Kilobyte"),
                         (96024 * 1024, "93,8 Megabyte"),
                         (1228171 * 1024, "1,2 Gigabyte")]:
    hat = wahrnehmung.groesse_sagen(bytes_)
    pruefen(f"{bytes_} Byte -> {erwartet}", hat == erwartet, hat)

pruefen("keine Groesse sagt je '0 Kilobyte'",
        all("0 Kilobyte" != wahrnehmung.groesse_sagen(n)
            for n in range(0, 2048)))
pruefen("Komma, nicht Punkt - der Satz wird vorgelesen",
        "." not in wahrnehmung.groesse_sagen(1228171 * 1024),
        wahrnehmung.groesse_sagen(1228171 * 1024))


# ---------------------------------------------------------------- 2. Gattung
print("\nGattung - eine Spielverknuepfung ist erkennbar")

steam = ort / "Dying Light The Beast.url"
steam.write_text("[InternetShortcut]\nURL=steam://rungameid/534380\n",
                 encoding="utf-8")
netz = ort / "SwarmUI.url"
netz.write_text("[InternetShortcut]\nURL=http://localhost:7801/Text2Image\n",
                encoding="utf-8")
startskript = ort / "ComfyUI starten.bat"
startskript.write_text("@echo off\ncd C:\\ComfyUI\npython main.py\n",
                       encoding="utf-8")
# Eine .lnk im Rumpf: der Zielpfad steht im Klartext drin.
verkn = ort / "Rockstar Games Launcher.lnk"
verkn.write_bytes(b"L\x00\x00\x00\x01\x14\x02\x00" + b"\x00" * 60
                  + b"C:\\Program Files\\Rockstar Games\\Launcher\\"
                    b"Launcher.exe\x00")
vektor = ort / "blume.svg"
vektor.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                  encoding="utf-8")
exe = ort / "L-Connect-3-x64.exe"
exe.write_bytes(b"MZ" + b"\x00" * 4000)
fremd = ort / "20251001082157155.smap"
fremd.write_bytes(b"\x01\x02\x03" * 400)

for datei, erwartet_art in [(steam, "verknuepfung"), (netz, "verknuepfung"),
                            (verkn, "verknuepfung"), (startskript, "skript"),
                            (vektor, "grafik"), (exe, "programm"),
                            (fremd, "unbekannt")]:
    hat = wahrnehmung.art(datei)
    pruefen(f"{datei.name} -> {erwartet_art}", hat == erwartet_art, hat)

# verstehen() ohne Modell: nur die Zweige, die kein Ollama brauchen.
s = wahrnehmung.verstehen(steam)
print(f"    {s}")
pruefen("die Spielverknuepfung wird als Spiel benannt",
        "Spielverknuepfung" in s and "Steam" in s, s)
pruefen("und nennt den Namen, nicht die Endung",
        "Dying Light The Beast" in s and ".url" not in s, s)

s = wahrnehmung.verstehen(netz)
print(f"    {s}")
pruefen("die Internetverknuepfung nennt das Ziel",
        "Internetverknuepfung" in s and "localhost" in s, s)

s = wahrnehmung.verstehen(verkn)
print(f"    {s}")
pruefen("die Verknuepfung nennt, was sie startet",
        "Verknuepfung" in s and "Launcher.exe" in s, s)

s = wahrnehmung.verstehen(vektor)
print(f"    {s}")
pruefen("die Vektorgrafik heisst Vektorgrafik", "Vektorgrafik" in s, s)

s = wahrnehmung.verstehen(exe)
print(f"    {s}")
pruefen("das Programm heisst Programm", "Programm" in s, s)

s = wahrnehmung.verstehen(fremd)
print(f"    {s}")
pruefen("das wirklich Unbekannte nennt seine Endung",
        ".smap" in s and "Art unbekannt" not in s, s)

alle = [wahrnehmung.verstehen(d) for d in
        (steam, netz, verkn, vektor, exe, fremd)]
pruefen("KEIN Satz sagt mehr 'Art unbekannt'",
        not any("Art unbekannt" in t for t in alle))
pruefen("KEIN Satz sagt mehr '0 Kilobyte'",
        not any("0 Kilobyte" in t for t in alle))


# --------------------------------------------------------------- 3. Lernlauf
print("\nLernlauf - eine verlorene Merkliste loest keine Flut aus")

# NICHT an der echten gesehen.json arbeiten. Der Bewohner laeuft, schreibt
# sie jederzeit - und eine zurueckgelegte alte Liste loeste genau die Flut
# aus, um die es hier geht. Also eigene Ordner unterschieben.
import json

lern = probenort.ablage("lern")
lern_eingang = lern / "eingang"
lern_mit = lern / "desktop"
for d in (lern_eingang, lern_mit):
    d.mkdir(parents=True, exist_ok=True)
for i in range(7):
    (lern_mit / f"lag schon da {i}.txt").write_text("alt", encoding="utf-8")

echt_gesehen, echt_eingang, echt_mit = (wahrnehmung.GESEHEN,
                                        wahrnehmung.EINGANG,
                                        wahrnehmung.MITLESEN)
try:
    wahrnehmung.GESEHEN = lern / "gesehen.json"
    wahrnehmung.EINGANG = lern_eingang
    wahrnehmung.MITLESEN = (lern_mit,)

    pruefen("ohne gesehen.json gibt es etwas zu lernen",
            len(wahrnehmung.neue_dateien()) == 7,
            f"{len(wahrnehmung.neue_dateien())} Dateien")

    gelernt = wahrnehmung.ersteinlesen()
    pruefen("der Lernlauf hat abgehakt, nicht nur gezaehlt", gelernt == 7,
            f"{gelernt} eingetragen")
    pruefen("gesehen.json liegt danach da", wahrnehmung.GESEHEN.exists())

    inhalt = json.loads(wahrnehmung.GESEHEN.read_text(encoding="utf-8"))
    pruefen("und enthaelt so viele Eintraege wie gelernt",
            len(inhalt) == gelernt, f"{len(inhalt)} vs {gelernt}")

    # Das Entscheidende: danach ist NICHTS mehr neu.
    danach = wahrnehmung.neue_dateien()
    pruefen("nach dem Lernlauf ist nichts mehr neu - keine Flut",
            len(danach) == 0, f"{len(danach)} uebrig: "
                              f"{[p.name for p, _, _ in danach][:4]}")

    # Ein zweiter Aufruf lernt NICHT erneut.
    pruefen("ein zweiter Lernlauf tut nichts",
            wahrnehmung.ersteinlesen() == 0)

    # Was jetzt dazukommt, ist wirklich neu.
    (lern_mit / "gerade erst entstanden.txt").write_text("neu",
                                                         encoding="utf-8")
    namen = [p.name for p, _, _ in wahrnehmung.neue_dateien()]
    pruefen("was DANACH dazukommt, gilt als neu - und nur das",
            namen == ["gerade erst entstanden.txt"], str(namen[:4]))

    # Und der Lernlauf legt die Datei auch an, wenn es nichts zu lernen gab -
    # sonst waere der naechste Start wieder ein Lernlauf.
    leer = lern / "leer"
    leer.mkdir(exist_ok=True)
    wahrnehmung.GESEHEN = leer / "gesehen.json"
    wahrnehmung.EINGANG = leer / "eingang"
    wahrnehmung.MITLESEN = ()
    pruefen("Lernlauf ohne Dateien legt die Liste trotzdem an",
            wahrnehmung.ersteinlesen() == 0 and wahrnehmung.GESEHEN.exists())
finally:
    (wahrnehmung.GESEHEN, wahrnehmung.EINGANG,
     wahrnehmung.MITLESEN) = echt_gesehen, echt_eingang, echt_mit

probenort.wegraeumen(lern)
probenort.wegraeumen(ort)

print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
