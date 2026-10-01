import SwiftUI

/// Der Vorarbeiter als Anwesenheit, nicht als Register.
///
/// Ein Register ist ein Ort, zu dem man hingeht; ein Assistent ist jemand, der
/// da ist. Deshalb liegt der Orb über allem, auf jedem Bildschirm, immer an
/// derselben Stelle - und deshalb klappt er an Ort und Stelle auf, statt eine
/// Seite zu öffnen.
///
/// Seine Haltung ist die Messreihe, nicht Stimmung: schneller Atem, solange es
/// besser wird, flacher, wenn es zäh wird, stockend im Stillstand. Was er
/// zeigt, kann man antippen und bekommt die Zahlen dahinter. Und er ist stumm -
/// kein Klang, keine gesprochene Antwort.
/// Wo er sitzt: frei, aber mit Rastpunkten.
///
/// Nur vier Ecken war zu grob - wenn er genau dort stört, hilft es nicht, ihn
/// in eine andere Ecke zu legen, die auch belegt ist. Frei ablegen allein ist
/// aber auch nichts: dann landet er halb über dem Rand oder schief neben der
/// Kante. Also acht Posen, und wer innerhalb des Fangradius loslässt, rastet
/// ein; wer weiter weg loslässt, bleibt genau dort.
enum OrbPose {
    /// Anteilig, damit dieselbe Pose auf jedem Bildschirm dieselbe ist.
    static let posen: [CGPoint] = [
        CGPoint(x: 0, y: 0),   CGPoint(x: 0.5, y: 0),   CGPoint(x: 1, y: 0),
        CGPoint(x: 0, y: 0.5),                          CGPoint(x: 1, y: 0.5),
        CGPoint(x: 0, y: 1),   CGPoint(x: 0.5, y: 1),   CGPoint(x: 1, y: 1),
    ]

    /// Wie nah man loslassen muss, damit er einrastet - in Punkten, nicht
    /// anteilig: auf dem Mac wäre ein Anteil sonst eine halbe Handbreite.
    static let fang: CGFloat = 78

    /// Die Pose, in die ein Punkt fällt - oder der Punkt selbst, wenn keine
    /// nah genug ist. Beides anteilig, zwischen 0 und 1.
    static func einrasten(_ p: CGPoint, in groesse: CGSize) -> CGPoint {
        let frei = CGPoint(x: min(max(p.x / max(groesse.width, 1), 0), 1),
                           y: min(max(p.y / max(groesse.height, 1), 0), 1))
        var beste: (CGPoint, CGFloat)?
        for pose in posen {
            let punkt = CGPoint(x: pose.x * groesse.width, y: pose.y * groesse.height)
            let d = hypot(punkt.x - p.x, punkt.y - p.y)
            if d <= fang, beste == nil || d < beste!.1 { beste = (pose, d) }
        }
        return beste?.0 ?? frei
    }
}

struct VorarbeiterOrb: View {
    @Environment(AppModel.self) private var app
    /// 0 = Kugel, 1 = Tafel. Dazwischen ist sie unterwegs - und genau dieses
    /// Dazwischen gab es vorher nicht.
    ///
    /// Erst war die Tafel eine eigene Ansicht, die neben dem Orb erschien,
    /// mit `.scale` und `.opacity` darauf. Calvin: „das ist keine Animation,
    /// das ist peinlich" - und er hatte recht: es wuchs nichts, es blendete
    /// nur ein. Jetzt gibt es eine einzige Huelle, die von der Kugel zur
    /// Karte wird: Groesse, Ort und Eckenradius laufen zusammen, der Inhalt
    /// wird erst sichtbar, wenn Platz dafuer da ist.
    @State private var grad: Double = 0
    @State private var zug: CGSize = .zero
    @State private var traegt = false
    @State private var geprueft = false
    @State private var inhaltHoehe: CGFloat = 160
    @AppStorage("iris.orb.x") private var relX = 1.0
    @AppStorage("iris.orb.y") private var relY = 1.0

    private var haltung: Haltung { Haltung.aus(app.wachen) }
    private var laufend: [Wache] { app.wachen.filter(\.laeuft) }
    private var offen: Bool { grad > 0.5 }

    private static let kugelGroesse: CGFloat = 34

    /// DEBUG: IRIS_ORB=auf klappt ihn beim Start auf, IRIS_ORB_LANGSAM
    /// verlangsamt die Bewegung, damit man sie in Einzelbildern sehen kann.
    private var dauer: Double {
        #if DEBUG
        if let f = ProcessInfo.processInfo.environment["IRIS_ORB_LANGSAM"],
           let z = Double(f) { return 0.42 * z }
        #endif
        return 0.42
    }

    private func zuerstOeffnen() {
        #if DEBUG
        guard !geprueft, ProcessInfo.processInfo.environment["IRIS_ORB"] == "auf" else { return }
        geprueft = true
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(800))
            umschalten()
        }
        #endif
    }

    private func umschalten() {
        withAnimation(.spring(response: dauer, dampingFraction: 0.82)) {
            grad = grad > 0.5 ? 0 : 1
        }
    }

    private func mitte(in groesse: CGSize) -> CGPoint {
        let rand: CGFloat = 34
        return CGPoint(x: rand + CGFloat(relX) * max(groesse.width - 2 * rand, 0),
                       y: rand + CGFloat(relY) * max(groesse.height - 2 * rand, 0))
    }

    private func tafelBreite(_ groesse: CGSize) -> CGFloat { min(360, groesse.width - 32) }
    /// So hoch wie ihr Inhalt, nicht hoeher.
    ///
    /// Vorher war es eine feste Zahl, und die Tafel stand mit zwei Zeilen
    /// Inhalt als grosses leeres Feld da - „ih", wie Calvin sagte, und zu
    /// Recht. Gemessen wird, was drin ist; die Grenzen halten sie nur davon
    /// ab, laecherlich klein oder groesser als der Bildschirm zu werden.
    private func tafelHoehe(_ groesse: CGSize) -> CGFloat {
        min(max(inhaltHoehe, 132), max(groesse.height - 220, 160))
    }

    /// Wohin die Huelle waechst: direkt ueber den Orb, sonst darunter.
    private func tafelMitte(bei orb: CGPoint, in groesse: CGSize) -> CGPoint {
        let breite = tafelBreite(groesse), hoehe = tafelHoehe(groesse)
        let luft: CGFloat = 10, rand: CGFloat = 16
        let obenPlatz = orb.y - hoehe - luft - 24 > rand
        let y = obenPlatz ? orb.y - Self.kugelGroesse / 2 - luft - hoehe / 2
                          : orb.y + Self.kugelGroesse / 2 + luft + hoehe / 2
        let x = min(max(orb.x, breite / 2 + rand), groesse.width - breite / 2 - rand)
        return CGPoint(x: x, y: min(max(y, hoehe / 2 + rand), groesse.height - hoehe / 2 - rand))
    }

    var body: some View {
        GeometryReader { geo in
            let p = mitte(in: geo.size)
            let ziel = tafelMitte(bei: p, in: geo.size)
            let bW = tafelBreite(geo.size), bH = tafelHoehe(geo.size)
            let k = Self.kugelGroesse
            // Alles laeuft zusammen: Breite, Hoehe, Ort, Eckenradius.
            let w = k + (bW - k) * grad
            let h = k + (bH - k) * grad
            let mx = p.x + (ziel.x - p.x) * grad
            let my = p.y + (ziel.y - p.y) * grad
            let radius = k / 2 + (24 - k / 2) * grad

            ZStack {
                if grad > 0.02 {
                    Color.black.opacity(0.001)
                        .ignoresSafeArea()
                        .onTapGesture { umschalten() }
                }

                ZStack {
                    // Die Huelle. Als Kugel ist sie rund und leuchtet, als
                    // Tafel ist sie eine Karte - dieselbe Form, nur gewachsen.
                    Tropfen(grad: grad)
                        .fill(LinearGradient(colors: [Palette.ground,
                                                      Color(hex: 0x272420)],
                                             startPoint: .topLeading,
                                             endPoint: .bottomTrailing))
                        .opacity(grad)
                        .overlay {
                            Tropfen(grad: grad)
                                .stroke(LinearGradient(
                                    colors: [Palette.brassLight.opacity(0.55 * grad + 0.35),
                                             Palette.brass.opacity(0.12)],
                                    startPoint: .topLeading, endPoint: .bottomTrailing),
                                    lineWidth: 0.9)
                        }

                    // Die Kugel selbst - sie verschwindet, sobald die Huelle
                    // Form annimmt.
                    Kugel(haltung: haltung, anzahl: laufend.count, ruhig: traegt)
                        .opacity(1 - min(1, grad * 2.4))
                        .scaleEffect(1 + grad * 0.6)

                    // Der Inhalt kommt erst, wenn Platz da ist. In voller
                    // Groesse gezeichnet und beschnitten, damit nichts
                    // umbricht, waehrend es waechst.
                    OrbInhalt(wachen: app.wachen, schliessen: { umschalten() })
                        .frame(width: bW)
                        .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { h in
                            if abs(h - inhaltHoehe) > 1 { inhaltHoehe = h }
                        }
                        .frame(width: bW, height: bH)
                        .opacity(max(0, (grad - 0.55) / 0.45))
                        .allowsHitTesting(offen)
                }
                .frame(width: w, height: h)
                .clipShape(Tropfen(grad: grad))
                // Die Messreihe als Kurve um den Orb: enger werdend heisst
                // besser werdend. Ausserhalb des Beschnitts, sonst schneidet
                // die Form sie ab.
                .overlay {
                    Messring(werte: laufend.first?.werte ?? [],
                             farbe: haltung.farbe)
                        .frame(width: 78, height: 78)
                        .opacity(1 - min(1, grad * 3))
                        .allowsHitTesting(false)
                }
                .shadow(color: .black.opacity(0.28 + 0.22 * grad),
                        radius: 8 + 14 * grad, y: 3 + 7 * grad)
                .scaleEffect(traegt ? 1.18 : 1)
                .contentShape(Tropfen(grad: grad))
                .gesture(
                    DragGesture(minimumDistance: 4, coordinateSpace: .named("orbflaeche"))
                        .onChanged { g in
                            guard !offen else { return }
                            traegt = true
                            zug = g.translation
                        }
                        .onEnded { g in
                            guard !offen else { return }
                            let ziel = OrbPose.einrasten(g.location, in: geo.size)
                            withAnimation(.spring(duration: 0.3)) {
                                relX = Double(ziel.x)
                                relY = Double(ziel.y)
                                zug = .zero
                                traegt = false
                            }
                        }
                )
                .onTapGesture { if !offen { umschalten() } }
                .position(x: mx + zug.width, y: my + zug.height)
                .accessibilityIdentifier("orb")
                .accessibilityLabel("Assistent, \(haltung.wort)")
            }
        }
        .coordinateSpace(.named("orbflaeche"))
        .ignoresSafeArea(.keyboard)
        .task { zuerstOeffnen() }
    }
}

/// Was aufgeklappt darin steht: der Auftrag, die Messreihe, der Stand. Nicht
/// die Karten der beaufsichtigten Sitzung - die stehen in der Sitzung, einen
/// Fingertipp entfernt. Zwei Fassungen desselben Verlaufs sind schlimmer als
/// keine.
struct OrbInhalt: View {
    @Environment(AppModel.self) private var app
    let wachen: [Wache]
    var schliessen: () -> Void = {}
    @State private var modell: SessionModel?
    @State private var entwurf = ""
    @State private var schickt = false
    @State private var da = false
    @FocusState private var tippt: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Kein Schliessen-Kreuz: daneben tippen schliesst, und ein Kreuz
            // waere das dritte Bedienelement in einer Tafel, die mit einem
            // auskommt.
            HStack(alignment: .firstTextBaseline, spacing: 9) {
                Text("Assistent")
                    .font(Face.display(21))
                    .foregroundStyle(Palette.text)
                Text(Haltung.aus(wachen).wort)
                    .font(Face.mono(10.5))
                    .foregroundStyle(Palette.meta)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 22)
            .padding(.top, 19)
            .padding(.bottom, 4)
            .opacity(da ? 1 : 0)
            .offset(y: da ? 0 : 6)
            gespraech
            eingabe
        }
        // Kein eigener Hintergrund mehr: den stellt die Huelle, die aus dem
        // Orb gewachsen ist. Zwei Flaechen uebereinander sahen durchsichtig
        // aus, weil die obere nur halb deckte.
        // Ein Lichtsaum oben: dort, wo in dieser App das Licht steht.
        .overlay(alignment: .top) {
            LinearGradient(colors: [Palette.brassLight.opacity(0.18), .clear],
                           startPoint: .top, endPoint: .bottom)
                .frame(height: 26)
                .allowsHitTesting(false)
        }
        .task {
            // Gestaffelt: erst der Name, dann die Ansprache, dann die
            // Eingabe. Alles auf einmal wirkt wie ein Sprung, nacheinander
            // wie ein Aufgehen - 60 Millisekunden Abstand genuegen dafuer.
            withAnimation(.easeOut(duration: 0.28).delay(0.06)) { da = true }
            // Nur nachsehen, nichts anlegen: Aufklappen ist kein Auftrag.
            modell = app.vorarbeiterModell()
            // Aber seinen Kartenstrom starten - ohne den bleibt der Verlauf
            // leer, und die Tafel sieht aus, als haette er nie etwas gesagt.
            modell?.start()
            // Aufgeklappt heisst: du wolltest etwas sagen. Also steht der
            // Zeiger schon im Feld, statt dass man erst hineintippt.
            tippt = true
        }
    }

    /// Was er zuletzt gesagt hat. Kurz gehalten: das Lange steht in seiner
    /// Sitzung, und zwei Fassungen desselben Verlaufs sind schlimmer als eine.
    @ViewBuilder private var gespraech: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                                ForEach(wachen.filter(\.laeuft)) { w in
                    WacheZeile(wache: w)
                }
                let fertige = wachen.filter { !$0.laeuft }.suffix(3)
                if !fertige.isEmpty {
                    SectionLabel("Abgeschlossen")
                    ForEach(fertige) { w in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(w.ziel).font(Face.ui(12.5)).foregroundStyle(Palette.soft)
                            Text(w.grund.isEmpty ? "fertig" : w.grund)
                                .font(Face.mono(10.5)).foregroundStyle(Palette.meta)
                        }
                    }
                }
                if wachen.isEmpty, (modell?.turns.isEmpty ?? true) {
                    // Ohne Auftrag keine Erklaerseite, keine Einrichtung: eine
                    // Frage und ein Textfeld. Und die Frage ist offen - er ist
                    // ein Assistent, der auch beaufsichtigt, nicht ein
                    // Aufpasser, der sonst nichts kann.
                    Text("Was liegt an?")
                        .font(Face.ui(13.5)).foregroundStyle(Palette.soft)
                }
                if let m = modell, !m.turns.isEmpty {
                    SectionLabel("Zuletzt")
                    ForEach(m.turns.suffix(6)) { zug in
                        if !zug.text.isEmpty {
                            Text(zug.text)
                                .font(Face.ui(zug.kind == .user ? 12.5 : 13))
                                .foregroundStyle(zug.kind == .user ? Palette.soft : Palette.text)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
            }
            .padding(.horizontal, 22)
            .padding(.vertical, 16)
        }
        // Nur nach unten verankern, wenn es etwas zu verankern gibt - sonst
        // klebt eine einzige Zeile am unteren Rand und darueber steht Leere.
        .defaultScrollAnchor((modell?.turns.isEmpty ?? true) ? .top : .bottom)
        .scrollBounceBehavior(.basedOnSize)
        // Nur so hoch wie noetig: eine ScrollView nimmt sonst allen Platz,
        // den sie bekommen kann, und der war das Loch in der Tafel.
        .fixedSize(horizontal: false, vertical: true)
        .opacity(da ? 1 : 0)
        .offset(y: da ? 0 : 8)
        .animation(.easeOut(duration: 0.3).delay(0.10), value: da)
    }

    /// Getippt, nicht gesprochen: man hat nicht immer die Ruhe zu reden.
    /// Gemeldet von Calvin, 25.09. - Diktat kommt daneben, nicht an seine
    /// Stelle.
    @ViewBuilder private var eingabe: some View {
        HStack(spacing: 8) {
            TextField("", text: $entwurf,
                      prompt: Text("Frag mich was, oder gib mir was ab …").foregroundStyle(Palette.hint),
                      axis: .vertical)
                .font(Face.ui(13.5))
                .foregroundStyle(Palette.text)
                .lineLimit(1...4)
                .textFieldStyle(.plain)
                .focused($tippt)
                .onSubmit { senden() }
                .accessibilityIdentifier("orb-eingabe")
            Button {
                senden()
            } label: {
                Image(systemName: "arrow.up")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(entwurf.isEmpty ? Palette.faint : Palette.brass)
            }
            .buttonStyle(.plain)
            .disabled(entwurf.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || schickt)
        }
        .padding(.horizontal, 22)
        .padding(.vertical, 16)
        .opacity(da ? 1 : 0)
        .offset(y: da ? 0 : 10)
        .animation(.easeOut(duration: 0.3).delay(0.16), value: da)
        // Keine zweite Flaeche: eine Haarlinie genuegt, um die Eingabe vom
        // Gesagten zu trennen. Wer Flaechen stapelt, liest Raender statt Text.
        .overlay(alignment: .top) {
            Rectangle().fill(Palette.text.opacity(0.07)).frame(height: 1)
        }
    }

    private func senden() {
        let text = entwurf.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !schickt else { return }
        schickt = true
        entwurf = ""
        Task {
            // Beim ersten Wort entsteht er - eine Einrichtung gibt es nicht.
            var m = modell
            if m == nil { m = await app.vorarbeiterAnlegen() }
            modell = m
            if let m {
                m.start()
                _ = await m.send(text)
            }
            schickt = false
        }
    }
}

struct WacheZeile: View {
    @Environment(AppModel.self) private var app
    let wache: Wache

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(wache.ziel).font(Face.ui(14)).foregroundStyle(Palette.text)

            HStack(spacing: 8) {
                Text("Runde \(wache.runden.count) von \(wache.budget)")
                if wache.stillstand {
                    Text("· steht").foregroundStyle(Palette.clayText)
                }
                Spacer(minLength: 0)
                Button("HALT") { Task { await app.wacheBeenden(wache.id) } }
                    .font(Face.mono(10))
                    .foregroundStyle(Palette.clayText)
                    .buttonStyle(.plain)
            }
            .font(Face.mono(10.5))
            .foregroundStyle(Palette.meta)

            if !wache.werte.isEmpty {
                Reihe(werte: wache.werte)
                // Das Beste steht gross da - es ist die einzige Zahl, auf die
                // es ankommt, und der einzige Moment, an dem diese Tafel laut
                // sein darf.
                HStack(alignment: .firstTextBaseline, spacing: 7) {
                    if let b = wache.bestes {
                        Text(Mess.zahl(b))
                            .font(Face.display(27))
                            .foregroundStyle(Palette.sageText)
                    }
                    if !wache.mass.isEmpty {
                        Text(wache.mass).font(Face.mono(10.5)).foregroundStyle(Palette.meta)
                    }
                    if let e = wache.erstes, let b = wache.bestes, e > b {
                        Text("von \(Mess.zahl(e))")
                            .font(Face.mono(10.5)).foregroundStyle(Palette.faint)
                    }
                }
            } else if wache.mass.isEmpty {
                Text("Noch kein Maß vereinbart.")
                    .font(Face.ui(11.5)).foregroundStyle(Palette.clayText)
            }
        }
    }
}

/// Eine Zahl, wie sie in eine Zeile passt: ohne Nachkomma, wenn keins nötig
/// ist. `Fmt` hat dafür nichts, und eine Messreihe mit "41.0" liest sich
/// schlechter als eine mit "41".
enum Mess {
    static func zahl(_ w: Double) -> String {
        w == w.rounded() && abs(w) < 1e9 ? String(Int(w.rounded()))
                                         : String(format: "%.2f", w)
    }
}

/// Die Messreihe als Balken. Kleiner ist besser, also steht der niedrigste
/// Balken für das beste Ergebnis - und genau der soll ins Auge fallen.
struct Reihe: View {
    let werte: [Double]

    var body: some View {
        let hoch = werte.max() ?? 1
        let tief = werte.min() ?? 0
        HStack(alignment: .bottom, spacing: 3) {
            ForEach(Array(werte.enumerated()), id: \.offset) { i, w in
                let anteil = hoch > 0 ? (w / hoch) : 1
                RoundedRectangle(cornerRadius: 1.5, style: .continuous)
                    .fill(w <= tief ? Palette.sage : Palette.brass.opacity(0.55))
                    .frame(width: 6, height: max(3, 34 * anteil))
                    .accessibilityLabel("Runde \(i + 1): \(Mess.zahl(w))")
            }
        }
        .frame(height: 34, alignment: .bottom)
    }
}
