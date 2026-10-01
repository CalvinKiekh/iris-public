import PhotosUI
import SwiftUI
import UIKit

/// What only the phone does with attachments: photos from the library, a
/// probe for the UI tests, and the strip above the input.
extension Attachment {
    /// Claude reads JPEG, PNG, GIF and WebP - not HEIC, which is what the
    /// camera writes. Photos are turned into JPEG and brought down to 1600
    /// points on the long side: past that Claude scales them down anyway, and
    /// every megabyte less goes out faster over a phone connection.
    init?(photo item: PhotosPickerItem) async {
        guard let raw = try? await item.loadTransferable(type: Data.self),
              let image = UIImage(data: raw) else { return nil }
        let longest = max(image.size.width, image.size.height)
        let scale = min(1, 1600 / max(longest, 1))
        let size = CGSize(width: image.size.width * scale, height: image.size.height * scale)
        let resized = UIGraphicsImageRenderer(size: size).image { _ in image.draw(in: CGRect(origin: .zero, size: size)) }
        guard let jpeg = resized.jpegData(compressionQuality: 0.85) else { return nil }
        let stamp = Date().formatted(.iso8601.year().month().day().time(includingFractionalSeconds: false))
            .replacingOccurrences(of: ":", with: "")
        name = "foto-\(stamp).jpg"
        data = jpeg
        mediaType = "image/jpeg"
        preview = jpeg
    }

    #if DEBUG
    /// A small square in brass - for UI tests, which cannot use the picker.
    static func probe() -> Attachment {
        let size = CGSize(width: 96, height: 96)
        let image = UIGraphicsImageRenderer(size: size).image { ctx in
            UIColor(red: 0xE8 / 255, green: 0xD3 / 255, blue: 0xA4 / 255, alpha: 1).setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
        }
        let jpeg = image.jpegData(compressionQuality: 0.9) ?? Data()
        return Attachment(name: "probe.jpg", data: jpeg, mediaType: "image/jpeg", preview: jpeg)
    }
    #endif
}

/// The attachments above the input, each with a way to take it back.
struct AttachmentStrip: View {
    @Binding var attachments: [Attachment]

    var body: some View {
        ScrollView(.horizontal) {
            HStack(spacing: 8) {
                ForEach(attachments) { a in
                    HStack(spacing: 8) {
                        if let p = a.preview, let img = UIImage(data: p) {
                            Image(uiImage: img).resizable().scaledToFill()
                                .frame(width: 34, height: 34)
                                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                        } else {
                            Image(systemName: "doc").font(.system(size: 13, weight: .light))
                                .foregroundStyle(Palette.meta).frame(width: 34, height: 34)
                        }
                        Text(a.name).font(Face.mono(10)).foregroundStyle(Palette.soft).lineLimit(1)
                            .frame(maxWidth: 120, alignment: .leading)
                        Button {
                            attachments.removeAll { $0.id == a.id }
                        } label: {
                            Image(systemName: "xmark").font(.system(size: 9, weight: .semibold))
                                .foregroundStyle(Palette.meta).frame(width: 22, height: 22)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("\(a.name) entfernen")
                    }
                    .padding(.leading, 4).padding(.trailing, 6).padding(.vertical, 4)
                    .background(Capsule().fill(Color(hex: 0xEFECE5, opacity: 0.05)))
                    .overlay(Capsule().strokeBorder(Palette.brass.opacity(0.18), lineWidth: 1))
                }
            }
        }
        .scrollIndicators(.hidden)
    }
}
