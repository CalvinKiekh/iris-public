#!/bin/sh
# UI-Tests im Simulator, gegen eine eigene Testbrücke auf Port 8776.
#
# Die Testbrücke schickt keinen Push, hat ihren eigenen Zustand und einen
# Wegwerf-Ordner auf dem Mac, in dem die Sitzungen der Tests laufen. Mit der
# Brücke, die du benutzt, kommt sie nicht in Berührung.
set -e
cd "$(dirname "$0")"
. ./apple.sh
HERE=$(pwd)
ROOT=$(dirname "$HERE")
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
DEVICE="${IRIS_SIM:-iPhone 17 Pro Max}"
SIM=$(xcrun simctl list devices available | grep "$DEVICE (" | head -1 \
      | sed -E 's/.*\(([0-9A-F-]{36})\).*/\1/')
PORT=8776
WORK=$(mktemp -d -t iris-uitest)
STATE=$(mktemp -d -t iris-uitest-state)

(cd "$ROOT" && exec env IRIS_NO_PUSH=1 IRIS_AWAY_PATH="$STATE/away.json" \
   IRIS_TERMINALS_PATH="$STATE/terminals.json" \
   python3 -m bridge --host 127.0.0.1 --port $PORT > "$STATE/bridge.log" 2>&1) &
BRIDGE=$!
# The app talks to the bridge through a switch the tests can turn off
# (tools/offline_proxy.py): that is how a dropped connection is tested.
python3 "$HERE/tools/offline_proxy.py" 8774 $PORT 8773 > "$STATE/proxy.log" 2>&1 &
PROXY=$!
cleanup() {
  kill $BRIDGE $PROXY 2>/dev/null || true
  cp "$STATE/proxy.log" "$HERE/build/proxy.log" 2>/dev/null || true
  rm -rf "$WORK" "$STATE"
  # The test sessions leave transcripts under ~/.claude/projects.
  find "$HOME/.claude/projects" -maxdepth 1 -name "*iris-uitest*" -exec rm -rf {} + 2>/dev/null || true
}
trap cleanup EXIT
sleep 2

TOKEN=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.config/iris/config.json')))['token'])")
xattr -cr Iris IrisUITests
xcodegen generate --quiet
rm -rf "$HERE/build/uitest.xcresult"
mkdir -p "$HERE/build"
TEST_RUNNER_IRIS_URL="http://127.0.0.1:8774/?token=$TOKEN" \
TEST_RUNNER_IRIS_CONTROL="http://127.0.0.1:8773/__offline" \
TEST_RUNNER_IRIS_WORKDIR="$WORK" \
xcodebuild test -project Iris.xcodeproj -scheme Iris \
  -destination "platform=iOS Simulator,id=$SIM" \
  -derivedDataPath "$HOME/Library/Developer/Xcode/DerivedData/iris" \
  -resultBundlePath "$HERE/build/uitest.xcresult" \
  CODE_SIGN_STYLE=Manual CODE_SIGN_IDENTITY=- PROVISIONING_PROFILE_SPECIFIER= "$@" \
  2>&1 | tee "$HERE/build/uitest.log" \
  | grep -E "Test Case .*(passed|failed)|error:|\*\* TEST|XCTAssert|Fehlt|fehlt|erscheint nicht|kam nicht" || true
