@preconcurrency import AVFoundation
import Observation
@preconcurrency import Speech

/// The recognition request the microphone feeds - swapped for a fresh one
/// between two things said, while the microphone keeps running. Touched on
/// the audio thread and the main thread, hence the lock.
final class RequestBox: @unchecked Sendable {
    private let lock = NSLock()
    private var request: SFSpeechAudioBufferRecognitionRequest?

    func set(_ r: SFSpeechAudioBufferRecognitionRequest?) {
        lock.lock()
        request = r
        lock.unlock()
    }

    func append(_ buffer: AVAudioPCMBuffer) {
        lock.lock()
        request?.append(buffer)
        lock.unlock()
    }
}

/// What was said, kept as a recording (16 kHz mono WAV) for the resident,
/// who listens to how it was said, not only to the words. Written on the
/// audio thread, begun and taken on the main thread - hence the lock. At
/// most a minute per thing said.
final class RecordBox: @unchecked Sendable {
    private let lock = NSLock()
    private var file: AVAudioFile?
    private var url: URL?
    private var converter: AVAudioConverter?
    private var frames: AVAudioFramePosition = 0
    private let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 16000, channels: 1, interleaved: false)!
    private static let maxFrames: AVAudioFramePosition = 16000 * 60

    func begin() {
        lock.lock()
        defer { lock.unlock() }
        drop()
        let u = FileManager.default.temporaryDirectory.appendingPathComponent("iris-\(UUID().uuidString).wav")
        let settings: [String: Any] = [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 16000,
                                       AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16,
                                       AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false]
        file = try? AVAudioFile(forWriting: u, settings: settings, commonFormat: .pcmFormatFloat32, interleaved: false)
        url = file == nil ? nil : u
        converter = nil
        frames = 0
    }

    /// The recording so far, closed; nil when there is none.
    func take() -> URL? {
        lock.lock()
        defer { lock.unlock() }
        guard let u = url, frames > 1600 else {
            drop()
            return nil
        }
        file = nil                     // closing writes the header
        url = nil
        return u
    }

    func stop() {
        lock.lock()
        drop()
        lock.unlock()
    }

    private func drop() {
        file = nil
        if let url { try? FileManager.default.removeItem(at: url) }
        url = nil
    }

    func write(_ buffer: AVAudioPCMBuffer) {
        lock.lock()
        defer { lock.unlock() }
        guard let file, frames < Self.maxFrames, buffer.frameLength > 0 else { return }
        if converter == nil || converter?.inputFormat != buffer.format {
            converter = AVAudioConverter(from: buffer.format, to: format)
        }
        guard let converter else { return }
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * format.sampleRate / buffer.format.sampleRate + 32)
        guard let out = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: capacity) else { return }
        let given = Given()
        var error: NSError?
        converter.convert(to: out, error: &error) { _, status in
            if given.done {
                status.pointee = .noDataNow
                return nil
            }
            given.done = true
            status.pointee = .haveData
            return buffer
        }
        guard error == nil, out.frameLength > 0 else { return }
        try? file.write(from: out)
        frames += AVAudioFramePosition(out.frameLength)
    }

    private final class Given: @unchecked Sendable { var done = false }
}

#if os(iOS)
/// What the microphone feeds Apple's newer transcriber: its buffers,
/// converted to the format the transcriber wants. Fed on the audio thread,
/// swapped on the main thread between two things said - hence the lock.
final class FeedBox: @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: AsyncStream<AnalyzerInput>.Continuation?
    private var format: AVAudioFormat?
    private var converter: AVAudioConverter?

    func set(_ c: AsyncStream<AnalyzerInput>.Continuation?, format f: AVAudioFormat?) {
        lock.lock()
        continuation?.finish()
        continuation = c
        format = f
        converter = nil
        lock.unlock()
    }

    func feed(_ buffer: AVAudioPCMBuffer) {
        lock.lock()
        defer { lock.unlock() }
        guard let continuation, let format, buffer.frameLength > 0 else { return }
        if converter == nil || converter?.inputFormat != buffer.format {
            converter = AVAudioConverter(from: buffer.format, to: format)
        }
        guard let converter else { return }
        let ratio = format.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio + 32)
        guard let out = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: capacity) else { return }
        let given = Given()
        var error: NSError?
        converter.convert(to: out, error: &error) { _, status in
            if given.done {
                status.pointee = .noDataNow
                return nil
            }
            given.done = true
            status.pointee = .haveData
            return buffer
        }
        if error == nil, out.frameLength > 0 { continuation.yield(AnalyzerInput(buffer: out)) }
    }

    private final class Given: @unchecked Sendable { var done = false }
}

/// Apple's newer on-device transcriber (iOS 26) - clearly more accurate in
/// German than SFSpeechRecognizer. One analysis per thing said; begin()
/// starts the next one on the running microphone.
@MainActor
final class ModernListener {
    private let feed: FeedBox
    private var analyzer: SpeechAnalyzer?
    private var reading: Task<Void, Never>?
    /// It stopped with an error - the recognizer takes over.
    private(set) var failed = false
    private static var downloading = false
    private static let german = Locale(identifier: "de-DE")

    init(feed: FeedBox) { self.feed = feed }

    /// Whether it can be used now. Its German model comes as a download the
    /// first time; while that runs, the recognizer stands in.
    static func ready() async -> Bool {
        guard SpeechTranscriber.isAvailable,
              let locale = await SpeechTranscriber.supportedLocale(equivalentTo: german) else { return false }
        let probe = SpeechTranscriber(locale: locale, preset: .progressiveTranscription)
        do {
            if let request = try await AssetInventory.assetInstallationRequest(supporting: [probe]) {
                if !downloading {
                    downloading = true
                    Task.detached { try? await request.downloadAndInstall() }
                }
                return false
            }
        } catch {
            return false
        }
        return true
    }

    /// A new analysis; what it hears goes to update, the settled part and
    /// the part still changing together.
    func begin(update: @escaping @MainActor (String) -> Void) async throws {
        await end()
        guard let locale = await SpeechTranscriber.supportedLocale(equivalentTo: Self.german) else {
            throw CocoaError(.featureUnsupported)
        }
        let transcriber = SpeechTranscriber(locale: locale, transcriptionOptions: [],
                                            reportingOptions: [.volatileResults, .fastResults], attributeOptions: [])
        guard let format = await SpeechAnalyzer.bestAvailableAudioFormat(compatibleWith: [transcriber]) else {
            throw CocoaError(.featureUnsupported)
        }
        let analyzer = SpeechAnalyzer(modules: [transcriber])
        let (stream, continuation) = AsyncStream<AnalyzerInput>.makeStream()
        try await analyzer.start(inputSequence: stream)
        feed.set(continuation, format: format)
        self.analyzer = analyzer
        reading = Task { [weak self] in
            var settled = ""
            do {
                for try await r in transcriber.results {
                    let text = Self.unheard(String(r.text.characters))
                    let joined = [settled, text].filter { !$0.isEmpty }.joined(separator: " ")
                    if r.isFinal { settled = joined }
                    update(joined)
                }
            } catch is CancellationError {
            } catch {
                self?.failed = true
            }
        }
    }

    /// Phrases these models make up out of a moment of quiet or a noise -
    /// "Thank you" in front of a German sentence was never said. Dropped
    /// where they stand alone at the start of a piece.
    nonisolated static func unheard(_ raw: String) -> String {
        var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let madeUp = ["thank you", "thanks for watching", "thank you for watching", "thanks",
                      "untertitel im auftrag des zdf", "untertitel der amara.org-community",
                      "copyright wdr", "swr"]
        var changed = true
        while changed {
            changed = false
            let lower = text.lowercased()
            for m in madeUp where lower.hasPrefix(m) {
                let rest = lower.dropFirst(m.count)
                // Only a whole phrase: followed by nothing, punctuation or a space.
                guard rest.isEmpty || rest.first.map({ " .,!?;:".contains($0) }) == true else { continue }
                // Only the front: the sentence's own "?" at the end stays - the
                // end-of-speech rule reads it.
                text = String(text.dropFirst(m.count).drop { " .,!?;:\n".contains($0) })
                changed = true
                break
            }
        }
        return text
    }

    func end() async {
        feed.set(nil, format: nil)
        reading?.cancel()
        reading = nil
        if let analyzer { await analyzer.cancelAndFinishNow() }
        analyzer = nil
    }
}
#endif

/// Speaking a task instead of typing it - on the road the faster way, and on
/// the glasses later the only one. German, on the device, nothing stored.
///
/// The model lives on the main thread, but three things here call back on
/// threads of their own: the answer to the permission question, the
/// microphone tap (the audio thread, many times a second), and the
/// recognizer's results. A closure written inside a main-actor type is itself
/// main-actor isolated in Swift 6, and one run on another thread stops the
/// app on the spot. So each of them is made in a nonisolated place and hands
/// over to the main thread explicitly.
@MainActor @Observable
final class Dictation {
    private(set) var listening = false
    private(set) var partial = ""
    /// Listening while an answer plays (the resident's conversation mode):
    /// the phone's echo cancellation keeps the answer out of what it hears,
    /// so speaking up can cut the answer short.
    private(set) var duplex = false
    /// When the microphone last heard a voice rather than the room: the level
    /// above a floor that follows the quiet. A breath stays under it; a cough
    /// does not - it brings no words, so it only makes the pause longer.
    /// Read by a watch, not observed: it changes many times a second.
    @ObservationIgnored private(set) var lastSound = Date.distantPast
    /// When the recognized words last changed.
    @ObservationIgnored private(set) var lastWords = Date.distantPast
    @ObservationIgnored private var floor: Float = -40
    @ObservationIgnored private let box = RequestBox()
    @ObservationIgnored private let recorder = RecordBox()
    #if os(iOS)
    @ObservationIgnored private let feed = FeedBox()
    @ObservationIgnored private var modern: ModernListener?
    #endif

    @ObservationIgnored private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "de-DE"))
    @ObservationIgnored private var engine: AVAudioEngine?
    @ObservationIgnored private var task: SFSpeechRecognitionTask?
    /// Counts the listening rounds. A result belongs to the round it was
    /// heard in; one arriving after that round was cancelled is dropped.
    @ObservationIgnored private var round = 0

    var available: Bool { recognizer?.isAvailable ?? false }

    func start(duplex: Bool = false) async {
        guard !listening, await Self.permitted(), let recognizer, recognizer.isAvailable else { return }
        #if DEBUG
        // The simulator gets no microphone here - its audio service times out
        // and takes the app with it. A UI test stops after the permissions,
        // which is where the app once went down (IRIS_DICTATION=dry).
        if ProcessInfo.processInfo.environment["IRIS_DICTATION"] == "dry" {
            listening = true
            return
        }
        #endif
        do {
            #if os(iOS)
            // The phone shares its audio between apps; the Mac has no such
            // session - the engine takes the input directly.
            let session = AVAudioSession.sharedInstance()
            if duplex {
                try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .duckOthers])
            } else {
                try session.setCategory(.record, mode: .measurement, options: .duckOthers)
            }
            try session.setActive(true, options: .notifyOthersOnDeactivation)
            #endif

            let engine = AVAudioEngine()
            #if os(iOS)
            // Voice processing is what subtracts the phone's own output.
            if duplex { try? engine.inputNode.setVoiceProcessingEnabled(true) }
            #endif
            floor = -40
            lastSound = Date()
            lastWords = Date()
            #if os(iOS)
            let also: (@Sendable (AVAudioPCMBuffer) -> Void)? = { [feed, recorder] b in
                feed.feed(b)
                recorder.write(b)
            }
            #else
            let also: (@Sendable (AVAudioPCMBuffer) -> Void)? = nil
            #endif
            Self.tap(engine.inputNode, into: box, also: also) { [weak self] db in self?.hear(db) }
            engine.prepare()
            try engine.start()
            self.engine = engine
            self.duplex = duplex
            listening = true
            recorder.begin()
            #if os(iOS)
            // The newer transcriber when it is there - unless it was turned
            // off. It was put in because it looked more accurate in German;
            // Calvin used both and found the older one better. Whose ear is
            // right is not something to decide from here, so it is a switch.
            let neu = UserDefaults.standard.object(forKey: "iris.diktat.neu") as? Bool ?? true
            if neu, await ModernListener.ready() {
                let m = ModernListener(feed: feed)
                modern = m
                if !(await beginModern(m)) { modern = nil }
            }
            if modern != nil { return }
            #endif
            recognize()
        } catch {
            stop()
        }
    }

    #if os(iOS)
    private func beginModern(_ m: ModernListener) async -> Bool {
        partial = ""
        lastWords = Date()
        round += 1
        let mine = round
        do {
            try await m.begin { [weak self] text in
                guard let self, mine == self.round, text != self.partial else { return }
                self.partial = text
                self.lastWords = Date()
            }
            return true
        } catch {
            return false
        }
    }
    #endif

    /// Start hearing anew on the running microphone: what was said so far is
    /// dropped, the next thing said begins from nothing. The conversation
    /// keeps the microphone open this way - switching it off and on again
    /// between answer and question upsets the playing answer.
    func fresh() {
        guard listening, engine != nil else { return }
        recorder.begin()
        #if os(iOS)
        if let m = modern, !m.failed {
            partial = ""
            lastWords = Date()
            round += 1
            Task {
                if !(await beginModern(m)) {
                    modern = nil
                    recognize()
                }
            }
            return
        }
        if let m = modern {
            modern = nil
            Task { await m.end() }
        }
        #endif
        task?.cancel()
        recognize()
    }

    private func recognize() {
        guard let recognizer else { return }
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        // Punctuation tells a finished sentence from a pause in one.
        if #available(iOS 16, macOS 13, *) { request.addsPunctuation = true }
        box.set(request)
        partial = ""
        lastWords = Date()
        round += 1
        let mine = round
        task = Self.recognize(with: recognizer, request: request) { [weak self] text, done in
            guard let self, mine == self.round else { return }
            if let text, text != self.partial {
                self.partial = text
                self.lastWords = Date()
            }
            // The recognizer ends a request on its own after a while; in the
            // conversation the microphone stays and a new request takes over.
            if done { self.duplex ? self.fresh() : self.stop() }
        }
    }

    /// Stop and drop what is still on its way. After sending, the recognizer's
    /// late final result would put the sent words back into the field - and
    /// a second tap on send would send them twice.
    func cancel() {
        round += 1
        task?.cancel()
        task = nil
        stop()
    }

    /// What was said since listening began (or since fresh()), as a WAV
    /// file to send along; listening goes on with a new recording.
    func takeRecording() -> URL? {
        let u = recorder.take()
        if listening { recorder.begin() }
        return u
    }

    func stop() {
        recorder.stop()
        #if os(iOS)
        if let m = modern {
            modern = nil
            Task { await m.end() }
        }
        #endif
        box.set(nil)
        engine?.stop()
        engine?.inputNode.removeTap(onBus: 0)
        engine = nil
        task?.finish()
        task = nil
        listening = false
        #if os(iOS)
        // In the conversation an answer may be playing on the same session.
        if !duplex { try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation) }
        #endif
        duplex = false
    }

    private func hear(_ db: Float) {
        guard listening else { return }
        // The floor sinks at once to the quietest and creeps up slowly, so
        // a steady room sound becomes part of it and a voice stands out.
        floor = db < floor ? db : floor + (db - floor) * 0.01
        if db > floor + 12, db > -60 { lastSound = Date() }
    }

    // MARK: off the main thread

    /// The microphone's buffers go straight to the recognizer, on the audio
    /// thread - never through the main thread; only their level is handed over.
    nonisolated private static func tap(_ input: AVAudioInputNode,
                                        into box: RequestBox,
                                        also: (@Sendable (AVAudioPCMBuffer) -> Void)?,
                                        level: @escaping @MainActor @Sendable (Float) -> Void) {
        input.installTap(onBus: 0, bufferSize: 1024, format: input.outputFormat(forBus: 0)) { buffer, _ in
            box.append(buffer)
            also?(buffer)
            guard let samples = buffer.floatChannelData?[0], buffer.frameLength > 0 else { return }
            let n = Int(buffer.frameLength)
            var sum: Float = 0
            for i in 0..<n { sum += samples[i] * samples[i] }
            let db = 10 * log10(max(sum / Float(n), 1e-10))
            Task { @MainActor in level(db) }
        }
    }

    /// Results arrive on the recognizer's queue; what the view needs is
    /// handed to the main thread.
    nonisolated private static func recognize(
        with recognizer: SFSpeechRecognizer,
        request: SFSpeechAudioBufferRecognitionRequest,
        update: @escaping @MainActor @Sendable (String?, Bool) -> Void
    ) -> SFSpeechRecognitionTask {
        recognizer.recognitionTask(with: request) { result, error in
            let text = result?.bestTranscription.formattedString
            let done = error != nil || (result?.isFinal ?? false)
            Task { @MainActor in update(text, done) }
        }
    }

    nonisolated private static func speechAllowed() async -> Bool {
        await withCheckedContinuation { (c: CheckedContinuation<Bool, Never>) in
            SFSpeechRecognizer.requestAuthorization { c.resume(returning: $0 == .authorized) }
        }
    }

    private static func permitted() async -> Bool {
        guard await speechAllowed() else { return false }
        return await AVAudioApplication.requestRecordPermission()
    }
}
