import SwiftUI

/// What he is doing right now, and what he was thinking while he did it.
///
/// The page used to say "Überlegt, ob etwas zu tun ist" - the same sentence
/// every time, whatever he was actually considering. Meanwhile every pass
/// writes its reasoning into the journal ("Keine Änderung, die Maßnahmen
/// erfordert"), every tool use its occasion ("neuer python.exe Prozess
/// gestartet - überprüfe, ob noch GPU-belegende Prozesse aktiv sind").
/// None of it reached the phone. This shows it.
struct GedankenStrom: View {
    let entries: [ResidentEntry]
    var hoechstens = 14

    /// Lines that are the program talking to itself, not him thinking. They
    /// were the bulk of the first version: "unterbrochen", "Zweiter Versuch
    /// war lesbar", "Antwort unlesbar (JSONDecodeError)". True, useful in the
    /// journal, and nothing anyone wants to read as a thought.
    private static let maschine = [
        "unterbrochen", "zweiter versuch", "antwort unlesbar", "warmlauf",
        "faden", "aufräumer", "gedächtnis-faden", "im freien zustand",
        "keine änderung", "keine anweisung", "erfordert keine",
    ]

    /// What he thinks, sees and reaches for - in the order it happened.
    private var strom: [ResidentEntry] {
        entries.filter { e in
            guard ["tick", "werkzeug", "fund", "haus", "ansprache", "auftrag",
                   "ergebnis", "antrag", "entscheidung", "erinnerung"].contains(e.kind)
            else { return false }
            let t = (e.text ?? "").lowercased()
            if t.isEmpty { return false }
            if Self.maschine.contains(where: { t.contains($0) }) { return false }
            // A session key says nothing to anyone but us.
            if t.contains(":b'") || t.contains(":t:") { return false }
            // The quiet passes are counted below instead of listed one by one.
            if e.kind == "tick",
               ["keine anomalie", "keine anfallende", "keine aufgabe"]
                .contains(where: { t.contains($0) }) { return false }
            return true
        }
        .suffix(hoechstens)
        .reversed()
    }

    /// How many passes found nothing worth doing. Most of his day is this,
    /// and it is the normal case - worth one line, not thirty.
    private var stille: Int {
        entries.filter { e in
            guard e.kind == "tick", let t = e.text?.lowercased() else { return false }
            return ["keine änderung", "keine anweisung", "erfordert keine",
                    "keine anomalie", "keine anfallende", "keine aufgabe"]
                .contains(where: { t.contains($0) })
        }.count
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if strom.isEmpty {
                Text("Noch kein Durchgang seit dem Start.")
                    .font(Face.ui(13)).foregroundStyle(Palette.meta)
                    .padding(.vertical, 10)
            }
            ForEach(Array(strom.enumerated()), id: \.element.id) { i, e in
                GedankeZeile(entry: e)
                if i < strom.count - 1 || stille > 0 { ZeilenStrich() }
            }
            if stille > 0 {
                HStack(spacing: 8) {
                    Marke(text: "still", ton: .ruhig)
                    Text(stille == 1 ? "einmal nachgesehen, nichts zu tun"
                                     : "\(stille) mal nachgesehen, nichts zu tun")
                        .font(Face.ui(13)).foregroundStyle(Palette.meta)
                }
                .padding(.vertical, 10)
            }
        }
        // The talk bar floats over the bottom of the page; without room the
        // last thought sits behind it.
        .padding(.bottom, 8)
    }
}

/// One thought. The kind decides the mark and the wording; the text is his.
private struct GedankeZeile: View {
    let entry: ResidentEntry

    private var art: (wort: String, ton: Marke.Ton) {
        switch entry.kind {
        case "werkzeug": return ("nachgesehen", .laeuft)
        case "fund":     return ("bemerkt", .gut)
        case "haus":     return ("am Rechner", .ruhig)
        case "ansprache":return ("gesagt", .laeuft)
        case "auftrag":  return ("beauftragt", .laeuft)
        case "ergebnis": return ("fertig", .gut)
        case "antrag":   return ("gefragt", .laeuft)
        case "entscheidung": return ("entschieden", .gut)
        case "erinnerung":   return ("erinnert", .laeuft)
        case "fehler":   return ("Fehler", .schlecht)
        default:         return ("gedacht", .ruhig)
        }
    }

    /// The occasion he named for reaching to a tool - the interesting half.
    private var anlass: String? {
        guard let a = entry.anlass, !a.isEmpty else { return nil }
        return a
    }

    private var frisch: Bool {
        guard let ts = entry.ts else { return false }
        return Date().timeIntervalSince1970 - ts < 60
    }

    /// A machine timestamp read aloud badly and looked worse: "Notiert für
    /// 2026-09-12T12:30:49" becomes "Notiert für 12:30".
    static func lesbar(_ text: String) -> String {
        var t = text
        let rx = try? NSRegularExpression(pattern: #"\d{4}-\d{2}-\d{2}T(\d{2}:\d{2}):\d{2}"#)
        if let rx {
            t = rx.stringByReplacingMatches(in: t, range: NSRange(t.startIndex..., in: t),
                                            withTemplate: "$1 Uhr")
        }
        return t
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Marke(text: art.wort, ton: art.ton)
                Spacer(minLength: 0)
                // Under a minute the age is noise - "0 s" on every line said
                // nothing. "gerade eben" is what a person would say.
                Text(frisch ? "gerade eben" : ResidentPanel.ago(entry.ts))
                    .font(Face.mono(9)).foregroundStyle(Palette.faint)
            }
            Text(GedankeZeile.lesbar(entry.text ?? ""))
                .font(Face.ui(13.5)).foregroundStyle(Palette.soft)
                .fixedSize(horizontal: false, vertical: true)
            if let anlass {
                // Why he looked - without it a tool use is just a name.
                Text("weil: " + anlass)
                    .font(Face.ui(12)).foregroundStyle(Palette.meta)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.vertical, 10)
    }
}

/// The figures that matter at a glance: how he is, how fast he thinks, how
/// much room the machine has, and whether anything waits for Calvin.
struct JetztZahlen: View {
    let state: ResidentState
    let lage: ResidentLage?
    let entries: [ResidentEntry]

    /// Token per second from the last timing line - what he manages right now.
    private var tempo: String? {
        for e in entries.reversed() where e.kind == "zeiten" {
            guard let t = e.text, let r = t.range(of: #"(\d+[.,]?\d*)\s*(Token|tok)"#,
                                                  options: .regularExpression) else { continue }
            return String(t[r]).replacingOccurrences(of: "Token", with: "")
                .replacingOccurrences(of: "tok", with: "").trimmingCharacters(in: .whitespaces)
        }
        return nil
    }

    private var offen: Int { state.requests.filter { $0.status == "offen" }.count }

    var body: some View {
        Kennzahlen(zahlen: [
            Kennzahl(label: "Durchgänge heute",
                     wert: "\(entries.filter { $0.kind == "tick" }.count)",
                     dazu: "seit Mitternacht"),
            Kennzahl(label: "Werkzeuge benutzt",
                     wert: "\(entries.filter { $0.kind == "werkzeug" }.count)",
                     dazu: "von selbst"),
            Kennzahl(label: "Wartet auf dich", wert: "\(offen)",
                     dazu: offen == 1 ? "ein Antrag" : "Anträge",
                     betont: offen > 0),
        ])
    }
}
