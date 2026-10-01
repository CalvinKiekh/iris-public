#!/bin/sh
# Baut die App fürs iPhone und spielt sie auf - nur auf das Gerät aus
# apple.env (IRIS_GERAET), nie auf ein anderes im Konto. Starten klappt nur bei entsperrtem
# Telefon (sonst devicectl-Fehler 10002); dafür kommt nach jeder Installation
# eine Mitteilung aufs Handy, dass die neue Version drauf ist.
set -e
cd "$(dirname "$0")"
. ./apple.sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
DEVICE="$IRIS_GERAET"                            # nur dieses Gerät
if [ -z "$DEVICE" ] || [ "$DEVICE" = "00000000-0000-0000-0000-000000000000" ]; then
  echo "apple.env: IRIS_GERAET fehlt - die Kennung zeigt 'xcrun devicectl list devices'." >&2
  exit 1
fi
# Outside ~/Documents: iCloud's xattrs make codesign fail there.
DERIVED="$HOME/Library/Developer/Xcode/DerivedData/iris-device"
LOG="$(pwd)/build/device.log"
mkdir -p build
xattr -cr Iris
xcodegen generate --quiet
code=0
set -- $(../tools/version.sh)
VERSION=$1 BUILD=$2
xcodebuild -project Iris.xcodeproj -scheme Iris -configuration Debug \
  -destination 'generic/platform=iOS' -derivedDataPath "$DERIVED" \
  MARKETING_VERSION="$VERSION" CURRENT_PROJECT_VERSION="$BUILD" \
  -allowProvisioningUpdates -quiet build > "$LOG" 2>&1 || code=$?
grep -E "^/[^ ]+\.swift:[0-9]+:[0-9]+: (error|warning):" "$LOG" | sed 's|.*/ios/Iris/||' | sort -u | head
echo "Bau: Exit $code"
[ $code -eq 0 ] || exit 1
out=$(xcrun devicectl device install app --device $DEVICE "$DERIVED/Build/Products/Debug-iphoneos/Iris.app" 2>&1 || true)
echo "$out" | grep -E "App installed|error" | head -2
echo "$out" | grep -q "App installed" || exit 1
xcrun devicectl device process launch --device $DEVICE --terminate-existing "$IRIS_BUNDLE" 2>&1 \
  | grep -E "Launched|error|locked" | head -2 || true
# Installing works with the phone locked, starting the app does not: a push
# says the new version is on, so the next open picks it up.
echo "Version $VERSION ($BUILD)"
python3 ../tools/notify.py "iris $VERSION ist drauf" "App einmal ganz schließen und neu öffnen." \
  || echo "Mitteilung ging nicht raus"
