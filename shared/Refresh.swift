import Foundation

/// Keeps the kept conversations current while nobody looks: for the
/// sessions opened lately, what came since their last number is fetched and
/// written down. The phone runs it as a background refresh, the Mac on a
/// timer. Each stream is read only briefly - the replay arrives in one burst.
enum Refresh {
    private final class Box: @unchecked Sendable {
        var lines: [String] = []
        var last = 0
        var renumbered = false
    }

    static func cached(with bridge: Bridge) async {
        let client = BridgeClient(bridge)
        for key in CardCache.recentKeys() {
            if Task.isCancelled { return }
            let since = CardCache.lastSeq(key)
            let box = Box()
            box.last = since
            let reader = Task {
                for try await incoming in client.events(key, since: since) {
                    if let s = incoming.card.seq, s > 0 {
                        if s <= since { box.renumbered = true; return }
                        box.last = s
                    }
                    box.lines.append(incoming.line)
                }
            }
            try? await Task.sleep(for: .seconds(3))
            reader.cancel()
            _ = await reader.result
            if box.renumbered {
                CardCache.clear(key)             // loaded afresh on next open
            } else {
                CardCache.append(box.lines, lastSeq: box.last, for: key)
            }
        }
    }
}
