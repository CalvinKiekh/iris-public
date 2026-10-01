# Das Gedächtnis des Bewohners

Was der Bewohner über die Zeit sammelt — Erinnerungen, Chronik, Gespräche —
liegt in `werkstatt/` neben dem Code. **Es gehört niemals ins Git.** Es ist
das Leben eines bestimmten Menschen mit seinem Bewohner, und ein Repo wird
gepusht und weitergegeben.

Bis zum 29.09.2026 lief eine Sicherung davon unter `bewohner/sicherung/` im
Repo mit. Sie ist dort herausgenommen; die Dateien liegen weiter auf dem
Rechner, der spiegelt, nur nicht mehr im Git (`.gitignore`). Im älteren
Verlauf stehen sie noch — ein Repo aus dieser Zeit wird deshalb nie
weitergegeben, sondern nur eine Kopie aus `tools/uebergabe.py`.

## Neu anfangen: leeres Gedächtnis, aber seine Werkzeuge

Ein neuer Bewohner beginnt mit leerem Gedächtnis, und das ist richtig so.
Er legt `werkstatt/` beim ersten Start selbst an und jede Datei darin beim
ersten Schreiben. Fehlt eine, liest er sie als leer.

Eines aber wird vorher eingerichtet, einmal, mit

```
python -X utf8 einrichten.py
```

Das sind keine Erinnerungen, sondern das, womit er arbeitet:

- **Die zehn Werkzeuge** aus `bewohner/werkzeuge/` nach
  `werkstatt/werkzeuge/`. Er lädt sie nur von dort, und ein Teil seines
  eigenen Codes braucht sie (`erinnern`, `sehen`, `ansprechen`). Jedes geht
  durch seine eigene Abnahme — Quelltext lesen, `--selbsttest` laufen
  lassen — und wird erst dann in `werkzeuge.json` eingetragen. `lesen`
  besteht nur mit laufendem Ollama, `sehen` nur unter Windows.
- **`faehigkeiten.json`**: was in ihm eingebaut ist, mit Namen und Zweck,
  alles als noch nicht erprobt. Die Liste des ersten Bewohners bleibt
  draußen, weil sie seine Erlebnisse festhält.

Ein Recht bringt er schon im Code mit: `eingreifen.py` lässt ihn den
Ollama-Dienst neu starten, wenn der nicht antwortet, und verwaiste
`llama-server` beenden, die die Grafikkarte belegen, höchstens alle zehn
Minuten und mit Eintrag im Journal. Wer das nicht will, nimmt es dort heraus.

| Datei | Was darin steht | Wer schreibt |
|---|---|---|
| `gedaechtnis.db` | Erinnerungen und ihre Einbettungen (SQLite; Tabellen legt er selbst an) | `gedaechtnis.py` |
| `journal.jsonl` | die Chronik — was wann geschah; Rückblick und Anlässe lesen nur daraus | `bewohner.py` |
| `sitzungen.jsonl`, `sitzungen/` | jedes Gespräch im Wortlaut | `sitzung.py` |
| `bestand.json` | welche Erkenntnis unter welcher Kennung liegt | `bestand.py` |
| `pruefung.json` | welcher Verdacht schon vorgelegt wurde | `pruefung.py` |
| `anlaesse.json`, `ansprachen.jsonl` | was er von sich aus schon angesprochen hat | `anlaesse.py`, `werkzeuge/ansprechen.py` |
| `beschreibungen.json`, `gesehen.json` | ein Satz je gesehener Datei, und die Merkliste dazu | `wahrnehmung.py` |
| `platzverlauf.jsonl` | Messreihe des freien Speichers | `werkzeuge/platzverlauf.py` |
| `erinnerungen.json` | was er zu einem bestimmten Zeitpunkt melden soll — das Gegenstück zum Gedächtnis, das festhält, was war | `werkzeuge/erinnern.py` |

Die ersten Tage kosten deshalb etwas: `beschreibungen.json` entsteht aus
einem Modellaufruf je Datei, die er sieht, und Messreihen wie der
Platzverlauf sagen erst als lange Reihe etwas.

## Was vorher eingerichtet sein muss

Nicht das Gedächtnis, sondern die Umgebung:

- **`~/.config/iris/config.json`** mit deinem Namen, `"nutzer": {"name": "…"}`.
  Aus ihm leitet der Bewohner ab, wie du in seinen Daten heißt — **ändere
  ihn nicht mehr, sobald er Erinnerungen hat**, sonst erkennt er sie nicht
  mehr als deine.
- **Ollama** mit `gpt-oss:20b`, lokal auf `127.0.0.1:11434`.
- **Die iris-Brücke** auf demselben Rechner — über sie beauftragt er
  Claude Code.
- Optional die **Sprachausgabe**: eine Umgebung unter `~/tts-test` (oder
  `"bewohner": {"tts": "…"}` in der Konfiguration) und, für ElevenLabs,
  `~/.config/iris/elevenlabs.key`.
- Auf Windows startet ihn eine geplante Aufgabe:
  `bewohner/aufgabe-einrichten.ps1` in einer PowerShell ausführen.

## Prüfen

```
python -X utf8 pruefen.py
```

lässt jede Probe einzeln laufen und zählt dreierlei getrennt: bestanden,
übersprungen, fehlgeschlagen. Übersprungen wird, was hier fehlt — der
Bewohner selbst, ein Werkzeug, das Modell, Windows —, mit einem Satz dazu.
Wo kein Bewohner wohnt, laufen die meisten Proben trotzdem, in
Wegwerf-Ordnern. Und keine darf dort eine Werkstatt anlegen: `pruefen.py`
wertet das als Fehler.

Nicht darin: die `*_messung.py`, die Zahlen zum Vergleichen ausgeben statt
eines Urteils, und `schluesseltest_app.py`, das über die Brücke einen echten
Bewohner befragt und neu startet — nur von Hand.

## Sichern und zurückspielen

`bewohner/spiegeln.sh` holt die Dateien vom Rechner des Bewohners nach
`bewohner/sicherung/` — auf dem Rechner, der spiegelt, nicht ins Git. Die
Datenbank kommt über `sqlite3 .backup`, damit keine halb geschriebene Kopie
entsteht.

Zurück geht es von Hand: den Bewohner anhalten, die Dateien aus
`sicherung/` nach `werkstatt/` legen, wieder starten. Das ist Absicht — ein
Rückspielen überschreibt, was er seit der Sicherung gelernt hat, und das
soll nie ein Skript nebenbei tun.

Eine Sicherung auf nur einem Rechner ist eine halbe. Wer das Gedächtnis
behalten will, legt `sicherung/` zusätzlich woanders ab — nur eben nicht in
ein Repo.
