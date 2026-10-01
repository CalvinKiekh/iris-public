import SwiftUI

/// What runs and what does not. Services report themselves; one glance has to
/// answer "is anything broken" - so what is broken sorts to the top, and what
/// is fine stays quiet.
struct ServicesView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss

    /// Grouped by machine, machines ordered by their worst service: sorting
    /// services on their own would list the same host twice.
    private var groups: [(host: String, rows: [ServiceRow])] {
        Dictionary(grouping: app.serviceRows, by: \.host)
            .map { host, rows in (host, rows.sorted { ($0.rank, $0.name) < ($1.rank, $1.name) }) }
            .sorted { (($0.rows.first?.rank ?? 3), $0.host) < (($1.rows.first?.rank ?? 3), $1.host) }
    }

    var body: some View {
        ZStack {
            Room()
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ScreenHeader(eyebrow: "Dienste", title: "Was läuft", subtitle: subtitle, back: { dismiss() })
                    if let s = app.services, s.total > 0 {
                        Tally(summary: s).padding(.top, 22)
                    }
                    if app.serviceRows.isEmpty {
                        Text("Noch meldet sich nichts. Am Mac zeigt **make ingest-token**, was ein Dienst braucht, um sich zu melden.")
                            .font(Face.ui(14))
                            .foregroundStyle(Palette.meta)
                            .lineSpacing(4)
                            .padding(.top, 24)
                    }
                    ForEach(groups, id: \.host) { group in
                        SectionLabel(group.host.isEmpty ? "ohne Gerät" : group.host)
                        ForEach(group.rows) { row in
                            ServiceLine(row: row)
                            if row.id != group.rows.last?.id { Hairline() }
                        }
                    }
                }
                .padding(.horizontal, 22).padding(.top, 10).padding(.bottom, 40)
            }
            .scrollIndicators(.hidden)
            .refreshable { await app.refreshServices() }
        }
        .toolbar(.hidden, for: .navigationBar)
        .task {
            while !Task.isCancelled {
                await app.refreshServices()
                try? await Task.sleep(for: .seconds(10))
            }
        }
    }

    private var subtitle: String? {
        guard let s = app.services, s.total > 0 else { return nil }
        return "\(s.healthy) von \(s.total) melden sich"
    }
}

/// Three numbers: fine, disturbed, missing. Colour only where it is not fine.
private struct Tally: View {
    let summary: ServiceSummary

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 28) {
            figure(summary.healthy, "in Ordnung", Palette.sage)
            figure(summary.unhealthy, "gestört", summary.unhealthy > 0 ? Palette.brass : Palette.meta)
            figure(summary.missing, "vermisst", summary.missing > 0 ? Palette.clayText : Palette.meta)
        }
    }

    private func figure(_ n: Int, _ label: String, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("\(n)").font(Face.display(30)).foregroundStyle(color)
            Text(label.uppercased()).font(Face.mono(9)).tracking(9 * 0.22).foregroundStyle(Palette.meta)
        }
    }
}

private struct ServiceLine: View {
    let row: ServiceRow

    var body: some View {
        HStack(spacing: 12) {
            led.frame(width: 10)
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 7) {
                    Text(row.name).font(Face.ui(15)).foregroundStyle(Palette.soft).lineLimit(1)
                    if !row.version.isEmpty {
                        Text(row.version).font(Face.mono(10)).foregroundStyle(Palette.faint).lineLimit(1)
                    }
                }
                Text(meta).font(Face.ui(11.5))
                    .foregroundStyle(row.missing ? Palette.clayText : Palette.meta)
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            Text(age).font(Face.mono(10.5)).foregroundStyle(row.missing ? Palette.clayText : Palette.faint)
        }
        .padding(.vertical, 12)
    }

    @ViewBuilder private var led: some View {
        if row.missing {
            Circle().strokeBorder(Palette.clay, lineWidth: 1.5).frame(width: 8, height: 8)
        } else {
            Circle()
                .fill(row.status == "error" ? Palette.clay : row.status == "warn" ? Palette.brass : Palette.sage)
                .frame(width: 7, height: 7)
        }
    }

    private var meta: String {
        if row.missing { return "meldet sich nicht mehr" }
        let bits = row.detail.sorted { $0.key < $1.key }.map { "\($0.key) \($0.value)" }
        return bits.isEmpty ? row.status : bits.joined(separator: " · ")
    }

    /// How long since the last report.
    private var age: String {
        guard let s = row.silentFor else { return "" }
        if s < 60 { return "vor \(Int(s)) s" }
        if s < 3600 { return "vor \(Int(s / 60)) min" }
        if s < 86400 { return "vor \(Int(s / 3600)) h" }
        return "vor \(Int(s / 86400)) d"
    }
}
