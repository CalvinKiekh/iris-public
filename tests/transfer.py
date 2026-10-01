"""Verschluesselte Uebergabe: kommt die Datei an, und nur die richtige?

    python3 tests/transfer.py

Geprueft wird ohne Netz und ohne Bruecke, nur das Siegel und die Ablage.
Die Haelfte der Pruefungen sind Angriffe: jede davon MUSS abbrechen, und
zwar ohne etwas im Arbeitsverzeichnis zu hinterlassen.

  - eine versiegelte Datei kommt unveraendert an
  - ein fremder Zielrechner bricht ab          (Aufkleber, Regel 5)
  - eine fremde Sitzung bricht ab              (Aufkleber, Regel 5)
  - ein gekipptes Byte bricht ab               (Siegel)
  - vertauschte Bloecke brechen ab             (Zaehler-Nonce, Regel 1)
  - ein abgeschnittener Strom bricht ab        (Blockzahl im Aufkleber)
  - angehaengter Muell bricht ab
  - ein zweites Einspielen bricht ab           (Einmalschluessel, Regel 4)
  - ../ im Dateinamen landet nicht ausserhalb  (Regel 3)
  - eine vorhandene Datei wird nicht ueberschrieben
  - nach einem Fehlschlag liegt kein Rest herum (Regel 2)
"""
import io
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge import transfer

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


HIER = transfer.config.machine_name()
SITZUNG = "sitzung-abc"
# Zwei volle Bloecke und ein Rest, damit die Blockgrenzen wirklich vorkommen.
# Die Zeile ist 33 Byte: erst genug davon erzeugen, dann zuschneiden, sonst
# schneidet der Zuschnitt ins Leere und es bleibt bei zwei Bloecken.
ZEILE = b"Messdaten Lackierzelle, Spalte A\n"
INHALT = (ZEILE * (3 * transfer.BLOCK // len(ZEILE) + 2))[:2 * transfer.BLOCK + 517]


def aufbau():
    """Ein Quell- und ein Zielverzeichnis, die Datei darin versiegelt."""
    quelle = tempfile.mkdtemp(prefix="iris-quelle-")
    ziel = tempfile.mkdtemp(prefix="iris-ziel-")
    with open(os.path.join(quelle, "messwerte.csv"), "wb") as fh:
        fh.write(INHALT)
    return quelle, ziel


def versiegelt(quelle, ziel_name=HIER, sitzung=SITZUNG):
    s = transfer.versiegeln(quelle, sitzung, ziel_name, "messwerte.csv")
    with open(transfer.ausgang_pfad(s["id"]), "rb") as fh:
        return s, fh.read()


def einspielen(s, blob, ziel, sitzung=SITZUNG):
    t = transfer.schluessel_annehmen(sitzung, s["name"], s["bloecke"],
                                     s["schluessel"])
    return transfer.oeffnen(t["ticket"], io.BytesIO(blob), ziel)


def rest_im_ordner(ordner):
    return [f for f in os.listdir(ordner) if f.startswith(".iris-eingang-")]


print("Der ehrliche Weg")
quelle, ziel = aufbau()
s, blob = versiegelt(quelle)
pruefe(s["ok"] and s["bloecke"] == 3, "drei Bloecke versiegelt", str(s.get("bloecke")))
pruefe(blob and INHALT[:64] not in blob, "im Spool steht kein Klartext")
r = einspielen(s, blob, ziel)
pruefe(r["ok"], "kommt an", r.get("grund", ""))
if r["ok"]:
    with open(os.path.join(ziel, r["name"]), "rb") as fh:
        pruefe(fh.read() == INHALT, "und ist Byte fuer Byte dieselbe Datei")
transfer.ausgang_weg(s["id"])
pruefe(not transfer.ausgang_pfad(s["id"]), "der Spool ist danach leer")
shutil.rmtree(quelle); shutil.rmtree(ziel)

print("Fremder Zielrechner")
quelle, ziel = aufbau()
s, blob = versiegelt(quelle, ziel_name="ein-anderer-rechner")
r = einspielen(s, blob, ziel)
pruefe(not r["ok"], "bricht ab", str(r))
pruefe(not rest_im_ordner(ziel), "und laesst nichts liegen")
shutil.rmtree(quelle); shutil.rmtree(ziel)

print("Fremde Sitzung")
quelle, ziel = aufbau()
s, blob = versiegelt(quelle)
r = einspielen(s, blob, ziel, sitzung="eine-ganz-andere")
pruefe(not r["ok"], "bricht ab", str(r))
shutil.rmtree(quelle); shutil.rmtree(ziel)

print("Ein gekipptes Byte")
quelle, ziel = aufbau()
s, blob = versiegelt(quelle)
kaputt = bytearray(blob)
kaputt[len(kaputt) // 2] ^= 0x01
r = einspielen(s, bytes(kaputt), ziel)
pruefe(not r["ok"], "bricht ab", str(r))
pruefe(not rest_im_ordner(ziel), "und laesst nichts liegen")
shutil.rmtree(quelle); shutil.rmtree(ziel)

print("Vertauschte Bloecke")
# Der Nonce ist die Blocknummer: ein Block an falscher Stelle wird mit dem
# falschen Nonce geoeffnet und faellt durch. Genau dafuer ist der Zaehler da.
quelle, ziel = aufbau()
s, blob = versiegelt(quelle)
laenge = int.from_bytes(blob[:4], "big")
erster, rest = blob[:4 + laenge], blob[4 + laenge:]
l2 = int.from_bytes(rest[:4], "big")
zweiter = rest[:4 + l2]
r = einspielen(s, zweiter + erster + rest[4 + l2:], ziel)
pruefe(not r["ok"], "bricht ab", str(r))
shutil.rmtree(quelle); shutil.rmtree(ziel)

print("Abgeschnittener Strom")
quelle, ziel = aufbau()
s, blob = versiegelt(quelle)
r = einspielen(s, blob[:len(blob) // 2], ziel)
pruefe(not r["ok"], "bricht ab", str(r))
pruefe(not rest_im_ordner(ziel), "und laesst den halben Stand nicht liegen")
shutil.rmtree(quelle); shutil.rmtree(ziel)

print("Angehaengter Muell")
quelle, ziel = aufbau()
s, blob = versiegelt(quelle)
r = einspielen(s, blob + b"\x00\x00\x00\x10" + b"X" * 16, ziel)
pruefe(not r["ok"], "bricht ab", str(r))
shutil.rmtree(quelle); shutil.rmtree(ziel)

print("Zweites Einspielen mit demselben Ticket")
quelle, ziel = aufbau()
s, blob = versiegelt(quelle)
t = transfer.schluessel_annehmen(SITZUNG, s["name"], s["bloecke"], s["schluessel"])
erst = transfer.oeffnen(t["ticket"], io.BytesIO(blob), ziel)
nochmal = transfer.oeffnen(t["ticket"], io.BytesIO(blob), ziel)
pruefe(erst["ok"] and not nochmal["ok"], "das erste geht, das zweite nicht",
       str(nochmal))
shutil.rmtree(quelle); shutil.rmtree(ziel)

print("Ein Dateiname, der ausbrechen will")
quelle, ziel = aufbau()
for boese in ["../../etc/passwd", "/etc/passwd", "..", ".versteckt",
              "ordner/datei.txt", ""]:
    pruefe(transfer.sicherer_name(boese) in ("", "passwd", "datei.txt"),
           f"'{boese}' wird entschaerft", repr(transfer.sicherer_name(boese)))
# Und der ganze Weg: das Ziel baut den Namen selbst, der Absender bestimmt ihn nicht.
s, blob = versiegelt(quelle)
t = transfer.schluessel_annehmen(SITZUNG, "../../entwischt.csv", s["bloecke"],
                                 s["schluessel"])
pruefe(t["ok"] and t["name"] == "entwischt.csv", "der Pfad faellt weg",
       str(t.get("name")))
oben = os.path.join(os.path.dirname(ziel), "entwischt.csv")
pruefe(not os.path.exists(oben), "nichts liegt eine Ebene hoeher")
shutil.rmtree(quelle); shutil.rmtree(ziel)

print("Eine Datei, die es schon gibt")
quelle, ziel = aufbau()
with open(os.path.join(ziel, "messwerte.csv"), "wb") as fh:
    fh.write(b"daran arbeitet gerade jemand")
s, blob = versiegelt(quelle)
r = einspielen(s, blob, ziel)
pruefe(r["ok"] and r["name"] == "messwerte (2).csv", "landet daneben",
       str(r.get("name")))
with open(os.path.join(ziel, "messwerte.csv"), "rb") as fh:
    pruefe(fh.read() == b"daran arbeitet gerade jemand", "das Vorhandene bleibt")
shutil.rmtree(quelle); shutil.rmtree(ziel)

print("Was gar nicht erst versiegelt wird")
quelle, ziel = aufbau()
raus = transfer.versiegeln(quelle, SITZUNG, HIER, "../../../etc/hosts")
pruefe(not raus["ok"], "eine Datei ausserhalb des Arbeitsverzeichnisses",
       str(raus))
ohne = transfer.versiegeln(quelle, SITZUNG, "", "messwerte.csv")
pruefe(not ohne["ok"], "ohne genannten Zielrechner", str(ohne))
fehlt = transfer.versiegeln(quelle, SITZUNG, HIER, "gibtsnicht.csv")
pruefe(not fehlt["ok"], "eine Datei, die es nicht gibt", str(fehlt))
shutil.rmtree(quelle); shutil.rmtree(ziel)

print("Der Schluessel taucht nirgends auf")
quelle, ziel = aufbau()
s, blob = versiegelt(quelle)
roh = bytes.fromhex(s["schluessel"])
pruefe(roh not in blob, "nicht im versiegelten Klotz")
pruefe(len(roh) == 32, "und ist 32 Byte lang", str(len(roh)))
s2, _ = versiegelt(quelle)
pruefe(s2["schluessel"] != s["schluessel"], "jede Uebertragung bekommt einen neuen")
transfer.ausgang_weg(s["id"]); transfer.ausgang_weg(s2["id"])
shutil.rmtree(quelle); shutil.rmtree(ziel)

print()
print(f"{ok_count} ok, {len(fehler)} fehlgeschlagen")
sys.exit(1 if fehler else 0)
