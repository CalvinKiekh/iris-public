@preconcurrency import BackgroundTasks
import Foundation

/// Asks iOS to wake the app now and then - at the earliest in 15 minutes;
/// when exactly is iOS's call - so opening a session later finds its
/// conversation already current.
enum BackgroundRefresh {
    /// Muss in der Info.plist unter BGTaskSchedulerPermittedIdentifiers stehen;
    /// project.yml traegt dort ${IRIS_BUNDLE}.refresh ein, also dasselbe.
    static let id = (Bundle.main.bundleIdentifier ?? "iris") + ".refresh"

    /// Must happen before the app has finished launching.
    static func register() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: id, using: nil) { task in
            handle(task)
        }
    }

    static func schedule() {
        let request = BGAppRefreshTaskRequest(identifier: id)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        try? BGTaskScheduler.shared.submit(request)
    }

    private static func handle(_ task: BGTask) {
        schedule()                          // the next one
        nonisolated(unsafe) let task = task
        let work = Task {
            for bridge in Connection.all() { await Refresh.cached(with: bridge) }
            task.setTaskCompleted(success: !Task.isCancelled)
        }
        task.expirationHandler = { work.cancel() }
    }
}
