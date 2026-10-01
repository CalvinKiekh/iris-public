# iris am iPhone

Native SwiftUI-App (`ios/`), gestaltet nach dem Designschema in `design/` —
nicht nach dem Aussehen anderer Apps. Sie spricht dieselbe Brücke wie die
Web-Oberfläche: JSON über HTTP, der Kartenstrom über SSE.

## Bauen und ansehen

```bash
make ios-run                              # bauen, im Simulator starten, Foto
IRIS_OPEN=last make ios-run               # gleich die zuletzt aktive Sitzung
IRIS_OPEN=MacBook IRIS_SHOT=x make ios-run  # Sitzung nach Titel, Foto ios/build/x.png
```

Gerät ist der Simulator eines iPhone 17 Pro Max. Xcode wird über
`DEVELOPER_DIR` gefunden, weil `xcode-select` auf die Command Line Tools
zeigt — kein `sudo` nötig. Das Projekt erzeugt XcodeGen aus
`ios/project.yml`; die `.xcodeproj` steht nicht im Git.

Im Simulator braucht es keinen eingefügten Schlüssel: `run.sh` gibt die
Adresse der laufenden Brücke über `IRIS_URL` mit (nur im Debug-Bau). Am
echten Telefon wird einmal die Adresse aus `make token` eingefügt; der
Schlüssel liegt danach im Schlüsselbund.

## Wie das Design hineinkommt

- **Werte aus den Artboards**, nicht nachempfunden: `Theme.swift` hält
  Farben, Schriften und die vier Materialien — Licht im Raum, Korn,
  Tinte, Messingkante.
- **Schriften** sind dieselben wie im Entwurf (Cormorant Garamond, Outfit,
  JetBrains Mono), als TTF in `ios/Iris/Fonts/`.
- **Tinte und Korn** rechnet `ios/tools/textures.py` aus genau den
  SVG-Filtern des Entwurfs, nach der Referenzimplementierung von
  `feTurbulence` in der SVG-Spezifikation — gleicher Zufallsgenerator,
  gleicher Seed. QuickLook taugt dafür nicht: es drückt die Transparenz
  auf Weiß.
- Die Tinte wird **gegen den Raum** gemischt, nicht gegen die eigene
  Füllung einer Fläche — eine fast durchsichtige Füllung gibt dem weichen
  Licht nichts zum Mischen, und die Tinte erschiene roh als blasse Wolke.

## Was die App kann

- Übersicht: laufende Sitzungen (eigene und aus dem Terminal), Projekte,
  der Unterwegs-Schalter, das Abo-Kontingent.
- Sitzung: Verlauf mit Stern und Ring, Werkzeugzeilen mit Ziel und Dauer
  (Fehlschläge nie eingeklappt, Grund darunter), Kontext, Git-Bilanz,
  Dienste, Laufzeit, Modus zum Umschalten.
- Freigaben mit dem, was freigegeben wird: Befehl oder Zeilen der Änderung.
- Auswahlfragen als Liste zum Abhaken; freier Text in der Eingabe
  beantwortet sie auch.
- Claude-Antworten in Markdown mit iris' Schriften: Tabellen als Zeilen
  aus Beschriftung und Wert, Code in Mono.
- Diktat auf Deutsch, auf dem Gerät.
- Anhänge über „+" in der Eingabe: Fotos (als JPEG, auf 1600 Punkte
  verkleinert — HEIC nimmt Claude nicht) und Dateien. Die Brücke legt sie
  unter `~/.config/iris/uploads/` ab, nie in einem Projekt. Eigene Sitzungen
  bekommen Bilder direkt in die Nachricht, Terminal-Sitzungen den Pfad —
  ein Hook kann nur Text übergeben.
- Dienste: was sich meldet, was gestört ist, was vermisst wird — nach Gerät,
  das Kaputte oben.

## Mitteilungen

Die Brücke schickt direkt an Apple (`bridge/push.py`), kein Server dazwischen.

- **Freigabe:** Mitteilung mit *Erlauben* und *Ablehnen*. Erlauben verlangt
  ein entsperrtes Telefon oder die Uhr am Handgelenk — es führt etwas auf
  dem Mac aus. Die Uhr zeigt dieselben Knöpfe.
- **Frage:** *Antworten* mit einem Textfeld; tippen öffnet die Auswahlliste.
- **Fertig:** wenn ein Zug länger als anderthalb Minuten lief.
- Gepusht wird nur, wenn niemand die Sitzung ansieht oder Unterwegs an ist.
- Wird eine Freigabe woanders beantwortet, nimmt ein stiller Push ihre
  Mitteilung vom Telefon.
- In der App bleibt eine Mitteilung stumm, wenn ihre Sitzung gerade offen ist.

Mehr als das erlaubt iOS im Hintergrund nicht: Die App wird für den
Knopfdruck kurz geweckt, ein dauernd lauschender Strom ist nicht möglich —
dafür ist Push da.

## Offen

- Die Brillenansicht gibt es bisher nur im Web; wie die RayNeo-App gebaut
  wird, hängt am SDK.
