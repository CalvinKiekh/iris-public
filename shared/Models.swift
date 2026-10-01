import Foundation

// What the bridge sends. Everything is decoded leniently: a card the app does
// not fully understand is better than a stream that stops at it.

extension KeyedDecodingContainer {
    func lenient<T: Decodable>(_ key: Key, _ type: T.Type = T.self) -> T? {
        (try? decodeIfPresent(T.self, forKey: key)) ?? nil
    }
}

/// One card of a session's stream. The kinds are listed in docs/PROTOCOL.md.
struct Card: Decodable, Sendable {
    var kind: String
    var seq: Int?
    var ts: Double?
    var text: String?
    var tool: String?
    var detail: String?
    var toolUseId: String?
    var ok: Bool?
    var requestId: String?
    var allow: Bool?
    var input: ToolInput?
    var change: Change?
    var durationMs: Int?
    var mode: String?
    var reason: String?
    var windows: [String: QuotaWindow]?
    var tasks: [BackgroundTask]?
    var attachments: [AttachmentInfo]?
    var delivery: String?
    var via: String?
    /// A question answered at the Mac: what was picked, by question.
    var answers: [String: String]?
    /// What Claude is doing, from the terminal's working line.
    var verb: String?
    var thinking: Bool?
    /// The pages the session published.
    var items: [ArtifactLink]?
    /// A view in the terminal holds the tab (kind "view").
    var open: Bool?
    /// A window of the plan is used up (kind "usage").
    var limited: UsageLimit?
    /// The full path of a picture a Read call opened.
    var image: String?
    /// Files Claude handed over (SendUserFile).
    var files: [String]?
    /// The cards this one supersedes, by their seq. A terminal session is
    /// read from the screen first, where the markdown is already drawn away;
    /// the transcript has it whole and comes after, saying what it replaces.
    var replaces: [Int]?

    enum CodingKeys: String, CodingKey {
        case kind, seq, ts, text, tool, detail, toolUseId, ok, requestId, allow
        case input, change, durationMs, mode, reason, windows, tasks, attachments
        case delivery, via, answers, verb, thinking, items, open, limited, image, files
        case replaces
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        kind = c.lenient(.kind) ?? "unknown"
        seq = c.lenient(.seq)
        ts = c.lenient(.ts)
        text = c.lenient(.text)
        tool = c.lenient(.tool)
        detail = c.lenient(.detail)
        toolUseId = c.lenient(.toolUseId)
        ok = c.lenient(.ok)
        requestId = c.lenient(.requestId)
        allow = c.lenient(.allow)
        input = c.lenient(.input)
        change = c.lenient(.change)
        durationMs = c.lenient(.durationMs)
        mode = c.lenient(.mode)
        reason = c.lenient(.reason)
        windows = c.lenient(.windows)
        tasks = c.lenient(.tasks)
        attachments = c.lenient(.attachments)
        delivery = c.lenient(.delivery)
        via = c.lenient(.via)
        answers = c.lenient(.answers)
        verb = c.lenient(.verb)
        thinking = c.lenient(.thinking)
        items = c.lenient(.items)
        open = c.lenient(.open)
        limited = c.lenient(.limited)
        image = c.lenient(.image)
        files = c.lenient(.files)
        replaces = c.lenient(.replaces)
    }
}

/// A file named with its size, because its size is the reason it is named.
struct GrosseDatei: Decodable, Sendable, Hashable, Identifiable {
    var path = ""
    var bytes = 0

    /// The path, because within one handover it is what tells them apart.
    var id: String { path }
}

/// One entry of `git status`, counted and not shown.
private struct EineAenderung: Decodable { var path: String? }

/// Whether a session could be picked up on another machine, and what stands
/// in the way. The repository is the transport - the target clones or pulls
/// it - so this is mostly git, plus the size of the history that would have
/// to travel.
struct Handover: Decodable, Sendable {
    var ok = false
    var grund = ""
    var repo = false
    var remote = ""
    var account = ""
    var branch = ""
    var ahead = 0
    var behind = 0
    var offen = 0
    var bytes = 0
    /// Ignored and big enough to miss: these travel with nothing.
    var ignoriert: [GrosseDatei] = []
    /// Ignored whole - named, not measured.
    var ignorierteOrdner: [String] = []
    /// Would be committed, but GitHub refuses a file this size.
    var schwer: [GrosseDatei] = []
    /// What the work was done on. The stand travels through git, the
    /// conditions do not - and a session picked up on the Pi otherwise tries
    /// `swift build` and finds out at the error.
    var maschine: Maschine?
    /// The same thing in prose, to hand to the session on the other side.
    var zettel = ""

    /// The button only exists where the transport does.
    var github: Bool { remote.contains("github.com") }

    enum CodingKeys: String, CodingKey {
        case ok, grund, repo, remote, account, branch, ahead, behind, changes, verlauf
        case ignoriert, schwer, maschine, zettel
    }

    enum VerlaufKeys: String, CodingKey { case da, bytes }
    enum IgnoriertKeys: String, CodingKey { case dateien, ordner }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ok = c.lenient(.ok) ?? false
        grund = c.lenient(.grund) ?? ""
        repo = c.lenient(.repo) ?? false
        remote = c.lenient(.remote) ?? ""
        account = c.lenient(.account) ?? ""
        branch = c.lenient(.branch) ?? ""
        ahead = c.lenient(.ahead) ?? 0
        behind = c.lenient(.behind) ?? 0
        // Only how many there are; what they are called is not the point here.
        offen = ((try? c.decode([EineAenderung].self, forKey: .changes)) ?? []).count
        if let v = try? c.nestedContainer(keyedBy: VerlaufKeys.self, forKey: .verlauf) {
            bytes = (try? v.decode(Int.self, forKey: .bytes)) ?? 0
        }
        if let i = try? c.nestedContainer(keyedBy: IgnoriertKeys.self, forKey: .ignoriert) {
            ignoriert = (try? i.decode([GrosseDatei].self, forKey: .dateien)) ?? []
            ignorierteOrdner = (try? i.decode([String].self, forKey: .ordner)) ?? []
        }
        schwer = c.lenient(.schwer) ?? []
        maschine = try? c.decode(Maschine.self, forKey: .maschine)
        zettel = c.lenient(.zettel) ?? ""
    }
}

/// The machine a piece of work was done on.
///
/// Travels with a handover because the stand goes through git and the
/// conditions do not. Which tools the work actually needed is deliberately
/// not here: the session writes that itself when the handoff runs. It was
/// there while the work happened, the bridge was not.
struct Maschine: Decodable, Sendable {
    var name = ""
    var os = ""
    var arch = ""
    var chip = ""
    var kerne = 0
    var ramGb = 0

    /// "macOS 26.4.1, Apple M4, 10 Kerne, 16 GB"
    var kurz: String {
        [os, chip, kerne > 0 ? "\(kerne) Kerne" : "", ramGb > 0 ? "\(ramGb) GB" : ""]
            .filter { !$0.isEmpty }.joined(separator: ", ")
    }

    enum CodingKeys: String, CodingKey {
        case name, os, arch, chip, kerne
        case ramGb
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = c.lenient(.name) ?? ""
        os = c.lenient(.os) ?? ""
        arch = c.lenient(.arch) ?? ""
        chip = c.lenient(.chip) ?? ""
        kerne = c.lenient(.kerne) ?? 0
        ramGb = c.lenient(.ramGb) ?? 0
    }
}

/// Was ein Update von Claude Code täte, bevor es etwas tut.
///
/// Updating used to mean ending every session and picking up every thread by
/// hand. It does not have to: a terminal session's key here is its Claude
/// session id, and `--resume` keeps it - so the same session comes back into
/// the same tab with the same history.
struct UpdatePlan: Decodable, Sendable {
    var ok = false
    var grund = ""
    var art = ""
    var version = ""
    /// What is available, "" when nothing is.
    var neu = ""
    var sitzungen: [UpdateSitzung] = []

    var lohnt: Bool { !neu.isEmpty && neu != version }
    /// Die, die stehen bleiben - weil sie arbeiten oder etwas nebenher läuft.
    var arbeiten: Int { sitzungen.filter { !$0.verschont.isEmpty }.count }

    enum CodingKeys: String, CodingKey { case ok, grund, installiert, neu, sitzungen }
    enum InstalliertKeys: String, CodingKey { case art, version }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ok = c.lenient(.ok) ?? false
        grund = c.lenient(.grund) ?? ""
        neu = c.lenient(.neu) ?? ""
        sitzungen = c.lenient(.sitzungen) ?? []
        if let i = try? c.nestedContainer(keyedBy: InstalliertKeys.self, forKey: .installiert) {
            art = (try? i.decode(String.self, forKey: .art)) ?? ""
            version = (try? i.decode(String.self, forKey: .version)) ?? ""
        }
    }
}

struct UpdateSitzung: Decodable, Sendable, Identifiable {
    var key = ""
    var titel = ""
    var cwd = ""
    var busy = false
    /// Agents from `/fork` and commands sent off with Ctrl+B keep running
    /// while the turn itself is done - the session looks idle and is not.
    var hintergrund = 0
    var id: String { key }

    /// Why this one is left alone, or "" when it is not.
    var verschont: String {
        busy ? "arbeitet" : hintergrund > 0 ? "Agent läuft" : ""
    }

    enum CodingKeys: String, CodingKey { case key, titel, cwd, busy, hintergrund }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        key = c.lenient(.key) ?? ""
        titel = c.lenient(.titel) ?? ""
        cwd = c.lenient(.cwd) ?? ""
        busy = c.lenient(.busy) ?? false
        hintergrund = c.lenient(.hintergrund) ?? 0
    }
}

/// Wie es ausgegangen ist - samt dem, was von Hand nachzuholen wäre.
struct UpdateErgebnis: Decodable, Sendable {
    var ok = false
    var grund = ""
    var vorher = ""
    var nachher = ""
    var aktualisiert = false
    /// Sessions that did not come back, with the command to type.
    var vonHand: [VonHand] = []

    struct VonHand: Decodable, Sendable, Identifiable {
        var titel = ""
        var befehl = ""
        var id: String { befehl }
    }

    enum CodingKeys: String, CodingKey {
        case ok, grund, vorher, nachher, aktualisiert
        case vonHand
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ok = c.lenient(.ok) ?? false
        grund = c.lenient(.grund) ?? ""
        vorher = c.lenient(.vorher) ?? ""
        nachher = c.lenient(.nachher) ?? ""
        aktualisiert = c.lenient(.aktualisiert) ?? false
        vonHand = (try? c.decode([VonHand].self, forKey: .vonHand)) ?? []
    }
}

/// A file that came with a message.
struct AttachmentInfo: Decodable, Sendable, Hashable {
    var name: String
    var path: String
    var mediaType: String?
}

struct UploadBody: Decodable, Sendable {
    var path: String
    var name: String
}

/// A slash command the session knows: Claude Code's own, a skill, or a
/// custom command. `phone` says whether it works from here; `why` if not.
struct SlashCommand: Decodable, Sendable, Hashable, Identifiable {
    var name: String
    var group: String
    var summary: String
    var detail: String
    var original: String
    var hint: String
    var phone: Bool
    var why: String?
    /// Opens a view in the terminal - the phone shows the screen for it.
    var view: Bool
    var id: String { name }

    enum CodingKeys: String, CodingKey { case name, group, summary, detail, original, hint, phone, why, view }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = c.lenient(.name) ?? ""
        group = c.lenient(.group) ?? "claude"
        summary = c.lenient(.summary) ?? ""
        detail = c.lenient(.detail) ?? ""
        original = c.lenient(.original) ?? ""
        hint = c.lenient(.hint) ?? ""
        phone = c.lenient(.phone) ?? false
        why = c.lenient(.why)
        view = c.lenient(.view) ?? false
    }

    /// What goes to Claude Code: the command, and what was typed after it.
    func line(with words: String) -> String {
        words.isEmpty ? "/\(name)" : "/\(name) \(words)"
    }

    /// The input's placeholder while this command is picked.
    var prompt: String { hint.isEmpty ? "Senden führt /\(name) aus" : hint }
}

struct CommandsBody: Decodable, Sendable {
    var commands: [SlashCommand]
}

/// The terminal as it is right now, and whether a view is open in it.
struct ScreenBody: Decodable, Sendable {
    var text: String
    var view: Bool
}

struct KeysBody: Encodable, Sendable {
    var key: String
    var text: String
}

/// A page Claude published in this session, to open from the phone.
struct ArtifactLink: Decodable, Sendable, Hashable, Identifiable {
    var url: String
    var title: String
    var icon: String
    var ts: Double?
    var id: String { url }

    enum CodingKeys: String, CodingKey { case url, title, icon, ts }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        url = c.lenient(.url) ?? ""
        title = c.lenient(.title) ?? "Seite"
        icon = c.lenient(.icon) ?? ""
        ts = c.lenient(.ts)
    }
}

/// Something that keeps running after the call that started it returned: a
/// command sent to the background (asked for, or with Ctrl+B), or a subagent.
struct BackgroundTask: Decodable, Sendable, Identifiable, Hashable {
    var id: String
    var type: String
    var status: String
    var description: String
    var command: String
    var since: Double?

    enum CodingKeys: String, CodingKey { case id, type, status, description, command, since }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = c.lenient(.id) ?? UUID().uuidString
        type = c.lenient(.type) ?? "shell"
        status = c.lenient(.status) ?? "running"
        description = c.lenient(.description) ?? ""
        command = c.lenient(.command) ?? ""
        since = c.lenient(.since)
    }
}

/// The parts of a tool's input the app shows. Any tool's input decodes into
/// this; what is not there stays nil.
struct ToolInput: Decodable, Sendable {
    var command: String?
    var filePath: String?
    var content: String?
    var url: String?
    var questions: [Question]?

    enum CodingKeys: String, CodingKey { case command, filePath, content, url, questions }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        command = c.lenient(.command)
        filePath = c.lenient(.filePath)
        content = c.lenient(.content)
        url = c.lenient(.url)
        questions = c.lenient(.questions)
    }
}

struct Question: Decodable, Sendable, Hashable {
    var question: String
    var header: String?
    var options: [Option]
    var multiSelect: Bool

    enum CodingKeys: String, CodingKey { case question, header, options, multiSelect }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        question = c.lenient(.question) ?? ""
        header = c.lenient(.header)
        options = c.lenient(.options) ?? []
        multiSelect = c.lenient(.multiSelect) ?? false
    }
}

struct Option: Decodable, Sendable, Hashable {
    var label: String
    var description: String?

    enum CodingKeys: String, CodingKey { case label, description }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        label = c.lenient(.label) ?? ""
        description = c.lenient(.description)
    }
}

/// What a file change changes: counts and the first lines, marked + or -.
struct Change: Decodable, Sendable, Hashable {
    var added: Int
    var removed: Int
    var lines: [[String]]

    enum CodingKeys: String, CodingKey { case added, removed, lines }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        added = c.lenient(.added) ?? 0
        removed = c.lenient(.removed) ?? 0
        lines = c.lenient(.lines) ?? []
    }
}

struct QuotaWindow: Decodable, Sendable {
    var used: Double?
    var resetsAt: Double?
}

/// One session as the bridge lists it - hosted here or running in a terminal.
struct SessionInfo: Decodable, Sendable, Hashable, Identifiable {
    var key: String
    var cwd: String
    var label: String
    var title: String
    var claudeSessionId: String?
    var permissionMode: String
    var permissionLabel: String
    var busy: Bool
    var exited: Bool
    var created: Double
    var lastActive: Double
    var openAsks: Int
    /// Welche Freigaben wirklich noch offen sind - nicht nur wie viele.
    /// Die App haelt ihre Karten selbst und entfernt eine erst, wenn ein
    /// "answered" dazu eintrifft. Verpasst sie das, weil die Bruecke
    /// zwischendurch neu startete, steht die Karte fuer immer, und kein
    /// Neustart der App hilft. Damit laesst sie sich abgleichen.
    var openAskIds: [String]
    var terminal: Bool
    /// Wofuer die Sitzung da ist. "vorarbeiter" heisst: sie fuehrt andere,
    /// und sie gehoert nicht in die Liste deiner Arbeit.
    var rolle: String
    var acts: Int
    var failed: Int
    var queued: Int
    /// A terminal session iris can type into (Terminal.app on the Mac).
    var typable: Bool
    var background: Int
    /// When the running turn began, as the bridge saw it.
    var turnStarted: Double?
    /// How full the context is, 0...1 - for a terminal session read from
    /// its transcript.
    var context: Double?

    var id: String { key }

    enum CodingKeys: String, CodingKey {
        case key, cwd, label, title, claudeSessionId, permissionMode, permissionLabel, busy, exited, rolle
        case created, lastActive, openAsks, openAskIds, terminal, acts, failed, queued, background, typable
        case turnStarted, context
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        key = try c.decode(String.self, forKey: .key)
        cwd = c.lenient(.cwd) ?? ""
        label = c.lenient(.label) ?? ""
        title = c.lenient(.title) ?? ""
        rolle = c.lenient(.rolle) ?? ""
        claudeSessionId = c.lenient(.claudeSessionId)
        permissionMode = c.lenient(.permissionMode) ?? ""
        permissionLabel = c.lenient(.permissionLabel) ?? ""
        busy = c.lenient(.busy) ?? false
        exited = c.lenient(.exited) ?? false
        created = c.lenient(.created) ?? 0
        lastActive = c.lenient(.lastActive) ?? 0
        openAsks = c.lenient(.openAsks) ?? 0
        // Eine aeltere Bruecke schickt das Feld nicht. Dann bleibt es leer,
        // und der Abgleich unterbleibt - er darf nichts wegwerfen, nur weil
        // die Gegenseite nichts sagt.
        openAskIds = (try? c.decode([String].self, forKey: .openAskIds)) ?? []
        terminal = c.lenient(.terminal) ?? false
        typable = c.lenient(.typable) ?? false
        acts = c.lenient(.acts) ?? 0
        failed = c.lenient(.failed) ?? 0
        queued = c.lenient(.queued) ?? 0
        background = c.lenient(.background) ?? 0
        turnStarted = c.lenient(.turnStarted)
        context = c.lenient(.context)
    }
}

struct Project: Decodable, Sendable, Hashable, Identifiable {
    var id: String
    var label: String
    var path: String
    var sessions: Int
    var lastUsed: Double?

    enum CodingKeys: String, CodingKey { case id, label, path, sessions, lastUsed }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        label = c.lenient(.label) ?? ""
        path = c.lenient(.path) ?? ""
        sessions = c.lenient(.sessions) ?? 0
        lastUsed = c.lenient(.lastUsed)
    }
}

/// A conversation that can be resumed.
struct Conversation: Decodable, Sendable, Hashable, Identifiable {
    var sessionId: String
    var title: String
    var modified: Double?
    var likelyOpen: Bool

    var id: String { sessionId }

    enum CodingKeys: String, CodingKey { case sessionId, title, modified, likelyOpen }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        sessionId = try c.decode(String.self, forKey: .sessionId)
        title = c.lenient(.title) ?? ""
        modified = c.lenient(.modified)
        likelyOpen = c.lenient(.likelyOpen) ?? false
    }
}

struct Mode: Decodable, Sendable, Hashable, Identifiable {
    var id: String
    var label: String
}

struct Shortcut: Decodable, Sendable, Hashable, Identifiable {
    var label: String
    var text: String
    var id: String { label + "\u{1}" + text }
}

struct ServiceSummary: Decodable, Sendable {
    var total: Int
    var healthy: Int
    var unhealthy: Int
    var missing: Int
}

struct ContextUsage: Decodable, Sendable {
    var percentage: Double?
    var totalTokens: Int?
    var maxTokens: Int?
}

/// What /usage shows - on a subscription the real limit, not a price.
struct Quota: Codable, Sendable, Equatable {
    var fiveHour: Double?
    var week: Double?
    /// When each window starts over, seconds since 1970.
    var fiveHourResets: Double?
    var weekResets: Double?
    /// A window is used up: nothing runs before this.
    var limitedUntil: Double?

    init?(_ card: Card) {
        guard let w = card.windows else { return nil }
        // The decoder turns snake_case keys into camelCase - dictionary keys
        // included - so both spellings are looked up.
        let five = w["fiveHour"] ?? w["five_hour"]
        let seven = w["sevenDay"] ?? w["seven_day"]
        guard five != nil || seven != nil else { return nil }
        fiveHour = five?.used
        week = seven?.used
        fiveHourResets = five?.resetsAt
        weekResets = seven?.resetsAt
        limitedUntil = card.limited?.resetsAt
    }

    init?(_ u: UsageBody) {
        guard u.fiveHour?.used != nil || u.sevenDay?.used != nil || u.limited != nil else { return nil }
        fiveHour = u.fiveHour?.used
        week = u.sevenDay?.used
        fiveHourResets = u.fiveHour?.resetsAt
        weekResets = u.sevenDay?.resetsAt
        limitedUntil = u.limited?.resetsAt
    }

    /// Used up right now.
    var limited: Bool { (limitedUntil ?? 0) > Date().timeIntervalSince1970 }

    /// The share of a window that is still running - nothing once it has
    /// turned over. A figure from a window that has ended says nothing about
    /// now, and the phone keeps the last one it was told: on 12.09. the
    /// header still read "100 %" at 21:34 while the window had reset at 20:50
    /// and the bridge was reporting 28 %. The bridge drops stale windows the
    /// same way; the app had never learned to.
    private func laufend(_ wert: Double?, _ ende: Double?) -> Double? {
        guard let wert else { return nil }
        if let ende, ende < Date().timeIntervalSince1970 { return nil }
        return wert
    }

    var fiveHourNow: Double? { laufend(fiveHour, fiveHourResets) }
    var weekNow: Double? { laufend(week, weekResets) }

    /// "18:40", or with the weekday when it is not today.
    static func clock(_ ts: Double?) -> String {
        guard let ts else { return "?" }
        let d = Date(timeIntervalSince1970: ts)
        let f = DateFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = Calendar.current.isDateInToday(d) ? "HH:mm" : "EE HH:mm"
        return f.string(from: d)
    }

    static func load() -> Quota? {
        guard let d = UserDefaults.standard.data(forKey: "iris.quota") else { return nil }
        return try? JSONDecoder().decode(Quota.self, from: d)
    }

    func save() {
        UserDefaults.standard.set(try? JSONEncoder().encode(self), forKey: "iris.quota")
    }
}

// MARK: - Response bodies

struct SessionsBody: Decodable, Sendable { var sessions: [SessionInfo] }
struct SessionBody: Decodable, Sendable { var session: SessionInfo }
struct ProjectsBody: Decodable, Sendable { var projects: [Project] }
struct ConversationsBody: Decodable, Sendable { var sessions: [Conversation] }
struct HistoryBody: Decodable, Sendable { var cards: [Card] }
struct ModesBody: Decodable, Sendable { var modes: [Mode] }
struct ShortcutsBody: Decodable, Sendable { var shortcuts: [Shortcut] }
struct ServicesBody: Decodable, Sendable { var summary: ServiceSummary }
struct ContextBody: Decodable, Sendable { var context: ContextUsage? }
/// GET /api/usage - what the status lines and streams last said.
struct UsageBody: Decodable, Sendable {
    var fiveHour: QuotaWindow?
    var sevenDay: QuotaWindow?
    var limited: UsageLimit?
}
struct UsageLimit: Decodable, Sendable {
    var window: String?
    var resetsAt: Double?
}
struct GitBody: Decodable, Sendable { var repo: Bool; var added: Int?; var removed: Int? }
struct AwayBody: Codable, Sendable { var away: Bool }

struct OkBody: Decodable, Sendable {
    var ok: Bool?
    var error: String?
    var queued: Bool?
    var note: String?
    var mode: String?
    var duplicate: Bool?
}

// MARK: - Request bodies
//
// Explicit keys instead of a snake_case strategy: that strategy rewrites
// dictionary keys too, and the answers to a question are keyed by the
// question's own text.

struct TextBody: Encodable, Sendable {
    var text: String
    var attachments: [String]? = nil
    /// The same id on a repeat: the bridge sends the message only once.
    var id: String? = nil
}
struct ModeBody: Encodable, Sendable { var mode: String }
struct GrundBody: Encodable, Sendable { var grund: String }
struct EmptyBody: Encodable, Sendable {}

struct PermissionBody: Encodable, Sendable {
    var requestId: String
    var allow: Bool
    var answers: [String: String]?
    enum CodingKeys: String, CodingKey { case requestId = "request_id", allow, answers }
}

struct CreateBody: Encodable, Sendable {
    var cwd: String
    var resume: String?
    var fork: Bool
    /// Leer bei einer gewoehnlichen Sitzung; "vorarbeiter" gibt ihr den
    /// Charakter und die Werkzeuge, andere Sitzungen zu fuehren.
    var rolle: String?
}

struct RegisterBody: Encodable, Sendable {
    var token: String
    var env: String
    var name: String
}

// MARK: - Services
//
// Decoded with the keys as they are: a service's detail is a free-form
// dictionary ("cpu_temp": 51), and the snake_case strategy would rename its
// keys on the way in.

/// A value from a service's detail - text, number or flag - as text.
struct LooseValue: Decodable, Sendable {
    let text: String

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if let s = try? c.decode(String.self) { text = s }
        else if let i = try? c.decode(Int.self) { text = String(i) }
        else if let d = try? c.decode(Double.self) { text = String(format: "%g", d) }
        else if let b = try? c.decode(Bool.self) { text = b ? "ja" : "nein" }
        else { text = "" }
    }
}

/// A service that reports itself to the bridge.
struct ServiceRow: Decodable, Sendable, Identifiable {
    var id: String
    var name: String
    var host: String
    var version: String
    var status: String
    var missing: Bool
    var detail: [String: String]
    var silentFor: Double?
    var interval: Double?

    enum CodingKeys: String, CodingKey {
        case id, name, host, version, missing, detail, interval
        case status = "reported_status"
        case silentFor = "silent_for"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = c.lenient(.name) ?? "?"
        host = c.lenient(.host) ?? ""
        id = c.lenient(.id) ?? "\(host)/\(name)"
        version = c.lenient(.version) ?? ""
        status = c.lenient(.status) ?? "ok"
        missing = c.lenient(.missing) ?? false
        detail = (c.lenient(.detail, [String: LooseValue].self) ?? [:]).mapValues(\.text)
        silentFor = c.lenient(.silentFor)
        interval = c.lenient(.interval)
    }

    /// Broken first: missing, then error, then warning, then fine.
    var rank: Int { missing ? 0 : status == "error" ? 1 : status == "warn" ? 2 : 3 }
}

struct ServicesFullBody: Decodable, Sendable {
    var services: [ServiceRow]
    var summary: ServiceSummary
}

/// What a bridge says about itself - the name is how a computer shows in the
/// list and in a notification.
struct HealthBody: Decodable, Sendable {
    var name: String?
    var platform: String?
}

/// A name for a session; empty gives the automatic title back.
struct TitleBody: Encodable, Sendable {
    var title: String
}
