# Dienste melden sich selbst

Das Schema, das jedes künftige System übernimmt. Einmal definiert, überall
gleich — ein neuer Dienst braucht drei Zeilen und erscheint im Dashboard.

## Warum Melden statt Abfragen

Der naheliegende Weg wäre, per SSH nachzusehen. Er ist der schlechtere:

- Er braucht einen erreichbaren Host und Zugangsdaten auf diesem Mac. Ein Pi
  im Heimnetz ist von unterwegs nicht erreichbar — der Dienst selbst aber
  kann jederzeit hinausfunken.
- Er lernt nur, was im Moment der Abfrage galt. Ein Dienst weiß dagegen
  selbst, ob er seine Arbeit tut, und kann es sofort sagen.
- Er kostet eine SSH-Verbindung je Host. Melden kostet einen HTTP-POST.

iris greift also **nie** von sich aus zu.

## Der Vertrag

Ein Dienst schickt alle N Sekunden an `POST /api/heartbeat`:

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `name` | ja | was der Dienst ist — `"bev-stitch"` |
| `host` | ja | auf welcher Maschine — `"pi-head"` |
| `status` | nein | `"ok"` · `"warn"` · `"error"` (Vorgabe `ok`) |
| `detail` | nein | frei, ein paar Zahlen — `{"queue": 3}` |
| `version` | nein | Git-Kurzform, Tag, was auch immer |
| `interval` | nein | wie oft er sich meldet, in Sekunden (Vorgabe 60) |

Die Kennung ist `host/name`. Zweimal derselbe Name auf derselben Maschine ist
derselbe Dienst.

### Drei Regeln, die das Dashboard erst brauchbar machen

1. **`status` ist das Urteil des Dienstes über sich selbst.** `warn`, solange
   er eingeschränkt arbeitet, `error`, wenn er seine Aufgabe nicht erfüllt.
   Ein Dienst, der nichts mehr tut und weiter `ok` meldet, ist schlimmer als
   einer, der schweigt.
2. **`interval` ist ein Versprechen.** Wer es um mehr als das 2,5-fache
   reißt, gilt als **vermisst** — der einzige Zustand, den ein Dienst nicht
   selbst melden kann.
3. **Ein sauberes Ende sagt das auch.** `stop()` meldet `gestoppt`, statt
   still zu werden. Das ist der Unterschied zwischen „abgeschaltet" und
   „abgestürzt".

## Einbauen

`clients/` enthält beides zum Kopieren. Zugangsdaten liefert `make ingest-token`.

**Python** — Hintergrund-Thread, der nie stört:

```python
from iris_heartbeat import Heartbeat

hb = Heartbeat("bev-stitch", host="pi-head", interval=60, version="1.4.2")
hb.start()
...
hb.warn(grund="Kamera liefert nicht")   # wenn sich etwas ändert
hb.ok(queue=len(pending), fps=12.4)
```

Oder als `with`-Block, der beim Verlassen automatisch `gestoppt` bzw. `error`
meldet:

```python
with Heartbeat("nightly-backup", host="nas") as hb:
    hb.ok(dateien=1204)
```

**Shell** — für Cronjobs und systemd:

```sh
iris-heartbeat.sh nightly-backup ok dateien=1204
# im Cron:
0 3 * * * /pfad/backup.sh && iris-heartbeat.sh backup ok || iris-heartbeat.sh backup error
```

**Alles andere** — ein POST genügt:

```
POST /api/heartbeat
Authorization: Bearer <ingest-token>
{"name":"…","host":"…","status":"ok","interval":60,"detail":{}}
```

## Das eigene Token

Heartbeats nutzen ein **zweites, schwächeres Token** (`make ingest-token`).
Es liegt am Ende auf jedem Pi und jedem Roboter — es darf deshalb nur melden
dürfen, nicht Sitzungen lesen oder starten. Das volle Token wird ebenfalls
akzeptiert, damit ein Client, der es ohnehin hat, kein zweites braucht.

## Ansehen

```
GET  /api/services                  Liste + Zusammenfassung
GET  /api/services?host=pi-head     nur eine Maschine
GET  /api/services?what=events      Zustandswechsel, neueste zuerst
POST /api/services/forget {"id":"host/name"}
```

Im Dashboard (◈ im Kopf): Kacheln für läuft / auffällig / vermisst / Geräte,
darunter nach Maschine gruppiert. Geräte mit einem Problem stehen oben, und
innerhalb einer Maschine der schlimmste Dienst zuerst — ein Dashboard, in dem
man den Fehler suchen muss, tut seine Arbeit nicht.

Protokolliert werden nur **Zustandswechsel**, nicht jeder Herzschlag. Eine
Liste von „läuft noch" im Minutentakt hilft niemandem.
