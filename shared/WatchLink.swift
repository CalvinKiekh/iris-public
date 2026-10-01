import Foundation

/// What the watch asks the iPhone and what comes back. The watch cannot reach
/// the bridges itself - they live on the Tailscale network, and there is no
/// Tailscale on the watch - so the iPhone asks for it and answers
/// (WatchConnectivity). Plain JSON both ways.
enum WatchLink {
    struct Request: Codable, Sendable {
        /// "overview", "use", "session", "decide", "send", "interrupt"
        var op: String
        var key: String?
        var requestId: String?
        var allow: Bool?
        var text: String?
        var machine: String?
    }

    struct Machine: Codable, Sendable, Hashable, Identifiable {
        var id: String
        var name: String
        var current: Bool
    }

    struct SessionRow: Codable, Sendable, Hashable, Identifiable {
        var id: String
        var title: String
        var busy: Bool
        var asks: Int
    }

    /// An approval or a question waiting in the session.
    struct Ask: Codable, Sendable, Hashable {
        var id: String
        var title: String
        var detail: String
        var isQuestion: Bool
        var options: [String]
    }

    struct SessionDetail: Codable, Sendable {
        var key: String
        var title: String
        var status: String
        var busy: Bool
        var doing: String?
        var lastAnswer: String
        var ask: Ask?
        var canStop: Bool
        var ended: Bool
    }

    struct Reply: Codable, Sendable {
        var ok: Bool
        var error: String?
        var machines: [Machine]?
        var sessions: [SessionRow]?
        var session: SessionDetail?
    }

    static func encode<T: Encodable>(_ value: T) -> Data { (try? JSONEncoder().encode(value)) ?? Data() }
    static func decode<T: Decodable>(_ type: T.Type, _ data: Data) -> T? { try? JSONDecoder().decode(type, from: data) }
}
