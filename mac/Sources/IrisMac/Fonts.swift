import CoreText
import Foundation

/// The iris typefaces (Cormorant Garamond, Outfit, JetBrains Mono) come with
/// the package. The phone names them in its Info.plist; the Mac registers
/// them for this process at launch.
enum Fonts {
    /// The package's resource bundle inside the app, found by path. Not
    /// Bundle.module: its lookup tries the build folder under ~/Documents,
    /// which makes macOS ask for access to Documents and blocks the launch
    /// until someone answers.
    static let resources: URL? = Bundle.main.resourceURL?
        .appendingPathComponent("IrisMac_IrisMac.bundle")

    static func register() {
        guard let folder = Fonts.resources?.appendingPathComponent("Resources/Fonts"),
              let files = try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
        else { return }
        for url in files where url.pathExtension == "ttf" {
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
        }
    }
}
