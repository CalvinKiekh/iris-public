# orbfilm — die Bewegung ansehen, statt sie zu behaupten

    swift run --package-path tools/orbfilm orbfilm 11 ios/build/film

Zeichnet die Entfaltung des Assistenten in gleichmäßigen Stufen und legt sie
als Einzelbilder ab, dazu `bogen.png` mit allen nebeneinander.

**Warum es das gibt.** Am 25.09. habe ich behauptet, die Tafel wachse aus dem
Orb heraus. Calvin: „Render dir das mal als einzelne Frames und behaupte
nochmal, das wächst aus der Form heraus. Kein Morphen, gar nichts." Er hatte
recht — im Simulator sieht man eine Bewegung von 0,4 Sekunden nicht, und
Bildschirmfotos treffen sie nicht.

Hier ist `grad` nur eine Zahl: 0 ist die Kugel, 1 die Tafel. Jede Stufe lässt
sich einzeln zeichnen, wiederholen und vergleichen — ohne Simulator, ohne
Zeit, ohne Zufall. Drei Fehler waren so in Minuten zu sehen:

- die Kugel blieb gleich groß, während ein Kasten um sie herum wuchs
- zwei Stufen lang war die Fläche leer (Kugel weg, Inhalt noch nicht da)
- der Inhalt stand in voller Größe hinter einem kleinen Fenster, man sah
  „ssistent" und „g mich was"

Die Form dafür steht in `shared/OrbForm.swift` und hängt bewusst an nichts
aus der App — sonst ließe sie sich hier nicht zeichnen.
