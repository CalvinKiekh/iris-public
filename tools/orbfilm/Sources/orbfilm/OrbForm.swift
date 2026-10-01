import SwiftUI

/// Die Form des Assistenten - nur Geometrie und Farbe, ohne App.
///
/// Absichtlich frei von `AppModel`, `Wache` und allem anderen: so laesst sie
/// sich ausserhalb des Simulators zeichnen, Bild fuer Bild, und jede Stufe
/// der Bewegung einzeln ansehen (`tools/orbfilm`). Vorher konnte ich eine
/// Animation nur behaupten - Calvin am 25.09.: „render dir das mal als
/// einzelne Frames und behaupte nochmal, das waechst aus der Form heraus."

/// Wie der Assistent dasteht. Abgeleitet aus der Messreihe, nie gesetzt.
enum Haltung: Sendable, CaseIterable {
    case ruht, zuversichtlich, skeptisch, festgefahren, erledigt

    /// Wie schnell der Atem geht, in Sekunden je Zug.
    var atem: Double {
        switch self {
        case .ruht: return 3.2
        case .zuversichtlich: return 1.6
        case .skeptisch: return 2.4
        case .festgefahren: return 4.0
        case .erledigt: return 2.0
        }
    }

    var wort: String {
        switch self {
        case .ruht: return "bereit"
        case .zuversichtlich: return "läuft"
        case .skeptisch: return "zäh"
        case .festgefahren: return "steht"
        case .erledigt: return "fertig"
        }
    }

    var farbe: Color {
        switch self {
        case .festgefahren: return Palette.clay
        case .skeptisch: return Palette.brassDeep
        case .erledigt: return Palette.sage
        default: return Palette.brass
        }
    }
}

/// Die Kugel: ein großer Bud mit Messingrand. Acht Bilder je Sekunde, wie
/// überall in dieser App - eine endlose Animation hat den Mac schon einmal ein
/// Fünftel Kern gekostet.
struct Kugel: View {
    let haltung: Haltung
    var anzahl: Int = 0
    var groesse: CGFloat = 34
    /// Beim Tragen atmet er nicht.
    ///
    /// Nicht aus Stilgruenden: der Atem laeuft ueber einen TimelineView mit
    /// acht Bildern je Sekunde - sparsam, damit er nichts kostet - und genau
    /// dieser Takt bestimmt waehrend des Ziehens, wie oft die Kugel neu
    /// gezeichnet wird. Der Finger laeuft ihr davon, und es sieht hakelig
    /// aus. Ohne Zeitgeber folgt sie der Bewegung so schnell wie das Bild.
    var ruhig = false

    private var farbe: Color { haltung.farbe }

    var body: some View {
        if ruhig {
            kreis(phase: 0.6)
        } else {
            TimelineView(.animation(minimumInterval: 1 / 8)) { t in
                kreis(phase: (sin(t.date.timeIntervalSinceReferenceDate * .pi / haltung.atem) + 1) / 2)
            }
        }
    }

    @ViewBuilder private func kreis(phase: Double) -> some View {
        // Licht, keine Materie. Der erste Entwurf hatte eine dunkle Pupille
        // und sah aus wie ein Augapfel - organisch, fast unheimlich. Was
        // gemeint war, ist ein Punkt aus Licht mit Struktur: ein heller Kern,
        // zwei feine Ringe, ein Bogen, der langsam wandert. Die Farben bleiben
        // Messing auf Daemmerung, damit er zu dieser App gehoert und nicht zu
        // einem Raumschiff.
        let helle = 0.55 + 0.35 * phase
        ZStack {
            // Der Schein: eng und warm. Weit und blass war er ein grauer
            // Fleck auf dem Grund - Licht, das sich verliert, sieht nach
            // Schmutz aus, nicht nach Leuchten.
            Circle()
                .fill(farbe.opacity(0.16 + 0.10 * phase))
                .blur(radius: groesse * 0.22)
                .scaleEffect(1.32)

            // Der Koerper: eine Kugel, kein Klecks. Licht faellt von oben
            // links ein, die gegenueberliegende Seite bleibt dunkel - erst
            // das Gefaelle macht daraus etwas Rundes.
            Circle()
                .fill(RadialGradient(
                    colors: [Palette.brassLight.opacity(0.95),
                             farbe.opacity(0.85),
                             farbe.opacity(0.28),
                             Palette.ground.opacity(0.55)],
                    center: UnitPoint(x: 0.36, y: 0.32),
                    startRadius: 0, endRadius: groesse * 0.78))

            // Der Kern selbst, klein und hell: der Punkt, auf den das Auge
            // faellt. Er atmet, der Rest steht.
            Circle()
                .fill(RadialGradient(
                    colors: [Color.white.opacity(0.75 * helle), .clear],
                    center: .center, startRadius: 0, endRadius: groesse * 0.22))
                .frame(width: groesse * 0.44, height: groesse * 0.44)
                .offset(x: -groesse * 0.05, y: -groesse * 0.07)

            // Zwei Ringe, ganz fein. Der aeussere steht, der innere ist nur
            // ein Bogen - er wandert, und daran sieht man, dass etwas laeuft.
            Circle()
                .strokeBorder(farbe.opacity(0.35), lineWidth: 0.6)
                .scaleEffect(0.86)
            Circle()
                .trim(from: 0, to: 0.30)
                .stroke(Palette.brassLight.opacity(0.85), style: StrokeStyle(lineWidth: 1.1, lineCap: .round))
                .scaleEffect(0.66)
                .rotationEffect(.degrees(ruhig ? 0 : phase * 360))

            // Die Kante aussen: Luxus ist eine Kante, keine Flaeche.
            Circle()
                .strokeBorder(LinearGradient(
                    colors: [Palette.brassLight.opacity(0.9), farbe.opacity(0.15)],
                    startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 0.9)

            if anzahl > 1 {
                Text("\(anzahl)")
                    .font(Face.mono(9))
                    .foregroundStyle(Palette.ground)
                    .offset(y: groesse * 0.02)
            }
        }
        .frame(width: groesse, height: groesse)
        .shadow(color: farbe.opacity(0.35), radius: 6 + 3 * phase)
    }
}


/// Die Hülle, die aus der Kugel eine Tafel macht.
///
/// `grad` ist der einzige Regler: 0 ist die Kugel, 1 die Karte. Größe, Ort,
/// Eckenradius und Deckung laufen daran entlang. Weil hier nichts außer
/// SwiftUI steckt, lässt sich jede Stufe einzeln zeichnen und ansehen.
struct OrbHuelle<Inhalt: View>: View {
    var grad: Double
    var haltung: Haltung = .ruht
    var kugel: CGFloat = 34
    var breite: CGFloat = 360
    var hoehe: CGFloat = 320
    var anzahl: Int = 0
    /// Die Messreihe des laufenden Auftrags - als Ring um die Kugel.
    var reihe: [Double] = []
    @ViewBuilder var inhalt: () -> Inhalt

    /// Weiches Ein- und Ausblenden zwischen zwei Marken - hart geschnitten
    /// wirkt jeder Uebergang wie ein Sprung.
    static func weich(_ x: Double, _ a: Double, _ b: Double) -> Double {
        let t = min(max((x - a) / max(b - a, 0.0001), 0), 1)
        return t * t * (3 - 2 * t)
    }

    var w: CGFloat { kugel + (breite - kugel) * grad }
    var h: CGFloat { kugel + (hoehe - kugel) * grad }
    var radius: CGFloat { kugel / 2 + (24 - kugel / 2) * grad }

    var body: some View {
        ZStack {
            Tropfen(grad: grad)
                .fill(LinearGradient(colors: [Palette.ground, Color(hex: 0x272420)],
                                     startPoint: .topLeading, endPoint: .bottomTrailing))
                // Der Koerper ist sofort da. Lief er mit `grad`, war die
                // Huelle in der ersten Haelfte halbdurchsichtig.
                .opacity(min(1, grad * 3.5))
                .overlay {
                    Tropfen(grad: grad)
                        .stroke(LinearGradient(
                            colors: [Palette.brassLight.opacity(0.35 + 0.35 * grad),
                                     haltung.farbe.opacity(0.12)],
                            startPoint: .topLeading, endPoint: .bottomTrailing),
                            lineWidth: 0.9)
                }
            // Die Kugel sinkt in die Flaeche ein, statt zu wachsen und
            // dann zu verschwinden: sie wird kleiner und blasser, und sie
            // bleibt lange genug, dass die Bewegung keine Luecke hat.
            Kugel(haltung: haltung, anzahl: anzahl)
                .scaleEffect(1 - 0.40 * Self.weich(grad, 0, 0.45))
                .opacity(1 - Self.weich(grad, 0.06, 0.40))
            // Der Inhalt waechst mit der Huelle, statt von ihr beschnitten zu
            // werden. Vorher stand er in voller Groesse hinter einem kleinen
            // Fenster - man sah „ssistent" und „g mich was", also die Mitte
            // eines zu grossen Textes. Jetzt ist die Karte samt Inhalt klein
            // und wird gross: eine Bewegung statt eines Guckloches.
            // Ohne Unschaerfe, und das ist keine Feinheit: Jayse Hansen, der
            // das Iron-Man-HUD entworfen hat, nennt es als Regel - „everything
            // is in focus, so everything is readable". Was unscharf wird,
            // waehrend es sich bewegt, kann man nicht lesen, und ein
            // Assistent, den man im Moment des Erscheinens nicht lesen kann,
            // kostet genau die Zeit, die er sparen soll.
            inhalt()
                .frame(width: breite, height: hoehe)
                .scaleEffect(max(0.12, w / breite))
                .opacity(Self.weich(grad, 0.22, 0.72))
        }
        .frame(width: w, height: h)
        .clipShape(Tropfen(grad: grad))
        // Der Ring liegt AUSSERHALB des Beschnitts - innen wurde er an der
        // Kugelkante abgeschnitten und war nur als zwei Stricheln zu sehen.
        .overlay {
            Messring(werte: reihe, farbe: haltung.farbe)
                .frame(width: 78, height: 78)
                .opacity(1 - Self.weich(grad, 0.05, 0.35))
                .allowsHitTesting(false)
        }
        .shadow(color: .black.opacity(0.28 + 0.22 * grad),
                radius: 8 + 14 * grad, y: 3 + 7 * grad)
    }
}


/// Die Form zwischen Kugel und Karte - ein Tropfen, kein Rechteck.
///
/// Calvin, 25.09.: „Ein Viereck oeffnen ist nichts Besonderes, du morphst
/// auch nicht aus dem Kreis raus - wie so ein organischer Blob waere viel
/// geiler." Genau das macht diese Form: die Seiten bauchen sich in der Mitte
/// der Bewegung nach aussen, als wuerde etwas hindurchgedrueckt, und ziehen
/// sich zum Schluss zur ruhigen Karte zusammen. Dazu haengt sie anfangs mit
/// einem Hals am Ausgangspunkt, der duenner wird und abreisst.
struct Tropfen: Shape {
    /// 0 = Kugel, 1 = Karte.
    var grad: Double
    /// Woher er waechst, in Anteilen der eigenen Flaeche (0…1).
    var quelle: UnitPoint = .bottom

    var animatableData: Double {
        get { grad }
        set { grad = newValue }
    }

    func path(in r: CGRect) -> Path {
        let e = min(r.width, r.height) / 2
        // Eckenradius laeuft von rund (Kugel) zu Karte.
        let radius = e + (24 - e) * min(1, grad * 1.15)
        // Der Bauch ist in der Mitte am groessten und zum Schluss weg -
        // sin(pi*t) ist genau diese Kurve.
        let bauch = sin(Double(min(1, grad)) * .pi) * min(r.width, r.height) * 0.13

        var p = Path()
        let x0 = r.minX, x1 = r.maxX, y0 = r.minY, y1 = r.maxY
        let rr = min(radius, min(r.width, r.height) / 2)

        p.move(to: CGPoint(x: x0 + rr, y: y0))
        // Auch oben und unten leicht gewoelbt: stossen gerade Kanten auf
        // gewoelbte Seiten, entstehen an den Ecken kleine Dellen. Eine
        // durchgehende Kontur hat keine Naht.
        p.addQuadCurve(to: CGPoint(x: x1 - rr, y: y0),
                       control: CGPoint(x: (x0 + x1) / 2, y: y0 - bauch * 0.55))
        p.addQuadCurve(to: CGPoint(x: x1, y: y0 + rr),
                       control: CGPoint(x: x1 + bauch * 0.5, y: y0 - bauch * 0.5))
        p.addQuadCurve(to: CGPoint(x: x1, y: y1 - rr),
                       control: CGPoint(x: x1 + bauch, y: (y0 + y1) / 2))
        p.addQuadCurve(to: CGPoint(x: x1 - rr, y: y1),
                       control: CGPoint(x: x1 + bauch * 0.5, y: y1 + bauch * 0.5))
        p.addQuadCurve(to: CGPoint(x: x0 + rr, y: y1),
                       control: CGPoint(x: (x0 + x1) / 2, y: y1 + bauch * 0.55))
        p.addQuadCurve(to: CGPoint(x: x0, y: y1 - rr),
                       control: CGPoint(x: x0 - bauch * 0.5, y: y1 + bauch * 0.5))
        p.addQuadCurve(to: CGPoint(x: x0, y: y0 + rr),
                       control: CGPoint(x: x0 - bauch, y: (y0 + y1) / 2))
        p.addQuadCurve(to: CGPoint(x: x0 + rr, y: y0),
                       control: CGPoint(x: x0 - bauch * 0.5, y: y0 - bauch * 0.5))
        p.closeSubpath()

        // Der Hals. Nach innen gewoelbt, nicht schraeg: eine gerade Schraege
        // sieht aus wie eine Kartennadel, erst die Einschnuerung macht daraus
        // Fluessigkeit. Er wird duenner und reisst ab, statt zu verschwinden.
        // Nur unterwegs, nie im Ruhezustand. Vorher war er bei `grad = 0` am
        // staerksten - und dann haengt dauerhaft ein Zipfel unter dem Orb,
        // der ihn zur Kartennadel macht. Calvin: „das sieht richtig schlimm
        // aus." Jetzt waechst er beim Aufgehen, ist auf einem Viertel des
        // Weges am kraeftigsten und danach weg.
        let halsStaerke = grad <= 0.001 || grad >= 0.5 ? 0
            : sin(min(max(grad / 0.5, 0), 1) * Double.pi)
        if halsStaerke > 0.02 {
            let unten = quelle.y > 0.5
            let qx = r.minX + quelle.x * r.width
            let qy = unten ? r.maxY : r.minY
            let laenge = 30 * halsStaerke
            let spitzeY = qy + (unten ? laenge : -laenge)
            // Am Ansatz breit, an der Spitze fast nichts - und die Seiten
            // ziehen zur Achse hin ein.
            let ansatz = 15 * halsStaerke
            let spitze = 4 * halsStaerke
            let einzug = ansatz * 0.55

            var h = Path()
            h.move(to: CGPoint(x: qx - ansatz, y: qy))
            h.addCurve(to: CGPoint(x: qx - spitze, y: spitzeY),
                       control1: CGPoint(x: qx - einzug, y: qy + (unten ? laenge * 0.45 : -laenge * 0.45)),
                       control2: CGPoint(x: qx - spitze, y: qy + (unten ? laenge * 0.72 : -laenge * 0.72)))
            // Die Spitze ist rund, nicht spitz - sonst sticht sie.
            h.addQuadCurve(to: CGPoint(x: qx + spitze, y: spitzeY),
                           control: CGPoint(x: qx, y: spitzeY + (unten ? spitze : -spitze)))
            h.addCurve(to: CGPoint(x: qx + ansatz, y: qy),
                       control1: CGPoint(x: qx + spitze, y: qy + (unten ? laenge * 0.72 : -laenge * 0.72)),
                       control2: CGPoint(x: qx + einzug, y: qy + (unten ? laenge * 0.45 : -laenge * 0.45)))
            h.closeSubpath()
            p.addPath(h)
        }
        return p
    }
}


/// Die Messreihe als Ring um den Orb.
///
/// Nach der Regel, die Jayse Hansen fuer das Iron-Man-HUD nennt: man liest
/// das **Muster**, nicht die Einzelwerte. Stark sieht nicht 41 ms, er sieht,
/// dass die Kurve faellt. Genau das soll hier aus drei Metern lesbar sein -
/// und es braucht keine Flaeche, die etwas verdeckt.
///
/// Kleiner ist besser, also ist der kuerzeste Strich der beste Wert. Der Ring
/// laeuft oben los und im Uhrzeigersinn: die juengste Runde steht rechts.
struct Messring: View {
    var werte: [Double]
    var farbe: Color = Palette.brass
    var radius: CGFloat = 22
    var laenge: CGFloat = 8

    var body: some View {
        Canvas { ctx, groesse in
            guard werte.count > 1, let hoch = werte.max(), let tief = werte.min(),
                  hoch > 0 else { return }
            let m = CGPoint(x: groesse.width / 2, y: groesse.height / 2)
            let spanne = max(hoch - tief, hoch * 0.05)
            // Ein Bogen von drei Vierteln, oben offen: ein geschlossener Ring
            // sieht nach Ladebalken aus, und die Luecke sagt, wo die Reihe
            // anfaengt.
            let start = -Double.pi * 0.72
            let bogen = 1.44 * Double.pi

            // Eine durchgehende Linie, deren Abstand vom Orb die Zahl traegt.
            // Einzelne Striche sahen aus wie eine Sonne - eine Kurve liest
            // man als Verlauf, und darum geht es: faellt sie oder nicht.
            // Geglaettet: gerade Strecken zwischen acht Punkten ergeben ein
            // Vieleck, und ein Vieleck liest man als Form, nicht als Verlauf.
            // Die Kurve laeuft durch die Punkte, die Mittelpunkte fuehren sie.
            let punkte: [CGPoint] = werte.enumerated().map { i, w in
                let t = Double(i) / Double(max(werte.count - 1, 1))
                let winkel = start + t * bogen
                let anteil = min(max((w - tief) / spanne, 0), 1)
                let r = radius + laenge * anteil
                return CGPoint(x: m.x + cos(winkel) * r, y: m.y + sin(winkel) * r)
            }
            var pfad = Path()
            if let erster = punkte.first {
                pfad.move(to: erster)
                for i in 1..<punkte.count {
                    let a = punkte[i - 1], b = punkte[i]
                    let mitte = CGPoint(x: (a.x + b.x) / 2, y: (a.y + b.y) / 2)
                    pfad.addQuadCurve(to: mitte, control: a)
                    if i == punkte.count - 1 { pfad.addQuadCurve(to: b, control: b) }
                }
            }
            ctx.stroke(pfad, with: .color(farbe.opacity(0.75)),
                       style: StrokeStyle(lineWidth: 1.4, lineCap: .round, lineJoin: .round))

            // Der beste Wert bekommt einen Punkt - das ist die Zahl, die
            // zaehlt, und man findet sie ohne zu suchen.
            if let i = werte.firstIndex(of: tief) {
                let t = Double(i) / Double(max(werte.count - 1, 1))
                let winkel = start + t * bogen
                let p = CGPoint(x: m.x + cos(winkel) * radius, y: m.y + sin(winkel) * radius)
                ctx.fill(Path(ellipseIn: CGRect(x: p.x - 1.6, y: p.y - 1.6, width: 3.2, height: 3.2)),
                         with: .color(Palette.sageText))
            }
        }
    }
}
