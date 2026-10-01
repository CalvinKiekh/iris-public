@preconcurrency import AVFoundation
import Foundation

/// The resident's answers, out loud: its own recording from the PC (the
/// voice chosen there), or the device's voice when none comes in time.
/// One thing speaks at a time; a new answer cuts the old one short.
@MainActor
final class Speaker: NSObject, AVAudioPlayerDelegate, AVSpeechSynthesizerDelegate {
    private var player: AVAudioPlayer?
    private let synthesizer = AVSpeechSynthesizer()
    private var done: (() -> Void)?
    private(set) var speaking = false
    private var watch: Task<Void, Never>?
    /// The conversation mode: play with the microphone open, on the session
    /// Dictation listens on (see Dictation.duplex).
    var duplex = false

    override init() {
        super.init()
        synthesizer.delegate = self
    }

    /// A recording, as it came from the bridge.
    func play(_ data: Data, then: (() -> Void)? = nil) {
        stop()
        guard let p = try? AVAudioPlayer(data: data) else {
            then?()
            return
        }
        prepareOutput()
        p.delegate = self
        player = p
        done = then
        speaking = p.play()
        if !speaking {
            finish(p)
            return
        }
        // A player cut off by a change of the audio session (the microphone
        // switching on mid-answer) stops without saying so - no "finished"
        // ever came, and every answer after it stayed silent until one was
        // played by hand. So look: stopped playing means done.
        watch = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(400))
                guard let self, self.player === p else { return }
                if !p.isPlaying {
                    self.finish(p)
                    return
                }
            }
        }
    }

    /// The device's own voice - when the PC sends no recording.
    func say(_ text: String, then: (() -> Void)? = nil) {
        stop()
        prepareOutput()
        let u = AVSpeechUtterance(string: text)
        u.voice = AVSpeechSynthesisVoice(language: "de-DE")
        done = then
        speaking = true
        synthesizer.speak(u)
    }

    /// Softer while someone may be talking into the answer - not silent:
    /// a sound alone does not stop it, only words do.
    func duck(_ on: Bool) {
        player?.setVolume(on ? 0.4 : 1, fadeDuration: 0.15)
    }

    func stop() {
        watch?.cancel()
        watch = nil
        player?.stop()
        player = nil
        if synthesizer.isSpeaking { synthesizer.stopSpeaking(at: .immediate) }
        speaking = false
        done = nil
    }

    /// Once per recording: the player's delegate and the watch may both
    /// come; only the first counts.
    private func finish(_ p: AVAudioPlayer? = nil) {
        if let p, player !== p { return }
        watch?.cancel()
        watch = nil
        speaking = false
        player = nil
        let next = done
        done = nil
        next?()
    }

    private func prepareOutput() {
        #if os(iOS)
        // Dictation leaves the session set for recording; answers go to the
        // speaker, loud enough to hear with the phone in hand.
        let s = AVAudioSession.sharedInstance()
        if duplex {
            try? s.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .duckOthers])
        } else {
            try? s.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
        }
        try? s.setActive(true)
        #endif
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in self.finish(player) }
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor in self.finish() }
    }
}
