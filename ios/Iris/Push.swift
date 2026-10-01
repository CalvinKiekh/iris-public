import SwiftUI
import UIKit
import UserNotifications

/// Notifications. What needs you reaches you - and the answer is on the
/// notification itself: allow or deny from the lock screen or the watch,
/// without opening the app.
enum Notifications {
    static let allowAction = "ERLAUBEN"
    static let denyAction = "ABLEHNEN"
    static let replyAction = "ANTWORTEN"
    static let grantAction = "GENEHMIGEN"
    static let refuseAction = "VERWEIGERN"

    /// The session on screen right now. Its notifications stay quiet - the
    /// same thing is already in front of you.
    @MainActor static var visibleSession: String?

    static func categories() -> Set<UNNotificationCategory> {
        // Allowing runs something on the Mac, so it wants an unlocked phone -
        // or the watch on the wrist. Denying never does harm.
        let allow = UNNotificationAction(identifier: allowAction, title: "Erlauben",
                                         options: [.authenticationRequired])
        let deny = UNNotificationAction(identifier: denyAction, title: "Ablehnen", options: [.destructive])
        let reply = UNTextInputNotificationAction(identifier: replyAction, title: "Antworten",
                                                  options: [.authenticationRequired],
                                                  textInputButtonTitle: "Senden",
                                                  textInputPlaceholder: "Antwort …")
        return [
            UNNotificationCategory(identifier: "FREIGABE", actions: [allow, deny], intentIdentifiers: [], options: []),
            UNNotificationCategory(identifier: "FRAGE", actions: [reply], intentIdentifiers: [], options: []),
            // Fertig heisst oft: hier ist der naechste Schritt faellig. Dafuer
            // muss man die App nicht oeffnen - die Antwort geht aus der
            // Mitteilung heraus in die Sitzung, wie in einem
            // Nachrichtenprogramm.
            UNNotificationCategory(identifier: "FERTIG", actions: [reply], intentIdentifiers: [], options: []),
            // The resident asks to move a limit - you decide, from the lock screen too.
            UNNotificationCategory(identifier: "ANTRAG", actions: [
                UNNotificationAction(identifier: grantAction, title: "Genehmigen", options: [.authenticationRequired]),
                UNNotificationAction(identifier: refuseAction, title: "Ablehnen", options: [.destructive]),
            ], intentIdentifiers: [], options: []),
        ]
    }

    /// What iris put into a push, read back.
    struct Payload: Sendable {
        var kind: String?
        var key: String?
        var requestId: String?
        var question: String?
        /// Which computer sent it - answers go back there.
        var machine: String?
        /// A resident's request ("antrag").
        var id: String?

        init(_ info: [AnyHashable: Any]) {
            let iris = info["iris"] as? [String: Any] ?? [:]
            kind = iris["kind"] as? String
            key = iris["key"] as? String
            requestId = iris["request_id"] as? String
            question = iris["question"] as? String
            machine = iris["machine"] as? String
            id = iris["id"] as? String
        }
    }

    @MainActor static func start() async {
        let center = UNUserNotificationCenter.current()
        var options: UNAuthorizationOptions = [.alert, .sound, .badge]
        #if DEBUG
        // Driven from outside (simulator runs): ask quietly, so no system
        // dialog blocks a screen nobody can tap.
        if ProcessInfo.processInfo.environment["IRIS_URL"] != nil { options.insert(.provisional) }
        #endif
        let granted = (try? await center.requestAuthorization(options: options)) ?? false
        // On every launch, not only the first: a reinstall brings a new
        // token, and the bridge must not keep pushing to the dead one.
        if granted { UIApplication.shared.registerForRemoteNotifications() }
    }

    private static let tokenKey = "iris.pushToken"

    /// After a computer was added: it gets this phone's address as well.
    static func registerAgain() async {
        guard let token = UserDefaults.standard.string(forKey: tokenKey) else { return }
        await register(token: token)
    }

    /// Every computer gets this phone's address - each one pushes on its own.
    static func register(token: String) async {
        UserDefaults.standard.set(token, forKey: tokenKey)
        #if DEBUG
        let env = "sandbox"
        #else
        let env = "production"
        #endif
        let name = await MainActor.run { UIDevice.current.name }
        for bridge in Connection.all() {
            _ = try? await BridgeClient(bridge).post("api/push/register",
                                                     RegisterBody(token: token, env: env, name: name),
                                                     as: OkBody.self)
        }
    }

    /// The answer given on the notification, sent the same way the app sends it.
    static func answer(_ p: Payload, allow: Bool, text: String? = nil) async {
        guard let bridge = Connection.bridge(named: p.machine), let key = p.key, let rid = p.requestId else { return }
        var answers: [String: String]?
        if let text, let q = p.question { answers = [q: text] }
        _ = try? await BridgeClient(bridge).post("api/sessions/\(key)/permission",
                                                 PermissionBody(requestId: rid, allow: allow, answers: answers),
                                                 as: OkBody.self)
    }

    /// Eine Antwort aus der Mitteilung heraus, als Nachricht an die Sitzung.
    ///
    /// Nicht dasselbe wie `answer`: das beantwortet eine Rueckfrage, die auf
    /// eine Entscheidung wartet. Hier wartet niemand - es ist der naechste
    /// Auftrag, getippt ohne die App zu oeffnen.
    static func say(_ p: Payload, text: String?) async {
        let text = (text ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let key = p.key,
              let bridge = Connection.bridge(named: p.machine) else { return }
        // Mit Kennung: schlaegt das Senden fehl und iOS versucht es noch
        // einmal, kommt die Nachricht trotzdem nur einmal an.
        _ = try? await BridgeClient(bridge).post("api/sessions/\(key)/message",
                                                 TextBody(text: text, id: UUID().uuidString),
                                                 as: OkBody.self)
    }

    /// A resident's request decided on the notification.
    static func decide(_ p: Payload, allow: Bool) async {
        guard let bridge = Connection.bridge(named: p.machine), let id = p.id else { return }
        _ = try? await BridgeClient(bridge).post("api/resident/decide",
                                                 ResidentDecideBody(id: id, allow: allow),
                                                 as: ResidentReply.self)
    }

    static func remove(requestId: String) async {
        let center = UNUserNotificationCenter.current()
        let ids = await center.deliveredNotifications()
            .filter { Payload($0.request.content.userInfo).requestId == requestId }
            .map(\.request.identifier)
        center.removeDeliveredNotifications(withIdentifiers: ids)
    }
}

/// Receives what the user does with a notification - also when the app was
/// not running; iOS wakes it just long enough for the answer to go out.
final class NotificationHandler: NSObject, UNUserNotificationCenterDelegate {
    // iOS takes its "done" only on the main thread: called from a background
    // thread, UIKit asserts and the app stops - that is what tapping a
    // notification did (NSAssertionHandler in
    // _performBlockAfterCATransactionCommitSynchronizes). So the work and
    // the completion both go to the main actor, explicitly.
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        let key = Notifications.Payload(notification.request.content.userInfo).key
        nonisolated(unsafe) let done = completionHandler
        Task { @MainActor in
            let visible = Notifications.visibleSession
            done(key != nil && key == visible ? [] : [.banner, .list, .sound])
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        nonisolated(unsafe) let p = Notifications.Payload(response.notification.request.content.userInfo)
        let action = response.actionIdentifier
        let text = (response as? UNTextInputNotificationResponse)?.userText
        nonisolated(unsafe) let done = completionHandler
        Task { @MainActor in
            switch action {
            case Notifications.allowAction:
                await Notifications.answer(p, allow: true)
            case Notifications.denyAction:
                await Notifications.answer(p, allow: false)
            case Notifications.grantAction:
                await Notifications.decide(p, allow: true)
            case Notifications.refuseAction:
                await Notifications.decide(p, allow: false)
            case Notifications.replyAction:
                // Steht eine Rueckfrage dahinter, ist die Antwort ihre
                // Entscheidung. Sonst ist es schlicht eine Nachricht.
                if p.requestId != nil {
                    await Notifications.answer(p, allow: true, text: text)
                } else {
                    await Notifications.say(p, text: text)
                }
            default:
                if let key = p.key {
                    AppModel.shared.open(session: key, machine: p.machine)
                } else if p.kind == "resident" || p.kind == "antrag" {
                    // The resident's news: straight to its page.
                    UserDefaults.standard.set("bewohner", forKey: "iris.layer")
                    AppModel.shared.path = []
                }
            }
            done()
        }
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate {
    private let notifications = NotificationHandler()

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        let center = UNUserNotificationCenter.current()
        center.delegate = notifications
        center.setNotificationCategories(Notifications.categories())
        BackgroundRefresh.register()
        BackgroundRefresh.schedule()
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task { await Notifications.register(token: token) }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        AppModel.shared.pushProblem = error.localizedDescription
    }

    /// A request answered elsewhere - at the Mac, or in the app - takes its
    /// notification with it.
    func application(_ application: UIApplication,
                     didReceiveRemoteNotification userInfo: [AnyHashable: Any]) async -> UIBackgroundFetchResult {
        let p = Notifications.Payload(userInfo)
        guard p.kind == "settled", let rid = p.requestId else { return .noData }
        await Notifications.remove(requestId: rid)
        return .newData
    }
}
