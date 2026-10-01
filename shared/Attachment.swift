import Foundation
import UniformTypeIdentifiers

/// A file waiting to go out with the next message - the same on the phone
/// and on the Mac. How a photo becomes one is the platform's business (see
/// the app's Attachment+Photo).
struct Attachment: Identifiable, Sendable {
    let id = UUID()
    let name: String
    let data: Data
    let mediaType: String
    let preview: Data?

    init(name: String, data: Data, mediaType: String, preview: Data?) {
        self.name = name
        self.data = data
        self.mediaType = mediaType
        self.preview = preview
    }

    init?(file url: URL) {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        guard let d = try? Data(contentsOf: url) else { return nil }
        let type = UTType(filenameExtension: url.pathExtension)
        name = url.lastPathComponent
        data = d
        mediaType = type?.preferredMIMEType ?? "application/octet-stream"
        preview = (type?.conforms(to: .image) ?? false) ? d : nil
    }
}

#if os(macOS)
import AppKit

extension Attachment {
    /// A drag and a paste both arrive on a pasteboard - the drag on its own
    /// one. Reading it there is synchronous, where NSItemProvider would mean
    /// handing a non-sendable object across actors for no gain.
    ///
    /// Files come as URLs; a screenshot dragged from its thumbnail and a
    /// picture pulled out of a browser carry the image itself with no name,
    /// and taking only URLs let those fall through.
    @MainActor
    static func read(from pb: NSPasteboard?) -> [Attachment] {
        guard let pb else { return [] }
        if let urls = pb.readObjects(forClasses: [NSURL.self]) as? [URL], !urls.isEmpty {
            return urls.compactMap(Attachment.init(file:))
        }
        for (type, ext, mime) in [(NSPasteboard.PasteboardType.png, "png", "image/png"),
                                  (.tiff, "tiff", "image/tiff"),
                                  (.pdf, "pdf", "application/pdf")] {
            guard let data = pb.data(forType: type) else { continue }
            let f = DateFormatter()
            f.dateFormat = "HH-mm-ss"
            return [Attachment(name: "Bild-\(f.string(from: Date())).\(ext)",
                               data: data, mediaType: mime, preview: ext == "pdf" ? nil : data)]
        }
        return []
    }
}
#endif
