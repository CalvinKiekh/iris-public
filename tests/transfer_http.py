"""Die verschluesselte Uebergabe durch die echte Bruecke, nicht nur daneben.

    python3 tests/transfer_http.py

tests/transfer.py prueft das Siegel fuer sich, mit Stroemen im Speicher.
Hier laeuft derselbe Weg durch den echten Handler aus bridge/server.py:
versiegeln, abholen, Schluessel gegen Ticket, einspielen - ueber HTTP, mit
Token, mit Content-Length, mit allem was dazwischen schiefgehen kann.

Genau dieser Teil war vorher ungeprueft, und es ist der Teil, an dem die
haesslichen Fehler sitzen: ein Strom, der einen Block mitten durchschneidet,
eine Laenge, die nicht passt, ein Lesen, das ueber den Koerper hinausgeht
und am offenen Socket haengt.

Die laufende Bruecke wird dabei NICHT angefasst. Der Server hier bekommt
einen eigenen Port, einen eigenen Token und einen erfundenen Sitzungs-
verwalter mit zwei Wegwerf-Verzeichnissen.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge import maschine, server, transfer

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


TOKEN = "pruef-token-nur-fuer-diesen-lauf"
ZEILE = b"Messdaten Lackierzelle, Spalte A\n"
INHALT = (ZEILE * (3 * transfer.BLOCK // len(ZEILE) + 2))[:2 * transfer.BLOCK + 517]


class Sitzung:
    def __init__(self, key, cwd):
        self.key, self.cwd = key, cwd
        self.claude_session_id = ""
        self.resume = ""
        self.transcript = None


class Verwalter:
    """Nur das, was die Uebergabe-Endpunkte anfassen."""

    def __init__(self, sitzungen):
        self.sessions = {s.key: s for s in sitzungen}

    def get(self, key):
        return self.sessions.get(key)


def hole(pfad, daten=None, roh=None, token=TOKEN, methode=None):
    """Ein Aufruf gegen den Testserver. Gibt (Status, Koerper) zurueck."""
    url = "http://127.0.0.1:%d%s" % (PORT, pfad)
    kopf = {"Authorization": "Bearer " + token} if token else {}
    if roh is not None:
        koerper, kopf["Content-Type"] = roh, "application/octet-stream"
    elif daten is not None:
        koerper = json.dumps(daten).encode()
        kopf["Content-Type"] = "application/json"
    else:
        koerper = None
    anfrage = urllib.request.Request(url, data=koerper, headers=kopf,
                                     method=methode or ("POST" if koerper is not None else "GET"))
    try:
        with urllib.request.urlopen(anfrage, timeout=30) as a:
            return a.status, a.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def alsJson(koerper):
    try:
        return json.loads(koerper)
    except ValueError:
        return {}


# ---------- Aufbau ----------

QUELLE = tempfile.mkdtemp(prefix="iris-http-quelle-")
ZIEL = tempfile.mkdtemp(prefix="iris-http-ziel-")
with open(os.path.join(QUELLE, "messwerte.csv"), "wb") as fh:
    fh.write(INHALT)

server.Handler.manager = Verwalter([Sitzung("quelle", QUELLE), Sitzung("ziel", ZIEL)])
server.Handler.token = TOKEN
# Port 0: das Betriebssystem sucht einen freien aus, damit der Lauf nie mit
# der echten Bruecke kollidiert.
HTTP = server._Server(("127.0.0.1", 0), server.Handler)
PORT = HTTP.server_address[1]
threading.Thread(target=HTTP.serve_forever, daemon=True).start()

try:
    print("Ohne Token kommt niemand durch")
    st, _ = hole("/api/sessions/quelle/ausgang", {"ziel": "x", "path": "messwerte.csv"},
                 token="falsch")
    pruefe(st == 401, "falscher Token wird abgewiesen", str(st))

    print("Der ganze Weg ueber HTTP")
    st, k = hole("/api/sessions/quelle/ausgang",
                 {"ziel": maschine.specs()["name"], "path": "messwerte.csv"})
    siegel = alsJson(k)
    pruefe(st == 200 and siegel.get("ok"), "versiegeln", str(st) + " " + str(siegel.get("grund")))
    pruefe(siegel.get("bloecke") == 3, "drei Bloecke", str(siegel.get("bloecke")))
    pruefe(len(siegel.get("schluessel", "")) == 64, "Schluessel kommt zurueck")

    st, blob = hole("/api/ausgang/" + siegel["id"])
    pruefe(st == 200 and len(blob) == siegel["versiegelt"],
           "Klotz kommt vollstaendig an", "%s %d/%d" % (st, len(blob), siegel.get("versiegelt", 0)))
    pruefe(INHALT[:64] not in blob, "und traegt keinen Klartext")

    st, k = hole("/api/eingang/schluessel",
                 {"sitzung": "quelle", "name": siegel["name"],
                  "bloecke": siegel["bloecke"], "schluessel": siegel["schluessel"]})
    ticket = alsJson(k)
    pruefe(st == 200 and ticket.get("ticket"), "Ticket fuer den Schluessel", str(st))

    st, k = hole("/api/sessions/ziel/eingang/" + ticket["ticket"], roh=blob)
    an = alsJson(k)
    pruefe(st == 201 and an.get("ok"), "eingespielt", str(st) + " " + str(an.get("grund")))
    if an.get("ok"):
        with open(os.path.join(ZIEL, an["name"]), "rb") as fh:
            pruefe(fh.read() == INHALT, "Byte fuer Byte dieselbe Datei")

    st, _ = hole("/api/ausgang/weg", {"id": siegel["id"]})
    pruefe(st == 200 and not transfer.ausgang_pfad(siegel["id"]),
           "Spool ist danach leer")

    print("Ein Klotz, an dem unterwegs gedreht wurde")
    st, k = hole("/api/sessions/quelle/ausgang",
                 {"ziel": maschine.specs()["name"], "path": "messwerte.csv"})
    s2 = alsJson(k)
    _, blob2 = hole("/api/ausgang/" + s2["id"])
    kaputt = bytearray(blob2)
    kaputt[len(kaputt) // 2] ^= 0x01
    _, k = hole("/api/eingang/schluessel",
                {"sitzung": "quelle", "name": s2["name"], "bloecke": s2["bloecke"],
                 "schluessel": s2["schluessel"]})
    t2 = alsJson(k)
    st, k = hole("/api/sessions/ziel/eingang/" + t2["ticket"], roh=bytes(kaputt))
    pruefe(st == 400 and not alsJson(k).get("ok"), "wird abgewiesen", str(st))
    pruefe(not [f for f in os.listdir(ZIEL) if f.startswith(".iris-eingang-")],
           "und laesst keinen halben Stand liegen")
    hole("/api/ausgang/weg", {"id": s2["id"]})

    print("Was die Endpunkte nicht mit sich machen lassen")
    st, _ = hole("/api/sessions/gibtsnicht/ausgang",
                 {"ziel": "x", "path": "messwerte.csv"})
    pruefe(st == 404, "unbekannte Sitzung", str(st))
    st, k = hole("/api/sessions/quelle/ausgang",
                 {"ziel": "x", "path": "../../../etc/hosts"})
    pruefe(st == 400 and not alsJson(k).get("ok"), "Pfad aus dem Verzeichnis heraus", str(st))
    st, _ = hole("/api/ausgang/nichtvorhanden")
    pruefe(st == 404, "unbekannter Klotz", str(st))
    st, k = hole("/api/sessions/ziel/eingang/abgelaufenesticket", roh=b"egal")
    pruefe(st == 400 and not alsJson(k).get("ok"), "unbekanntes Ticket", str(st))
    st, k = hole("/api/eingang/schluessel",
                 {"sitzung": "quelle", "name": "x.csv", "bloecke": 1,
                  "schluessel": "zu-kurz"})
    pruefe(st == 400, "Schluessel mit falscher Laenge", str(st))

    print("Die Uebergabe traegt die Maschine mit")
    st, k = hole("/api/sessions/quelle/uebergabe")
    u = alsJson(k)
    pruefe(st == 200 and u.get("maschine", {}).get("chip"),
           "Chip steht drin", str(u.get("maschine")))
    pruefe(bool(u.get("zettel")) and u["maschine"]["name"] in u["zettel"],
           "und der Zettel nennt den Rechner", str(u.get("zettel")))

finally:
    HTTP.shutdown()
    HTTP.server_close()
    shutil.rmtree(QUELLE, ignore_errors=True)
    shutil.rmtree(ZIEL, ignore_errors=True)

print()
print(f"{ok_count} ok, {len(fehler)} fehlgeschlagen")
sys.exit(1 if fehler else 0)
