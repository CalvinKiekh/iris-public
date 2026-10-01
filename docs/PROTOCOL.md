# iris-Protokoll v1

Alles, was ein Client können muss. Der spätere RayNeo-Client spricht genau
dieses Protokoll — er ersetzt nur die Darstellung, nichts an der Logik.

## Transport

HTTP + Server-Sent Events. Bewusst kein WebSocket: SSE ist gewöhnliches
HTTP, verbindet sich nach einem Abriss selbst neu und braucht auf keiner
Plattform eine Bibliothek. Genau das zählt, solange das Brillen-SDK fehlt.

Authentifizierung: `Authorization: Bearer <token>`. Beim SSE-Endpunkt geht
auch `?token=…`, weil `EventSource` keine Header setzen kann.

Die Bridge lauscht auf der Tailscale-Adresse, nie auf `0.0.0.0`.

## Endpunkte

| Methode | Pfad | Zweck |
|---|---|---|
| GET  | `/api/health` | Lebenszeichen |
| GET  | `/api/projects` | bekannte Arbeitsverzeichnisse |
| GET  | `/api/projects/<id>/sessions` | fortsetzbare Konversationen |
| GET  | `/api/sessions` | laufende Sitzungen |
| POST | `/api/sessions` | Sitzung starten `{cwd, resume?, model?, permission_mode?}` |
| GET  | `/api/sessions/<key>` | Zustand + offene Bestätigungen |
| GET  | `/api/sessions/<key>/events?since=<seq>` | Kartenstrom (SSE) |
| POST | `/api/sessions/<key>/message` | `{text, attachments?}` — `attachments` sind Pfade aus einem Upload |
| POST | `/api/sessions/<key>/upload` | die Datei selbst als Body, `Content-Type` und `X-Filename` (URL-kodiert) im Kopf; Antwort `{path, name, size, media_type}` |
| POST | `/api/sessions/<key>/permission` | `{request_id, allow, message?, answers?}` — `answers` beantwortet eine Auswahlfrage: `{Fragetext: gewählte Option}` |
| POST | `/api/sessions/<key>/interrupt` | laufenden Zug abbrechen |
| POST | `/api/sessions/<key>/close` | Sitzung beenden |
| GET/POST | `/api/shortcuts` | Standard-Abfragen lesen/schreiben |
| GET  | `/api/sessions/<key>/context` | Kontextaufschlüsselung (wie `/context`) |
| GET  | `/api/sessions/<key>/capabilities` | Modelle, Befehle, Agenten, Konto |
| GET  | `/api/sessions/<key>/files` | geänderte Dateien |
| GET  | `/api/sessions/<key>/files/<id>/diff` | Diff, `?from=`/`?to=` |
| POST | `/api/sessions/<key>/mode` | `{mode}` |
| POST | `/api/sessions/<key>/model` | `{model}` |
| POST | `/api/sessions/<key>/control` | `{subtype, payload}` — roher Steuerbefehl |
| GET  | `/api/git?cwd=…&what=…` | `status`, `log`, `diff`, `branches`, `pulls`, `checks`, `accounts` — **nur lesend** |
| GET/POST | `/api/terminals/away` | `{away}` — Freigaben aus Terminal-Sitzungen kommen aufs Handy |
| GET  | `/api/push` | eingerichtet?, angemeldete Telefone, Apples letzte Antworten |
| POST | `/api/push/register` | `{token, env, name}` — ein Telefon meldet sich an; `env` ist `sandbox` oder `production` |
| POST | `/api/push/test` | eine Probe an alle Telefone, Antwort sind Apples Statuscodes |
| POST | `/api/hooks` | nur für `hooks/iris_hook.py`: ein Hook-Aufruf, Antwort `{output}` |

## Detailgrade

`/events` nimmt `?detail=full|card|minimal` (Vorgabe `card`). Die Verdichtung
passiert **serverseitig**, nicht im Client: die Brille erreicht uns über BLE,
und 20 KB zu schicken, damit sie vier Zeilen zeichnet, wäre der falsche
Tausch.

| Grad | für | Unterschied |
|---|---|---|
| `full` | Rechner-Client | nichts wird gekürzt, `act` trägt die vollständige Werkzeug-Eingabe mit, `result` meldet die echte Länge |
| `card` | Handy, Browser | wie gehabt: eine Zeile je Aufruf, Text bis 4000 Zeichen |
| `minimal` | Brille | nur das Nötigste, Text bis 1200 Zeichen, keine Zähler |

Die Kartenarten sind auf jeder Stufe dieselben — ein Client muss also nie
Sonderfälle kennen, die Nutzlast wird nur reicher oder dünner.

## Karten

Jede Karte hat `kind`, `seq` und `ts`. `seq` zählt pro Sitzung lückenlos
hoch; nach einem Verbindungsabriss fordert der Client mit `since=<letzte seq>`
das Fehlende nach. Die Bridge hält die letzten 500 Karten vor.

| kind | Felder | Bedeutung |
|---|---|---|
| `ready` | `session_id`, `cwd`, `model` | Sitzung steht |
| `sent` | `text` | eigene Eingabe (Echo) |
| `say` | `text` | Antwort für den Menschen |
| `think` | `tokens` | denkt nach, ohne Inhalt |
| `act` | `tool`, `detail` | Werkzeugaufruf, auf eine Zeile verdichtet |
| `result` | `ok`, `text` | Ergebnis eines Aufrufs |
| `ask` | `request_id`, `tool`, `detail`, `input` | **Entscheidung nötig** |
| `answered` | `request_id`, `allow` | Entscheidung ist durch |
| `usage` | `windows.five_hour.used`, `…resets_at` | Kontingent wie `/usage` |
| `done` | `stop_reason`, `duration_ms` | Zug fertig |
| `closed` | `reason` | Sitzung beendet |
| `error` | `text` | Störung |
| `timing` | `tool_use_id`, `duration_ms` | Dauer eines Aufrufs — nur Terminal-Sitzungen, aus dem Hook |
| `queued` | `text` | Nachricht vom Handy, noch nicht übergeben — nur Terminal-Sitzungen |
| `delivered` | `count`, `via` | übergeben; `via` ist `stop` (am Zugende) oder `prompt` (mit der nächsten Eingabe) |
| `background` | `tasks[]` mit `id`, `type` (`shell`/`agent`), `status`, `description`, `command`, `since` | was gerade im Hintergrund läuft — die ganze Liste, nicht nur die Änderung |

`done` trägt auch `cost_usd`. Der Wert ist der rechnerische Gegenwert zu
API-Listenpreisen und wird bei Abo-Nutzung **nicht abgerechnet** — deshalb
zeigt ihn kein Client an. Die belastbare Größe ist `usage`.

## Terminal-Sitzungen

Sitzungen, die in einem Terminal laufen, stehen mit `terminal: true` in
`/api/sessions`, Schlüssel `t-<session_id>`, dazu `acts`, `failed` und
`queued`. Sie liefern dieselben Karten wie eigene Sitzungen; eine `ask`-Karte
trägt dort `terminal: true`.

`message` antwortet mit **202** und `{queued, note}`: zugestellt wird am
Zugende oder mit der nächsten Eingabe am Terminal. `mode`, `model`,
`control`, `interrupt` und `close` antworten mit **409** — eine
Terminal-Sitzung hat keinen Steuerkanal nach außen. Einzelheiten und Grenzen
in `TERMINAL.md`.

## Bestätigungen

Kommt eine `ask`-Karte, wartet auf der anderen Seite ein blockierter Prozess.
Ohne Antwort läuft nichts. Nach `IRIS_PERMISSION_TIMEOUT` (Vorgabe 300 s)
gilt die Anfrage als abgelehnt — im Zweifel passiert also nichts.

Nicht jeder Werkzeugaufruf fragt nach: Claude Code winkt harmlose Befehle
(`echo`, `ls`, …) selbst durch. Das ist so gewollt und keine Lücke.

## Bedienung mit einem Rad

Die RayNeo IO wird über ein Scrollrad und eine Bestätigungstaste bedient.
Deshalb muss **jeder** Bildschirm als flache Liste bedienbar sein: Rad bewegt
den Fokus, Druck löst aus. `web/wheel.js` setzt das um; für die Brille ist
nur `attachInput()` neu zu schreiben, der Rest bleibt.

Zwei Regeln, die daraus folgen:

- Eine offene Bestätigung zieht den Fokus sofort auf **Erlauben**.
- Kein Bedienelement darf ein anderes verdecken. Ohne Touch gibt es keinen
  Weg, ein Overlay wieder loszuwerden.

Weil auf der Brille getippt wird, tragen die Standard-Abfragen
(`/api/shortcuts`) die Hauptlast der Eingabe. Sie liegen auf der Bridge,
damit jeder Client dieselbe Liste zeigt.
