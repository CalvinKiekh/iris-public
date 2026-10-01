import SwiftUI
import AppKit

// Zeichnet die Entfaltung in gleichmaessigen Stufen und legt sie als
// Einzelbilder ab - dazu eine Kontaktbogen-Datei, auf der alle nebeneinander
// stehen. Damit laesst sich eine Animation ansehen, statt sie zu behaupten.
//
//   swift run --package-path tools/orbfilm orbfilm 12 ios/build/film

@MainActor
func zeichne(_ stufen: Int, nach ordner: String) {
    let fm = FileManager.default
    try? fm.createDirectory(atPath: ordner, withIntermediateDirectories: true)
    var bilder: [NSImage] = []

    for i in 0...stufen {
        let grad = Double(i) / Double(stufen)
        let szene = ZStack {
            Palette.ground
            OrbHuelle(grad: grad, haltung: .zuversichtlich,
                      kugel: 34, breite: 300, hoehe: 220,
                      reihe: [118, 96, 64, 52, 47, 41, 41, 29]) {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(alignment: .firstTextBaseline, spacing: 9) {
                        Text("Assistent").font(Face.display(21)).foregroundStyle(Palette.text)
                        Text("bereit").font(Face.mono(10.5)).foregroundStyle(Palette.meta)
                        Spacer(minLength: 0)
                    }
                    Text("Was liegt an?").font(Face.ui(13.5)).foregroundStyle(Palette.soft)
                    Spacer(minLength: 0)
                    Rectangle().fill(Palette.text.opacity(0.07)).frame(height: 1)
                    Text("Frag mich was …").font(Face.ui(13.5)).foregroundStyle(Palette.hint)
                }
                .padding(22)
            }
        }
        .frame(width: 360, height: 280)

        let r = ImageRenderer(content: szene)
        r.scale = 2
        guard let bild = r.nsImage else { continue }
        bilder.append(bild)
        if let tiff = bild.tiffRepresentation,
           let rep = NSBitmapImageRep(data: tiff),
           let png = rep.representation(using: .png, properties: [:]) {
            try? png.write(to: URL(fileURLWithPath: "\(ordner)/stufe-\(String(format: "%02d", i)).png"))
        }
    }

    // Kontaktbogen: alle Stufen nebeneinander, vier je Reihe.
    let spalten = 4
    let reihen = (bilder.count + spalten - 1) / spalten
    let b = bilder.first?.size ?? .zero
    let bogen = NSImage(size: NSSize(width: b.width * CGFloat(spalten),
                                     height: b.height * CGFloat(reihen)))
    bogen.lockFocus()
    for (n, bild) in bilder.enumerated() {
        let x = CGFloat(n % spalten) * b.width
        let y = CGFloat(reihen - 1 - n / spalten) * b.height
        bild.draw(at: NSPoint(x: x, y: y), from: .zero, operation: .sourceOver, fraction: 1)
    }
    bogen.unlockFocus()
    if let tiff = bogen.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
       let png = rep.representation(using: .png, properties: [:]) {
        try? png.write(to: URL(fileURLWithPath: "\(ordner)/bogen.png"))
    }
    print("\(bilder.count) Stufen nach \(ordner)")
}

let args = CommandLine.arguments
let stufen = args.count > 1 ? Int(args[1]) ?? 12 : 12
let ordner = args.count > 2 ? args[2] : "film"
MainActor.assumeIsolated { zeichne(stufen, nach: ordner) }
