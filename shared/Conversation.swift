import SwiftUI
#if os(iOS)
import UIKit
#endif

// The conversation as both apps draw it - the phone and the Mac show the
// same turns, tool lines, diffs and approval cards, so a fix lands in both.
// What only the phone has (its screen, the input with the photo picker,
// the sheets) stays in the iPhone app's SessionView.

/// Whether the work runs and for how long - or that the Mac cannot be
/// reached. Stands first in the phone's facts, first in the Mac's line.
struct StatusItem: View {
    let model: SessionModel

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { timeline in
            HStack(spacing: 8) {
                if !model.connected {
                    // The link is down: nothing here is current, and what you
                    // send waits on the phone until it is back.
                    Circle().fill(Palette.clay).frame(width: 5, height: 5)
                    // Den Rechner benennen. Eine Sitzung kann auf dem PC
                    // laufen, und "Mac nicht erreichbar" schickt einen dann
                    // zum falschen Gerät.
                    Text("\(model.app?.machine?.name ?? "Brücke") nicht erreichbar")
                        .foregroundStyle(Palette.clayText)
                } else {
                    if model.busy {
                        Bud()
                    } else {
                        Circle().fill(model.ended ? Palette.faint : Palette.sage.opacity(0.85)).frame(width: 5, height: 5)
                    }
                    Text(status(at: timeline.date))
                }
            }
            .font(Face.mono(10.5))
            .foregroundStyle(Palette.meta)
            .lineLimit(1)
            .fixedSize()
        }
    }

    private func status(at now: Date) -> String {
        if model.ended { return "beendet" }
        guard model.busy else { return "bereit" }
        guard let since = model.busySince else { return "arbeitet" }
        return "läuft seit \(Fmt.clock(now.timeIntervalSince(since)))"
    }
}

/// Interrupts the running turn - a terminal session with Ctrl+C in its tab,
/// if iris can reach it. "anhalten" sounded like a pause it is not: the turn
/// ends where it stands.
struct StopButton: View {
    let model: SessionModel

    var body: some View {
        if model.busy && (!model.isTerminal || model.info?.typable == true) {
            Button("unterbrechen") { Task { await model.interrupt() } }
                .font(Face.mono(10.5))
                .foregroundStyle(Palette.clayText)
                .buttonStyle(.plain)
                .fixedSize()
        }
    }
}

/// Ctrl+B in the tab: what runs keeps running, but the turn goes on without
/// waiting for it. Only for a terminal session iris can type into, and only
/// while a shell command is actually running - offered next to a thought,
/// the key would do nothing and the button would have lied.
struct BackgroundButton: View {
    let model: SessionModel
    @State private var geschickt = false

    var body: some View {
        if model.canBackground && model.isTerminal && model.info?.typable == true {
            Button {
                Trace.write("Hintergrund gedrückt [\(model.key.prefix(10))] "
                            + "läuft=\(model.runningTool ?? "nichts")")
                geschickt = true
                Task {
                    await model.press("background")
                    try? await Task.sleep(for: .seconds(1.6))
                    geschickt = false
                }
            } label: {
                Text(geschickt ? "geschickt" : "in den Hintergrund")
                    .font(Face.mono(10.5))
                    .foregroundStyle(geschickt ? Palette.sage : Palette.meta)
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    .background(Capsule().fill(Color(hex: 0xEFECE5, opacity: 0.06)))
                    .contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .fixedSize()
            .accessibilityIdentifier("hintergrund-knopf")
        }
    }
}

/// The state of the work in one line: whether it runs, for how long, and
/// the button to stop it. What Claude is doing right now stands at the
/// bottom, in WorkingRow.
struct ActivityLine: View {
    let model: SessionModel

    var body: some View {
        HStack(spacing: 14) {
            StatusItem(model: model)
            Spacer(minLength: 8)
            StopButton(model: model)
        }
    }
}

/// The terminal's spinner line, where the terminal has it: right under the
/// work in progress, while Claude works - its word for the turn
/// ("Deciphering…") and what goes on, a tool or thinking. Messages that
/// wait stand below it, greyed, until Claude takes them.
struct WorkingRow: View {
    let model: SessionModel

    var body: some View {
        HStack(spacing: 9) {
            // Turned in steps, ten a second - like the terminal's spinner,
            // and a tenth of the work of an endless animation.
            TimelineView(.animation(minimumInterval: 1 / 10)) { t in
                ClaudeStar()
                    .fill(Palette.brass)
                    .frame(width: 12, height: 12)
                    .rotationEffect(.degrees(t.date.timeIntervalSinceReferenceDate
                        .truncatingRemainder(dividingBy: 4) / 4 * 360))
            }
            Text(model.verb ?? "Arbeitet…")
                .font(Face.ui(13))
                .foregroundStyle(Palette.brass)
                .lineLimit(1)
            if let doing = model.doing {
                Text("·").opacity(0.45)
                Text(doing).font(Face.mono(10.5)).foregroundStyle(Palette.meta).lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .padding(.leading, 1)
        // .combine folds the children into one element and the button inside
        // stops taking clicks. The row holds something to press now.
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("arbeitszeile")
    }
}

/// The numbers of this session, each with its word: how full the context
/// is, what changed in the tree, what still runs
/// in the background, how the services are. They wrap instead of being cut.
struct FactsRow: View {
    @Environment(AppModel.self) private var app
    let model: SessionModel
    let services: ServiceSummary?
    /// How full the window is.
    var context = true
    /// The plan's five-hour window. The Mac keeps it in its sidebar, where it
    /// stands for the machine rather than for one session.
    var quota = true
    /// Lines added and removed since the session started.
    var git = false
    /// Pass a binding and the mode stands in this line and opens its list -
    /// it wraps with the numbers instead of pinning them to one line.
    var showModes: Binding<Bool>? = nil
    /// The state first, in the same wrapping line - on the phone it shares
    /// its line with what opens (background, pages).
    var status = false
    /// The numbers: context, the plan's limit, changed lines, services.
    var counts = true
    /// What opens a list: background tasks, pages.
    var toggles = true
    @Binding var showBackground: Bool
    @Binding var showPages: Bool

    var body: some View {
        // Wrapping, never scrolling: every number stays in sight.
        Flow(spacing: 16, lineSpacing: 8) { items }
    }

    /// A terminal session steps through what Shift+Tab offers at the Mac.
    private var modes: [Mode] {
        guard model.isTerminal else { return app.modes }
        return ["default", "acceptEdits", "plan", "auto"].compactMap { id in app.modes.first { $0.id == id } }
    }

    @ViewBuilder private var items: some View {
        if status {
            StatusItem(model: model)
        }
        if let showModes, !model.mode.isEmpty, !model.isTerminal || model.info?.typable == true {
            ModeChip(label: model.mode, plan: model.mode == "plan") { showModes.wrappedValue = true }
                .popover(isPresented: showModes, arrowEdge: .bottom) {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(modes) { m in
                            Button {
                                Task { await model.setMode(m.id); showModes.wrappedValue = false }
                            } label: {
                                HStack {
                                    Tick(on: m.id == model.mode)
                                    Text(m.label).font(Face.ui(13))
                                    Spacer()
                                }
                                .padding(.vertical, 6).contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(14).frame(width: 220)
                }
        }
        if toggles {
            // Work that keeps running after its call returned - Ctrl+B,
            // run_in_background, subagents. Easy to forget, so it stands
            // here, and a tap lists it.
            if !model.background.isEmpty {
                opener(value: "\(model.background.count)", label: "im Hintergrund", tint: Palette.brass,
                       open: showBackground, id: "hintergrund") {
                    withAnimation(.easeOut(duration: 0.2)) { showBackground.toggle() }
                }
            }
            // The pages published here - design drafts, reports - a tap away
            // instead of buried in the conversation.
            if !model.artifacts.isEmpty {
                opener(value: "\(model.artifacts.count)", label: model.artifacts.count == 1 ? "Seite" : "Seiten",
                       tint: nil, open: showPages, id: "seiten") {
                    withAnimation(.easeOut(duration: 0.2)) { showPages.toggle() }
                }
            }
        }
        if counts {
            if context, let c = model.context {
                HStack(spacing: 8) {
                    Fact(value: "\(Int((c * 100).rounded())) %", label: "Kontext")
                    ContextLine(fraction: c)
                }
            }
            if git, let a = model.added, let r = model.removed, a + r > 0 {
                HStack(alignment: .firstTextBaseline, spacing: 5) {
                    Text("+\(a)").font(Face.display(17)).foregroundStyle(Palette.sage)
                    Text("−\(r)").font(Face.display(17)).foregroundStyle(Palette.clayText)
                    Text("Zeilen").font(Face.ui(11)).foregroundStyle(Palette.meta)
                }
                .fixedSize()
            }
            // The plan's five-hour window: run into its end unknowingly and
            // from afar the session just stops answering.
            if quota, let q = app.quota {
                if q.limited {
                    Fact(value: "Limit", label: "frei um \(Quota.clock(q.limitedUntil))", tint: Palette.clayText)
                } else if let f = q.fiveHourNow {
                    Fact(value: "\(Int((f * 100).rounded())) %", label: "5-h-Limit",
                         tint: f >= 0.8 ? Palette.clayText : nil)
                }
            }
            if let s = services, s.total > 0 {
                Button { app.path.append(.services) } label: {
                    Fact(value: "\(s.healthy)/\(s.total)", label: "Dienste ok",
                         tint: s.healthy < s.total ? Palette.clayText : nil)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
    }

    /// A number that opens its list, with the chevron that says so.
    private func opener(value: String, label: String, tint: Color?, open: Bool, id: String,
                        action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(alignment: .firstTextBaseline, spacing: 5) {
                Fact(value: value, label: label, tint: tint)
                Image(systemName: "chevron.down")
                    .font(.system(size: 8, weight: .semibold))
                    .foregroundStyle(Palette.meta)
                    .rotationEffect(.degrees(open ? 180 : 0))
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(id)
    }
}

/// A number and what it counts.
struct Fact: View {
    let value: String
    let label: String
    var tint: Color? = nil

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 5) {
            Text(value).font(Face.display(17)).foregroundStyle(tint ?? Palette.text)
            Text(label).font(Face.ui(11)).foregroundStyle(Palette.meta)
        }
        .fixedSize()
    }
}

/// Parts side by side, wrapping into the next line where the width ends.
struct Flow: Layout {
    var spacing: CGFloat = 16
    var lineSpacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let lines = arrange(subviews, width: proposal.width ?? .infinity)
        let height = lines.map(\.height).reduce(0, +) + lineSpacing * CGFloat(max(0, lines.count - 1))
        return CGSize(width: proposal.width ?? (lines.map(\.width).max() ?? 0), height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for line in arrange(subviews, width: bounds.width) {
            var x = bounds.minX
            for i in line.items {
                let size = subviews[i].sizeThatFits(.unspecified)
                subviews[i].place(at: CGPoint(x: x, y: y + (line.height - size.height) / 2), proposal: .unspecified)
                x += size.width + spacing
            }
            y += line.height + lineSpacing
        }
    }

    private func arrange(_ subviews: Subviews, width: CGFloat) -> [(items: [Int], width: CGFloat, height: CGFloat)] {
        var lines: [(items: [Int], width: CGFloat, height: CGFloat)] = []
        for i in subviews.indices {
            let size = subviews[i].sizeThatFits(.unspecified)
            if let last = lines.last, !last.items.isEmpty, last.width + spacing + size.width <= width {
                lines[lines.count - 1].items.append(i)
                lines[lines.count - 1].width += spacing + size.width
                lines[lines.count - 1].height = max(last.height, size.height)
            } else {
                lines.append(([i], size.width, size.height))
            }
        }
        return lines
    }
}

/// What runs in the background, one line each: what it is, and the command.
struct BackgroundList: View {
    let tasks: [BackgroundTask]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(tasks) { task in
                HStack(alignment: .firstTextBaseline, spacing: 9) {
                    Bud(size: 5).alignmentGuide(.firstTextBaseline) { d in d[.bottom] }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(task.description.isEmpty ? (task.type == "agent" ? "Agent" : "Befehl") : task.description)
                            .font(Face.ui(12.5))
                            .foregroundStyle(Palette.text)
                            .lineLimit(1)
                        if !task.command.isEmpty {
                            Text(task.command)
                                .font(Face.mono(10.5))
                                .foregroundStyle(Palette.meta)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        }
                    }
                    Spacer(minLength: 6)
                    if let since = task.since {
                        TimelineView(.periodic(from: .now, by: 1)) { t in
                            Text(Fmt.clock(t.date.timeIntervalSince1970 - since))
                        }
                        .font(Face.mono(10))
                        .foregroundStyle(Palette.faint)
                    }
                }
                .padding(.vertical, 5)
            }
        }
        .padding(.leading, 13)
        .overlay(alignment: .leading) { Rectangle().fill(Palette.brass.opacity(0.25)).frame(width: 1) }
    }
}

/// The pages the session published, newest first; a tap opens one.
struct PagesList: View {
    let pages: [ArtifactLink]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(pages) { page in
                if let url = URL(string: page.url) {
                    Link(destination: url) {
                        HStack(alignment: .firstTextBaseline, spacing: 9) {
                            Text(page.icon.isEmpty ? "◇" : page.icon).font(.system(size: 12))
                            Text(page.title)
                                .font(Face.ui(12.5))
                                .foregroundStyle(Palette.text)
                                .lineLimit(1)
                            Spacer(minLength: 6)
                            Text(Fmt.age(page.ts)).font(Face.mono(10)).foregroundStyle(Palette.faint)
                            Image(systemName: "arrow.up.right")
                                .font(.system(size: 8, weight: .semibold))
                                .foregroundStyle(Palette.meta)
                        }
                        .padding(.vertical, 6)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.leading, 13)
        .overlay(alignment: .leading) { Rectangle().fill(Palette.brass.opacity(0.25)).frame(width: 1) }
    }
}

struct ModeChip: View {
    let label: String
    let plan: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 7) {
                Circle().fill(plan ? Palette.sage : Palette.brass).frame(width: 5, height: 5)
                Text(label).font(Face.ui(12.5)).foregroundStyle(Palette.text).lineLimit(1)
                Image(systemName: "chevron.down").font(.system(size: 8, weight: .semibold)).foregroundStyle(Palette.meta)
            }
            .padding(.vertical, 10)
            .padding(.horizontal, 14)
            .background(Capsule().fill(Palette.brass.opacity(0.1)))
            .overlay(Capsule().strokeBorder(
                LinearGradient(colors: [Palette.brass.opacity(0.22), .clear], startPoint: .top, endPoint: .center),
                lineWidth: 1))
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Modus \(label), umstellen")
    }
}

// MARK: - Conversation

struct TurnView: View {
    let turn: Turn

    var body: some View {
        switch turn.kind {
        case .user:
            // A brass edge down the side, not a symbol beside it: what you
            // said has to be findable while scrolling past tool lines, and
            // the ring alone read like any other line of text.
            HStack(alignment: .top, spacing: 14) {
                Capsule()
                    .fill(Palette.brass.opacity(0.55))
                    .frame(width: 2)
                    .frame(maxHeight: .infinity)
                VStack(alignment: .leading, spacing: 4) {
                    Text(turn.text)
                        .font(Face.ui(15))
                        .foregroundStyle(Palette.text)
                        .lineSpacing(4)
                        .textSelection(.enabled)
                    ForEach(turn.attachments, id: \.self) { name in
                        Label(name, systemImage: "paperclip")
                            .font(Face.mono(10.5))
                            .foregroundStyle(Palette.meta)
                            .labelStyle(.titleAndIcon)
                    }
                    if turn.pending {
                        // As the terminal shows it: typed, but Claude has
                        // not taken it yet - it finishes the running step first.
                        Text("wartet – Claude nimmt es nach dem laufenden Schritt")
                            .font(Face.mono(10))
                            .foregroundStyle(Palette.faint)
                    } else if turn.queued && !turn.taken {
                        Text(turn.deliveryLabel)
                            .font(Face.mono(10))
                            .foregroundStyle(Palette.faint)
                    }
                }
                .opacity(turn.pending ? 0.45 : turn.queued && !turn.delivered ? 0.62 : 1)
            }
            .fixedSize(horizontal: false, vertical: true)   // the edge is as tall as the text
            .padding(.top, 6)
        case .claude:
            HStack(alignment: .top, spacing: 14) {
                ClaudeStar().fill(Palette.brass.opacity(0.92)).frame(width: 15, height: 15).padding(.top, 5)
                VStack(alignment: .leading, spacing: 12) {
                    if !turn.text.isEmpty {
                        // Selecting works inside a paragraph but not across
                        // them - every block is a Text of its own. Taking a
                        // whole answer meant dragging it piece by piece.
                        Prose(text: turn.text).copyable(turn.text)
                    }
                    if !turn.tools.isEmpty { ToolLines(turn: turn) }
                }
            }
        case .summary:
            SummaryCard(text: turn.text)
        case .note:
            Text(turn.text)
                .font(Face.mono(10.5))
                .foregroundStyle(turn.tone == .bad ? Palette.clayText : Palette.faint)
                .frame(maxWidth: .infinity, alignment: turn.tone == .seam ? .center : .leading)
                .padding(.leading, turn.tone == .seam ? 0 : 21)
        }
    }

}

/// Not "a tool was used": tool, target, duration - enough to know what is
/// going on without a tap.
struct ToolLines: View {
    let turn: Turn
    @State private var showAll = false

    var body: some View {
        let shown = Self.visible(turn, showAll: showAll)
        VStack(alignment: .leading, spacing: 0) {
            if shown.hidden > 0 {
                Button { withAnimation(.easeOut(duration: 0.2)) { showAll = true } } label: {
                    Text("+ \(shown.hidden) weitere").font(Face.mono(10.5)).foregroundStyle(Palette.faint)
                        .padding(.vertical, 4.5)
                }
                .buttonStyle(.plain)
            }
            ForEach(shown.runs) { ToolLineView(run: $0) }
        }
        .padding(.leading, 13)
        .overlay(alignment: .leading) { Rectangle().fill(Palette.text.opacity(0.1)).frame(width: 1) }
    }

    /// A running turn shows every call. A finished one keeps the last three -
    /// and every failure, however far back: what failed is never folded away.
    /// Neither is a picture it read or a file it handed over: those are for
    /// you to see, not steps of its work.
    static func visible(_ t: Turn, showAll: Bool) -> (runs: [ToolRun], hidden: Int) {
        guard t.finished, !showAll, t.tools.count > 3 else { return (t.tools, 0) }
        let tail = Set(t.tools.suffix(3).map(\.id))
        let keep = t.tools.filter {
            tail.contains($0.id) || $0.state == .failed || !$0.files.isEmpty || $0.image != nil
        }
        return (keep, t.tools.count - keep.count)
    }
}

struct ToolLineView: View {
    let run: ToolRun
    @State private var open = false

    private var hasMore: Bool { !(run.change?.lines.isEmpty ?? true) || !(run.output?.isEmpty ?? true) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { withAnimation(.easeOut(duration: 0.2)) { open.toggle() } } label: {
                HStack(spacing: 9) {
                    marker
                    Text(run.tool)
                        .font(Face.ui(12.5))
                        .foregroundStyle(run.state == .failed ? Palette.clayText : Palette.text)
                    Text(run.target)
                        .font(Face.mono(10.5))
                        .foregroundStyle(Palette.meta)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Spacer(minLength: 6)
                    stat
                }
                .padding(.vertical, 4.5)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(!hasMore)
            // The reason sits right under the failure. Whoever has to unfold
            // it first cannot tell whether it mattered.
            if let path = run.image {
                SessionImage(path: path).padding(.leading, 14).padding(.vertical, 6)
            }
            ForEach(run.files, id: \.self) { path in
                SessionFileRow(path: path).padding(.leading, 14).padding(.vertical, 4)
            }
            if run.state == .failed, let reason = run.reason {
                Text(reason)
                    .font(Face.mono(10.5))
                    .foregroundStyle(Palette.clay)
                    .lineSpacing(3)
                    .padding(.leading, 14)
                    .padding(.bottom, 6)
            }
            if open {
                Group {
                    if let change = run.change, !change.lines.isEmpty {
                        DiffCard(tool: run.tool, target: run.target, change: change)
                    } else if let out = run.output, !out.isEmpty {
                        OutputBox(text: out)
                    }
                }
                .padding(.leading, 14)
                .padding(.vertical, 6)
                .transition(.opacity)
            }
        }
    }

    @ViewBuilder private var marker: some View {
        switch run.state {
        case .running: Bud(size: 5)
        case .ok: Circle().fill(Palette.sage.opacity(0.85)).frame(width: 5, height: 5)
        case .failed:
            Circle().fill(Palette.clay).frame(width: 5, height: 5).shadow(color: Palette.clay.opacity(0.7), radius: 3.5)
        }
    }

    @ViewBuilder private var stat: some View {
        if let ch = run.change {
            HStack(spacing: 5) {
                Text("+\(ch.added)").foregroundStyle(Palette.sage)
                Text("−\(ch.removed)").foregroundStyle(Palette.clay)
            }
            .font(Face.mono(10))
        } else if run.state == .running {
            TimelineView(.periodic(from: .now, by: 1)) { timeline in
                Text("läuft · \(Int(timeline.date.timeIntervalSince(run.started))) s")
            }
            .font(Face.mono(10))
            .foregroundStyle(Palette.faint)
        } else if let d = run.duration {
            Text(Fmt.duration(d)).font(Face.mono(10)).foregroundStyle(Palette.faint)
        }
    }
}

struct OutputBox: View {
    let text: String

    var body: some View {
        Text(String(text.prefix(1500)))
            .font(Face.mono(10.5))
            .foregroundStyle(Palette.soft)
            .lineSpacing(3)
            .lineLimit(14)
            .textSelection(.enabled)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Palette.codeGround))
    }
}

/// The change as a card: one corner stays sharp where it hangs off the
/// sentence, the other three are round. It grows out of the answer instead
/// of lying next to it.
struct DiffCard: View {
    let tool: String
    let target: String
    let change: Change

    var body: some View {
        let shape = UnevenRoundedRectangle(topLeadingRadius: 3, bottomLeadingRadius: 20,
                                           bottomTrailingRadius: 22, topTrailingRadius: 22, style: .continuous)
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                Text(tool).font(Face.ui(12.5, .regular)).foregroundStyle(Palette.text)
                Text(target).font(Face.mono(10.5)).foregroundStyle(Palette.meta).lineLimit(1).truncationMode(.middle)
                Spacer(minLength: 6)
                Text("+\(change.added)").font(Face.mono(10.5)).foregroundStyle(Palette.sage)
                Text("−\(change.removed)").font(Face.mono(10.5)).foregroundStyle(Palette.clay)
            }
            .padding(.horizontal, 15)
            .padding(.vertical, 11)
            DiffLines(change: change)
        }
        .inked(shape, LinearGradient(colors: [Color(hex: 0x332D26), Color(hex: 0x2A251F)],
                                     startPoint: .leading, endPoint: .trailing))
        .clipShape(shape)
        .gilt(shape)
        .shadow(color: .black.opacity(0.28), radius: 3, y: 2)
        .shadow(color: .black.opacity(0.35), radius: 17, y: 16)
    }
}

struct DiffLines: View {
    let change: Change

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(change.lines.enumerated()), id: \.offset) { _, line in
                let added = line.first == "+"
                let tint = added ? Palette.sage : Palette.clay
                Text(line.count > 1 ? line[1] : " ")
                    .font(Face.mono(10.5))
                    .foregroundStyle(added ? Palette.sageText : Palette.clayCode)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .padding(.leading, 14)
                    .padding(.trailing, 10)
                    .padding(.vertical, 2.5)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(tint.opacity(0.1))
                    .overlay(alignment: .leading) { Rectangle().fill(tint).frame(width: 2) }
            }
            let more = change.added + change.removed - change.lines.count
            if more > 0 {
                Text("… \(more) weitere Zeilen")
                    .font(Face.mono(10))
                    .foregroundStyle(Palette.faint)
                    .padding(.leading, 14)
                    .padding(.top, 4)
            }
        }
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Palette.codeGround)
    }
}

// MARK: - Waiting for you

/// The approval: the one surface that is warm. What is being approved is on
/// it - the command, or the lines of the change - not only where.
struct ApprovalCard: View {
    let decision: Decision
    let model: SessionModel

    var body: some View {
        let shape = UnevenRoundedRectangle(topLeadingRadius: 5, bottomLeadingRadius: 30,
                                           bottomTrailingRadius: 32, topTrailingRadius: 32, style: .continuous)
        VStack(alignment: .leading, spacing: 0) {
            Text("FREIGABE").font(Face.mono(9)).tracking(9 * 0.26).foregroundStyle(Palette.brassLabel)
            Text(decision.title)
                .font(Face.display(26))
                .foregroundStyle(Palette.text)
                .padding(.top, 7)
            if let meta = decision.meta {
                Text(meta)
                    .font(Face.mono(10.5))
                    .foregroundStyle(Palette.meta)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .padding(.top, 6)
            }
            if let command = decision.command {
                CommandBox(command: command).padding(.top, 12)
            }
            if let change = decision.change, !change.lines.isEmpty {
                DiffLines(change: change)
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .padding(.top, 12)
            }
            HStack(spacing: 10) {
                Button { Task { await model.answer(decision, allow: true) } } label: {
                    Text("Erlauben")
                        .font(Face.ui(13.5, .regular))
                        .tracking(0.27)
                        .foregroundStyle(Color(hex: 0xF7F3E9))
                        .padding(.vertical, 12)
                        .padding(.horizontal, 26)
                        .background(Capsule().fill(Palette.brass.opacity(0.18)))
                        .gilt(Capsule())
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                Button { Task { await model.answer(decision, allow: false) } } label: {
                    Text("Ablehnen")
                        .font(Face.ui(13))
                        .foregroundStyle(Palette.meta)
                        .padding(.vertical, 12)
                        .padding(.horizontal, 20)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
            .padding(.top, 17)
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 22)
        .frame(maxWidth: .infinity, alignment: .leading)
        .inked(shape, LinearGradient(stops: [
            .init(color: Palette.brass.opacity(0.2), location: 0),
            .init(color: Color(hex: 0xC8AD74, opacity: 0.075), location: 0.55),
            .init(color: Color(hex: 0x786034, opacity: 0.05), location: 1),
        ], startPoint: UnitPoint(x: 0.25, y: 0), endPoint: UnitPoint(x: 0.75, y: 1)))
        .gilt(shape, strength: 0.65)
        .shadow(color: .black.opacity(0.3), radius: 4.5, y: 3)
        .shadow(color: .black.opacity(0.4), radius: 24, y: 22)
    }
}

struct CommandBox: View {
    let command: String

    var body: some View {
        Text(command)
            .font(Face.mono(11))
            .foregroundStyle(Palette.text)
            .lineSpacing(3)
            .lineLimit(8)
            .textSelection(.enabled)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Palette.codeGround.opacity(0.85)))
    }
}

/// A question with options: a list to tick off, not a set of objects. A
/// hairline separates, brass marks what is ticked - and the whole row is the
/// target, never a box beside it.
struct ChoiceCard: View {
    let decision: Decision
    let model: SessionModel
    @State private var picked: [String: [String]] = [:]

    private var questions: [Question] { decision.questions }
    private var total: Int { questions.reduce(0) { $0 + $1.options.count } }
    private var count: Int { picked.values.reduce(0) { $0 + $1.count } }
    private var complete: Bool { questions.allSatisfy { !(picked[$0.question] ?? []).isEmpty } }
    private var anyMulti: Bool { questions.contains(where: \.multiSelect) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Eyebrow("Auswahl", size: 9, color: Palette.brassLabel)
            ForEach(questions, id: \.self) { q in
                Text(q.question)
                    .font(Face.ui(15))
                    .foregroundStyle(Palette.text)
                    .lineSpacing(3)
                    .padding(.top, 10)
                    .padding(.bottom, 4)
                VStack(spacing: 0) {
                    ForEach(Array(q.options.enumerated()), id: \.offset) { i, option in
                        row(q, option)
                        if i < q.options.count - 1 { Hairline() }
                    }
                }
            }
            HStack(spacing: 14) {
                Text("\(count) von \(total) gewählt").font(Face.mono(10.5)).foregroundStyle(Palette.meta)
                Spacer(minLength: 0)
                if anyMulti {
                    Button("Alle", action: selectAll)
                        .font(Face.ui(13))
                        .foregroundStyle(Palette.meta)
                        .buttonStyle(.plain)
                        .padding(.horizontal, 10)
                }
                Button { Task { await model.answer(decision, allow: true, answers: answers) } } label: {
                    Text("Loslegen")
                        .font(Face.ui(13.5, .regular))
                        .tracking(0.27)
                        .foregroundStyle(Palette.onBrass)
                        .padding(.vertical, 12)
                        .padding(.horizontal, 28)
                        .background(Capsule().fill(LinearGradient(colors: [Palette.brassLight, Palette.brassDeep],
                                                                  startPoint: UnitPoint(x: 0.25, y: 0),
                                                                  endPoint: UnitPoint(x: 0.75, y: 1))))
                        .shadow(color: Palette.brassDeep.opacity(0.45), radius: 6, y: 4)
                }
                .buttonStyle(.plain)
                .disabled(!complete)
                .opacity(complete ? 1 : 0.45)
            }
            .padding(.top, 14)
        }
    }

    private func row(_ q: Question, _ option: Option) -> some View {
        let on = (picked[q.question] ?? []).contains(option.label)
        return Button { toggle(q, option.label) } label: {
            HStack(spacing: 12) {
                Tick(on: on)
                Text(option.label)
                    .font(Face.ui(14.5, on ? .regular : .light))
                    .foregroundStyle(on ? Palette.text : Palette.unchecked)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                Spacer(minLength: 0)
            }
            .padding(.vertical, 9)
            .padding(.horizontal, 2)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func toggle(_ q: Question, _ label: String) {
        var chosen = picked[q.question] ?? []
        if let i = chosen.firstIndex(of: label) {
            chosen.remove(at: i)
        } else if q.multiSelect {
            chosen.append(label)
        } else {
            chosen = [label]
        }
        picked[q.question] = chosen
        #if os(iOS)
        UISelectionFeedbackGenerator().selectionChanged()
        #endif
    }

    private func selectAll() {
        for q in questions where q.multiSelect { picked[q.question] = q.options.map(\.label) }
    }

    private var answers: [String: String] {
        var out: [String: String] = [:]
        for q in questions { out[q.question] = (picked[q.question] ?? []).joined(separator: ", ") }
        return out
    }
}

// MARK: - Input

struct UnreadPill: View {
    let count: Int
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: "arrow.down").font(.system(size: 10, weight: .semibold)).foregroundStyle(Palette.brass)
                Text("\(count) neue").font(Face.ui(12)).foregroundStyle(Palette.text)
            }
            .padding(.vertical, 7)
            .padding(.horizontal, 14)
            .background(Capsule().fill(Palette.ground.opacity(0.92)))
            .overlay(Capsule().strokeBorder(
                LinearGradient(colors: [Palette.brass.opacity(0.3), .clear], startPoint: .top, endPoint: .center),
                lineWidth: 1))
            .shadow(color: .black.opacity(0.4), radius: 7, y: 4)
        }
        .buttonStyle(.plain)
    }
}

struct NoticeToast: View {
    let text: String
    let dismiss: () -> Void

    var body: some View {
        Text(text)
            .font(Face.ui(12.5))
            .foregroundStyle(Palette.text)
            .multilineTextAlignment(.center)
            .padding(.vertical, 9)
            .padding(.horizontal, 16)
            .background(Capsule().fill(Color(hex: 0x3A342D)))
            .overlay(Capsule().strokeBorder(Palette.brass.opacity(0.2), lineWidth: 1))
            .shadow(color: .black.opacity(0.4), radius: 10, y: 6)
            .padding(.horizontal, 30)
            .onTapGesture(perform: dismiss)
            .task(id: text) {
                try? await Task.sleep(for: .seconds(3))
                dismiss()
            }
    }
}

// MARK: - Sheets

/// Where the context ran full and Claude went on with a summary of what came
/// before. Closed it is one line; open, the summary reads like an answer.
struct SummaryCard: View {
    let text: String
    @State private var open = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Button {
                withAnimation(.easeOut(duration: 0.2)) { open.toggle() }
            } label: {
                HStack(spacing: 10) {
                    Hairline()
                    Text("Sitzung zusammengefasst").font(Face.mono(10.5)).foregroundStyle(Palette.meta).fixedSize()
                    Image(systemName: "chevron.down")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundStyle(Palette.meta)
                        .rotationEffect(.degrees(open ? 180 : 0))
                    Hairline()
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("zusammenfassung")
            if open {
                Prose(text: Self.readable(text))
                    .padding(.leading, 13)
                    .overlay(alignment: .leading) { Rectangle().fill(Palette.brass.opacity(0.25)).frame(width: 1) }
                    .transition(.opacity)
            }
        }
    }

    /// The summary's own sections ("1. Primary Request and Intent:") become
    /// headings - numbered lines ending in a colon would read as a list.
    static func readable(_ text: String) -> String {
        text.split(separator: "\n", omittingEmptySubsequences: false).map { line -> String in
            let s = String(line)
            guard let dot = s.firstIndex(of: "."), s[..<dot].allSatisfy(\.isNumber), !s[..<dot].isEmpty,
                  s.hasSuffix(":") else { return s }
            return "### " + s[s.index(after: dot)...].dropLast().trimmingCharacters(in: .whitespaces)
        }.joined(separator: "\n")
    }
}

// MARK: - Slash commands

/// The command picked for the input: a chip in front of what you type,
/// which goes after it - "/compact" and then what to keep.
struct CommandChip: View {
    let command: SlashCommand
    let remove: () -> Void

    var body: some View {
        HStack(spacing: 6) {
            Text("/" + command.name).font(Face.mono(12)).foregroundStyle(Palette.brass)
            Button(action: remove) {
                Image(systemName: "xmark").font(.system(size: 8, weight: .semibold)).foregroundStyle(Palette.meta)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Befehl entfernen")
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Capsule().fill(Palette.brass.opacity(0.12)))
        .fixedSize()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("befehl-chip")
    }
}

/// While "/…" is typed: the commands that match, one tap each.
struct CommandSuggestions: View {
    let items: [SlashCommand]
    let pick: (SlashCommand) -> Void

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 20, style: .continuous)
        VStack(alignment: .leading, spacing: 0) {
            ForEach(items) { c in
                Button { pick(c) } label: {
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Text("/" + c.name).font(Face.mono(12)).foregroundStyle(Palette.brass).lineLimit(1).fixedSize()
                        Text(c.summary).font(Face.ui(12.5)).foregroundStyle(Palette.soft).lineLimit(1)
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 9)
                    .padding(.horizontal, 16)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("vorschlag-" + c.name)
            }
        }
        .padding(.vertical, 4)
        .background(shape.fill(Color(hex: 0x2A251F, opacity: 0.97)))
        .gilt(shape)
    }
}

/// Every command to look through and learn: what works from here first,
/// then the skills and your own, then what only the Mac can do. Behind the
/// "?" each says what it does - and, if it cannot be used from here, why.
struct CommandsList: View {
    let commands: [SlashCommand]
    /// Opens the terminal's screen - where the session has one.
    var showScreen: (() -> Void)? = nil
    let pick: (SlashCommand) -> Void
    @State private var query = ""
    @State private var open: String?

    private var sections: [(String, [SlashCommand])] {
        let f = query.isEmpty ? commands : commands.filter {
            $0.name.localizedCaseInsensitiveContains(query) || $0.summary.localizedCaseInsensitiveContains(query)
                || $0.detail.localizedCaseInsensitiveContains(query)
        }
        return [("Claude Code", f.filter { $0.group == "claude" && $0.phone }),
                ("Skills", f.filter { $0.group == "skill" && $0.phone }),
                ("Eigene Befehle", f.filter { $0.group == "command" && $0.phone }),
                ("Nur am Mac", f.filter { !$0.phone })].filter { !$0.1.isEmpty }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let showScreen {
                Button(action: showScreen) {
                    HStack(spacing: 10) {
                        Image(systemName: "terminal").font(.system(size: 13, weight: .light)).foregroundStyle(Palette.brass)
                        Text("Bildschirm des Terminals ansehen").font(Face.ui(13.5)).foregroundStyle(Palette.text)
                        Spacer(minLength: 0)
                        Image(systemName: "chevron.right").font(.system(size: 9, weight: .semibold)).foregroundStyle(Palette.meta)
                    }
                    .padding(.vertical, 8)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("bildschirm-oeffnen")
            }
            TextField("", text: $query, prompt: Text("Befehl oder Stichwort …").foregroundStyle(Palette.hint))
                .textFieldStyle(.plain)
                .font(Face.ui(14))
                .foregroundStyle(Palette.text)
                .padding(.horizontal, 16)
                .padding(.vertical, 11)
                .background(Capsule().fill(Color(hex: 0xEFECE5, opacity: 0.06)))
                .accessibilityIdentifier("befehle-suche")
            if commands.isEmpty {
                Text("Befehle werden geladen …").font(Face.mono(10.5)).foregroundStyle(Palette.meta).padding(.top, 8)
            }
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    ForEach(sections, id: \.0) { title, items in
                        SectionLabel(title).padding(.top, 14)
                        ForEach(items) { c in
                            row(c)
                            Hairline()
                        }
                    }
                }
                .padding(.bottom, 24)
            }
            .scrollIndicators(.hidden)
        }
    }

    private func row(_ c: SlashCommand) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center, spacing: 8) {
                Button { c.phone ? pick(c) : toggle(c) } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text("/" + c.name).font(Face.mono(12.5)).foregroundStyle(c.phone ? Palette.brass : Palette.meta)
                            if !c.hint.isEmpty {
                                Text(c.hint).font(Face.mono(10.5)).foregroundStyle(Palette.faint).lineLimit(1)
                            }
                        }
                        Text(c.summary).font(Face.ui(13)).foregroundStyle(c.phone ? Palette.text : Palette.meta).lineLimit(2)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("befehl-" + c.name)
                Button { toggle(c) } label: {
                    Image(systemName: open == c.name ? "questionmark.circle.fill" : "questionmark.circle")
                        .font(.system(size: 16, weight: .light))
                        .foregroundStyle(Palette.meta)
                        .frame(width: 32, height: 32)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Erklärung zu /\(c.name)")
            }
            if open == c.name {
                VStack(alignment: .leading, spacing: 6) {
                    Text(c.detail).font(Face.ui(12.5)).foregroundStyle(Palette.soft)
                        .fixedSize(horizontal: false, vertical: true)
                    if !c.original.isEmpty && c.original != c.detail {
                        Text(c.original).font(Face.mono(10)).foregroundStyle(Palette.faint)
                    }
                    if let why = c.why {
                        Text(why).font(Face.mono(10.5)).foregroundStyle(Palette.clayText)
                    }
                }
                .padding(.bottom, 4)
                .transition(.opacity)
            }
        }
        .padding(.vertical, 9)
    }

    private func toggle(_ c: SlashCommand) {
        withAnimation(.easeOut(duration: 0.15)) { open = open == c.name ? nil : c.name }
    }
}

/// The terminal as it is right now - for a view a command opened there
/// (/status, /config, a list): read here, closed with Esc, confirmed with
/// Enter, answered by typing. Paging with the arrow keys stays at the Mac:
/// every key iris sends comes with a Return, and in a list that picks.
struct TerminalScreen: View {
    let model: SessionModel
    @State private var typed = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Eyebrow("Terminal")
                Spacer()
                Text(model.screenView ? "Ansicht offen" : "Eingabezeile")
                    .font(Face.mono(10))
                    .foregroundStyle(model.screenView ? Palette.brass : Palette.meta)
            }
            ScrollView([.vertical, .horizontal], showsIndicators: false) {
                Text(Self.visible(model.screenText))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Palette.soft)
                    .fixedSize()
                    .textSelection(.enabled)
                    .padding(12)
            }
            .defaultScrollAnchor(.bottomLeading)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Color(hex: 0x241F1B)))
            .accessibilityIdentifier("bildschirm")
            HStack(spacing: 8) {
                key("Esc", "schließen") { await model.press("esc") }
                key("⏎", "Enter") { await model.press("enter") }
                TextField("", text: $typed, prompt: Text("eintippen …").foregroundStyle(Palette.hint))
                    .textFieldStyle(.plain)
                    .font(Face.ui(13.5))
                    .foregroundStyle(Palette.text)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 11)
                    .background(Capsule().fill(Color(hex: 0xEFECE5, opacity: 0.06)))
                    .onSubmit {
                        let t = typed
                        typed = ""
                        Task { await model.press(text: t) }
                    }
            }
            Text("Blättern mit den Pfeiltasten geht nur am Mac.")
                .font(Face.mono(10))
                .foregroundStyle(Palette.faint)
        }
        .task {
            while !Task.isCancelled {
                await model.fetchScreen()
                try? await Task.sleep(for: .seconds(1))
            }
        }
    }

    private func key(_ label: String, _ hint: String, _ action: @escaping () async -> Void) -> some View {
        Button { Task { await action() } } label: {
            VStack(spacing: 1) {
                Text(label).font(Face.mono(13)).foregroundStyle(Palette.brass)
                Text(hint).font(Face.mono(8.5)).foregroundStyle(Palette.meta)
            }
            .frame(width: 60, height: 44)
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Palette.brass.opacity(0.1)))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("taste-" + hint)
    }

    /// The screen without the blank lines and trailing spaces Terminal pads it with.
    static func visible(_ text: String) -> String {
        var lines = text.replacingOccurrences(of: "\u{00A0}", with: " ").components(separatedBy: "\n").map { line -> String in
            var s = line
            while s.last == " " { s.removeLast() }
            return s
        }
        while lines.last?.isEmpty == true { lines.removeLast() }
        return lines.joined(separator: "\n")
    }
}

/// A view is open in the terminal (/status, /config ...): what you send
/// waits until it is closed - here with Esc, or at the Mac.
struct ViewBanner: View {
    let model: SessionModel
    var show: (() -> Void)? = nil

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "rectangle.on.rectangle")
                .font(.system(size: 11, weight: .light))
                .foregroundStyle(Palette.brass)
            Text("Im Terminal ist eine Ansicht offen – Nachrichten warten")
                .font(Face.ui(12.5))
                .foregroundStyle(Palette.soft)
                .lineLimit(2)
            Spacer(minLength: 4)
            if let show {
                Button("Ansehen", action: show)
                    .font(Face.mono(11))
                    .foregroundStyle(Palette.brass)
                    .buttonStyle(.plain)
            }
            Button("Esc") { Task { await model.press("esc") } }
                .font(Face.mono(11))
                .foregroundStyle(Palette.clayText)
                .buttonStyle(.plain)
                .accessibilityIdentifier("ansicht-esc")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Capsule().fill(Palette.brass.opacity(0.1)))
        .accessibilityIdentifier("ansicht-offen")
    }
}

// MARK: - pictures it read

/// The session a conversation belongs to - what a picture is fetched by.
/// A plain key rather than @Entry: the Mac app builds with SwiftPM, which
/// has no plugin for SwiftUI's macros.
private struct SessionKeyKey: EnvironmentKey {
    static let defaultValue: String? = nil
}

extension EnvironmentValues {
    var sessionKey: String? {
        get { self[SessionKeyKey.self] }
        set { self[SessionKeyKey.self] = newValue }
    }
}

#if os(iOS)
typealias PlatformImage = UIImage
#else
typealias PlatformImage = NSImage
#endif

/// A picture the session read, under its Read line: fetched from the bridge,
/// which hands out only pictures the session's own transcript names.
struct SessionImage: View {
    @Environment(AppModel.self) private var app
    @Environment(\.sessionKey) private var key
    let path: String
    @State private var image: PlatformImage?
    @State private var failed = false
    @State private var big = false

    @MainActor private static var cache: [String: PlatformImage] = [:]

    static func isImage(_ path: String) -> Bool {
        ["png", "jpg", "jpeg", "gif", "webp", "heic"].contains((path as NSString).pathExtension.lowercased())
    }

    var body: some View {
        Group {
            if let image {
                // So breit wie die Spalte hergibt, statt auf 260 Punkt
                // gedeckelt - ein Bildschirmfoto oder ein Kamerabild war
                // darin eine Briefmarke, auf der nichts zu erkennen war.
                // scaledToFit, weil ein resizable Bild in einem Rahmen mit
                // Maximalmassen sonst in die Breite gezogen wird.
                picture(image)
                    .scaledToFit()
                    // Feste Obergrenze statt .infinity: mit unendlicher
                    // Breite blieb am Mac nichts uebrig - das Bild war ganz
                    // verschwunden, waehrend die alte Fassung auf dem
                    // Telefon es weiter zeigte. Gross genug ist es trotzdem:
                    // vorher waren es 260 Punkt.
                    .frame(maxWidth: 520, maxHeight: 420, alignment: .leading)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(Palette.hair, lineWidth: 1))
                    .onTapGesture { big = true }
                    .help("Klicken, um das Bild gross zu sehen")
                    #if os(iOS)
                    .fullScreenCover(isPresented: $big) { FullPicture(image: image) }
                    #else
                    .sheet(isPresented: $big) { FullPicture(image: image) }
                    #endif
            } else if failed {
                Text("Bild nicht abrufbar").font(Face.mono(10)).foregroundStyle(Palette.faint)
            } else {
                // Beschriftet, weil der blanke graue Kasten wie ein kaputtes
                // Bild aussah - ich habe ihn selbst dafür gehalten.
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(Palette.hair)
                    .frame(width: 160, height: 96)
                    .overlay(Text("lädt …").font(Face.mono(10))
                        .foregroundStyle(Palette.meta))
            }
        }
        .task(id: path) { await load() }
    }

    private func picture(_ i: PlatformImage) -> Image {
        #if os(iOS)
        Image(uiImage: i).resizable()
        #else
        Image(nsImage: i).resizable()
        #endif
    }

    private func load() async {
        if let hit = Self.cache[path] { image = hit; return }
        guard let key, let client = app.client,
              let data = try? await client.raw("api/sessions/\(key)/image",
                                                query: [URLQueryItem(name: "path", value: path)]),
              let i = PlatformImage(data: data) else {
            failed = true
            return
        }
        Self.cache[path] = i
        image = i
    }
}

/// The picture as large as the screen allows - pinch to look closer. On the
/// phone it fills the screen, on the Mac it comes as a sheet; Esc closes it
/// there, so a look at what the session read costs one click and one key.
private struct FullPicture: View {
    @Environment(\.dismiss) private var dismiss
    let image: PlatformImage
    @State private var scale: CGFloat = 1

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Color.black.ignoresSafeArea()
            picture.resizable().scaledToFit()
                .scaleEffect(scale)
                .gesture(MagnifyGesture().onChanged { scale = max(1, $0.magnification) }
                    .onEnded { _ in withAnimation { scale = 1 } })
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            Button { dismiss() } label: {
                Image(systemName: "xmark").font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(.white).padding(12).background(.black.opacity(0.4), in: Circle())
            }
            .padding(16)
            #if os(macOS)
            // Esc closes the sheet; the phone keeps the plain tap it had.
            .buttonStyle(.plain)
            .keyboardShortcut(.cancelAction)
            #endif
        }
        #if os(macOS)
        .frame(minWidth: 640, idealWidth: 1100, minHeight: 480, idealHeight: 820)
        #endif
    }

    private var picture: Image {
        #if os(iOS)
        Image(uiImage: image)
        #else
        Image(nsImage: image)
        #endif
    }
}

/// A file the session handed over: a picture as a picture, a sound with a
/// play button, anything else by its name.
struct SessionFileRow: View {
    let path: String

    static func isAudio(_ path: String) -> Bool {
        ["mp3", "m4a", "wav", "aac"].contains((path as NSString).pathExtension.lowercased())
    }

    var body: some View {
        if SessionImage.isImage(path) {
            SessionImage(path: path)
        } else if Self.isAudio(path) {
            SessionAudio(path: path)
        } else {
            HStack(spacing: 7) {
                Image(systemName: "doc").font(.system(size: 11, weight: .light)).foregroundStyle(Palette.meta)
                Text((path as NSString).lastPathComponent).font(Face.mono(10.5)).foregroundStyle(Palette.meta)
            }
        }
    }
}

/// A sound the session handed over, played on the spot - fetched from the
/// bridge, which serves only files the session's transcript names.
struct SessionAudio: View {
    @Environment(AppModel.self) private var app
    @Environment(\.sessionKey) private var key
    let path: String
    @State private var playing = false
    @State private var loading = false
    @State private var failed = false
    @State private var speaker: Speaker?

    var body: some View {
        Button(action: toggle) {
            HStack(spacing: 9) {
                ZStack {
                    Circle().fill(Palette.brass.opacity(playing ? 1 : 0.18))
                    Image(systemName: playing ? "stop.fill" : "play.fill")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(playing ? Palette.onBrass : Palette.brass)
                }
                .frame(width: 28, height: 28)
                Text((path as NSString).lastPathComponent)
                    .font(Face.mono(11)).foregroundStyle(failed ? Palette.clayText : Palette.text)
                if loading { ProgressView().controlSize(.mini) }
                if failed { Text("nicht abrufbar").font(Face.mono(9.5)).foregroundStyle(Palette.faint) }
            }
            .padding(.vertical, 3)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onDisappear { speaker?.stop() }
    }

    private func toggle() {
        if playing {
            speaker?.stop()
            playing = false
            return
        }
        guard let key, let client = app.client else { failed = true; return }
        loading = true
        Task {
            defer { loading = false }
            guard let data = try? await client.raw("api/sessions/\(key)/media",
                                                   query: [URLQueryItem(name: "path", value: path)]) else {
                failed = true
                return
            }
            let s = speaker ?? Speaker()
            speaker = s
            playing = true
            s.play(data) { playing = false }
        }
    }
}

