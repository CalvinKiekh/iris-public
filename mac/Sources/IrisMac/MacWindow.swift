import AppKit
import SwiftUI
import UniformTypeIdentifiers

/// The window after design/Desktop.dc.html: a lit room, the sessions on the
/// left, the conversation on the stage beside it - the only thing that gets a
/// surface. What the session is made of stands over the conversation, not in
/// a column of its own: the window is often half a screen wide.
struct MacWindow: View {
    @Environment(AppModel.self) private var app
    @State private var selected: String?
    /// Half a screen is a normal size for this window. Three columns need
    /// about 1100 points; below that they would each get a strip too narrow
    /// to read, so the side columns become panels that open on demand.
    @State private var width: CGFloat = 1400
    @State private var sidebarOpen = false
    /// Folded away by hand, and kept that way across launches. Width decides
    /// whether the column *can* stand; this decides whether it should.
    @AppStorage("sidebarWanted") private var sidebarWanted = true

    private var sidebarFits: Bool { width >= 820 }
    private var showsSidebar: Bool { sidebarFits && sidebarWanted }

    private var live: [SessionInfo] {
        app.sessions.filter { !$0.exited }.sorted { $0.lastActive > $1.lastActive }
    }
    /// The newest session only until one is shown. `live` is sorted by when
    /// a session was last active, so following it meant the window changed
    /// the conversation under your eyes whenever another session did
    /// anything - the one you were reading was simply gone.
    private var current: String? {
        // Once picked it stays, even if this refresh does not list it.
        // `refresh` replaces the whole array, and one answer without the
        // session took the stage away and put it back - the conversation
        // blinked out for a moment. Ending is handled below, deliberately.
        if let selected { return selected }
        return live.first?.key
    }

    var body: some View {
        ZStack {
            Room()
            VStack(spacing: 8) {
                // Flush with the columns below it, and low enough to clear the
                // window's own buttons - those sit in the top 32 points.
                HStack(spacing: 8) {
                    BarButton(symbol: "sidebar.leading", active: showsSidebar || sidebarOpen) {
                        toggleSidebar()
                    }
                    Spacer(minLength: 0)
                }
                .frame(height: 28)
                HStack(alignment: .top, spacing: 18) {
                    if showsSidebar { sidebar.frame(width: 256) }
                    stage
                }
            }
            .padding(.horizontal, 18)
            .padding(.top, 34)            // under the hidden title bar's buttons
            .padding(.bottom, 18)

            if sidebarOpen && !showsSidebar {
                panel(at: .topLeading, from: .leading) { sidebar.frame(width: 256) }
            }
            // Der Assistent, ueber allem und in jeder Ansicht erreichbar.
            VorarbeiterOrb()
        }
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
        // Hold on to what is shown. Only when nothing is picked yet, or what
        // was picked has ended and left the list, does the newest take over.
        .onChange(of: current, initial: true) { _, key in
            guard let chosen = selected else {
                if key != nil { Trace.write("Auswahl: keine -> \(key!.prefix(10))") }
                selected = key
                return
            }
            // Gone for good, not just missing from one answer: the list has
            // to say something, and say that this session is not in it or has
            // ended. An empty answer means nothing.
            let ended = app.sessions.contains { $0.key == chosen && $0.exited }
            let absent = !app.sessions.isEmpty && !app.sessions.contains { $0.key == chosen }
            if ended || absent {
                Trace.write("Auswahl: \(chosen.prefix(10)) ist \(ended ? "beendet" : "fort")"
                            + " -> \(live.first?.key.prefix(10) ?? "keine")")
                selected = live.first?.key
            }
        }
        // Grown wide again: the panel would stand in front of its own column.
        .onChange(of: showsSidebar) { _, now in if now { sidebarOpen = false } }
        // Another computer: what was selected belonged to the one before. Not
        // at start-up though - the machine is nil until the first refresh
        // answers, and clearing there threw away the session just pinned.
        .onChange(of: app.machine?.id) { before, now in
            if before != nil && now != before { selected = nil }
        }
        .animation(.spring(duration: 0.28), value: sidebarOpen)
        .task {
            while !Task.isCancelled {
                await app.refresh()
                try? await Task.sleep(for: .seconds(5))
            }
        }
        // A session picked in the menu bar opens here.
        .onChange(of: app.path) { _, path in
            if case .session(let key)? = path.last {
                Trace.write("Pfad wählt [\(key.prefix(10))]")
                selected = key
            }
        }
    }

    /// One button, one meaning: show the column or hide it. Whether it then
    /// stands as a column or slides over the stage is the window's width.
    private func toggleSidebar() {
        if sidebarFits {
            sidebarWanted.toggle()
            sidebarOpen = false
        } else {
            sidebarOpen.toggle()
        }
    }

    private var sidebar: some View {
        // Picking a session is what the panel was opened for - it closes itself.
        Sidebar(sessions: live, selected: current) { key in
            selected = key
            sidebarOpen = false
        }
    }

    private var stage: some View {
        Group {
            if let key = current {
                Stage(model: app.model(for: key)).id(key)
            } else {
                Text(app.problem ?? "Keine laufende Sitzung")
                    .font(Face.ui(15)).foregroundStyle(Palette.meta)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(StageSurface())
    }

    /// A column that has no room as a column: laid over the stage, closed by
    /// clicking beside it.
    @ViewBuilder
    private func panel<Content: View>(at corner: Alignment, from edge: Edge,
                                      @ViewBuilder content: () -> Content) -> some View {
        ZStack(alignment: corner) {
            Color.black.opacity(0.3)
                .onTapGesture { sidebarOpen = false }
            content()
                .padding(14)
                .background(StageSurface())
                .padding(.horizontal, 18)
                .padding(.top, 70)        // level with the columns beside it
                .padding(.bottom, 18)
                .transition(.move(edge: edge).combined(with: .opacity))
        }
        .ignoresSafeArea()
    }
}

/// Folds a column in or out. Smaller than the round buttons of the input:
/// it lives in the title bar's band and must not push the window down.
struct BarButton: View {
    let symbol: String
    var active = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 12, weight: .regular))
                .foregroundStyle(active ? Palette.brass : Color(hex: 0x9A9287))
                .frame(width: 28, height: 28)
                .background(Circle().fill(Color(hex: 0xEFECE5, opacity: active ? 0.12 : 0.05)))
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
    }
}

/// Depth from light, not texture: a raised, softly lit surface.
struct StageSurface: View {
    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 28, style: .continuous)
        shape
            .fill(Color(hex: 0xFFFCF4, opacity: 0.026))
            .overlay(shape.fill(LinearGradient(
                colors: [Color(hex: 0xFFF7E7, opacity: 0.075), Color(hex: 0xFFF7E7, opacity: 0.012), .black.opacity(0.10)],
                startPoint: .top, endPoint: .bottom)))
            .shadow(color: .black.opacity(0.35), radius: 30, y: 18)
    }
}

// MARK: - Left: the sessions

struct Sidebar: View {
    @Environment(AppModel.self) private var app
    let sessions: [SessionInfo]
    let selected: String?
    let select: (String) -> Void
    @State private var addingMachine = false
    @State private var newSession = false
    @State private var renameTarget: SessionInfo?
    @State private var newName = ""
    @State private var openProject: Project?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Eyebrow("iris").padding(.horizontal, 14)
                Text("Sitzungen")
                    .font(Face.display(30))
                    .foregroundStyle(Palette.text)
                    .padding(.horizontal, 14)
                    .padding(.top, 2)
                MachineRow { addingMachine = true }
                    .padding(.horizontal, 14)
                    .padding(.top, 10)
                    .alert("Sitzung umbenennen", isPresented: Binding(get: { renameTarget != nil }, set: { if !$0 { renameTarget = nil } })) {
                TextField("Name", text: $newName)
                Button("Speichern") { if let t = renameTarget { Task { await app.rename(session: t.key, to: newName) } } }
                Button("Abbrechen", role: .cancel) {}
            } message: {
                Text("Leer lassen stellt den automatischen Titel wieder her.")
            }
                    .popover(isPresented: $addingMachine) { AddMachine(shown: $addingMachine) }
                Button { newSession = true } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "plus").font(.system(size: 11, weight: .light)).foregroundStyle(Palette.brass)
                        Text("Neue Sitzung").font(Face.ui(13)).foregroundStyle(Palette.text)
                        Spacer()
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .padding(.top, 8)
                .popover(isPresented: $newSession) {
                    NewSessionList { cwd in
                        Task {
                            if let key = await app.start(cwd: cwd) {
                                newSession = false
                                await app.refresh()
                                select(key)
                            }
                        }
                    }
                    .padding(18)
                    .frame(width: 380, height: 420)
                }
                if let q = app.quota { QuotaLine(quota: q).padding(.horizontal, 14).padding(.top, 8) }
                AwayRow().padding(.top, 16)
                UpdateRow().padding(.top, 10)
                SectionLabel("Laufend").padding(.horizontal, 14)
                ForEach(sessions) { s in
                    Button { select(s.key) } label: { SessionRow(info: s) }
                        .buttonStyle(.plain)
                        .contextMenu {
                            Button("Umbenennen") {
                                newName = s.title
                                renameTarget = s
                            }
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 2)
                        // The active one is set into the surface, not raised.
                        .background(RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(.black.opacity(s.key == selected ? 0.20 : 0))
                            .shadow(color: .black.opacity(s.key == selected ? 0.45 : 0), radius: 3, y: 2))
                }
                SectionLabel("Projekte").padding(.horizontal, 14)
                ForEach(app.projects) { p in
                    // The row only drew itself - on the phone a NavigationLink
                    // carried it, and the Mac had nothing in its place.
                    Button { openProject = p } label: {
                        ProjectRow(project: p).padding(.horizontal, 12)
                    }
                    .buttonStyle(.plain)
                }
                SectionLabel("Brücke").padding(.horizontal, 14)
                Text(app.problem ?? (app.bridge?.base.host ?? "nicht verbunden"))
                    .font(Face.mono(10.5))
                    .foregroundStyle(app.problem == nil ? Palette.meta : Palette.clayText)
                    .padding(.horizontal, 14)
            }
            .padding(.bottom, 20)
        }
        .scrollIndicators(.never)
        .sheet(item: $openProject) { ProjectSheet(project: $0) }
    }
}

/// A project's conversations, as the phone shows them: start a new session in
/// that folder, or pick up one that ran there before.
struct ProjectSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    let project: Project
    @State private var rows: [Conversation] = []
    @State private var loaded = false
    @State private var starting = false
    @State private var forkCandidate: Conversation?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                ScreenHeader(eyebrow: "Projekt", title: project.label, subtitle: Fmt.path(project.path))
                Button { open(nil, fork: false) } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "plus").font(.system(size: 12, weight: .light))
                            .foregroundStyle(Palette.brass).frame(width: 10)
                        Text("Neue Sitzung").font(Face.ui(15)).foregroundStyle(Palette.text)
                        Spacer()
                    }
                    .padding(.vertical, 13)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(starting)
                .padding(.top, 18)
                if !rows.isEmpty { SectionLabel("Fortsetzen") }
                ForEach(rows) { c in
                    Button { pick(c) } label: {
                        ConversationRow(conversation: c, live: app.liveTerminal(for: c) != nil)
                    }
                    .buttonStyle(.plain)
                    .disabled(starting)
                    Hairline()
                }
                if loaded && rows.isEmpty {
                    Text("Noch keine Unterhaltungen in diesem Verzeichnis.")
                        .font(Face.ui(13)).foregroundStyle(Palette.meta).padding(.top, 20)
                }
            }
            .padding(.horizontal, 24).padding(.top, 16).padding(.bottom, 28)
        }
        .scrollIndicators(.never)
        .background(Room())
        .frame(width: 460, height: 560)
        .task {
            rows = await app.conversations(of: project)
            loaded = true
        }
        .overlay(alignment: .topTrailing) {
            Button { dismiss() } label: {
                Image(systemName: "xmark").font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Palette.meta).padding(10)
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.cancelAction)
        }
        .confirmationDialog("Läuft vermutlich gerade im Terminal",
                            isPresented: Binding(get: { forkCandidate != nil }, set: { if !$0 { forkCandidate = nil } }),
                            titleVisibility: .visible, presenting: forkCandidate) { c in
            Button("Als Abzweig öffnen") { open(c.sessionId, fork: true) }
            Button("Abbrechen", role: .cancel) {}
        } message: { _ in
            Text("Der bisherige Verlauf kommt mit, die Sitzung am Rechner bleibt unberührt. Was hier passiert, fliesst nicht zurück.")
        }
    }

    private func pick(_ c: Conversation) {
        if let live = app.liveTerminal(for: c) {
            app.path.append(.session(live.key))
            dismiss()
        } else if c.likelyOpen {
            forkCandidate = c
        } else {
            open(c.sessionId, fork: false)
        }
    }

    private func open(_ resume: String?, fork: Bool) {
        guard !starting else { return }
        starting = true
        Task {
            if let key = await app.start(cwd: project.path, resume: resume, fork: fork) {
                app.path.append(.session(key))
                dismiss()
            }
            starting = false
        }
    }
}

// MARK: - Middle: the conversation

struct Stage: View {
    let model: SessionModel
    @State private var text = ""
    /// Empty on purpose: a position preset to .bottom is carried out when the
    /// view is built, and that is a jump to an end the lazy list has not
    /// measured yet - the last automatic one left. Where it opens is settled
    /// by defaultScrollAnchor(.bottom, for: .initialOffset), which SwiftUI
    /// resolves after layout. This one only serves the "neu" pill.
    @State private var position = ScrollPosition()
    @State private var atBottom = true
    @State private var unread = 0
    /// How many turns there were when you left the bottom - what came since
    /// is what "neu" counts. Updates to a turn already there are not new.
    @State private var seenTurns = 0
    /// Only the last turns are drawn; "Frühere Nachrichten" adds more. With
    /// thousands of rows the list can only guess their heights, and every
    /// jump to the end landed somewhere else - the view jumped about and
    /// "unten" flickered on every card.
    /// Fewer rows than before: with a hundred and fifty of them the list has
    /// to guess the height of everything not drawn yet, and the guess is what
    /// put the view into empty space. "Frühere Nachrichten" fetches more.
    @State private var visible = 50
    /// Set by your own finger or trackpad only. The flicker while rows get
    /// measured no longer counts anything as new.
    @State private var scrolledUp = false
    @State private var dragging = false
    @Environment(AppModel.self) private var app
    @State private var showBackground = false
    @State private var showPages = false
    @State private var showModes = false
    /// Held here, not in the composer: the whole stage takes a dropped file,
    /// so you do not have to hit the input strip.
    @State private var attachments: [Attachment] = []
    @State private var dropping = false
    @State private var zeigeUebergabe = false
    /// Wie hoch die Eingabezeile gerade ist - die Freigabe legt sich als
    /// Ueberlagerung genau darueber, und die Zeile waechst beim Tippen mit.
    @State private var ablageHoehe: CGFloat = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ScreenHeader(eyebrow: model.isTerminal ? "Terminal" : "Sitzung", title: model.title, subtitle: model.path)
                .padding(.horizontal, 30)
                .padding(.top, 26)
            ActivityLine(model: model)
                .padding(.horizontal, 30)
                .padding(.top, 12)
            // What the session is made of, over the conversation instead of in
            // a column beside it: always in view, and it takes no width from
            // the text. The quota stays in the sidebar - it belongs to the
            // machine, not to this session.
            HStack(alignment: .firstTextBaseline, spacing: 16) {
                FactsRow(model: model, services: app.services, quota: false, git: true,
                         showModes: $showModes, showBackground: $showBackground, showPages: $showPages)
                // Only where the repository could carry the work across: the
                // button has no meaning without a remote to clone from.
                if model.handover?.github == true {
                    Button("mitnehmen") { zeigeUebergabe = true }
                        .font(Face.mono(10.5))
                        .foregroundStyle(Palette.brass)
                        .buttonStyle(.plain)
                        .fixedSize()
                }
            }
            .padding(.horizontal, 30)
            .padding(.top, 8)
            .task(id: model.key) { await model.loadHandover() }
            .sheet(isPresented: $zeigeUebergabe) {
                UebergabeBlatt(model: model)
            }
            if showBackground && !model.background.isEmpty {
                BackgroundList(tasks: model.background).padding(.horizontal, 30).padding(.top, 8)
            }
            if showPages && !model.artifacts.isEmpty {
                PagesList(pages: model.artifacts).padding(.horizontal, 30).padding(.top, 8)
            }
            conversation
            // Below the conversation, not floating over it: the input is
            // see-through, and text under it would read through.
            dock
                .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { ablageHoehe = $0 }
        }
        .overlay(alignment: .top) {
            if let notice = model.notice {
                NoticeToast(text: notice) { model.notice = nil }.padding(.top, 8)
            }
        }
        // Die Freigabe liegt als Ueberlagerung ueber der Eingabe.
        //
        // Dort war sie zu sehen und nahm keinen Klick an - auch ein Horcher
        // auf der Karte selbst blieb stumm, waehrend der Knopf in der
        // Eingabezeile daneben tadellos ansprach. Was die Flaeche verschluckt
        // hat, habe ich nicht gefunden: weder die Maske des Gespraechs (die
        // Ablage liegt ausserhalb), noch das Ablegen-Feld, noch die
        // Animation - beide einzeln stillgelegt, beide ohne Wirkung.
        //
        // Eine Ueberlagerung liegt ueber allem und ist nachweislich
        // klickbar: die Meldung oben arbeitet seit jeher so. Belegt am
        // 23.09.: in der Ablage blieb die Spur nach einem Dutzend Klicks
        // leer, als Ueberlagerung stand sofort "Freigabe erlauben" darin.
        // Der Platz bleibt unten am Gespraech, wo sie hingehoert.
        .overlay(alignment: .bottom) {
            if let d = model.decisions.first {
                Group {
                    if d.isQuestion { ChoiceCard(decision: d, model: model) }
                    else { ApprovalCard(decision: d, model: model) }
                }
                // Die Karte ist fuer einen undurchsichtigen Untergrund
                // gebaut - ihre Fuellung ist ein zarter Verlauf. Als
                // Ueberlagerung stand die Kopfzeile mitten durch den Text.
                // Also der Grund des Raums darunter, in derselben Form.
                .background(Palette.ground)
                .clipShape(RoundedRectangle(cornerRadius: 30, style: .continuous))
                .frame(maxWidth: 720, alignment: .leading)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 30)
                // Direkt ueber der Eingabe, deren Hoehe mitwaechst.
                .padding(.bottom, ablageHoehe + 8)
                .id(d.id)
                // Ohne Bewegung. Jede Variante sah aus, als rutsche etwas
                // ueber die Kopfzeile - und eine Freigabe, die die Sitzung
                // anhaelt, braucht keinen Auftritt.
            }
        }

        // Anywhere on the stage - the input strip alone was a few points tall
        // and most drops landed beside it.
        // Not dropDestination(for: URL.self): a screenshot dragged from its
        // thumbnail and a picture pulled out of a browser carry the image
        // itself, not a file, and were turned away at the door.
        .onDrop(of: [.fileURL, .image, .pdf], isTargeted: Binding(
            get: { dropping }, set: { dropping = $0 && !model.ended })) { _ in
            guard !model.ended else { return false }
            let taken = Attachment.read(from: NSPasteboard(name: .drag))
            attachments += taken
            return !taken.isEmpty
        }
        .overlay {
            if dropping {
                let shape = RoundedRectangle(cornerRadius: 28, style: .continuous)
                shape
                    .fill(Palette.brass.opacity(0.05))
                    .overlay(shape.strokeBorder(Palette.brass.opacity(0.65),
                                                style: StrokeStyle(lineWidth: 2, dash: [8, 6])))
                    .overlay(Text("Dateien hier ablegen")
                        .font(Face.ui(14)).foregroundStyle(Palette.brass))
                    .padding(6)
                    .allowsHitTesting(false)
            }
        }
        .animation(.easeOut(duration: 0.15), value: dropping)
        .onAppear {
            model.start()
            Trace.write("Bühne auf [\(model.key.prefix(10))] \(model.turns.count) Züge, "
                        + "\(app.sessions.count) Sitzungen gemeldet")
        }
        .onDisappear {
            model.stop()
            Trace.write("Bühne zu [\(model.key.prefix(10))]")
        }
    }

    private var conversation: some View {
        ScrollView {
            // Not lazy. A lazy stack measures a row when it draws it, so
            // every anchor and every jump works from an estimate, and when
            // the estimate is wrong the view stands past the rows: the stage
            // in its own colour, nothing on it. Patching the jumps was not
            // enough - the estimate itself is the fault. Fifty turns lay
            // themselves out at once, and then the heights are known.
            VStack(alignment: .leading, spacing: 22) {
                if model.turns.count > visible {
                    Button {
                        visible += 100
                    } label: {
                        Text("Frühere Nachrichten (\(model.turns.count - visible))")
                            .font(Face.mono(10.5))
                            .foregroundStyle(Palette.meta)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.plain)
                }
                // Opened for the first time the model is empty and reads its
                // cards from the cache - a second or two in which the view
                // showed nothing at all, and nothing looks exactly like a
                // conversation that went missing. Say which of the two it is.
                if model.turns.isEmpty {
                    HStack(spacing: 9) {
                        if model.settling {
                            Bud(color: Palette.meta, size: 5)
                            Text("Verlauf wird geladen …")
                        } else {
                            Text("Noch nichts in dieser Sitzung.")
                        }
                    }
                    .font(Face.mono(10.5))
                    .foregroundStyle(Palette.meta)
                    .padding(.vertical, 6)
                }
                let drawn = model.drawn(last: visible)
                ForEach(drawn.settled) { TurnView(turn: $0).environment(\.sessionKey, model.key) }
                if model.busy && model.connected && !model.ended {
                    WorkingRow(model: model).transition(.opacity)
                }
                ForEach(drawn.waiting) { TurnView(turn: $0).environment(\.sessionKey, model.key) }
            }
            .padding(.horizontal, 30)
            .padding(.top, 20)
            // Taller than the fade below: what is masked out takes no clicks,
            // and the working row is always the lowest thing there. Its
            // button did nothing until the padding pushed it clear.
            .padding(.bottom, 34)
            .frame(maxWidth: 760, alignment: .leading)
        }
        .scrollIndicators(.automatic)
        .defaultScrollAnchor(.bottom, for: .initialOffset)
        // Growing content keeps the end in view by itself while you are there.
        .defaultScrollAnchor(.bottom, for: .sizeChanges)
        .scrollPosition($position)
        .onScrollGeometryChange(for: Bool.self) { g in
            g.contentOffset.y + g.containerSize.height >= g.contentSize.height - 120
        } action: { _, near in
            atBottom = near
            if near {
                scrolledUp = false
                unread = 0
                seenTurns = model.turns.count
            }
        }
        // Whoever scrolled up is reading; nothing new pulls them down.
        // No jumping to the end by hand any more. A LazyVStack measures its
        // rows as they are drawn, so "the end" is a guess until they exist,
        // and every jump could land past them - the conversation went blank
        // and stayed blank until it was opened again. The size-change anchor
        // above keeps the end in view while it grows, which is all this was
        // ever for.
        .onChange(of: model.revision) {
            if !scrolledUp {
                seenTurns = model.turns.count
            } else {
                unread = max(0, model.turns.count - seenTurns)
            }
        }
        .onChange(of: model.settling) { _, settling in
            if !settling {
                unread = 0
                seenTurns = model.turns.count
            }
        }
        .onScrollPhaseChange { _, phase in
            if phase == .interacting {
                dragging = true
            } else if phase == .idle && dragging {
                dragging = false
                scrolledUp = !atBottom
                if !scrolledUp {
                    unread = 0
                    seenTurns = model.turns.count
                }
            }
        }
        // What runs off either edge fades instead of breaking off.
        .mask {
            VStack(spacing: 0) {
                LinearGradient(colors: [.clear, .black], startPoint: .top, endPoint: .bottom).frame(height: 26)
                Rectangle()
                LinearGradient(colors: [.black, .clear], startPoint: .top, endPoint: .bottom).frame(height: 22)
            }
        }
    }

    /// What waits for you sits right above the input.
    private var dock: some View {
        VStack(alignment: .leading, spacing: 12) {
            if unread > 0 {
                UnreadPill(count: unread) {
                    scrolledUp = false
                    unread = 0
                    seenTurns = model.turns.count
                    withAnimation(.easeOut(duration: 0.3)) { position.scrollTo(edge: .bottom) }
                }
            }
            if model.screenView && model.isTerminal {
                ViewBanner(model: model).frame(maxWidth: 760)
            }
            if !model.ended {
                MacComposer(model: model, text: $text, attachments: $attachments)
            }
        }
        .padding(.horizontal, 30)
        .padding(.bottom, 22)
        .padding(.top, 4)
    }
}

/// The input on the Mac: Return sends, Option-Return starts a new line,
/// files come through the open panel or dropped onto the stage.
struct MacComposer: View {
    let model: SessionModel
    @Binding var text: String
    @Binding var attachments: [Attachment]
    @State private var pickFiles = false
    @State private var dictation = Dictation()
    @State private var base = ""
    @State private var command: SlashCommand?
    @State private var showCommands = false
    @State private var spokenHeight: CGFloat = 0
    @State private var geschickt = false

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 26, style: .continuous)
        VStack(alignment: .leading, spacing: 8) {
            if command == nil {
                let found = model.suggestions(for: text)
                if !found.isEmpty {
                    CommandSuggestions(items: found) { c in
                        command = c
                        text = ""
                    }
                    .frame(maxWidth: 520)
                }
            }
            if !attachments.isEmpty {
                HStack(spacing: 8) {
                    ForEach(attachments) { a in
                        HStack(spacing: 6) {
                            Image(systemName: "paperclip").font(.system(size: 10))
                            Text(a.name).font(Face.mono(10)).lineLimit(1)
                            Button { attachments.removeAll { $0.id == a.id } } label: {
                                Image(systemName: "xmark").font(.system(size: 8, weight: .semibold))
                            }
                            .buttonStyle(.plain)
                        }
                        .foregroundStyle(Palette.soft)
                        .padding(.horizontal, 10).padding(.vertical, 5)
                        .background(Capsule().fill(Color(hex: 0xEFECE5, opacity: 0.05)))
                    }
                }
                .padding(.leading, 12)
            }
            HStack(alignment: .bottom, spacing: 8) {
                RoundButton(symbol: "plus") { pickFiles = true }
                // Beside the other tools, not in the conversation: the mask
                // that fades the scroll view takes no clicks, so the button
                // there could not be pressed at all.
                if model.canBackground && model.isTerminal && model.info?.typable == true {
                    RoundButton(symbol: geschickt ? "checkmark" : "arrow.down.to.line",
                                active: geschickt) {
                        Trace.write("Hintergrund gedrückt [\(model.key.prefix(10))] "
                                    + "läuft=\(model.runningTool ?? "nichts")")
                        geschickt = true
                        Task {
                            await model.press("background")
                            try? await Task.sleep(for: .seconds(1.6))
                            geschickt = false
                        }
                    }
                    .help("Den laufenden Befehl im Hintergrund weiterlaufen lassen (Ctrl+B)")
                }
                // Every slash command, explained - and picked into the input.
                RoundButton(symbol: "slash.circle") { showCommands = true }
                    .popover(isPresented: $showCommands, arrowEdge: .top) {
                        CommandsList(commands: model.commands) { c in
                            command = c
                            showCommands = false
                        }
                        .padding(18)
                        .frame(width: 460, height: 560)
                        .task { await model.loadCommands() }
                    }
                if let c = command {
                    CommandChip(command: c) { command = nil }.padding(.vertical, 6)
                }
                if dictation.listening {
                    // While you speak the newest words come in at the end and
                    // stay in view - a text field keeps showing its first lines.
                    ScrollView(showsIndicators: false) {
                        Text(text.isEmpty ? "Ich höre zu …" : text)
                            .font(Face.ui(15))
                            .foregroundStyle(text.isEmpty ? Palette.hint : Palette.text)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { spokenHeight = $0 }
                    }
                    .frame(height: min(max(spokenHeight, 19), 160))
                    .defaultScrollAnchor(.bottom, for: .initialOffset)
                    .defaultScrollAnchor(.bottom, for: .sizeChanges)
                    .padding(.vertical, 9)
                } else {
                    TextField("", text: $text,
                              prompt: Text(command?.prompt ?? (model.isTerminal ? "Nachricht an die Terminal-Sitzung …" : "Auftrag …"))
                                  .foregroundStyle(Palette.hint),
                              axis: .vertical)
                        .textFieldStyle(.plain)
                        .font(Face.ui(15))
                        .foregroundStyle(Palette.text)
                        .lineLimit(1...8)
                        .onSubmit(send)
                        .padding(.vertical, 9)
                }
                if dictation.available {
                    RoundButton(symbol: dictation.listening ? "waveform" : "mic", active: dictation.listening) {
                        if dictation.listening {
                            dictation.stop()
                        } else {
                            base = text.trimmingCharacters(in: .whitespacesAndNewlines)
                            Task { await dictation.start() }
                        }
                    }
                }
                RoundButton(symbol: "arrow.up", brass: true, action: send)
            }
        }
        .padding(.leading, 8).padding(.trailing, 8).padding(.vertical, 8)
        .inked(shape, Color(hex: 0xEFECE5, opacity: 0.035))
        .gilt(shape)
        .frame(maxWidth: 760)
        .onChange(of: text) { _, now in
            if now.hasPrefix("/") { Task { await model.loadCommands() } }
        }
        // What is said goes after what was typed, as it is recognised.
        .onChange(of: dictation.partial) { _, spoken in
            if dictation.listening { text = [base, spoken].filter { !$0.isEmpty }.joined(separator: " ") }
        }
        // Cmd+V with a picture on the clipboard: the same as dropping it.
        .onPasteCommand(of: [.fileURL, .image, .pdf]) { _ in
            attachments += Attachment.read(from: .general)
        }
        .fileImporter(isPresented: $pickFiles, allowedContentTypes: [.item], allowsMultipleSelection: true) { result in
            if case .success(let urls) = result {
                attachments += urls.compactMap(Attachment.init(file:))
            }
        }
    }

    private func send() {
        // Cancelled, not stopped: a late result would refill the field.
        dictation.cancel()
        let typed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let t = command.map { $0.line(with: typed) } ?? typed
        guard !t.isEmpty || !attachments.isEmpty else { return }
        let files = attachments
        text = ""
        attachments = []
        command = nil
        Task { _ = await model.send(t, attachments: files) }
    }
}

/// Another computer's address, as `make token` prints it there.
struct AddMachine: View {
    @Environment(AppModel.self) private var app
    @Binding var shown: Bool
    @State private var text = ""
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Rechner hinzufügen").font(Face.ui(14)).foregroundStyle(Palette.text)
            Text("Auf dem anderen Rechner zeigt make token im iris-Ordner seine Adresse.")
                .font(Face.ui(11.5)).foregroundStyle(Palette.meta)
            TextField("http://…:8780/?token=…", text: $text)
                .textFieldStyle(.roundedBorder)
                .font(Face.mono(11))
                .onSubmit(add)
            if let error {
                Text(error).font(Face.mono(10)).foregroundStyle(Palette.clayText)
            }
            HStack {
                Spacer()
                Button("Hinzufügen", action: add)
            }
        }
        .padding(16)
        .frame(width: 380)
    }

    private func add() {
        error = app.connect(text.trimmingCharacters(in: .whitespacesAndNewlines))
        if error == nil {
            shown = false
            Task { await app.refresh() }
        }
    }
}

/// What a handover would mean, before anything happens. This one only looks:
/// the repository is the transport, so it says whether there is one, which
/// account owns it, what is still lying around, and how much history would
/// have to travel. Nothing here acts - committing and pushing are a separate,
/// answered decision.
struct UebergabeBlatt: View {
    @Environment(\.dismiss) private var dismiss
    let model: SessionModel

    // Der Inhalt liegt in shared/Uebergabe.swift: dasselbe Blatt braucht das
    // Telefon auch, und dort gab es bisher gar keine Uebergabe. Hier bleibt
    // nur der Rahmen - feste Groesse und ein eigener Schliessknopf, die auf
    // dem Mac dazugehoeren und auf dem Telefon das System uebernimmt.
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ScreenHeader(eyebrow: "Sitzung mitnehmen", title: model.title,
                         subtitle: Fmt.path(model.path))
            UebergabeInhalt(model: model)
        }
        .padding(24)
        .frame(width: 460, height: 460)
        .background(Room())
        .overlay(alignment: .topTrailing) {
            Button { dismiss() } label: {
                Image(systemName: "xmark").font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Palette.meta).padding(10)
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.cancelAction)
        }
    }
}
