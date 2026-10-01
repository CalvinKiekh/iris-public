import Foundation

/// Ein Auftrag unter Aufsicht, wie die Brücke ihn führt.
///
/// Das Gegenstück zu `bridge/wachen.py`. Die Messreihe ist der Kern: sie ist
/// das Einzige, was es nirgends sonst gibt, und der Grund, warum es einen
/// Vorarbeiter überhaupt gibt - wer seit zwanzig Zügen an einer Optimierung
/// sitzt, sieht selbst nicht mehr, dass es seit drei Runden nicht besser wird.
struct Wache: Decodable, Sendable, Identifiable {
    struct Runde: Decodable, Sendable, Identifiable {
        var n: Int
        var wert: Double?
        var notiz: String
        var ts: Double
        var id: Int { n }
    }

    var id: String
    var ziel: String
    var mass: String
    var sitzung: String
    var vorarbeiter: String
    var budget: Int
    var stand: String
    var grund: String
    var runden: [Runde]

    var laeuft: Bool { stand == "laeuft" }

    /// Die Zahlen der Reihe, in ihrer Reihenfolge - Runden ohne Messung
    /// fallen heraus, nicht die Reihe.
    var werte: [Double] { runden.compactMap(\.wert) }

    /// Die beste bisher. Kleiner ist besser: die Maße, um die es geht
    /// (ms je Bild, Laufzeit), zählen nach unten.
    var bestes: Double? { werte.min() }

    /// Wo die Reihe angefangen hat, damit „118 auf 29" sagbar bleibt.
    var erstes: Double? { werte.first }

    /// Steht es seit drei Runden still? Dieselbe Rechnung wie in der Brücke,
    /// damit die Ansicht nicht etwas anderes behauptet als der Vorarbeiter.
    var stillstand: Bool {
        guard werte.count > 3, let bestesVorher = werte.dropLast(3).min(), bestesVorher > 0
        else { return false }
        return (werte.suffix(3).min() ?? .infinity) > bestesVorher * 0.95
    }

    enum CodingKeys: String, CodingKey {
        case id, ziel, mass, sitzung, vorarbeiter, budget, stand, grund, runden
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = c.lenient(.id) ?? ""
        ziel = c.lenient(.ziel) ?? ""
        mass = c.lenient(.mass) ?? ""
        sitzung = c.lenient(.sitzung) ?? ""
        vorarbeiter = c.lenient(.vorarbeiter) ?? ""
        budget = c.lenient(.budget) ?? 0
        stand = c.lenient(.stand) ?? "laeuft"
        grund = c.lenient(.grund) ?? ""
        runden = (try? c.decode([Runde].self, forKey: .runden)) ?? []
    }
}

struct WachenBody: Decodable, Sendable {
    var wachen: [Wache] = []
}

/// Die Haltung aus den Wachen ableiten - die Form selbst steht in
/// `OrbForm.swift`, damit sie sich auch ausserhalb der App zeichnen laesst.
extension Haltung {
    static func aus(_ wachen: [Wache]) -> Haltung {
        let laufend = wachen.filter(\.laeuft)
        guard let w = laufend.first else {
            return wachen.contains(where: { $0.stand == "fertig" }) ? .erledigt : .ruht
        }
        if laufend.contains(where: \.stillstand) { return .festgefahren }
        guard w.werte.count >= 2, let erstes = w.erstes, let bestes = w.bestes,
              erstes > 0 else { return .zuversichtlich }
        return bestes < erstes * 0.95 ? .zuversichtlich : .skeptisch
    }
}
