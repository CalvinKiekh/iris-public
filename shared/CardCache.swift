import Foundation

/// The conversation as far as this device has already seen it, kept on
/// disk: opening a session shows it at once, and only what came since is
/// asked for (`events?since=<last number>`). Before, every open fetched the
/// whole feed again - thousands of cards - and whatever arrived late of it
/// was counted as new.
///
/// Per session a folder in the caches: the history from before the bridge
/// watched (as the bridge sent it), the cards since as raw lines, and the
/// last number. Raw lines, so nothing has to learn to encode a card.
enum CardCache {
    struct Stored: Sendable {
        var history: [Card]
        var feed: [Card]
        var lastSeq: Int
    }

    private struct Meta: Codable {
        var lastSeq: Int
        var lines: Int
    }

    /// The feed keeps this many cards - what the bridge keeps as well.
    static let keep = 3000

    private static var root: URL {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("cards", isDirectory: true)
    }

    private static func folder(_ key: String) -> URL {
        let safe = key.replacingOccurrences(of: "/", with: "_")
        return root.appendingPathComponent(safe, isDirectory: true)
    }

    static func load(_ key: String) -> Stored? {
        let dir = folder(key)
        guard let m = try? JSONDecoder().decode(Meta.self, from: Data(contentsOf: dir.appendingPathComponent("meta.json")))
        else { return nil }
        let decoder = BridgeClient.cardDecoder()
        let history = (try? Data(contentsOf: dir.appendingPathComponent("history.json")))
            .flatMap { try? decoder.decode(HistoryBody.self, from: $0).cards } ?? []
        var feed: [Card] = []
        if let text = try? String(contentsOf: dir.appendingPathComponent("feed.jsonl"), encoding: .utf8) {
            // Strictly rising numbers: a card the background refresh and an
            // open session both wrote down is shown once.
            var last = 0
            for line in text.split(separator: "\n") {
                if let card = try? decoder.decode(Card.self, from: Data(line.utf8)),
                   let seq = card.seq, seq > last {
                    feed.append(card)
                    last = seq
                }
            }
        }
        return Stored(history: history, feed: feed, lastSeq: m.lastSeq)
    }

    static func saveHistory(_ raw: Data, for key: String) {
        let dir = folder(key)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try? raw.write(to: dir.appendingPathComponent("history.json"), options: .atomic)
        if (try? Data(contentsOf: dir.appendingPathComponent("meta.json"))) == nil {
            writeMeta(Meta(lastSeq: 0, lines: 0), in: dir)
        }
    }

    /// Adds cards as they came over the wire, and the number of the last.
    static func append(_ lines: [String], lastSeq: Int, for key: String) {
        guard !lines.isEmpty else { return }
        let dir = folder(key)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let file = dir.appendingPathComponent("feed.jsonl")
        let chunk = Data((lines.joined(separator: "\n") + "\n").utf8)
        if let handle = try? FileHandle(forWritingTo: file) {
            _ = try? handle.seekToEnd()
            try? handle.write(contentsOf: chunk)
            try? handle.close()
        } else {
            try? chunk.write(to: file, options: .atomic)
        }
        var m = (try? JSONDecoder().decode(Meta.self, from: Data(contentsOf: dir.appendingPathComponent("meta.json"))))
            ?? Meta(lastSeq: 0, lines: 0)
        m.lastSeq = lastSeq
        m.lines += lines.count
        if m.lines > keep * 2 { m.lines = compact(file) }
        writeMeta(m, in: dir)
    }

    /// The bridge started counting afresh - what is here no longer matches.
    static func clear(_ key: String) {
        try? FileManager.default.removeItem(at: folder(key))
    }

    /// Sessions seen lately, newest first - what a refresh in the
    /// background goes through.
    static func recentKeys(limit: Int = 12) -> [String] {
        let fm = FileManager.default
        let dirs = (try? fm.contentsOfDirectory(at: root, includingPropertiesForKeys: [.contentModificationDateKey])) ?? []
        return dirs
            .compactMap { url -> (String, Date)? in
                let date = (try? url.appendingPathComponent("meta.json")
                    .resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? nil
                return date.map { (url.lastPathComponent, $0) }
            }
            .sorted { $0.1 > $1.1 }
            .prefix(limit)
            .map(\.0)
    }

    static func lastSeq(_ key: String) -> Int {
        (try? JSONDecoder().decode(Meta.self, from: Data(contentsOf: folder(key).appendingPathComponent("meta.json"))))?.lastSeq ?? 0
    }

    private static func writeMeta(_ m: Meta, in dir: URL) {
        if let data = try? JSONEncoder().encode(m) {
            try? data.write(to: dir.appendingPathComponent("meta.json"), options: .atomic)
        }
    }

    /// Keeps the last `keep` lines. Returns how many are left.
    private static func compact(_ file: URL) -> Int {
        guard let text = try? String(contentsOf: file, encoding: .utf8) else { return 0 }
        let lines = text.split(separator: "\n").suffix(keep)
        try? Data((lines.joined(separator: "\n") + "\n").utf8).write(to: file, options: .atomic)
        return lines.count
    }
}
