#!/bin/sh
# Baut die App, startet sie im Simulator gegen die laufende Brücke und legt
# ein Bildschirmfoto nach ios/build/<name>.png.
#
#   ios/run.sh                  Übersicht
#   IRIS_OPEN=last ios/run.sh   gleich die zuletzt aktive Sitzung
#   IRIS_SHOT=verlauf ios/run.sh  Name des Bildschirmfotos
#
# Das Gerät ist ein iPhone 17 Pro Max, weil das das Telefon ist, auf dem iris
# benutzt wird - geprüft wird an der Größe, die zählt.
set -e
cd "$(dirname "$0")"
. ./apple.sh
HERE=$(pwd)
# The build lives outside ~/Documents: iCloud tags files there with extended
# attributes, and codesign refuses a bundle that carries them.
DERIVED="$HOME/Library/Developer/Xcode/DerivedData/iris"
mkdir -p "$HERE/build"
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
DEVICE="${IRIS_SIM:-iPhone 17 Pro Max}"
SIM=$(xcrun simctl list devices available | grep "$DEVICE (" | head -1 \
      | sed -E 's/.*\(([0-9A-F-]{36})\).*/\1/')
[ -n "$SIM" ] || { echo "Simulator '$DEVICE' fehlt"; exit 1; }

xcodegen generate --quiet
xcodebuild -project Iris.xcodeproj -scheme Iris -configuration Debug \
  -destination "platform=iOS Simulator,id=$SIM" -derivedDataPath "$DERIVED" \
  CODE_SIGN_STYLE=Manual CODE_SIGN_IDENTITY=- PROVISIONING_PROFILE_SPECIFIER= \
  -quiet build
# Signed "to run locally" rather than not at all: only a signed app carries
# its entitlements, and without aps-environment there is no push token.

xcrun simctl boot "$SIM" 2>/dev/null || true
open -a Simulator --args -CurrentDeviceUDID "$SIM"
xcrun simctl bootstatus "$SIM" -b >/dev/null
xcrun simctl install "$SIM" "$DERIVED/Build/Products/Debug-iphonesimulator/Iris.app"

CFG="$HOME/.config/iris/config.json"
TOKEN=$(python3 -c "import json;print(json.load(open('$CFG'))['token'])")
PORT=$(python3 -c "import json;print(json.load(open('$CFG')).get('port',8780))")
# The simulator shares the Mac's network, so loopback reaches the bridge.
SIMCTL_CHILD_IRIS_URL="http://127.0.0.1:$PORT/?token=$TOKEN" \
SIMCTL_CHILD_IRIS_OPEN="${IRIS_OPEN:-}" \
  xcrun simctl launch --terminate-running-process "$SIM" "$IRIS_BUNDLE" >/dev/null
sleep "${IRIS_SHOT_DELAY:-5}"
# simctl resolves relative paths against its own service, not this shell.
xcrun simctl io "$SIM" screenshot "$HERE/build/${IRIS_SHOT:-screen}.png" >/dev/null
echo "$HERE/build/${IRIS_SHOT:-screen}.png"
