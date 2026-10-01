# iris

*iris* – nach der griechischen Götterbotin, die als Regenbogen Nachrichten zwischen Göttern und Menschen trägt. Hier: zwischen dir und Claude auf deinen Rechnern.

Fernsteuerung für Claude-Code-Sitzungen auf dem Mac. Läuft im Tailnet, ohne
Cloud-Dienst dazwischen, und ist von Anfang an so gebaut, dass eine Smartbrille
(RayNeo IO) später nur ein weiterer Client ist.

## Zwei Ansichten

- **Normal** (`/`) — Handy, Tablet, jeder Browser. Vollständig.
- **Brille** (`/sim/`) — monochrom grün, eine Karte pro Bild, nur Krone und
  Bestätigen. Umschalten über ◉ im Kopf der normalen Ansicht, zurück über
  das Menü in der Brillenansicht.

Der Simulator unter `sim/` ist ein **eigenständiges System**: er kennt nur
Panels und Eingaben, keine Claude-Code-Interna. Andere Brillen-Apps lassen
sich dort genauso prüfen — siehe `docs/GLASSES-APP.md`.

## Was es kann

- Projekte und frühere Konversationen am Rechner sehen und **fortsetzen**
- Aufträge schicken, per Tastatur oder Diktat
- Werkzeugaufrufe mitlesen, verdichtet auf eine Zeile
- **Bestätigen oder ablehnen** — ohne Antwort passiert nichts
- Laufenden Zug **unterbrechen**, oder einen laufenden Befehl **in den
  Hintergrund** schicken (Ctrl+B) — er läuft weiter, der Zug wartet nicht mehr
- Kontingent im Blick behalten (dasselbe, was `/usage` zeigt)
- Standard-Abfragen durchschalten, statt zu tippen
- **Modus im Betrieb wechseln** — Plan, Auto, Änderungen ohne Nachfrage,
  alles fragen … ohne die Sitzung neu zu starten
- **Verlauf mitnehmen**: eine fortgesetzte Konversation öffnet nicht mehr
  leer, sondern zeigt, wo du stehengeblieben bist
- **Abzweigen**: eine Unterhaltung, die noch am Rechner offen ist, lässt
  sich von unterwegs weiterführen, ohne sie dort zu stören
- **Am Mac**: Fenster ab halber Bildschirmbreite, Sitzungsliste ein- und
  ausklappbar, Antwort am Stück kopieren, Bilder groß ansehen, Dateien ziehen
  oder mit Cmd+V einfügen

## Start

Zum ersten Mal auf einem eigenen Rechner? **`docs/EINRICHTEN.md`** führt von
null bis zur ersten Sitzung vom Handy aus.

```bash
make run        # im Vordergrund
make token      # Zugangs-URL anzeigen
make check      # Selbsttest (kostet etwas Kontingent, läuft auf Haiku)
make install-agent   # beim Login mitstarten
```

Die URL aus `make token` auf dem Handy öffnen und zum Home-Bildschirm
hinzufügen — dann läuft es als eigenständige App.

## Die API ist der Kern

Der Dienst läuft durchgehend und liefert nur Daten. Oberflächen holen sich
davon, was sie brauchen — pro Plattform verschieden, ohne den Dienst
anzufassen:

- **Detailgrade** `?detail=full|card|minimal`, serverseitig verdichtet
- **Kontext** — vollständige Aufschlüsselung, was den Kontext füllt
- **Fähigkeiten** — Modelle, 147 Slash-Befehle, Agenten, Abo
- **Modell und Modus** im Betrieb wechselbar
- **Roher Steuerkanal** für alles, was Claude Code künftig dazubekommt

Was Claude Code überhaupt hergibt, steht nachgemessen in
`docs/WAS-CLAUDE-LIEFERT.md`.

## Aufbau

```
bridge/     Daemon: treibt die Claude-Code-CLI, verteilt Karten, hält Bestätigungen
  session.py              ein Prozess pro Konversation, Vollduplex über stream-json
  permissions.py          Bestätigungen parken, bis jemand antwortet
  mcp_permission_server.py  MCP-Server, den Claude Code zum Nachfragen benutzt
  protocol.py             fette Rohereignisse -> schlanke Karten
  server.py               HTTP + SSE
hooks/      der eine Hook, mit dem Terminal-Sitzungen sich an iris melden
web/        Client: PWA, mobile-first, mit Rad-Navigation
sim/        Brillen-Simulator, ein eigenständiges System (docs/GLASSES-APP.md)
shared/     Swift-Code, den iOS-, Watch- und Mac-App gemeinsam nutzen
ios/        iPhone- und Watch-App (XcodeGen, project.yml ist die Wahrheit)
mac/        Mac-App (SwiftPM, kein Xcode-Projekt), teilt sich shared/ mit iOS
pi/         Abbild für einen Container-Wirt, z. B. Raspberry Pi mit Home Assistant OS
tools/      Ausrollen auf weitere Rechner, Übergabe, Versionsnummer
clients/    Heartbeat für Dienste, die sich bei iris melden sollen
bewohner/   optional: ein dauerhafter Begleiter mit Gedächtnis (siehe unten)
docs/       Einrichten, Protokoll und geprüfte Befunde zur Claude-Code-Schnittstelle
tests/      Selbsttest über echtes HTTP gegen eine echte Sitzung
  markdown.py             Markdown aus Terminal-Sitzungen, ohne Netz und Sitzung
```

## Eine Sitzung vom Rechner weiterführen

iris markiert Unterhaltungen, die vermutlich gerade in einem Terminal laufen
(erkannt über das Arbeitsverzeichnis laufender `claude`-Prozesse plus die
Schreibzeit des Transcripts — eine begründete Vermutung, keine Gewissheit;
die Sitzungs-ID selbst gibt macOS nicht heraus).

Beim Öffnen einer solchen Unterhaltung legt iris einen **Abzweig** an
(`--resume … --fork-session`): der vollständige Verlauf kommt mit, die
Sitzung am Rechner läuft unberührt weiter. Was im Abzweig passiert, fließt
nicht dorthin zurück — deshalb fragt iris vorher nach.

Damit unterscheidet sich iris bewusst von der Claude-Code-App: die hängt
sich über `claude remote-control` an die *laufende* Sitzung, über einen
Kanal zu claude.ai, der nicht offen dokumentiert ist. Wer echtes
gleichzeitiges Mitsteuern braucht, ist dort richtig. Wer von jedem Gerät an
seine Arbeit will, ohne diesen Umweg, ist hier richtig.

## Git und GitHub

Die API liest den Zustand: Zweig, Upstream-Abstand, was schmutzig ist,
Historie, Zweige, offene Pull Requests, CI-Prüfungen — und **welches
GitHub-Konto** hinter dem Remote steht.

Schreibende Operationen gibt es hier bewusst nicht. Committen und Pushen
laufen über Claude, wo sie als Bestätigung bei dir landen. Ein Endpunkt, der
von sich aus pusht, wäre genau die Art Automatik, die man einmal zu oft
auslöst.

Die Fähigkeit `versionieren` (`.claude/skills/`) sagt Claude, wie hier
committet wird: erst prüfen, was mitgeht (keine Token, keine `.env`, keine
Artefakte), zusammengehörendes zusammen, Nachricht im Imperativ — und vor
jedem Push das **richtige Konto** wählen, wenn auf dem Rechner mehrere
GitHub-Konten angemeldet sind.

## Dienste-Dashboard

Was läuft gerade, und was nicht — über alle Geräte hinweg. Dienste **melden
sich selbst** (`POST /api/heartbeat`), iris fragt nie nach. Damit funktioniert
es auch für einen Pi im Heimnetz, den dieser Mac von unterwegs gar nicht
erreichen könnte.

Bleibt ein Herzschlag aus, gilt der Dienst als **vermisst** — der einzige
Zustand, den er nicht selbst melden kann.

Fertige Clients zum Kopieren liegen in `clients/` (Python und Shell), das
Schema steht in `docs/DIENSTE.md`. Ein neuer Dienst braucht drei Zeilen:

```python
from iris_heartbeat import Heartbeat
Heartbeat("bev-stitch", host="pi-head").start()
```

Zugangsdaten liefert `make ingest-token` — ein **eigenes, schwächeres Token**,
weil es am Ende auf jedem Pi liegt.

## Inventar der Maschine

Damit Claude nicht in jeder Unterhaltung neu herausfindet, wie diese Maschine
aussieht: 68 Projekte mit Art, Git-Konto, Zweig und Startbefehlen, 14
Umgebungen, alle lauschenden Dienste — in einer SQLite-Datenbank, abfragbar
über HTTP **und über MCP von Claude selbst** (`make install-mcp`).

Hält sich selbst aktuell: jede beendete Sitzung zieht ihr Projekt nach
(< 1 s). Ein vollständiger Lauf (`make scan`, knapp eine Minute) ist nur
nötig, wenn Projekte dazukommen. Details in `docs/INVENTAR.md`.

## Der Bewohner

`bewohner/` ist ein eigener, **optionaler** Teil: ein Begleiter, der
dauerhaft auf einem Windows-PC mit Grafikkarte läuft, mit einem lokalen
Sprachmodell (gpt-oss über Ollama) denkt, ein eigenes Gedächtnis führt und
über die iris-Brücke Claude Code beauftragt. Er kann sich von selbst melden,
an Termine erinnern und — mit Sprachausgabe — antworten.

iris braucht ihn nicht. Wer nur Sitzungen fernsteuern will, lässt den Ordner
liegen: die Brücke meldet dann einfach keinen, und die iPhone-App blendet
den Umschalter zu seiner Seite erst ein, wenn sie auf einem deiner Rechner
einen findet. Gesucht wird nebenher, ohne das Laden aufzuhalten.

Einrichten ist aufwendig und experimentell:

- Pakete: `bewohner/requirements.txt` — eigene Liste, getrennt von der der
  Brücke. Pflicht ist nur `httpx`; Bilder, PDFs und Sprache sind abgestuft
  optional, die Sprachausgabe bringt PyTorch mit.
- Was er braucht und was er selbst anlegt: `bewohner/GEDAECHTNIS.md`.
  Er beginnt mit leerem Gedächtnis; seine Werkzeuge bekommt er einmal mit
  `bewohner/einrichten.py`.
- Proben: `bewohner/pruefen.py` — bestanden, übersprungen, fehlgeschlagen,
  getrennt gezählt.
- Die Schnittstelle zur App: `docs/BEWOHNER.md`.
- Start auf Windows: `bewohner/aufgabe-einrichten.ps1`.

## Sicherheit

- Bindet auf die Tailscale-Adresse, nie auf `0.0.0.0`
- Zugang über ein Token in `~/.config/iris/config.json` (Modus 600);
  `make new-token` wirft alle Clients raus
- Bestätigungen sind **fail-closed**: keine Antwort, keine Ausführung.
  Auch wenn die Bridge wegbricht, wird abgelehnt statt durchgewunken.
- Die Vorgabe ist `permission_mode: manual` — unabhängig davon, was lokal
  in den Claude-Code-Einstellungen an Auto-Mode eingestellt ist.

## Nächster Schritt: die Brille

Belegt für die **RayNeo iO** (Start September 2026, 479 $): monochrom grün,
23,5° Sichtfeld, 1300 nits, 33 g. Bedient über eine **Krone** am rechten
Bügel — drehen, klicken, doppelklicken — dazu **Kopfgesten** (nicken = ja,
schütteln = nein) und Sprache. Die Pixelzahl gibt RayNeo nicht heraus; im
Simulator steht sie als Schätzung und ist an einer Stelle zu korrigieren
(`sim/apps.json`).

Wenn das SDK kommt, ist genau eine Funktion neu zu schreiben:
`attachInput()` in `web/glasses.js`. Sie erzeugt sechs Absichten — next,
prev, confirm, back, approve, reject. Alles darüber ist geräteunabhängig.

Zu Animationen: Anzeige und Eingabe laufen über BLE via Telefon, das reicht
grob für **5 Vollbilder je Sekunde**. Der Simulator drosselt darauf, damit
man es sieht statt es zu glauben. Springende Zustände tragen, fließende
Bewegung nicht.
