import XCTest

/// Fährt die Bewohner-Ansicht so, wie Calvin sie bedient - und prüft genau
/// die zwei Stellen, an denen er am 13.09. hängen blieb: "Ich kann keine
/// Chats auswählen" und "er zeigt mir keinen Text im Chat".
///
/// Braucht nur IRIS_URL. Gedacht für einen Lauf gegen die ECHTE Brücke des
/// Bewohners - sie wird dabei nur gelesen: Der Test tippt keine Frage ein und
/// schickt nichts ab.
@MainActor
final class BewohnerUITests: XCTestCase {
    private var adresse = ""

    override func setUp() async throws {
        continueAfterFailure = false
        guard let url = ProcessInfo.processInfo.environment["IRIS_URL"] else {
            throw XCTSkip("IRIS_URL fehlt")
        }
        adresse = url
    }

    /// Ein Bildschirmfoto, das den Lauf ueberlebt - sonst wirft Xcode es
    /// bei einem bestandenen Test weg, und dann kann niemand nachsehen.
    private func bild(_ app: XCUIApplication) {
        let a = XCTAttachment(screenshot: app.screenshot())
        a.lifetime = .keepAlways
        add(a)
    }

    /// Eine Frage ueber die Bruecke stellen - so, wie die App es tut.
    ///
    /// Ueber den ECHTEN Weg (`/api/resident/talk`, `von: "app"`), nicht ueber
    /// die Tastatur: Hier wird geprueft, ob die ANTWORT ankommt, nicht ob das
    /// Tippen geht. Das misst `IrisUITests` an anderer Stelle.
    private func fragen(_ text: String) {
        // Die Adresse kommt als "http://host:port/?token=…" - der Testlaeufer
        // hat den App-Code nicht, also hier von Hand zerlegt.
        guard let teile = URLComponents(string: adresse),
              let token = teile.queryItems?.first(where: { $0.name == "token" })?.value,
              let host = teile.host
        else { return XCTFail("Adresse unbrauchbar: \(adresse)") }
        let port = teile.port.map { ":\($0)" } ?? ""
        guard let url = URL(string: "http://\(host)\(port)/api/resident/talk")
        else { return XCTFail("Adresse unbrauchbar") }
        var r = URLRequest(url: url)
        r.httpMethod = "POST"
        r.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try? JSONSerialization.data(withJSONObject: [
            "text": text, "von": "app", "stimme": false])
        let fertig = XCTestExpectation(description: "gefragt")
        URLSession.shared.dataTask(with: r) { _, resp, _ in
            XCTAssertEqual((resp as? HTTPURLResponse)?.statusCode, 200,
                           "Die Frage kam nicht an")
            fertig.fulfill()
        }.resume()
        wait(for: [fertig], timeout: 30)
    }

    private func starten() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchEnvironment["IRIS_URL"] = adresse
        app.launch()
        return app
    }

    /// Zeigt der Chat die letzte Antwort? Genau das fehlte Calvin am
    /// 14.09. um 01:49: Seine Frage "Bist du wach?" stand da, die Antwort
    /// "Ja." kam nach zwei Sekunden und war im Strom - im Chat blieb es leer.
    func testAntwortStehtImChat() throws {
        let app = starten()
        let reiter = app.buttons["Bewohner"]
        XCTAssertTrue(reiter.waitForExistence(timeout: 30), "Umschalter fehlt")
        reiter.tap()
        let sprechen = app.descendants(matching: .any)["bewohner-gespraech"]
        XCTAssertTrue(sprechen.waitForExistence(timeout: 30), "Knopf fehlt")
        sprechen.tap()

        // Irgendeine Blase muss da sein. Ein leerer Chat bei vorhandenem
        // Gespräch ist der Fehler selbst.
        let irgendwas = app.staticTexts.firstMatch
        XCTAssertTrue(irgendwas.waitForExistence(timeout: 25),
                      "Der Chat zeigt gar nichts")
        Thread.sleep(forTimeInterval: 6)          // der Rückstand kommt an
        bild(app)

        // EINE FRAGE ÜBER DIE BRÜCKE, UND DIE ANTWORT MUSS ERSCHEINEN.
        //
        // Ein Test, der nur nachsieht, was zufällig dasteht, traegt nichts:
        // Der erste Lauf dieses Tests ging durch, WÄHREND der Fehler auf dem
        // Bildschirm zu sehen war - er hatte Text aus der Ansicht dahinter
        // gefunden. Darum wird jetzt gefragt und auf die eigene Antwort
        // gewartet.
        let marke = "Antworte bitte nur mit dem Wort Messing"
        fragen(marke)
        // NUR die Antwortblase im Chat, nicht irgendein Text auf dem Schirm.
        // Der erste Versuch suchte ueberall und fand "Messing" in der
        // Uebersicht hinter dem Blatt - er bestand, waehrend der Chat leer
        // war. Ein Test, der den Fehler nicht sieht, ist keiner.
        let blasen = app.descendants(matching: .any)
            .matching(identifier: "bewohner-antwort")
        var gefunden = false
        for _ in 0..<45 {                       // bis 90 s
            for i in 0..<blasen.count where blasen.element(boundBy: i)
                .label.localizedCaseInsensitiveContains("Messing") {
                gefunden = true
            }
            if gefunden { break }
            Thread.sleep(forTimeInterval: 2)
        }
        var labels: [String] = []
        for i in 0..<blasen.count { labels.append(blasen.element(boundBy: i).label) }
        XCTAssertTrue(gefunden,
                      "Die Antwort steht nicht in der Blase - genau das stand "
                      + "am 14.09. auf dem Telefon: Frage da, darunter nichts. "
                      + "Blasen: \(labels)")
        bild(app)
    }

    /// Von der Übersicht in das Gespräch und zurück in die früheren.
    func testFrueherGespraecheAuswaehlen() throws {
        let app = starten()

        // Der Umschalter ist ein Knopf, kein Reiter.
        let reiter = app.buttons["Bewohner"]
        XCTAssertTrue(reiter.waitForExistence(timeout: 30), "Umschalter Bewohner fehlt")
        reiter.tap()

        let sprechen = app.descendants(matching: .any)["bewohner-gespraech"]
        XCTAssertTrue(sprechen.waitForExistence(timeout: 30),
                      "Der Knopf ins Gespräch fehlt")
        sprechen.tap()

        let frueher = app.descendants(matching: .any)["bewohner-frueher"]
        XCTAssertTrue(frueher.waitForExistence(timeout: 20),
                      "Kein Weg zu den früheren Gesprächen - genau das fehlte")
        frueher.tap()

        let titel = app.staticTexts["Frühere Gespräche"]
        XCTAssertTrue(titel.waitForExistence(timeout: 20), "Die Liste öffnet nicht")

        // Mindestens ein früheres Gespräch - gegen die echte Brücke gibt es
        // welche, und "leer" hiesse: die Liste kommt nicht an.
        let zeilen = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Frage'"))
        XCTAssertGreaterThan(zeilen.count, 0,
                             "Die Liste ist leer - kein Gespräch zum Auswählen")
        bild(app)

        // Und eines lässt sich öffnen.
        zeilen.element(boundBy: 0).tap()
        let fertig = app.buttons["Fertig"]
        XCTAssertTrue(fertig.waitForExistence(timeout: 20),
                      "Das gewählte Gespräch öffnet nicht")
        bild(app)
    }
}
