import SwiftUI

/// Eine Datei, die git nicht mitnimmt, auf einen anderen Rechner bringen.
///
/// Zwei Schritte, sonst nichts: welcher Rechner, welche Sitzung dort. Danach
/// traegt `Kurier` sie versiegelt hinueber und sagt unterwegs, wo er steht.
///
/// Das Blatt ist bewusst klein. Es taucht nur dort auf, wo es einen Grund
/// gibt - an einer Datei, die zu gross fuer GitHub ist oder ignoriert wird
/// und deshalb bei einer Uebergabe stillschweigend zurueckbliebe.
struct DateiMitnehmen: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    let model: SessionModel
    let pfad: String
    let bytes: Int

    @State private var ziel: Machine?
    @State private var sitzungen: [SessionInfo] = []
    @State private var laedt = false
    @State private var schritt: Kurier.Schritt?
    @State private var fehler = ""
    @State private var fertig: Kurier.Ergebnis?

    /// Der eigene Rechner steht nicht zur Wahl: eine Datei zu sich selbst zu
    /// tragen ist kein Fall, den es gibt.
    private var andere: [Machine] {
        app.machines.filter { $0.id != app.machine?.id }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Eyebrow("Datei mitnehmen").padding(.bottom, 6)
            Text((pfad as NSString).lastPathComponent)
                .font(Face.ui(16)).foregroundStyle(Palette.text)
            Text(groesse(bytes) + " · verschlüsselt über die Brücke, nicht über git")
                .font(Face.ui(11.5)).foregroundStyle(Palette.meta)
                .padding(.top, 2)

            if let fertig {
                SectionLabel("Angekommen")
                Text("Liegt als \(fertig.name) im Arbeitsverzeichnis der Zielsitzung.")
                    .font(Face.ui(13)).foregroundStyle(Palette.soft)
                    .padding(.top, 4)
                if fertig.name != (pfad as NSString).lastPathComponent {
                    // Nichts wird ueberschrieben - wenn dort schon etwas lag,
                    // steht die neue Datei daneben und heisst anders.
                    Text("Dort lag schon eine Datei dieses Namens; sie ist unberührt.")
                        .font(Face.ui(11.5)).foregroundStyle(Palette.meta)
                        .padding(.top, 4)
                }
            } else if let schritt {
                SectionLabel("Unterwegs")
                Text(schritt.text).font(Face.ui(13)).foregroundStyle(Palette.soft)
                    .padding(.top, 4)
                ProgressView(value: schritt.anteil)
                    .tint(Palette.brass)
                    .padding(.top, 8)
            } else {
                SectionLabel("Wohin")
                if andere.isEmpty {
                    Text("Nur dieser Rechner ist eingetragen. Ein zweiter muss in iris bekannt sein, damit etwas hinübergehen kann.")
                        .font(Face.ui(12.5)).foregroundStyle(Palette.meta)
                        .padding(.top, 4)
                }
                ForEach(andere) { m in
                    Button {
                        ziel = m
                        Task { await ladeSitzungen(m) }
                    } label: {
                        HStack(spacing: 10) {
                            Tick(on: ziel?.id == m.id)
                            Text(m.name).font(Face.ui(13)).foregroundStyle(Palette.soft)
                            Spacer(minLength: 0)
                        }
                        .contentShape(Rectangle())
                        .padding(.vertical, 5)
                    }
                    .buttonStyle(.plain)
                }

                if ziel != nil {
                    SectionLabel("In welche Sitzung")
                    if laedt {
                        Text("Wird geladen …").font(Face.mono(10.5))
                            .foregroundStyle(Palette.meta).padding(.top, 4)
                    } else if sitzungen.isEmpty {
                        Text("Dort läuft keine Sitzung. Die Datei braucht ein Arbeitsverzeichnis, in das sie gehört.")
                            .font(Face.ui(12.5)).foregroundStyle(Palette.meta)
                            .padding(.top, 4)
                    }
                    ForEach(sitzungen, id: \.key) { s in
                        Button {
                            Task { await trage(nach: s) }
                        } label: {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(s.title).font(Face.ui(13)).foregroundStyle(Palette.soft)
                                Text(Fmt.path(s.cwd)).font(Face.mono(10))
                                    .foregroundStyle(Palette.meta)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .contentShape(Rectangle())
                            .padding(.vertical, 5)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            if !fehler.isEmpty {
                Text(fehler).font(Face.ui(12.5)).foregroundStyle(Palette.clayText)
                    .padding(.top, 12)
            }
            Spacer(minLength: 0)
            // Ein Blatt ohne Ausweg ist ein Blatt, aus dem man nicht
            // herauskommt - egal wie eindeutig die Knöpfe darin aussehen.
            Button(fertig == nil ? "Abbrechen" : "Schließen") { dismiss() }
                .font(Face.ui(13))
                .foregroundStyle(fertig == nil ? Palette.meta : Palette.brass)
                .buttonStyle(.plain)
                .keyboardShortcut(.cancelAction)
        }
    }

    private func ladeSitzungen(_ m: Machine) async {
        laedt = true
        defer { laedt = false }
        sitzungen = []
        fehler = ""
        guard let b = Connection.bridge(for: m) else {
            fehler = "Für \(m.name) ist kein Zugang hinterlegt."
            return
        }
        do {
            let body: SessionsBody = try await BridgeClient(b).get("api/sessions")
            sitzungen = body.sessions
        } catch {
            fehler = Bridge.explain(error, on: m.name)
        }
    }

    private func trage(nach s: SessionInfo) async {
        guard let m = ziel, let nachB = Connection.bridge(for: m),
              let vonB = app.client?.bridge else { return }
        fehler = ""
        schritt = Kurier.Schritt(text: "vorbereiten …", anteil: 0)
        do {
            fertig = try await Kurier.trage(
                pfad: pfad,
                vonBruecke: vonB, vonSitzung: model.key,
                nachBruecke: nachB, nachSitzung: s.key,
                melde: { st in Task { @MainActor in schritt = st } })
        } catch {
            schritt = nil
            fehler = (error as? Kurier.Fehler)?.errorDescription
                ?? Bridge.explain(error, on: m.name)
        }
    }

    private func groesse(_ bytes: Int) -> String {
        let mb = Double(bytes) / 1_048_576
        return mb >= 1 ? String(format: "%.0f MB", mb)
                       : String(format: "%.0f KB", Double(bytes) / 1024)
    }
}
