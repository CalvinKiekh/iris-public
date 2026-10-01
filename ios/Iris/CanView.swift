import SwiftUI

/// What he can do, in his own words. Two kinds, told apart because they are
/// different things: tools he built and calls himself, and what is simply
/// built into him - memory, perception, speaking up. Each entry says what it
/// does and what shows that it works.
struct CanGlance: View {
    let model: ResidentModel
    @State private var me: ResidentSelf?
    @State private var showAll = false

    private var built: [ResidentTool] { me?.faehigkeiten ?? [] }
    private var tools: [ResidentTool] { me?.werkzeuge ?? [] }
    private var all: [ResidentTool] { built + tools }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if all.isEmpty {
                Text("Noch hat er nichts aufgeschrieben, was er kann.")
                    .font(Face.ui(13)).foregroundStyle(Palette.meta)
            } else {
                ForEach(all.prefix(4)) { c in row(c, short: true) }
                if all.count > 4 {
                    Button { showAll = true } label: {
                        Text("Alle \(all.count) ansehen")
                            .font(Face.ui(13.5)).foregroundStyle(Palette.brass)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("bewohner-faehigkeiten-alle")
                }
            }
        }
        .sheet(isPresented: $showAll) {
            NavigationStack { CanSheet(built: built, tools: tools) }
        }
        .task {
            while !Task.isCancelled {
                if let v = await model.selfView() { me = v }
                try? await Task.sleep(for: .seconds(30))
            }
        }
    }

    /// One capability. Short in the glance, with its proof in the full list.
    @ViewBuilder
    fileprivate func row(_ c: ResidentTool, short: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Circle()
                    .fill(c.geprueft == true ? Palette.sage : Palette.hair)
                    .frame(width: 5, height: 5)
                    .alignmentGuide(.firstTextBaseline) { $0[.bottom] + 1 }
                Text(Self.title(c.name)).font(Face.ui(14.5)).foregroundStyle(Palette.text)
                Spacer(minLength: 0)
                if !short, let t = c.erstellt, t > 0 {
                    Text(Self.since(t)).font(Face.mono(10)).foregroundStyle(Palette.meta)
                }
            }
            if let z = c.zweck, !z.isEmpty {
                Text(z).font(Face.ui(13)).foregroundStyle(Palette.meta)
                    .lineLimit(short ? 2 : nil)
                    .padding(.leading, 13)
            }
            if !short, let e = c.ergebnis, !e.isEmpty {
                Text(e).font(Face.mono(10.5)).foregroundStyle(Palette.meta.opacity(0.85))
                    .padding(.leading, 13)
            }
            if !short, let a = c.aufruf, !a.isEmpty {
                Text(a).font(Face.mono(10)).foregroundStyle(Palette.meta.opacity(0.7))
                    .padding(.leading, 13)
            }
        }
    }

    /// "stimme_hoeren" reads badly in a list; the file name is not the name.
    static func title(_ raw: String) -> String {
        guard raw.contains("_") || raw.contains("-") else { return raw }
        let words = raw.split { $0 == "_" || $0 == "-" }.map(String.init)
        guard let first = words.first else { return raw }
        return ([first.prefix(1).uppercased() + first.dropFirst()] + words.dropFirst()).joined(separator: " ")
    }

    static func since(_ ts: Double) -> String {
        let f = DateFormatter()
        f.dateFormat = "dd.MM."
        return "seit " + f.string(from: Date(timeIntervalSince1970: ts))
    }
}

/// The full list: what is built in, then the tools he wrote himself.
struct CanSheet: View {
    @Environment(\.dismiss) private var dismiss
    let built: [ResidentTool]
    let tools: [ResidentTool]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                if !built.isEmpty {
                    section("Das kann er von sich aus", built,
                            "Eingebaut – nichts davon muss aufgerufen werden.")
                }
                if !tools.isEmpty {
                    section("Werkzeuge, die er sich gebaut hat", tools,
                            "Geschrieben und selbst geprüft, jedes mit einem Aufruf.")
                }
                if built.isEmpty && tools.isEmpty {
                    Text("Noch hat er nichts aufgeschrieben, was er kann.")
                        .font(Face.ui(13.5)).foregroundStyle(Palette.meta)
                }
                Text("Grüner Punkt: einmal auf dem echten Weg belegt. Grauer Punkt: hat er, aber noch nie gebraucht.")
                    .font(Face.mono(10)).foregroundStyle(Palette.meta)
                    .padding(.top, 4)
            }
            .padding(18)
        }
        .background(Room())
        .navigationTitle("Was er kann")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
    }

    @ViewBuilder
    private func section(_ title: String, _ items: [ResidentTool], _ note: String) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Eyebrow(title)
            Text(note).font(Face.ui(12)).foregroundStyle(Palette.meta)
            ForEach(items) { c in
                CanRow(entry: c)
                if c.id != items.last?.id {
                    Rectangle().fill(Palette.hair).frame(height: 1)
                }
            }
        }
    }
}

/// One entry in the full list, with its proof.
private struct CanRow: View {
    let entry: ResidentTool

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Circle()
                    .fill(entry.geprueft == true ? Palette.sage : Palette.hair)
                    .frame(width: 5, height: 5)
                    .alignmentGuide(.firstTextBaseline) { $0[.bottom] + 1 }
                Text(CanGlance.title(entry.name)).font(Face.ui(15)).foregroundStyle(Palette.text)
                Spacer(minLength: 0)
                if let t = entry.erstellt, t > 0 {
                    Text(CanGlance.since(t)).font(Face.mono(10)).foregroundStyle(Palette.meta)
                }
            }
            if let z = entry.zweck, !z.isEmpty {
                Text(z).font(Face.ui(13.5)).foregroundStyle(Palette.text).padding(.leading, 13)
            }
            if let e = entry.ergebnis, !e.isEmpty {
                Text(e).font(Face.mono(10.5)).foregroundStyle(Palette.meta).padding(.leading, 13)
            }
            if let a = entry.aufruf, !a.isEmpty {
                Text(a).font(Face.mono(10)).foregroundStyle(Palette.meta.opacity(0.7)).padding(.leading, 13)
            }
        }
    }
}
