// swift-tools-version: 6.0
import PackageDescription

// Zeichnet die Bewegung des Assistenten Bild fuer Bild - ohne Simulator,
// ohne Zeit, ohne Zufall. `grad` ist eine Zahl, also ist jede Stufe
// wiederholbar und einzeln zu betrachten.
let package = Package(
    name: "orbfilm",
    platforms: [.macOS(.v14)],
    targets: [.executableTarget(name: "orbfilm", path: "Sources/orbfilm")]
)
