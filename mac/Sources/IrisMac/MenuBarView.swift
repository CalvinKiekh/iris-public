import AppKit
import SwiftUI

/// The glance from the menu bar: away or at the Mac, what waits for an
/// answer, and the way into the window.
struct MenuBarView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        let live = app.sessions.filter { !$0.exited }
        let waiting = live.filter { $0.openAsks > 0 }
        let working = live.filter(\.busy).count
        VStack(alignment: .leading, spacing: 12) {
            AwayRow()
            Text(summary(waiting: waiting.count, working: working, total: live.count))
                .font(Face.mono(10.5))
                .foregroundStyle(Palette.meta)
            ForEach(waiting) { s in
                Button { show(s.key) } label: { SessionRow(info: s) }.buttonStyle(.plain)
            }
            Button("iris öffnen") { show(nil) }
                .buttonStyle(.plain)
                .font(Face.ui(13, .regular))
                .foregroundStyle(Palette.brass)
        }
        .padding(16)
        .frame(width: 320)
        .background(Palette.ground)
        .task { await app.refresh() }
    }

    private func summary(waiting: Int, working: Int, total: Int) -> String {
        var parts = ["\(total) \(total == 1 ? "Sitzung" : "Sitzungen")"]
        if working > 0 { parts.append("\(working) arbeiten") }
        if waiting > 0 { parts.append("\(waiting) warten auf dich") }
        return parts.joined(separator: " · ")
    }

    private func show(_ key: String?) {
        if let key { app.open(session: key) }
        openWindow(id: "main")
        NSApp.activate()
    }
}
