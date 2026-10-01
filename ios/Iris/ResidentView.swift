import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

/// The resident's side of the home screen. The sessions are built for
/// density; this page for insight - what it is doing right now, what it
/// watches, what it noticed, what it had done and why - at a glance, drawn
/// rather than written. The conversation and the full journal open on
/// sheets of their own.
struct ResidentPanel: View {
    @Environment(AppModel.self) private var app
    let model: ResidentModel
    @State private var note: String?
    @State private var busy = false
    @State private var showFiles = false
    @State private var showTalk = false
    @State private var journal: JournalFilter?
    /// Which of the four rooms is open. Kept across launches: whoever last
    /// looked at his memory usually wants it again.
    @AppStorage("iris.bewohner.register") private var reiter = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let s = model.state {
                // Above the tabs: how he is, and anything that waits for an
                // answer. Neither may hide behind a tab nobody opened.
                ResidentPulse(state: s, doing: doing(s))
                    .padding(.top, 20)
                controls(s).padding(.top, 20)
                if let note {
                    Text(note).font(Face.mono(10)).foregroundStyle(Palette.clayText).padding(.top, 8)
                }
                ForEach(s.requests.filter { $0.status == "offen" }) { r in
                    RequestCard(request: r) { allow in
                        Task { note = await model.decide(r.id, allow: allow) }
                    }
                    .padding(.top, 16)
                }
                Register(namen: ["Jetzt", "Verlauf", "Er selbst", "Reden"], gewaehlt: $reiter)
                    .padding(.top, 22)
                Rectangle().fill(Palette.hair).frame(height: 1)
                switch reiter {
                case 0: jetzt(s)
                case 1: verlauf(s)
                case 2: erSelbst
                default: reden
                }
            } else if model.machine == nil {
                Text("Auf keinem Rechner wohnt ein Bewohner. Er zieht auf dem PC ein – sobald dort `mcp-test\\werkstatt` steht, erscheint er hier.")
                    .font(Face.ui(13.5)).foregroundStyle(Palette.meta).padding(.top, 18)
            } else {
                Text(model.problem ?? "Wird geladen …").font(Face.ui(13.5)).foregroundStyle(Palette.meta).padding(.top, 18)
            }
        }
        .sheet(isPresented: $showTalk) { ResidentTalkSheet(model: model) }
        .sheet(isPresented: $showFiles) { ResidentFilesSheet(model: model) }
        .sheet(item: $journal) { f in ResidentJournalSheet(model: model, filter: f) }
        .onAppear { model.start() }
        .onDisappear { model.stop() }
    }

    // MARK: die vier Räume

    /// What he is doing, and what he was thinking while he did it.
    @ViewBuilder private func jetzt(_ s: ResidentState) -> some View {
        JetztZahlen(state: s, lage: nil, entries: model.entries).padding(.top, 18)
        SectionLabel("Was er im Blick hat")
        SensesRow(watching: s.watching ?? [], awake: s.alive && !s.stopped)
        SectionLabel("Woran er denkt")
        GedankenStrom(entries: model.entries)
        HStack(spacing: 26) {
            link("Arbeitsraum", "folder", id: "arbeitsraum") { showFiles = true }
            link("Journal", "list.bullet.rectangle", id: "journal") { journal = .all }
            Spacer()
        }
        .padding(.top, 20)
    }

    /// The day as a strip, the figures under it, and the work he finished.
    @ViewBuilder private func verlauf(_ s: ResidentState) -> some View {
        SectionLabel(DayStrip.title(model.entries))
        DayStrip(entries: model.entries)
        TodayNumbers(entries: model.entries, budget: s.budget,
                     open: { journal = $0 }, talk: { showTalk = true })
            .padding(.top, 18)
        SectionLabel("Was er getan hat")
        cycles
    }

    /// Who he says he is, what he remembers, what he can.
    @ViewBuilder private var erSelbst: some View {
        SectionLabel("Wer er ist")
        SelfGlance(model: model)
        SectionLabel("Was er kann")
        CanGlance(model: model)
        SectionLabel("Gedächtnis")
        MemoryGlance(model: model)
    }

    /// Talking to him - the last exchange and the way in.
    @ViewBuilder private var reden: some View {
        SectionLabel("Gespräch")
        TalkEntry(model: model) { showTalk = true }
    }

    /// In one sentence, what it is doing - the first thing to read.
    private func doing(_ s: ResidentState) -> String {
        if s.stopped { return "Beobachtet weiter, gibt Claude aber keine Aufträge." }
        if !s.alive {
            return s.state == "beendet" ? "Das Programm läuft auf dem PC gerade nicht."
                : "Meldet sich seit \(Self.ago(s.seen)) nicht."
        }
        switch s.state {
        case "arbeitet":
            if let o = model.entries.last(where: { $0.kind == "auftrag" }), let t = o.text {
                return "Lässt Claude gerade: \(t)"
            }
            return "Ein Auftrag an Claude läuft."
        case "denkt":
            return "Überlegt, ob etwas zu tun ist."
        default:
            if let b = s.brake { return "Aufträge ruhen – \(b)." }
            return "Wartet auf eine Veränderung, um dann zu entscheiden."
        }
    }

    // MARK: controls

    private func controls(_ s: ResidentState) -> some View {
        HStack(alignment: .top, spacing: 10) {
            ControlTile(symbol: s.stopped ? "play.fill" : "pause.fill",
                        title: s.stopped ? "Weiterarbeiten" : "Anhalten",
                        caption: s.stopped ? "Er darf wieder Aufträge geben."
                            : "Er beobachtet weiter, gibt aber keine Aufträge.",
                        tint: s.stopped ? Palette.brass : Palette.clayText) {
                busy = true
                Task {
                    note = await model.setStopped(!s.stopped)
                    busy = false
                }
            }
            .disabled(busy)
            .accessibilityIdentifier("bewohner-anhalten")
            ControlTile(symbol: "eye",
                        title: s.waking ? "Schaut gleich …" : "Jetzt nachsehen",
                        caption: "Sofort prüfen – nicht erst bei der nächsten Veränderung.",
                        tint: Palette.brass) {
                Task { note = await model.wake() }
            }
            .disabled(!s.alive || s.stopped || s.waking)
            .opacity(!s.alive || s.stopped ? 0.45 : 1)
            .accessibilityIdentifier("bewohner-wecken")
        }
    }

    // MARK: what it did

    @ViewBuilder private var cycles: some View {
        let all = ResidentCycle.from(model.entries)
        if all.isEmpty {
            Text(model.connected ? "Bisher nichts – er hat noch nichts gefunden, das zu tun wäre."
                 : "Wird geladen …")
                .font(Face.ui(13)).foregroundStyle(Palette.meta)
        }
        VStack(spacing: 10) {
            ForEach(all.prefix(8)) { c in
                CycleCard(cycle: c) { key in app.open(session: key, machine: model.machine?.name) }
            }
        }
    }

    private func link(_ title: String, _ symbol: String, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: symbol).font(.system(size: 12, weight: .light)).foregroundStyle(Palette.brass)
                Text(title).font(Face.ui(14.5)).foregroundStyle(Palette.text)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(id)
    }

    // MARK: formatting

    static func clock(_ ts: Double?) -> String {
        guard let ts else { return "" }
        let d = Date(timeIntervalSince1970: ts)
        let f = DateFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = Calendar.current.isDateInToday(d) ? "HH:mm" : "dd.MM. HH:mm"
        return f.string(from: d)
    }

    static func ago(_ ts: Double?, now: Date = Date()) -> String {
        guard let ts else { return "?" }
        let s = max(0, Int(now.timeIntervalSince1970 - ts))
        if s < 60 { return "\(s) s" }
        if s < 3600 { return "\(s / 60) min" }
        return "\(s / 3600) h"
    }
}

// MARK: - the pulse

/// What state it is in, drawn: breathing while it watches, quicker while it
/// thinks, circling while it works, still when stopped or gone.
struct ResidentPulse: View {
    let state: ResidentState
    let doing: String

    enum Mode { case watching, thinking, working, stopped, off }

    var mode: Mode {
        if state.stopped { return .stopped }
        if !state.alive { return .off }
        switch state.state {
        case "denkt": return .thinking
        case "arbeitet": return .working
        default: return .watching
        }
    }

    private var title: String {
        switch mode {
        case .watching: return "Wach"
        case .thinking: return "Denkt nach"
        case .working: return "Arbeitet"
        case .stopped: return "Angehalten"
        case .off: return "Aus"
        }
    }

    var body: some View {
        HStack(alignment: .center, spacing: 18) {
            Orb(mode: mode).frame(width: 96, height: 96)
            VStack(alignment: .leading, spacing: 6) {
                Text(title)
                    .font(Face.display(32))
                    .foregroundStyle(mode == .stopped ? Palette.clayText : Palette.text)
                    .accessibilityIdentifier("bewohner-zustand")
                Text(doing)
                    .font(Face.ui(13.5))
                    .foregroundStyle(Palette.soft)
                    .fixedSize(horizontal: false, vertical: true)
                TimelineView(.periodic(from: .now, by: 1)) { t in
                    Text(meta(t.date)).font(Face.mono(9.5)).foregroundStyle(Palette.meta)
                }
            }
        }
    }

    private func meta(_ now: Date) -> String {
        var parts = [state.model, state.machine].compactMap { $0 }
        if state.seen != nil { parts.append("zuletzt vor \(ResidentPanel.ago(state.seen, now: now))") }
        return parts.joined(separator: " · ")
    }
}

private struct Orb: View {
    let mode: ResidentPulse.Mode

    private var color: Color {
        switch mode {
        case .watching: return Palette.sage
        case .thinking, .working: return Palette.brass
        case .stopped: return Palette.clay
        case .off: return Palette.faint
        }
    }

    /// Seconds for one ring to spread, and how many at once.
    private var rhythm: (period: Double, rings: Int) {
        switch mode {
        case .watching: return (4.0, 2)
        case .thinking: return (1.4, 3)
        case .working: return (2.4, 2)
        case .stopped, .off: return (0, 0)
        }
    }

    var body: some View {
        // Twelve frames a second is plenty for a slow pulse.
        TimelineView(.animation(minimumInterval: 1.0 / 12, paused: mode == .off || mode == .stopped)) { tl in
            Canvas { ctx, size in
                let t = tl.date.timeIntervalSinceReferenceDate
                let c = CGPoint(x: size.width / 2, y: size.height / 2)
                let r = min(size.width, size.height) / 2
                let (period, rings) = rhythm
                if period > 0 {
                    for i in 0..<rings {
                        let phase = (t / period + Double(i) / Double(rings)).truncatingRemainder(dividingBy: 1)
                        let rr = r * (0.44 + 0.56 * phase)
                        ctx.stroke(Path(ellipseIn: CGRect(x: c.x - rr, y: c.y - rr, width: rr * 2, height: rr * 2)),
                                   with: .color(color.opacity(0.55 * (1 - phase))), lineWidth: 1.2)
                    }
                } else {
                    let rr = r * 0.7
                    ctx.stroke(Path(ellipseIn: CGRect(x: c.x - rr, y: c.y - rr, width: rr * 2, height: rr * 2)),
                               with: .color(color.opacity(0.35)), lineWidth: 1)
                }
                let core = r * 0.4
                ctx.fill(Path(ellipseIn: CGRect(x: c.x - core, y: c.y - core, width: core * 2, height: core * 2)),
                         with: .radialGradient(Gradient(colors: [color.opacity(0.95), color.opacity(0.18)]),
                                               center: c, startRadius: 0, endRadius: core))
                if mode == .working {
                    let a = Angle.degrees((t / 2.0).truncatingRemainder(dividingBy: 1) * 360)
                    var arc = Path()
                    arc.addArc(center: c, radius: r * 0.62, startAngle: a, endAngle: a + .degrees(110), clockwise: false)
                    ctx.stroke(arc, with: .color(color), style: StrokeStyle(lineWidth: 2.2, lineCap: .round))
                }
            }
        }
        .accessibilityHidden(true)
    }
}

/// A button that says what it does.
private struct ControlTile: View {
    let symbol: String
    let title: String
    let caption: String
    let tint: Color
    let action: () -> Void

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 16, style: .continuous)
        Button(action: action) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 7) {
                    Image(systemName: symbol).font(.system(size: 11, weight: .semibold)).foregroundStyle(tint)
                    Text(title).font(Face.ui(14.5, .regular)).foregroundStyle(tint)
                }
                Text(caption).font(Face.ui(11.5)).foregroundStyle(Palette.meta)
                    .fixedSize(horizontal: false, vertical: true)
                    .multilineTextAlignment(.leading)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .contentShape(shape)
        }
        .buttonStyle(.plain)
        .inked(shape, Color(hex: 0xEFECE5, opacity: 0.035))
        .gilt(shape, strength: 0.35)
    }
}

// MARK: - the day at a glance

/// Its time in lanes, one per kind of thing, each named: how often it
/// looked, what it noticed, when Claude worked, errors, and your questions.
/// Tap or drag across to see what happened in that stretch.
struct DayStrip: View {
    let entries: [ResidentEntry]
    @State private var picked: Int?
    @State private var laneWidth: CGFloat = 1

    static let buckets = 36
    private static let label: CGFloat = 64

    struct Lane {
        let name: String
        let kinds: Set<String>
        let color: Color
        let heat: Bool
    }

    static let lanes: [Lane] = [
        Lane(name: "Blicke", kinds: ["tick"], color: Palette.faint, heat: true),
        Lane(name: "Bemerkt", kinds: ["fund", "pause", "antrag"], color: Palette.brass, heat: false),
        Lane(name: "Claude", kinds: ["auftrag", "ergebnis", "pruefung"], color: Palette.brassDeep, heat: false),
        Lane(name: "Fehler", kinds: ["fehler"], color: Palette.clay, heat: false),
        Lane(name: "Gespräch", kinds: ["frage", "zuruf"], color: Palette.soft, heat: false),
    ]

    /// Seconds shown: from the first line on, at least an hour, at most twelve.
    static func span(_ entries: [ResidentEntry], now: Double) -> Double {
        let first = entries.compactMap(\.ts).min() ?? now
        return min(max((now - first) * 1.04, 3600), 12 * 3600)
    }

    static func title(_ entries: [ResidentEntry]) -> String {
        let now = Date().timeIntervalSince1970
        let span = span(entries, now: now)
        if span >= 12 * 3600 { return "Die letzten 12 Stunden" }
        return "Seit \(ResidentPanel.clock(now - span))"
    }

    var body: some View {
        TimelineView(.periodic(from: .now, by: 30)) { tl in
            let now = tl.date.timeIntervalSince1970
            let span = Self.span(entries, now: now)
            let start = now - span
            let step = span / Double(Self.buckets)
            let grid = counts(start: start, step: step)
            let stopped = stoppedBuckets(start: start, step: step, now: now)
            VStack(alignment: .leading, spacing: 7) {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(Self.lanes.indices, id: \.self) { li in
                        HStack(spacing: 0) {
                            Text(Self.lanes[li].name)
                                .font(Face.mono(9)).foregroundStyle(Palette.meta)
                                .frame(width: Self.label, alignment: .leading)
                            laneRow(Self.lanes[li], grid[li], stopped: stopped)
                                .frame(height: 16)
                        }
                    }
                }
                .contentShape(Rectangle())
                .gesture(DragGesture(minimumDistance: 0).onChanged { g in
                    let x = g.location.x - Self.label
                    guard x >= 0 else { return }
                    picked = min(Self.buckets - 1, max(0, Int(x / max(laneWidth, 1) * CGFloat(Self.buckets))))
                })
                HStack(spacing: 0) {
                    Spacer().frame(width: Self.label)
                    Text(ResidentPanel.clock(start))
                    Spacer()
                    Text(ResidentPanel.clock(start + span / 2))
                    Spacer()
                    Text("jetzt")
                }
                .font(Face.mono(9)).foregroundStyle(Palette.faint)
                detail(start: start, step: step)
                    .padding(.top, 4)
            }
        }
    }

    private func laneRow(_ lane: Lane, _ counts: [Int], stopped: Set<Int>) -> some View {
        Canvas { ctx, size in
            let w = size.width / CGFloat(Self.buckets)
            let peak = max(counts.max() ?? 1, 1)
            for i in 0..<Self.buckets {
                let r = CGRect(x: CGFloat(i) * w + 0.5, y: 0, width: w - 1, height: size.height)
                if stopped.contains(i) {
                    // One quiet band for the stopped time, not a box per stretch.
                    let band = CGRect(x: CGFloat(i) * w, y: size.height / 2 - 1, width: w, height: 2)
                    ctx.fill(Path(band), with: .color(Palette.clay.opacity(0.45)))
                }
                if picked == i {
                    ctx.fill(Path(r), with: .color(Palette.brass.opacity(0.16)))
                }
                let n = counts[i]
                guard n > 0 else { continue }
                if lane.heat {
                    let a = 0.18 + 0.62 * Double(n) / Double(peak)
                    ctx.fill(Path(roundedRect: r.insetBy(dx: 0.5, dy: 4), cornerRadius: 2), with: .color(lane.color.opacity(a)))
                } else {
                    let d = min(w - 1.5, 5 + CGFloat(min(n, 4)) * 1.2)
                    let c = CGPoint(x: r.midX, y: r.midY)
                    ctx.fill(Path(ellipseIn: CGRect(x: c.x - d / 2, y: c.y - d / 2, width: d, height: d)), with: .color(lane.color))
                }
            }
        }
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { laneWidth = $0 }
    }

    private func bucket(_ ts: Double, start: Double, step: Double) -> Int? {
        let i = Int((ts - start) / step)
        return (0..<Self.buckets).contains(i) ? i : nil
    }

    private func counts(start: Double, step: Double) -> [[Int]] {
        var grid = Array(repeating: Array(repeating: 0, count: Self.buckets), count: Self.lanes.count)
        for e in entries {
            guard let ts = e.ts, let i = bucket(ts, start: start, step: step) else { continue }
            for (li, lane) in Self.lanes.enumerated() where lane.kinds.contains(e.kind) {
                grid[li][i] += 1
            }
        }
        return grid
    }

    private func stoppedBuckets(start: Double, step: Double, now: Double) -> Set<Int> {
        var out = Set<Int>()
        var from: Double?
        func mark(_ a: Double, _ b: Double) {
            var t = max(a, start)
            while t <= min(b, now) {
                if let i = bucket(t, start: start, step: step) { out.insert(i) }
                t += step / 2
            }
        }
        for e in entries {
            if e.kind == "stop" { from = from ?? e.ts }
            if e.kind == "weiter" || (e.kind == "tick" && (e.text ?? "").hasPrefix("weiter")), let f = from {
                mark(f, e.ts ?? now)
                from = nil
            }
        }
        if let f = from { mark(f, now) }
        return out
    }

    /// What happened in the picked stretch, in words.
    @ViewBuilder private func detail(start: Double, step: Double) -> some View {
        if let p = picked {
            let a = start + Double(p) * step
            let inside = entries.filter { ($0.ts ?? 0) >= a && ($0.ts ?? 0) < a + step && $0.kind != "stimme" && $0.kind != "antwort" }
            let looks = inside.filter { $0.kind == "tick" }.count
            let rest = inside.filter { $0.kind != "tick" }
            VStack(alignment: .leading, spacing: 5) {
                HStack {
                    Text("\(ResidentPanel.clock(a))–\(ResidentPanel.clock(a + step))")
                        .font(Face.mono(10.5)).foregroundStyle(Palette.brass)
                    Spacer()
                    Button("schließen") { picked = nil }.font(Face.ui(11.5)).foregroundStyle(Palette.meta).buttonStyle(.plain)
                }
                if inside.isEmpty {
                    Text("Nichts in dieser Zeit.").font(Face.ui(12.5)).foregroundStyle(Palette.meta)
                }
                if looks > 0 {
                    Text("\(looks)× nachgesehen, nichts zu tun").font(Face.ui(12.5)).foregroundStyle(Palette.meta)
                }
                ForEach(rest.suffix(6)) { e in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(ResidentJournalSheet.word(e)).font(Face.mono(8.5)).tracking(0.6)
                            .foregroundStyle(ResidentJournalSheet.tint(e))
                        Text(e.text ?? "").font(Face.ui(12.5)).foregroundStyle(Palette.soft).lineLimit(2)
                    }
                }
            }
            .padding(12)
            .background(Palette.hair, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        } else {
            Text("Tippen oder ziehen, um zu sehen, was wann war.").font(Face.ui(11.5)).foregroundStyle(Palette.hint)
        }
    }
}

/// Today in four numbers - each opens what it counts.
struct TodayNumbers: View {
    let entries: [ResidentEntry]
    let budget: ResidentBudget?
    let open: (JournalFilter) -> Void
    let talk: () -> Void

    var body: some View {
        let start = Calendar.current.startOfDay(for: Date()).timeIntervalSince1970
        let today = entries.filter { ($0.ts ?? 0) >= start }
        HStack(alignment: .firstTextBaseline, spacing: 22) {
            number(today.filter { $0.kind == "auftrag" }.count, "Aufträge") { open(.orders) }
            number(today.filter { $0.kind == "fund" || $0.kind == "pause" }.count, "bemerkt") { open(.noticed) }
            number(today.filter { $0.kind == "tick" }.count, "Blicke") { open(.looks) }
            number(today.filter { $0.kind == "frage" }.count, "Fragen", action: talk)
            Spacer()
        }
        if let h = budget?.ordersHour, let m = budget?.ordersHourMax {
            Text("diese Stunde \(h) von \(m) Aufträgen").font(Face.mono(9.5)).foregroundStyle(Palette.meta).padding(.top, 4)
        }
    }

    private func number(_ n: Int, _ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 2) {
                Text("\(n)").font(Face.display(26)).foregroundStyle(Palette.text)
                HStack(spacing: 3) {
                    Text(label).font(Face.ui(11)).foregroundStyle(Palette.meta)
                    Image(systemName: "chevron.right").font(.system(size: 7, weight: .semibold)).foregroundStyle(Palette.faint)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// Which lines the journal sheet shows.
enum JournalFilter: String, Identifiable {
    case all, orders, noticed, looks
    var id: String { rawValue }

    var title: String {
        switch self {
        case .all: return "Journal"
        case .orders: return "Aufträge"
        case .noticed: return "Bemerkt"
        case .looks: return "Blicke"
        }
    }

    func keeps(_ e: ResidentEntry) -> Bool {
        switch self {
        case .all: return !e.spoken
        case .orders: return ["auftrag", "ergebnis", "pruefung"].contains(e.kind)
        case .noticed: return ["fund", "pause", "antrag", "entscheidung"].contains(e.kind)
        case .looks: return e.kind == "tick"
        }
    }
}

/// What it keeps an eye on, as the resident names it.
struct SensesRow: View {
    let watching: [String]
    let awake: Bool

    var body: some View {
        Flow(spacing: 8, lineSpacing: 8) {
            ForEach(watching, id: \.self) { name in
                HStack(spacing: 7) {
                    Image(systemName: Self.symbol(name)).font(.system(size: 11, weight: .light))
                        .foregroundStyle(awake ? Palette.sage : Palette.faint)
                    Text(name).font(Face.ui(12.5)).foregroundStyle(awake ? Palette.text : Palette.meta)
                }
                .padding(.horizontal, 11).padding(.vertical, 7)
                .overlay(Capsule().stroke(Palette.hair, lineWidth: 1))
            }
        }
    }

    static func symbol(_ name: String) -> String {
        let n = name.lowercased()
        if n.contains("dienst") { return "gearshape.2" }
        if n.contains("ollama") || n.contains("modell") { return "cpu" }
        if n.contains("platte") || n.contains("disk") { return "internaldrive" }
        if n.contains("brücke") || n.contains("bruecke") { return "point.3.connected.trianglepath.dotted" }
        if n.contains("werkstatt") { return "folder" }
        return "circle.dotted"
    }
}

// MARK: - what it did

/// One piece of work, from what it noticed to the check: built from the
/// journal, which only has lines.
struct ResidentCycle: Identifiable {
    enum Stage { case noticed, held, working, done, checked, failed }

    var id: Int
    var ts: Double
    var title: String
    var why: String?
    var fromYou = false
    var order: String?
    var held: String?
    var result: String?
    var check: String?
    var checkOK: Bool?
    var failure: String?
    var session: String?
    var seconds: Double?
    var request = false
    var stage: Stage = .noticed

    static func from(_ entries: [ResidentEntry]) -> [ResidentCycle] {
        var out: [ResidentCycle] = []
        for e in entries where !e.spoken {
            let last = out.indices.last
            switch e.kind {
            case "zuruf":
                var c = ResidentCycle(id: e.seq, ts: e.ts ?? 0, title: e.text ?? "")
                c.fromYou = true
                out.append(c)
            case "fund":
                let plan = planned(e.detail)
                if let i = last, out[i].fromYou, out[i].why == nil, out[i].stage == .noticed {
                    out[i].why = e.text
                    out[i].order = plan
                } else {
                    var c = ResidentCycle(id: e.seq, ts: e.ts ?? 0, title: e.text ?? "")
                    c.order = plan
                    out.append(c)
                }
            case "pause":
                if let i = last { out[i].held = e.text; out[i].stage = .held }
            case "tick":
                if let t = e.text, t.hasPrefix("Auftrag zurückgehalten"), let i = last {
                    out[i].held = t
                    out[i].stage = .held
                }
            case "auftrag":
                if let i = last, out[i].stage == .noticed || out[i].stage == .held {
                    out[i].order = e.text
                    out[i].held = nil
                    out[i].session = e.sessionKey
                    out[i].stage = .working
                } else {
                    var c = ResidentCycle(id: e.seq, ts: e.ts ?? 0, title: e.text ?? "")
                    c.order = e.text
                    c.session = e.sessionKey
                    c.stage = .working
                    out.append(c)
                }
            case "ergebnis":
                if let i = last {
                    out[i].result = e.text
                    out[i].seconds = e.seconds
                    out[i].session = out[i].session ?? e.sessionKey
                    out[i].stage = .done
                }
            case "pruefung":
                if let i = last {
                    out[i].check = e.text
                    out[i].checkOK = e.ok
                    out[i].stage = e.ok == false ? .failed : .checked
                }
            case "fehler":
                // Errors of the voice belong to the conversation.
                if e.ref == nil, let i = last, out[i].stage == .working {
                    out[i].failure = e.text
                    out[i].stage = .failed
                }
            case "antrag":
                var c = ResidentCycle(id: e.seq, ts: e.ts ?? 0, title: e.text ?? "")
                c.request = true
                out.append(c)
            case "entscheidung":
                if let i = out.lastIndex(where: { $0.request }) {
                    // The journal already writes a whole sentence with its own
                    // subject ("Calvin hat genehmigt: …"). Putting "Du hast"
                    // in front of it produced "Du hast Calvin hat genehmigt".
                    out[i].result = e.text ?? "Du hast entschieden."
                    out[i].stage = .done
                }
            default:
                break
            }
        }
        return out.reversed()
    }

    /// The order gpt-oss wanted to give, from a finding's detail.
    private static func planned(_ detail: String?) -> String? {
        guard let d = detail?.data(using: .utf8),
              let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return nil }
        return (o["auftrag"] as? String).flatMap { $0.isEmpty ? nil : $0 }
    }
}

struct CycleCard: View {
    let cycle: ResidentCycle
    let openSession: (String) -> Void
    @State private var open = false

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 16, style: .continuous)
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(ResidentPanel.clock(cycle.ts)).font(Face.mono(10.5)).foregroundStyle(Palette.meta)
                if cycle.fromYou {
                    Text("DEIN ZURUF").font(Face.mono(9)).tracking(0.8).foregroundStyle(Palette.brass)
                }
                if cycle.request {
                    Text("ANTRAG").font(Face.mono(9)).tracking(0.8).foregroundStyle(Palette.brassLight)
                }
                Spacer()
                Text(stageLabel).font(Face.mono(9)).tracking(0.8).foregroundStyle(stageColor)
            }
            Text(cycle.title).font(Face.ui(15)).foregroundStyle(Palette.text)
                .fixedSize(horizontal: false, vertical: true)
            if !cycle.request {
                StageTrack(stage: cycle.stage).padding(.vertical, 2)
            }
            if let why = cycle.why, why != cycle.title { detail("Bemerkt", why) }
            if let o = cycle.order {
                detail(cycle.stage == .noticed || cycle.stage == .held ? "Wollte Claude beauftragen" : "Auftrag an Claude", o)
            }
            if let h = cycle.held {
                Text(h.replacingOccurrences(of: "Auftrag zurückgehalten", with: "Zurückgehalten"))
                    .font(Face.ui(12.5)).foregroundStyle(Palette.brass)
            }
            if let r = cycle.result {
                detail(cycle.seconds.map { "Ergebnis nach \(Int($0)) s" } ?? "Ergebnis", r, limit: open ? nil : 3)
            }
            if let c = cycle.check {
                detail(cycle.checkOK == false ? "Prüfung fehlgeschlagen" : "Geprüft", c)
            }
            if let f = cycle.failure {
                Text(f).font(Face.ui(12.5)).foregroundStyle(Palette.clayText)
            }
            if let key = cycle.session {
                Button { openSession(key) } label: {
                    Text("In der Sitzung ansehen →").font(Face.ui(12.5)).foregroundStyle(Palette.brass)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .inked(shape, Color(hex: 0xEFECE5, opacity: 0.035))
        .gilt(shape, strength: 0.3)
        .contentShape(shape)
        .onTapGesture { open.toggle() }
    }

    private var stageLabel: String {
        switch cycle.stage {
        case .noticed: return cycle.request ? "WARTET AUF DICH" : "BEMERKT"
        case .held: return "ZURÜCKGEHALTEN"
        case .working: return "LÄUFT"
        case .done: return "ERLEDIGT"
        case .checked: return "GEPRÜFT ✓"
        case .failed: return "FEHLGESCHLAGEN"
        }
    }

    private var stageColor: Color {
        switch cycle.stage {
        case .held, .working: return Palette.brass
        case .checked: return Palette.sage
        case .failed: return Palette.clayText
        default: return Palette.meta
        }
    }

    /// A detail under a piece of work. Your own words are never cut: a call
    /// of yours ended mid-sentence at four lines, and what was missing was
    /// exactly the part that said what to do about it.
    private func detail(_ label: String, _ text: String, limit: Int? = 4) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label.uppercased()).font(Face.mono(8.5)).tracking(0.8).foregroundStyle(Palette.faint)
            Text(text).font(Face.ui(12.5)).foregroundStyle(Palette.soft)
                .lineLimit(label.caseInsensitiveCompare("dein zuruf") == .orderedSame ? nil : limit)
        }
    }
}

/// Noticed, ordered, done, checked - how far a piece of work got.
struct StageTrack: View {
    let stage: ResidentCycle.Stage
    private let names = ["bemerkt", "beauftragt", "erledigt", "geprüft"]

    private var reached: Int {
        switch stage {
        case .noticed, .held: return 1
        case .working: return 2
        case .done: return 3
        case .checked, .failed: return 4
        }
    }

    var body: some View {
        HStack(spacing: 0) {
            ForEach(0..<4, id: \.self) { i in
                VStack(spacing: 5) {
                    Circle()
                        .fill(fill(i))
                        .overlay(Circle().stroke(stroke(i), style: StrokeStyle(lineWidth: 1, dash: stage == .held && i == 1 ? [2, 2] : [])))
                        .frame(width: 10, height: 10)
                    Text(names[i]).font(Face.mono(8.5)).foregroundStyle(i < reached ? Palette.soft : Palette.faint)
                }
                .frame(maxWidth: .infinity)
            }
        }
        .background(alignment: .top) {
            Rectangle().fill(Palette.hair).frame(height: 1).padding(.horizontal, 36).padding(.top, 4.5)
        }
    }

    private func fill(_ i: Int) -> Color {
        if stage == .failed && i == reached - 1 { return Palette.clay }
        guard i < reached else { return Palette.ground }
        return i == 3 ? Palette.sage : Palette.brass
    }

    private func stroke(_ i: Int) -> Color {
        if stage == .held && i == 1 { return Palette.brass }
        return i < reached ? .clear : Palette.faint.opacity(0.6)
    }
}

// MARK: - talking

/// The door to the conversation: the last answer, and the button to speak.
struct TalkEntry: View {
    let model: ResidentModel
    let open: () -> Void

    var body: some View {
        let answer = model.entries.last(where: { $0.kind == "antwort" })
        Button(action: open) {
            HStack(spacing: 14) {
                ZStack {
                    Circle().fill(Palette.brass)
                    Image(systemName: "mic.fill").font(.system(size: 17)).foregroundStyle(Palette.onBrass)
                }
                .frame(width: 50, height: 50)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Mit ihm sprechen").font(Face.ui(15, .regular)).foregroundStyle(Palette.text)
                    if let answer {
                        Text("„\(model.answerText(answer))“").font(Face.ui(12.5)).foregroundStyle(Palette.meta).lineLimit(2)
                    } else {
                        Text("Frag ihn, was er gerade tut – er antwortet mit seiner Stimme.")
                            .font(Face.ui(12.5)).foregroundStyle(Palette.meta)
                    }
                }
                Spacer(minLength: 0)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("bewohner-sprechen")
    }
}

/// Always at the bottom of the resident's page: talk to it - the one thing
/// that must never be a scroll away.
struct ResidentTalkBar: View {
    let model: ResidentModel
    @State private var sheet: TalkOpening?

    enum TalkOpening: Identifiable {
        case voice, text
        var id: Self { self }
    }

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 26, style: .continuous)
        HStack(spacing: 10) {
            Button { sheet = .text } label: {
                HStack(spacing: 10) {
                    Image(systemName: "bubble.left.and.text.bubble.right").font(.system(size: 14, weight: .light))
                        .foregroundStyle(Palette.brass)
                    Text(model.waitingFor != nil ? "Er antwortet gleich …" : "Mit dem Bewohner sprechen")
                        .font(Face.ui(15)).foregroundStyle(Palette.text)
                    Spacer(minLength: 0)
                }
                .padding(.leading, 16)
                .frame(maxHeight: .infinity)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("bewohner-gespraech")
            Button { sheet = .voice } label: {
                ZStack {
                    Circle().fill(Palette.brass)
                    Image(systemName: "mic.fill").font(.system(size: 16)).foregroundStyle(Palette.onBrass)
                }
                .frame(width: 44, height: 44)
            }
            .buttonStyle(.plain)
            .padding(.trailing, 6)
            .accessibilityLabel("Sprechen")
            .accessibilityIdentifier("bewohner-mikrofon-leiste")
        }
        .frame(height: 56)
        .inked(shape, Color(hex: 0x2E2A25, opacity: 0.94))
        .gilt(shape, strength: 0.6)
        .padding(.horizontal, 16)
        .padding(.bottom, 8)
        .sheet(item: $sheet) { how in ResidentTalkSheet(model: model, listenAtOnce: how == .voice) }
    }
}

/// The conversation itself: ask by voice or text, hear the answer in the
/// PC's voice. In conversation mode it listens again after each answer.
struct ResidentTalkSheet: View {
    @Environment(\.dismiss) private var dismiss
    let model: ResidentModel
    /// Opened by the microphone: listen right away.
    var listenAtOnce = false
    @State private var word = ""
    @State private var note: String?
    @State private var dictation = Dictation()
    @State private var spokenBase = ""
    @AppStorage("iris.bewohner.gespraech") private var conversation = false
    /// Answers out loud, or in writing only. Kept across launches: whoever
    /// wants it quiet should not have to say so again every time.
    @AppStorage("iris.bewohner.stimme") private var outLoud = true
    /// Which ear listens. The newer transcriber looked better in German on
    /// paper; whether it is better in this room is Calvin's call, not mine.
    @AppStorage("iris.diktat.neu") private var neuesDiktat = true
    /// Die früheren Gespräche, und welches davon gerade offen ist.
    @State private var frueher: [ResidentGespraech] = []
    @State private var zeigeFrueher = false
    @State private var geoeffnet: ResidentGespraechBody?

    /// Nach so langer Stille ist ein Gespräch zu Ende. Dieselbe Zahl wie
    /// `sitzung.RUHE_MIN` beim Bewohner: Er schließt die Sitzung dann ab,
    /// fasst sie zusammen und legt sie ins Gedächtnis. Was archiviert ist,
    /// gehört nicht mehr in den Chat.
    static let gespraechsEnde: Double = 10 * 60

    /// NUR DAS LAUFENDE GESPRÄCH.
    ///
    /// Vorher standen hier die letzten dreißig Frage- und Antwortzeilen aus
    /// dem ganzen Journal - ohne Sitzungsgrenze und ohne Absender. Calvin
    /// öffnete den Chat und las Nachrichten von gestern Abend, dazwischen
    /// Testfragen aus den Proben. Ein Chat, der nie endet, ist kein Chat,
    /// sondern ein Protokoll.
    /// Die Liste der früheren Gespräche.
    private var frueherListe: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    if frueher.isEmpty {
                        Text("Noch keine abgeschlossenen Gespräche.")
                            .font(Face.ui(13)).foregroundStyle(Palette.meta)
                            .padding(.vertical, 24)
                    }
                    ForEach(frueher) { g in
                        Button {
                            zeigeFrueher = false
                            Task { geoeffnet = await model.gespraech(g.id) }
                        } label: {
                            zeile(g)
                        }
                        .buttonStyle(.plain)
                        Divider().overlay(Palette.faint)
                    }
                }
                .padding(18)
            }
            .background(Room())
            .navigationTitle("Frühere Gespräche")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) {
                Button("Fertig") { zeigeFrueher = false } } }
        }
    }

    /// Eine Zeile der Liste. Eigene Funktion, weil der Übersetzer den
    /// Ausdruck sonst nicht in vertretbarer Zeit prüfen kann.
    private func zeile(_ g: ResidentGespraech) -> some View {
        // Ohne Zusammenfassung ist es noch offen oder er hatte nichts zu
        // sagen - beides ist kein Fehler, und beides gehört benannt.
        let offen = g.geschlossen == nil
        let untertitel = g.zusammenfassung
            ?? (offen ? "läuft noch" : "keine Zusammenfassung")
        let anzahl = g.paare == 1 ? "1 Frage" : "\(g.paare) Fragen"
        return VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(Self.wann(g.zuletzt))
                Spacer()
                Text(anzahl)
            }
            .font(Face.mono(11))
            .foregroundStyle(Palette.meta)
            Text(untertitel)
                .font(Face.ui(14))
                .foregroundStyle(g.zusammenfassung == nil ? Palette.meta : Palette.text)
                .multilineTextAlignment(.leading)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 12)
    }

    /// Ein früheres Gespräch, zum Lesen - geantwortet wird im laufenden.
    private func frueherGespraech(_ g: ResidentGespraechBody) -> some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if let z = g.kopf?.zusammenfassung {
                        Text(z).font(Face.ui(13)).foregroundStyle(Palette.meta)
                            .padding(.bottom, 4)
                    }
                    ForEach(g.paare) { p in
                        if let f = p.frage, !f.isEmpty {
                            blase(f, meins: true)
                        }
                        if let a = p.antwort, !a.isEmpty {
                            blase(a, meins: false)
                        }
                    }
                    if g.paare.isEmpty {
                        Text("Dieses Gespräch hat keinen Wortlaut mehr.")
                            .font(Face.ui(13)).foregroundStyle(Palette.meta)
                    }
                }
                .padding(18)
            }
            .background(Room())
            .navigationTitle(Self.wann(g.kopf?.zuletzt))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) {
                Button("Fertig") { geoeffnet = nil } } }
        }
    }

    private func blase(_ text: String, meins: Bool) -> some View {
        HStack {
            if meins { Spacer(minLength: 40) }
            Text(text)
                .font(Face.ui(14.5))
                .foregroundStyle(Palette.text)
                .padding(.horizontal, 13).padding(.vertical, 9)
                .background(meins ? Palette.brass.opacity(0.18)
                                  : Palette.faint.opacity(0.5),
                            in: RoundedRectangle(cornerRadius: 13))
            if !meins { Spacer(minLength: 40) }
        }
    }

    static func wann(_ ts: Double?) -> String {
        guard let ts, ts > 0 else { return "" }
        let d = Date(timeIntervalSince1970: ts)
        let f = DateFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = Calendar.current.isDateInToday(d) ? "'heute' HH:mm"
                     : Calendar.current.isDateInYesterday(d) ? "'gestern' HH:mm"
                     : "d. MMM HH:mm"
        return f.string(from: d)
    }

    private var exchange: [ResidentEntry] {
        // `antwort_teil` ist ein Satz der Antwort, sobald er steht - er
        // erscheint, WÄHREND gesprochen wird, und nicht erst danach. Ist die
        // ganze Antwort da, ersetzt sie ihre Teile: sonst stünde derselbe
        // Satz zweimal untereinander.
        let fertige = Set(model.entries.filter { $0.kind == "antwort" }
                                       .compactMap(\.ref))
        let seine = model.entries.filter { e in
            guard !e.ausProbe else { return false }
            if e.kind == "antwort_teil" {
                return !fertige.contains(e.ref ?? "")
            }
            return e.kind == "frage" || e.kind == "antwort" || e.kind == "ansprache"
        }
        // Von hinten bis zur ersten Lücke: alles davor ist ein anderes,
        // abgeschlossenes Gespräch.
        var heraus: [ResidentEntry] = []
        var jüngere: Double?
        for e in seine.reversed() {
            let t = e.ts ?? 0
            if let j = jüngere, j - t > Self.gespraechsEnde { break }
            heraus.append(e)
            jüngere = t
        }
        return Array(heraus.reversed().suffix(60))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(exchange) { e in bubble(e) }
                    if let w = model.waitingFor {
                        let ahead = model.ahead(of: w)
                        HStack(spacing: 8) {
                            Bud(size: 9)
                            Text(ahead > 0 ? "\(ahead == 1 ? "Eine Frage ist" : "\(ahead) Fragen sind") vor deiner dran – er antwortet der Reihe nach."
                                 : "denkt über die Antwort nach … Was du jetzt sagst, geht als Nachtrag mit.")
                                .font(Face.ui(12.5)).foregroundStyle(Palette.meta)
                        }
                    } else if let busy = Self.busy(model.state?.waiting ?? []) {
                        HStack(spacing: 8) {
                            Bud(size: 9)
                            Text(busy).font(Face.ui(12.5)).foregroundStyle(Palette.meta)
                        }
                    }
                    if let p = model.problem, model.waitingFor == nil {
                        Text(p).font(Face.mono(10.5)).foregroundStyle(Palette.clayText)
                    }
                    if let note {
                        Text(note).font(Face.mono(10)).foregroundStyle(Palette.clayText)
                    }
                }
                .padding(18)
            }
            .defaultScrollAnchor(.bottom)
            .background(Room())
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 10) {
                    talkRow
                    Toggle(isOn: $outLoud) {
                        Text(outLoud ? "Antworten werden vorgelesen"
                                     : "Antworten nur als Text – er bleibt stumm")
                            .font(Face.ui(12)).foregroundStyle(Palette.meta)
                    }
                    .tint(Palette.brass)
                    .accessibilityIdentifier("bewohner-vorlesen")
                    if outLoud {
                        Toggle(isOn: $conversation) {
                            Text("Gesprächsmodus – hört nach jeder Antwort wieder zu, Reinsprechen unterbricht")
                                .font(Face.ui(12)).foregroundStyle(Palette.meta)
                        }
                        .tint(Palette.brass)
                    }
                    Toggle(isOn: $neuesDiktat) {
                        Text(neuesDiktat ? "Neue Spracherkennung (iOS 26)"
                                         : "Ältere Spracherkennung – greift beim nächsten Antippen")
                            .font(Face.ui(12)).foregroundStyle(Palette.meta)
                    }
                    .tint(Palette.brass)
                    .accessibilityIdentifier("bewohner-diktat")
                }
                .padding(.horizontal, 18).padding(.vertical, 10)
                .background(Palette.ground.opacity(0.92))
            }
            .navigationTitle("Gespräch")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } }
                // DER WEG ZURÜCK. Der Chat zeigt nur das laufende Gespräch;
                // ohne diesen Knopf wären die früheren nicht mehr erreichbar.
                ToolbarItem(placement: .navigation) {
                    Button {
                        zeigeFrueher = true
                        Task { frueher = await model.gespraeche() }
                    } label: {
                        Label("Frühere", systemImage: "clock.arrow.circlepath")
                    }
                    .accessibilityIdentifier("bewohner-frueher")
                }
            }
            .sheet(isPresented: $zeigeFrueher) { frueherListe }
            .sheet(item: $geoeffnet) { g in frueherGespraech(g) }
        }
        .onAppear {
            model.conversing = true
            model.voice = outLoud
            model.duplex = outLoud && conversation
            // Listen anew after an answer: what the microphone caught while
            // it played - its echo, if any got through - is dropped.
            model.answered = {
                guard conversation else { return }
                model.duck(false)
                if dictation.listening { dictation.fresh() } else { listen() }
            }
            if listenAtOnce { listen() }
        }
        .onChange(of: conversation) { _, on in
            model.duplex = outLoud && on
            if !on, dictation.duplex, model.speakingFor != nil { dictation.cancel() }
        }
        .onChange(of: outLoud) { _, on in
            model.voice = on
            model.duplex = on && conversation
            // Switched off mid-sentence: it stops now, not after the answer.
            if !on { model.silence() }
        }
        .onChange(of: model.speakingFor) { _, id in
            // An answer starts: in the conversation the microphone stays
            // open, so you can talk into it.
            guard id != nil, conversation, !dictation.listening else { return }
            spokenBase = ""
            Task { await dictation.start(duplex: true) }
        }
        .onChange(of: dictation.partial) { _, spoken in
            if model.speakingFor != nil, dictation.duplex {
                // Still speaking: only your own words cut it short - not its
                // echo, should the phone let some through.
                guard Self.interrupts(spoken, over: model.speakingText) else { return }
                model.silence()
            }
            word = [spokenBase, spoken].filter { !$0.isEmpty }.joined(separator: " ")
        }
        .task(id: dictation.listening) {
            // Hands free: while it listens, a watch decides when you are done.
            guard conversation, dictation.listening else { return }
            var drafted = ""
            while !Task.isCancelled, dictation.listening {
                try? await Task.sleep(for: .milliseconds(150))
                let now = Date()
                let wordsQuiet = now.timeIntervalSince(dictation.lastWords)
                let soundQuiet = now.timeIntervalSince(dictation.lastSound)
                // An answer is playing and you have not talked into it (yet):
                // a voice makes it softer, only words stop it (see interrupts).
                if model.speakingFor != nil {
                    if soundQuiet < 0.2 { model.duck(true) } else if soundQuiet > 1.2 { model.duck(false) }
                    continue
                }
                let text = word.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !dictation.partial.isEmpty, !text.isEmpty else { continue }
                let need = Self.pause(after: text)
                // Done: no new words for as long as the sentence needs, and
                // real quiet - no voice, no cough. A loud room would never be
                // quiet; the words alone decide a little later then.
                if wordsQuiet >= need && (soundQuiet >= min(need, 0.9) || wordsQuiet >= need + 2.5) {
                    ask()
                    break
                }
                // The first pause: it starts thinking on what stands so far.
                if wordsQuiet >= 0.6, soundQuiet >= 0.5, text != drafted, model.canDraft {
                    drafted = text
                    Task { await model.draft(text) }
                }
            }
        }
        .onDisappear {
            dictation.cancel()
            model.answered = nil
            model.duplex = false
            model.conversing = false
        }
    }

    /// How long a pause must last before your words go off: short after a
    /// finished sentence, long in the middle of one - "weil …", "und",
    /// an "ähm" or a comma keep it open for a breath or a cough.
    static func pause(after text: String) -> Double {
        guard let last = text.last else { return 9 }
        if ".?!".contains(last) { return 1.1 }
        if ",;:-–".contains(last) { return 2.4 }
        let word = text.lowercased().split { !$0.isLetter }.last.map(String.init) ?? ""
        let open: Set<String> = [
            "und", "oder", "aber", "dass", "weil", "wenn", "ob", "also", "denn", "sondern", "damit", "bis", "als",
            "um", "dann", "so", "noch", "mal", "sehr", "nicht", "kein", "keine", "ähm", "äh", "ehm", "hm", "mhm",
            "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "mein", "meine",
            "dein", "deine", "mit", "zu", "von", "für", "auf", "in", "im", "an", "am", "bei", "nach", "über",
            "unter", "vor", "aus", "wie", "ich", "du", "er", "sie", "wir", "es", "ihr"]
        if open.contains(word) { return 3.2 }
        return text.split(separator: " ").count < 3 ? 2.2 : 1.8
    }

    /// Whether what the microphone heard during an answer is you: a word to
    /// stop, or two words the answer does not contain.
    static func interrupts(_ heard: String, over answer: String?) -> Bool {
        func words(_ s: String) -> [String] {
            s.lowercased().split { !$0.isLetter && !$0.isNumber }.map(String.init)
        }
        let heardWords = words(heard)
        if heardWords.contains(where: { ["stopp", "stop", "halt", "warte", "moment"].contains($0) }) { return true }
        let said = Set(words(answer ?? ""))
        return heardWords.filter { !said.contains($0) }.count >= 2
    }

    /// Busy with questions that are not yours - before you ask.
    static func busy(_ waiting: [ResidentQueued]) -> String? {
        guard !waiting.isEmpty else { return nil }
        let tests = waiting.filter { $0.von == "test" }.count
        let n = waiting.count
        let what = n == 1 ? "eine Frage" : "\(n) Fragen"
        return tests == n ? "Beschäftigt: beantwortet gerade \(what) aus einem Test – deine kommen vorher dran."
            : "Beschäftigt: \(what) in der Warteschlange – er antwortet der Reihe nach."
    }

    @ViewBuilder private func bubble(_ e: ResidentEntry) -> some View {
        if e.kind == "frage", e.zu != nil {
            VStack(alignment: .trailing, spacing: 3) {
                Text("NACHTRAG").font(Face.mono(8.5)).tracking(0.8).foregroundStyle(Palette.brass)
                Text(e.text ?? "")
                    .font(Face.ui(14)).foregroundStyle(Palette.text)
                    .padding(.horizontal, 12).padding(.vertical, 8)
                    .background(Palette.brass.opacity(0.10), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            .frame(maxWidth: .infinity, alignment: .trailing)
            .padding(.leading, 40)
        } else if e.kind == "frage" {
            Text(e.text ?? "")
                .font(Face.ui(14)).foregroundStyle(Palette.text)
                .padding(.horizontal, 12).padding(.vertical, 8)
                .background(Palette.brass.opacity(0.10), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .frame(maxWidth: .infinity, alignment: .trailing)
                .padding(.leading, 40)
        } else {
            HStack(alignment: .top, spacing: 8) {
                // EIGENE KENNUNG, damit eine Probe genau DIESE Blase prueft.
                // Ohne sie fand der erste Versuch den Antworttext in der
                // Uebersicht DAHINTER und bestand, waehrend der Chat leer
                // blieb - ein Test, der den Fehler nicht sieht, ist keiner.
                Text(model.answerText(e)).font(Face.ui(14)).foregroundStyle(Palette.text)
                    .accessibilityIdentifier("bewohner-antwort")
                    .frame(maxWidth: .infinity, alignment: .leading)
                Button {
                    if model.speakingFor == e.ref { model.silence() } else { model.replay(e) }
                } label: {
                    Image(systemName: model.speakingFor == e.ref ? "stop.circle" : "speaker.wave.2")
                        .font(.system(size: 14, weight: .light)).foregroundStyle(Palette.brass)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(model.speakingFor == e.ref ? "Vorlesen stoppen" : "Vorlesen")
            }
            .padding(.trailing, 40)
        }
    }

    private var talkRow: some View {
        let shape = RoundedRectangle(cornerRadius: 22, style: .continuous)
        return HStack(spacing: 6) {
            TextField("", text: $word,
                      prompt: Text(dictation.listening ? "Ich höre zu …"
                                   : model.waitingFor != nil ? "Etwas nachschieben …" : "Etwas fragen …").foregroundStyle(Palette.hint),
                      axis: .vertical)
                .font(Face.ui(14.5))
                .foregroundStyle(Palette.text)
                .tint(Palette.brass)
                .lineLimit(1...5)
                .padding(.vertical, 11)
                .padding(.leading, 14)
                .accessibilityIdentifier("bewohner-frage")
            if dictation.available {
                RoundButton(symbol: dictation.listening ? "waveform" : "mic", active: dictation.listening) {
                    if dictation.listening { ask() } else { listen() }
                }
                .accessibilityIdentifier("bewohner-mikrofon")
            }
            if !word.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                RoundButton(symbol: "arrow.up", brass: true) { ask() }
                    .accessibilityIdentifier("bewohner-fragen")
                    .contextMenu {
                        // Not a question: a note it reads and keeps.
                        Button("Als Notiz ablegen", systemImage: "note.text") { keepAsNote() }
                    }
            }
        }
        .padding(.trailing, 4)
        .inked(shape, Color(hex: 0xEFECE5, opacity: 0.035))
        .gilt(shape)
    }

    private func listen() {
        model.silence()
        spokenBase = word.trimmingCharacters(in: .whitespacesAndNewlines)
        Task { await dictation.start(duplex: conversation) }
    }

    /// Send what stands in the field as a question. Dictation is cancelled,
    /// not stopped: a late result would put the words back.
    private func ask() {
        // Said aloud: the recording goes with it (taken before listening
        // starts anew or stops, which would drop it).
        let clip = dictation.listening ? dictation.takeRecording() : nil
        // In the conversation the microphone stays open for what comes next.
        if conversation, dictation.listening, dictation.duplex { dictation.fresh() } else { dictation.cancel() }
        spokenBase = ""
        model.silence()
        let text = word.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        word = ""
        // Said while it still works on your last question: goes with it.
        let addTo = model.addingTo
        Task {
            note = await model.talk(text, addTo: addTo, recording: clip)
            if note != nil { word = text }
        }
    }

    private func keepAsNote() {
        dictation.cancel()
        let text = word
        word = ""
        Task {
            note = await model.say(text)
            if note != nil { word = text }
        }
    }
}

// MARK: - the full journal

/// Every line, newest first; quiet stretches folded into one grey line.
struct ResidentJournalSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppModel.self) private var app
    let model: ResidentModel
    var filter: JournalFilter = .all
    @State private var expanded: Set<Int> = []

    private var rows: [JournalRow] {
        var out: [JournalRow] = []
        for e in model.entries.reversed() where filter.keeps(e) {
            if filter == .looks {
                out.append(.entry(e))
            } else if e.quiet, case .quiet(let newest, _, let n)? = out.last {
                out[out.count - 1] = .quiet(first: newest, last: e, count: n + 1)
            } else if e.quiet {
                out.append(.quiet(first: e, last: e, count: 1))
            } else {
                out.append(.entry(e))
            }
        }
        return out
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(rows) { row in
                        switch row {
                        case .quiet(let newest, let oldest, let n):
                            HStack(alignment: .firstTextBaseline, spacing: 10) {
                                Text(ResidentPanel.clock(newest.ts)).font(Face.mono(10.5)).foregroundStyle(Palette.meta)
                                    .frame(width: 44, alignment: .leading)
                                Text(n == 1 ? (newest.text ?? "nichts zu tun") : "\(n)× nichts zu tun, seit \(ResidentPanel.clock(oldest.ts))")
                                    .font(Face.ui(12.5)).foregroundStyle(Palette.meta)
                            }
                            .padding(.vertical, 7)
                        case .entry(let e):
                            entryRow(e)
                        }
                        Hairline()
                    }
                }
                .padding(18)
            }
            .background(Room())
            .navigationTitle(filter.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
        }
    }

    private func entryRow(_ e: ResidentEntry) -> some View {
        let open = expanded.contains(e.seq)
        return VStack(alignment: .leading, spacing: 5) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(ResidentPanel.clock(e.ts)).font(Face.mono(10.5)).foregroundStyle(Palette.meta)
                    .frame(width: 44, alignment: .leading)
                Text(Self.word(e)).font(Face.mono(9.5)).tracking(0.8).foregroundStyle(Self.tint(e))
                Text(e.text ?? "").font(Face.ui(13.5)).foregroundStyle(Palette.text)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            if open, let d = e.detail, !d.isEmpty {
                Text(d).font(Face.ui(12.5)).foregroundStyle(Palette.meta).padding(.leading, 54)
            }
            if let key = e.sessionKey, e.kind == "auftrag" || e.kind == "ergebnis" {
                Button {
                    dismiss()
                    app.open(session: key, machine: model.machine?.name)
                } label: {
                    Text("In der Sitzung ansehen →").font(Face.ui(12)).foregroundStyle(Palette.brass)
                }
                .buttonStyle(.plain)
                .padding(.leading, 54)
            }
        }
        .padding(.vertical, 8)
        .contentShape(Rectangle())
        .onTapGesture {
            guard e.detail != nil else { return }
            if open { expanded.remove(e.seq) } else { expanded.insert(e.seq) }
        }
    }

    static func word(_ e: ResidentEntry) -> String {
        switch e.kind {
        case "fund": return "FUND"
        case "auftrag": return "AUFTRAG"
        case "ergebnis": return "ERGEBNIS"
        case "pruefung": return e.ok == false ? "PRÜFUNG ✗" : "PRÜFUNG ✓"
        case "antrag": return "ANTRAG"
        case "entscheidung": return "ENTSCHIEDEN"
        case "zuruf": return "ZURUF"
        case "stop": return "STOP"
        case "weiter": return "WEITER"
        case "pause": return "ZURÜCKGEHALTEN"
        case "fehler": return "FEHLER"
        default: return e.kind.uppercased()
        }
    }

    static func tint(_ e: ResidentEntry) -> Color {
        switch e.kind {
        case "fehler", "stop": return Palette.clayText
        case "pruefung": return e.ok == false ? Palette.clayText : Palette.sage
        case "antrag", "fund", "pause": return Palette.brass
        default: return Palette.meta
        }
    }
}

private enum JournalRow: Identifiable {
    case entry(ResidentEntry)
    /// Newest and oldest of a quiet stretch, and how many.
    case quiet(first: ResidentEntry, last: ResidentEntry, count: Int)

    var id: Int {
        switch self {
        case .entry(let e): return e.seq
        case .quiet(let first, _, _): return -first.seq
        }
    }
}

// MARK: - requests and workspace

/// A limit the resident wants moved - it asks, you decide.
struct RequestCard: View {
    let request: ResidentRequest
    let decide: (Bool) -> Void

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 16, style: .continuous)
        VStack(alignment: .leading, spacing: 8) {
            Eyebrow("Antrag – wartet auf dich", color: Palette.brass)
            Text(request.title ?? "").font(Face.ui(15)).foregroundStyle(Palette.text)
            if let r = request.reason, !r.isEmpty {
                Text(r).font(Face.ui(13)).foregroundStyle(Palette.meta)
            }
            HStack(spacing: 10) {
                Spacer()
                Button("Ablehnen") { decide(false) }
                    .font(Face.ui(13)).foregroundStyle(Palette.clayText)
                    .accessibilityIdentifier("antrag-ablehnen")
                Button("Genehmigen") { decide(true) }
                    .font(Face.ui(13, .medium)).foregroundStyle(Palette.brass)
                    .accessibilityIdentifier("antrag-genehmigen")
            }
            .buttonStyle(.plain)
            .padding(.top, 2)
        }
        .padding(14)
        .inked(shape, Color(hex: 0xEFECE5, opacity: 0.035))
        .gilt(shape, strength: 0.6)
    }
}

/// The workspace: what it keeps on disk - read it, and write into the
/// plain notes yourself ("the key is in the hall").
struct ResidentFilesSheet: View {
    @Environment(\.dismiss) private var dismiss
    let model: ResidentModel
    @State private var files: [ResidentFile] = []

    var body: some View {
        NavigationStack {
            List(files) { f in
                NavigationLink(value: f) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(f.path).font(Face.mono(12.5)).foregroundStyle(Palette.text)
                        Text("\(ByteCountFormatter.string(fromByteCount: Int64(f.size), countStyle: .file)) · \(ResidentPanel.clock(f.mtime))\(f.editable ? " · bearbeitbar" : "")")
                            .font(Face.mono(9.5)).foregroundStyle(Palette.meta)
                    }
                }
                .listRowBackground(Color.clear)
            }
            .scrollContentBackground(.hidden)
            .background(Room())
            .navigationTitle("Arbeitsraum")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: ResidentFile.self) { f in ResidentFileView(model: model, file: f) }
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
            .task { files = await model.files() }
        }
    }
}

struct ResidentFileView: View {
    let model: ResidentModel
    let file: ResidentFile
    @State private var text = ""
    @State private var loaded = false
    @State private var saved = ""
    @State private var note: String?

    var body: some View {
        Group {
            if file.editable {
                TextEditor(text: $text)
                    .font(Face.mono(12.5))
                    .foregroundStyle(Palette.text)
                    .scrollContentBackground(.hidden)
                    .padding(.horizontal, 12)
            } else {
                ScrollView {
                    Text(text).font(Face.mono(11.5)).foregroundStyle(Palette.text).textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(16)
                }
            }
        }
        .background(Room())
        .navigationTitle(file.path)
        .navigationBarTitleDisplayMode(.inline)
        .safeAreaInset(edge: .bottom) {
            if let note { Text(note).font(Face.mono(10)).foregroundStyle(Palette.clayText).padding(8) }
        }
        .toolbar {
            if file.editable {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Sichern") {
                        Task {
                            note = await model.write(file.path, text: text)
                            if note == nil { saved = text }
                        }
                    }
                    .disabled(!loaded || text == saved)
                }
            }
        }
        .task {
            if let t = await model.read(file.path) {
                text = t
            } else if file.editable {
                // Not written yet - the core knowledge starts empty.
                text = ""
                note = "Noch leer – was hier steht, weiß er immer."
            } else {
                text = "Konnte nicht gelesen werden."
            }
            saved = text
            loaded = true
        }
    }
}

// MARK: - memory

/// What it keeps in mind, at a glance: how much, and the newest facts. Tap
/// to search, correct, forget.
struct MemoryGlance: View {
    let model: ResidentModel
    @State private var seen: ResidentMemoryBody?
    @State private var problem: String?
    @State private var open = false

    var body: some View {
        Button { open = true } label: {
            VStack(alignment: .leading, spacing: 12) {
                if let m = seen, m.present {
                    if !m.counts.isEmpty {
                        Text(Self.counts(m.counts)).font(Face.mono(9.5)).tracking(0.6).foregroundStyle(Palette.meta)
                    }
                    if m.memories.isEmpty {
                        Text("Noch keine Fakten – sag ihm „Merk dir …“.").font(Face.ui(13)).foregroundStyle(Palette.meta)
                    }
                    ForEach(m.memories) { f in MemoryLine(memory: f) }
                    if !m.pending.isEmpty {
                        Text(m.pending.count == 1 ? "Eine Änderung wartet, bis er sie übernimmt."
                             : "\(m.pending.count) Änderungen warten, bis er sie übernimmt.")
                            .font(Face.ui(12.5)).foregroundStyle(Palette.brass)
                    }
                } else if let m = seen, !m.present {
                    Text("Noch kein Gedächtnis – es entsteht gerade auf dem PC. Bis dahin weiß er nach einem Neustart nichts mehr.")
                        .font(Face.ui(13)).foregroundStyle(Palette.meta)
                } else {
                    Text(problem ?? "Wird geladen …").font(Face.ui(13)).foregroundStyle(Palette.meta)
                }
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass").font(.system(size: 12, weight: .light)).foregroundStyle(Palette.brass)
                    Text("Durchsuchen, korrigieren, vergessen").font(Face.ui(14.5)).foregroundStyle(Palette.text)
                }
                .padding(.top, 2)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("gedaechtnis")
        .sheet(isPresented: $open, onDismiss: { Task { await load() } }) { ResidentMemorySheet(model: model) }
        .task {
            while !Task.isCancelled {
                await load()
                try? await Task.sleep(for: .seconds(30))
            }
        }
    }

    private func load() async {
        let (b, err) = await model.memories("", art: "fakt", limit: 3)
        if let b { seen = b }
        problem = err
    }

    static let order = ["fakt", "gespraech", "ereignis", "tagesrueckblick", "datei"]

    static func counts(_ c: [String: Int]) -> String {
        let words = ["fakt": ("Fakt", "Fakten"), "gespraech": ("Gespräch", "Gespräche"),
                     "ereignis": ("Ereignis", "Ereignisse"), "tagesrueckblick": ("Rückblick", "Rückblicke"),
                     "datei": ("Datei", "Dateien")]
        let keys = order.filter { c[$0] != nil } + c.keys.filter { !order.contains($0) }.sorted()
        return keys.map { k in
            let n = c[k] ?? 0
            let w = words[k].map { n == 1 ? $0.0 : $0.1 } ?? k
            return "\(n) \(w)".uppercased()
        }.joined(separator: " · ")
    }
}

struct MemoryLine: View {
    let memory: ResidentMemory
    var lines = 3

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                Text(memory.kindWord).font(Face.mono(8.5)).tracking(0.8).foregroundStyle(Self.tint(memory.art))
                Text(ResidentPanel.clock(memory.ts)).font(Face.mono(9)).foregroundStyle(Palette.faint)
            }
            Text(memory.text).font(Face.ui(13.5)).foregroundStyle(Palette.text).lineLimit(lines)
                .strikethrough(memory.ersetztDurch != nil, color: Palette.meta)
        }
    }

    static func tint(_ art: String) -> Color {
        switch art {
        case "fakt": return Palette.brass
        case "gespraech", "datei": return Palette.sage
        default: return Palette.meta
        }
    }
}

/// Everything it remembers: search, by kind, and the core knowledge you
/// write yourself.
struct ResidentMemorySheet: View {
    @Environment(\.dismiss) private var dismiss
    let model: ResidentModel
    @State private var query = ""
    @State private var art = ""
    @State private var found = ResidentMemoryBody()
    @State private var loaded = false
    @State private var problem: String?

    private static let kinds = [("", "Alle"), ("fakt", "Fakten"), ("gespraech", "Gespräche"),
                                ("ereignis", "Ereignisse"), ("tagesrueckblick", "Rückblicke"), ("datei", "Dateien")]

    var body: some View {
        NavigationStack {
            List {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(Self.kinds, id: \.0) { k in
                            let on = art == k.0
                            Button { art = k.0 } label: {
                                Text(k.1 + (k.0.isEmpty ? "" : found.counts[k.0].map { " \($0)" } ?? ""))
                                    .font(Face.ui(12.5)).foregroundStyle(on ? Palette.text : Palette.meta)
                                    .padding(.horizontal, 11).padding(.vertical, 6)
                                    .overlay(Capsule().stroke(on ? Palette.brass : Palette.hair, lineWidth: 1))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .listRowBackground(Color.clear)
                .listRowSeparator(.hidden)
                if !found.pending.isEmpty {
                    Section {
                        ForEach(found.pending) { p in
                            Text(p.aktion == "vergessen" ? "Vergessen – wartet, bis er es übernimmt"
                                 : "Korrektur – „\(p.text ?? "")“ wartet")
                                .font(Face.ui(12.5)).foregroundStyle(Palette.brass)
                        }
                    }
                    .listRowBackground(Color.clear)
                }
                if let problem {
                    Text(problem).font(Face.ui(13)).foregroundStyle(Palette.clayText).listRowBackground(Color.clear)
                } else if loaded && !found.present {
                    Text("Noch kein Gedächtnis – es entsteht gerade auf dem PC.")
                        .font(Face.ui(13)).foregroundStyle(Palette.meta).listRowBackground(Color.clear)
                } else if loaded && found.memories.isEmpty {
                    Text(query.isEmpty ? "Hier ist noch nichts." : "Dazu erinnert er sich an nichts.")
                        .font(Face.ui(13)).foregroundStyle(Palette.meta).listRowBackground(Color.clear)
                }
                ForEach(found.memories) { m in
                    NavigationLink(value: m) { MemoryLine(memory: m, lines: 4) }
                        .listRowBackground(Color.clear)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Room())
            .searchable(text: $query, prompt: "Woran erinnert er sich?")
            .navigationTitle("Gedächtnis")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: ResidentMemory.self) { m in ResidentMemoryView(model: model, memory: m) }
            .navigationDestination(for: ResidentFile.self) { f in ResidentFileView(model: model, file: f) }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    NavigationLink(value: ResidentFile(path: "ERINNERUNG.md", size: 0, mtime: 0, editable: true)) {
                        Text("Kernwissen")
                    }
                    .accessibilityIdentifier("kernwissen")
                }
                ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } }
            }
            .task(id: query + "|" + art) {
                if !query.isEmpty { try? await Task.sleep(for: .milliseconds(300)) }
                guard !Task.isCancelled else { return }
                await load()
            }
        }
    }

    private func load() async {
        let (b, err) = await model.memories(query, art: art, limit: 150)
        if let b { found = b }
        problem = err
        loaded = true
    }
}

/// One memory: what replaced it, and correcting or forgetting it - as a
/// file the resident takes in, like everything the app puts there.
struct ResidentMemoryView: View {
    let model: ResidentModel
    let memory: ResidentMemory
    @State private var chain: [ResidentMemory] = []
    @State private var fixing = false
    @State private var fix = ""
    @State private var asking = false
    @State private var note: String?
    @State private var sent: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text(memory.kindWord).font(Face.mono(9)).tracking(0.8).foregroundStyle(MemoryLine.tint(memory.art))
                    Spacer()
                    Text(ResidentPanel.clock(memory.ts)).font(Face.mono(9.5)).foregroundStyle(Palette.meta)
                }
                Text(memory.text).font(Face.ui(16.5)).foregroundStyle(Palette.text).textSelection(.enabled)
                    .strikethrough(memory.ersetztDurch != nil, color: Palette.meta)
                let origin = [memory.quelle.map { "aus \($0)" },
                              memory.wichtig.map { "Gewicht \(String(format: "%.1f", $0))" }].compactMap { $0 }
                if !origin.isEmpty {
                    Text(origin.joined(separator: " · ")).font(Face.mono(10)).foregroundStyle(Palette.meta)
                }
                if chain.count > 1 {
                    Eyebrow("Ersetzt durch")
                    ForEach(chain.dropFirst()) { m in MemoryLine(memory: m, lines: 6) }
                }
                if let sent {
                    Text(sent).font(Face.ui(13.5)).foregroundStyle(Palette.brass)
                } else if fixing {
                    Eyebrow("Was stimmt stattdessen?")
                    TextEditor(text: $fix)
                        .font(Face.ui(14.5)).foregroundStyle(Palette.text)
                        .scrollContentBackground(.hidden)
                        .frame(minHeight: 100)
                        .padding(8)
                        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(Palette.hair, lineWidth: 1))
                    HStack(spacing: 22) {
                        Spacer()
                        Button("Abbrechen") { fixing = false }.foregroundStyle(Palette.meta)
                        Button("Korrektur senden") { send("korrigieren", fix) }
                            .font(Face.ui(14.5, .medium)).foregroundStyle(Palette.brass)
                            .disabled(fix.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || fix == memory.text)
                    }
                    .buttonStyle(.plain)
                } else if memory.ersetztDurch == nil {
                    HStack(spacing: 26) {
                        Button { fix = memory.text; fixing = true } label: {
                            Label("Korrigieren", systemImage: "pencil").font(Face.ui(14.5)).foregroundStyle(Palette.text)
                        }
                        .accessibilityIdentifier("erinnerung-korrigieren")
                        Button { asking = true } label: {
                            Label("Vergessen", systemImage: "eye.slash").font(Face.ui(14.5)).foregroundStyle(Palette.clayText)
                        }
                        .accessibilityIdentifier("erinnerung-vergessen")
                        Spacer()
                    }
                    .buttonStyle(.plain)
                    .padding(.top, 6)
                }
                if let note { Text(note).font(Face.mono(10)).foregroundStyle(Palette.clayText) }
            }
            .padding(20)
        }
        .background(Room())
        .navigationTitle("Erinnerung")
        .navigationBarTitleDisplayMode(.inline)
        .confirmationDialog("Vergessen?", isPresented: $asking, titleVisibility: .visible) {
            Button("Vergessen", role: .destructive) { send("vergessen", "") }
        } message: {
            Text("Er übernimmt es beim nächsten Blick und weiß es danach nicht mehr.")
        }
        .task { chain = await model.memoryChain(memory.id) }
    }

    private func send(_ aktion: String, _ text: String) {
        Task {
            note = await model.changeMemory(memory.id, aktion: aktion, text: text)
            if note == nil {
                fixing = false
                sent = aktion == "vergessen" ? "Wird vergessen, sobald er es übernimmt."
                    : "Korrektur liegt bei ihm – er übernimmt sie beim nächsten Blick."
            }
        }
    }
}

// MARK: - who it is

/// Who it is in its own words, and what it sees - the page shows what it
/// wrote about itself, not what we say about it. And a way to show it
/// something: a photo or a file goes into its eingang folder.
struct SelfGlance: View {
    let model: ResidentModel
    @State private var me: ResidentSelf?
    @State private var file: ResidentFile?
    @State private var photo: PhotosPickerItem?
    @State private var importing = false
    @State private var note: String?
    @State private var sending = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let me, me.name != nil || me.about != nil {
                Button { file = ResidentFile(path: "ICH.md", size: 0, mtime: 0, editable: true) } label: {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(me.name ?? "Noch ohne Namen").font(Face.ui(19)).foregroundStyle(Palette.text)
                        if let about = me.about {
                            Text(about).font(Face.ui(13)).foregroundStyle(Palette.meta).lineLimit(3)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("bewohner-ich")
            } else {
                Text("Noch hat er sich nicht beschrieben – Namen und Charakter sucht er sich selbst.")
                    .font(Face.ui(13)).foregroundStyle(Palette.meta)
            }
            if let wishes = me?.wishes, !wishes.isEmpty {
                Button { file = ResidentFile(path: "WUENSCHE.md", size: 0, mtime: 0, editable: true) } label: {
                    VStack(alignment: .leading, spacing: 7) {
                        Eyebrow("Er wünscht sich")
                        ForEach(wishes.prefix(3), id: \.self) { w in
                            HStack(alignment: .firstTextBaseline, spacing: 9) {
                                Circle().fill(Palette.brass).frame(width: 4, height: 4).alignmentGuide(.firstTextBaseline) { $0[.bottom] + 1 }
                                Text(w).font(Face.ui(13.5)).foregroundStyle(Palette.text).lineLimit(2)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
            let chips = Self.chips(me)
            if !chips.isEmpty {
                Flow(spacing: 8, lineSpacing: 8) {
                    ForEach(chips, id: \.self) { t in
                        Text(t).font(Face.ui(12.5)).foregroundStyle(Palette.text)
                            .padding(.horizontal, 11).padding(.vertical, 7)
                            .overlay(Capsule().stroke(Palette.hair, lineWidth: 1))
                    }
                }
            }
            HStack(spacing: 24) {
                PhotosPicker(selection: $photo, matching: .images) {
                    Label("Foto zeigen", systemImage: "photo").font(Face.ui(14.5)).foregroundStyle(Palette.text)
                }
                .accessibilityIdentifier("bewohner-foto")
                Button { importing = true } label: {
                    Label("Datei zeigen", systemImage: "doc").font(Face.ui(14.5)).foregroundStyle(Palette.text)
                }
                .accessibilityIdentifier("bewohner-datei")
                Spacer()
            }
            .buttonStyle(.plain)
            .disabled(sending)
            if let note {
                Text(note).font(Face.mono(10)).foregroundStyle(note.hasPrefix("Liegt") ? Palette.sage : Palette.clayText)
            }
        }
        .sheet(item: $file, onDismiss: { Task { me = await model.selfView() ?? me } }) { f in
            NavigationStack { ResidentFileView(model: model, file: f) }
        }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.item]) { result in
            guard case .success(let url) = result else { return }
            Task { await showFile(url) }
        }
        .onChange(of: photo) { _, item in
            guard let item else { return }
            Task { await showPhoto(item) }
        }
        .task {
            while !Task.isCancelled {
                if let v = await model.selfView() { me = v }
                try? await Task.sleep(for: .seconds(30))
            }
        }
    }

    static func chips(_ me: ResidentSelf?) -> [String] {
        var out: [String] = []
        if let l = me?.lage {
            if let p = l.tagesphase, !p.isEmpty { out.append(p) }
            if let n = l.netz?.count { out.append(n == 1 ? "1 Gerät im Netz" : "\(n) Geräte im Netz") }
            if l.arbeitszeit == true { out.append("deine Arbeitszeit") }
        }
        if let t = me?.werkzeuge.count, t > 0 { out.append(t == 1 ? "1 eigenes Werkzeug" : "\(t) eigene Werkzeuge") }
        if let f = me?.faehigkeiten.count, f > 0 { out.append("\(f) Fähigkeiten") }
        if let e = me?.eingang.count, e > 0 { out.append("\(e) im Eingang") }
        return out
    }

    private func showPhoto(_ item: PhotosPickerItem) async {
        photo = nil
        guard let data = try? await item.loadTransferable(type: Data.self) else {
            note = "Foto nicht lesbar"
            return
        }
        // JPEG, whatever the phone keeps: the PC's image models read that.
        let jpeg = UIImage(data: data)?.jpegData(compressionQuality: 0.85) ?? data
        await send("foto-" + Self.stamp() + ".jpg", jpeg)
    }

    private func showFile(_ url: URL) async {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        guard let data = try? Data(contentsOf: url) else {
            note = "Datei nicht lesbar"
            return
        }
        await send(url.lastPathComponent, data)
    }

    private func send(_ name: String, _ data: Data) async {
        guard data.count <= 20_000_000 else {
            note = "Zu groß – höchstens 20 MB"
            return
        }
        sending = true
        let err = await model.show(name: name, data: data)
        sending = false
        note = err ?? "Liegt in seinem Eingang: \(name)"
        if let v = await model.selfView() { me = v }
    }

    static func stamp() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd-HHmmss"
        return f.string(from: Date())
    }
}
