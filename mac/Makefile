# iris on the Mac - built like WindowSnap: SPM, a Makefile, no Xcode project.
APP_NAME = iris
EXECUTABLE = IrisMac
# Die Apple-Identitaet steht in ../apple.env, nicht hier - dieselbe Datei,
# aus der die iOS-App gebaut wird. Das Format ist zugleich Shell und Make.
-include ../apple.env
ifeq ($(strip $(IRIS_BUNDLE)),)
$(error apple.env fehlt oder IRIS_BUNDLE ist leer - cp apple.env.beispiel apple.env)
endif
BUNDLE_ID = $(IRIS_BUNDLE).mac
# Bundle-ID und Schluesselbund-Name werden beim Bauen gesetzt, nicht in der
# Info.plist gepflegt. Der Schluesselbund heisst wie auf dem Telefon, nicht
# wie diese App: sonst verschwinden gespeicherte Token beim Umbenennen.
PLIST_IDENTITAET = /usr/libexec/PlistBuddy \
  -c "Set :CFBundleIdentifier $(BUNDLE_ID)" \
  -c "Set :IrisSchluesselbund $(IRIS_BUNDLE)"
BUILD_DIR = .build/release
# /Applications, where programs are looked for. ~/Applications was
# a place nobody thinks to open.
APP_BUNDLE = /Applications/$(APP_NAME).app
CONTENTS = $(APP_BUNDLE)/Contents

# Ad-hoc (`-`) gives every build a different identity, and the keychain then
# asks for the login password again on every install, because from its side a
# stranger wants the bridge tokens of the app before it. A certificate that
# stays the same makes it ask once. Falls back to ad-hoc where there is none.
SIGN_ID := $(shell security find-identity -v -p codesigning 2>/dev/null | \
             sed -n 's/.*"\(Apple Development: .*\)"/\1/p' | head -1)
SIGN = $(if $(SIGN_ID),$(SIGN_ID),-)

.PHONY: build install run dev clean reset-permission sign-info

build:
	swift build -c release

# The resource bundle (fonts, textures) goes to Contents/Resources, where the
# generated Bundle.module looks for it.
RUNNING = .build/.lief

install: build
	@pgrep -x $(EXECUTABLE) >/dev/null && touch $(RUNNING) || rm -f $(RUNNING)
	@pkill -x $(EXECUTABLE) 2>/dev/null || true
	@mkdir -p $(CONTENTS)/MacOS $(CONTENTS)/Resources
	@cp $(BUILD_DIR)/$(EXECUTABLE) $(CONTENTS)/MacOS/$(EXECUTABLE)
	@rm -rf $(CONTENTS)/Resources/IrisMac_IrisMac.bundle
	@cp -R $(BUILD_DIR)/IrisMac_IrisMac.bundle $(CONTENTS)/Resources/
	@cp Sources/IrisMac/Resources/iris.icns $(CONTENTS)/Resources/iris.icns
	@cp Info.plist $(CONTENTS)/Info.plist
	@$(PLIST_IDENTITAET) $(CONTENTS)/Info.plist
	@set -- $$(../tools/version.sh); \
	  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $$1" -c "Set :CFBundleVersion $$2" $(CONTENTS)/Info.plist; \
	  echo "Version $$1 ($$2)"
	@codesign --force --deep --sign "$(SIGN)" $(APP_BUNDLE)
	@$(MAKE) --no-print-directory sign-info
	@echo "Installed to $(APP_BUNDLE)"
	@# Was lief, läuft weiter: installieren beendet die App, und sie liegen
	@# zu lassen hat sie schon zweimal stillschweigend ausgeschaltet.
	@test -f $(RUNNING) && (open $(APP_BUNDLE); rm -f $(RUNNING); echo "Neu gestartet") || true

run: install
	@open $(APP_BUNDLE)

sign-info:
ifeq ($(SIGN_ID),)
	@echo "Signiert: ad hoc - Schluesselbund und Mikrofon fragen nach jedem Build erneut"
	@$(MAKE) --no-print-directory reset-permission
else
	@echo "Signiert: $(SIGN_ID)"
endif

# Only for ad-hoc builds: every one of them is a new program to macOS, so the
# old permission entry is stale. Clearing it makes macOS ask again instead of
# failing silently. With a stable certificate the entry keeps working - then
# resetting it would be the thing that makes it ask.
reset-permission:
	@tccutil reset Microphone $(BUNDLE_ID) >/dev/null 2>&1 || true
	@tccutil reset SpeechRecognition $(BUNDLE_ID) >/dev/null 2>&1 || true

# Fast loop while working on the window: the debug build in the same bundle.
dev:
	swift build
	@pkill -x $(EXECUTABLE) 2>/dev/null || true
	@mkdir -p $(CONTENTS)/MacOS $(CONTENTS)/Resources
	@cp .build/debug/$(EXECUTABLE) $(CONTENTS)/MacOS/$(EXECUTABLE)
	@rm -rf $(CONTENTS)/Resources/IrisMac_IrisMac.bundle
	@cp -R .build/debug/IrisMac_IrisMac.bundle $(CONTENTS)/Resources/
	@cp Sources/IrisMac/Resources/iris.icns $(CONTENTS)/Resources/iris.icns
	@cp Info.plist $(CONTENTS)/Info.plist
	@$(PLIST_IDENTITAET) $(CONTENTS)/Info.plist
	@set -- $$(../tools/version.sh); \
	  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $$1" -c "Set :CFBundleVersion $$2" $(CONTENTS)/Info.plist; \
	  echo "Version $$1 ($$2)"
	@codesign --force --deep --sign "$(SIGN)" $(APP_BUNDLE)
	@open $(APP_BUNDLE)

clean:
	swift package clean
	@rm -rf $(APP_BUNDLE)
