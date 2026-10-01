# Terminal-Sitzungen in iris

Claude-Code-Sitzungen, die in einem Terminal laufen, erscheinen in iris wie
eigene: live mitlesbar, mit Freigaben vom Handy und mit Nachrichten, die in
die laufende Sitzung gehen. Möglich machen das Hooks; wie sie sich verhalten,
ist in `BEFUNDE.md` nachgewiesen.

## Einrichten

```bash
make install-hooks     # trägt die Hooks in ~/.claude/settings.json ein
make hooks-status      # was ist eingetragen?
make uninstall-hooks   # nimmt nur die von iris wieder heraus
make check-hooks       # Ende-zu-Ende-Test gegen eine Brücke auf Port 8777
```

Vor jedem Schreiben entsteht eine Sicherung unter
`~/.config/iris/config-backups/`. Hooks, die schon da sind, bleiben
unangetastet. Die Hooks gelten für **jede** Sitzung, auch für bereits
laufende — die melden sich mit ihrem nächsten Werkzeugaufruf.

## Was woher kommt

| Information                        | Quelle                         |
|------------------------------------|--------------------------------|
| Sitzungs-ID, Transcript-Pfad       | `SessionStart` (oder jeder andere Hook) |
| Was Claude sagt                    | `MessageDisplay` — genau der Text, der erscheint |
| Was getan wurde                    | das Transcript, live mitgelesen |
| Was im Hintergrund läuft           | `PostToolUse` (`backgroundTaskId`, Ctrl+B), `SubagentStart/Stop`, die Liste in `Stop` |
| Dauer je Werkzeug                  | `PostToolUse.duration_ms`      |
| arbeitet / fertig / beendet        | `UserPromptSubmit`, `Stop`, `SessionEnd` |
| Freigabe                           | `PreToolUse`, von iris festgehalten |
| Nachricht vom Handy                | Antwort auf `Stop` bzw. `UserPromptSubmit` |

Jede Information hat genau eine Quelle. Claudes Text kommt nicht aus dem
Transcript: ein Satz vor einem Werkzeugaufruf wird dort mal viel später,
mal gar nicht geschrieben. `MessageDisplay` sieht, was Terminal und
Claude-App zeigen. Werkzeuge und Ergebnisse kommen dagegen nur aus dem
Transcript, die Dauer nur aus dem Hook.

**Neue Hook-Typen kommen in einer laufenden Sitzung verzögert an.** Als
`MessageDisplay` dazukam, blieb die laufende Sitzung zunächst stumm und
schickte es erst einige Züge später. Deshalb entscheidet iris die Textquelle
je Sitzung: bis `MessageDisplay` kommt, liefert das Transcript den Text, und
am Ende jedes Zugs `Stop` die letzte Antwort.

## Unterwegs

Freigaben gehen nur ans Handy, wenn in iris **Unterwegs** eingeschaltet ist
(oben in der Liste). Sonst lässt der Hook sofort durch, und am Rechner
erscheint der normale Dialog — wer dort sitzt, soll nie auf ein Handy
warten, das in der Tasche steckt.

Auch bei eingeschaltetem Unterwegs wird nicht alles festgehalten:

- lesende Werkzeuge nie (`Read`, `Grep`, `Glob`, `WebSearch`, …)
- nichts in den Modi `bypassPermissions`, `dontAsk`, `auto`, `plan` — dort
  hat der am Terminal schon entschieden, nicht gefragt zu werden
- in `acceptEdits` keine Dateiänderungen, wohl aber Shell-Befehle

Kommt vom Handy innerhalb von 9½ Minuten keine Antwort, wird abgelehnt —
dieselbe Regel wie bei iris' eigenen Freigaben. Fährt die Brücke herunter,
geht die Entscheidung an den Dialog im Terminal zurück.

## Nachrichten vom Handy

Eine Nachricht wird in den Terminal-Tab der Sitzung **eingetippt** – als
Einfügen mit anschließendem Return, genau als hätte man sie am Mac getippt.
Sie steht im Terminal als ganz normale Eingabe, Claude antwortet darauf, und
Terminal und Handy zeigen dieselbe Unterhaltung.

- **Sitzung ist fertig** (steht an ihrer Eingabe): sofort eingetippt.
  Antwort HTTP 200 `typed: true`, die Karte zeigt „im Terminal eingegeben".
- **Claude arbeitet noch:** direkt nach dem Zug eingetippt (HTTP 202, Hinweis
  „kommt direkt nach diesem Zug dran"). Die Nachricht rückt in der App an die
  Stelle, an der sie übergeben wurde – hinter die Antwort, auf die sie wartete.
- **Sitzung läuft nicht in Terminal.app** (Editor, anderes Terminal): dort kann
  iris nicht tippen. Die Nachricht geht mit der nächsten Eingabe am Rechner als
  Kontext mit, oder am Ende des laufenden Zugs über den `Stop`-Hook. Die App
  sagt genau das, statt „wartet" zu behaupten.

Getippt wird nur in den Tab, dessen tty zum claude-Prozess dieser Sitzung
gehört, und nur solange claude dort im Vordergrund läuft – geprüft im selben
AppleScript, das tippt. Ein Einfügen in eine blanke Shell würde als Befehl
laufen. Den Prozess zur Sitzung nennt Claude Code selbst in
`~/.claude/sessions/<pid>.json`; so ist auch eine Sitzung erreichbar, die
seit dem Start der Brücke keinen einzigen Hook geschickt hat.

**Anhalten** geht genauso: Ctrl+C in den Tab, nur solange Claude Code die
Sitzung selbst als „busy" führt, und nie zweimal kurz hintereinander – ein
Ctrl+C an leerer Eingabe macht das Beenden scharf.

Alle laufenden Sitzungen erscheinen in der App, auch die still stehenden:
die Brücke liest `~/.claude/sessions` alle paar Sekunden. Ist der Prozess
weg (Fenster geschlossen), gilt die Sitzung als beendet.

## Claudes Text und der Verlauf

Claudes Sätze kommen bei einer Sitzung in Terminal.app aus der **Historie des
Tabs** – dem, was das Fenster zeigt, samt allem, was nach oben weggescrollt
ist. Das Transcript lässt die meisten Sätze zwischen zwei Werkzeugaufrufen
weg, und `MessageDisplay` kommt in langen Sitzungen spät oder gar nicht. Das
Terminal zeigt sie immer. Gelesen wird vor jedem Werkzeugaufruf (so steht der
Satz vor dem Befehl, wie im Terminal), alle 1,5 s während Claude arbeitet und
am Zugende. Befehle und Ergebnisse kommen weiter aus dem Transcript.

Auf Linux/Pi gilt dasselbe für tmux (`capture-pane`). Ohne beides – Editor,
anderes Terminalprogramm – bleibt es bei `MessageDisplay`, sonst Transcript.

Jede Karte einer Terminal-Sitzung wird geschrieben nach
`~/.config/iris/feeds/<session_id>.jsonl` (0600), mit der Stelle, bis zu der
gelesen war. Nach einem Neustart der Brücke geht es genau dort weiter, und
die Nummern laufen weiter: öffnest du die App, kommt alles seitdem nach.
Aufgehoben werden die letzten 3000 Karten je Sitzung; vergessen wird eine
Sitzung zusammen mit ihr (beendet + 15 min, oder 12 h still).

## Modus und Auswahlfragen

- **Modus:** umgestellt mit Shift+Tab in den Tab, nach jedem Schritt an der
  Statuszeile abgelesen, höchstens einmal rundherum. Nur bei leerer Eingabe
  am Rechner und wenn Claude nicht arbeitet – jeder Tastendruck bringt ein
  Return mit, das sonst abschicken würde, was dort steht.
- **Auswahlfragen** (`AskUserQuestion`) stehen auf dem Handy wie bei eigenen
  Sitzungen. Unterwegs an: die Frage wird angehalten und die Antwort vom
  Handy als `updatedInput.answers` mitgegeben – im Terminal steht dann
  „User answered Claude's questions: … → Wahl". Kommt in 9½ Minuten keine
  Antwort, geht die Frage an den Dialog im Terminal. Am Rechner: der Dialog
  erscheint wie immer, eine Antwort vom Handy wird als Ziffer hineingetippt
  (freier Text über „Type something"). Getippt wird nur, wenn genau dieser
  Dialog auf dem Schirm steht. Wird am Rechner geantwortet, verschwindet die
  Frage vom Handy und die Wahl steht dort als deine Antwort.

## Was nicht geht

- **Das Modell** einer Terminal-Sitzung stellen: `/model` speichert es
  zugleich als Standard für alle neuen Sitzungen. iris sagt das (HTTP 409).
- **Mehrere Fragen auf einmal oder Mehrfachauswahl** am Rechner vom Handy
  aus beantworten – unterwegs geht es, am Rechner bitte dort.
- **Andere Terminal-Programme** als Terminal.app (und tmux): dort kommt die
  Nachricht erst mit der nächsten Eingabe an, Text kommt aus MessageDisplay
  bzw. dem Transcript.

## Kosten

Jeder Hook startet einmal Python und stellt eine Anfrage an die Brücke.
`make check-hooks` misst den Aufschlag je Werkzeugaufruf.
