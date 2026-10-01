import Foundation
import Observation

enum Route: Hashable {
    case project(Project)
    case session(String)
    case services
}

/// Everything the app knows across screens: the computers it can reach, and
/// for the one in use its sessions, projects and away switch.
@MainActor @Observable
final class AppModel {
    private(set) var bridge: Bridge?
    private(set) var machines: [Machine] = []
    private(set) var machine: Machine?
    var path: [Route] = []
    private(set) var sessions: [SessionInfo] = []
    /// Was ein Update von Claude Code täte - nil, solange nicht gefragt.
    private(set) var update: UpdatePlan?
    private(set) var projects: [Project] = []
    private(set) var away = false
    private(set) var services: ServiceSummary?
    private(set) var modes: [Mode] = []
    private(set) var shortcuts: [Shortcut] = []
    private(set) var quota: Quota?
    private(set) var problem: String?
    private(set) var serviceRows: [ServiceRow] = []
    /// Die Auftraege unter Aufsicht. Der Orb lebt davon, und die App fragt
    /// sie im selben Takt wie die Sitzungen ab - es sind ein paar Zeilen
    /// JSON, keine eigene Runde wert.
    private(set) var wachen: [Wache] = []
    /// Was die App von sich aus getan hat und du wissen solltest - etwa, dass
    /// sie den Rechner gewechselt hat.
    var notiz: String?
    /// Ob diese Bruecke den Wachen-Endpunkt ueberhaupt kennt. Wird beim
    /// Rechnerwechsel zurueckgesetzt.
    @ObservationIgnored private var wachenFehlen = false
    /// Wann zuletzt eine Antwort ankam und wie viele Sitzungen darin standen.
    /// Nur zum Suchen da - wenn die Ursache gefunden ist, fliegt es raus.
    private(set) var zuletztGeholt: Date?
    private(set) var zuletztAnzahl = -1
    private(set) var versuche = 0
    /// Welcher Abruf gerade lief - damit ein Fehler sagt, woran er hing.
    private(set) var letzterAufruf = ""
    /// Alles, was die Bruecke fuehrt - samt Assistent. `sessions` laesst ihn
    /// aus, dieser Vorrat nicht: gefunden werden muss er trotzdem.
    private(set) var alleSitzungen: [SessionInfo] = []

    var diagnose: String {
        let wo = machine?.base.absoluteString ?? "keine Brücke"
        guard let t = zuletztGeholt else {
            let woran = letzterAufruf.isEmpty ? "" : " bei \(letzterAufruf)"
            return "\(wo) · \(versuche) Versuche, nie geantwortet\(woran)"
        }
        let alter = Int(Date().timeIntervalSince(t))
        return "\(wo) · \(zuletztAnzahl) Sitzungen vor \(alter) s"
    }

    /// Ob auf diesem Rechner ein Vorarbeiter laeuft. Erst dann hat der Orb
    /// etwas darzustellen - vorher waere er eine Kugel ohne Gegenueber.
    var hatVorarbeiter: Bool { vorarbeiter != nil }

    var vorarbeiter: SessionInfo? {
        alleSitzungen.first { $0.rolle == "vorarbeiter" && !$0.exited }
    }

    /// Den Vorarbeiter holen, falls es ihn gibt. Legt nichts an.
    ///
    /// Anlegen beim blossen Aufklappen war ein teurer Fehler: jedes Oeffnen
    /// der Tafel startete eine echte Claude-Sitzung, und weil eine Bruecke
    /// ohne `rolle` sie als gewoehnliche fuehrt, wurde sie beim naechsten Mal
    /// nicht wiedererkannt - also gleich noch eine. Gemeldet von Calvin,
    /// 25.09.: „die App ist komisch vom Verhalten."
    func vorarbeiterModell() -> SessionModel? {
        guard let v = vorarbeiter else { return nil }
        return model(for: v.key)
    }

    /// Ihn anlegen - nur beim ersten Wort an ihn, nie beim Ansehen.
    ///
    /// Und mit Kontrolle danach: fuehrt die Bruecke ihn nicht als Vorarbeiter
    /// (weil sie zu alt ist), wird die Sitzung gleich wieder geschlossen. Eine
    /// gewoehnliche Sitzung, die sich als Assistent ausgibt, waere schlimmer
    /// als keiner.
    func vorarbeiterAnlegen() async -> SessionModel? {
        if let v = vorarbeiter { return model(for: v.key) }
        guard let key = await start(cwd: "", rolle: "vorarbeiter") else { return nil }
        await refresh()
        guard let neu = alleSitzungen.first(where: { $0.key == key }) else { return nil }
        guard neu.rolle == "vorarbeiter" else {
            await schliessen(session: key)
            problem = "Diese Brücke kennt noch keinen Assistenten — sie braucht einen Neustart."
            return nil
        }
        return model(for: key)
    }

    /// Der Rechner, der durchlaeuft: ein erreichbarer, der kein Mac ist.
    ///
    /// Kein Kunstgriff, sondern die Lage: Macs klappen zu und werden
    /// mitgenommen, der Pi steht und laeuft. Antwortet keiner, bleibt es beim
    /// gewaehlten - ein Assistent hier ist besser als keiner.
    private func dauerlaeufer() async -> Machine? {
        for m in machines {
            guard let b = Connection.bridge(for: m) else { continue }
            guard let h = try? await BridgeClient(b).get("api/health", as: HealthBody.self),
                  (h.platform ?? "") != "darwin" else { continue }
            return m
        }
        return nil
    }

    private func schliessen(session key: String) async {
        guard let client else { return }
        _ = try? await client.post("api/sessions/\(key)/close", EmptyBody(), as: OkBody.self)
        await refresh()
    }
    var pushProblem: String?

    @ObservationIgnored private var models: [String: SessionModel] = [:]
    @ObservationIgnored private var known: [String: SessionInfo] = [:]
    /// Computers whose own name was asked for already, this run.
    @ObservationIgnored private var named: Set<String> = []

    /// One for the whole app - the notification handler reaches it when a tap
    /// on a notification has to open a session.
    static let shared = AppModel()

    init() {
        machines = Connection.machines()
        machine = Connection.current(in: machines)
        bridge = machine.flatMap(Connection.bridge(for:))
        quota = Quota.load()
    }

    var client: BridgeClient? { bridge.map { BridgeClient($0) } }

    /// Takes the address `make token` prints. Returns what is wrong with it,
    /// or nil when it is in use.
    func connect(_ text: String) -> String? {
        guard let b = Bridge.parse(text) else {
            return "Das ist keine vollständige Adresse mit Zugangsschlüssel (…/?token=…)."
        }
        let m = Connection.add(b, name: b.base.host ?? "Rechner")
        machines = Connection.machines()
        use(m)
        return nil
    }

    /// Switches to another computer. What was on screen belonged to the one
    /// before, so it goes.
    /// Der Nachlade-Kreislauf. Er gehoert dem Modell, nicht einer Ansicht.
    ///
    /// Vorher lief er im `.task` der Uebersicht - und weil dort eine Zeile
    /// davor stand, die auf einen seit Tagen ausgeschalteten Rechner wartete,
    /// lief er gar nicht. Die App zeigte nichts und meldete nichts, weil
    /// nichts fehlgeschlagen war. Am Modell kann keine Ansicht ihn mehr
    /// aufhalten. (Calvin, 25.09.)
    @ObservationIgnored private var takt: Task<Void, Never>?

    private func taktStarten() {
        takt?.cancel()
        takt = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }

    func use(_ m: Machine) {
        guard let b = Connection.bridge(for: m) else { return }
        Connection.currentID = m.id
        machine = m
        bridge = b
        taktStarten()
        path = []
        sessions = []
        // Anhalten, nicht nur vergessen. Ein SessionModel fragt ueber
        // app?.client - also immer die *aktuelle* Bruecke, nicht die, zu der
        // seine Sitzung gehoert. Blieb es nach dem Umschalten laufen, fragte
        // es den neuen Rechner nach Schluesseln, die es dort nie gab: im
        // Logbuch der Pi-Bruecke eine Reihe 404 auf `t-...`-Schluessel vom
        // Mac. Geschadet hat es nichts, aber es sucht im Fremden.
        wachenFehlen = false
        wachen = []
        for m in models.values { m.stop() }
        projects = []
        models = [:]
        known = [:]
        services = nil
        serviceRows = []
        modes = []
        shortcuts = []
        away = false
        problem = nil
    }

    /// The name the computer gives itself - for the list, and for telling
    /// which one a notification came from.
    private func nameMachine() async {
        guard let m = machine, m.id != "env", m.id != "local", !named.contains(m.id), let client,
              let h = try? await client.get("api/health", as: HealthBody.self) else { return }
        named.insert(m.id)
        guard let name = h.name, !name.isEmpty, name != m.name else { return }
        Connection.rename(m.id, to: name)
        machines = Connection.machines()
        machine = machines.first { $0.id == m.id }
    }

    /// Removes the computer in use; the next one, if any, takes its place.
    func forget() {
        guard let m = machine else { return }
        Connection.remove(m.id)
        machines = Connection.machines()
        machine = nil
        bridge = nil
        path = []
        sessions = []
        projects = []
        models = [:]
        if let next = Connection.current(in: machines) { use(next) }
    }

    func refresh() async {
        versuche += 1
        guard let client else { return }
        await nameMachine()
        do {
            // Nacheinander, nicht nebeneinander. Mit `async let` bricht Swift
            // die uebrigen ab, sobald eines scheitert - und was die App dann
            // meldet, ist oft nur der Abbruch der Geschwister: „cancelled",
            // waehrend die eigentliche Ursache verschwindet. Drei kleine
            // Abrufe hintereinander kosten Millisekunden und sagen, woran es
            // wirklich hing. Gemeldet von Calvin am 26.09.
            letzterAufruf = "api/sessions"
            let sb = try await client.get("api/sessions", as: SessionsBody.self)
            letzterAufruf = "api/projects"
            let pb = try await client.get("api/projects", as: ProjectsBody.self)
            letzterAufruf = "api/terminals/away"
            let ab = try await client.get("api/terminals/away", as: AwayBody.self)
            letzterAufruf = ""
            // Der Assistent gehoert nicht in die Liste deiner Arbeit. Er ist
            // eine Anwesenheit, kein Auftrag - und wer ihn in der Liste
            // antippt, landet in einer gewoehnlichen Sitzungsansicht, genau
            // dem, was der Orb vermeiden soll. Gemeldet von Calvin, 25.09.
            sessions = sb.sessions.filter { $0.rolle != "vorarbeiter" }
            alleSitzungen = sb.sessions
            zuletztGeholt = Date()
            zuletztAnzahl = sb.sessions.count
            projects = pb.projects
            away = ab.away
            problem = nil
            for info in sessions {
                known[info.key] = info
                models[info.key]?.update(info)
            }
        } catch {
            problem = Bridge.explain(error, on: machine?.name)
        }
        // Die Wachen danach und getrennt: sie duerfen den Verlauf nie
        // aufhalten. Und nur so lange, wie die Bruecke sie kennt.
        //
        // Einmal 404 heisst: diese Bruecke ist aelter, das aendert sich nicht
        // im Betrieb. Ohne dieses Merken fragte die App bei jedem Durchgang
        // erneut, das Logbuch war eine Wand aus 404, und jede Absage liess
        // eine Verbindung zurueck - einunddreissig offene, der Vorrat voll,
        // und die Abfrage der Sitzungen kam nicht mehr durch. In der App:
        // alles leer. Gemeldet von Calvin, 25.09.
        if !wachenFehlen {
            if let r = try? await client.get("api/wachen", as: WachenBody.self) {
                wachen = r.wachen
            } else {
                wachenFehlen = true
                wachen = []
            }
        }
        // What waits on the phone goes out now - also for sessions not open.
        for m in models.values where m.hasOutbox { await m.flushOutbox() }
        // The plan's limits - one account, whichever computer answers.
        if let u = try? await client.get("api/usage", as: UsageBody.self), let q = Quota(u) { updateQuota(q) }
        if let sv = try? await client.get("api/services", as: ServicesBody.self) { services = sv.summary }
        if modes.isEmpty, let m = try? await client.get("api/modes", as: ModesBody.self) { modes = m.modes }
        if shortcuts.isEmpty, let sc = try? await client.get("api/shortcuts", as: ShortcutsBody.self) {
            shortcuts = sc.shortcuts
        }
        // Whether a new Claude Code is out. Asked along with everything else
        // and shown only when there is one - a row saying "nothing to do" is
        // a row in the way.
        update = try? await client.get("api/aktualisieren", as: UpdatePlan.self)
    }

    /// Claude Code aktualisieren, ohne die Terminals zu verlieren.
    ///
    /// Ends every idle terminal session, upgrades, and brings each one back
    /// into its own tab with `--resume`. The session id stays the same, so
    /// the conversation comes back with it. Runs long - the bridge does the
    /// waiting, and the answer says what did not come back.
    func runUpdate() async -> UpdateErgebnis? {
        Trace.write("Update gedrückt")
        guard let client else {
            Trace.write("Update: keine Verbindung")
            return nil
        }
        do {
            // Fuenf Minuten: beenden, brew, zurueckholen. Mit den sonst
            // ueblichen 20 Sekunden gab die App auf, bevor brew fertig war.
            let r: UpdateErgebnis = try await client.post(
                "api/aktualisieren", [String: String](), frist: 300)
            Trace.write("Update fertig: ok=\(r.ok) \(r.vorher) -> \(r.nachher)"
                        + (r.grund.isEmpty ? "" : " · \(r.grund)"))
            await refresh()
            return r
        } catch {
            Trace.write("Update fehlgeschlagen: "
                        + Bridge.explain(error, on: machine?.name))
            await refresh()
            return nil
        }
    }

    /// One model per session, kept while the app runs: going back and forth
    /// must not lose what was already on screen.
    func model(for key: String) -> SessionModel {
        if let m = models[key] { return m }
        let m = SessionModel(key: key, info: known[key], app: self)
        models[key] = m
        return m
    }

    /// Shows what the bridge confirmed, never what was only asked for - a
    /// switch that says "away" while the bridge still thinks otherwise would
    /// leave approvals waiting at a Mac nobody sits at.
    func setAway(_ on: Bool) async {
        guard let client else { return }
        do {
            away = try await client.post("api/terminals/away", AwayBody(away: on), as: AwayBody.self).away
            problem = nil
        } catch {
            problem = Bridge.explain(error, on: machine?.name)
        }
    }

    func conversations(of project: Project) async -> [Conversation] {
        guard let client else { return [] }
        let r = try? await client.get("api/projects/\(project.id)/sessions",
                                      query: [URLQueryItem(name: "path", value: project.path)],
                                      as: ConversationsBody.self)
        return r?.sessions ?? []
    }

    /// A conversation that is live in a terminal is not forked - it is opened
    /// as the terminal session it is.
    func liveTerminal(for conversation: Conversation) -> SessionInfo? {
        sessions.first { $0.terminal && !$0.exited && $0.claudeSessionId == conversation.sessionId }
    }

    func start(cwd: String, resume: String? = nil, fork: Bool = false,
               rolle: String? = nil) async -> String? {
        guard let client else { return nil }
        do {
            let r = try await client.post("api/sessions",
                                          CreateBody(cwd: cwd, resume: resume, fork: fork, rolle: rolle),
                                          as: SessionBody.self)
            known[r.session.key] = r.session
            return r.session.key
        } catch {
            problem = Bridge.explain(error, on: machine?.name)
            return nil
        }
    }

    /// Names a session - the bridge keeps it, so every device shows it. An
    /// empty name gives the automatic title back.
    @discardableResult
    func rename(session key: String, to title: String) async -> Bool {
        guard let client else { return false }
        do {
            _ = try await client.post("api/sessions/\(key)/title", TitleBody(title: title), as: OkBody.self)
            await refresh()
            return true
        } catch {
            problem = Bridge.explain(error, on: machine?.name)
            return false
        }
    }

    /// Halt. Wie `STOP` beim Bewohner: ein Griff, der wirkt, auch wenn alles
    /// andere klemmt - er beendet die Wache, nicht die Sitzung. Was dort
    /// gerade laeuft, laeuft zu Ende; nur beauftragt wird nichts mehr.
    @discardableResult
    func wacheBeenden(_ id: String) async -> Bool {
        guard let client else { return false }
        let ok = (try? await client.post("api/wachen/\(id)/ende",
                                         GrundBody(grund: "In der App angehalten"),
                                         as: OkBody.self)) != nil
        await refresh()
        return ok
    }

    /// Die naechste Bruecke, die antwortet - und nur dann wird gewechselt.
    ///
    /// Bewusst ohne Vorlieben: die Reihenfolge ist die deiner Liste. Was
    /// zuerst antwortet, gewinnt; wer gar nicht antwortet, aendert nichts,
    /// damit ein kurzer Netzhaenger dich nicht auf einen anderen Rechner
    /// schiebt.
    private func weiterZuEinerDieAntwortet() async {
        guard machines.count > 1, let jetzt = machine else { return }
        for kandidat in machines where kandidat.id != jetzt.id {
            guard let b = Connection.bridge(for: kandidat) else { continue }
            let probe = BridgeClient(b)
            guard (try? await probe.get("api/health", as: OkBody.self)) != nil else { continue }
            let vorher = jetzt.name
            use(kandidat)
            problem = nil
            notiz = "\(vorher) antwortet nicht — auf \(kandidat.name) gewechselt."
            await refresh()
            return
        }
    }

    func refreshServices() async {
        guard let client else { return }
        if let r = try? await client.get("api/services", as: ServicesFullBody.self, snakeCase: false) {
            serviceRows = r.services
            services = r.summary
        }
    }

    /// Straight to a session - from a tapped notification, which says which
    /// computer it came from.
    func open(session key: String, machine name: String? = nil) {
        if let name, name != machine?.name, let m = machines.first(where: { $0.name == name }) { use(m) }
        path = [.session(key)]
    }

    func updateQuota(_ q: Quota) {
        guard q != quota else { return }
        quota = q
        q.save()
    }
}
