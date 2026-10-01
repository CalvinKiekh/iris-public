# Das Inventar

Claude fängt sonst in jeder neuen Unterhaltung von vorn an: Welche Projekte
gibt es, welche Sprache, wo liegt das venv, wie startet man die Tests, was
lauscht auf Port 8780. Dieselbe Arbeit jedes Mal, und sie kostet in jeder
Sitzung Tokens.

Das Inventar liest die Maschine einmal ein und beantwortet die Fragen danach
aus einer SQLite-Datenbank — über HTTP für die Oberflächen und über **MCP für
Claude selbst**.

## Was erfasst wird

| | |
|---|---|
| **Projekte** | Pfad, Name, Art (git, python, node, swift, docker, rust, go, make), Git-Remote, **GitHub-Konto**, Zweig, Änderungsdatum |
| **Befehle** | Make-Ziele, npm-Skripte, vorhandene `pyproject.toml`/`requirements.txt` — also *wie* man das Projekt baut und testet |
| **Umgebungen** | venvs mit Python-Version, Paketzahl und Platz auf der Platte |
| **Dienste** | was gerade auf welchem Port lauscht, mit Prozess und PID |

Stand hier: 68 Projekte, 14 venvs (4,5 GB), rund 20 lauschende Dienste.

## Aktualisieren

Ein vollständiger Durchlauf dauert knapp eine Minute — er läuft deshalb
**nie** im Vordergrund.

```bash
make scan                 # vollständig, im Vordergrund (für die Konsole)
```

```
POST /api/inventory/scan              # vollständig, im Hintergrund → 202
POST /api/inventory/scan {"project":"…"}   # nur dieses Projekt, < 1 s
GET  /api/inventory?what=state        # läuft gerade etwas, und woran
GET  /api/inventory?what=summary      # enthält `stale` und `age_seconds`
```

Von allein bleibt es aktuell, weil **jede beendete Sitzung ihr Projekt
nachzieht** — unter einer Sekunde, im Hintergrund. Ein vollständiger Lauf ist
nur nötig, wenn Projekte dazukommen oder verschwinden.

## Abfragen

```
GET /api/inventory?what=summary                     Überblick
GET /api/inventory?what=projects&kind=python        gefiltert
GET /api/inventory?what=projects&account=mein-konto
GET /api/inventory?what=search&q=hestia             gewichtete Suche
GET /api/inventory?what=envs&project=…
GET /api/inventory?what=services&refresh=1          live nachsehen
```

Die Suche ist **gewichtet**, nicht nur gefiltert: exakter Name, dann Name
enthält, dann Remote, dann irgendwo im Pfad. Ohne das versinkt ein kurzer
Name unter allem, was zufällig danebenliegt.

## Für Claude: der MCP-Server

```bash
make install-mcp      # trägt ihn in ~/.claude/settings.json ein (mit Sicherung)
make uninstall-mcp
```

Danach Claude Code neu starten. Fünf Werkzeuge, alle nur lesend:

| Werkzeug | wofür |
|---|---|
| `find_project` | „wo liegt hestia" — mit Zweig, Konto und Startbefehlen |
| `list_projects` | nach Art oder GitHub-Konto gefiltert |
| `project_environment` | welcher Interpreter, wie viele Pakete |
| `listening_services` | „läuft mein Dev-Server noch", „wer belegt 8780" |
| `machine_summary` | Überblick samt Alter des Inventars |

## Grenzen

- Gescannt wird `~/Documents` bis Tiefe 4. Andere Wurzeln: `ROOTS` in
  `bridge/inventory.py`.
- Übersprungen werden `node_modules`, `.git`, `venv`, `build`, `dist`,
  `DerivedData` und Ähnliches — sonst dauert der Lauf ein Vielfaches.
- Paketlisten werden **nicht** eingelesen, nur gezählt. Wer wissen will,
  welche Version installiert ist, fragt das venv direkt.
- Nur lesend. Das Inventar beschreibt die Maschine, es verändert sie nicht.
