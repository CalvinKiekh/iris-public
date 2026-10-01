import Foundation

/// Messages that have not reached the bridge yet - the phone was offline,
/// the Mac asleep, the bridge restarting. They wait here, on the phone and
/// across app restarts, and go out as soon as the bridge answers again.
///
/// Each carries an id that goes along with every attempt: when an attempt
/// did arrive but its answer got lost, the repeat is recognised by the
/// bridge and not sent a second time.
struct Outgoing: Codable, Sendable, Identifiable {
    struct File: Codable, Sendable {
        let name: String
        let path: String
        let mediaType: String
    }

    let id: String
    let text: String
    let files: [File]
    let created: Date
}

enum Outbox {
    private static func key(_ session: String) -> String { "iris.outbox.\(session)" }

    private static var folder: URL {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("outbox", isDirectory: true)
    }

    static func load(_ session: String) -> [Outgoing] {
        guard let data = UserDefaults.standard.data(forKey: key(session)) else { return [] }
        return (try? JSONDecoder().decode([Outgoing].self, from: data)) ?? []
    }

    static func save(_ items: [Outgoing], for session: String) {
        UserDefaults.standard.set(try? JSONEncoder().encode(items), forKey: key(session))
    }

    /// Keeps the attachments as files, so a message that waits survives the
    /// app being closed - its pictures included.
    static func make(text: String, attachments: [Attachment]) -> Outgoing {
        let id = UUID().uuidString
        let dir = folder.appendingPathComponent(id, isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let files = attachments.compactMap { a -> Outgoing.File? in
            let url = dir.appendingPathComponent(a.name)
            guard (try? a.data.write(to: url)) != nil else { return nil }
            return Outgoing.File(name: a.name, path: url.path, mediaType: a.mediaType)
        }
        return Outgoing(id: id, text: text, files: files, created: Date())
    }

    static func discard(_ item: Outgoing) {
        try? FileManager.default.removeItem(at: folder.appendingPathComponent(item.id, isDirectory: true))
    }

    /// Worth trying again later: anything that did not end in an answer from
    /// the bridge - no network, a refused or dropped connection, a timeout.
    /// Only an answer with a status (the bridge said no) is final: waiting
    /// would not change it. Better to hold a message once too often than to
    /// drop one that only met a bad moment.
    static func unreachable(_ error: Error) -> Bool {
        if error is BridgeError { return false }
        let ns = error as NSError
        return ns.domain == NSURLErrorDomain && ns.code != NSURLErrorCancelled
    }
}
