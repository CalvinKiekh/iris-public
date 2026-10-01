# Wie iris funktioniert

**Der Name:** Iris ist in der griechischen Sage die Götterbotin. Sie trägt als
Regenbogen Nachrichten zwischen den Göttern und den Menschen hin und her. Das
ist die Aufgabe dieses Projekts: Botschaften zwischen dir und Claude auf
deinen Rechnern tragen, heute vom iPhone und von der Uhr, später von der
Brille.

Für alle, die etwas Ähnliches bauen wollen: Claude-Code-Sitzungen, die am
Mac im Terminal laufen, vom Handy aus sehen und steuern – ohne die Sitzung
selbst zu verändern und ohne Anthropic-API (alles läuft über das Abo).

Stand 10.09.2026, Claude Code 2.1.263, macOS 26. Geprüfte Einzelheiten und
Sackgassen stehen in [BEFUNDE.md](BEFUNDE.md).

## Das Bild im Ganzen

```
 iPhone-App ── HTTP + SSE (Tailscale, Token) ──▶ Brücke (Python, nur stdlib, am Mac)
                                                  │
     ┌────────────────────────────────────────────┼───────────────────────────┐
     │ sieht                                      │ steuert                   │
     │ • Hooks aus jeder Sitzung  (POST /api/hooks)│ • tippt in den Tab        │
     │ • ~/.claude/sessions/*.json (wer läuft)     │   (AppleScript do script) │
     │ • Transcript (Befehle, Ergebnisse)          │ • beantwortet Hooks       │
     │ • Tab-Historie (Claudes Text)               │   (Freigabe, Frage)       │
     └────────────────────────────────────────────┴───────────────────────────┘
                                                  │
                                    Terminal.app ─┴─ claude (interaktiv)
```

Es gibt zwei Arten von Sitzungen:

- **Eigene Sitzungen** startet die Brücke selbst als `claude -p
  --input-format stream-json --output-format stream-json`. Sie hat den
  Strom und einen Steuerkanal (`control_request`: Modus, Modell, Abbruch).
  Das ist der einfache Fall.
- **Terminal-Sitzungen** laufen, wie man sie am Mac gestartet hat, in
  Terminal.app. Von außen kommt man an sie nicht heran – kein Socket, keine
  API. Alles unten beschreibt, wie es trotzdem geht.

## 1. Erfahren, dass es eine Sitzung gibt

**Hooks.** In `~/.claude/settings.json` eingetragene Hooks laufen in *jeder*
Sitzung, auch in bereits laufenden (Claude Code liest die Datei nach). Ein
kleines Programm (`hooks/iris_hook.py`) schickt jeden Hook als JSON an die
Brücke und gibt deren Antwort zurück. Jeder Hook trägt `session_id`,
`transcript_path`, `cwd`, `permission_mode`.

Weil es bei jedem Werkzeugaufruf zweimal startet, zählt jede Millisekunde:
nacktes `socket` statt `urllib`, `python -S` → ~50 ms. Und es darf nie
stören: ohne Brücke sofort und wirkungslos durch, jeder Fehler endet in
`exit 0` ohne Ausgabe („mach weiter").

```python
# hooks/iris_hook.py, im Kern
payload = json.load(sys.stdin)
payload["iris_ppid"] = os.getppid()          # damit die Brücke den Tab findet
conn = socket.create_connection(("127.0.0.1", 8780), timeout=1)
conn.sendall(http_post("/api/hooks", payload))  # Antwort -> stdout, sonst nichts
```

**`~/.claude/sessions/<pid>.json`.** Claude Code führt dort jede laufende
interaktive Sitzung: `pid`, `sessionId`, `cwd`, `status` (idle/busy). Damit
sieht die Brücke auch Sitzungen, die seit ihrem Start keinen Hook geschickt
haben (die still an ihrer Eingabe stehen), und korrigiert „busy" nach einem
verpassten Zugende. ⚠️ Der `messagingSocketPath` darin gehört Remote Control.

## 2. Den Tab finden

Der Hook schickt die pid seines Elternprozesses mit. Die Brücke läuft den
Prozessbaum hoch (`ps -A -o pid,ppid,pgid,tpgid,tty,comm`) bis zum
`claude`-Prozess und nimmt dessen tty (`/dev/ttys009`). Terminal.app nennt zu
jedem Tab dessen tty – so passt beides zusammen.

Nur ein claude, der **im Vordergrund** seines Terminals läuft (`pgid ==
tpgid`), zählt. Sonst würde ein `claude -p`, das aus einer anderen Sitzung
heraus gestartet wurde, als deren Tab gelten.

## 3. Lesen

- **Befehle und Ergebnisse**: aus dem Transcript
  (`~/.claude/projects/<projekt>/<session_id>.jsonl`), laufend mitgelesen.
- **Claudes Text**: aus der **Historie des Tabs**. Das Transcript lässt die
  meisten Sätze zwischen zwei Werkzeugaufrufen weg, der Text-Hook
  (`MessageDisplay`) kommt in langen Sitzungen spät oder gar nicht. Das
  Terminal zeigt sie immer, und Terminal.app gibt die ganze Historie eines
  Tabs heraus (~500 KB in 0,2 s):

  ```applescript
  tell application "Terminal"
    repeat with w in windows
      repeat with i from 1 to count of tabs of w
        if tty of tab i of w is "/dev/ttys009" then return history of tab i of w
      end repeat
    end repeat
  end tell
  ```

  Auf dem Bildschirm beginnt ein Textblock mit `⏺ `, Fortsetzungen sind mit
  2 Leerzeichen eingerückt, Listenpunkte mit 4. `⏺ Name(` ist ein
  Werkzeugaufruf, `⎿` ein Ergebnis. Ein Block gilt erst als fertig, wenn etwas
  Eindeutiges folgt (nächster Block, Werkzeugaufruf, `❯`, „Worked for …",
  „(ctrl+o to expand)") – der Rand des Eingabefelds unter noch laufendem Text
  zählt nicht. Gelesen wird vor jedem Werkzeugaufruf (so steht der Satz vor
  dem Befehl), alle 1,5 s während Claude arbeitet und am Zugende. Wurde ein
  Block doch schon genommen, während er noch wuchs, kommt beim nächsten Blick
  nur sein Rest nach – nie der ganze Block ein zweites Mal.
  (`bridge/screen.py`)

## 4. Schreiben: in den Tab tippen

Nach dem Zugende läuft kein Hook mehr – eine Nachricht vom Handy hätte keinen
Weg in die Sitzung. Also tippt die Brücke sie in den Tab, als säße man davor:

```applescript
tell application "Terminal"
  set e to ASCII character 27
  do script (e & "[200~" & msg & e & "[201~") in theTab   -- Einfügen, dann Return
end tell
```

- `do script … in tab` schreibt in die Eingabe des Tabs, auch wenn dort ein
  Programm läuft, und hängt **immer** ein Return an.
- **Immer als Einfügen** (bracketed paste, ESC[200~ … ESC[201~). Schnell
  „getippter" Text ohne die Klammern hält Claude selbst für ein Einfügen –
  das Return landet darin, nichts wird abgeschickt.
- **Wann**: sofort – auch wenn Claude gerade arbeitet. Claude Code reiht
  Getipptes während eines Zugs ein und nimmt es nach dem laufenden Schritt
  auf, genau wie die Claude-App Nachrichten einschiebt. Nur wenn am Terminal
  ein Dialog offen ist (Freigabe, Auswahl), wartet die Nachricht, bis er zu
  ist – Getipptes würde dort eine Auswahl treffen.
- **Nichts bleibt liegen**: was wartet, liegt auf der Platte
  (`~/.config/iris/feeds/<id>.queue.json`) und übersteht einen Neustart der
  Brücke; alle paar Sekunden versucht sie es erneut.
- **Nur wenn sicher**: der Tab muss zur tty des claude-Prozesses gehören und
  claude muss dort laufen – geprüft im selben AppleScript, das tippt. Ein
  Einfügen in eine blanke Shell würde als Befehl ausgeführt.
- **Zustellung prüfen**: getippt ist nicht abgeschickt. Ein eingefügter
  Bildpfad wird zum angehängten Bild, und das Return geht dabei verloren.
  Deshalb prüft die Brücke danach, ob der Zug begonnen hat oder die Eingabe
  leer ist, drückt sonst noch einmal Return und meldet erst dann „eingegeben"
  – oder „nicht angekommen".

## 5. Steuern

| Was | Wie | Achtung |
|---|---|---|
| **Anhalten** | Ctrl+C in den Tab | Esc geht nicht: Esc + angehängtes Return = Alt+Return. Ctrl+C an leerer Eingabe macht das Beenden scharf – nur an einen laufenden Zug, nie zweimal. Danach legt Claude den alten Auftrag manchmal zurück in die Eingabe; ein zweites Ctrl+C leert sie. |
| **Modus** | Shift+Tab (ESC[Z), nach jedem Schritt die Statuszeile lesen | Nur bei leerer Eingabe – das Return würde sonst abschicken, was dort steht (auch einen grauen Vorschlag). |
| **Freigaben** | `PreToolUse`-Hook hält an (bis 570 s) und antwortet `allow`/`deny` | Nur wenn „Unterwegs" an ist; ohne Antwort: abgelehnt. |
| **Auswahlfragen** | Unterwegs: Hook hält an, Antwort als `updatedInput.answers`. Am Rechner: die Ziffer in den Dialog tippen, freier Text über „Type something". | Nur tippen, wenn genau dieser Dialog auf dem Schirm steht. |
| **Modell** | – | Nicht machen: `/model` speichert das Modell zugleich als Standard für alle neuen Sitzungen. |

## 6. Verlauf

Jede Karte einer Terminal-Sitzung wird mitgeschrieben
(`~/.config/iris/feeds/<session_id>.jsonl`, nur für den Benutzer lesbar),
zusammen mit der Stelle, bis zu der gelesen war. Nach einem Neustart der
Brücke geht es genau dort weiter, und die Nummern laufen weiter. Die App
fragt mit der letzten Nummer, die sie kennt (`/events?since=N`), und bekommt
alles seitdem – auch, was passierte, während sie zu war.

## 7. Die Apps

Es gibt zwei: das iPhone und den Mac. Was beide gleich zeigen – Verbindung
zur Brücke, Karten, Unterhaltung, Übersicht, Warteschlange, Theme – liegt in
`shared/`; die iPhone-App bindet den Ordner über ihr Xcode-Projekt ein, die
Mac-App (SwiftPM, wie WindowSnap) über einen Link in ihre Quellen. Die
Mac-App liegt unter `/Applications`, hat ein Dock-Symbol **und** einen
Menüleisten-Eintrag, und verbindet sich selbst mit der Brücke auf demselben
Rechner. (Sie lief lange mit `LSUIElement`, also ohne Dock-Symbol und ohne
Cmd-Tab — auf einem Gerät mit Notch schiebt sich der Menüleisten-Eintrag
hinter die Notch, und dann ist das Programm faktisch nicht erreichbar.)

Das Fenster hat **zwei** Spalten: die Sitzungen links, das Gespräch daneben.
Was die Sitzung ausmacht — Modus, Kontext, geänderte Zeilen, Dienste — steht
**über** dem Gespräch statt in einer dritten Spalte; es bleibt so im Blick,
ohne dem Text Breite zu nehmen. Die linke Spalte lässt sich über den Knopf
oben links ein- und ausklappen, und die Wahl bleibt über Neustarts erhalten.
Unter 820 Punkten Fensterbreite klappt sie von selbst weg und kommt als Panel
über das Gespräch, das sich beim Klick daneben wieder schließt. Das Fenster
geht bis 520 Punkte herunter, passt also auf eine halbe Bildschirmseite.

- **Verlauf auf dem Gerät**: jede Karte, die ankommt, wird mitgeschrieben
  (im Cache des Geräts, samt der letzten Nummer). Öffnet man eine Sitzung,
  steht der Verlauf sofort da, und von der Brücke kommt nur, was seitdem
  dazukam. Fängt die Brücke doch bei null an, wird einmal ganz neu geladen.
- **Im Schwung zeichnen**: eintreffende Karten werden gesammelt und alle
  80 ms in einem Rutsch verarbeitet. Einzeln lief die Unterhaltung nach jeder
  Karte neu durch das Layout – ein Rückstand von 3000 Karten dauerte Minuten.
- **Auffrischen im Hintergrund**: für die zuletzt geöffneten Sitzungen holt
  die App regelmäßig den Rest – auf dem iPhone als Hintergrundaufgabe (alle
  15 Minuten frühestens; wann genau, entscheidet iOS), auf dem Mac im
  15-Minuten-Takt.

- Nachrichten gehen immer über eine **Warteschlange auf dem Handy**: ist die
  Brücke nicht erreichbar, bleibt die Nachricht dort (auch über einen
  App-Neustart), die App zeigt „wartet auf Verbindung" und „Mac nicht
  erreichbar" und schickt nach, sobald die Brücke antwortet.
- Verworfen wird eine wartende Nachricht nur, wenn die Brücke sie
  ausdrücklich ablehnt (eine Antwort mit Status, etwa „Sitzung ist beendet").
  Alles andere – kein Netz, abgelehnte oder abgerissene Verbindung, Zeitüberschreitung –
  heißt: später nochmal. (`ios/Iris/Outbox.swift`)
- Jede Nachricht hat eine **Kennung**. Ist ein Versuch angekommen, aber die
  Antwort verloren gegangen, erkennt die Brücke die Wiederholung und schickt
  sie nicht noch einmal.
- **Push** direkt an Apple (APNs) mit `curl --http2` und einem selbst
  signierten ES256-Token (`openssl`) – kein Server, keine Pakete.

### Was die Sitzungsansicht zeigt

- **Kopf**: Pfad neben der Art der Sitzung, darunter der Titel. Die nächste Zeile
  beginnt mit dem Zustand („läuft seit 4:12“, „bereit“, „Mac nicht erreichbar“),
  daneben stehen, was sich aufklappen lässt („im Hintergrund“, „Seiten“), rechts
  „unterbrechen“ — nicht „anhalten“, denn fortsetzen lässt sich der Zug nicht,
  er endet, wo er steht. Darunter die Zahlen: Kontext, geänderte Zeilen,
  Dienste. Sie brechen um, gescrollt wird nichts.
- **Abo-Limit**: Das 5-Stunden-Fenster steht im Kopf jeder Sitzung („42 %
  5-h-Limit“), auf dem Startbildschirm dazu die Rücksetzzeit und die Woche.
  Quelle ist die Statuszeile von Claude Code: iris trägt `iris_hook.py
  --statusline` als statusLine ein (nur wenn keine eigene gesetzt ist). Sie
  gibt nichts aus, reicht aber `rate_limits` und `context_window` an die
  Brücke (`GET /api/usage`). Bei 80 und 95 % kommt je eine Mitteilung. Ist ein
  Fenster aufgebraucht, steht im Transcript ein API-Fehler mit `quotaLimits`
  (status „rejected“, resetsAt): Dann kommt sofort „Limit erreicht – wieder frei
  um 18:40“ als Mitteilung und als Karte im Verlauf. Von weitem sähe eine
  Sitzung, die nicht mehr antwortet, sonst wie hängengeblieben aus. Von der
  Brücke gestartete Sitzungen melden dasselbe über rate_limit_event.
- **Kontext**: Auch Terminal-Sitzungen zeigen, wie voll der Kontext ist. Die
  Brücke liest aus dem Transcript, mit wie vielen Tokens die letzte Antwort
  geschickt wurde (Eingabe plus Cache). Das Fenster steht nicht im Transcript:
  „[1m]“ im Modell der Einstellungen oder mehr als 200.000 belegte Tokens heißt
  1 Million, sonst 200.000.
- **Arbeitszeile**: Solange Claude arbeitet, steht direkt unter der laufenden
  Arbeit die Zeile, die das Terminal als Spinner zeigt, zum Beispiel
  „✽ Deciphering… · führt einen Befehl aus“. Die Brücke liest sie vom Bildschirm
  und schickt sie nur, wenn sich das Wort ändert.
- **In den Hintergrund**: Läuft gerade ein Shell-Befehl, steht in der
  Eingabezeile ein Knopf, der Ctrl+B in den Tab schickt — der Befehl läuft
  weiter, der Zug wartet nicht mehr auf ihn. Nur bei `Bash`, nicht während
  Claude nachdenkt: Ctrl+B täte dort nichts. Er sitzt bei den anderen Knöpfen
  der Eingabe und nicht im Gespräch, weil eine maskierte Ansicht keine Klicks
  annimmt (siehe `docs/BEFUNDE.md`).
- **Antwort kopieren**: Unter jeder Antwort ein Knopf, der sie am Stück in die
  Zwischenablage legt; dasselbe im Kontextmenü, was der Weg auf dem iPhone ist.
  Auswählen mit der Maus reicht immer nur über einen Block — Absatz, Liste und
  Tabelle sind je ein eigener Text.
- **Bilder**: Ein Bild, das die Sitzung gelesen hat, steht unter der
  Read-Zeile; ein Klick zeigt es groß, Esc schließt es wieder.
- **Dateien anhängen**: über `+`, durch Ziehen auf die Bühne, oder mit Cmd+V.
  Ziehen und Einfügen lesen die Ablage direkt — ein Bildschirmfoto aus der
  Vorschau und ein Bild aus dem Browser tragen die Bilddaten und keine Datei.
- **Wartende Nachrichten**: Was während der Arbeit eingegeben wird, am Mac oder
  auf dem Handy, stellt Claude Code in eine Warteschlange. Die App zeigt es grau
  unter der Arbeitszeile, bis Claude es übernimmt. Grundlage sind die
  `queue-operation`-Einträge im Transcript: enqueue, dann remove oder dequeue.
- **Zusammenfassung**: Wenn der Kontext voll war, steht eine zugeklappte Zeile
  „Sitzung zusammengefasst“ da. Antippen zeigt die Zusammenfassung.
- **Seiten**: Seiten, die die Sitzung veröffentlicht hat, zum Beispiel
  Design-Entwürfe, stehen als Liste zum Antippen im Kopf. Die zuletzt geänderte
  steht oben.
- **Befehle**: Das „/“ oben öffnet alle Befehle. Das sind die von Claude Code,
  gelesen aus dem installierten Programm und damit passend zur Version, dazu
  die Skills und die eigenen Befehle. Hinter dem „?“ erklärt jeder Befehl auf
  Deutsch, was er tut, und gegebenenfalls, warum er nur am Mac geht:
  - Befehle, die im Terminal eine Ansicht öffnen, lassen sich vom Handy nicht
    schließen.
  - `/model` stellt das Modell für alle Sitzungen um.

  Tippt man „/“ ins Eingabefeld, schlägt die App passende Befehle vor. Ein
  gewählter Befehl steht als Marke vor dem Text, der Text kommt dahinter.
- **Bildschirm des Terminals**: Befehle, die im Terminal eine Ansicht öffnen
  (`/status`, `/config`, `/resume` …), sind vom Handy aus nutzbar. Die App
  zeigt den Bildschirm des Tabs live, jede Sekunde neu. Dazu gibt es Esc zum
  Schließen, Enter und ein Feld zum Eintippen. Blättern mit den Pfeiltasten
  geht nur am Mac, Einzelheiten in BEFUNDE unter „CSI 27 u“. Gesperrt bleiben
  nur Befehle, die mehr als diese Sitzung ändern (`/model`), die Sitzung von
  iris lösen (`/background`, `/teleport`) oder einen Editor öffnen.
- **Strom**: Die Brücke prüft alle 20 Sekunden, ob der Mac am Strom hängt. Wird
  das Kabel gezogen, kommt sofort eine Mitteilung, solange der Mac noch
  erreichbar ist. Im Akkubetrieb geht er bald schlafen, und die Sitzungen
  halten an. Schläft er, merkt die App das nach spätestens 45 Sekunden Stille.
- **Neue Version**: `ios/device.sh` spielt die App aufs iPhone, das geht auch
  bei gesperrtem Bildschirm. Danach schickt es eine Mitteilung „iris 1.0.N ist
  drauf“. Die Nummer kommt aus `tools/version.sh`.

### Mehrere Rechner

- Die App führt eine Liste von Rechnern, auf denen je eine Brücke läuft,
  zum Beispiel Mac, Windows-PC oder Pi. Jeder hat seinen eigenen Zugangsschlüssel
  im Schlüsselbund, der nur die Sitzungen auf diesem Rechner öffnet.
- Auf dem Startbildschirm steht unter „Sitzungen“ die Zeile der Rechner, der
  aktive in Messing. Ein Tipp schaltet um. Mit „+ Rechner“ fügt man einen
  weiteren hinzu, über die Adresse, die `make token` dort zeigt. Auf dem Mac
  steht die Zeile in der Seitenleiste, und der Mac selbst ist immer als
  „Dieser Mac“ drin.
- Die frühere einzelne Verbindung wird beim ersten Start zum ersten Eintrag
  der Liste.
- **Umbenennen**: Den Titel einer Sitzung lange drücken, oder eine Zeile in
  der Sitzungsliste, dann „Umbenennen“. Das geht auf dem iPhone und in der
  Mac-Seitenleiste. Den Namen speichert die Brücke in `names.json` neben ihrem
  Zustand, zugeordnet über Claudes Sitzungskennung. Er gilt auf allen Geräten
  und bleibt auch beim Fortsetzen erhalten. Er schlägt jeden automatischen
  Titel. Leer lassen gibt den automatischen Titel zurück.
- **Neue Sitzung**: Unter der Rechner-Zeile steht „+ Neue Sitzung“, auf dem
  iPhone auf dem Startbildschirm, auf dem Mac in der Seitenleiste. Ein Tipp
  zeigt die Projekte des gewählten Rechners und ein Feld für einen anderen
  Ordner. Die Sitzung startet dort als von der Brücke gestartete Sitzung, und
  die App springt direkt hinein.
- Das Handy meldet sich für Mitteilungen bei allen Rechnern an. Jede
  Mitteilung nennt den Rechner, von dem sie kommt. Ein Tipp darauf öffnet
  diesen Rechner, und Antworten von der Mitteilung aus gehen dorthin zurück.
- **Windows**: Die Brücke läuft dort mit Python 3.10. Für Freigaben nimmt sie
  statt eines Unix-Sockets eine TCP-Verbindung auf 127.0.0.1, die nur vom PC
  selbst erreichbar ist.
- **In Windows-Konsolen tippen**: Der „Tab“ einer PC-Sitzung ist die Konsole
  ihres claude-Prozesses (`con:<pid>`, auch in Windows Terminal). Für jeden
  Zugriff startet die Brücke `python -m bridge.wincon` als eigenen Prozess:
  Er hängt sich mit AttachConsole an, schreibt Tasten mit WriteConsoleInput und
  liest den sichtbaren Bildschirm mit ReadConsoleOutputCharacter. Ein eigener
  Prozess, weil das Anhängen für den ganzen Prozess gilt – eine angehängte
  Brücke würde die Konsole an alles vererben, was sie gerade startet. Esc,
  Shift+Tab und Ctrl+C gehen als echte Tasten; mehrere Zeilen als eine
  eingeklammerte Einfügung, damit kein Return dazwischen abschickt. Damit gehen
  auf dem PC Nachrichten, Antworten auf Fragen mit Auswahl, Esc für Ansichten
  und der Moduswechsel wie am Mac. Voraussetzung: Die Brücke läuft in der
  angemeldeten Windows-Sitzung (Aufgabe „iris Bruecke“, /it) – aus einer
  SSH-Sitzung heraus lässt sich keine Konsole anhängen.

## 8. Eine Sitzung mitnehmen

Eine Sitzung auf einem anderen Rechner fortsetzen: der Stand reist über git,
der Verlauf als Abzweig, und was git nicht annimmt, geht versiegelt über die
Brücke.

### Das Blatt

Der Knopf „mitnehmen" steht neben den Zahlen einer Sitzung und **nur**, wenn
das Arbeitsverzeichnis ein GitHub-Remote hat — ohne Remote gäbe es nichts zu
klonen. Das Blatt selbst liegt in `shared/Uebergabe.swift` und ist auf Mac
und iPhone dasselbe; nur der Rahmen unterscheidet sich.

Es zeigt, was der Übergabe im Weg steht (ungesicherte Dateien, nicht
gepushte Commits, kein Upstream), wie groß der Verlauf ist, auf welchem
Rechner gearbeitet wurde — und was **nicht** mitreist.

### Der Auftrag

Committen und pushen ändern etwas außerhalb dieses Rechners, also tut die
Brücke es nicht. Der Knopf schickt einen Auftrag als Nachricht an die
Sitzung, den du wie jeden anderen Befehl freigibst. Er verlangt zwei Dinge:
erst `UEBERGABE.md` schreiben — woran gearbeitet wird, was offen ist, womit
gebaut wird, was nur hier läuft —, dann alles samt dieser Datei committen und
pushen.

Dass die Sitzung diesen Zettel selbst schreibt, ist eine Entscheidung. Ein
Versuch, die Werkzeugkette aus Makefiles und Skripten zu lesen, steht
bewusst nicht mehr im Code: er meldete `$(MAKE)` als Programm und übersah
swift, xcodebuild und xcodegen, weil die Bau-Dateien in Unterordnern liegen.
Die Brücke steuert nur bei, was sie sicher weiß — Betriebssystem, Chip,
Kerne, Speicher (`bridge/maschine.py`).

### Große Dateien, versiegelt

GitHub warnt ab 50 MB und lehnt ab 100 MB ab. Die Tabelle, die mitmuss, ist
genau die Datei, die git nicht nimmt. Sie geht deshalb an git vorbei, und
zwar versiegelt — nicht weil der Weg unsicher wäre, sondern weil sie
unterwegs zwischengelagert wird.

AES-256-GCM, ein frischer Schlüssel je Übertragung (`bridge/transfer.py`).
Sechs Regeln, die nicht verhandelbar sind:

1. **Zähler-Nonce.** Ein wiederholter Nonce unter demselben Schlüssel
   schwächt GCM nicht, er gibt den Authentisierungsschlüssel preis.
2. **Siegel vor Verwendung.** GCM liefert Klartext, bevor es prüft — also
   erst vollständig in eine Temp-Datei, umbenannt wird nach der Prüfung.
3. **Ziel auf das Arbeitsverzeichnis begrenzt.** Ein Dateiname von der
   Gegenseite ist gefährlicher als der Schlüssel.
4. **Einmalschlüssel.** Das Ticket wird vor dem Lesen aus dem Speicher
   genommen, nicht nach Ablauf.
5. **Der Aufkleber wird vom Ziel gebaut**, aus dem, was es selbst weiß.
6. **Der Schlüssel geht nie** in eine Karte, die Spur oder eine Push-Nutzlast
   — dort liegen die Sitzungskennungen im Klartext.

Was das **nicht** schützt, damit sich niemand darauf verlässt: ein
übernommenes Zielgerät, eine übernommene Brücke, und die Datei nach dem
Ablegen. Schlüssel und Klotz nehmen denselben token-gesicherten Weg — es ist
ein Schloss, nicht zwei.

### Wer trägt

Die **App** ist der Kurier (`shared/Kurier.swift`). Die Brücken kennen
einander nicht; die App hat beide Token ohnehin. Würde die Quelle direkt
ans Ziel liefern, bräuchte sie dessen Token — ein Rechner bekäme Zugriff auf
einen zweiten, nur damit eine Datei umzieht. Der Klotz geht dabei auf die
Platte, nicht in den Speicher.

Den Namen des Zielrechners erfragt der Kurier beim Ziel selbst (`/api/health`).
Der Name in der Maschinenliste ist nur ein Zettel — der eigene Mac steht
dort als „Dieser Mac", während seine Brücke sich `maro` nennt.

### Die Endpunkte

| | |
|---|---|
| `POST /api/sessions/<key>/ausgang` | versiegeln, gibt den Schlüssel einmal zurück |
| `GET /api/ausgang/<id>` | den versiegelten Klotz holen |
| `POST /api/eingang/schluessel` | Schlüssel abgeben, bekommt ein Ticket |
| `POST /api/sessions/<key>/eingang/<ticket>` | Klotz einspielen |
| `POST /api/ausgang/weg` | Zwischenlager räumen |

## 9. Fallen, in die wir getreten sind

- `contents of t` auf einer `repeat with t in tabs`-Variablen liefert den
  Verweis („tab 1 of window id …"), nicht den Text. Über den Index gehen.
- Der Text im Terminal kann anders formuliert sein als der, den das Modell
  geschrieben hat – es ist die angezeigte Fassung.
- Tests aus einer Sitzung heraus starten `claude -p` im selben tty – ohne die
  Vordergrund-Prüfung tippt man in die eigene Sitzung.
- In Versuchssitzungen nur neutralen Text tippen: eine echte Nachricht wird
  im Auto-Modus als Auftrag verstanden.
- `~/Documents` liegt in iCloud; dessen Dateiattribute lassen `codesign`
  scheitern – Xcode-Builds außerhalb bauen.

### Der Hook startet über einen Starter

In `~/.claude/settings.json` steht `~/.config/iris/hook.py`, nicht der Hook
selbst. Der Starter liegt außerhalb der von macOS geschützten Ordner und
führt `hooks/iris_hook.py` aus, wenn er ihn lesen kann — sonst endet er still
mit 0. Ohne ihn blockierte eine fehlende Freigabe für `~/Documents` jede
Eingabe in jeder Sitzung (siehe `docs/BEFUNDE.md`). `make install-hooks`
schreibt ihn neu; der Hook selbst wird nicht kopiert, Änderungen wirken sofort.

## 10. Wie es geprüft wird

- `tests/tippen.py` öffnet echte Terminal-Fenster mit echten Sitzungen gegen
  eine eigene Testbrücke: fertige und arbeitende Sitzung, Text zwischen
  Befehlen, Neustart, Foto, Anhalten, Modus, Fragen, Sitzung ohne Hooks.
- `tests/hooks.py`: die Hooks mit `claude -p`-Läufen.
- `tests/transfer.py` (31) und `tests/transfer_http.py` (19): die
  Verschlüsselung für sich und der ganze Weg durch den echten Handler. Neun
  der Prüfungen sind Angriffe — fremder Zielrechner, fremde Sitzung,
  gekipptes Byte, vertauschte Blöcke, abgeschnittener Strom, angehängter
  Müll, zweites Einspielen, `../` im Namen, vorhandene Datei.
- `tests/anhang.py` (14): ob ein Foto im Terminal auch abgeschickt wird und
  nicht nur in der Eingabe steht.
- `tests/markdown.py`: Markdown aus Terminal-Sitzungen, beide Textwege.
- `make ios-test`: UI-Tests im Simulator; ein kleiner Zwischenhändler
  (`ios/tools/offline_proxy.py`) kappt dabei auf Zuruf die Verbindung.
