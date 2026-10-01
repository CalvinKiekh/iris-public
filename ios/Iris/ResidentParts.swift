import SwiftUI

/// The pieces the resident's pages are built from. Atlas showed the shape:
/// a figure is a tile, a state is a mark, a line that leads somewhere says so.
/// The look stays ours - warm ground, Cormorant for figures, brass and sage
/// instead of neon, and a chevron you have to look for rather than one that
/// shouts.

// MARK: - Kennzahl

/// One figure, and what makes it readable. A number alone says nothing:
/// "39 GB" needs "von 61,6" beside it, "131" needs "Token je Sekunde".
struct Kennzahl: View {
    let label: String
    let wert: String
    var dazu: String?
    /// Worth a look - drawn in brass instead of the quiet ground.
    var betont = false

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label.uppercased())
                .font(Face.mono(8.5)).tracking(0.9)
                .foregroundStyle(betont ? Palette.brassLabel : Palette.faint)
            Text(wert)
                .font(Face.display(27))
                .foregroundStyle(betont ? Palette.brass : Palette.text)
                .lineLimit(1).minimumScaleFactor(0.6)
            if let dazu {
                Text(dazu)
                    .font(Face.ui(11)).foregroundStyle(Palette.meta)
                    .lineLimit(1).minimumScaleFactor(0.8)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 12).padding(.vertical, 11)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color(hex: 0x241F1B, opacity: 0.55))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(betont ? Palette.brass.opacity(0.28) : Palette.hair, lineWidth: 1)
        )
    }
}

/// Figures side by side, as many as fit without squeezing.
struct Kennzahlen: View {
    let zahlen: [Kennzahl]

    var body: some View {
        HStack(alignment: .top, spacing: 9) {
            ForEach(Array(zahlen.enumerated()), id: \.offset) { _, z in z }
        }
    }
}

// MARK: - Marke

/// How something stands, in a word and a colour: awake, thinking, quiet,
/// gone. Muted on purpose - this page is read in the evening, not in a
/// control room.
struct Marke: View {
    enum Ton { case gut, laeuft, ruhig, schlecht }
    let text: String
    var ton: Ton = .ruhig

    private var farbe: Color {
        switch ton {
        case .gut: return Palette.sage
        case .laeuft: return Palette.brass
        case .ruhig: return Palette.meta
        case .schlecht: return Palette.clay
        }
    }

    var body: some View {
        HStack(spacing: 5) {
            Circle().fill(farbe).frame(width: 5, height: 5)
            Text(text).font(Face.ui(11.5)).foregroundStyle(farbe.opacity(0.92))
        }
        .padding(.horizontal, 8).padding(.vertical, 3.5)
        .background(Capsule().fill(farbe.opacity(0.10)))
    }
}

// MARK: - Zeile

/// A line that answers three questions at a glance: what it is, what it is
/// more precisely, and how it stands. Tapping is offered, never demanded -
/// the chevron appears only where there is somewhere to go.
struct Zeile<Rechts: View>: View {
    let titel: String
    var dazu: String?
    var fuehrt = false
    @ViewBuilder var rechts: Rechts
    var tippen: (() -> Void)?

    init(_ titel: String, dazu: String? = nil, fuehrt: Bool = false,
         @ViewBuilder rechts: () -> Rechts = { EmptyView() },
         tippen: (() -> Void)? = nil) {
        self.titel = titel
        self.dazu = dazu
        self.fuehrt = fuehrt
        self.rechts = rechts()
        self.tippen = tippen
    }

    var body: some View {
        let inhalt = HStack(alignment: .firstTextBaseline, spacing: 9) {
            Text(titel).font(Face.ui(14.5)).foregroundStyle(Palette.text)
                .lineLimit(1)
            if let dazu {
                // Beside the name, not beneath it - that is what makes a list
                // scannable instead of a stack of paragraphs.
                Text(dazu).font(Face.ui(12)).foregroundStyle(Palette.meta)
                    .lineLimit(1).truncationMode(.tail)
            }
            Spacer(minLength: 8)
            rechts
            if fuehrt {
                Image(systemName: "chevron.right")
                    .font(.system(size: 10, weight: .light))
                    .foregroundStyle(Palette.faint)
                    .alignmentGuide(.firstTextBaseline) { $0[.bottom] - 1 }
            }
        }
        .padding(.vertical, 9)
        .contentShape(Rectangle())

        if let tippen {
            Button(action: tippen) { inhalt }.buttonStyle(.plain)
        } else {
            inhalt
        }
    }
}

/// Lines with a hairline between them, so they read as one object.
struct Zeilen<Inhalt: View>: View {
    @ViewBuilder var inhalt: Inhalt

    var body: some View {
        VStack(alignment: .leading, spacing: 0) { inhalt }
            .padding(.horizontal, 13)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Color(hex: 0x241F1B, opacity: 0.4))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(Palette.hair, lineWidth: 1)
            )
    }
}

/// The hairline between two lines.
struct ZeilenStrich: View {
    var body: some View {
        Rectangle().fill(Palette.hair).frame(height: 1)
    }
}

// MARK: - Register

/// The four ways to look at him. Not a scroll through seven sections but
/// four rooms - what he is doing, what he did, who he is, and talking to him.
struct Register: View {
    let namen: [String]
    @Binding var gewaehlt: Int

    var body: some View {
        HStack(spacing: 0) {
            ForEach(Array(namen.enumerated()), id: \.offset) { i, name in
                Button { gewaehlt = i } label: {
                    VStack(spacing: 6) {
                        Text(name)
                            .font(Face.ui(13))
                            .foregroundStyle(i == gewaehlt ? Palette.text : Palette.meta)
                        Rectangle()
                            .fill(i == gewaehlt ? Palette.brass : Color.clear)
                            .frame(height: 1.5)
                    }
                    .frame(maxWidth: .infinity)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("bewohner-register-\(i)")
            }
        }
        .animation(.easeOut(duration: 0.15), value: gewaehlt)
    }
}
