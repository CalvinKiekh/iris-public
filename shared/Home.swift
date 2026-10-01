import SwiftUI

// Pieces of the overview that both apps show: the header of a screen,
// section labels, quota, the away switch, services, sessions and projects.

/// Eyebrow, title, path - the same three lines on every screen, so nothing is
/// relearnt from one to the next.
struct ScreenHeader<Accessory: View>: View {
    let eyebrow: String
    let title: String
    var subtitle: String?
    var back: (() -> Void)?
    /// Title and path tighter: the path beside the eyebrow, a smaller title
    /// on one line - for a screen whose header must leave room below it.
    var compact = false
    @ViewBuilder var accessory: () -> Accessory

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 6) {
                    if let back {
                        Button(action: back) {
                            Image(systemName: "chevron.left")
                                .font(.system(size: 12, weight: .light))
                                .foregroundStyle(Palette.meta)
                                .frame(width: 26, height: 26, alignment: .leading)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Zurück")
                    }
                    Eyebrow(eyebrow)
                    if compact, let subtitle, !subtitle.isEmpty {
                        Text(subtitle)
                            .font(Face.mono(10))
                            .foregroundStyle(Palette.meta)
                            .lineLimit(1)
                            .truncationMode(.middle)
                            .padding(.leading, 6)
                    }
                }
                .frame(minHeight: 26)
                Text(title)
                    .accessibilityIdentifier("titel")
                    .font(Face.display(compact ? 27 : 33))
                    .tracking(-0.33)
                    .foregroundStyle(Palette.text)
                    .lineLimit(compact ? 1 : 2)
                    .minimumScaleFactor(0.8)
                if !compact, let subtitle, !subtitle.isEmpty {
                    Text(subtitle)
                        .font(Face.mono(10.5))
                        .foregroundStyle(Palette.meta)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .padding(.top, 8)
                }
            }
            Spacer(minLength: 0)
            accessory()
        }
    }
}

extension ScreenHeader where Accessory == EmptyView {
    init(eyebrow: String, title: String, subtitle: String? = nil, back: (() -> Void)? = nil) {
        self.init(eyebrow: eyebrow, title: title, subtitle: subtitle, back: back) { EmptyView() }
    }
}



struct SectionLabel: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View { Eyebrow(text).padding(.top, 28).padding(.bottom, 6) }
}


struct QuotaLine: View {
    let quota: Quota

    var body: some View {
        HStack(spacing: 9) {
            Text("ABO").font(Face.mono(9)).tracking(9 * 0.26)
            if quota.limited {
                // Used up: nothing runs before then - the one thing to know.
                Text("Limit erreicht · frei um \(Quota.clock(quota.limitedUntil))")
                    .foregroundStyle(Palette.clayText)
            } else {
                if let f = quota.fiveHourNow {
                    Text("5 h \(Int((f * 100).rounded())) %")
                        .foregroundStyle(f >= 0.8 ? Palette.clayText : Palette.meta)
                    if quota.fiveHourResets != nil {
                        Text("bis \(Quota.clock(quota.fiveHourResets))").opacity(0.7)
                    }
                }
                if let w = quota.weekNow {
                    Text("·").opacity(0.45)
                    Text("Woche \(Int((w * 100).rounded())) %")
                        .foregroundStyle(w >= 0.8 ? Palette.clayText : Palette.meta)
                }
            }
        }
        .font(Face.mono(10.5))
        .foregroundStyle(Palette.meta)
        .accessibilityIdentifier("abo")
    }
}

/// Away: approvals from terminal sessions come to the phone. Off means the
/// dialog shows up at the Mac as always - whoever sits there must never wait
/// for a phone that is in a pocket.

struct AwayRow: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 20, style: .continuous)
        Button { Task { await app.setAway(!app.away) } } label: {
            HStack(spacing: 14) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(app.away ? "Unterwegs" : "Am Rechner")
                        .font(Face.ui(15, app.away ? .regular : .light))
                        .foregroundStyle(app.away ? Palette.brass : Palette.text)
                    Text(app.away ? "Freigaben aus dem Terminal kommen hierher"
                                  : "Freigaben aus dem Terminal erscheinen am Rechner")
                        .font(Face.ui(11.5))
                        .foregroundStyle(Palette.meta)
                }
                Spacer(minLength: 0)
                BrassToggle(isOn: app.away)
            }
            .padding(.vertical, 14).padding(.horizontal, 16)
            .inked(shape, Color(hex: 0xFFFCF4, opacity: 0.035))
            .gilt(shape, strength: app.away ? 0.55 : 0.25)
            .contentShape(shape)
        }
        .buttonStyle(.plain)
    }
}

/// Claude Code aktualisieren, ohne die Terminals zu verlieren.
///
/// Shown only when there is a new version - a row saying "nothing to do" is
/// a row in the way. Two steps on purpose: the tap opens what would happen,
/// and only the second one ends anything. Every idle session is quit and
/// picked up again in its own tab; the session id survives, so does the
/// conversation.
struct UpdateRow: View {
    @Environment(AppModel.self) private var app
    @State private var zeigt = false
    @State private var laeuft = false
    @State private var ergebnis: UpdateErgebnis?

    var body: some View {
        if let u = app.update, u.lohnt {
            let shape = RoundedRectangle(cornerRadius: 20, style: .continuous)
            Button { zeigt = true } label: {
                HStack(spacing: 14) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Claude Code \(u.neu)")
                            .font(Face.ui(15)).foregroundStyle(Palette.brass)
                        // Nur was läuft. Wie viele Sitzungen zurückkehren
                        // steht im Blatt, und vorher ist es eine Zahl ohne
                        // Frage dahinter.
                        Text("\(u.version) läuft")
                            .font(Face.ui(11.5)).foregroundStyle(Palette.meta)
                    }
                    Spacer(minLength: 0)
                    Text("aktualisieren")
                        .font(Face.mono(10.5)).foregroundStyle(Palette.brass)
                }
                .padding(.vertical, 14).padding(.horizontal, 16)
                .inked(shape, Color(hex: 0xFFFCF4, opacity: 0.035))
                .gilt(shape, strength: 0.4)
                .contentShape(shape)
            }
            .buttonStyle(.plain)
            .sheet(isPresented: $zeigt) {
                UpdateBlatt(plan: u, laeuft: $laeuft, ergebnis: $ergebnis)
            }
        }
    }

}

/// Was passieren würde, bevor es passiert - und danach, was passiert ist.
struct UpdateBlatt: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    let plan: UpdatePlan
    @Binding var laeuft: Bool
    @Binding var ergebnis: UpdateErgebnis?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Eyebrow("Claude Code aktualisieren").padding(.bottom, 6)
            Text("\(plan.version) → \(plan.neu)")
                .font(Face.ui(19)).foregroundStyle(Palette.text)

            if let e = ergebnis {
                SectionLabel(e.ok ? "Fertig" : "Nicht ganz")
                Text(e.aktualisiert ? "Läuft jetzt auf \(e.nachher)."
                                    : (e.grund.isEmpty ? "Nichts geändert." : e.grund))
                    .font(Face.ui(13)).foregroundStyle(e.ok ? Palette.soft : Palette.clayText)
                    .padding(.top, 4)
                if !e.vonHand.isEmpty {
                    // Was nicht zurückkam, steht mit seinem Befehl da - das
                    // ist zu retten, aber nur wenn man weiß womit.
                    SectionLabel("Von Hand zurückholen")
                    ForEach(e.vonHand) { v in
                        VStack(alignment: .leading, spacing: 1) {
                            Text(v.titel).font(Face.ui(13)).foregroundStyle(Palette.soft)
                            Text(v.befehl).font(Face.mono(10.5))
                                .foregroundStyle(Palette.meta).textSelection(.enabled)
                        }
                        .padding(.vertical, 3)
                    }
                }
            } else if laeuft {
                SectionLabel("Läuft")
                Text("Sitzungen beenden, aktualisieren, zurückholen. Die Tabs bleiben stehen.")
                    .font(Face.ui(13)).foregroundStyle(Palette.soft).padding(.top, 4)
                ProgressView().tint(Palette.brass).padding(.top, 10)
            } else {
                SectionLabel("Was passiert")
                Text("Jede wartende Sitzung wird beendet und im selben Tab wieder "
                     + "aufgenommen. Die Kennung bleibt, der Verlauf also auch. "
                     + "Wer gerade arbeitet, wird nicht angefasst.")
                    .font(Face.ui(13)).foregroundStyle(Palette.soft).padding(.top, 4)

                SectionLabel("Betroffen")
                ForEach(plan.sitzungen) { s in
                    // Anklickbar, weil die Frage beim Lesen aufkommt: was
                    // macht die denn gerade? Wer das sehen will, soll nicht
                    // erst das Blatt schließen und die Sitzung suchen müssen.
                    Button {
                        dismiss()
                        app.open(session: s.key)
                    } label: {
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            Text(s.verschont.isEmpty ? "kehrt zurück" : s.verschont)
                                .font(Face.mono(10))
                                .foregroundStyle(s.verschont.isEmpty ? Palette.meta : Palette.clayText)
                                .frame(width: 92, alignment: .leading)
                            Text(s.titel.isEmpty ? Fmt.path(s.cwd) : s.titel)
                                .font(Face.ui(13)).foregroundStyle(Palette.soft)
                            Spacer(minLength: 0)
                            Image(systemName: "chevron.right")
                                .font(.system(size: 9, weight: .light))
                                .foregroundStyle(Palette.faint)
                        }
                        .padding(.vertical, 4)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }

                HStack(spacing: 10) {
                    Button {
                        laeuft = true
                        Task {
                            ergebnis = await app.runUpdate()
                            laeuft = false
                        }
                    } label: {
                        Text("Jetzt aktualisieren")
                            .font(Face.ui(13)).foregroundStyle(Palette.brass)
                            .padding(.horizontal, 12).padding(.vertical, 8)
                            .background(Capsule().fill(Color(hex: 0xEFECE5, opacity: 0.07)))
                            .contentShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    Button("Abbrechen") { dismiss() }
                        .font(Face.ui(13))
                        .foregroundStyle(Palette.meta)
                        .buttonStyle(.plain)
                        .padding(.horizontal, 4)
                        .keyboardShortcut(.cancelAction)
                }
                .padding(.top, 20)
            }
            Spacer(minLength: 0)
            // Waehrend es laeuft steht hier nichts, und das ist ehrlich:
            // Zumachen hielte nichts an - die Bruecke ist ein eigener Prozess
            // und arbeitet weiter. Es dauert Sekunden.
            if ergebnis != nil {
                Button("Schließen") { dismiss() }
                    .font(Face.ui(13)).foregroundStyle(Palette.brass)
                    .buttonStyle(.plain)
                    .keyboardShortcut(.cancelAction)
            }
        }
        .padding(24)
        .frame(minWidth: 380, minHeight: 340)
        .background(Room())
    }
}

/// One line to the services: whether everything reports, and how many.

struct ServicesEntry: View {
    let summary: ServiceSummary?

    private var broken: Bool { (summary?.unhealthy ?? 0) + (summary?.missing ?? 0) > 0 }
    private var dot: Color { summary == nil ? Palette.faint : broken ? Palette.clay : Palette.sage }

    var body: some View {
        HStack(spacing: 12) {
            Circle().fill(dot).frame(width: 7, height: 7).frame(width: 10)
            VStack(alignment: .leading, spacing: 3) {
                Text("Dienste").font(Face.ui(15)).foregroundStyle(Palette.soft)
                Text(meta).font(Face.ui(11.5)).foregroundStyle(broken ? Palette.clayText : Palette.meta)
            }
            Spacer(minLength: 8)
            Image(systemName: "chevron.right").font(.system(size: 11, weight: .light)).foregroundStyle(Palette.faint)
        }
        .padding(.vertical, 12)
        .padding(.horizontal, 2)
        .contentShape(Rectangle())
    }

    private var meta: String {
        guard let s = summary else { return "nicht abrufbar" }
        guard s.total > 0 else { return "noch meldet sich nichts" }
        var parts = ["\(s.healthy) von \(s.total) in Ordnung"]
        if s.missing > 0 { parts.append("\(s.missing) vermisst") }
        if s.unhealthy > 0 { parts.append("\(s.unhealthy) gestört") }
        return parts.joined(separator: " · ")
    }
}

struct SessionRow: View {
    let info: SessionInfo

    var body: some View {
        HStack(spacing: 12) {
            Group {
                if info.openAsks > 0 || info.busy { Bud(size: 7) }
                else { Circle().fill(Palette.sage).frame(width: 7, height: 7) }
            }
            .frame(width: 10)
            VStack(alignment: .leading, spacing: 3) {
                Text(info.title.isEmpty ? info.label : Fmt.title(info.title))
                    .font(Face.ui(15, info.openAsks > 0 ? .regular : .light))
                    .foregroundStyle(info.openAsks > 0 ? Palette.text : Palette.soft)
                    .lineLimit(1)
                Text(meta).font(Face.ui(11.5)).foregroundStyle(Palette.meta).lineLimit(1)
            }
            Spacer(minLength: 8)
            if info.openAsks > 0 {
                Text("FREIGABE").font(Face.mono(9)).tracking(9 * 0.22).foregroundStyle(Palette.brass)
            } else {
                Image(systemName: "chevron.right").font(.system(size: 11, weight: .light)).foregroundStyle(Palette.faint)
            }
        }
        .padding(.vertical, 13)
        .contentShape(Rectangle())
    }

    private var meta: String {
        var parts: [String] = []
        if info.terminal { parts.append("Terminal") }
        parts.append(info.label)
        parts.append(info.busy ? "arbeitet" : "bereit")
        if info.acts > 0 { parts.append("\(info.acts) Befehle") }
        if info.failed > 0 { parts.append("\(info.failed) fehlgeschlagen") }
        if info.background > 0 { parts.append("\(info.background) im Hintergrund") }
        return parts.joined(separator: " · ")
    }
}

struct ProjectRow: View {
    let project: Project

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(project.label).font(Face.ui(15)).foregroundStyle(Palette.soft).lineLimit(1)
                Text(Fmt.age(project.lastUsed)).font(Face.ui(11.5)).foregroundStyle(Palette.meta)
            }
            Spacer(minLength: 8)
            Text("\(project.sessions)").font(Face.mono(10.5)).foregroundStyle(Palette.meta)
        }
        .padding(.vertical, 13)
        .contentShape(Rectangle())
    }
}

/// One conversation that ran in a project - what to pick up again. Shared:
/// the phone lists them on its project screen, the Mac in its project sheet.
struct ConversationRow: View {
    let conversation: Conversation
    let live: Bool

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(conversation.title.isEmpty ? String(conversation.sessionId.prefix(8)) : conversation.title)
                    .font(Face.ui(15)).foregroundStyle(Palette.soft).lineLimit(1)
                Text(Fmt.age(conversation.modified) + (live ? " · läuft im Terminal" : ""))
                    .font(Face.ui(11.5)).foregroundStyle(Palette.meta)
            }
            Spacer(minLength: 8)
            if live { Bud(color: Palette.sage, size: 6) }
        }
        .padding(.vertical, 13)
        .contentShape(Rectangle())
    }
}

/// The computers this device reaches - the one in use in brass. One tap
/// switches; "+ Rechner" adds a Pi, a Windows machine, a second Mac.
struct MachineRow: View {
    @Environment(AppModel.self) private var app
    let add: () -> Void

    var body: some View {
        Flow(spacing: 18, lineSpacing: 8) {
            ForEach(app.machines) { m in
                let on = m.id == app.machine?.id
                Button {
                    guard !on else { return }
                    app.use(m)
                    Task { await app.refresh() }
                } label: {
                    HStack(spacing: 6) {
                        Circle().fill(on ? Palette.brass : Palette.faint.opacity(0.6)).frame(width: 5, height: 5)
                        Text(m.name).font(Face.mono(11)).foregroundStyle(on ? Palette.brass : Palette.meta)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(on ? .isSelected : [])
                .accessibilityIdentifier("rechner-" + m.name)
            }
            Button(action: add) {
                Text("+ Rechner").font(Face.mono(11, .light)).foregroundStyle(Palette.hint)
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("rechner-hinzufuegen")
        }
    }
}

/// Where a new session starts: the projects of the computer in use, newest
/// first, or any other folder on it. One tap starts it there.
struct NewSessionList: View {
    @Environment(AppModel.self) private var app
    let start: (String) -> Void
    @State private var folder = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(app.machine.map { "auf \($0.name)" } ?? "")
                .font(Face.mono(10.5))
                .foregroundStyle(Palette.meta)
                .padding(.bottom, 10)
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(app.projects) { p in
                        Button { start(p.path) } label: {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(p.label).font(Face.ui(15)).foregroundStyle(Palette.text)
                                Text(Fmt.path(p.path)).font(Face.mono(10.5)).foregroundStyle(Palette.meta).lineLimit(1)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.vertical, 11)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("neu-" + p.label)
                        Hairline()
                    }
                    if app.projects.isEmpty {
                        Text("Auf diesem Rechner gibt es noch keine Projekte - unten einen Ordner angeben.")
                            .font(Face.ui(13)).foregroundStyle(Palette.meta).padding(.vertical, 12)
                    }
                }
            }
            .scrollIndicators(.hidden)
            // Any other folder, as the computer names it (C:\... on Windows).
            HStack(spacing: 8) {
                TextField("", text: $folder, prompt: Text("Anderer Ordner …").foregroundStyle(Palette.hint))
                    .textFieldStyle(.plain)
                    .font(Face.mono(12))
                    .foregroundStyle(Palette.text)
                    #if os(iOS)
                    .textInputAutocapitalization(.never)
                    #endif
                    .autocorrectionDisabled()
                    .onSubmit(startFolder)
                    .accessibilityIdentifier("neu-ordner")
                Button("Starten", action: startFolder)
                    .font(Face.ui(13))
                    .foregroundStyle(Palette.brass)
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("neu-starten")
                    .disabled(folder.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 11)
            .background(Capsule().fill(Color(hex: 0xEFECE5, opacity: 0.06)))
            .padding(.top, 12)
            if let problem = app.problem {
                Text(problem).font(Face.mono(10.5)).foregroundStyle(Palette.clayText).padding(.top, 8)
            }
        }
    }

    private func startFolder() {
        let f = folder.trimmingCharacters(in: .whitespaces)
        if !f.isEmpty { start(f) }
    }
}
