import Foundation
import Observation
import SwiftUI
import WatchConnectivity

/// What the watch shows, as the iPhone last told it.
@MainActor @Observable
final class WatchStore {
    static let brass = Color(red: 0.84, green: 0.71, blue: 0.47)

    private(set) var machines: [WatchLink.Machine] = []
    private(set) var sessions: [WatchLink.SessionRow] = []
    private(set) var problem: String?
    @ObservationIgnored private let link = PhoneLink()

    init() { link.start() }

    func overview() async { take(await ask(.init(op: "overview"))) }
    func use(_ m: WatchLink.Machine) async { take(await ask(.init(op: "use", machine: m.id))) }

    func session(_ key: String) async -> WatchLink.SessionDetail? {
        await ask(.init(op: "session", key: key))?.session
    }

    func decide(_ key: String, _ requestId: String, allow: Bool) async -> WatchLink.SessionDetail? {
        await ask(.init(op: "decide", key: key, requestId: requestId, allow: allow))?.session
    }

    func send(_ key: String, _ text: String) async -> WatchLink.SessionDetail? {
        await ask(.init(op: "send", key: key, text: text))?.session
    }

    func interrupt(_ key: String) async -> WatchLink.SessionDetail? {
        await ask(.init(op: "interrupt", key: key))?.session
    }

    private func take(_ r: WatchLink.Reply?) {
        guard let r else { return }
        machines = r.machines ?? machines
        sessions = r.sessions ?? sessions
    }

    private func ask(_ request: WatchLink.Request) async -> WatchLink.Reply? {
        switch await link.send(request) {
        case .answer(let reply):
            problem = reply.ok ? nil : reply.error
            return reply
        case .failed(let message):
            problem = message
            return nil
        }
    }
}

/// WatchConnectivity on the watch. Its callbacks come on queues of their own,
/// so it stays off the main actor; answers are handed back as values.
final class PhoneLink: NSObject, WCSessionDelegate, @unchecked Sendable {
    enum Outcome: Sendable {
        case answer(WatchLink.Reply)
        case failed(String)
    }

    func start() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {}

    func send(_ request: WatchLink.Request) async -> Outcome {
        let s = WCSession.default
        guard s.activationState == .activated else { return .failed("Verbindung zum iPhone startet …") }
        guard s.isReachable else { return .failed("iPhone nicht erreichbar") }
        return await withCheckedContinuation { c in
            s.sendMessageData(WatchLink.encode(request), replyHandler: { data in
                if let reply = WatchLink.decode(WatchLink.Reply.self, data) {
                    c.resume(returning: .answer(reply))
                } else {
                    c.resume(returning: .failed("Antwort vom iPhone unlesbar"))
                }
            }, errorHandler: { error in
                c.resume(returning: .failed(error.localizedDescription))
            })
        }
    }
}
