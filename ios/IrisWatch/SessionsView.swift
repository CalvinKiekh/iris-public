import SwiftUI

/// The computers, and the running sessions of the one in use.
struct SessionsView: View {
    @Environment(WatchStore.self) private var store

    var body: some View {
        List {
            if store.machines.count > 1 {
                Section("Rechner") {
                    ForEach(store.machines) { m in
                        Button { Task { await store.use(m) } } label: {
                            HStack(spacing: 8) {
                                Circle().fill(m.current ? WatchStore.brass : Color.gray.opacity(0.5))
                                    .frame(width: 6, height: 6)
                                Text(m.name).lineLimit(1)
                                    .foregroundStyle(m.current ? WatchStore.brass : .primary)
                            }
                        }
                    }
                }
            }
            Section("Sitzungen") {
                if store.sessions.isEmpty {
                    Text(store.problem ?? "Keine laufende Sitzung")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                ForEach(store.sessions) { s in
                    NavigationLink(value: s.id) { row(s) }
                }
            }
        }
        .navigationTitle("iris")
        .navigationDestination(for: String.self) { SessionScreen(key: $0) }
        .task {
            while !Task.isCancelled {
                await store.overview()
                try? await Task.sleep(for: .seconds(4))
            }
        }
    }

    private func row(_ s: WatchLink.SessionRow) -> some View {
        HStack(spacing: 8) {
            Circle()
                .fill(s.asks > 0 || s.busy ? WatchStore.brass : Color.green.opacity(0.8))
                .frame(width: 7, height: 7)
            VStack(alignment: .leading, spacing: 2) {
                Text(s.title).lineLimit(2)
                if s.asks > 0 {
                    Text("Freigabe offen").font(.caption2).foregroundStyle(WatchStore.brass)
                } else if s.busy {
                    Text("arbeitet").font(.caption2).foregroundStyle(.secondary)
                }
            }
        }
    }
}

/// One session: what it does, what it last said, what waits - and a short
/// answer by voice or scribble.
struct SessionScreen: View {
    @Environment(WatchStore.self) private var store
    let key: String
    @State private var detail: WatchLink.SessionDetail?
    @State private var reply = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                if let d = detail {
                    Text(d.status).font(.caption2).foregroundStyle(.secondary)
                    if let doing = d.doing {
                        Text(doing).font(.caption).foregroundStyle(WatchStore.brass)
                    }
                    if let a = d.ask { askCard(a) }
                    if !d.lastAnswer.isEmpty {
                        Text(d.lastAnswer).font(.footnote)
                    }
                    if !d.ended {
                        TextField("Antworten …", text: $reply)
                            .onSubmit(sendReply)
                    }
                    if d.canStop {
                        Button("Anhalten", role: .destructive) {
                            Task { if let n = await store.interrupt(key) { detail = n } }
                        }
                    }
                } else {
                    ProgressView()
                }
                if let p = store.problem {
                    Text(p).font(.caption2).foregroundStyle(.red)
                }
            }
        }
        .navigationTitle(detail?.title ?? "Sitzung")
        .task {
            while !Task.isCancelled {
                if let n = await store.session(key) { detail = n }
                try? await Task.sleep(for: .seconds(3))
            }
        }
    }

    private func askCard(_ a: WatchLink.Ask) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(a.isQuestion ? "FRAGE" : "FREIGABE").font(.caption2).foregroundStyle(WatchStore.brass)
            Text(a.title).font(.headline)
            if !a.detail.isEmpty {
                Text(a.detail).font(.caption2).foregroundStyle(.secondary).lineLimit(3)
            }
            if a.isQuestion {
                ForEach(a.options, id: \.self) { option in
                    Button(option) {
                        Task { if let n = await store.send(key, option) { detail = n } }
                    }
                }
            } else {
                HStack {
                    Button("Erlauben") {
                        Task { if let n = await store.decide(key, a.id, allow: true) { detail = n } }
                    }
                    .tint(.green)
                    Button("Nein") {
                        Task { if let n = await store.decide(key, a.id, allow: false) { detail = n } }
                    }
                }
            }
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 10).fill(WatchStore.brass.opacity(0.15)))
    }

    private func sendReply() {
        let text = reply.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        reply = ""
        Task { if let n = await store.send(key, text) { detail = n } }
    }
}
