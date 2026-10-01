import SwiftUI
import UIKit

@main
struct IrisApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @State private var app = AppModel.shared

    init() {
        // The watch asks through this app - it listens from the first moment.
        WatchRelay.shared.start()
    }

    var body: some Scene {
        WindowGroup {
            RootView().environment(app)
        }
    }
}

struct RootView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        @Bindable var app = app
        Group {
            if app.bridge == nil {
                ConnectView()
            } else {
                NavigationStack(path: $app.path) {
                    HomeView()
                        .navigationDestination(for: Route.self) { route in
                            switch route {
                            case .project(let p): ProjectView(project: p)
                            case .session(let key): SessionView(model: app.model(for: key))
                            case .services: ServicesView()
                            }
                        }
                }
            }
        }
        // Der Assistent liegt ueber allem, auf jedem Bildschirm. Er war am
        // 25.09. einen Abend lang draussen, nachdem zwei Fehler die App
        // lahmgelegt hatten: Gesten hinter `.position()` lagen ueber dem
        // ganzen Fenster, und das Aufklappen legte jedes Mal eine echte
        // Sitzung an. Beides ist behoben und im Simulator geprueft, bevor er
        // wieder aufs Telefon ging.
        .overlay { VorarbeiterOrb() }
        .preferredColorScheme(.dark)
        .tint(Palette.brass)
        // Once connected, ask for notifications and hand the bridge this
        // phone's address - on every launch, see Notifications.start.
        .task(id: app.bridge) {
            if app.bridge != nil { await Notifications.start() }
        }
    }
}

// The screens draw their own header, so the navigation bar is hidden - which
// switches off the swipe back. This hands it back.
extension UINavigationController: @retroactive UIGestureRecognizerDelegate {
    override open func viewDidLoad() {
        super.viewDidLoad()
        interactivePopGestureRecognizer?.delegate = self
    }

    public func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        viewControllers.count > 1
    }
}

// MARK: - Shared pieces of a screen
// MARK: - Connect

struct ConnectView: View {
    @Environment(AppModel.self) private var app
    @State private var text = ""
    @State private var error: String?
    /// A further computer, from the list on the home screen - not the first.
    var adding = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            Room()
            VStack(alignment: .leading, spacing: 0) {
                Spacer()
                Eyebrow("iris")
                Text(adding ? "Rechner hinzufügen" : "Verbinden")
                    .font(Face.display(40))
                    .foregroundStyle(Palette.text)
                    .padding(.top, 4)
                Text(adding
                     ? "Auf dem anderen Rechner zeigt **make token** im iris-Ordner seine Adresse. Jeder Rechner hat seinen eigenen Zugangsschlüssel."
                     : "Die Adresse zeigt am Mac **make token** im Ordner ~/Documents/iris. Sie trägt den Zugangsschlüssel mit – einmal einfügen genügt.")
                    .font(Face.ui(15))
                    .foregroundStyle(Palette.soft)
                    .lineSpacing(4)
                    .padding(.top, 14)
                let shape = RoundedRectangle(cornerRadius: 26, style: .continuous)
                HStack(spacing: 8) {
                    TextField("", text: $text,
                              prompt: Text(verbatim: "http://…:8780/?token=…").foregroundStyle(Palette.hint))
                        .font(Face.mono(12.5))
                        .foregroundStyle(Palette.text)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .submitLabel(.go)
                        .onSubmit(connect)
                        .padding(.vertical, 9)
                    RoundButton(symbol: "arrow.right", brass: true, action: connect)
                }
                .padding(.leading, 22).padding(.trailing, 8).padding(.vertical, 8)
                .inked(shape, Color(hex: 0xEFECE5, opacity: 0.035))
                .gilt(shape)
                .padding(.top, 26)
                if let error {
                    Text(error).font(Face.mono(10.5)).foregroundStyle(Palette.clayText).padding(.top, 12)
                }
                Spacer()
                Spacer()
            }
            .padding(.horizontal, 26)
        }
    }

    private func connect() {
        error = app.connect(text)
        if error == nil {
            // The new computer learns where to send notifications, too.
            Task { await Notifications.registerAgain() }
            if adding { dismiss() }
        }
    }
}

// MARK: - Home

struct HomeView: View {
    @Environment(AppModel.self) private var app
    @State private var openedFromEnvironment = false
    @State private var addingMachine = false
    @State private var newSession = false
    @State private var renameTarget: SessionInfo?
    @State private var newName = ""
    /// Sessions (per computer) or the resident (one for all).
    @AppStorage("iris.layer") private var layer = "sitzungen"
    private let resident = ResidentModel.shared

    var body: some View {
        ZStack {
            Room()
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ScreenHeader(eyebrow: "iris", title: layer == "bewohner" ? "Bewohner" : "Sitzungen")
                    if resident.machine != nil || layer == "bewohner" {
                        LayerSwitch(layer: $layer).padding(.top, 10)
                    }
                    if layer == "bewohner" {
                        ResidentPanel(model: resident)
                    } else {
                    // Which computer's sessions these are - and the others, one tap away.
                    MachineRow { addingMachine = true }.padding(.top, 12)
                    Button { newSession = true } label: {
                        HStack(spacing: 10) {
                            Image(systemName: "plus").font(.system(size: 12, weight: .light)).foregroundStyle(Palette.brass)
                            Text("Neue Sitzung").font(Face.ui(15)).foregroundStyle(Palette.text)
                            Spacer()
                        }
                        .padding(.vertical, 12)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("neue-sitzung")
                    .padding(.top, 14)
                    if let q = app.quota {
                        QuotaLine(quota: q).padding(.top, 14)
                    }
                    AwayRow().padding(.top, 24)
                    UpdateRow().padding(.top, 12)
                    NavigationLink(value: Route.services) { ServicesEntry(summary: app.services) }
                        .buttonStyle(.plain)
                        .padding(.top, 10)
                    if let problem = app.pushProblem {
                        Text("Mitteilungen gehen nicht: \(problem)")
                            .font(Face.mono(10))
                            .foregroundStyle(Palette.clayText)
                            .padding(.top, 6)
                    }
                    let live = app.sessions.filter { !$0.exited }
                    // Eine leere Liste ist zweideutig: kein Rechner arbeitet,
                    // oder die Bruecke sagt nichts. Der Unterschied entscheidet,
                    // ob man wartet oder handelt - und stand bisher nirgends.
                    // Ein halber Abend ging dafuer drauf (Calvin, 25.09.).
                    if live.isEmpty {
                        SectionLabel("Laufend")
                        VStack(alignment: .leading, spacing: 3) {
                            Text(app.problem ?? "Keine Sitzung auf diesem Rechner.")
                                .font(Face.ui(12.5))
                                .foregroundStyle(app.problem == nil ? Palette.meta : Palette.clayText)
                            // Die harten Tatsachen daneben, solange die Ursache
                            // nicht gefunden ist: welche Adresse gefragt wurde
                            // und wann zuletzt etwas ankam. Ohne das raet man.
                            Text(app.diagnose)
                                .font(Face.mono(9.5))
                                .foregroundStyle(Palette.faint)
                        }
                        .padding(.vertical, 6)
                    }
                    if !live.isEmpty {
                        SectionLabel("Laufend")
                        ForEach(live) { s in
                            NavigationLink(value: Route.session(s.key)) { SessionRow(info: s) }
                                .buttonStyle(.plain)
                                .contextMenu {
                                    Button("Umbenennen", systemImage: "pencil") {
                                        newName = s.title
                                        renameTarget = s
                                    }
                                }
                            if s.key != live.last?.key { Hairline() }
                        }
                    }
                    SectionLabel("Projekte")
                    ForEach(app.projects) { p in
                        NavigationLink(value: Route.project(p)) { ProjectRow(project: p) }
                            .buttonStyle(.plain)
                        if p.id != app.projects.last?.id { Hairline() }
                    }
                    if let problem = app.problem {
                        Text(problem).font(Face.mono(10.5)).foregroundStyle(Palette.clayText).padding(.top, 20)
                    }
                    Button(app.machines.count > 1 ? "Diesen Rechner entfernen" : "Verbindung trennen") { app.forget() }
                        .font(Face.ui(12.5))
                        .foregroundStyle(Palette.faint)
                        .buttonStyle(.plain)
                        .padding(.top, 40)
                    }
                }
                .padding(.horizontal, 22).padding(.top, 10).padding(.bottom, 40)
            }
            .scrollIndicators(.hidden)
            .refreshable { await app.refresh() }
            .safeAreaInset(edge: .bottom) {
                // Talking to the resident is never a scroll away.
                if layer == "bewohner" && resident.state != nil {
                    ResidentTalkBar(model: resident)
                }
            }
        }
        .toolbar(.hidden, for: .navigationBar)
        .sheet(isPresented: $addingMachine) { ConnectView(adding: true) }
        .sheet(isPresented: $newSession) { NewSessionSheet() }
        .alert("Sitzung umbenennen", isPresented: Binding(get: { renameTarget != nil }, set: { if !$0 { renameTarget = nil } })) {
                TextField("Name", text: $newName)
                Button("Speichern") { if let t = renameTarget { Task { await app.rename(session: t.key, to: newName) } } }
                Button("Abbrechen", role: .cancel) {}
            } message: {
                Text("Leer lassen stellt den automatischen Titel wieder her.")
            }
        .task {
            // Wo der Bewohner wohnt, nebenher: diese Suche darf das Nachladen
            // nie aufhalten. Stand sie davor, blockierte ein einziger toter
            // Rechner die ganze Uebersicht.
            if resident.machine == nil {
                Task { await resident.locate() }
            }
            // Kein zweiter Nachlade-Kreislauf mehr: der laeuft seit dem
            // 25.09. am Modell. Zwei Schleifen bedeuteten doppelte Abrufe -
            // und, schlimmer, die hier starb mit der Ansicht. Verschwand sie
            // kurz, wurde die laufende Anfrage abgebrochen, und in der App
            // stand „cancelled", obwohl der Bruecke nichts fehlte.
            openFromEnvironment()
        }
    }

    /// DEBUG: IRIS_OPEN=last (or part of a key or title) opens a session on
    /// launch, so a screenshot of the conversation needs no tapping.
    private func openFromEnvironment() {
        #if DEBUG
        guard !openedFromEnvironment, let want = ProcessInfo.processInfo.environment["IRIS_OPEN"],
              !want.isEmpty else { return }
        openedFromEnvironment = true
        if want == "services" {
            app.path.append(.services)
            return
        }
        let live = app.sessions.filter { !$0.exited }.sorted { $0.lastActive > $1.lastActive }
        // contains, nicht hasPrefix: jeder Schluessel faengt mit "t-" an, also
        // trifft ein Stueck aus der Mitte - was man beim Abtippen erwischt -
        // sonst nie, obwohl "part of a key" genau das verspricht.
        let pick = want == "last" ? live.first
            : live.first { $0.key.contains(want) || $0.title.localizedCaseInsensitiveContains(want) }
        if let pick { app.path.append(.session(pick.key)) }
        #endif
    }
}
/// Sessions or the resident - two words, the chosen one in brass.
struct LayerSwitch: View {
    @Binding var layer: String

    var body: some View {
        HStack(spacing: 18) {
            item("Sitzungen", "sitzungen")
            item("Bewohner", "bewohner")
            Spacer()
        }
    }

    private func item(_ title: String, _ value: String) -> some View {
        Button {
            withAnimation(.easeOut(duration: 0.18)) { layer = value }
        } label: {
            VStack(alignment: .leading, spacing: 5) {
                Text(title).font(Face.ui(14, layer == value ? .regular : .light))
                    .foregroundStyle(layer == value ? Palette.text : Palette.meta)
                Rectangle().fill(layer == value ? Palette.brass : Color.clear).frame(height: 1)
            }
            .fixedSize()
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("ebene-" + value)
    }
}

/// Starts a session where you pick - and goes straight into it.
struct NewSessionSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var starting = false

    var body: some View {
        ZStack(alignment: .top) {
            Room()
            VStack(alignment: .leading, spacing: 12) {
                Eyebrow("Neue Sitzung")
                NewSessionList { cwd in
                    guard !starting else { return }
                    starting = true
                    Task {
                        if let key = await app.start(cwd: cwd) {
                            dismiss()
                            try? await Task.sleep(for: .milliseconds(350))
                            app.path.append(.session(key))
                        }
                        starting = false
                    }
                }
            }
            .padding(.horizontal, 22)
            .padding(.top, 26)
            .padding(.bottom, 14)
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }
}

// MARK: - Project

struct ProjectView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    let project: Project
    @State private var rows: [Conversation] = []
    @State private var loaded = false
    @State private var starting = false
    @State private var forkCandidate: Conversation?

    var body: some View {
        ZStack {
            Room()
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ScreenHeader(eyebrow: "Projekt", title: project.label,
                                 subtitle: Fmt.path(project.path), back: { dismiss() })
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
                    .padding(.top, 22)
                    if !rows.isEmpty { SectionLabel("Fortsetzen") }
                    ForEach(rows) { c in
                        Button { pick(c) } label: { ConversationRow(conversation: c, live: app.liveTerminal(for: c) != nil) }
                            .buttonStyle(.plain)
                        Hairline()
                    }
                    if loaded && rows.isEmpty {
                        Text("Noch keine Unterhaltungen in diesem Verzeichnis.")
                            .font(Face.ui(13)).foregroundStyle(Palette.meta).padding(.top, 20)
                    }
                }
                .padding(.horizontal, 22).padding(.top, 10).padding(.bottom, 40)
            }
            .scrollIndicators(.hidden)
        }
        .toolbar(.hidden, for: .navigationBar)
        .task {
            rows = await app.conversations(of: project)
            loaded = true
        }
        .confirmationDialog("Läuft vermutlich gerade im Terminal",
                            isPresented: Binding(get: { forkCandidate != nil }, set: { if !$0 { forkCandidate = nil } }),
                            titleVisibility: .visible, presenting: forkCandidate) { c in
            Button("Als Abzweig öffnen") { open(c.sessionId, fork: true) }
            Button("Abbrechen", role: .cancel) {}
        } message: { _ in
            Text("Der bisherige Verlauf kommt mit, die Sitzung am Rechner bleibt unberührt. Was hier passiert, fließt nicht zurück.")
        }
    }

    private func pick(_ c: Conversation) {
        if let live = app.liveTerminal(for: c) {
            app.path.append(.session(live.key))
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
            }
            starting = false
        }
    }
}
