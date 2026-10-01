import XCTest

/// Drives the app in the simulator the way a person would - typing, tapping
/// Send, Allow, an option - and checks at the bridge that it arrived.
///
/// Runs against a test bridge that ios/uitest.sh starts: no push, its own
/// state, a scratch folder on the Mac. The runner gets both through
/// TEST_RUNNER_IRIS_URL and TEST_RUNNER_IRIS_WORKDIR.
@MainActor
final class IrisUITests: XCTestCase {
    private var bridge: TestBridge!

    override func setUp() async throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard let url = env["IRIS_URL"], let dir = env["IRIS_WORKDIR"] else {
            throw XCTSkip("IRIS_URL / IRIS_WORKDIR fehlen – über ios/uitest.sh starten")
        }
        bridge = try TestBridge(address: url, workdir: dir)
    }

    private func open(_ key: String, attach: Bool = false) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchEnvironment["IRIS_URL"] = bridge.address
        app.launchEnvironment["IRIS_OPEN"] = key
        if attach { app.launchEnvironment["IRIS_ATTACH"] = "probe" }
        app.launch()
        return app
    }

    private func write(_ text: String, in app: XCUIApplication) {
        let field = app.descendants(matching: .any).matching(identifier: "eingabe").firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 30), "Eingabe fehlt")
        field.tap()
        field.typeText(text)
        let send = app.buttons["senden"]
        XCTAssertTrue(send.waitForExistence(timeout: 5), "Senden fehlt")
        send.tap()
    }

    func testNachrichtSenden() async throws {
        let key = try await bridge.newSession()
        let app = open(key)
        write("Antworte nur mit dem Wort: Messing", in: app)
        // While Claude works the line above the input says so - the
        // terminal's spinner line, here.
        let working = app.descendants(matching: .any)["arbeitszeile"]
        XCTAssertTrue(working.waitForExistence(timeout: 20), "Keine Arbeitszeile, während Claude arbeitet")
        let answered = try await bridge.waitForSay(key, containing: "Messing")
        XCTAssertTrue(answered, "Claude hat nicht geantwortet")
        let shown = app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Messing'")).firstMatch
        XCTAssertTrue(shown.waitForExistence(timeout: 30), "Antwort erscheint nicht in der App")
    }

    func testBefehle() async throws {
        let key = try await bridge.newSession()
        let app = open(key)
        let field = app.descendants(matching: .any).matching(identifier: "eingabe").firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 30), "Eingabe fehlt")
        field.tap()
        field.typeText("/comp")
        // Typing a slash offers the commands that match.
        let suggestion = app.descendants(matching: .any)["vorschlag-compact"]
        XCTAssertTrue(suggestion.waitForExistence(timeout: 15), "Kein Vorschlag für /compact")
        suggestion.tap()
        XCTAssertTrue(app.descendants(matching: .any)["befehl-chip"].waitForExistence(timeout: 5),
                      "Befehl steht nicht in der Eingabe")
        // And the whole list, searchable, each with its explanation.
        app.buttons["befehle"].tap()
        let search = app.descendants(matching: .any).matching(identifier: "befehle-suche").firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 10), "Befehlsliste öffnet sich nicht")
        search.tap()
        search.typeText("goal")
        XCTAssertTrue(app.descendants(matching: .any)["befehl-goal"].waitForExistence(timeout: 10),
                      "/goal fehlt in der Liste")
    }

    func testNeueSitzung() async throws {
        // From the home screen, in the tests' own scratch folder - never in
        // one of the real projects the list also shows.
        let app = XCUIApplication()
        app.launchEnvironment["IRIS_URL"] = bridge.address
        app.launch()
        let start = app.buttons["neue-sitzung"]
        XCTAssertTrue(start.waitForExistence(timeout: 30), "Kein Eintrag „Neue Sitzung“ auf dem Startbildschirm")
        start.tap()
        let folder = app.descendants(matching: .any).matching(identifier: "neu-ordner").firstMatch
        XCTAssertTrue(folder.waitForExistence(timeout: 10), "Ordnerfeld fehlt")
        folder.tap()
        folder.typeText(bridge.workdir)
        app.buttons["neu-starten"].tap()
        // Straight into the new session: its input is there.
        let input = app.descendants(matching: .any).matching(identifier: "eingabe").firstMatch
        XCTAssertTrue(input.waitForExistence(timeout: 30), "Neue Sitzung öffnet sich nicht")
    }

    func testUmbenennen() async throws {
        let key = try await bridge.newSession()
        let app = open(key)
        // Hold the title, pick "Umbenennen", give a name.
        let title = app.descendants(matching: .any).matching(identifier: "titel").firstMatch
        XCTAssertTrue(title.waitForExistence(timeout: 30), "Titel fehlt")
        title.press(forDuration: 1.2)
        let rename = app.buttons["Umbenennen"]
        XCTAssertTrue(rename.waitForExistence(timeout: 10), "Kein „Umbenennen“ im Menü")
        rename.tap()
        let field = app.alerts.textFields.firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 10), "Kein Namensfeld")
        field.typeText("Messingprobe")
        app.alerts.buttons["Speichern"].tap()
        let named = app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Messingprobe'")).firstMatch
        XCTAssertTrue(named.waitForExistence(timeout: 15), "Neuer Name erscheint nicht")
    }

    func testFreigabeErlauben() async throws {
        let key = try await bridge.newSession()
        try await bridge.send(key, "Lege die Datei ui-test.txt mit dem Inhalt ja an. Antworte danach nur mit fertig.")
        try await bridge.waitForAsk(key)
        let app = open(key)
        let allow = app.buttons["Erlauben"]
        XCTAssertTrue(allow.waitForExistence(timeout: 30), "Freigabe erscheint nicht")
        allow.tap()
        let settled = try await bridge.waitForCard(key) {
            $0["kind"] as? String == "answered" && $0["allow"] as? Bool == true
        }
        XCTAssertTrue(settled, "Erlauben kam nicht an")
        let ran = try await bridge.waitForCard(key) { $0["kind"] as? String == "result" && $0["ok"] as? Bool == true }
        XCTAssertTrue(ran, "Datei wurde nicht angelegt")
    }

    func testAuswahlAbhaken() async throws {
        let key = try await bridge.newSession()
        try await bridge.send(key, "Benutze jetzt das Werkzeug AskUserQuestion und frag mich, welche Farbe das Logo "
            + "bekommen soll, mit den Optionen Messing und Salbei. Antworte danach nur mit der gewählten Farbe.")
        try await bridge.waitForAsk(key)
        let app = open(key)
        let option = app.buttons["Salbei"]
        XCTAssertTrue(option.waitForExistence(timeout: 30), "Auswahl erscheint nicht")
        option.tap()
        app.buttons["Loslegen"].tap()
        let answered = try await bridge.waitForSay(key, containing: "Salbei")
        XCTAssertTrue(answered, "Die Wahl kam nicht bei Claude an")
    }

    func testAnhangSenden() async throws {
        let key = try await bridge.newSession()
        let app = open(key, attach: true)
        write("Welche Farbe hat das angehängte Bild? Antworte mit einem Wort.", in: app)
        let sent = try await bridge.waitForCard(key) { card in
            card["kind"] as? String == "sent" && !((card["attachments"] as? [Any]) ?? []).isEmpty
        }
        XCTAssertTrue(sent, "Anhang kam nicht mit der Nachricht an")
        let answered = try await bridge.waitForCard(key) { $0["kind"] as? String == "say" }
        XCTAssertTrue(answered, "Claude hat auf den Anhang nicht geantwortet")
    }
}

extension IrisUITests {
    /// The connection drops while a message is sent: it waits on the phone,
    /// the app says so, and it goes out by itself once the link is back -
    /// exactly once.
    func testWarteschlange() async throws {
        // Never from a cache: an "ok" kept from an earlier run once made the
        // plug look pulled while the request never reached the switch.
        guard let control = ProcessInfo.processInfo.environment["IRIS_CONTROL"],
              let off = URL(string: control + "?seconds=20&n=\(UUID().uuidString)") else {
            throw XCTSkip("IRIS_CONTROL fehlt – über ios/uitest.sh starten")
        }
        var pull = URLRequest(url: off, cachePolicy: .reloadIgnoringLocalAndRemoteCacheData)
        pull.timeoutInterval = 10
        let key = try await bridge.newSession()
        let app = open(key)
        let field = app.descendants(matching: .any).matching(identifier: "eingabe").firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 30), "Eingabe fehlt")
        let (answer, _) = try await URLSession.shared.data(for: pull)   // plug pulled
        XCTAssertEqual(String(decoding: answer, as: UTF8.self), "ok", "Schalter nicht erreicht")
        print("IRIS-BELEG offline geschaltet:", Self.clock())
        write("Antworte nur mit dem Wort: Kobalt", in: app)
        print("IRIS-BELEG Senden getippt:", Self.clock())
        let waiting = app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'wartet auf Verbindung'")).firstMatch
        if !waiting.waitForExistence(timeout: 15) {
            // Evidence instead of guessing: what the app shows, and whether
            // the message got through to the bridge despite the plug.
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.lifetime = .keepAlways
            add(shot)
            let shown = app.staticTexts.allElementsBoundByIndex.map(\.label)
                .filter { $0.contains("Kobalt") || $0.contains("wartet") || $0.contains("Verbindung") || $0.contains("gesendet") }
            print("IRIS-BELEG sichtbar: \(shown)")
            let atBridge = await bridge.cards(key).filter { ($0["text"] as? String ?? "").contains("Kobalt") }
                .map { card -> String in
                    let ts = (card["ts"] as? Double).map { Self.clock(Date(timeIntervalSince1970: $0)) } ?? "?"
                    return "\(card["kind"] ?? "?") um \(ts)"
                }
            print("IRIS-BELEG an der Brücke: \(atBridge)")
            XCTFail("Nachricht wartet nicht sichtbar")
            return
        }
        let offline = app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'nicht erreichbar'")).firstMatch
        XCTAssertTrue(offline.waitForExistence(timeout: 15), "Verbindungsabbruch wird nicht angezeigt")
        let answered = try await bridge.waitForSay(key, containing: "Kobalt")
        XCTAssertTrue(answered, "Nachricht ging nach dem Abbruch nicht raus")
        let sent = await bridge.cards(key).filter {
            $0["kind"] as? String == "sent" && (($0["text"] as? String) ?? "").contains("Kobalt")
        }
        XCTAssertEqual(sent.count, 1, "Nachricht kam nicht genau einmal an")
    }
}

extension IrisUITests {
    /// Dictation: the microphone starts and the app stays up. It once went
    /// down the moment audio and speech recognition got going - their
    /// callbacks arrive on other threads.
    func testDiktat() async throws {
        let key = try await bridge.newSession()
        let app = XCUIApplication()
        app.launchEnvironment["IRIS_URL"] = bridge.address
        app.launchEnvironment["IRIS_OPEN"] = key
        // Up to the permissions and no further: the simulator has no working
        // microphone, the real one is checked on the phone.
        app.launchEnvironment["IRIS_DICTATION"] = "dry"
        app.launch()
        let mic = app.buttons["diktat"]
        XCTAssertTrue(mic.waitForExistence(timeout: 30), "Mikrofon-Knopf fehlt")
        // The permission questions come from the system, not from the app.
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        func allowAll() {
            for _ in 0..<3 {
                let allow = springboard.buttons.matching(
                    NSPredicate(format: "label IN %@", ["Erlauben", "OK", "Allow"])).firstMatch
                guard allow.waitForExistence(timeout: 4) else { return }
                allow.tap()
            }
        }
        mic.tap()
        allowAll()
        try await Task.sleep(nanoseconds: 1_000_000_000)
        // Once allowed: the tap that starts the microphone for real.
        if app.state == .runningForeground, mic.exists, !app.buttons["diktat"].images["waveform"].exists {
            mic.tap()
        }
        try await Task.sleep(nanoseconds: 4_000_000_000)
        XCTAssertEqual(app.state, .runningForeground, "App ist beim Diktieren abgestürzt")
    }

    /// Seconds within the minute, to the millisecond - to line the test's own
    /// steps up with the switch's log.
    static func clock(_ date: Date = Date()) -> String {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss.SSS"
        return f.string(from: date)
    }
}

/// The bridge, as the tests see it: plain HTTP, the card stream read briefly.
struct TestBridge {
    let address: String
    let base: URL
    let token: String
    let workdir: String

    init(address: String, workdir: String) throws {
        guard var c = URLComponents(string: address),
              let t = c.queryItems?.first(where: { $0.name == "token" })?.value else {
            throw XCTSkip("keine Adresse mit Token")
        }
        c.query = nil
        c.path = ""
        self.address = address
        self.base = c.url!
        self.token = t
        self.workdir = workdir
    }

    private func request(_ path: String) -> URLRequest {
        var r = URLRequest(url: base.appendingPathComponent(path))
        r.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        return r
    }

    @discardableResult
    func call(_ path: String, _ body: [String: Any]? = nil) async throws -> [String: Any] {
        var r = request(path)
        if let body {
            r.httpMethod = "POST"
            r.httpBody = try JSONSerialization.data(withJSONObject: body)
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, _) = try await URLSession.shared.data(for: r)
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    func newSession() async throws -> String {
        let d = try await call("api/sessions", ["cwd": workdir])
        guard let key = (d["session"] as? [String: Any])?["key"] as? String else {
            throw XCTSkip("Sitzung ließ sich nicht anlegen: \(d)")
        }
        return key
    }

    func send(_ key: String, _ text: String) async throws {
        try await call("api/sessions/\(key)/message", ["text": text])
    }

    func waitForAsk(_ key: String, timeout: TimeInterval = 150) async throws {
        let end = Date().addingTimeInterval(timeout)
        while Date() < end {
            let d = try await call("api/sessions/\(key)")
            if !((d["open_asks"] as? [Any]) ?? []).isEmpty { return }
            try await Task.sleep(nanoseconds: 1_000_000_000)
        }
        XCTFail("Keine offene Anfrage nach \(Int(timeout)) s")
    }

    /// What the stream holds right now. It stays open by design, so the
    /// reading is cut off after two seconds.
    func cards(_ key: String) async -> [[String: Any]] {
        final class Box { var items: [[String: Any]] = [] }
        let box = Box()
        let r = request("api/sessions/\(key)/events")
        let reader = Task {
            guard let (bytes, _) = try? await URLSession.shared.bytes(for: r) else { return }
            for try await line in bytes.lines {
                guard line.hasPrefix("data: "), let d = line.dropFirst(6).data(using: .utf8),
                      let obj = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { continue }
                box.items.append(obj)
            }
        }
        try? await Task.sleep(nanoseconds: 2_000_000_000)
        reader.cancel()
        return box.items
    }

    func waitForCard(_ key: String, timeout: TimeInterval = 180,
                     _ match: @escaping ([String: Any]) -> Bool) async throws -> Bool {
        let end = Date().addingTimeInterval(timeout)
        while Date() < end {
            if await cards(key).contains(where: match) { return true }
            try await Task.sleep(nanoseconds: 1_500_000_000)
        }
        return false
    }

    func waitForSay(_ key: String, containing text: String) async throws -> Bool {
        try await waitForCard(key) {
            $0["kind"] as? String == "say" && (($0["text"] as? String) ?? "").localizedCaseInsensitiveContains(text)
        }
    }
}
