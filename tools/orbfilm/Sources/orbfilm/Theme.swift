import SwiftUI

// Aus shared/Theme.swift: nur die Farben und eine schlichte Schriftwahl. Die
// Texturen liegen im App-Bundle und werden hier nicht gebraucht - es geht um
// Form und Bewegung, nicht um Korn.

extension Color {
    init(hex: UInt32, opacity: Double = 1) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255,
                  opacity: opacity)
    }
}

enum Face {
    static func ui(_ s: CGFloat) -> Font { .system(size: s) }
    static func mono(_ s: CGFloat) -> Font { .system(size: s, design: .monospaced) }
    static func display(_ s: CGFloat) -> Font { .system(size: s, design: .serif) }
}

enum Palette {
    /// Twilight, not black: black has no warmth, and the room light needs a
    /// ground to fall on.
    static let ground = Color(hex: 0x2E2A25)
    static let text = Color(hex: 0xF7F4ED)
    /// What you typed - a step quieter than Claude, so the two voices part at
    /// a glance without a bubble around either.
    static let soft = Color(hex: 0xDDD6C8)
    static let meta = Color(hex: 0xA89F8F)
    static let faint = Color(hex: 0x8D8578)
    static let hint = Color(hex: 0x9A9184)
    static let unchecked = Color(hex: 0x8F887C)
    static let brass = Color(hex: 0xE8D3A4)
    static let brassDeep = Color(hex: 0xD6B678)
    static let brassLight = Color(hex: 0xF0DCAE)
    static let brassLabel = Color(hex: 0xA3906C)
    static let onBrass = Color(hex: 0x2A2119)
    static let sage = Color(hex: 0xA8BD93)
    static let sageText = Color(hex: 0xBCCFAB)
    static let clay = Color(hex: 0xC08D7E)
    static let clayText = Color(hex: 0xE0A99B)
    static let clayCode = Color(hex: 0xD3A89C)
    static let codeGround = Color(hex: 0x241F1B)
    static let hair = Color(hex: 0xF7F4ED, opacity: 0.07)
}
