import Foundation
import WatchConnectivity

/// The watch's way to the bridges: it asks here, this app asks the bridge of
/// the computer in use and answers. WatchConnectivity wakes the app in the
/// background for it, so the iPhone can stay in the pocket.
final class WatchRelay: NSObject, WCSessionDelegate, @unchecked Sendable {
    static let shared = WatchRelay()

    func start() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {}
    func sessionDidBecomeInactive(_ session: WCSession) {}
    func sessionDidDeactivate(_ session: WCSession) { WCSession.default.activate() }

    /// Called on a queue of WatchConnectivity's own; the answer is worked out
    /// on the main thread, where the app's models live.
    func session(_ session: WCSession, didReceiveMessageData data: Data, replyHandler: @escaping (Data) -> Void) {
        let reply = Reply(send: replyHandler)
        guard let request = WatchLink.decode(WatchLink.Request.self, data) else {
            reply.send(WatchLink.encode(WatchLink.Reply(ok: false, error: "Anfrage unlesbar")))
            return
        }
        Task { @MainActor in
            reply.send(WatchLink.encode(await WatchRelay.handle(request)))
        }
    }

    /// WatchConnectivity's reply closure, carried over to the main thread.
    private struct Reply: @unchecked Sendable {
        let send: (Data) -> Void
    }

    @MainActor
    static func handle(_ r: WatchLink.Request) async -> WatchLink.Reply {
        let app = AppModel.shared
        switch r.op {
        case "overview":
            await app.refresh()
            return overview(app)
        case "use":
            if let id = r.machine, let m = app.machines.first(where: { $0.id == id }) {
                app.use(m)
                await app.refresh()
            }
            return overview(app)
        case "session":
            guard let key = r.key else { return .init(ok: false, error: "Keine Sitzung") }
            return .init(ok: true, session: detail(await loaded(key, in: app)))
        case "decide":
            guard let key = r.key, let rid = r.requestId else { return .init(ok: false, error: "Keine Freigabe") }
            let m = await loaded(key, in: app)
            guard let d = m.decisions.first(where: { $0.id == rid }) else {
                return .init(ok: false, error: "Die Freigabe ist nicht mehr offen")
            }
            await m.answer(d, allow: r.allow ?? false)
            return .init(ok: true, session: detail(m))
        case "send":
            guard let key = r.key, let text = r.text, !text.isEmpty else { return .init(ok: false, error: "Nichts zu senden") }
            // An open question takes the text as its answer - a picked option too.
            let m = await loaded(key, in: app)
            let sent = await m.send(text)
            return .init(ok: sent, error: sent ? nil : "Nicht gesendet", session: detail(m))
        case "interrupt":
            guard let key = r.key else { return .init(ok: false, error: "Keine Sitzung") }
            let m = await loaded(key, in: app)
            await m.interrupt()
            return .init(ok: true, session: detail(m))
        default:
            return .init(ok: false, error: "Unbekannte Anfrage")
        }
    }

    @MainActor
    private static func overview(_ app: AppModel) -> WatchLink.Reply {
        let machines = app.machines.map { WatchLink.Machine(id: $0.id, name: $0.name, current: $0.id == app.machine?.id) }
        let rows = app.sessions.filter { !$0.exited }.map {
            WatchLink.SessionRow(id: $0.key, title: $0.title.isEmpty ? $0.label : $0.title,
                                 busy: $0.busy, asks: $0.openAsks)
        }
        return .init(ok: true, machines: machines, sessions: rows)
    }

    /// The session's model with its cards in: started if it was not, and
    /// given a moment to catch up with the bridge.
    @MainActor
    private static func loaded(_ key: String, in app: AppModel) async -> SessionModel {
        let m = app.model(for: key)
        m.start()
        for _ in 0..<20 where m.settling {
            try? await Task.sleep(for: .milliseconds(200))
        }
        return m
    }

    @MainActor
    private static func detail(_ m: SessionModel) -> WatchLink.SessionDetail {
        let status: String
        if m.ended { status = "beendet" }
        // Den Rechner benennen, nicht "Mac" raten: Eine Sitzung kann auf dem
        // PC laufen, und der Bewohner lebt ohnehin dort.
        else if !m.connected { status = (m.app?.machine?.name ?? "Brücke") + " nicht erreichbar" }
        else if m.busy, let since = m.busySince { status = "läuft seit " + Fmt.clock(Date().timeIntervalSince(since)) }
        else { status = m.busy ? "arbeitet" : "bereit" }
        let answer = m.turns.last(where: { $0.kind == .claude && !$0.text.isEmpty })?.text ?? ""
        let ask = m.decisions.first.map { d in
            WatchLink.Ask(id: d.id, title: d.title, detail: d.detail, isQuestion: d.isQuestion,
                          options: d.questions.first?.options.map(\.label) ?? [])
        }
        let doing = m.busy ? [m.verb, m.doing].compactMap { $0 }.joined(separator: " · ") : nil
        return .init(key: m.key, title: m.title, status: status, busy: m.busy,
                     doing: doing?.isEmpty == false ? doing : nil,
                     lastAnswer: String(answer.prefix(600)), ask: ask,
                     canStop: m.busy && (!m.isTerminal || m.info?.typable == true), ended: m.ended)
    }
}
