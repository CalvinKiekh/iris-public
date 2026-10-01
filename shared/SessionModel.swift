import Foundation
import Observation
#if os(iOS)
import UIKit
#endif

/// One tool call as a line: tool, target, how long, and how it ended.
struct ToolRun: Identifiable {
    enum State { case running, ok, failed }

    let id: String
    let tool: String
    let target: String
    let started: Date
    var change: Change?
    var state: State = .running
    var duration: TimeInterval?
    var reason: String?
    var output: String?
    /// A picture it read - shown under the line.
    var image: String?
    /// Files it handed over - pictures shown, sound played, under the line.
    var files: [String] = []
}

/// One step of the conversation: what you said, what Claude said and did, or
/// a quiet note between them.
struct Turn: Identifiable {
    enum Kind { case user, claude, note, summary }
    enum Tone { case quiet, bad, seam }

    let id: Int
    let kind: Kind
    var text: String
    var tools: [ToolRun] = []
    var queued = false
    var delivered = false
    /// Typed while Claude worked and not taken yet - it waits in Claude
    /// Code's queue until the running step is through.
    var pending = false
    var taken = false
    /// How a message sent to a terminal session gets there: "now" typed at
    /// once, "turn" after the running turn, "prompt" with the next input.
    var delivery: String?
    var via: String?
    /// A message still on the phone, not yet taken by the bridge (Outbox).
    var localId: String?
    var attachments: [String] = []
    var tone: Tone = .quiet
    var finished = false
    /// The card this turn was drawn from - a later card can say it replaces
    /// it, which is how a terminal session gets its markdown back.
    var seq: Int?

    /// What is true about a message from the phone - not a hopeful guess.
    var deliveryLabel: String {
        if delivered { return via == "terminal" ? "im Terminal eingegeben" : "übergeben" }
        switch delivery {
        case "offline": return "wartet auf Verbindung – geht raus, sobald sie steht"
        case "now": return "wird eingetippt …"
        case "turn": return "kommt direkt nach diesem Zug dran"
        default: return "geht mit der nächsten Eingabe am Rechner mit"
        }
    }
}

/// Something waiting for you: an approval, or a question with options.
struct Decision: Identifiable {
    let id: String
    let tool: String
    let detail: String
    let input: ToolInput?
    let change: Change?
    /// Wann sie hier ankam. Der Abgleich mit der Bruecke darf nur Karten
    /// wegwerfen, die aelter sind als deren Auskunft - sonst faellt eine
    /// Freigabe weg, die gerade erst hereinkam, waehrend die Auskunft schon
    /// unterwegs war.
    var seen: Date = .now

    var questions: [Question] { input?.questions ?? [] }
    var isQuestion: Bool { tool == "AskUserQuestion" && !questions.isEmpty }

    var title: String {
        switch tool {
        case "Write": "Datei anlegen"
        case "Edit", "MultiEdit": "Datei ändern"
        case "NotebookEdit": "Notebook ändern"
        case "Bash": "Befehl ausführen"
        case "WebFetch": "Seite abrufen"
        case "WebSearch": "Im Netz suchen"
        default: tool.hasPrefix("mcp__") ? (tool.components(separatedBy: "__").last ?? tool) : tool
        }
    }

    var command: String? { tool == "Bash" ? (input?.command ?? detail) : nil }

    var meta: String? {
        switch tool {
        case "Write":
            // The change summary counts lines the way a diff does; a trailing
            // newline is not a line of its own.
            let lines = change?.added ?? (input?.content ?? "").split(separator: "\n").count
            return "\(detail) · \(lines) \(lines == 1 ? "Zeile" : "Zeilen")"
        case "Edit", "MultiEdit":
            guard let c = change else { return detail }
            return "\(detail) · +\(c.added) −\(c.removed)"
        case "Bash":
            return nil
        default:
            return detail.isEmpty ? nil : detail
        }
    }
}

/// A session on screen: its conversation rebuilt from the card stream, what
/// is waiting for an answer, and the counters the header shows.
@MainActor @Observable
final class SessionModel {
    let key: String
    private(set) var info: SessionInfo?
    private(set) var turns: [Turn] = []
    private(set) var decisions: [Decision] = []
    private(set) var busy = false
    private(set) var busySince: Date?
    private(set) var acts = 0
    private(set) var failed = 0
    private(set) var ended = false
    private(set) var context: Double?
    private(set) var background: [BackgroundTask] = []
    /// The word of the terminal's working line ("Prestidigitating…") and
    /// whether Claude thinks - both only while it works.
    /// The terminal's screen - for a view a command opened there.
    private(set) var screenText = ""
    private(set) var screenView = false

    func fetchScreen() async {
        guard let client = app?.client,
              let r = try? await client.get("api/sessions/\(key)/screen", as: ScreenBody.self) else { return }
        screenText = r.text
        screenView = r.view
    }

    /// Esc, Enter - or words with a Return - for the view in the tab.
    func press(_ key: String = "", text: String = "") async {
        guard let client = app?.client else {
            Trace.write("Taste \(key): keine Verbindung")
            return
        }
        do {
            let r = try await client.post("api/sessions/\(self.key)/keys",
                                          KeysBody(key: key, text: text), as: OkBody.self)
            Trace.write("Taste \(key) -> ok=\(r.ok ?? false) \(r.error ?? "")")
        } catch {
            Trace.write("Taste \(key) fehlgeschlagen: \(error)")
        }
        try? await Task.sleep(for: .milliseconds(600))
        await fetchScreen()
    }

    /// The slash commands this session knows - loaded when first needed.
    private(set) var commands: [SlashCommand] = []

    func loadCommands() async {
        guard commands.isEmpty, let client = app?.client,
              let r = try? await client.get("api/commands", query: [URLQueryItem(name: "session", value: key)],
                                            as: CommandsBody.self) else { return }
        commands = r.commands
    }

    /// While "/…" is typed: the commands that work from here and match -
    /// those that start with it first.
    func suggestions(for text: String) -> [SlashCommand] {
        guard text.hasPrefix("/"), !text.contains(" "), !text.contains("\n") else { return [] }
        let q = text.dropFirst().lowercased()
        let usable = commands.filter(\.phone)
        let starts = usable.filter { $0.name.lowercased().hasPrefix(q) }
        let inside = q.isEmpty ? [] : usable.filter { !$0.name.lowercased().hasPrefix(q) && $0.name.lowercased().contains(q) }
        return Array((starts + inside).prefix(6))
    }

    /// Whether this session could be picked up on another machine - loaded
    /// once when it opens, because it asks git and that is cheap but not free.
    private(set) var handover: Handover?

    func loadHandover() async {
        guard handover == nil, let client = app?.client else { return }
        handover = try? await client.get("api/sessions/\(key)/uebergabe", as: Handover.self)
    }

    /// The pages this session published, newest first.
    private(set) var artifacts: [ArtifactLink] = []
    private(set) var verb: String?
    private(set) var thinking = false

    /// What is going on in words, while Claude works: the tool that runs,
    /// or thinking. Nil when it writes, or nothing more is known.
    var doing: String? {
        guard busy else { return nil }
        for t in turns.suffix(4).reversed() where t.kind == .claude {
            if let run = t.tools.last(where: { $0.state == .running }) { return Self.doing(run.tool) }
        }
        return thinking ? "denkt nach" : nil
    }

    /// The tool that is running right now, if any. Ctrl+B sends a command
    /// away; while Claude thinks there is nothing to send, and offering it
    /// there promises something the key cannot do.
    var runningTool: String? {
        guard busy else { return nil }
        for t in turns.suffix(4).reversed() where t.kind == .claude {
            if let run = t.tools.last(where: { $0.state == .running }) { return run.tool }
        }
        return nil
    }

    /// Only a shell command goes to the background - an agent or a web call
    /// keeps the turn either way.
    var canBackground: Bool {
        guard let tool = runningTool else { return false }
        return tool == "Bash" || tool == "BashOutput"
    }

    static func doing(_ tool: String) -> String {
        switch tool {
        case "Bash", "BashOutput": return "führt einen Befehl aus"
        case "Read", "NotebookRead": return "liest"
        case "Edit", "MultiEdit", "Write", "NotebookEdit": return "schreibt Dateien"
        case "Grep", "Glob", "ToolSearch": return "sucht"
        case "WebFetch", "WebSearch": return "sieht im Netz nach"
        case "Agent", "Task": return "ein Agent arbeitet"
        default:
            if tool.hasPrefix("mcp__claude-in-chrome") { return "arbeitet im Browser" }
            return "benutzt \(tool.split(separator: "_").last.map(String.init) ?? tool)"
        }
    }
    private(set) var added: Int?
    private(set) var removed: Int?
    /// Bumps whenever something is appended; the view scrolls on it.
    private(set) var revision = 0
    /// True while history and the replayed backlog arrive in one burst after
    /// opening. Then the view jumps to the end and counts nothing as unread -
    /// nobody has scrolled up yet, there is nothing to protect.
    private(set) var settling = true
    var notice: String?

    @ObservationIgnored weak var app: AppModel?
    @ObservationIgnored private var lastSeq = 0
    /// When the conversation was last thrown away and read again.
    @ObservationIgnored private var startedOver = Date.distantPast
    @ObservationIgnored private var toolIndex: [String: (turn: Int, run: Int)] = [:]
    /// Phone entries the bridge's "queued" card took over - kept, not removed,
    /// once the send is confirmed.
    @ObservationIgnored private var adopted: Set<String> = []
    @ObservationIgnored private var timings: [String: Int] = [:]
    @ObservationIgnored private var stream: Task<Void, Never>?
    @ObservationIgnored private var figures: Task<Void, Never>?
    /// Whether the bridge answers right now - shown, so a dropped link is
    /// never mistaken for a quiet session.
    private(set) var connected = true
    @ObservationIgnored private var outbox: [Outgoing] = []
    @ObservationIgnored private var outboxLoaded = false
    @ObservationIgnored private var flushing = false
    @ObservationIgnored private var retry: Task<Void, Never>?
    var hasOutbox: Bool { !outbox.isEmpty }
    @ObservationIgnored private var nextId = 0
    @ObservationIgnored private var historyLoaded = false
    /// Cards that came since the last write to the device's cache.
    @ObservationIgnored private var pendingLines: [String] = []
    @ObservationIgnored private var flushTask: Task<Void, Never>?
    @ObservationIgnored private var lastCardAt = Date()
    /// Cards that arrived and wait to be drawn - applied in one go every
    /// 80 ms. One at a time, the whole conversation was laid out again per
    /// card: a replay of thousands took minutes and the view fell behind.
    @ObservationIgnored private var arriving: [Card] = []
    @ObservationIgnored private var drawTask: Task<Void, Never>?
    /// Set once the card stream is connected: only then can "quiet" mean the
    /// backlog is through. Loading the history before it sends no cards.
    @ObservationIgnored private var streaming = false

    init(key: String, info: SessionInfo?, app: AppModel) {
        self.key = key
        self.info = info
        self.app = app
        busy = info?.busy ?? false
        if busy, let t = info?.turnStarted { busySince = Date(timeIntervalSince1970: t) }
        ended = info?.exited ?? false
    }

    /// Offene Freigaben gegen die Bruecke abgleichen.
    ///
    /// Die App entfernt eine Karte sonst nur, wenn ein "answered" dazu
    /// eintrifft. Verpasst sie das - die Bruecke startete neu, das Telefon
    /// war weg -, steht die Karte fuer immer, und auch ein Neustart der App
    /// holt sie zurueck, weil sie beim Wiederaufbau erneut mitkommt.
    /// Gemeldet von Calvin am 28.09. an einer Frage, die niemand mehr
    /// beantworten konnte.
    ///
    /// Die Bruecke weiss, was offen ist. Weggeworfen wird nur, was sie nicht
    /// nennt und was schon da war, bevor ihre Auskunft entstand.
    private func abgleichenMitBruecke(_ info: SessionInfo, stand: Date) {
        guard !decisions.isEmpty else { return }
        let offen = Set(info.openAskIds)
        // Eine aeltere Bruecke nennt keine Kennungen. Dann zaehlt nur, dass
        // sie ueberhaupt keine offen hat - sonst wuerde blind geleert.
        if offen.isEmpty && info.openAsks > 0 { return }
        decisions.removeAll { !offen.contains($0.id) && $0.seen < stand }
    }

    var isTerminal: Bool { info?.terminal ?? key.hasPrefix("t-") }
    var mode: String { info?.permissionMode ?? "" }
    var title: String {
        let t = info?.title ?? ""
        return t.isEmpty ? (info?.label ?? "Sitzung") : Fmt.title(t)
    }
    var path: String { Fmt.path(info?.cwd ?? "") }

    func update(_ info: SessionInfo) {
        let davor = Date.now
        self.info = info
        abgleichenMitBruecke(info, stand: davor)
        // Uebernehmen, nicht nur setzen. Vorher stand hier
        // `if info.exited { ended = true }` - einmal beendet, fuer immer
        // beendet. Das Update beendet jede Sitzung und holt sie per
        // --resume zurueck; danach meldet die Bruecke wieder exited=false,
        // die App blieb aber beim Zwischenstand stehen und blendete die
        // Eingabezeile aus. Die Bruecke weiss, ob eine Sitzung lebt.
        ended = info.exited
        // A terminal session has no control channel; its figure comes along.
        if info.terminal, let c = info.context { context = c }
    }

    // MARK: stream

    /// One line per step that decides what the view shows.
    func trace(_ text: @autoclosure () -> String) {
        let line = "\(Date().formatted(.dateTime.hour().minute().second())) [\(key.prefix(10))] \(text())"
        #if DEBUG
        print("IRIS-LOG " + line)
        #endif
        Trace.write(line)
    }

    func start() {
        guard stream == nil else { return }
        loadOutbox()
        settle()
        stream = Task { await run() }
        // Context and limits move within a long turn too - not only when it
        // ends, and the home screen, which asks as well, is not in view.
        figures = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(20))
                await self?.refreshFigures()
            }
        }
    }

    func stop() {
        stream?.cancel()
        stream = nil
        figures?.cancel()
        figures = nil
        flushCache()
    }

    /// Settling lasts until the burst is over - half a second without a card -
    /// not a fixed time: a long backlog used to run past it, and all of its
    /// late part was counted as new.
    private func settle() {
        settling = true
        streaming = false
        lastCardAt = Date()
        Task {
            let begun = Date()
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(250))
                let quiet = Date().timeIntervalSince(lastCardAt) > 0.6
                if (streaming && quiet) || Date().timeIntervalSince(begun) > 30 { break }
            }
            settling = false
            trace("Nachladen fertig: \(turns.count) Züge, lastSeq \(lastSeq)")
        }
    }

    private func run() async {
        guard let client = app?.client else { return }
        if !historyLoaded {
            historyLoaded = true
            await loadHistory(client)
            await refreshDetails()
        }
        while !Task.isCancelled {
            // A short question first: a stream that cannot connect would only
            // say so after its timeout.
            guard (try? await client.get("api/health", as: OkBody.self)) != nil else {
                connected = false
                try? await Task.sleep(for: .seconds(3))
                continue
            }
            connected = true
            await flushOutbox()
            do {
                var renumbered = false, outOfOrder = 0
                // From here the backlog comes; the quiet after it ends settling.
                lastCardAt = Date()
                streaming = true
                for try await incoming in client.events(key, since: lastSeq) {
                    let card = incoming.card
                    if let s = card.seq, s > 0 {
                        // Asked for what came after lastSeq, got a smaller
                        // number: the bridge counts afresh (its record was
                        // lost). What is kept here no longer lines up, so it
                        // is read again - but only once a minute. Numbers
                        // that keep falling back are a fault over there,
                        // two bridges writing one feed, and loading again
                        // for every one of them leaves the app doing
                        // nothing else. Then skip what is out of order.
                        // The same number again is normal: one event
                        // becomes several cards - a sentence and the tool
                        // calls after it - and they all carry its number.
                        if s < lastSeq {
                            if Date().timeIntervalSince(startedOver) > 60 {
                                renumbered = true
                                break
                            }
                            outOfOrder += 1
                            continue
                        }
                        lastSeq = s
                    }
                    lastCardAt = Date()
                    arriving.append(card)
                    scheduleDraw()
                    pendingLines.append(incoming.line)
                    scheduleFlush()
                }
                drawArrived()
                if outOfOrder > 0 {
                    trace("\(outOfOrder) Karten außer der Reihe übersprungen")
                }
                if renumbered {
                    arriving = []
                    startedOver = Date()
                    startOver()
                    await loadHistory(client)
                    continue
                }
            } catch {
                if Outbox.unreachable(error) { connected = false }
            }
            if Task.isCancelled || ended { break }
            try? await Task.sleep(for: .seconds(1.5))
        }
        stream = nil
    }

    /// What came before: first what this device kept (shown at once, and
    /// only the rest is fetched), otherwise the bridge's history - kept for
    /// next time.
    private func loadHistory(_ client: BridgeClient) async {
        if let cached = CardCache.load(key) {
            trace("aus dem Speicher: \(cached.history.count) Verlauf + \(cached.feed.count) Karten, lastSeq \(cached.lastSeq)")
            for c in cached.history { apply(c, historic: true) }
            if !cached.history.isEmpty { closeHistory() }
            for c in cached.feed { apply(c, historic: true) }
            lastSeq = cached.lastSeq
            return
        }
        guard let raw = try? await client.raw("api/sessions/\(key)/history",
                                              query: [URLQueryItem(name: "limit", value: "120")]),
              let h = try? BridgeClient.cardDecoder().decode(HistoryBody.self, from: raw) else { return }
        trace("von der Brücke: \(h.cards.count) Verlaufskarten")
        CardCache.saveHistory(raw, for: key)
        for c in h.cards { apply(c, historic: true) }
        if !h.cards.isEmpty { closeHistory() }
    }

    private func closeHistory() {
        for i in turns.indices where turns[i].kind == .claude { turns[i].finished = true }
        note("hier geht es weiter", tone: .seam)
    }

    /// The bridge numbered afresh: drop what is shown and kept, and load again.
    private func startOver() {
        trace("NEU LADEN: Brücke zählt neu (lastSeq \(lastSeq))")
        CardCache.clear(key)
        pendingLines = []
        turns = []
        decisions = []
        toolIndex = [:]
        timings = [:]
        acts = 0
        failed = 0
        background = []
        artifacts = []
        lastSeq = 0
        revision += 1
        settle()
    }

    private func scheduleDraw() {
        guard drawTask == nil else { return }
        drawTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(80))
            self?.drawTask = nil
            self?.drawArrived()
        }
    }

    /// Everything that came since the last draw, in one pass - SwiftUI lays
    /// the conversation out once for all of it.
    private func drawArrived() {
        guard !arriving.isEmpty else { return }
        let batch = arriving
        arriving = []
        if batch.count > 20 { trace("Schwung: \(batch.count) Karten, dann \(turns.count) Züge") }
        for card in batch { apply(card, historic: false) }
    }

    private func scheduleFlush() {
        guard flushTask == nil else { return }
        flushTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(1))
            self?.flushTask = nil
            self?.flushCache()
        }
    }

    /// Writes what came since the last time, off the main thread.
    private func flushCache() {
        guard !pendingLines.isEmpty else { return }
        let lines = pendingLines, seq = lastSeq, key = key
        pendingLines = []
        Task.detached { CardCache.append(lines, lastSeq: seq, for: key) }
    }

    func rename(_ title: String) async {
        guard await app?.rename(session: key, to: title) == true else { return }
        await refreshDetails()
    }

    func refreshDetails() async {
        guard let client = app?.client else { return }
        if let r = try? await client.get("api/sessions/\(key)", as: SessionBody.self) { update(r.session) }
        if let g = try? await client.get("api/git", query: [URLQueryItem(name: "session", value: key),
                                                            URLQueryItem(name: "what", value: "status")],
                                         as: GitBody.self), g.repo {
            added = g.added
            removed = g.removed
        }
        await loadContext(client)
    }

    /// The figures only: context and the plan's limits.
    private func refreshFigures() async {
        guard let client = app?.client else { return }
        if let r = try? await client.get("api/sessions/\(key)", as: SessionBody.self) { update(r.session) }
        if let u = try? await client.get("api/usage", as: UsageBody.self), let q = Quota(u) { app?.updateQuota(q) }
        // A hosted session's context is asked through its control channel -
        // only while it works, when it changes.
        if busy { await loadContext(client) }
    }

    private func loadContext(_ client: BridgeClient) async {
        // A terminal session's figure comes with its info (update above).
        guard !isTerminal,
              let c = try? await client.get("api/sessions/\(key)/context", as: ContextBody.self),
              let u = c.context else { return }
        if let p = u.percentage {
            context = p > 1 ? p / 100 : p
        } else if let t = u.totalTokens, let m = u.maxTokens, m > 0 {
            context = Double(t) / Double(m)
        }
    }

    // MARK: cards

    func apply(_ c: Card, historic: Bool) {
        switch c.kind {
        case "sent":
            if let i = waitingTurn(c.text ?? "") {
                take(i)
            } else {
                addUser(c.text ?? "", queued: false, attachments: c.attachments ?? [])
            }
            if !historic { begin(at: c.ts) }
        case "pending":
            // Your own message from the phone is already here; one typed at
            // the Mac comes in as a new turn - greyed, either way.
            let text = c.text ?? ""
            if let i = turns.indices.suffix(12).last(where: {
                turns[$0].kind == .user && !turns[$0].pending && !turns[$0].taken && Self.same(turns[$0].text, text)
            }) {
                turns[i].pending = true
                revision += 1
            } else {
                addTurn(Turn(id: newId(), kind: .user, text: text, pending: true))
            }
        case "taken":
            if let i = waitingTurn(c.text ?? "") { take(i) }
        case "view":
            screenView = c.open ?? false
        case "artifacts":
            artifacts = (c.items ?? []).filter { URL(string: $0.url) != nil }
        case "activity":
            verb = c.verb
            thinking = c.thinking ?? false
            working(historic)
        case "summary":
            addTurn(Turn(id: newId(), kind: .summary, text: c.text ?? ""))
        case "queued":
            // The bridge's word for a message this phone sent: it takes the
            // place of the phone's own entry instead of standing beside it.
            if let i = turns.lastIndex(where: { $0.localId != nil && !$0.delivered && $0.text == (c.text ?? "") }),
               let id = turns[i].localId {
                turns[i].delivery = c.delivery
                adopted.insert(id)
                revision += 1
            } else {
                addUser(c.text ?? "", queued: true, attachments: c.attachments ?? [])
                turns[turns.count - 1].delivery = c.delivery
            }
        case "delivered":
            deliver(via: c.via)
        case "say":
            let text = c.text ?? ""
            // Said outright which cards it supersedes: the screen showed the
            // paragraphs without their markdown, the transcript has them
            // whole. No comparing of texts that no longer look alike.
            if let replaces = c.replaces, !replaces.isEmpty {
                let gone = Set(replaces)
                var at = turns.firstIndex { $0.seq.map(gone.contains) == true }
                turns.removeAll { $0.seq.map(gone.contains) == true }
                var t = Turn(id: newId(), kind: .claude, text: text)
                t.seq = c.seq
                if let i = at, i <= turns.count {
                    turns.insert(t, at: i)
                } else {
                    at = nil
                    turns.append(t)
                }
                reindexTools()
                revision += 1
                break
            }
            // A sentence taken while it was still being drawn, and then
            // again whole: the longer one replaces the part instead of
            // standing twice - whatever source sent it.
            if let i = turns.indices.last(where: { turns[$0].kind == .claude && !turns[$0].text.isEmpty }),
               i >= turns.count - 4,
               text.count > turns[i].text.count,
               text.hasPrefix(turns[i].text) {
                turns[i].text = text
                turns[i].seq = c.seq ?? turns[i].seq
                revision += 1
            } else {
                var t = Turn(id: newId(), kind: .claude, text: text)
                t.seq = c.seq
                addTurn(t)
            }
        case "act":
            addTool(c)
            working(historic)
        case "result":
            finishTool(c)
        case "timing":
            guard let id = c.toolUseId, let ms = c.durationMs else { break }
            timings[id] = ms
            if let ix = toolIndex[id], holds(ix) { turns[ix.turn].tools[ix.run].duration = Double(ms) / 1000 }
        case "ask":
            guard let rid = c.requestId, !decisions.contains(where: { $0.id == rid }) else { break }
            decisions.append(Decision(id: rid, tool: c.tool ?? "?", detail: c.detail ?? "",
                                      input: c.input, change: c.change))
            #if os(iOS)
            if !historic { UINotificationFeedbackGenerator().notificationOccurred(.warning) }
            #endif
        case "answered":
            guard let rid = c.requestId else { break }
            // Answered at the Mac while it stood here too: what was picked
            // there is your turn, the same as when you pick it here.
            if let d = decisions.first(where: { $0.id == rid }), d.isQuestion, let answers = c.answers {
                addUser(d.questions.compactMap { answers[$0.question] }.joined(separator: " · "), queued: false)
            }
            decisions.removeAll { $0.id == rid }
        case "think":
            // Replayed too: an app opened mid-turn must end up working, not
            // "bereit" because the last thing it replayed was the turn before
            // ending. When it began comes with the session info.
            if historic {
                // But only if the session really is working. A backlog often
                // ends on a think whose done never came - a turn stopped with
                // Esc, a bridge restarted in between, a tab without hooks -
                // and every terminal session then read "arbeitet" although it
                // sat idle. The session info knows the truth; believe it.
                guard info?.busy ?? true else { break }
                busy = true
                if busySince == nil, let t = info?.turnStarted { busySince = Date(timeIntervalSince1970: t) }
            } else {
                begin(at: nil)
            }
        case "done":
            end()
        case "mode":
            if let m = c.mode {
                info?.permissionMode = m
                note("Modus: \(m)")
            }
        case "closed":
            ended = true
            busy = false
            busySince = nil
            note("Sitzung beendet" + (c.reason.map { " — \($0)" } ?? ""))
        case "interrupted":
            busy = false
            busySince = nil
            verb = nil
            note("angehalten")
        case "background":
            background = (c.tasks ?? []).filter { $0.status == "running" || $0.status == "pending" }
        case "usage":
            if let q = Quota(c) { app?.updateQuota(q) }
        case "error":
            if let t = c.text { note(t, tone: .bad) }
        default:
            break
        }
    }

    /// In the order to draw: what happened, then - while Claude works - the
    /// working row, then what waits to be taken. A message that waits is
    /// not part of the work yet, so it stands below it until it is.
    func drawn(last count: Int) -> (settled: [Turn], waiting: [Turn]) {
        let shown = turns.suffix(count)
        return (shown.filter { !$0.pending }, shown.filter(\.pending))
    }

    private func waitingTurn(_ text: String) -> Int? {
        turns.indices.last { turns[$0].pending && Self.same(turns[$0].text, text) }
    }

    /// Claude took a waiting message: it stops being grey and moves to where
    /// it was taken - after what Claude did while it waited.
    private func take(_ i: Int) {
        var t = turns.remove(at: i)
        t.pending = false
        t.taken = true
        turns.append(t)
        reindexTools()
        revision += 1
    }

    /// The same message as the phone sent it and as the terminal queued it:
    /// the terminal adds the attachment lines, and long ones get clipped.
    static func same(_ a: String, _ b: String) -> Bool {
        let x = a.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        let y = b.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        let n = min(x.count, y.count, 80)
        return n > 0 && x.prefix(n) == y.prefix(n)
    }

    private func newId() -> Int {
        nextId += 1
        return nextId
    }

    private func addTurn(_ t: Turn) {
        turns.append(t)
        revision += 1
    }

    private func addUser(_ text: String, queued: Bool, attachments: [AttachmentInfo] = []) {
        addTurn(Turn(id: newId(), kind: .user, text: text, queued: queued,
                     attachments: attachments.map(\.name)))
    }

    /// A message that waited is placed where it was actually handed over -
    /// after the answer it waited for, not in the middle of it.
    private func deliver(via: String?) {
        // Only what the bridge holds - not what still waits on the phone.
        let held = { (t: Turn) in t.queued && !t.delivered && (t.localId == nil || self.adopted.contains(t.localId!)) }
        var waiting = turns.filter(held)
        guard !waiting.isEmpty else { return }
        turns.removeAll(where: held)
        for i in waiting.indices {
            waiting[i].delivered = true
            waiting[i].via = via
        }
        turns.append(contentsOf: waiting)
        reindexTools()
        revision += 1
    }

    private func note(_ text: String, tone: Turn.Tone = .quiet) {
        addTurn(Turn(id: newId(), kind: .note, text: text, tone: tone))
    }

    private func addTool(_ c: Card) {
        // A question is shown once, as the choice list waiting for you - not a
        // second time as a tool line running beside it.
        guard c.tool != "AskUserQuestion" else { return }
        let id = c.toolUseId ?? UUID().uuidString
        var run = ToolRun(id: id, tool: c.tool ?? "?", target: c.detail ?? "",
                          started: c.ts.map { Date(timeIntervalSince1970: $0) } ?? Date(), change: c.change)
        if let ms = timings[id] { run.duration = Double(ms) / 1000 }
        if c.tool == "Read", let path = c.image ?? c.input?.filePath, SessionImage.isImage(path) { run.image = path }
        if let sent = c.files, !sent.isEmpty {
            run.files = sent
            // The names, not the call's JSON.
            run = ToolRun(id: run.id, tool: run.tool,
                          target: sent.map { ($0 as NSString).lastPathComponent }.joined(separator: ", "),
                          started: run.started, change: run.change, state: run.state,
                          duration: run.duration, reason: run.reason, output: run.output,
                          image: run.image, files: sent)
        }
        // Tools hang off the Claude turn they belong to; a call without a
        // sentence before it starts a turn of its own.
        // Waiting messages stand below the work, so the turn it belongs to is
        // the last one that is not waiting.
        // The index is where the call went - with a waiting message at the
        // end, that is not the last turn.
        if let last = turns.indices.last(where: { !turns[$0].pending }),
           turns[last].kind == .claude, !turns[last].finished {
            turns[last].tools.append(run)
            toolIndex[id] = (last, turns[last].tools.count - 1)
            revision += 1
        } else {
            addTurn(Turn(id: newId(), kind: .claude, text: "", tools: [run]))
            toolIndex[id] = (turns.count - 1, 0)
        }
        acts += 1
    }

    /// Whether a remembered tool position still points at a tool - never
    /// again a crash for a position that went stale.
    private func holds(_ ix: (turn: Int, run: Int)) -> Bool {
        turns.indices.contains(ix.turn) && turns[ix.turn].tools.indices.contains(ix.run)
    }

    private func finishTool(_ c: Card) {
        guard let id = c.toolUseId, let ix = toolIndex[id], holds(ix) else { return }
        var run = turns[ix.turn].tools[ix.run]
        run.state = c.ok == false ? .failed : .ok
        if run.duration == nil, let ts = c.ts { run.duration = max(0, ts - run.started.timeIntervalSince1970) }
        run.output = c.text
        if c.ok == false {
            failed += 1
            run.reason = c.text.map(Self.firstLine)
        }
        turns[ix.turn].tools[ix.run] = run
    }

    static func firstLine(_ s: String) -> String {
        let line = s.split(separator: "\n", omittingEmptySubsequences: true).first.map(String.init) ?? s
        return String(line.prefix(160))
    }

    /// A tool call or the working line says Claude works - also when the
    /// turn's start got lost (an app opened mid-turn, a message typed at
    /// the Mac). When it began comes from the session info.
    private func working(_ historic: Bool) {
        guard !busy else { return }
        busy = true
        if let t = info?.turnStarted { busySince = Date(timeIntervalSince1970: t) }
        else if !historic { busySince = Date() }
    }

    private func begin(at ts: Double?) {
        guard !busy || busySince == nil else { return }
        busy = true
        busySince = ts.map { Date(timeIntervalSince1970: $0) } ?? Date()
    }

    private func end() {
        busy = false
        busySince = nil
        verb = nil
        thinking = false
        // Whatever still stands as waiting was taken - at the latest now,
        // with the next turn. A lost "taken" must not keep it grey for good.
        for i in turns.indices where turns[i].pending {
            turns[i].pending = false
            turns[i].taken = true
        }
        let from = (turns.lastIndex { $0.kind == .user && !$0.pending } ?? -1) + 1
        for i in turns.indices where i >= from && turns[i].kind == .claude { turns[i].finished = true }
        Task { await refreshDetails() }
    }

    // MARK: actions

    /// Sends a message. An open question takes free text as its answer -
    /// that is the "Oder etwas anderes …" of the choice list.
    func send(_ text: String, attachments: [Attachment] = []) async -> Bool {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty || !attachments.isEmpty, let client = app?.client else { return false }
        if attachments.isEmpty, let q = decisions.first(where: \.isQuestion) {
            let answers = Dictionary(q.questions.map { ($0.question, text) }, uniquingKeysWith: { a, _ in a })
            await answer(q, allow: true, answers: answers)
            return true
        }
        _ = client
        // Always through the outbox: if the bridge cannot be reached now, the
        // message waits on the phone instead of being lost.
        loadOutbox()
        let item = Outbox.make(text: text, attachments: attachments)
        outbox.append(item)
        Outbox.save(outbox, for: key)
        addLocal(item)
        // In the outbox it is safe - the input can empty now. The flush runs
        // on; a slow bridge must not keep the text standing in the field.
        Task { await flushOutbox() }
        return true
    }

    // MARK: outbox

    private func loadOutbox() {
        guard !outboxLoaded else { return }
        outboxLoaded = true
        outbox = Outbox.load(key)
        for item in outbox { addLocal(item) }
    }

    private func addLocal(_ item: Outgoing) {
        var t = Turn(id: newId(), kind: .user, text: item.text, queued: true,
                     attachments: item.files.map(\.name))
        t.delivery = "offline"
        t.localId = item.id
        addTurn(t)
    }

    /// Sends what waits, oldest first, each with its id - a repeat of one
    /// that did arrive is recognised by the bridge and not sent again.
    func flushOutbox() async {
        guard !flushing, !outbox.isEmpty, let client = app?.client else { return }
        flushing = true
        defer { flushing = false }
        while let item = outbox.first {
            do {
                // Files first; the message then names them by where they landed.
                var paths: [String] = []
                for f in item.files {
                    let data = try Data(contentsOf: URL(fileURLWithPath: f.path))
                    paths.append(try await client.upload(key, name: f.name, data: data, mediaType: f.mediaType).path)
                }
                let r = try await client.post("api/sessions/\(key)/message",
                                              TextBody(text: item.text, attachments: paths.isEmpty ? nil : paths,
                                                       id: item.id),
                                              as: OkBody.self)
                connected = true
                done(item)
                if r.queued == true, let n = r.note { notice = n }
            } catch {
                if Outbox.unreachable(error) {
                    connected = false
                    retryLater()
                    return
                }
                // The bridge answered and refused - an ended session, say.
                // Waiting would not change that.
                done(item)
                notice = "Nicht gesendet: " + Bridge.explain(error, on: app?.machine?.name)
            }
        }
    }

    private func done(_ item: Outgoing) {
        outbox.removeAll { $0.id == item.id }
        Outbox.save(outbox, for: key)
        Outbox.discard(item)
        // The bridge's own card (sent, queued) stands for it from now on - or
        // the entry already took that card over and simply stays.
        if adopted.remove(item.id) != nil, let i = turns.firstIndex(where: { $0.localId == item.id }) {
            turns[i].localId = nil
        } else {
            turns.removeAll { $0.localId == item.id }
        }
        reindexTools()
        revision += 1
    }

    private func retryLater() {
        guard retry == nil else { return }
        retry = Task { [weak self] in
            while let self, self.hasOutbox, !Task.isCancelled {
                try? await Task.sleep(for: .seconds(4))
                await self.flushOutbox()
            }
            self?.retry = nil
        }
    }

    private func reindexTools() {
        toolIndex.removeAll()
        for (t, turn) in turns.enumerated() {
            for (r, run) in turn.tools.enumerated() { toolIndex[run.id] = (t, r) }
        }
    }

    func answer(_ d: Decision, allow: Bool, answers: [String: String]? = nil) async {
        // Getippt, gesendet, angekommen - drei Dinge, die sich von aussen
        // nicht unterscheiden liessen. Schlaegt das Senden fehl, kommt die
        // Karte zurueck, und das sieht aus, als waere der Knopf tot.
        Trace.write("Freigabe [\(key.prefix(10))] \(allow ? "erlauben" : "ablehnen") "
                    + "· \(d.title)")
        guard let client = app?.client else {
            Trace.write("Freigabe: keine Verbindung")
            return
        }
        decisions.removeAll { $0.id == d.id }
        if !allow && !d.isQuestion { note("abgelehnt: \(d.title)" + (d.detail.isEmpty ? "" : " · \(d.detail)")) }
        // What you picked is what you said - it stands in the conversation as
        // your turn, where the question itself no longer does.
        if d.isQuestion, let answers {
            addUser(d.questions.compactMap { answers[$0.question] }.joined(separator: " · "), queued: false)
        }
        do {
            _ = try await client.post("api/sessions/\(key)/permission",
                                      PermissionBody(requestId: d.id, allow: allow, answers: answers),
                                      as: OkBody.self)
            Trace.write("Freigabe abgeschickt")
        } catch {
            decisions.insert(d, at: 0)
            notice = Bridge.explain(error, on: app?.machine?.name)
            Trace.write("Freigabe fehlgeschlagen: \(Bridge.explain(error, on: app?.machine?.name))")
        }
    }

    func setMode(_ id: String) async {
        guard let client = app?.client else { return }
        do {
            let r = try await client.post("api/sessions/\(key)/mode", ModeBody(mode: id), as: OkBody.self)
            if let m = r.mode { info?.permissionMode = m }
        } catch {
            notice = Bridge.explain(error, on: app?.machine?.name)
        }
    }

    func interrupt() async {
        guard let client = app?.client else { return }
        _ = try? await client.post("api/sessions/\(key)/interrupt", EmptyBody(), as: OkBody.self)
    }
}

/// Where the steps that decide what the conversation shows are written, in
/// release builds too. A conversation that empties itself now and then only
/// shows up in use, not in a test - and without a record there is nothing to
/// look at afterwards but a guess.
///
/// ~/Library/Logs/iris-app.log on the Mac, the app's own Library on the
/// phone. Kept small: past the cap the file starts over.
enum Trace {
    private static let queue = DispatchQueue(label: "iris.trace")
    private static let cap = 2 * 1024 * 1024

    static let file: URL? = {
        let fm = FileManager.default
        #if os(macOS)
        let dir = fm.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs")
        #else
        guard let dir = try? fm.url(for: .libraryDirectory, in: .userDomainMask,
                                    appropriateFor: nil, create: true) else { return nil }
        #endif
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("iris-app.log")
    }()

    static func write(_ line: String) {
        guard let file else { return }
        let stamp = Date().formatted(.dateTime.hour().minute().second())
        queue.async {
            let data = Data(("\(stamp) " + line + "\n").utf8)
            let fm = FileManager.default
            guard let handle = try? FileHandle(forWritingTo: file) else {
                try? data.write(to: file)
                return
            }
            defer { try? handle.close() }
            // Starting over beats trimming: the interesting part is the end.
            if (try? handle.seekToEnd()).map({ $0 > UInt64(cap) }) == true {
                try? handle.close()
                try? fm.removeItem(at: file)
                try? data.write(to: file)
                return
            }
            try? handle.write(contentsOf: data)
        }
    }
}
