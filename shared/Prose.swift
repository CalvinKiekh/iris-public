import SwiftUI

/// Claude writes Markdown. Shown here with iris' own means instead of raw
/// marks: headings in the display face, tables with a header row and hairlines
/// between rows, code in mono on the code ground, lists with a quiet dash. Bold, inline code and links stay inline.
struct Prose: View {
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(Self.blocks(text).enumerated()), id: \.offset) { _, block in
                view(for: block)
            }
        }
    }

    indirect enum Block {
        case paragraph(String)
        /// What the answer quotes - a file, an earlier finding. The terminal
        /// draws a bar beside it; without a kind of its own the "> " stood
        /// in the middle of a sentence and the quote ran into the text.
        case quote([Block])
        case heading(String, Int)
        case bullets([String])
        case numbered([String])
        case table(header: [String]?, rows: [[String]])
        case code(String)
        case rule
    }

    private func view(for block: Block) -> AnyView {
        AnyView(body(of: block))
    }

    @ViewBuilder private func body(of block: Block) -> some View {
        switch block {
        case .paragraph(let s):
            Text(Self.inline(s, size: 16.5))
                .font(Face.ui(16.5))
                .foregroundStyle(Palette.text)
                .lineSpacing(5)
                .textSelection(.enabled)
        case .heading(let s, let level):
            Text(Self.inline(s, size: level <= 2 ? 21 : 15))
                .font(level <= 2 ? Face.display(21) : Face.ui(15, .regular))
                .foregroundStyle(Palette.text)
                .textSelection(.enabled)
                .padding(.top, 4)
        case .bullets(let items):
            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Text("–").font(Face.ui(15)).foregroundStyle(Palette.meta)
                        Text(Self.inline(item, size: 15.5)).font(Face.ui(15.5)).foregroundStyle(Palette.text)
                            .lineSpacing(4)
                            .textSelection(.enabled)
                    }
                }
            }
        case .numbered(let items):
            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(items.enumerated()), id: \.offset) { i, item in
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Text("\(i + 1)").font(Face.mono(10.5)).foregroundStyle(Palette.meta)
                            .frame(minWidth: 14, alignment: .trailing)
                        Text(Self.inline(item, size: 15.5)).font(Face.ui(15.5)).foregroundStyle(Palette.text)
                            .lineSpacing(4)
                            .textSelection(.enabled)
                    }
                }
            }
        case .quote(let inner):
            HStack(alignment: .top, spacing: 12) {
                Capsule().fill(Palette.hair).frame(width: 2)
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(Array(inner.enumerated()), id: \.offset) { _, b in view(for: b) }
                }
            }
            .fixedSize(horizontal: false, vertical: true)
        case .table(let header, let rows):
            TableBlock(header: header, rows: rows)
        case .code(let s):
            Text(s)
                .font(Face.mono(11))
                .foregroundStyle(Palette.soft)
                .lineSpacing(3)
                .textSelection(.enabled)
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Palette.codeGround))
        case .rule:
            Hairline()
        }
    }

    // MARK: inline

    /// Inline Markdown in iris' faces: code in mono and brass - it is literal -,
    /// bold as the regular cut of the light face.
    static func inline(_ s: String, size: CGFloat) -> AttributedString {
        var a = (try? AttributedString(markdown: s, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
            ?? AttributedString(s)
        for run in a.runs {
            guard let intent = run.inlinePresentationIntent else { continue }
            if intent.contains(.code) {
                a[run.range].font = Face.mono(size * 0.84)
                a[run.range].foregroundColor = Palette.brass
            } else if intent.contains(.stronglyEmphasized) {
                a[run.range].font = Face.ui(size, .regular)
            }
        }
        return a
    }

    // MARK: blocks

    static func blocks(_ text: String) -> [Block] {
        var out: [Block] = []
        var paragraph: [String] = []
        let lines = text.components(separatedBy: "\n")
        var i = 0

        func flush() {
            let p = paragraph.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
            if !p.isEmpty { out.append(.paragraph(p)) }
            paragraph = []
        }

        while i < lines.count {
            let line = lines[i]
            let t = line.trimmingCharacters(in: .whitespaces)

            if t.hasPrefix("```") {
                flush()
                var code: [String] = []
                i += 1
                while i < lines.count, !lines[i].trimmingCharacters(in: .whitespaces).hasPrefix("```") {
                    code.append(lines[i])
                    i += 1
                }
                out.append(.code(code.joined(separator: "\n")))
                i += 1
                continue
            }
            if t.hasPrefix(">") {
                flush()
                var quoted: [String] = []
                while i < lines.count {
                    let q = lines[i].trimmingCharacters(in: .whitespaces)
                    guard q.hasPrefix(">") else {
                        // A blank line inside a quote is usually written as a
                        // bare ">", but an empty one ends it.
                        if q.isEmpty, i + 1 < lines.count,
                           lines[i + 1].trimmingCharacters(in: .whitespaces).hasPrefix(">") {
                            quoted.append("")
                            i += 1
                            continue
                        }
                        break
                    }
                    var rest = String(q.dropFirst())
                    if rest.hasPrefix(" ") { rest.removeFirst() }
                    quoted.append(rest)
                    i += 1
                }
                out.append(.quote(blocks(quoted.joined(separator: "\n"))))
                continue
            }
            if t.hasPrefix("|") {
                flush()
                var raw: [String] = []
                while i < lines.count, lines[i].trimmingCharacters(in: .whitespaces).hasPrefix("|") {
                    raw.append(lines[i].trimmingCharacters(in: .whitespaces))
                    i += 1
                }
                out.append(table(raw))
                continue
            }
            if let level = heading(t) {
                flush()
                out.append(.heading(String(t.drop(while: { $0 == "#" })).trimmingCharacters(in: .whitespaces), level))
                i += 1
                continue
            }
            if t == "---" || t == "***" || t == "___" {
                flush()
                out.append(.rule)
                i += 1
                continue
            }
            if bullet(t) != nil {
                flush()
                var items: [String] = []
                while i < lines.count, let item = bullet(lines[i].trimmingCharacters(in: .whitespaces)) {
                    items.append(item)
                    i += 1
                }
                out.append(.bullets(items))
                continue
            }
            if numbered(t) != nil {
                flush()
                var items: [String] = []
                while i < lines.count, let item = numbered(lines[i].trimmingCharacters(in: .whitespaces)) {
                    items.append(item)
                    i += 1
                }
                out.append(.numbered(items))
                continue
            }
            if t.isEmpty {
                flush()
            } else {
                paragraph.append(line)
            }
            i += 1
        }
        flush()
        return out
    }

    private static func heading(_ t: String) -> Int? {
        let hashes = t.prefix { $0 == "#" }.count
        guard (1...6).contains(hashes), t.dropFirst(hashes).first == " " else { return nil }
        return hashes
    }

    private static func bullet(_ t: String) -> String? {
        for mark in ["- ", "* ", "• "] where t.hasPrefix(mark) { return String(t.dropFirst(2)) }
        return nil
    }

    private static func numbered(_ t: String) -> String? {
        guard let r = t.range(of: #"^\d{1,3}[.)] "#, options: .regularExpression) else { return nil }
        return String(t[r.upperBound...])
    }

    private static func table(_ raw: [String]) -> Block {
        func cells(_ line: String) -> [String] {
            var parts = line.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
            if parts.first == "" { parts.removeFirst() }
            if parts.last == "" { parts.removeLast() }
            return parts
        }
        let isRule: (String) -> Bool = { line in
            let c = cells(line)
            return !c.isEmpty && c.allSatisfy { $0.range(of: #"^:?-{2,}:?$"#, options: .regularExpression) != nil }
        }
        var rows = raw.filter { !isRule($0) }.map(cells)
        var header: [String]?
        if raw.count > 1, isRule(raw[1]), !rows.isEmpty { header = rows.removeFirst() }
        return .table(header: header, rows: rows)
    }
}

/// A table as label-and-value rows: the first column quiet in mono, the rest
/// as reading text, a hairline between rows - the way the Mac's side rail
/// lists its state.
struct TableBlock: View {
    let header: [String]?
    let rows: [[String]]

    private var columns: Int { max(header?.count ?? 0, rows.map(\.count).max() ?? 0) }

    /// Up to three columns share the width and wrap; more scroll sideways,
    /// each cell kept to a readable width - squeezed, they would be letters.
    var body: some View {
        if columns > 3 {
            ScrollView(.horizontal, showsIndicators: false) { grid(cell: 200) }
        } else {
            shared
        }
    }

    /// Each column gets a share of the width by how much it holds; each row
    /// is as tall as its tallest cell at that width. (A Grid measured long
    /// cells wide and drew them narrow - their lines ran into the next row.)
    private var shared: some View {
        let weights = (0..<columns).map { j -> CGFloat in
            let lengths = rows.map { j < $0.count ? $0[j].count : 0 } + [header.map { j < $0.count ? $0[j].count : 0 } ?? 0]
            return CGFloat(min(max(lengths.max() ?? 0, 6), 48))
        }
        let sum = max(weights.reduce(0, +), 1)
        let fractions = weights.map { $0 / sum }
        return VStack(alignment: .leading, spacing: 0) {
            if let header {
                ColumnsRow(fractions: fractions, spacing: 16) {
                    ForEach(0..<columns, id: \.self) { j in
                        Text((j < header.count ? header[j] : "").uppercased())
                            .font(Face.mono(9)).tracking(9 * 0.22)
                            .foregroundStyle(Palette.meta)
                    }
                }
                .padding(.bottom, 7)
            }
            ForEach(Array(rows.enumerated()), id: \.offset) { i, row in
                if i > 0 || header != nil { Hairline() }
                ColumnsRow(fractions: fractions, spacing: 16) {
                    ForEach(0..<columns, id: \.self) { j in
                        cell(j < row.count ? row[j] : "", first: j == 0)
                    }
                }
                .padding(.vertical, 8)
            }
        }
    }

    private func cell(_ text: String, first: Bool) -> some View {
        // The first column names the row: quieter, like a label.
        Text(Prose.inline(text, size: first ? 13 : 14))
            .font(first ? Face.ui(13) : Face.ui(14))
            .foregroundStyle(first ? Palette.soft : Palette.text)
            .lineSpacing(2.5)
            .textSelection(.enabled)
    }

    private func grid(cell width: CGFloat) -> some View {
        Grid(alignment: .topLeading, horizontalSpacing: 16, verticalSpacing: 0) {
            if let header {
                GridRow(alignment: .top) {
                    ForEach(0..<columns, id: \.self) { j in
                        Text((j < header.count ? header[j] : "").uppercased())
                            .font(Face.mono(9)).tracking(9 * 0.22)
                            .foregroundStyle(Palette.meta)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(width: width, alignment: .leading)
                    }
                }
                .padding(.bottom, 7)
            }
            ForEach(Array(rows.enumerated()), id: \.offset) { i, row in
                if i > 0 || header != nil {
                    Hairline().gridCellColumns(columns)
                }
                GridRow(alignment: .top) {
                    ForEach(0..<columns, id: \.self) { j in
                        cell(j < row.count ? row[j] : "", first: j == 0)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(width: width, alignment: .leading)
                    }
                }
                .padding(.vertical, 8)
            }
        }
    }
}

/// One table row: fixed shares of the width, as tall as its tallest cell.
private struct ColumnsRow: Layout {
    let fractions: [CGFloat]
    let spacing: CGFloat

    private func widths(_ total: CGFloat) -> [CGFloat] {
        let free = max(total - spacing * CGFloat(max(fractions.count - 1, 0)), 0)
        return fractions.map { $0 * free }
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let total = proposal.width ?? 320
        let heights = zip(subviews, widths(total)).map { $0.sizeThatFits(ProposedViewSize(width: $1, height: nil)).height }
        return CGSize(width: total, height: heights.max() ?? 0)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        for (view, w) in zip(subviews, widths(bounds.width)) {
            view.place(at: CGPoint(x: x, y: bounds.minY), anchor: .topLeading,
                       proposal: ProposedViewSize(width: w, height: nil))
            x += w + spacing
        }
    }
}

// MARK: - Taking a whole answer

#if os(macOS)
import AppKit
#endif

/// Puts text on the clipboard - the one thing both platforms spell
/// differently and every copy here needs.
enum Clipboard {
    static func put(_ text: String) {
        #if os(macOS)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        #else
        UIPasteboard.general.string = text
        #endif
    }
}

extension View {
    /// A whole answer at once. Selection can only ever take one block - each
    /// paragraph, list and table is its own Text - so the text itself is
    /// offered: a button that appears when the pointer is over the answer,
    /// and "Antwort kopieren" in the context menu, which is also how it
    /// works on the phone, where there is no pointer.
    func copyable(_ text: String) -> some View {
        modifier(Copyable(text: text))
    }
}

private struct Copyable: ViewModifier {
    let text: String
    @State private var taken = false

    func body(content: Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            content
            #if os(macOS)
            // Its own row under the answer, not laid over it: nothing to
            // discover by hovering, and no chip sitting on a line of text.
            HStack(spacing: 0) {
                Spacer(minLength: 0)
                Button(action: copy) {
                    HStack(spacing: 5) {
                        Image(systemName: taken ? "checkmark" : "doc.on.doc")
                            .font(.system(size: 9, weight: .medium))
                        Text(taken ? "kopiert" : "Antwort kopieren").font(Face.mono(9.5))
                    }
                    .foregroundStyle(taken ? Palette.sage : Palette.meta)
                    .padding(.horizontal, 9).padding(.vertical, 4)
                    .background(Capsule().fill(Color(hex: 0xEFECE5, opacity: 0.06)))
                    .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .help("Die ganze Antwort in die Zwischenablage")
            }
            #endif
        }
        .contextMenu {
            Button("Antwort kopieren") { copy() }
        }
    }

    private func copy() {
        Clipboard.put(text)
        taken = true
        Task {
            try? await Task.sleep(for: .seconds(1.6))
            taken = false
        }
    }
}
