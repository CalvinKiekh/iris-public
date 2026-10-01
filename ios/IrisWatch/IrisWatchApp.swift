import SwiftUI

/// iris on the wrist: what runs, what waits for you, a short answer. The
/// watch asks the iPhone, the iPhone asks the bridge (WatchLink).
@main
struct IrisWatchApp: App {
    @State private var store = WatchStore()

    var body: some Scene {
        WindowGroup {
            NavigationStack { SessionsView() }
                .environment(store)
                .tint(WatchStore.brass)
        }
    }
}
