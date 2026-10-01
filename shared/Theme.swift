import SwiftUI

// iris' design schema in Swift. Every value here comes from the artboards in
// design/ (Main.dc.html, Auswahl.dc.html) - taken, not approximated. When a
// value changes there, it changes here, and nowhere else.

// MARK: - Palette

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

extension Color {
    init(hex: UInt32, opacity: Double = 1) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255,
                  opacity: opacity)
    }
}

// MARK: - Faces

/// Three faces, three jobs: Cormorant for titles and numbers - the one place
/// allowed to be ornamental; Outfit for everything you operate; JetBrains
/// Mono for everything that has to be literally right.
///
/// Fixed sizes on purpose: the layout is drawn to the point, and Dynamic Type
/// scaling it would break the rhythm the design is made of.
enum Face {
    enum Weight { case extraLight, light, regular, medium }

    static func display(_ size: CGFloat, _ weight: Weight = .regular) -> Font {
        let name = switch weight {
        case .extraLight, .light: "CormorantGaramondLight-Light"
        case .regular: "CormorantGaramondLight-Regular"
        case .medium: "CormorantGaramondLight-Medium"
        }
        return .custom(name, fixedSize: size)
    }

    static func ui(_ size: CGFloat, _ weight: Weight = .light) -> Font {
        let name = switch weight {
        case .extraLight: "OutfitThin-ExtraLight"
        case .light: "OutfitThin-Light"
        case .regular: "OutfitThin-Regular"
        case .medium: "OutfitThin-Medium"
        }
        return .custom(name, fixedSize: size)
    }

    static func mono(_ size: CGFloat, _ weight: Weight = .regular) -> Font {
        let name = (weight == .light || weight == .extraLight) ? "JetBrainsMono-Light" : "JetBrainsMono-Regular"
        return .custom(name, fixedSize: size)
    }
}

// MARK: - Room

/// A room, not a background colour: light from above left, a second warm
/// source to the right, a cool one low on the left, and everything falling
/// off towards the edges. Without it the ground reads flat, however good the
/// surfaces on it are.
struct Room: View {
    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            ZStack {
                Palette.ground
                RadialGradient(colors: [Color(hex: 0xFFF4DE, opacity: 0.10), .clear],
                               center: UnitPoint(x: 0.22, y: -0.04), startRadius: 0, endRadius: w * 0.5)
                RadialGradient(colors: [Color(hex: 0xE8CD96, opacity: 0.07), .clear],
                               center: UnitPoint(x: 0.96, y: 0.22), startRadius: 0, endRadius: w * 0.43)
                RadialGradient(colors: [Color(hex: 0x8CAA8C, opacity: 0.06), .clear],
                               center: UnitPoint(x: 0.04, y: 0.84), startRadius: 0, endRadius: w * 0.5)
                LinearGradient(stops: [
                    .init(color: Color(hex: 0xFFFAEE, opacity: 0.03), location: 0),
                    .init(color: .clear, location: 0.26),
                    .init(color: .black.opacity(0.22), location: 1),
                ], startPoint: .top, endPoint: .bottom)
                EllipticalGradient(stops: [
                    .init(color: .clear, location: 0.42),
                    .init(color: .black.opacity(0.42), location: 1),
                ], center: UnitPoint(x: 0.5, y: 0.44), startRadiusFraction: 0, endRadiusFraction: 0.62)
            }
        }
        .overlay(Grain())
        .ignoresSafeArea()
    }
}

/// One grain over everything. It lies on the surfaces and the ground at once,
/// which is what makes them read as one photograph instead of layers.
struct Grain: View {
    var body: some View {
        Texture.image("Korn")
            .resizable(resizingMode: .tile)
            .blendMode(.overlay)
            .opacity(0.6)
            .allowsHitTesting(false)
            .accessibilityHidden(true)
    }
}

// MARK: - Materials

extension View {
    /// Ink: a stretched turbulence, softly blended into a surface. It lives in
    /// the surfaces, never in the ground - that is what lifts them off it.
    ///
    /// Blended against what lies behind the surface, not against the
    /// surface's own fill: a translucent fill gives soft light nothing to work
    /// on, and the ink would show up raw, as pale clouds.
    func inked<S: Shape, F: ShapeStyle>(_ shape: S, _ fill: F, ink: Double = 0.5) -> some View {
        background {
            ZStack {
                shape.fill(fill)
                // Color.clear takes the surface's size; the image fills it and
                // overflows, and is cut to the shape in that frame - not in the
                // larger one scaledToFill would give it on its own.
                Color.clear
                    .overlay { Texture.image("Tinte").resizable().scaledToFill() }
                    .clipShape(shape)
                    .opacity(ink)
                    .blendMode(.softLight)
            }
        }
    }

    /// Luxury is an edge, not a surface: a brass hairline where light would
    /// catch a real edge - bright at the top left, gone towards the bottom.
    func gilt<S: InsettableShape>(_ shape: S, strength: Double = 0.5) -> some View {
        overlay {
            shape.strokeBorder(
                LinearGradient(stops: [
                    .init(color: Palette.brass.opacity(strength), location: 0),
                    .init(color: Palette.brass.opacity(0.1), location: 0.4),
                    .init(color: .clear, location: 0.74),
                ], startPoint: UnitPoint(x: 0.25, y: 0), endPoint: UnitPoint(x: 0.75, y: 1)),
                lineWidth: 1)
            .allowsHitTesting(false)
        }
    }
}

// MARK: - Marks

/// Claude's mark, from the design's 24-unit path. The star is Claude, the open
/// ring is you - the same distinction on every device, learnt once.
struct ClaudeStar: Shape {
    private static let points: [CGPoint] = {
        let data = "12 2.4 1.5 5.1 3.6-3.9-1.3 5.2 5-1.6-4 3.5 4.6 2.2-5.2.3 2.6 4.5-4.3-3"
            + "-.5 5.2-1.9-4.9-3.4 4-.1-5.2-4.8 2 3.4-4-5.2-.6 4.8-2-3.5-3.9 5 1.5"
        let n = data.matches(of: /-?\d*\.?\d+/).compactMap { Double($0.output) }
        var pts = [CGPoint(x: n[0], y: n[1])]
        var i = 2
        while i + 1 < n.count {
            let last = pts[pts.count - 1]
            pts.append(CGPoint(x: last.x + n[i], y: last.y + n[i + 1]))
            i += 2
        }
        return pts
    }()

    func path(in rect: CGRect) -> Path {
        let s = min(rect.width, rect.height) / 24
        var p = Path()
        p.addLines(Self.points.map { CGPoint(x: rect.minX + $0.x * s, y: rect.minY + $0.y * s) })
        p.closeSubpath()
        return p
    }
}


/// A breathing dot. Movement marks what needs attention, and nothing else.
struct Bud: View {
    var color: Color = Palette.brass
    var size: CGFloat = 5

    var body: some View {
        // Eight frames a second carry a slow breath. The endless SwiftUI
        // animation before redrew at 60-120 - one per running session - and
        // kept the Mac app at a fifth of a core doing nothing.
        TimelineView(.animation(minimumInterval: 1 / 8)) { t in
            let phase = (sin(t.date.timeIntervalSinceReferenceDate * .pi / 1.25) + 1) / 2
            Circle().fill(color).frame(width: size, height: size)
                .scaleEffect(1 + 0.45 * phase)
                .opacity(0.55 + 0.4 * phase)
        }
    }
}

/// The small, widely spaced label above a title. Small and wide enough to read
/// as a mark, never as a line you could tap.
struct Eyebrow: View {
    let text: String
    var size: CGFloat
    var color: Color

    init(_ text: String, size: CGFloat = 9.5, color: Color = Palette.meta) {
        self.text = text
        self.size = size
        self.color = color
    }

    var body: some View {
        Text(text.uppercased()).font(Face.mono(size)).tracking(size * 0.28).foregroundStyle(color)
    }
}

struct Hairline: View {
    var body: some View { Rectangle().fill(Palette.hair).frame(height: 1) }
}

/// The context as a stretch: the whole line is the window, the bright part
/// what is used. The pulse runs only through the used part and stops at its
/// end - past it, the drawing would claim more than was measured.
struct ContextLine: View {
    let fraction: Double

    var body: some View {
        // Twelve frames a second: the pulse is slow, and a Canvas redrawn at
        // thirty cost more than everything else on screen.
        TimelineView(.animation(minimumInterval: 1 / 12)) { timeline in
            Canvas { ctx, size in
                let path = Self.curve(in: size)
                let used = min(max(fraction, 0), 1)
                ctx.stroke(path, with: .color(Palette.text.opacity(0.22)),
                           style: StrokeStyle(lineWidth: 1.4, lineCap: .round))
                let filled = path.trimmedPath(from: 0, to: used)
                ctx.stroke(filled, with: .color(Palette.brassDeep.opacity(0.25)),
                           style: StrokeStyle(lineWidth: 4, lineCap: .round))
                ctx.stroke(filled, with: .color(Palette.brass),
                           style: StrokeStyle(lineWidth: 1.8, lineCap: .round))
                let t = timeline.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 3.4) / 3.4
                if used > 0, let pt = path.trimmedPath(from: 0, to: max(0.001, t * used)).currentPoint {
                    let alpha = t < 0.12 ? t / 0.12 : (t > 0.88 ? (1 - t) / 0.12 : 1)
                    ctx.fill(Path(ellipseIn: CGRect(x: pt.x - 2.2, y: pt.y - 2.2, width: 4.4, height: 4.4)),
                             with: .color(Color(hex: 0xF7ECD0).opacity(alpha)))
                }
            }
        }
        .frame(width: 86, height: 12)
        .accessibilityLabel("Kontext \(Int((fraction * 100).rounded())) Prozent belegt")
    }

    static func curve(in s: CGSize) -> Path {
        let sx = s.width / 128, sy = s.height / 12
        var p = Path()
        p.move(to: CGPoint(x: 2 * sx, y: 8 * sy))
        p.addCurve(to: CGPoint(x: 64 * sx, y: 6 * sy),
                   control1: CGPoint(x: 26 * sx, y: 8 * sy), control2: CGPoint(x: 40 * sx, y: 5 * sy))
        p.addCurve(to: CGPoint(x: 126 * sx, y: 6 * sy),
                   control1: CGPoint(x: 88 * sx, y: 7 * sy), control2: CGPoint(x: 104 * sx, y: 5 * sy))
        return p
    }
}

// MARK: - Controls

/// The round buttons of the input: quiet ones for tools, brass for sending.
struct RoundButton: View {
    let symbol: String
    var brass = false
    var active = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 14, weight: brass ? .semibold : .light))
                .foregroundStyle(brass ? Color(hex: 0x1A1710) : (active ? Palette.brass : Color(hex: 0x9A9287)))
                .frame(width: 36, height: 36)
                .background {
                    if brass {
                        Circle()
                            .fill(LinearGradient(colors: [Palette.brass, Color(hex: 0xC8AD74)],
                                                 startPoint: UnitPoint(x: 0.25, y: 0), endPoint: UnitPoint(x: 0.75, y: 1)))
                            .overlay(Circle().strokeBorder(
                                LinearGradient(colors: [.white.opacity(0.5), .clear], startPoint: .top, endPoint: .center),
                                lineWidth: 1))
                            .shadow(color: Color(hex: 0xC8AD74, opacity: 0.55), radius: 6, y: 4)
                    } else {
                        Circle().fill(Color(hex: 0xEFECE5, opacity: active ? 0.14 : 0.06))
                    }
                }
                .padding(4)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
    }
}

struct BrassToggle: View {
    let isOn: Bool

    var body: some View {
        ZStack(alignment: isOn ? .trailing : .leading) {
            Capsule().fill(isOn
                ? AnyShapeStyle(LinearGradient(colors: [Palette.brassLight, Palette.brassDeep],
                                               startPoint: .topLeading, endPoint: .bottomTrailing))
                : AnyShapeStyle(Palette.text.opacity(0.1)))
            Circle().fill(isOn ? Palette.onBrass : Palette.meta).frame(width: 18, height: 18).padding(4)
        }
        .frame(width: 46, height: 26)
        .animation(.spring(duration: 0.3), value: isOn)
    }
}

/// A tick for lists you check off. Brass is the only colour it has - enough
/// to see at a glance what is chosen.
struct Tick: View {
    let on: Bool

    var body: some View {
        ZStack {
            if on {
                RoundedRectangle(cornerRadius: 5)
                    .fill(LinearGradient(colors: [Palette.brassLight, Palette.brassDeep],
                                         startPoint: UnitPoint(x: 0.25, y: 0), endPoint: UnitPoint(x: 0.75, y: 1)))
                Image(systemName: "checkmark").font(.system(size: 9, weight: .heavy)).foregroundStyle(Palette.onBrass)
            } else {
                RoundedRectangle(cornerRadius: 5).strokeBorder(Palette.text.opacity(0.2), lineWidth: 1.5)
            }
        }
        .frame(width: 17, height: 17)
    }
}

// MARK: - Formatting

enum Fmt {
    static func duration(_ t: TimeInterval) -> String {
        if t < 1 { return "\(Int((t * 1000).rounded())) ms" }
        if t < 60 { return String(format: "%.1f s", t).replacingOccurrences(of: ".", with: ",") }
        return clock(t)
    }

    static func clock(_ t: TimeInterval) -> String {
        let s = max(0, Int(t))
        if s >= 3600 { return String(format: "%d:%02d:%02d", s / 3600, (s % 3600) / 60, s % 60) }
        return String(format: "%d:%02d", s / 60, s % 60)
    }

    static func age(_ ts: Double?) -> String {
        guard let ts else { return "" }
        let d = Date().timeIntervalSince1970 - ts
        if d < 60 { return "gerade eben" }
        if d < 3600 { return "vor \(Int(d / 60)) min" }
        if d < 86400 { return "vor \(Int(d / 3600)) h" }
        return "vor \(Int(d / 86400)) d"
    }

    /// A title the bridge cut to 48 characters ends at a word, not inside one.
    static func title(_ s: String) -> String {
        guard s.count >= 46, let space = s.lastIndex(of: " ") else { return s }
        return s[..<space].trimmingCharacters(in: .punctuationCharacters.union(.whitespaces)) + " …"
    }

    /// A path from the Mac, shortened the way the design shows it.
    static func path(_ p: String) -> String {
        if let r = p.range(of: #"^/Users/[^/]+"#, options: .regularExpression) {
            return "~" + p[r.upperBound...]
        }
        return p
    }
}

/// Ink and grain. The phone has them in its asset catalog; the Mac app is a
/// plain Swift package without one and carries them as resources.
enum Texture {
    static func image(_ name: String) -> Image {
        #if SWIFT_PACKAGE && os(macOS)
        // By path inside the app, not through Bundle.module - that one looks
        // in the build folder under ~/Documents first (see the Mac's Fonts).
        let url = Bundle.main.resourceURL?
            .appendingPathComponent("IrisMac_IrisMac.bundle/Resources/Textures/\(name).png")
        if let url, let image = NSImage(contentsOf: url) {
            return Image(nsImage: image)
        }
        return Image(systemName: "square")
        #else
        return Image(name)
        #endif
    }
}

