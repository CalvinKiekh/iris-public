import Foundation

/// Eine grosse Datei von einer Bruecke zur anderen tragen.
///
/// Der normale Weg einer Uebergabe ist git. Was GitHub nicht annimmt - eine
/// 124-MB-Tabelle, ein Messdatensatz - faellt dabei heraus und geht hier
/// entlang: versiegelt ueber die Bruecke, an git vorbei.
///
/// Die App ist der Kurier, und zwar mit Absicht. Die Bruecken kennen einander
/// nicht; es gibt keinen Begriff einer anderen Bruecke im ganzen Projekt. Die
/// App dagegen hat beide Token ohnehin schon. Wuerde stattdessen die Quelle
/// direkt an das Ziel liefern, muesste sie dessen Token bekommen - und damit
/// haette ein Rechner plotzlich Zugriff auf einen zweiten, nur damit eine
/// Datei umzieht. So bleibt der Vertrauensanker, wo er schon liegt.
///
/// Was hier NICHT passiert: entschluesseln. Der Kurier traegt den versiegelten
/// Klotz und den Schluessel, sieht aber in die Datei nie hinein - sie wird auf
/// dem Ziel geoeffnet, oder gar nicht.
enum Kurier {

    struct Schritt: Sendable {
        var text: String
        var anteil: Double        // 0 … 1
    }

    struct Ergebnis: Sendable {
        var name: String
        var pfad: String
        var bytes: Int
    }

    /// Was die Quelle nach dem Versiegeln zurueckgibt. `schluessel` kommt
    /// genau einmal und wird nirgends abgelegt.
    private struct Siegel: Decodable, Sendable {
        var ok = false
        var grund = ""
        var id = ""
        var name = ""
        var bytes = 0
        var bloecke = 0
        var schluessel = ""
    }

    private struct Ticket: Decodable, Sendable {
        var ok = false
        var grund = ""
        var ticket = ""
    }

    private struct Angekommen: Decodable, Sendable {
        var ok = false
        var grund = ""
        var name = ""
        var pfad = ""
        var bytes = 0
    }

    private struct Auftrag: Encodable, Sendable {
        var ziel: String
        var path: String
    }

    private struct Schluesselbrief: Encodable, Sendable {
        var sitzung: String
        var name: String
        var bloecke: Int
        var schluessel: String
    }

    private struct Aufraeumen: Encodable, Sendable { var id: String }
    private struct Nichts: Decodable, Sendable { var ok = false }

    enum Fehler: LocalizedError {
        case abgelehnt(String)
        var errorDescription: String? {
            switch self { case .abgelehnt(let grund): grund }
        }
    }

    /// Traegt `pfad` aus `vonSitzung` auf `vonBruecke` nach `nachSitzung` auf
    /// `nachBruecke`. `melde` bekommt jeden Schritt, damit die Oberflaeche
    /// zeigen kann, wo es steht.
    static func trage(pfad: String,
                      vonBruecke: Bridge, vonSitzung: String,
                      nachBruecke: Bridge, nachSitzung: String,
                      melde: @Sendable (Schritt) -> Void = { _ in }) async throws -> Ergebnis {
        let quelle = BridgeClient(vonBruecke)
        let ziel = BridgeClient(nachBruecke)

        // Wie das Ziel sich SELBST nennt, nicht wie es hier im Geraet steht.
        //
        // Der Name geht in den Aufkleber, und das Ziel prueft ihn gegen seinen
        // eigenen. Der Name in der Maschinenliste ist dagegen nur ein Zettel:
        // der eigene Mac steht dort fest als "Dieser Mac", waehrend seine
        // Bruecke sich "maro" nennt, und umbenennen kann man ihn auch. Mit dem
        // Zettel versiegelt scheitert jede Uebertragung an "Siegel passt
        // nicht" - ein Fehler, bei dem niemand an Namensgebung denkt.
        melde(Schritt(text: "Ziel fragen …", anteil: 0.02))
        let wer: HealthBody = try await ziel.get("api/health")
        guard let nachRechner = wer.name, !nachRechner.isEmpty else {
            throw Fehler.abgelehnt("Das Ziel nennt seinen Namen nicht.")
        }

        melde(Schritt(text: "versiegeln …", anteil: 0.05))
        let siegel: Siegel = try await quelle.post(
            "api/sessions/\(vonSitzung)/ausgang",
            Auftrag(ziel: nachRechner, path: pfad))
        guard siegel.ok else { throw Fehler.abgelehnt(siegel.grund) }

        // Der Klotz geht auf die Platte, nicht in den Speicher: er ist so
        // gross wie die Datei, um die es ueberhaupt erst geht.
        melde(Schritt(text: "holen …", anteil: 0.2))
        let datei = try await quelle.rohInDatei("api/ausgang/\(siegel.id)")
        defer { try? FileManager.default.removeItem(at: datei) }

        // Erst der Schluessel, dann der Klotz. Getrennt, damit der Schluessel
        // nicht in der Adresse des Uploads steht - dort landet er in jedem
        // Zugriffsprotokoll, das unterwegs mitschreibt.
        melde(Schritt(text: "Schlüssel übergeben …", anteil: 0.55))
        let ticket: Ticket = try await ziel.post(
            "api/eingang/schluessel",
            Schluesselbrief(sitzung: vonSitzung, name: siegel.name,
                            bloecke: siegel.bloecke, schluessel: siegel.schluessel))
        guard ticket.ok, !ticket.ticket.isEmpty else { throw Fehler.abgelehnt(ticket.grund) }

        melde(Schritt(text: "übertragen …", anteil: 0.6))
        let an: Angekommen = try await ziel.rohAusDatei(
            "api/sessions/\(nachSitzung)/eingang/\(ticket.ticket)", datei: datei)
        guard an.ok else { throw Fehler.abgelehnt(an.grund) }

        // Angekommen, also hat die Zwischenlagerung keinen Grund mehr. Sie
        // faellt nach einer Stunde ohnehin weg, aber erst dann.
        _ = try? await quelle.post("api/ausgang/weg", Aufraeumen(id: siegel.id),
                                   as: Nichts.self)
        melde(Schritt(text: "angekommen", anteil: 1))
        return Ergebnis(name: an.name, pfad: an.pfad, bytes: an.bytes)
    }
}
