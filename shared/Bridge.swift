import Foundation
import Security

/// Where the bridge lives and how to prove who we are.
struct Bridge: Sendable, Hashable {
    let base: URL
    let token: String

    /// Reads the address `make token` prints: http://host:port/?token=…
    /// The address `make token` prints: "http://host:8780/?token=…". Read
    /// forgivingly - a copy from a chat or a note brings spaces, line breaks,
    /// a stray "†" or smart quotes along, and a token is only ever letters,
    /// digits, "-" and "_".
    static func parse(_ text: String) -> Bridge? {
        guard let base = firstMatch(#"https?://[A-Za-z0-9.\-]+(:[0-9]+)?"#, in: text).flatMap(URL.init(string:)),
              let token = firstMatch(#"token\s*=\s*([A-Za-z0-9_\-]{8,})"#, in: text, group: 1)
        else { return nil }
        return Bridge(base: base, token: token)
    }

    private static func firstMatch(_ pattern: String, in text: String, group: Int = 0) -> String? {
        guard let re = try? NSRegularExpression(pattern: pattern),
              let m = re.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              let r = Range(m.range(at: group), in: text) else { return nil }
        return String(text[r])
    }
}

/// What the bridge says when it refuses: {"error": "…"}.
private struct FailureBody: Decodable { var error: String? }

extension Bridge {
    /// An error in words that say what to do about it.
    ///
    /// `machine` is the computer whose bridge refused - and it has to be
    /// named. The text said "läuft sie am Mac" no matter which bridge failed,
    /// and the resident does not live on the Mac: the app talks to his
    /// computer directly. Someone reading that message went looking on the
    /// wrong machine.
    static func explain(_ error: Error, on machine: String? = nil) -> String {
        let ns = error as NSError
        if ns.domain == NSURLErrorDomain {
            switch ns.code {
            case NSURLErrorAppTransportSecurityRequiresSecureConnection:
                return "iOS lässt die unverschlüsselte Verbindung zur Brücke nicht zu."
            case NSURLErrorCannotConnectToHost, NSURLErrorTimedOut, NSURLErrorCannotFindHost,
                 NSURLErrorNotConnectedToInternet, NSURLErrorNetworkConnectionLost:
                let wo = machine.map { "auf \($0)" } ?? "auf dem Rechner, zu dem sie gehört"
                return "Brücke \(wo) nicht erreichbar – läuft sie dort, und ist Tailscale an diesem Telefon verbunden?"
            default:
                break
            }
        }
        return error.localizedDescription
    }
}

enum BridgeError: LocalizedError {
    case refused(Int, String)

    var errorDescription: String? {
        switch self {
        case .refused(401, _): "Der Zugangsschlüssel gilt nicht mehr."
        case .refused(_, let message): message
        }
    }
}

/// Talks to the bridge: plain JSON over HTTP, and the card stream over SSE.
struct BridgeClient: Sendable {
    let bridge: Bridge
    private let urlSession: URLSession
    /// Eigene Sitzung fuer die Kartenstroeme.
    ///
    /// Sie teilten sich vorher eine mit den gewoehnlichen Abrufen, und das
    /// legte die App still: ein Strom ist eine Verbindung, die absichtlich
    /// offen bleibt, und `httpMaximumConnectionsPerHost` ist auf iOS
    /// voreingestellt **vier**. Bei sieben Terminal-Sitzungen waren die
    /// Plaetze belegt, und jeder Abruf stand danach in der Warteschlange -
    /// ohne Frist, denn die zaehlt erst ab dem Beginn eines Aufrufs. Die
    /// Uebersicht blieb leer, ohne einen einzigen Fehler: „1 Versuch, nie
    /// geantwortet". Gefunden am 25.09., nachdem es einen Abend gekostet hat.
    private let stromSession: URLSession

    init(_ bridge: Bridge) {
        self.bridge = bridge
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 20
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        // Genug Plaetze fuer die Handvoll Abrufe, die gleichzeitig laufen.
        config.httpMaximumConnectionsPerHost = 8
        urlSession = URLSession(configuration: config)

        let strom = URLSessionConfiguration.default
        // Ein Strom schweigt lange und ist trotzdem gesund - eine Frist waere
        // hier falsch. Er darf aber die Abrufe nicht mehr verdraengen.
        strom.timeoutIntervalForRequest = 0
        strom.requestCachePolicy = .reloadIgnoringLocalCacheData
        strom.httpMaximumConnectionsPerHost = 12
        stromSession = URLSession(configuration: strom)
    }

    private static func decoder(snakeCase: Bool = true) -> JSONDecoder {
        let d = JSONDecoder()
        if snakeCase { d.keyDecodingStrategy = .convertFromSnakeCase }
        return d
    }

    private func request(_ path: String, query: [URLQueryItem] = [], method: String = "GET",
                         body: Data? = nil) -> URLRequest {
        var url = bridge.base.appending(path: path)
        if !query.isEmpty { url.append(queryItems: query) }
        var r = URLRequest(url: url)
        r.httpMethod = method
        r.setValue("Bearer \(bridge.token)", forHTTPHeaderField: "Authorization")
        if let body {
            r.httpBody = body
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return r
    }

    /// `snakeCase: false` keeps keys as the bridge sends them - for bodies
    /// that carry free-form dictionaries.
    func get<T: Decodable & Sendable>(_ path: String, query: [URLQueryItem] = [],
                                      as type: T.Type = T.self, snakeCase: Bool = true) async throws -> T {
        try await send(request(path, query: query), snakeCase: snakeCase)
    }

    /// `frist` fuer Aufrufe, die laenger dauern als die 20 Sekunden, die
    /// hier sonst gelten: das Update beendet erst alle Sitzungen, laesst brew
    /// laufen und holt sie zurueck. Ohne eigene Frist brach die App nach 20
    /// Sekunden ab, waehrend die Bruecke noch arbeitete - und das Blatt fiel
    /// in den Ausgangszustand zurueck, als waere nichts geschehen.
    func post<T: Decodable & Sendable>(_ path: String, _ body: some Encodable & Sendable,
                                       as type: T.Type = T.self,
                                       frist: TimeInterval? = nil) async throws -> T {
        var r = request(path, method: "POST", body: try JSONEncoder().encode(body))
        if let frist { r.timeoutInterval = frist }
        return try await send(r)
    }

    /// Fehler, die eine KALTE Leitung macht - nicht eine tote.
    ///
    /// Tailscale laesst einen ungenutzten Pfad verfallen. Der erste Versuch
    /// nach einer Viertelstunde Ruhe trifft dann auf einen Handschlag, der
    /// noch laeuft, und schlaegt fehl; der zweite kommt in Millisekunden
    /// durch. Ohne den zweiten Versuch stand am 13.09. um 19:08 "Bruecke
    /// nicht erreichbar" auf dem Telefon, waehrend die Bruecke die ganze Zeit
    /// in 14 ms antwortete.
    private static let kalteLeitung: Set<Int> = [
        NSURLErrorCannotConnectToHost, NSURLErrorTimedOut,
        NSURLErrorNetworkConnectionLost, NSURLErrorCannotFindHost]

    /// Einmal noch, kurz gewartet. Nur bei einer kalten Leitung, und nur
    /// einmal: Ein Rechner, der wirklich aus ist, soll nicht zweimal so lange
    /// brauchen, bis das jemand erfaehrt.
    private func nochmal(_ error: Error) -> Bool {
        let ns = error as NSError
        return ns.domain == NSURLErrorDomain && Self.kalteLeitung.contains(ns.code)
    }

    private func daten(_ r: URLRequest) async throws -> (Data, URLResponse) {
        do {
            return try await urlSession.data(for: r)
        } catch {
            guard nochmal(error) else { throw error }
            try? await Task.sleep(for: .milliseconds(400))
            return try await urlSession.data(for: r)
        }
    }

    private func send<T: Decodable & Sendable>(_ r: URLRequest, snakeCase: Bool = true) async throws -> T {
        let (data, response) = try await daten(r)
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else {
            let message = (try? JSONDecoder().decode(FailureBody.self, from: data))?.error
                ?? HTTPURLResponse.localizedString(forStatusCode: code)
            throw BridgeError.refused(code, message)
        }
        return try Self.decoder(snakeCase: snakeCase).decode(T.self, from: data)
    }

    /// One file, as it is - the body is the file, the name goes in a header.
    func upload(_ key: String, name: String, data: Data, mediaType: String) async throws -> UploadBody {
        var r = request("api/sessions/\(key)/upload", method: "POST", body: data)
        r.setValue(mediaType, forHTTPHeaderField: "Content-Type")
        r.setValue(name.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? "anhang",
                   forHTTPHeaderField: "X-Filename")
        r.timeoutInterval = 120
        return try await send(r)
    }

    /// The live card stream of a session, from `since` on. Ends when the
    /// connection drops; the caller reconnects with the last seq it saw, and
    /// the bridge replays what was missed.
    /// The decoder the card stream uses - for cards kept on the device too.
    static func cardDecoder() -> JSONDecoder { decoder() }

    /// A GET whose answer is kept as it came (the history, for the cache).
    func raw(_ path: String, query: [URLQueryItem] = []) async throws -> Data {
        let r = request(path, query: query)
        let (data, response) = try await daten(r)
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else { throw BridgeError.refused(code, "Abruf abgelehnt") }
        return data
    }

    /// A GET of something big, straight to a file on disk.
    ///
    /// The sealed blob of a handover is the size git refused in the first
    /// place - holding it in memory on a phone is how that ends badly.
    func rohInDatei(_ path: String) async throws -> URL {
        var r = request(path)
        r.timeoutInterval = 600
        let (datei, antwort) = try await urlSession.download(for: r)
        let code = (antwort as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else {
            try? FileManager.default.removeItem(at: datei)
            throw BridgeError.refused(code, "Abruf abgelehnt")
        }
        return datei
    }

    /// A POST whose body is a file, not JSON - the other half of the same trip.
    func rohAusDatei<T: Decodable & Sendable>(_ path: String, datei: URL,
                                              as type: T.Type = T.self) async throws -> T {
        var r = request(path, method: "POST")
        r.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        r.timeoutInterval = 600
        let (data, antwort) = try await urlSession.upload(for: r, fromFile: datei)
        let code = (antwort as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else {
            let grund = (try? JSONDecoder().decode(Fehlertext.self, from: data))?.grund
            throw BridgeError.refused(code, grund ?? "Abgelehnt")
        }
        return try Self.decoder().decode(T.self, from: data)
    }

    /// Was die Bruecke sagt, wenn sie etwas nicht annimmt.
    private struct Fehlertext: Decodable { var grund: String? }

    /// Any other server-sent stream, as its JSON lines - the resident's journal.
    func lines(_ path: String, since: Int) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var r = request(path, query: [URLQueryItem(name: "since", value: String(since))])
                    r.timeoutInterval = 45
                    let (bytes, response) = try await stromSession.bytes(for: r)
                    let code = (response as? HTTPURLResponse)?.statusCode ?? 0
                    guard code == 200 else { throw BridgeError.refused(code, "Strom abgelehnt") }
                    for try await line in bytes.lines where line.hasPrefix("data: ") {
                        continuation.yield(String(line.dropFirst(6)))
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    func events(_ key: String, since: Int) -> AsyncThrowingStream<Incoming, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var r = request("api/sessions/\(key)/events",
                                    query: [URLQueryItem(name: "since", value: String(since))])
                    // Idle between cards is normal; the bridge sends a
                    // keepalive every 20 s, so this only trips on a dead
                    // link - a Mac gone to sleep shows within 45 s.
                    r.timeoutInterval = 45
                    let (bytes, response) = try await stromSession.bytes(for: r)
                    let code = (response as? HTTPURLResponse)?.statusCode ?? 0
                    guard code == 200 else { throw BridgeError.refused(code, "Strom abgelehnt") }
                    let decoder = Self.decoder()
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data: ") else { continue }
                        let json = String(line.dropFirst(6))
                        if let card = try? decoder.decode(Card.self, from: Data(json.utf8)) {
                            continuation.yield(Incoming(card: card, line: json))
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}

/// One computer running a bridge - the Mac, a Pi, a Windows machine. Each
/// has its own token: it opens every session on that computer, and only there.
struct Machine: Codable, Sendable, Hashable, Identifiable {
    let id: String
    /// What the bridge calls itself - also how a notification says where it
    /// came from.
    var name: String
    let base: URL
}

/// Where the computers are kept: the list in the defaults, each token in the
/// keychain. On the Mac its own bridge is always in the list, read from its
/// config.
enum Connection {
    private static let listKey = "iris.machines"
    private static let currentKey = "iris.current"
    // From before there could be more than one computer.
    private static let oldBaseKey = "iris.base"
    private static let oldTokenKey = "iris.token"

    private static func tokenKey(_ id: String) -> String { "iris.token.\(id)" }

    #if DEBUG
    /// The simulator is pointed at a bridge from outside, so a screenshot or
    /// a UI test never needs a pasted token:
    /// SIMCTL_CHILD_IRIS_URL=… xcrun simctl launch …
    private static var fromEnvironment: Bridge? {
        ProcessInfo.processInfo.environment["IRIS_URL"].flatMap(Bridge.parse)
    }
    #endif

    static func machines() -> [Machine] {
        #if DEBUG
        if let b = fromEnvironment { return [Machine(id: "env", name: b.base.host ?? "Mac", base: b.base)] }
        #endif
        migrate()
        var list = stored()
        #if os(macOS)
        if let b = local(), !list.contains(where: { $0.base == b.base }) {
            list.insert(Machine(id: "local", name: "Dieser Mac", base: b.base), at: 0)
        }
        #endif
        return list
    }

    private static func stored() -> [Machine] {
        guard let data = UserDefaults.standard.data(forKey: listKey),
              let list = try? JSONDecoder().decode([Machine].self, from: data) else { return [] }
        return list
    }

    private static func store(_ list: [Machine]) {
        let kept = list.filter { $0.id != "env" && $0.id != "local" }
        UserDefaults.standard.set(try? JSONEncoder().encode(kept), forKey: listKey)
    }

    /// The one connection from before becomes the first computer in the list.
    private static func migrate() {
        guard let s = UserDefaults.standard.string(forKey: oldBaseKey), let base = URL(string: s),
              let token = Keychain.read(oldTokenKey) else { return }
        var list = stored()
        if !list.contains(where: { $0.base == base }) {
            let m = Machine(id: UUID().uuidString, name: base.host ?? "Mac", base: base)
            list.append(m)
            Keychain.write(token, for: tokenKey(m.id))
            store(list)
            if currentID == nil { currentID = m.id }
        }
        UserDefaults.standard.removeObject(forKey: oldBaseKey)
        Keychain.delete(oldTokenKey)
    }

    static func bridge(for m: Machine) -> Bridge? {
        #if DEBUG
        if m.id == "env" { return fromEnvironment }
        #endif
        #if os(macOS)
        if m.id == "local" { return local() }
        #endif
        return Keychain.read(tokenKey(m.id)).map { Bridge(base: m.base, token: $0) }
    }

    /// The computer a notification names - the one in use when it names none.
    static func bridge(named name: String?) -> Bridge? {
        let list = machines()
        let m = name.flatMap { n in list.first { $0.name == n } } ?? current(in: list)
        return m.flatMap(bridge(for:))
    }

    static var currentID: String? {
        get { UserDefaults.standard.string(forKey: currentKey) }
        set { UserDefaults.standard.set(newValue, forKey: currentKey) }
    }

    static func current(in list: [Machine]) -> Machine? {
        list.first { $0.id == currentID } ?? list.first
    }

    /// The bridge of the computer in use.
    static func restore() -> Bridge? { current(in: machines()).flatMap(bridge(for:)) }

    /// The same address a second time renews its token instead of adding a twin.
    @discardableResult
    static func add(_ b: Bridge, name: String) -> Machine {
        var list = stored()
        let m: Machine
        if let existing = list.first(where: { $0.base == b.base }) {
            m = existing
        } else {
            m = Machine(id: UUID().uuidString, name: name, base: b.base)
            list.append(m)
            store(list)
        }
        Keychain.write(b.token, for: tokenKey(m.id))
        currentID = m.id
        return m
    }

    static func rename(_ id: String, to name: String) {
        store(stored().map { m in
            var m = m
            if m.id == id { m.name = name }
            return m
        })
    }

    static func remove(_ id: String) {
        store(stored().filter { $0.id != id })
        Keychain.delete(tokenKey(id))
        if currentID == id { currentID = machines().first?.id }
    }

    /// Every computer, for what goes to all of them - the push address, the
    /// refresh in the background.
    static func all() -> [Bridge] { machines().compactMap(bridge(for:)) }

    #if os(macOS)
    /// On the Mac the bridge runs on this very machine: port and token are
    /// read from its own config, nothing to paste.
    static func local() -> Bridge? {
        let path = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".config/iris/config.json")
        guard let data = try? Data(contentsOf: path),
              let cfg = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let token = cfg["token"] as? String, !token.isEmpty else { return nil }
        let port = cfg["port"] as? Int ?? 8780
        guard let base = URL(string: "http://127.0.0.1:\(port)") else { return nil }
        return Bridge(base: base, token: token)
    }
    #endif
}

enum Keychain {
    /// Unter welchem Namen die Token liegen. Aus der Info.plist
    /// (IrisSchluesselbund, gesetzt aus apple.env), nicht aus der Bundle-ID:
    /// die ist am Mac eine andere als auf dem Telefon, und ein Name, der sich
    /// mit ihr verschiebt, laesst gespeicherte Token spurlos verschwinden.
    /// Fehlt der Eintrag, ist die App falsch gebaut - dann lieber ein fester
    /// Name als einer, der nach der jeweiligen App klingt.
    private static let service: String =
        (Bundle.main.object(forInfoDictionaryKey: "IrisSchluesselbund") as? String)
            .flatMap { $0.isEmpty || $0.hasPrefix("$(") ? nil : $0 } ?? "iris"

    private static func query(_ key: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: key]
    }

    static func write(_ value: String, for key: String) {
        SecItemDelete(query(key) as CFDictionary)
        var add = query(key)
        add[kSecValueData as String] = Data(value.utf8)
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(add as CFDictionary, nil)
    }

    static func read(_ key: String) -> String? {
        var q = query(key)
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess,
              let data = out as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func delete(_ key: String) {
        SecItemDelete(query(key) as CFDictionary)
    }
}

/// A card as it came over the wire: decoded, and the line itself - which is
/// what the device keeps (CardCache).
struct Incoming: Sendable {
    let card: Card
    let line: String
}

