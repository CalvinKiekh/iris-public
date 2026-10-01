import PhotosUI
import SwiftUI
import UIKit

// MARK: - Session

/// One conversation: header on top, the history in the middle, and at the
/// bottom whatever waits for you plus the input.
/// Der Entwurf in der Eingabe - in einem eigenen Objekt, nicht als @State
/// der Ansicht, die auch den Verlauf zeichnet.
///
/// Vorher stand `text` als @State in `SessionView`. Jeder Tastendruck warf
/// damit deren Rumpf neu, also auch die ScrollView mit allen Zuegen, und die
/// gespeicherte Scrollposition wurde dabei erneut angelegt - der Verlauf
/// sprang beim Tippen hin und her. Mit @Observable wird nur neu gezeichnet,
/// wer `text` wirklich liest: die Eingabe. Wer nur hineinschreibt (das Blatt
/// mit den Bausteinen) oder das Objekt weiterreicht, bleibt unberuehrt.
@Observable final class Draft {
    var text = ""
}

struct SessionView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var phase
    let model: SessionModel
    @State private var draft = Draft()
    @State private var position = ScrollPosition(edge: .bottom)
    @State private var atBottom = true
    @State private var unread = 0
    /// How many turns there were when you left the bottom - what came since
    /// is what "neu" counts. Updates to a turn already there are not new.
    @State private var seenTurns = 0
    /// Only the last turns are drawn; "Frühere Nachrichten" adds more. With
    /// thousands of rows the list can only guess their heights, and every
    /// jump to the end landed somewhere else - the view jumped about and
    /// "unten" flickered on every card.
    @State private var visible = 150
    /// Set by your own finger or trackpad only. The flicker while rows get
    /// measured no longer counts anything as new.
    @State private var scrolledUp = false
    @State private var dragging = false
    @State private var showModes = false
    @State private var showShortcuts = false
    @State private var showCommands = false
    @State private var showScreen = false
    @State private var command: SlashCommand?

    var body: some View {
        ZStack(alignment: .top) {
            Room()
            VStack(spacing: 0) {
                SessionHeader(model: model, showModes: $showModes, showCommands: $showCommands, back: { dismiss() })
                    .padding(.horizontal, 22)
                    .padding(.top, 6)
                    .padding(.bottom, 8)
                conversation
            }
            if let notice = model.notice {
                NoticeToast(text: notice) { model.notice = nil }
                    .padding(.top, 4)
                    .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .animation(.easeOut(duration: 0.25), value: model.notice)
        .toolbar(.hidden, for: .navigationBar)
        .onAppear {
            Notifications.visibleSession = model.key
            model.start()
        }
        .onDisappear {
            if Notifications.visibleSession == model.key { Notifications.visibleSession = nil }
            model.stop()
        }
        // In the background iOS would cut the stream anyway. Closing it
        // tells the bridge nobody is looking - which is what lets it push.
        .onChange(of: phase) { _, now in
            if now == .active { model.start() } else if now == .background { model.stop() }
        }
        .sheet(isPresented: $showModes) { ModeSheet(model: model) }
        .sheet(isPresented: $showShortcuts) { ShortcutsSheet { draft.text = $0 } }
        .sheet(isPresented: $showCommands) {
            CommandsSheet(model: model, openScreen: model.isTerminal && model.info?.typable == true ? {
                // One sheet after the other: the list goes, then the screen comes.
                showCommands = false
                Task {
                    try? await Task.sleep(for: .milliseconds(450))
                    showScreen = true
                }
            } : nil) { command = $0 }
        }
        .sheet(isPresented: $showScreen) { ScreenSheet(model: model) }
    }

    private var conversation: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 22) {
                if model.turns.count > visible {
                    Button {
                        visible += 150
                    } label: {
                        Text("Frühere Nachrichten (\(model.turns.count - visible))")
                            .font(Face.mono(10.5))
                            .foregroundStyle(Palette.meta)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.plain)
                }
                let drawn = model.drawn(last: visible)
                ForEach(drawn.settled) { TurnView(turn: $0).environment(\.sessionKey, model.key) }
                if model.busy && model.connected && !model.ended {
                    WorkingRow(model: model).transition(.opacity)
                }
                ForEach(drawn.waiting) { TurnView(turn: $0).environment(\.sessionKey, model.key) }
            }
            .padding(.leading, 22)
            .padding(.trailing, 20)
            .padding(.top, 22)
            .padding(.bottom, 14)
        }
        .scrollIndicators(.hidden)
        .scrollDismissesKeyboard(.interactively)
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
        // Whoever scrolled up is reading. Nothing new pulls them down - it
        // announces itself instead, and the jump happens on a tap.
        .onChange(of: model.revision) {
            if model.settling {
                position.scrollTo(edge: .bottom)
                seenTurns = model.turns.count
            } else if !scrolledUp {
                withAnimation(.easeOut(duration: 0.25)) { position.scrollTo(edge: .bottom) }
                seenTurns = model.turns.count
            } else {
                unread = max(0, model.turns.count - seenTurns)
                model.trace("nicht unten: neu \(unread) (Züge \(model.turns.count), gesehen \(seenTurns))")
            }
        }
        .onChange(of: model.settling) { _, settling in
            if !settling {
                position.scrollTo(edge: .bottom)
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
        // What runs off the top is the conversation from before: it does not
        // break off, it fades.
        .mask {
            VStack(spacing: 0) {
                LinearGradient(colors: [.clear, .black], startPoint: .top, endPoint: .bottom).frame(height: 26)
                Rectangle()
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            // A growing input - dictation, a long text - pushes the end of
            // the conversation up with it instead of covering it.
            dock.onGeometryChange(for: CGFloat.self) { $0.size.height } action: { _, _ in
                if !scrolledUp { position.scrollTo(edge: .bottom) }
            }
        }
    }

    /// What waits for you is pinned above the input - it stays in reach
    /// however far back you have scrolled.
    private var dock: some View {
        VStack(spacing: 12) {
            if unread > 0 {
                UnreadPill(count: unread) {
                    scrolledUp = false
                    unread = 0
                    seenTurns = model.turns.count
                    withAnimation(.easeOut(duration: 0.3)) { position.scrollTo(edge: .bottom) }
                }
            }
            if model.screenView && model.isTerminal {
                ViewBanner(model: model, show: { showScreen = true })
            }
            if let d = model.decisions.first {
                Group {
                    if d.isQuestion { ChoiceCard(decision: d, model: model) }
                    else { ApprovalCard(decision: d, model: model) }
                }
                .padding(.leading, 21)
                .id(d.id)
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
            if !model.ended {
                Composer(model: model, draft: draft, command: $command, openScreen: { showScreen = true }) {
                    showShortcuts = true
                }
            }
        }
        .padding(.horizontal, 22)
        .padding(.top, 6)
        .padding(.bottom, 6)
        .animation(.spring(duration: 0.35), value: model.decisions.first?.id)
    }
}

// MARK: - Header

struct SessionHeader: View {
    @Environment(AppModel.self) private var app
    let model: SessionModel
    @Binding var showModes: Bool
    @Binding var showCommands: Bool
    let back: () -> Void
    @State private var showBackground = false
    @State private var showPages = false
    @State private var renaming = false
    @State private var newName = ""
    @State private var zeigeUebergabe = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ScreenHeader(eyebrow: model.isTerminal ? "Terminal" : "Sitzung", title: model.title,
                         subtitle: model.path, back: back, compact: true) {
                // The mode is a handle, not a menu item: it decides what runs
                // without asking, so it sits where you look. A terminal
                // session gets it too when iris can reach its tab - the bridge
                // switches with Shift+Tab there, as you would at the Mac.
                if !model.ended {
                    HStack(spacing: 8) {
                        // Every slash command, explained - and picked into the input.
                        Button { showCommands = true } label: {
                            Text("/")
                                .font(Face.mono(15))
                                .foregroundStyle(Palette.brass)
                                .frame(width: 40, height: 40)
                                .background(Circle().fill(Palette.brass.opacity(0.1)))
                                .overlay(Circle().strokeBorder(Palette.brass.opacity(0.2), lineWidth: 1))
                                .contentShape(Circle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Befehle")
                        .accessibilityIdentifier("befehle")
                        if (!model.isTerminal || model.info?.typable == true) && !model.mode.isEmpty {
                            ModeChip(label: model.mode, plan: model.mode == "plan") { showModes = true }
                        }
                    }
                    .padding(.top, 18)
                }
            }
            // Hold the title to give the session a name of its own.
            .contextMenu {
                Button("Umbenennen", systemImage: "pencil") {
                    newName = model.info?.title ?? ""
                    renaming = true
                }
            }
            .alert("Sitzung umbenennen", isPresented: $renaming) {
                TextField("Name", text: $newName)
                Button("Speichern") { Task { await model.rename(newName) } }
                Button("Abbrechen", role: .cancel) {}
            } message: {
                Text("Leer lassen stellt den automatischen Titel wieder her.")
            }
            // The state, and what opens a list, in the line "anhalten" ends;
            // the numbers below it.
            HStack(alignment: .top, spacing: 12) {
                FactsRow(model: model, services: nil, status: true, counts: false,
                         showBackground: $showBackground, showPages: $showPages)
                StopButton(model: model).padding(.top, 4)
            }
            .padding(.top, 10)
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                FactsRow(model: model, services: app.services, toggles: false,
                         showBackground: $showBackground, showPages: $showPages)
                // Only where the repository could carry the work across: the
                // button has no meaning without a remote to clone from. Same
                // rule as on the Mac, and the sheet behind it is the same
                // view - the phone is what you hold when the wish comes up.
                if model.handover?.github == true {
                    Button("mitnehmen") { zeigeUebergabe = true }
                        .font(Face.mono(10.5))
                        .foregroundStyle(Palette.brass)
                        .buttonStyle(.plain)
                        .fixedSize()
                }
            }
            .padding(.top, 8)
            .task(id: model.key) { await model.loadHandover() }
            .sheet(isPresented: $zeigeUebergabe) { UebergabeSheet(model: model) }
            if showBackground && !model.background.isEmpty {
                BackgroundList(tasks: model.background)
                    .padding(.top, 10)
                    .transition(.opacity)
            }
            if showPages && !model.artifacts.isEmpty {
                PagesList(pages: model.artifacts)
                    .padding(.top, 10)
                    .transition(.opacity)
            }
        }
    }
}

/// Was diese Sitzung braucht, um auf einem anderen Rechner weiterzulaufen.
///
/// The sheet existed on the Mac only, and the phone is the thing actually in
/// hand when the wish to move a session comes up. The content is shared
/// (shared/Uebergabe.swift); only the frame is the phone's - a sheet the
/// system dismisses, scrolling, and rows with a little more room.
struct UebergabeSheet: View {
    let model: SessionModel

    var body: some View {
        ZStack(alignment: .top) {
            Room()
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Eyebrow("Sitzung mitnehmen").padding(.bottom, 4)
                    Text(model.title).font(Face.ui(19)).foregroundStyle(Palette.text)
                    Text(model.path).font(Face.mono(10.5)).foregroundStyle(Palette.meta)
                        .padding(.top, 2)
                    UebergabeInhalt(model: model, kompakt: false)
                }
                .padding(.horizontal, 22)
                .padding(.top, 24)
                .padding(.bottom, 40)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .presentationDragIndicator(.visible)
    }
}

/// The input: text, dictation, photos and files.
struct Composer: View {
    let model: SessionModel
    @Bindable var draft: Draft
    @Binding var command: SlashCommand?
    /// After a command that opens a view in the terminal: show its screen.
    var openScreen: () -> Void = {}
    let openShortcuts: () -> Void
    @State private var dictation = Dictation()
    @State private var base = ""
    @State private var spokenHeight: CGFloat = 0
    @State private var sending = false
    @State private var attachments: [Attachment] = []
    @State private var pickPhotos = false
    @State private var pickFiles = false
    @State private var photoItems: [PhotosPickerItem] = []

    private var trimmed: String { draft.text.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var canSend: Bool { !trimmed.isEmpty || !attachments.isEmpty || command != nil }

    private var placeholder: String {
        if let c = command { return c.prompt }
        if model.decisions.first?.isQuestion == true { return "Oder etwas anderes …" }
        return model.isTerminal ? "Nachricht an die Terminal-Sitzung …" : "Auftrag …"
    }

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 26, style: .continuous)
        VStack(alignment: .leading, spacing: 8) {
            if command == nil {
                let found = model.suggestions(for: draft.text)
                if !found.isEmpty {
                    CommandSuggestions(items: found) { c in
                        command = c
                        draft.text = ""
                    }
                }
            }
            if !attachments.isEmpty {
                AttachmentStrip(attachments: $attachments).padding(.leading, 10)
            }
            pill(shape)
        }
        .photosPicker(isPresented: $pickPhotos, selection: $photoItems, maxSelectionCount: 6, matching: .images)
        .fileImporter(isPresented: $pickFiles, allowedContentTypes: [.item], allowsMultipleSelection: true) { result in
            if case .success(let urls) = result {
                attachments += urls.compactMap(Attachment.init(file:))
            }
        }
        .onAppear {
            #if DEBUG
            // UI tests cannot drive the system photo picker reliably; this
            // puts a made-up image where a picked one would be. From there on
            // it is the same path: upload, attach, send.
            if ProcessInfo.processInfo.environment["IRIS_ATTACH"] == "probe", attachments.isEmpty {
                attachments = [Attachment.probe()]
            }
            #endif
        }
        .onChange(of: photoItems) { _, items in
            guard !items.isEmpty else { return }
            Task {
                for item in items {
                    if let a = await Attachment(photo: item) { attachments.append(a) }
                }
                photoItems = []
            }
        }
    }

    private func pill(_ shape: RoundedRectangle) -> some View {
        HStack(alignment: .bottom, spacing: 6) {
            // Photo or file, the way the Claude app's "+" does it.
            Menu {
                Button("Foto", systemImage: "photo") { pickPhotos = true }
                Button("Datei", systemImage: "doc") { pickFiles = true }
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 14, weight: .light))
                    .foregroundStyle(Color(hex: 0x9A9287))
                    .frame(width: 36, height: 36)
                    .background(Circle().fill(Color(hex: 0xEFECE5, opacity: 0.06)))
                    .padding(4)
                    .contentShape(Circle())
            }
            .accessibilityLabel("Anhängen")
            .accessibilityIdentifier("anhaengen")
            if let c = command {
                CommandChip(command: c) { command = nil }.padding(.vertical, 7)
            }
            if dictation.listening {
                // While you speak the newest words come in at the end and
                // stay in view - a text field keeps showing its first lines.
                ScrollView(showsIndicators: false) {
                    Text(draft.text.isEmpty ? "Ich höre zu …" : draft.text)
                        .font(Face.ui(14.5))
                        .foregroundStyle(draft.text.isEmpty ? Palette.hint : Palette.text)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { spokenHeight = $0 }
                }
                .frame(height: min(max(spokenHeight, 18), 118))
                .defaultScrollAnchor(.bottom, for: .initialOffset)
                .defaultScrollAnchor(.bottom, for: .sizeChanges)
                .padding(.vertical, 13)
                .accessibilityIdentifier("gesprochen")
            } else {
                TextField("", text: $draft.text, prompt: Text(placeholder).foregroundStyle(Palette.hint), axis: .vertical)
                    .font(Face.ui(14.5))
                    .foregroundStyle(Palette.text)
                    .tint(Palette.brass)
                    .lineLimit(1...6)
                    .padding(.vertical, 13)
                    .accessibilityIdentifier("eingabe")
            }
            if dictation.available {
                RoundButton(symbol: dictation.listening ? "waveform" : "mic", active: dictation.listening) {
                    toggleDictation()
                }
                .accessibilityIdentifier("diktat")
            }
            // With nothing to send, the send slot opens the canned prompts -
            // sending nothing means nothing anyway.
            if !canSend {
                RoundButton(symbol: "list.bullet", action: openShortcuts)
            } else {
                RoundButton(symbol: "arrow.up", brass: true, action: submit)
                    .disabled(sending)
                    .accessibilityIdentifier("senden")
            }
        }
        .padding(.leading, 4)
        .padding(.trailing, 4)
        .padding(.vertical, 4)
        .inked(shape, Color(hex: 0xEFECE5, opacity: 0.035))
        .gilt(shape)
        .onChange(of: dictation.partial) { _, spoken in
            draft.text = [base, spoken].filter { !$0.isEmpty }.joined(separator: " ")
        }
        .onChange(of: draft.text) { _, now in
            if now.hasPrefix("/") { Task { await model.loadCommands() } }
        }
    }

    private func toggleDictation() {
        if dictation.listening {
            dictation.stop()
        } else {
            base = trimmed
            Task { await dictation.start() }
        }
    }

    private func submit() {
        let t = command.map { $0.line(with: trimmed) } ?? trimmed
        // Picked from the list, or typed as text - "/status" opens its view either way.
        let first = t.split(separator: " ").first.map(String.init) ?? ""
        let opensView = command?.view == true
            || (first.hasPrefix("/") && model.commands.contains { "/" + $0.name == first && $0.view })
        guard canSend else { return }
        // Cancelled, not stopped: the text sent is what stands in the field.
        dictation.cancel()
        sending = true
        let files = attachments
        Task {
            if await model.send(t, attachments: files) {
                draft.text = ""
                attachments = []
                command = nil
                if opensView { openScreen() }
            }
            sending = false
        }
    }
}

struct ModeSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    let model: SessionModel

    /// A terminal session offers what Shift+Tab steps through at the Mac -
    /// "manual" there is what the hooks call "default".
    private var choices: [Mode] {
        guard model.isTerminal else { return app.modes }
        let cycle = ["default", "acceptEdits", "plan", "auto"]
        return cycle.compactMap { id in app.modes.first { $0.id == id } }
    }

    var body: some View {
        ZStack(alignment: .top) {
            Room()
            VStack(alignment: .leading, spacing: 0) {
                Eyebrow("Modus").padding(.bottom, 12)
                ScrollView {
                    VStack(spacing: 0) {
                        ForEach(choices) { m in
                            Button {
                                Task {
                                    await model.setMode(m.id)
                                    dismiss()
                                }
                            } label: {
                                HStack(spacing: 12) {
                                    Tick(on: m.id == model.mode)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(m.label)
                                            .font(Face.ui(15, m.id == model.mode ? .regular : .light))
                                            .foregroundStyle(Palette.text)
                                        Text(m.id).font(Face.mono(10.5)).foregroundStyle(Palette.meta)
                                    }
                                    Spacer()
                                }
                                .padding(.vertical, 11)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            Hairline()
                        }
                    }
                }
                .scrollIndicators(.hidden)
            }
            .padding(.horizontal, 26)
            .padding(.top, 28)
        }
        .presentationDetents([.medium, .large])
        .presentationBackground(Palette.ground)
        .presentationCornerRadius(32)
        .presentationDragIndicator(.visible)
    }
}

/// The canned prompts, one tap each - on the road, typing is the slow way.
/// Every slash command, to read up on and to pick into the input.
struct CommandsSheet: View {
    let model: SessionModel
    var openScreen: (() -> Void)? = nil
    let pick: (SlashCommand) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack(alignment: .top) {
            Room()
            VStack(alignment: .leading, spacing: 12) {
                Eyebrow("Befehle")
                CommandsList(commands: model.commands, showScreen: openScreen) { c in
                    pick(c)
                    dismiss()
                }
            }
            .padding(.horizontal, 22)
            .padding(.top, 26)
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .task { await model.loadCommands() }
    }
}

/// The terminal's screen, for a view a command opened there.
struct ScreenSheet: View {
    let model: SessionModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Room()
            TerminalScreen(model: model)
                .padding(.horizontal, 18)
                .padding(.top, 26)
                .padding(.bottom, 14)
            // The screen scrolls both ways and takes the swipe that would
            // close the sheet - so it gets a button of its own.
            Button("Fertig") { dismiss() }
                .font(Face.ui(14))
                .foregroundStyle(Palette.brass)
                .buttonStyle(.plain)
                .padding(.top, 22)
                .padding(.trailing, 22)
                .accessibilityIdentifier("bildschirm-fertig")
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        // Closed with Esc - here or at the Mac: the sheet goes with the view.
        .onChange(of: model.screenView) { was, now in
            if was && !now { dismiss() }
        }
    }
}

struct ShortcutsSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    let pick: (String) -> Void

    var body: some View {
        ZStack(alignment: .top) {
            Room()
            VStack(alignment: .leading, spacing: 0) {
                Eyebrow("Standard-Abfragen").padding(.bottom, 12)
                ScrollView {
                    VStack(spacing: 0) {
                        ForEach(app.shortcuts) { s in
                            Button {
                                pick(s.text)
                                dismiss()
                            } label: {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(s.label).font(Face.ui(15)).foregroundStyle(Palette.text)
                                    Text(s.text).font(Face.ui(11.5)).foregroundStyle(Palette.meta).lineLimit(1)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.vertical, 11)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            Hairline()
                        }
                    }
                }
                .scrollIndicators(.hidden)
            }
            .padding(.horizontal, 26)
            .padding(.top, 28)
        }
        .presentationDetents([.medium, .large])
        .presentationBackground(Palette.ground)
        .presentationCornerRadius(32)
        .presentationDragIndicator(.visible)
    }
}
