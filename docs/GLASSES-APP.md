# Brillen-Apps: der Kontrakt

Der Simulator unter `sim/` ist bewusst von iris getrennt. Er weiß nichts über
Claude Code — nur über Panels und darüber, welche Eingaben eine Brille
erzeugen kann. Alles, was diesen Kontrakt erfüllt, lässt sich darin prüfen,
bevor es je Hardware sieht.

## Eine App eintragen

In `sim/apps.json` unter `apps` ergänzen:

```json
{ "id": "meine-app", "label": "Meine App", "url": "/meine-app.html",
  "needsToken": false, "note": "wozu sie da ist" }
```

`needsToken` hängt Token und Sitzung an die URL — nur nötig, wenn die App
gegen die iris-Bridge läuft.

## Eingaben, die hereinkommen

Der Simulator schickt `postMessage` an das Fenster der App:

```js
{ iris: "next" }      // Krone weiter / Ring nach unten
{ iris: "prev" }      // Krone zurück
{ iris: "confirm" }   // Krone klicken
{ iris: "back" }      // eine Ebene zurück
{ iris: "approve" }   // Kopf nicken   — nur bei offener Rückfrage sinnvoll
{ iris: "reject" }    // Kopf schütteln
{ irisProfile: "io" } // Gerät gewechselt: Geometrie neu berechnen
```

Mehr Vokabular gibt es nicht, und das ist Absicht: Wer nur diese sechs
Absichten bedient, läuft auf jeder Brille — ob sie eine Krone hat wie die
RayNeo iO oder einen Ring wie die Even Realities G2.

## Was die App zurückmeldet

```js
parent.postMessage({ irisGeometry: { cols: 48, lines: 11, id: "g2" } }, "*");
```

Nur die App weiß, mit welcher Schrift sie rendert, also misst nur sie, wie
viel Text hineinpasst. Der Simulator zeigt die Zahl als Budget an.

## Geräteprofile

In `sim/apps.json` unter `profiles`. `source` sagt, wie belastbar die Zahl ist:

| Gerät | Panel | Quelle |
|---|---|---|
| Even Realities G2 | 576 × 288 | Herstellerangabe |
| RayNeo iO | 640 × 480 | **geschätzt** — RayNeo nennt keine Pixelzahl |
| Schmales Band | 480 × 160 | Härtefall zum Gegenprüfen |

Belegt ist für die iO: monochrom grün, 23,5° Sichtfeld, 1300 nits, 33 g,
Bedienung über Krone (drehen, klicken, Doppelklick), Kopfgesten (nicken =
ja, schütteln = nein) und Sprache. Die Pixelzahl ist die eine offene Größe —
sobald das SDK sie meldet, nur den Wert in `apps.json` korrigieren, sonst
nichts.

## Was der Simulator erzwingt

- **Monochrom grün.** Kein Zufall, sondern ein Filter über der App: wer
  Bedeutung an Farbe hängt, sieht sie hier verschwinden.
- **Echte Panelgröße.** Vorgabe ist 1:1. Zoom hilft beim Hinsehen, ändert
  aber nie das Layout.
- **Bildratengrenze.** Anzeige und Eingabe laufen über BLE via Telefon. Ein
  Vollbild 576×288 in 1 Bit sind rund 20 KB; bei realistischen ~100 KB/s
  ergibt das etwa 5 Vollbilder je Sekunde. Vorgabe im Simulator sind 5 fps.
  Das ist eine Abschätzung, keine Herstellerangabe — aber sie zeigt
  zuverlässig, dass flüssige Animation kein Entwurfsmittel ist. Zustände,
  die springen, tragen; Bewegung, die fließen soll, nicht.

## Regeln, die sich beim Bauen von iris bewährt haben

- **Eine Sache pro Bild.** Kein Endlos-Scroll: langer Text wird in Seiten
  zerlegt, und jede Seite ist ein eigener Halt auf der Krone. Es gibt keinen
  Scrollbalken, an dem man seine Position ablesen könnte.
- **Nie auf einem Statusmarker landen.** „fertig" ist Satzzeichen, kein
  Inhalt; wer darauf stehenbleibt, sieht ein leeres Panel.
- **Rückfragen unterbrechen.** Sie sind das Einzige, was Arbeit blockiert,
  also nehmen sie das ganze Bild — invertiert, mit zwei Optionen.
- **Markdown gehört entfernt.** Keine Fettschrift, keine Farbe, kein Platz:
  `**so**` wird zu Großbuchstaben, Code-Zeichen und Links fallen weg.
- **Keine Grautöne für Bedeutung.** Auf einem 1-Bit-Panel verschwindet Grau.
  Es gibt an oder aus, Rahmen und Invertierung.
