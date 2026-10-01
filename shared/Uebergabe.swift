import SwiftUI

/// Was eine Sitzung braucht, um auf einem anderen Rechner weiterzulaufen.
///
/// Shared rather than written twice: the sheet was on the Mac only, and the
/// phone - the thing actually in hand when the wish to move a session comes
/// up - had nothing at all. Everything it draws with (Palette, Face,
/// ScreenHeader, SectionLabel) already lived here, so only the sheet itself
/// was missing.
///
/// The two platforms differ in their frame, not in their content: the Mac
/// puts it in a fixed panel with its own close button, the phone in a sheet
/// the system already knows how to dismiss.
struct UebergabeInhalt: View {
    let model: SessionModel
    /// The phone has more width than the Mac panel and no mouse, so it wants
    /// a little more room per row.
    var kompakt = true

    @State private var beauftragt = false
    @State private var mitnehmen: GrosseDatei?

    private var h: Handover? { model.handover }

    /// What the session is asked to do. Named, not vague: the branch it is
    /// on, and that nothing else should happen - this runs in a session that
    /// may be in the middle of something.
    ///
    /// The note is written by the session and not by us on purpose. Which
    /// tools this work actually needs was tried here by reading Makefiles
    /// and scripts, and it guessed badly: `$(MAKE)` came back as a program
    /// and swift, xcodebuild and xcodegen were missed entirely. The session
    /// was there while the work happened; the bridge only knows the machine,
    /// so the machine is all it fills in.
    func auftrag(_ h: Handover) -> String {
        let wo = h.zettel.isEmpty ? "diesem Rechner" : h.zettel
        return """
        Ich möchte diese Arbeit auf einem anderen Rechner fortsetzen. Bitte \
        zwei Dinge, sonst nichts:

        1. Schreibe UEBERGABE.md ins Projekt: woran du gerade arbeitest, was \
        fertig ist und was offen, mit welchen Befehlen gebaut und geprüft \
        wird, und was davon nur hier funktioniert. Gearbeitet wurde auf \
        \(wo) — nenne, was daran hängt, damit es auf einem anderen Rechner \
        nicht blind wiederholt wird.

        2. Committe den Stand samt dieser Datei und pushe nach \(h.branch).
        """
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let h {
                HStack(spacing: 9) {
                    Circle().fill(h.ok ? Palette.sage : Palette.clay).frame(width: 6, height: 6)
                    Text(h.ok ? "Bereit zum Mitnehmen" : h.grund)
                        .font(Face.ui(14))
                        .foregroundStyle(h.ok ? Palette.text : Palette.clayText)
                }
                .padding(.top, 18)

                SectionLabel("Repository")
                zeile("Remote", h.remote)
                zeile("Konto", h.account)
                zeile("Branch", h.branch + (h.ahead > 0 ? "  ·  \(h.ahead) nicht gepusht" : ""))
                zeile("Offen", h.offen == 0 ? "nichts" : "\(h.offen) Datei\(h.offen == 1 ? "" : "en")")

                SectionLabel("Verlauf")
                zeile("Größe", groesse(h.bytes))
                Text(h.bytes > 20 * 1024 * 1024
                     ? "Das ist viel für eine Übertragung — es geht, dauert aber."
                     : "Der ganze Kontext der Sitzung; er wandert als Abzweig mit.")
                    .font(Face.ui(11.5)).foregroundStyle(Palette.meta)
                    .padding(.top, 2)

                if let m = h.maschine, !m.kurz.isEmpty {
                    // The conditions do not travel through git. Named here so
                    // the sheet says out loud what the order will carry.
                    SectionLabel("Gearbeitet auf")
                    zeile(m.name, m.kurz)
                }

                if !h.ignoriert.isEmpty || !h.schwer.isEmpty {
                    SectionLabel("Reist nicht mit")
                    ForEach(h.ignoriert, id: \.self) { d in
                        dateiZeile(d, warum: "")
                    }
                    if !h.ignorierteOrdner.isEmpty {
                        Text("Ignorierte Ordner: " + h.ignorierteOrdner.joined(separator: ", "))
                            .font(Face.ui(11.5)).foregroundStyle(Palette.meta)
                            .padding(.top, 2)
                    }
                    ForEach(h.schwer, id: \.self) { d in
                        // Not a hint but an obstacle: the push itself fails.
                        dateiZeile(d, warum: "zu groß für GitHub")
                    }
                    Text("Einzeln mitnehmen geht trotzdem — verschlüsselt über die Brücke, an git vorbei.")
                        .font(Face.ui(11.5)).foregroundStyle(Palette.meta)
                        .padding(.top, 6)
                }

                // Committing and pushing change something outside this
                // machine, so they are not done here: the session is asked
                // to do it, and you answer for it as for any other tool.
                if h.offen > 0 || h.ahead > 0 {
                    Button {
                        Task {
                            _ = await model.send(auftrag(h))
                            beauftragt = true
                        }
                    } label: {
                        Text(beauftragt ? "Auftrag ist raus" : "Committen und pushen lassen")
                            .font(Face.ui(13))
                            .foregroundStyle(beauftragt ? Palette.sage : Palette.brass)
                            .padding(.horizontal, 12).padding(.vertical, kompakt ? 7 : 10)
                            .background(Capsule().fill(Color(hex: 0xEFECE5, opacity: 0.07)))
                            .contentShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .disabled(beauftragt)
                    .padding(.top, 20)
                    Text("Geht als Nachricht an die Sitzung — du siehst sie im Verlauf und gibst sie frei wie jeden anderen Befehl.")
                        .font(Face.ui(11.5)).foregroundStyle(Palette.meta)
                        .padding(.top, 6)
                }
            } else {
                Text("Wird geprüft …").font(Face.mono(10.5))
                    .foregroundStyle(Palette.meta).padding(.top, 18)
            }
            Spacer(minLength: 0)
        }
        .task { await model.loadHandover() }
        .sheet(item: $mitnehmen) { d in
            DateiMitnehmen(model: model, pfad: d.path, bytes: d.bytes)
                .padding(24)
                .frame(minWidth: 380, minHeight: 320)
                .background(Room())
        }
    }

    /// Eine Datei, die bei einer Uebergabe zurueckbliebe - mit dem Weg daneben.
    ///
    /// Der Knopf steht genau hier und nirgends sonst: an der Stelle, an der
    /// gerade steht, dass diese Datei nicht mitkommt. Ein eigener Menuepunkt
    /// "Datei uebertragen" waere eine Funktion auf der Suche nach einem Anlass.
    private func dateiZeile(_ d: GrosseDatei, warum: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(groesse(d.bytes)).font(Face.mono(10)).foregroundStyle(Palette.meta)
                .frame(width: kompakt ? 58 : 76, alignment: .leading)
            VStack(alignment: .leading, spacing: 1) {
                Text(d.path).font(Face.ui(13)).foregroundStyle(Palette.soft)
                    .textSelection(.enabled)
                if !warum.isEmpty {
                    Text(warum).font(Face.ui(11)).foregroundStyle(Palette.clayText)
                }
            }
            Spacer(minLength: 0)
            Button("mitnehmen") { mitnehmen = d }
                .font(Face.mono(10))
                .foregroundStyle(Palette.brass)
                .buttonStyle(.plain)
                .fixedSize()
        }
        .padding(.vertical, 3)
    }

    private func zeile(_ was: String, _ wert: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(was).font(Face.mono(10)).foregroundStyle(Palette.meta)
                .frame(width: kompakt ? 58 : 76, alignment: .leading)
            Text(wert.isEmpty ? "—" : wert).font(Face.ui(13))
                .foregroundStyle(Palette.soft).textSelection(.enabled)
            Spacer(minLength: 0)
        }
        .padding(.vertical, 3)
    }

    private func groesse(_ bytes: Int) -> String {
        let mb = Double(bytes) / 1_048_576
        return mb >= 1 ? String(format: "%.0f MB", mb)
                       : String(format: "%.0f KB", Double(bytes) / 1024)
    }
}
