// swift-tools-version: 6.0
// iris on the Mac: built like WindowSnap - SPM and a Makefile, no Xcode
// project. The code it shares with the iPhone app lives in ../shared and is
// linked into the sources (Sources/IrisMac/Shared), so a fix lands in both.
import PackageDescription

let package = Package(
    name: "IrisMac",
    platforms: [.macOS(.v15)],
    targets: [
        .executableTarget(
            name: "IrisMac",
            path: "Sources/IrisMac",
            // Fonts and the ink/grain textures - what the phone keeps in its
            // asset catalog.
            resources: [.copy("Resources")]
        )
    ]
)
