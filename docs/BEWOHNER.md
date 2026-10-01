# Bewohner – Schnittstelle zwischen PC und App

Stand 11.09.2026. Plan: `docs/PLAN.md`, Abschnitt 6.

Aufteilung:
- **PC-Seite (Claude in der PC-Sitzung):** der Bewohner-Prozess – Takt,
  gpt-oss als Dirigent, Aufträge an Claude Code über die iris-Brücke,
  Arbeitsraum. Ort: `C:\Users\calvi\mcp-test\` (später ins iris-Repo, `resident/`).
- **Mac-Seite (Claude in der iris-Sitzung):** `bridge/resident.py` in der
  Brücke und die Bewohner-Seite der iOS-App. Die Brücke auf dem PC spielt die
  Mac-Seite ein; `C:\Users\calvi\iris\` nicht selbst ändern und die Brücke
  nicht neu starten.

**Die Schnittstelle sind die Dateien im Arbeitsraum.** Die Brücke liest sie
und reicht sie an die App weiter; was die App will (anhalten, wecken, Zuruf,
Antrag entscheiden), legt die Brücke als Datei hinein. Bitte genau so, sonst
passt die App nicht. Abweichungen vorher melden.

## Ort

`C:\Users\calvi\mcp-test\werkstatt\` – alle Dateien UTF-8, Zeitangaben als
Sekunden seit 1970 (float), Texte deutsch. Überschriebene Dateien immer über
eine temporäre Datei und `os.replace`, damit die Brücke nie eine halbe liest.

## Dateien, die der Bewohner schreibt

### `bewohner.json` – der Zustand, bei jeder Änderung überschrieben

```json
{
  "name": "Bewohner",
  "model": "gpt-oss:20b",
  "state": "wach",
  "since": 1789130000.0,
  "last_check": 1789130004.0,
  "watching": ["Dienste", "Ollama", "Platte", "Brücke", "werkstatt"],
  "budget": {"orders_hour": 1, "orders_hour_max": 4, "orders_today": 3},
  "brake": null,
  "session_key": "6d4b4f28b3c7",
  "open_task": "offen/comfyui-modelle.md",
  "pid": 12345,
  "updated": 1789130005.0
}
```

- `state`: `wach` (beobachtet), `denkt` (gpt-oss entscheidet),
  `arbeitet` (ein Auftrag an Claude läuft), `angehalten` (STOP liegt da),
  `fehler`, `beendet` (der Prozess ist regulär zu Ende).
- `brake`: warum gerade keine Aufträge an Claude gehen, sonst `null` – etwa
  `"Abo 5 h bei 62 % (Schwelle 50 %)"` oder `"du arbeitest gerade selbst"`.
- `session_key`: der iris-Schlüssel der Claude-Sitzung, die er beauftragt
  (die App markiert sie als „vom Bewohner“).

### `journal.jsonl` – nur anhängen, eine Zeile je Ereignis

```json
{"ts": 1789130000.0, "kind": "tick", "text": "nichts zu tun"}
{"ts": 1789130000.0, "kind": "fund", "text": "ComfyUI-Modelle: 33 GB seit 90 Tagen unbenutzt", "detail": "…was gpt-oss gesehen und warum es das meldet…"}
{"ts": 1789130060.0, "kind": "auftrag", "text": "Liste die ungenutzten Modelle mit Größe", "session_key": "6d4b4f28b3c7"}
{"ts": 1789130200.0, "kind": "ergebnis", "text": "12 Dateien, 33,4 GB", "session_key": "6d4b4f28b3c7", "seconds": 140}
{"ts": 1789130210.0, "kind": "pruefung", "text": "dir models\\checkpoints zeigt 12 Dateien", "ok": true}
{"ts": 1789130300.0, "kind": "antrag", "id": "a-1789130300", "text": "Zugriff auf hestia für OCR"}
{"ts": 1789130400.0, "kind": "entscheidung", "id": "a-1789130300", "text": "genehmigt"}
{"ts": 1789130500.0, "kind": "zuruf", "text": "Schlüssel liegt im Flur"}
{"ts": 1789130550.0, "kind": "pause", "text": "Auftrag zurückgehalten: du arbeitest gerade selbst", "detail": "…der Auftrag…"}
{"ts": 1789130600.0, "kind": "stop", "text": "angehalten über die App"}
{"ts": 1789130650.0, "kind": "weiter", "text": "weiter, STOP ist weg"}
{"ts": 1789130700.0, "kind": "fehler", "text": "Ollama antwortet nicht"}
```

- `text`: eine Zeile, so wie sie in der App steht. `detail`: optional, länger.
- `pause`: gpt-oss wollte handeln, die Bremse hielt den Auftrag zurück – nie als
  `tick`, sonst faltet die App ihn als „nichts zu tun“ weg.
- `tick` heißt: gpt-oss wurde gefragt und fand nichts zu tun. Die billigen
  Prüfungen dazwischen kommen nicht ins Journal, sie setzen nur `last_check`.
  Die App fasst leere `tick` grau zusammen. Mitteilungen gibt es nur für `fund`, `antrag`, `stop`
  (angehalten nicht durch dich) und `fehler` – die schickt die Brücke.

Zwei weitere Arten für Stufe 7, die Calvin erreichen: `erinnerung` (etwas,
woran er erinnert werden wollte, jetzt fällig – `text`) und `ansprache`
(etwas, das der Bewohner ihm von sich aus sagen will – `text`, optional
`audio`). Beide gehen als Push aufs Handy; eine `ansprache` liest die App
vor, wenn das Gespräch offen ist.

### `antraege/<id>.json` – eine Grenze verschieben nur auf Antrag

```json
{"id": "a-1789130300", "ts": 1789130300.0, "title": "Zugriff auf hestia",
 "reason": "Für OCR reicht der VRAM neben gpt-oss nicht.", "status": "offen"}
```

Die Brücke setzt `status` auf `genehmigt` oder `abgelehnt` und ergänzt
`decided` (Zeit). Der Bewohner liest das beim nächsten Takt, handelt danach
und schreibt `entscheidung` ins Journal.

## Dateien, die die Brücke hineinlegt

| Datei | Bedeutung | Der Bewohner … |
|---|---|---|
| `STOP` | anhalten | vergibt keine Aufträge mehr, Zustand `angehalten`, Journal `stop`. Weiter erst, wenn die Datei weg ist. |
| `WECKEN` | jetzt nachsehen | fragt sofort gpt-oss und löscht die Datei. |
| `zurufe/<ts>.md` | Zuruf von dir | liest ihn im nächsten Takt (oder sofort, wenn es geht), schreibt `zuruf` ins Journal, verschiebt nach `zurufe/gelesen/`. |

## Regeln, die zur Schnittstelle gehören

- **Arbeitszeit und Abo (Calvin, 11.09. abends) – ersetzt die Regel „du
  arbeitest gerade selbst“:** Die Regeln stehen in `werkstatt\regeln.json`,
  damit sie sich später in der App ändern lassen:

      {"arbeitszeit": {"tage": [1, 2, 3, 4, 5], "von": "07:00", "bis": "16:00"},
       "abo_schwelle": 0.85}

  `tage` nach ISO (1 = Montag), Uhrzeit Europe/Berlin. In der Arbeitszeit
  gehen keine Aufträge an Claude (`brake`: „Arbeitszeit – Aufträge ruhen bis
  16:00“); beobachten, nachdenken und reden bleiben erlaubt, das läuft lokal.
  Außerhalb: Aufträge, solange `five_hour.used` **und** `seven_day.used` unter
  `abo_schwelle` liegen. Fehlt die Datei, gelten diese Werte.
- **(alt, ersetzt)** Abo-Bremse: Vor jedem Auftrag an Claude `GET /api/usage` fragen. Liegt
  `five_hour.used` (Bruchteil 0…1) über 0,5, oder arbeitet eine Terminal-Sitzung
  gerade (`GET /api/sessions`: `terminal` und `busy`), keinen Auftrag geben und
  `brake` setzen. Nachdenken mit gpt-oss ist davon nicht betroffen.
- Aufträge nur an seine eigene Brücken-Sitzung, nie an eine Terminal-Sitzung
  (die Prüfung `terminal == true` aus `chain.py` bleibt).
- **Durchgehend wach, kein fester Takt** (Calvin, 11.09.): Billige Prüfungen
  laufen ständig – Dienste und Prozesse, Ollama, Platte, die Sitzungen der
  Brücke (`/api/sessions`, `/api/usage`), Änderungen in `werkstatt\` (auch
  `zurufe\`, `antraege\`, STOP, WECKEN). gpt-oss wird gefragt, sobald eine davon
  eine Veränderung meldet – nicht nach der Uhr. Ein Rundumblick in größerem
  Abstand ist nur die Rückfallebene. `last_check` zeigt der App, dass er wach ist
  (spätestens alle 60 s aktualisieren).
- Höchstens 4 Aufträge je Stunde; höchstens eine offene Aufgabe.
- Freigaben: Die Brücken-Sitzung fragt wie gewohnt übers iPhone – Calvin
  bekommt die Mitteilung und entscheidet. Nicht selbst auf „Auto“ stellen.
- Läuft auf dem PC als Aufgabe bei der Anmeldung (wie „iris Bruecke“), ohne
  Konsolenfenster: `pythonw`, Unterprozesse mit `CREATE_NO_WINDOW`.

## Arbeitsannahmen, bis du anders entscheidest

Name „Bewohner“, Arbeitszeit Mo–Fr 7–16 Uhr ohne Aufträge, sonst bis 85 % Abo, erste Zuständigkeit: der
Zustand des PCs und der Systeme darauf (siehe `mcp-test\PLAN.md`, Abschnitt 7).

## Gespräch – mit dem Bewohner reden, Stimme hin und zurück

Calvin spricht in der App (Spracheingabe auf dem iPhone), der Bewohner
antwortet, und die Antwort kommt gesprochen zurück – mit der Stimme vom PC
(Chatterbox, `C:\Users\calvi\tts-test\stimme.wav`). So kann er fragen, was der
Bewohner gerade macht, was er sieht, was er vorhat.

1. **Frage:** Die Brücke legt `gespraech\<id>.json` an:
   `{"id": "g-1789136500123", "ts": 1789136500.1, "text": "Was machst du gerade?", "status": "offen"}`
2. **Sofort, nicht im Puls:** `gespraech\` mindestens alle 0,5 s ansehen. Wer
   redet, wartet nicht fünf Sekunden auf den ersten Blick.
3. **Antworten mit gpt-oss**, mitgegeben: `bewohner.json`, die letzten ~30
   Journalzeilen, der aktuelle Blick (was er gerade sieht) und das bisherige
   Gespräch (die letzten 20 Wechsel, damit „und sonst?“ funktioniert).
   Gesprochen gedacht: 1–3 Sätze, keine Listen, kein Markdown, keine Pfade
   vorlesen, wenn es sich vermeiden lässt. Ehrlich, wenn er etwas nicht weiß.
4. **Journal in dieser Reihenfolge:**
   - `{"kind": "frage", "id": "g-…", "text": "Was machst du gerade?"}`
   - `{"kind": "antwort", "id": "g-…", "text": "…"}` – sobald der Text da ist;
     die App zeigt ihn sofort. In der Datei `status: "beantwortet"`, `answer`.
   - `{"kind": "stimme", "id": "g-…", "audio": "gespraech/g-….mp3", "seconds": 6.2}`
     – wenn die Aufnahme fertig ist.
5. **Stimme:** Chatterbox mit `stimme.wav`, Ausgabe als MP3 (mono, 22–24 kHz,
   rund 64 kbit/s), atomar nach `gespraech\<id>.mp3`. Chatterbox bleibt
   geladen (eigener kleiner Dienst oder im Bewohner-Prozess) – nicht für jede
   Antwort neu laden. **VRAM messen:** gpt-oss (~13 GB) und Chatterbox auf 16 GB.
   Passt es nicht: Chatterbox auf die CPU, oder gpt-oss mit kleinerem Kontext –
   Ergebnis mit Zahlen melden. Kommt nach 25 s keine Aufnahme, liest die App
   mit der iPhone-Stimme vor.
6. **Reden ist kein Auftrag:** Die Bremse gilt nicht fürs Antworten. Entsteht im
   Gespräch ein Auftrag („kümmer dich um X“), geht der den normalen Weg mit
   Bremse und Journal.
7. Gespräche älter als 7 Tage darf er aufräumen (json und mp3).
8. **Satzweise Stimme (für die Wartezeit):** Nicht erst die ganze Antwort
   sprechen, sondern jeden Satz als eigene MP3, sobald er fertig ist, und je
   Satz einen Eintrag:
   `{"kind": "stimme", "id": "g-…", "audio": "gespraech/g-…-1.mp3", "part": 1, "final": false}`
   … bis zum letzten mit `"final": true`. Die App spielt die Teile der Reihe
   nach, der erste läuft, während der zweite entsteht. Ein einzelner Eintrag
   ohne `part` gilt weiter als ganze Antwort.
9. **Uhrzeit und Datum** gehören in jeden Gesprächskontext – ohne sie rät das
   Modell („ungefähr elf Uhr“ um 17 Uhr).

Die Brücke dazu: `POST /api/resident/talk {"text"}` legt die Frage an und gibt
die `id` zurück, `GET /api/resident/audio?path=gespraech/<id>.mp3` liefert die
Aufnahme.

### Gesprächsmodus: ein echtes Gespräch (11.09.2026)

Calvin will reden wie mit einem Menschen: reinsprechen, die Antwort kommt von
selbst und laut, jederzeit dazwischenreden – aber nicht so empfindlich, dass
ein Geräusch den Satz abbricht.

- **Das Mikrofon bleibt offen**, das ganze Gespräch lang, auch während eine
  Antwort spielt (`playAndRecord`, Sprachverarbeitung des iPhones zieht die
  eigene Ausgabe ab). Zwischen zwei Äußerungen beginnt nur die Erkennung neu.
- **Erkennung:** auf iOS 26 Apples neuer Transkribierer (SpeechAnalyzer +
  SpeechTranscriber, auf dem Gerät, mit Satzzeichen) – deutlich genauer. Das
  deutsche Modell lädt beim ersten Mal im Hintergrund; bis dahin und bei
  jedem Fehler die bisherige Erkennung (SFSpeechRecognizer).
- **Satzende:** abgeschickt wird, wenn keine neuen Wörter mehr kommen *und*
  keine Stimme mehr zu hören ist (Pegel über einem mitlaufenden
  Grundrauschen). Wie lange: nach einem fertigen Satz (`.?!`) 1,1 s, nach
  Komma 2,4 s, nach „und“, „weil“, „ähm“, Artikel usw. 3,2 s, sonst 1,8 s.
  Ein Husten ist laut, bringt aber keine Wörter – er verlängert nur.
- **Reinsprechen:** eine Stimme macht die Antwort leiser; stoppen tun nur
  Wörter – „stopp“, „halt“, „warte“, „moment“ oder zwei Wörter, die nicht in
  der Antwort stehen (so zählt ein durchgerutschtes Echo nicht).
- **Entwurf:** bei der ersten Pause (0,6 s ohne neue Wörter) geht der Text
  bisher als `gespraech/<id>.json` mit `"status": "entwurf"`; dieselbe id
  kommt später mit `"offen"` und dem fertigen Text. Nur wenn `bewohner.json`
  `"faehig": ["entwurf"]` enthält. Auf einen Entwurf wird nie geantwortet.
- **Warteschlange:** eine Frage nach der anderen, Calvins vor Tests
  (`"von": "test"`). Die Brücke meldet die offenen (`offen`, ohne `antwort`)
  als `conversation.waiting`; die App zeigt, wie viele vor der eigenen stehen
  und ob der Bewohner gerade mit Tests beschäftigt ist.
- **Nachtrag:** was Calvin innerhalb von 30 s nachschiebt, solange seine Frage
  keine Antwort hat, geht mit `"zu": "<id>"` – der Bewohner bricht ab und
  beantwortet beides zusammen unter der früheren id.
- **Aufnahme:** eine gesprochene Frage bringt ihre Aufnahme mit –
  `gespraech/<id>.wav` (16 kHz, mono, 16 Bit, höchstens eine Minute), in der
  Frage-Datei als `"aufnahme"`. Für Stufe 7 „Stimme verstehen“: wie Calvin
  klang, nicht nur was er sagte.
- **Letzter Teil:** der letzte `stimme`-Teil einer Antwort trägt
  `"final": true`. Fehlt er, wartet die App 5 s nach dem letzten Teil und nimmt
  die Antwort dann als beendet – sonst hörte der Gesprächsmodus nie wieder zu.

## Wer er ist und was er sieht – Dateien für die App (Stufen 2–4)

Die App zeigt auf der Bewohner-Seite „Wer er ist“; die Brücke liest dafür
(`GET /api/resident/self`):

- `werkstatt\ICH.md` – von ihm selbst geschrieben. Die erste Zeile
  `# <Name>` ist sein Name (fehlt sie, hat er noch keinen), darunter freier
  Text. Calvin kann in der App korrigieren.
- `werkstatt\WUENSCHE.md` – ein Wunsch je Zeile als `- <Wunsch> – <warum>`.

**Nichts am Charakter ist fest eingebaut (Calvin, 11.09.).** Kein
vorgegebener Name, keine Namensliste, keine Charakter-Vorlage, keine
eingestreuten Eigenschaften oder Vorlieben, keine fertigen Antworten auf
„Wie geht es dir?“. Code und Prompt geben nur das Verfahren (über eigene
Erinnerungen und Journal nachdenken, `ICH.md` fortschreiben) und die Form
des Sprechens (kurz, Deutsch, keine Listen) – nicht, *wer* er ist. Sein
Charakter geht nur über `ICH.md` in den Prompt, und die schreibt er selbst,
aus dem, was er erlebt hat. Calvin darf korrigieren; wir erfinden nichts.
- `werkstatt\lage.json` – das Lagebild ohne Modell, laufend überschrieben:

      {"ts": 1789…, "tagesphase": "Nacht", "arbeitszeit": false,
       "rechner": {"last": 0.12, "platz_frei_gb": 412, "gpu_belegt_mib": 13100},
       "netz": [{"name": "iPhone von Calvin", "ip": "192.168.0.23", "seit": 1789…}],
       "calvin_zuletzt": 1789…}

- **Nach jeder Änderung neu starten und die Wirkung prüfen.** Eine Reparatur
  in einer Datei wirkt erst nach dem Neustart des Bewohners; sonst läuft
  stundenlang die alte Fassung weiter (12.09.2026: der Import war längst
  ergänzt, der Faden blieb tot). Geprüft wird nicht die Datei, sondern das
  Verhalten – am besten auf Calvins Weg.
- **Kein stummes Sterben.** Jeder Faden im Bewohner meldet beim Start eine
  Zeile „läuft“ und jeden Absturz als `fehler` ins Journal, und wird wieder
  gestartet. Sonst tickt er weiter und sieht nichts – so blieb ein Foto
  unbemerkt, weil der Wahrnehmungs-Faden beim Import gestorben war
  (12.09.2026). Eine Fähigkeit gilt erst als fertig, wenn sie auf Calvins Weg
  wirkt: gezeigte Datei wird beschrieben, gesprochene Frage wird gemessen.
- **Selbstwahrnehmung** gehört ins Lagebild (`lage.json` → `"selbst"`):
  tok/s, erster Ton, GPU dediziert/geteilt, verwaiste Runner, Ticks pro
  Minute. Er muss merken, wenn er selbst langsam, blockiert oder im Kreis ist
  (Calvin, 11.09.) – als `fund`, Beheben über Antrag.
- `werkstatt\werkzeuge.json` – eine Liste:
  `[{"name", "zweck", "aufruf", "erstellt", "geprueft": true|false}]`.
- `werkstatt\eingang\` – was Calvin ihm aus der App zeigt (Foto, Datei;
  `POST /api/resident/eingang` legt es hinein). Wahrnehmung wie bei Desktop
  und Downloads: verstehen, merken, nie als Auftrag.

## Gedächtnis – nächste Stufe (B5), erst nach Echtzeit und Antworten

Stand: gebaut in der Nacht 11./12.09.2026 (`mcp-test\gedaechtnis.py` auf dem PC,
Bericht `BERICHT-GEDAECHTNIS.md`). Grundlage ist die
Kartierung der PC-Sitzung: SQLite + Volltext (FTS5) + BGE-M3-Einbettungen,
alles auf der CPU – so treffsicher wie fertige Gedächtnis-Systeme, bei einem
Fünfzigstel der Kosten, und für Calvin einsehbar und korrigierbar.

### Zuerst: fertiges Framework prüfen (Calvin, 11.09.)

Sich Dinge vernünftig zu merken ist der schwere Teil – nicht das Suchen,
sondern das Pflegen: was hinein kommt, wann ein neuer Fakt einen alten
ersetzt, was zusammengefasst und was vergessen wird. Deshalb vor dem eigenen
Bau ein Vergleich mit dem Beweis-Test unten als Maßstab:

- **Mem0** (Open Source, selbst betrieben, Ollama + lokale Einbettungen): lässt
  das Modell je neuer Information entscheiden – hinzufügen, ändern, löschen,
  nichts tun.
- **Eigener Entwurf** (unten).
- Risiko, aus der Kartierung: Solche Frameworks brauchen striktes JSON vom
  Modell; im Cognee-Feldtest scheiterten alle sieben lokalen Modelle daran,
  gpt-oss eingeschlossen. Mit Ollamas `format` (JSON-Schema) kann es anders
  aussehen – das ist die eigentliche Messfrage.
- Entscheidung nach Zahlen: besteht Mem0 den Schlüssel-Test mit gpt-oss
  zuverlässig (5 von 5 Durchläufen), nehmen wir es als Speicher darunter und
  behalten Arbeitsraum, App-Schnittstelle und Kernwissen. Sonst eigener
  Entwurf mit Mem0s vier Operationen als Verfahren.
- Letta (MemGPT) nur als Blick, nicht als Kandidat: eigener Server, eigenes
  Agentenmodell – das würde den Bewohner ersetzen, nicht ergänzen.

**Entschieden: eigener Entwurf.** Schlüssel-Test mit gpt-oss und bge-m3,
beide lokal: eigener Entwurf 5 von 5, Mem0 3 von 5. Mem0 übersetzte die
Erinnerungen ins Englische („The key is in the hallway“), ersetzte den alten
Fakt nicht (Flur und Küche standen nebeneinander), brauchte je Merken einen
LLM-Durchlauf (2,6–4,3 s gegen 0,04 s) und meldet sich per Telemetrie nach
Hause. Übernommen haben wir Mem0s Gedanken, dass ein neuer Fakt einen alten
ersetzt – ohne Modell: der ähnlichste geltende Fakt ab Kosinus 0,80 wird
`ersetzt_durch` markiert, nichts gelöscht. „Merk dir, dass …“ erkennt ein
regulärer Ausdruck, der das Verb des Nebensatzes an Platz zwei zurückholt.

### Was er sich merkt

| Art | woher | Beispiel |
|---|---|---|
| **Ereignis** | jeder Journal-Eintrag außer leerem `tick`, ohne Modell | „17:09 Calvin bat, den Platz auf C: zu prüfen – zurückgehalten“ |
| **Gespräch** | jede Frage mit Antwort | „Calvin fragte, ob ich ihn höre“ |
| **Fakt** | wenn Calvin etwas festhält („merk dir …“, Zuruf mit einer Tatsache) – gpt-oss zieht Fakten mit festem JSON-Schema heraus | „Der Schlüssel liegt im Flur.“ |
| **Tagesrückblick** | einmal am Tag (nachts) von gpt-oss aus den Ereignissen | „Ruhiger Tag, ein Auftrag, zwei Anträge abgelehnt“ |
| **Kernwissen** | `werkstatt\ERINNERUNG.md`, von Calvin frei bearbeitbar, geht immer mit | Namen, Vorlieben, feste Regeln |

Neuere Fakten ersetzen ältere zum selben Thema (`ersetzt_durch`), statt
danebenzustehen – sonst weiß er zwei Orte für denselben Schlüssel.

### Ablage

`werkstatt\gedaechtnis.db` (SQLite):

    erinnerung(id, ts, art, text, quelle, wichtig, ersetzt_durch)
    erinnerung_fts   – FTS5 über text
    einbettung(id, vektor)  – BGE-M3, 1024 float32; Suche per Kosinus in numpy

### Abruf

Vor jeder Entscheidung und jeder Antwort: die Frage bzw. die Lage als Suche –
Volltext und Vektor, zusammengeführt (Reciprocal Rank Fusion), die besten
etwa 8 Treffer plus das Kernwissen, zusammen höchstens ~1500 Token. Uhrzeit,
Platz, Zustand kommen weiter vom Dienst, nicht aus dem Gedächtnis.

### In der App

Neuer Bereich „Gedächtnis“ auf der Bewohner-Seite: Suche, Fakten oben,
Ereignisse darunter; eine Erinnerung antippen → korrigieren oder vergessen.
Die Brücke liest `gedaechtnis.db` nur lesend (Liste, Volltext); Korrigieren
und Vergessen legt sie als Datei hinein (`gedaechtnis\aenderungen\<id>.json`),
der Bewohner übernimmt es – dieselbe Regel wie beim Rest: die Schnittstelle
sind Dateien.

Brücke: `GET /api/resident/memory?q=&art=&limit=&replaced=1` (neueste oder
beste Treffer, Anzahl je Art, wartende Änderungen), `GET …/memory?id=<id>`
(die Erinnerung und was sie ersetzt hat), `POST /api/resident/memory`
`{"id", "aktion": "vergessen"|"korrigieren", "text"}`. Der Bewohner löscht die
Änderungsdatei, sobald er sie übernommen hat; bis dahin zeigt die App sie als
wartend. Kernwissen (`ERINNERUNG.md`) ist über „Kernwissen“ im Gedächtnis
bearbeitbar.

### Beweis

1. „Merk dir, dass der Schlüssel im Flur liegt.“ → Fakt in der App sichtbar.
2. Bewohner neu starten, dann „Wo liegt der Schlüssel?“ → „Im Flur.“
3. „Der Schlüssel liegt jetzt in der Küche.“ → alter Fakt ersetzt, nicht doppelt.
4. In der App „vergessen“ → er weiß es nicht mehr.
5. Zeiten: Abruf < 100 ms, Antwortzeit steigt nicht spürbar.
