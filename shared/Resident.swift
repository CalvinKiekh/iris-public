import Foundation
import Observation

// The resident (docs/PLAN.md section 6): a local model on one computer that
// watches and acts on its own. The app shows what it does and lets you stop
// it, wake it, tell it something and decide its requests. Its bridge reads
// the workspace; see docs/BEWOHNER.md for the files.

struct ResidentState: Decodable, Sendable {
    var name: String?
    var model: String?
    var state: String?
    var since: Double?
    var lastCheck: Double?
    var watching: [String]?
    var budget: ResidentBudget?
    var brake: String?
    var sessionKey: String?
    var openTask: String?
    var stopped = false
    var waking = false
    var alive = false
    var seen: Double?
    var requests: [ResidentRequest] = []
    var machine: String?
    /// What it can beyond the contract's basics - "entwurf": it takes a
    /// question before it is finished.
    var abilities: [String] = []
    /// Questions not answered yet, oldest first.
    var waiting: [ResidentQueued] = []

    enum CodingKeys: String, CodingKey {
        case name, model, state, since, lastCheck, watching, budget, brake, sessionKey, openTask
        case stopped, waking, alive, seen, requests, machine, conversation
        case abilities = "faehig"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = c.lenient(.name)
        model = c.lenient(.model)
        state = c.lenient(.state)
        since = c.lenient(.since)
        lastCheck = c.lenient(.lastCheck)
        watching = c.lenient(.watching)
        budget = c.lenient(.budget)
        brake = c.lenient(.brake)
        sessionKey = c.lenient(.sessionKey)
        openTask = c.lenient(.openTask)
        stopped = c.lenient(.stopped) ?? false
        waking = c.lenient(.waking) ?? false
        alive = c.lenient(.alive) ?? false
        seen = c.lenient(.seen)
        requests = c.lenient(.requests) ?? []
        machine = c.lenient(.machine)
        abilities = c.lenient(.abilities) ?? []
        waiting = (c.lenient(.conversation, ResidentConversation.self))?.waiting ?? []
    }

    /// In a word, as the header says it.
    var label: String {
        if stopped { return "angehalten" }
        if state == "beendet" { return "läuft nicht" }
        if !alive { return "meldet sich nicht" }
        switch state {
        case "denkt": return "denkt nach"
        case "arbeitet": return "arbeitet"
        case "fehler": return "Fehler"
        default: return "beobachtet"
        }
    }
}

struct ResidentQueued: Decodable, Sendable, Identifiable {
    var id: String
    var ts: Double?
    /// "app", or "test" for a test's question.
    var von: String?
    /// An addition to this earlier question.
    var zu: String?
}

struct ResidentConversation: Decodable, Sendable { var waiting: [ResidentQueued]? }

struct ResidentBudget: Decodable, Sendable {
    var ordersHour: Int?
    var ordersHourMax: Int?
    var ordersToday: Int?
}

struct ResidentRequest: Decodable, Sendable, Identifiable {
    var id: String
    var ts: Double?
    var title: String?
    var reason: String?
    var status: String?
    var decided: Double?
}

/// One line of the journal.
struct ResidentEntry: Decodable, Sendable, Identifiable {
    var seq: Int
    var ts: Double?
    var kind: String
    var text: String?
    var detail: String?
    var sessionKey: String?
    var ok: Bool?
    var seconds: Double?
    /// A request's id ("antrag", "entscheidung") or a question's
    /// ("frage", "antwort", "stimme").
    var ref: String?
    /// The recording of an answer ("stimme"), inside the workspace.
    var audio: String?
    /// Sentence by sentence: which part this is, and whether it is the last.
    var part: Int?
    var final: Bool?
    /// A question sent as an addition to this earlier one.
    var zu: String?
    /// Wer geredet hat: "calvin", "app" - oder "test" für den Testkanal.
    /// Eine Messung ist kein Gespräch, und sie hat in Calvins Chat nichts
    /// verloren. Am 13.09. standen 184 Frage- und Antwortzeilen im Journal,
    /// keine einzige mit Absender, und er fand seine Testfragen im Chat.
    var von: String?
    /// Ob die Zeile GERADE geschehen ist - oder nachgelesen wurde. Die Brücke
    /// weiß es und sagt es jetzt mit; geraten hat es eine Minute Warten auf
    /// eine Antwort gekostet, die längst da war. Fehlt das Feld, ist die
    /// Brücke älter und die Grenze entscheidet allein.
    var live: Bool?
    /// Which tool he reached for, and what made him reach for it. Without
    /// the occasion a tool use is just a name.
    var werkzeug: String?
    var anlass: String?

    var id: Int { seq }
    /// Stammt die Zeile aus einer Messung? Gefragt wird nach der PROBE, nicht
    /// nach Calvin: Sein Handy spricht unter "app", und eine Regel
    /// "alles außer calvin ist fremd" hätte es ausgeschlossen.
    var ausProbe: Bool { ["test", "probe"].contains((von ?? "").lowercased()) }
    /// gpt-oss was asked and found nothing to do - the usual case.
    var quiet: Bool { kind == "tick" }

    enum CodingKeys: String, CodingKey {
        case seq, ts, kind, text, detail, sessionKey, ok, seconds, audio, part, final, zu
        case werkzeug, anlass, live, von
        case ref = "id"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        seq = c.lenient(.seq) ?? 0
        ts = c.lenient(.ts)
        kind = c.lenient(.kind) ?? "?"
        text = c.lenient(.text)
        detail = c.lenient(.detail)
        sessionKey = c.lenient(.sessionKey)
        ok = c.lenient(.ok)
        seconds = c.lenient(.seconds)
        ref = c.lenient(.ref)
        audio = c.lenient(.audio)
        part = c.lenient(.part)
        final = c.lenient(.final)
        zu = c.lenient(.zu)
        live = c.lenient(.live)
        von = c.lenient(.von)
        werkzeug = c.lenient(.werkzeug)
        anlass = c.lenient(.anlass)
    }

    /// The last recording of an answer - a whole one, or the final part.
    var closing: Bool { part == nil || final == true }

    /// Where the recording of an answer lies - "audio" as the contract says,
    /// or a bare file name in "text", as the PC wrote it at first.
    var recording: String? {
        if let audio, !audio.isEmpty { return audio }
        if kind == "stimme", let t = text, t.lowercased().hasSuffix(".mp3") {
            return t.contains("/") ? t : "gespraech/" + t
        }
        return nil
    }

    /// Part of a conversation - shown there, not in the journal.
    var spoken: Bool { kind == "frage" || kind == "antwort" || kind == "stimme" }
}

struct ResidentFile: Decodable, Sendable, Identifiable, Hashable {
    var path: String
    var size: Int
    var mtime: Double
    var editable: Bool
    var id: String { path }
}

/// One thing it remembers (docs/BEWOHNER.md, Gedächtnis).
struct ResidentMemory: Decodable, Sendable, Identifiable, Hashable {
    var id: String
    var ts: Double?
    /// fakt, gespraech, ereignis, tagesrueckblick, datei
    var art: String
    var text: String
    var quelle: String?
    var wichtig: Double?
    /// A newer memory took its place ("the key is in the kitchen now").
    var ersetztDurch: String?

    enum CodingKeys: String, CodingKey { case id, ts, art, text, quelle, wichtig, ersetztDurch }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = c.lenient(.id) ?? ""
        ts = c.lenient(.ts)
        art = c.lenient(.art) ?? ""
        text = c.lenient(.text) ?? ""
        quelle = c.lenient(.quelle)
        wichtig = c.lenient(.wichtig) ?? (c.lenient(.wichtig, Bool.self).map { $0 ? 1 : 0 })
        ersetztDurch = c.lenient(.ersetztDurch)
    }

    var kindWord: String {
        switch art {
        case "fakt": return "FAKT"
        case "gespraech": return "GESPRÄCH"
        case "ereignis": return "EREIGNIS"
        case "tagesrueckblick": return "RÜCKBLICK"
        case "datei": return "DATEI"
        default: return art.uppercased()
        }
    }
}

/// A correction or forgetting on its way: a file the resident takes in.
struct ResidentMemoryChange: Decodable, Sendable, Identifiable {
    var id: String
    var aktion: String?
    var text: String?
    var ts: Double?
}

struct ResidentMemoryBody: Decodable, Sendable {
    var present = false
    var memories: [ResidentMemory] = []
    var counts: [String: Int] = [:]
    var pending: [ResidentMemoryChange] = []
    var error: String?

    enum CodingKeys: String, CodingKey { case present, memories, counts, pending, error }

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        present = c.lenient(.present) ?? false
        memories = c.lenient(.memories) ?? []
        counts = c.lenient(.counts) ?? [:]
        pending = c.lenient(.pending) ?? []
        error = c.lenient(.error)
    }
}

struct ResidentMemoryChain: Decodable, Sendable { var chain: [ResidentMemory] }

/// Who it is and what it sees (docs/BEWOHNER.md, "Wer er ist"): its own
/// notes, the situation read without a model, the tools it built, and what
/// you showed it.
struct ResidentSelf: Decodable, Sendable {
    var ich: String?
    var wuensche: String?
    var lage: ResidentLage?
    var werkzeuge: [ResidentTool] = []
    /// What it can do without being called - memory, perception, speaking up.
    var faehigkeiten: [ResidentTool] = []
    var eingang: [ResidentFile] = []

    enum CodingKeys: String, CodingKey { case ich, wuensche, lage, werkzeuge, faehigkeiten, eingang }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ich = c.lenient(.ich)
        wuensche = c.lenient(.wuensche)
        lage = c.lenient(.lage)
        werkzeuge = c.lenient(.werkzeuge) ?? []
        faehigkeiten = c.lenient(.faehigkeiten) ?? []
        eingang = c.lenient(.eingang) ?? []
    }

    /// The name it gave itself: the first line under a "Name" heading in
    /// ICH.md, or its opening heading when that is not just "Ich".
    var name: String? {
        guard let lines = ich?.split(separator: "\n", omittingEmptySubsequences: false)
            .map({ $0.trimmingCharacters(in: .whitespaces) }) else { return nil }
        if let i = lines.firstIndex(where: { $0.hasPrefix("#") && $0.lowercased().contains("name") }) {
            if let n = lines[(i + 1)...].first(where: { !$0.isEmpty && !$0.hasPrefix("#") }) {
                return String(n.prefix(60))
            }
        }
        if let head = lines.first(where: { $0.hasPrefix("# ") }) {
            let n = head.dropFirst(2).trimmingCharacters(in: .whitespaces)
            if !n.isEmpty, !["ich", "bewohner"].contains(n.lowercased()) { return n }
        }
        return nil
    }

    /// What it wrote about itself, as running text - without the headings,
    /// the name and the note about when it last wrote this.
    var about: String? {
        guard let ich else { return nil }
        var skipping = false
        let rest = ich.split(separator: "\n", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { line in
                if line.hasPrefix("#") {
                    skipping = line.lowercased().contains("name")
                    return false
                }
                // Everything under "Name" belongs to the name - the name
                // itself and why he chose it. Skipping only the first line
                // left the reasoning standing under "Wer er ist", so the page
                // said why he calls himself something instead of who he is.
                if skipping { return false }
                // Der Hinweis "<Name> darf das über die App korrigieren." ist
                // ein Satz fuer den Leser der Datei, nicht Teil dessen, wer er
                // ist. Am Ende erkannt, nicht am Namen: den kennt die App
                // nicht, und er steht in der Konfiguration des Bewohners.
                return !line.isEmpty && !line.hasPrefix("Zuletzt fortgeschrieben")
                    && !line.hasSuffix("darf das über die App korrigieren.")
            }
            .joined(separator: " ")
        return rest.isEmpty ? nil : rest
    }

    /// One wish per "- " line.
    var wishes: [String] {
        (wuensche ?? "").split(separator: "\n")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { $0.hasPrefix("- ") || $0.hasPrefix("* ") }
            .map { String($0.dropFirst(2)) }
    }
}

struct ResidentLage: Decodable, Sendable {
    var ts: Double?
    var tagesphase: String?
    var arbeitszeit: Bool?
    var netz: [ResidentDevice]?
    /// Wann der Nutzer zuletzt mit dem Bewohner sprach.
    var nutzerZuletzt: Double?

    enum CodingKeys: String, CodingKey { case ts, tagesphase, arbeitszeit, netz, nutzerZuletzt }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ts = c.lenient(.ts)
        tagesphase = c.lenient(.tagesphase)
        arbeitszeit = c.lenient(.arbeitszeit)
        netz = c.lenient(.netz)
        nutzerZuletzt = c.lenient(.nutzerZuletzt)
    }
}

struct ResidentDevice: Decodable, Sendable, Hashable {
    var name: String?
    var ip: String?
    var seit: Double?
}

/// One thing it can do: a tool it built, or something built into it. The
/// bridge sends both alike - a tool is called, a capability is simply there.
struct ResidentTool: Decodable, Sendable, Identifiable, Hashable {
    var name: String
    /// In its own words: what this does.
    var zweck: String?
    var geprueft: Bool?
    /// What shows it works - the proof from a real run.
    var ergebnis: String?
    /// How it is called; empty for what is built in.
    var aufruf: String?
    /// Since when it exists.
    var erstellt: Double?
    var id: String { name }

    enum CodingKeys: String, CodingKey { case name, zweck, geprueft, ergebnis, aufruf, erstellt }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = c.lenient(.name) ?? "?"
        zweck = c.lenient(.zweck)
        geprueft = c.lenient(.geprueft)
        ergebnis = c.lenient(.ergebnis)
        aufruf = c.lenient(.aufruf)
        erstellt = c.lenient(.erstellt)
    }
}

struct ResidentShowBody: Encodable, Sendable { var name: String; var data: String }
struct ResidentMemoryChangeBody: Encodable, Sendable { var id: String; var aktion: String; var text: String }
struct ResidentMemoryReply: Decodable, Sendable { var ok: Bool?; var error: String?; var pending: [ResidentMemoryChange]? }

struct ResidentBody: Decodable, Sendable { var resident: ResidentState }
struct ResidentReply: Decodable, Sendable { var ok: Bool?; var error: String?; var resident: ResidentState? }
struct ResidentFilesBody: Decodable, Sendable { var files: [ResidentFile] }

/// Ein früheres Gespräch, wie es in der Liste steht.
struct ResidentGespraech: Decodable, Sendable, Identifiable {
    var id: String
    var begonnen: Double?
    var zuletzt: Double?
    var geschlossen: Double?
    var paare: Int
    /// Erst da, wenn der Bewohner es abgeschlossen hat - vorher läuft es noch.
    var zusammenfassung: String?
}
struct ResidentGespraecheBody: Decodable, Sendable { var gespraeche: [ResidentGespraech] }
/// Ein Frage/Antwort-Paar aus einem früheren Gespräch.
struct ResidentPaar: Decodable, Sendable, Identifiable {
    var frage: String?
    var antwort: String?
    var ts: Double?
    var id: Double { ts ?? 0 }
}
/// Identifiable, damit `.sheet(item:)` es öffnen kann.
struct ResidentGespraechBody: Decodable, Sendable, Identifiable {
    var id: String
    var kopf: ResidentGespraech?
    var paare: [ResidentPaar]
}
struct ResidentFileBody: Decodable, Sendable { var path: String; var text: String }
struct ResidentStopBody: Encodable, Sendable { var on: Bool }
struct ResidentSayBody: Encodable, Sendable { var text: String }
struct ResidentDecideBody: Encodable, Sendable { var id: String; var allow: Bool }
struct ResidentWriteBody: Encodable, Sendable { var path: String; var text: String }
struct ResidentEmptyBody: Encodable, Sendable {}
struct ResidentTalkReply: Decodable, Sendable { var ok: Bool?; var id: String?; var error: String? }
/// A question - or its draft, sent at the first pause while you still speak.
struct ResidentTalkBody: Encodable, Sendable {
    var text: String
    var id: String?
    var draft: Bool
    var zu: String?
    /// The spoken question as a 16 kHz mono WAV, base64 - how it was said.
    var aufnahme: String?
    /// Ob er die Antwort auch sprechen soll. Ohne Sprachausgabe kostet jede
    /// Sprachdatei rund eine Sekunde, die niemand hört - und der Text kam
    /// bisher erst danach.
    var stimme: Bool?
}

/// The resident as the app sees it. There is one, on whichever computer
/// has it - not one per computer.
@MainActor @Observable
final class ResidentModel {
    static let shared = ResidentModel()

    /// The computer it lives on; nil while none was found.
    private(set) var machine: Machine?
    private(set) var state: ResidentState?
    private(set) var entries: [ResidentEntry] = []
    private(set) var problem: String?
    private(set) var connected = false

    @ObservationIgnored private var stream: Task<Void, Never>?
    @ObservationIgnored private var poll: Task<Void, Never>?

    // MARK: talking

    /// The whole answer to a question. Sentence by sentence, the "antwort"
    /// line holds only the first; the recordings carry the rest.
    func answerText(_ answer: ResidentEntry) -> String {
        guard let id = answer.ref else { return answer.text ?? "" }

        func teile(_ art: String) -> [String] {
            entries.filter { $0.kind == art && $0.ref == id && $0.part != nil }
                .sorted { ($0.part ?? 0) < ($1.part ?? 0) }
                .compactMap { $0.text }
                // LEERE TEILE ZAEHLEN NICHT.
                //
                // Ohne Sprachausgabe schreibt der Bewohner genau eine
                // `stimme`-Zeile: das Schlusszeichen, mit leerem Text. Eine
                // Liste, die nur daraus besteht, ist nicht leer - sie ergibt
                // aber einen leeren Satz. Am 14.09. um 01:49 stand Calvins
                // Frage "Bist du wach?" im Chat und darunter nichts, während
                // die Antwort "Ja." im Strom lag.
                .filter { !$0.isEmpty }
        }

        // Der TEXT zuerst: `antwort_teil` entsteht, sobald der Satz da ist,
        // die Aufnahme erst danach. Fehlt beides, steht die ganze Antwort da.
        let gesprochen = teile("stimme")
        let geschrieben = teile("antwort_teil")
        if !geschrieben.isEmpty, geschrieben.count >= gesprochen.count {
            return Self.fuegen(geschrieben)
        }
        return gesprochen.isEmpty ? (answer.text ?? "") : Self.fuegen(gesprochen)
    }

    /// Parts back into one text. A space between them is right almost always
    /// - but the PC sometimes cuts mid-word, and then "beob" + "achtet"
    /// became "beob achtet" on screen and "1202 Mi" + "B geteilt" aloud.
    /// Where a part ends inside a word and the next begins inside one, the
    /// two belong together without a space.
    static func fuegen(_ teile: [String]) -> String {
        var text = ""
        for teil in teile {
            guard !text.isEmpty else { text = teil; continue }
            let endetImWort = text.last.map { $0.isLetter || $0.isNumber } ?? false
            let beginntImWort = teil.first.map { $0.isLetter || $0.isNumber } ?? false
            // A capital or a sentence mark means a new word started properly.
            let neuerAnfang = teil.first.map { $0.isUppercase || !$0.isLetter } ?? true
            text += (endetImWort && beginntImWort && !neuerAnfang) ? teil : " " + teil
        }
        return text
    }

    /// Answers are read out - only to questions asked from here, so a phone
    /// in the pocket stays quiet when someone asks at the Mac.
    var voice = true
    /// Waiting for an answer to this question.
    private(set) var waitingFor: String?
    /// Speaking the answer to this question.
    private(set) var speakingFor: String?
    /// The conversation mode: answers play while the microphone stays open.
    var duplex: Bool {
        get { speaker.duplex }
        set { speaker.duplex = newValue }
    }

    /// What is being read out right now - to tell its echo from your voice.
    var speakingText: String? {
        guard let id = speakingFor,
              let a = entries.last(where: { $0.kind == "antwort" && $0.ref == id }) else { return nil }
        return answerText(a)
    }

    /// Called when an answer has been spoken - the conversation mode
    /// listens again then.
    @ObservationIgnored var answered: (() -> Void)?
    @ObservationIgnored private var asked: Set<String> = []
    @ObservationIgnored private var askedAt: [String: Date] = [:]

    /// How many questions are before this one in the queue.
    func ahead(of id: String) -> Int {
        state?.waiting.firstIndex(where: { $0.id == id }) ?? 0
    }

    /// The question something said now would be an addition to: yours,
    /// still without an answer, asked less than 30 s ago.
    var addingTo: String? {
        guard let w = waitingFor, let t = askedAt[w], Date().timeIntervalSince(t) < 30 else { return nil }
        return w
    }
    @ObservationIgnored private var fallback: [String: Task<Void, Never>] = [:]
    @ObservationIgnored private let speaker = Speaker()
    /// Recordings waiting their turn, sentence by sentence.
    @ObservationIgnored private var queue: [(id: String, path: String, closing: Bool)] = []
    @ObservationIgnored private var playing = false
    /// Answers whose closing mark came without a recording of its own.
    @ObservationIgnored private var ended: Set<String> = []

    private var client: BridgeClient? {
        machine.flatMap { Connection.bridge(for: $0) }.map { BridgeClient($0) }
    }

    /// Asks each computer whether the resident lives there.
    /// Wo der Bewohner wohnt - reihum bei allen Rechnern gefragt.
    ///
    /// Mit kurzer Frist je Rechner, und das ist keine Feinheit: ein Rechner,
    /// der offline ist (der PC war es fünf Tage), laesst den Aufruf ins Leere
    /// laufen, bis die Voreinstellung zuschlaegt. Weil diese Suche vor der
    /// Nachlade-Schleife stand, lief die App danach gar nichts mehr nach -
    /// keine Sitzungen, keine Dienste, keine Projekte, und kein Fehler, weil
    /// nichts fehlgeschlagen war. Ein halber Abend ging dafuer drauf
    /// (Calvin, 25.09.).
    func locate() async {
        for m in Connection.machines() {
            guard let b = Connection.bridge(for: m) else { continue }
            if let r = await Self.kurz(b) {
                machine = m
                state = r.resident
                return
            }
        }
        machine = nil
    }

    /// Ein Aufruf mit eigener Frist: was in drei Sekunden nicht da ist,
    /// interessiert hier nicht - es geht nur um die Frage, wo jemand wohnt.
    private static func kurz(_ b: Bridge) async -> ResidentBody? {
        await withTaskGroup(of: ResidentBody?.self) { gruppe in
            gruppe.addTask {
                try? await BridgeClient(b).get("api/resident", as: ResidentBody.self)
            }
            gruppe.addTask {
                try? await Task.sleep(for: .seconds(3))
                return nil
            }
            let erstes = await gruppe.next() ?? nil
            gruppe.cancelAll()
            return erstes
        }
    }

    func start() {
        guard stream == nil else { return }
        stream = Task { await run() }
        // The state changes without a journal line - last_check, the brake.
        poll = Task {
            while !Task.isCancelled {
                await refresh()
                try? await Task.sleep(for: .seconds(15))
            }
        }
    }

    func stop() {
        silence()
        stream?.cancel()
        poll?.cancel()
        stream = nil
        poll = nil
        connected = false
    }

    func refresh() async {
        if machine == nil { await locate() }
        guard let client else { return }
        do {
            state = try await client.get("api/resident", as: ResidentBody.self).resident
            problem = nil
        } catch {
            problem = Bridge.explain(error, on: machine?.name)
        }
    }

    private func run() async {
        while !Task.isCancelled {
            if machine == nil { await locate() }
            guard let client else {
                try? await Task.sleep(for: .seconds(15))
                continue
            }
            // Every connection from the start: the bridge counts anew after
            // a restart, and the journal it holds is short.
            var fresh: [ResidentEntry] = []
            var live = false
            var letzte = Date()
            do {
                for try await line in client.lines("api/resident/events", since: 0) {
                    guard let e = try? BridgeClient.cardDecoder().decode(ResidentEntry.self, from: Data(line.utf8))
                    else { continue }
                    connected = true
                    // DIE GRENZE. Die Brücke schickt sie ausdrücklich, seit
                    // klar ist, was Raten kostet: Vorher galt schon die
                    // zweite Zeile als "gerade passiert", und bei jeder
                    // neuen Verbindung wanderten fünfhundert alte Zeilen
                    // durch `heard` - im Gespräch also alle alten Ansprachen
                    // in die Abspielschlange, die frische Antwort dahinter.
                    if e.kind == "__live__" {
                        entries = fresh
                        live = true
                        continue
                    }
                    // Auch NACH der Grenze kann Nachgelesenes kommen: Die
                    // Brücke liest beim Start die letzten 200 KB Journal nach,
                    // und wer sich in dem Augenblick verbindet, bekommt das
                    // durch denselben Strom. Die Karte sagt selbst, was sie
                    // ist.
                    if live, e.live != false {
                        entries.append(e)
                        if entries.count > 600 { entries.removeFirst(entries.count - 600) }
                        heard(e)
                        if ["antrag", "entscheidung", "stop", "auftrag", "ergebnis", "fehler"].contains(e.kind) {
                            await refresh()
                        }
                    } else if live {
                        // Nachgelesenes nach der Grenze: zeigen, nicht hören.
                        entries.append(e)
                        if entries.count > 600 { entries.removeFirst(entries.count - 600) }
                    } else {
                        // Eine ältere Brücke kennt die Grenze nicht. Dann
                        // gilt: Was nach drei stillen Sekunden kommt, ist
                        // neu. Lieber eine Zeile zu spät live als den
                        // Rückstand für das Jetzt zu halten.
                        if Date().timeIntervalSince(letzte) > 3 {
                            entries = fresh
                            live = true
                            entries.append(e)
                            heard(e)
                        } else {
                            fresh.append(e)
                        }
                    }
                    letzte = Date()
                }
            } catch {
                problem = Bridge.explain(error, on: machine?.name)
            }
            // Bricht der Strom im Rückstand ab, wäre sonst nichts zu sehen.
            if !live, !fresh.isEmpty { entries = fresh }
            connected = false
            try? await Task.sleep(for: .seconds(3))
        }
    }

    // MARK: what you do

    @discardableResult
    private func act(_ path: String, _ body: some Encodable & Sendable) async -> String? {
        guard let client else { return "Bewohner nicht erreichbar" }
        do {
            let r = try await client.post(path, body, as: ResidentReply.self)
            if let s = r.resident { state = s }
            return r.ok == false ? (r.error ?? "abgelehnt") : nil
        } catch {
            return Bridge.explain(error, on: machine?.name)
        }
    }

    /// Whether it starts thinking at the first pause (see draft).
    var canDraft: Bool { state?.abilities.contains("entwurf") ?? false }
    @ObservationIgnored private var draftID: String?

    /// What you have said so far, while you still speak: the resident looks
    /// things up and starts on an answer, and says nothing until the
    /// question is sent. The question then goes under the same id.
    func draft(_ text: String) async {
        guard canDraft, let client else { return }
        if let r = try? await client.post("api/resident/talk", ResidentTalkBody(text: text, id: draftID, draft: true),
                                          as: ResidentTalkReply.self), let id = r.id {
            draftID = id
        }
    }

    /// Ask the resident something; it answers in the journal, then aloud.
    /// addTo: an earlier question of yours still without an answer - this
    /// goes with it, the resident answers both together.
    func talk(_ text: String, addTo: String? = nil, recording: URL? = nil) async -> String? {
        guard let client else { return "Bewohner nicht erreichbar" }
        let pending = draftID
        draftID = nil
        // How it was said goes with it - at most 5 MB, about two and a half minutes.
        var clip: String?
        if let recording {
            if let d = try? Data(contentsOf: recording), d.count <= 5_000_000 { clip = d.base64EncodedString() }
            try? FileManager.default.removeItem(at: recording)
        }
        do {
            let r = try await client.post("api/resident/talk",
                                          ResidentTalkBody(text: text, id: pending, draft: false,
                                                           zu: addTo, aufnahme: clip, stimme: voice),
                                          as: ResidentTalkReply.self)
            guard let id = r.id else { return r.error ?? "nicht angekommen" }
            asked.insert(id)
            askedAt[id] = Date()
            // An addition is answered under the question it belongs to.
            if addTo == nil { waitingFor = id }
            let waitID = addTo ?? id
            await refresh()
            // No answer at all - the resident is not running, or stuck. Say
            // so instead of thinking forever; behind other questions it
            // only waits its turn.
            Task {
                var waited = 0
                while waitingFor == waitID {
                    try? await Task.sleep(for: .seconds(15))
                    waited += 15
                    guard waitingFor == waitID else { return }
                    if ahead(of: waitID) > 0 { waited = 0 }
                    if waited >= 90 {
                        waitingFor = nil
                        problem = "Keine Antwort vom Bewohner – läuft er auf dem PC?"
                    }
                }
            }
            return nil
        } catch {
            return Bridge.explain(error, on: machine?.name)
        }
    }

    /// The conversation is open here - what the resident says on its own is
    /// read out then; otherwise the push is enough.
    var conversing = false

    /// A live journal line that belongs to a question asked from here.
    private func heard(_ e: ResidentEntry) {
        if e.kind == "ansprache" {
            guard conversing, voice else { return }
            let id = "ansprache-\(e.seq)"
            if let path = e.audio, !path.isEmpty {
                enqueue(id: id, path: path, closing: true)
            } else if let text = e.text, !text.isEmpty, speakingFor == nil {
                speakingFor = id
                speaker.say(text) { [weak self] in self?.spokeOut(id) }
            }
            return
        }
        guard let id = e.ref, asked.contains(id) else { return }
        switch e.kind {
        case "antwort":
            if waitingFor == id { waitingFor = nil }
            // An answer to an addition answers the question it belonged to.
            if let w = waitingFor, askedAt[id] != nil, entries.contains(where: { $0.kind == "frage" && $0.ref == id && $0.zu == w }) {
                waitingFor = nil
            }
            problem = nil
            guard voice, let text = e.text else { return }
            // Its recording is already playing or queued - no device voice.
            if speakingFor == id || queue.contains(where: { $0.id == id }) { return }
            // The PC's recording comes after the text; if it does not
            // come, the device reads the answer itself.
            fallback[id] = Task {
                try? await Task.sleep(for: .seconds(25))
                guard !Task.isCancelled else { return }
                fallback[id] = nil
                speakingFor = id
                speaker.say(text) { [weak self] in self?.spokeOut(id) }
            }
        case "stimme":
            // The first part (or the whole) cancels the device voice; later
            // parts join the queue behind it.
            // Any order: the first sentence's recording may come before the
            // answer's text line. Only questions asked from here get here.
            if e.final == true, e.recording == nil {
                // A closing mark without sound: the parts already queued are
                // all there is.
                ended.insert(id)
                if !playing, !queue.contains(where: { $0.id == id }), speakingFor == id { spokeOut(id) }
                return
            }
            guard voice, let path = e.recording else { return }
            fallback[id]?.cancel()
            fallback[id] = nil
            enqueue(id: id, path: path, closing: e.closing)
        default:
            break
        }
    }

    private func enqueue(id: String, path: String, closing: Bool) {
        queue.append((id, path, closing))
        speakingFor = id
        // Never stuck: "playing" with nothing to be heard is not playing.
        if playing && !speaker.speaking { playing = false }
        // The turn is claimed HERE, before the run starts. Two sentences
        // arriving in the same moment both found "not playing" and each
        // started a run; the second one's play() begins with stop(), so the
        // first sentence was cut off mid-word. That is how sentences went
        // missing from an answer.
        guard !playing else { return }
        playing = true
        Task { await playNext() }
    }

    /// One recording after the other; when the closing one has played, the
    /// answer is over.
    private func playNext() async {
        guard !queue.isEmpty, let client else {
            playing = false
            return
        }
        playing = true
        let item = queue.removeFirst()
        guard let data = try? await client.raw("api/resident/audio",
                                                query: [URLQueryItem(name: "path", value: item.path)]) else {
            await playNext()
            return
        }
        speaker.play(data) { [weak self] in
            guard let self else { return }
            if (item.closing || self.ended.contains(item.id)) && !self.queue.contains(where: { $0.id == item.id }) {
                self.spokeOut(item.id)
                // The claim is handed straight to the next answer's first
                // sentence, never let go in between - a sentence arriving in
                // that gap would have started a second run and cut this one.
                if self.queue.isEmpty {
                    self.playing = false
                } else {
                    Task { await self.playNext() }
                }
            } else if self.queue.isEmpty {
                // More sentences were announced but none has come: wait a
                // little, then take the answer as over. A last part that never
                // says it is the last must not leave the conversation waiting
                // for good - it would never listen again.
                self.playing = false
                Task { @MainActor in
                    try? await Task.sleep(for: .seconds(5))
                    if !self.playing, self.queue.isEmpty, self.speakingFor == item.id { self.spokeOut(item.id) }
                }
            } else {
                Task { await self.playNext() }
            }
        }
    }

    private func spokeOut(_ id: String) {
        if speakingFor == id { speakingFor = nil }
        answered?()
    }

    /// An answer once more - its recording if there is one, else the text.
    func replay(_ answer: ResidentEntry) {
        guard let id = answer.ref else { return }
        let parts = entries.filter { $0.kind == "stimme" && $0.ref == id && $0.recording != nil }
            .sorted { ($0.part ?? 0) < ($1.part ?? 0) }
        if !parts.isEmpty {
            silence()
            for (i, p) in parts.enumerated() {
                enqueue(id: id, path: p.recording!, closing: i == parts.count - 1)
            }
        } else if let text = answer.text {
            speakingFor = id
            speaker.say(text) { [weak self] in self?.spokeOut(id) }
        }
    }

    /// Softer while a voice may be talking into the answer.
    func duck(_ on: Bool) {
        guard ducked != on else { return }
        ducked = on
        speaker.duck(on)
    }
    @ObservationIgnored private var ducked = false

    func silence() {
        ducked = false
        speaker.stop()
        queue = []
        playing = false
        speakingFor = nil
        for t in fallback.values { t.cancel() }
        fallback = [:]
    }

    func setStopped(_ on: Bool) async -> String? { await act("api/resident/stop", ResidentStopBody(on: on)) }
    func wake() async -> String? { await act("api/resident/wake", ResidentEmptyBody()) }
    func say(_ text: String) async -> String? { await act("api/resident/say", ResidentSayBody(text: text)) }
    func decide(_ id: String, allow: Bool) async -> String? {
        await act("api/resident/decide", ResidentDecideBody(id: id, allow: allow))
    }

    func files() async -> [ResidentFile] {
        (try? await client?.get("api/resident/files", as: ResidentFilesBody.self).files) ?? []
    }

    func read(_ path: String) async -> String? {
        try? await client?.get("api/resident/file", query: [URLQueryItem(name: "path", value: path)],
                               as: ResidentFileBody.self).text
    }

    func write(_ path: String, text: String) async -> String? {
        await act("api/resident/file", ResidentWriteBody(path: path, text: text))
    }

    // MARK: who it is

    func selfView() async -> ResidentSelf? {
        try? await client?.get("api/resident/self", as: ResidentSelf.self)
    }

    /// Something to look at: a photo or a file goes into its eingang folder.
    func show(name: String, data: Data) async -> String? {
        await act("api/resident/eingang", ResidentShowBody(name: name, data: data.base64EncodedString()))
    }

    // MARK: memory

    /// What it remembers - the newest, or the best matches for a search.
    /// Die früheren Gespräche - das jüngste zuerst.
    ///
    /// Seit der Chat nur noch das laufende Gespräch zeigt, ist das der Weg
    /// zurück. Ohne ihn wäre mit den Nachrichten von gestern auch die
    /// Möglichkeit verschwunden, sie überhaupt noch einmal zu lesen.
    func gespraeche() async -> [ResidentGespraech] {
        (try? await client?.get("api/resident/gespraeche",
                                as: ResidentGespraecheBody.self).gespraeche) ?? []
    }

    /// Ein einzelnes früheres Gespräch mit seinen Paaren.
    func gespraech(_ id: String) async -> ResidentGespraechBody? {
        try? await client?.get("api/resident/gespraech",
                               query: [URLQueryItem(name: "id", value: id)],
                               as: ResidentGespraechBody.self)
    }

    func memories(_ query: String = "", art: String = "", limit: Int = 80) async -> (ResidentMemoryBody?, String?) {
        guard let client else { return (nil, "Bewohner nicht erreichbar") }
        var q = [URLQueryItem(name: "limit", value: String(limit))]
        if !query.isEmpty { q.append(URLQueryItem(name: "q", value: query)) }
        if !art.isEmpty { q.append(URLQueryItem(name: "art", value: art)) }
        do {
            let b = try await client.get("api/resident/memory", query: q, as: ResidentMemoryBody.self)
            return (b, b.error)
        } catch {
            return (nil, Bridge.explain(error, on: machine?.name))
        }
    }

    /// One memory and what replaced it, oldest first.
    func memoryChain(_ id: String) async -> [ResidentMemory] {
        (try? await client?.get("api/resident/memory", query: [URLQueryItem(name: "id", value: id)],
                                as: ResidentMemoryChain.self).chain) ?? []
    }

    /// "vergessen" or "korrigieren" - the resident takes it in on its next look.
    func changeMemory(_ id: String, aktion: String, text: String = "") async -> String? {
        guard let client else { return "Bewohner nicht erreichbar" }
        do {
            let r = try await client.post("api/resident/memory",
                                          ResidentMemoryChangeBody(id: id, aktion: aktion, text: text),
                                          as: ResidentMemoryReply.self)
            return r.ok == false ? (r.error ?? "abgelehnt") : nil
        } catch {
            return Bridge.explain(error, on: machine?.name)
        }
    }
}
