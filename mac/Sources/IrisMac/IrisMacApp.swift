import AppKit
import SwiftUI

/// iris on the Mac: a menu bar item for the glance, a window for the work.
/// Built like WindowSnap - SPM, a Makefile, no Xcode project.
@main
struct IrisMacApp: App {
    @State private var app = AppModel.shared

    init() {
        Fonts.register()
        // The Mac app lives in the menu bar: keep the kept conversations
        // current every 15 minutes, window open or not.
        Task.detached {
            while !Task.isCancelled {
                for bridge in Connection.all() { await Refresh.cached(with: bridge) }
                try? await Task.sleep(for: .seconds(15 * 60))
            }
        }
    }

    var body: some Scene {
        // Filled when an approval or a question waits - visible from any app.
        MenuBarExtra {
            MenuBarView().environment(app)
        } label: {
            Image(systemName: app.sessions.contains { !$0.exited && $0.openAsks > 0 }
                  ? "circle.hexagongrid.fill" : "circle.hexagongrid")
        }
        .menuBarExtraStyle(.window)

        Window("iris", id: "main") {
            MacWindow()
                .environment(app)
                // Half a screen is a normal size for this window, and on a
                // 13" Mac that is about 735 points - a 1040 minimum made the
                // window refuse to snap there at all. The columns fold away
                // on their own below 1100 (see MacWindow).
                .frame(minWidth: 520, minHeight: 520)
                .preferredColorScheme(.dark)
                .tint(Palette.brass)
        }
        .defaultSize(width: 1320, height: 860)
        .windowStyle(.hiddenTitleBar)
        // A menu bar app opens no window by default; this one shows it on
        // launch - closing it keeps iris in the menu bar.
        .defaultLaunchBehavior(.presented)
    }
}
