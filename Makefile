# iris - remote control for Claude Code sessions
PY := python3

.PHONY: run start stop restart status token ingest-token new-token check check-ci check-bewohner scan install-mcp uninstall-mcp install-agent uninstall-agent logs install-hooks uninstall-hooks hooks-status check-hooks check-typing check-feed ios ios-run ios-test ios-device

run:            ## bridge im Vordergrund starten
	$(PY) -m bridge

start:          ## bridge im Hintergrund starten
	@$(PY) -c "import subprocess,sys; subprocess.Popen([sys.executable,'-m','bridge'], \
	  stdout=open('/tmp/iris.log','w'), stderr=subprocess.STDOUT, start_new_session=True)"
	@sleep 2 && cat /tmp/iris.log

stop:           ## alle bridge-Instanzen beenden, Testbrücken (8775-8779) nicht
	@pids=$$(ps -Ao pid,command | grep "[-]m bridge" | grep -v -E -- "--port 87(75|76|77|78|79)" | awk '{print $$1}'); \
	if [ -z "$$pids" ]; then echo "läuft nicht"; else \
	  echo $$pids | xargs kill 2>/dev/null; \
	  for i in 1 2 3 4 5 6 7 8 9 10; do \
	    sleep 0.5; \
	    [ -z "$$(ps -Ao pid,command | grep "[-]m bridge" | grep -v -E -- "--port 87(75|76|77|78|79)" | awk '{print $$1}')" ] && break; \
	  done; \
	  rest=$$(ps -Ao pid,command | grep "[-]m bridge" | grep -v -E -- "--port 87(75|76|77|78|79)" | awk '{print $$1}'); \
	  [ -n "$$rest" ] && echo $$rest | xargs kill -9 2>/dev/null || true; \
	  echo "beendet: $$pids"; fi

restart: stop
	@$(MAKE) --no-print-directory start

status:         ## läuft sie, und wo?
	@ps -Ao pid,command | grep "[-]m bridge" || echo "läuft nicht"

ingest-token:   ## Token für Dienste, die sich melden (schwächer, nur schreiben)
	@$(PY) -c "import sys; sys.path.insert(0,'.'); \
	from bridge import heartbeat, config; c=config.load(); \
	print('IRIS_URL=http://%s:%s' % (c['host'], c['port'])); \
	print('IRIS_TOKEN=%s' % heartbeat.ingest_token())"

token:          ## Zugangs-URL und Token anzeigen
	@$(PY) -m bridge --print-token

new-token:      ## Token neu würfeln (alte Clients fliegen raus)
	@$(PY) -m bridge --new-token

check:          ## Syntax und Selbsttest
	@$(PY) -W error::SyntaxWarning -m compileall -q -f bridge bewohner hooks tools tests clients >/dev/null && echo "python ok"
	@command -v node >/dev/null && node --check web/app.js && node --check web/wheel.js && echo "js ok" || true
	@$(PY) -m tests.feed
	@$(PY) -m tests.routen
	@$(PY) -m tests.smoke
	@$(PY) -m tests.transfer
	@$(PY) -m tests.transfer_http
	@$(PY) -m tests.anhang
	@$(PY) -m tests.aktualisieren
	@$(PY) -m tests.sitzungen
	@$(PY) -m tests.markdown
	@$(PY) -m tests.wachen

scan:           ## Maschine neu einlesen (Projekte, venvs, Dienste)
	@$(PY) -c "import sys; sys.path.insert(0,'.'); \
	from bridge import inventory; print(inventory.scan())"

install-mcp:    ## Inventar als MCP-Server bei Claude Code eintragen
	@$(PY) -m bridge.install_mcp install

uninstall-mcp:
	@$(PY) -m bridge.install_mcp uninstall

install-hooks:  ## Terminal-Sitzungen an iris anbinden (~/.claude/settings.json, mit Sicherung)
	@$(PY) -m bridge.install_hooks install

uninstall-hooks: ## iris-Hooks wieder austragen, andere bleiben
	@$(PY) -m bridge.install_hooks uninstall

hooks-status:
	@$(PY) -m bridge.install_hooks status

check-ci:       ## Was ohne Claude Code geht - das, was GitHub bei jedem Push prueft
	@$(PY) -W error::SyntaxWarning -m compileall -q -f bridge bewohner hooks tools tests clients >/dev/null && echo "python ok"
	@node --check web/app.js && node --check web/wheel.js && echo "js ok"
	@$(PY) -m tests.feed
	@$(PY) -m tests.routen
	@$(PY) -m tests.transfer
	@$(PY) -m tests.transfer_http
	@$(PY) -m tests.anhang
	@$(PY) -m tests.aktualisieren
	@$(PY) -m tests.sitzungen
	@$(PY) -m tests.markdown
	@$(PY) -m tests.wachen
	@cd bewohner && $(PY) -X utf8 pruefen.py

check-bewohner: ## Proben des Bewohners - was ohne ihn geht, laeuft; der Rest sagt, warum nicht
	@cd bewohner && $(PY) -X utf8 pruefen.py

check-typing:   ## Eintippen in echte Terminal-Sitzungen (öffnet kurz Terminal-Fenster, kostet etwas Kontingent)
	python3 tests/tippen.py

check-hooks:    ## Ende-zu-Ende-Test der Terminal-Anbindung (kostet etwas Kontingent)
	@$(PY) -m tests.hooks

check-feed:     ## Nummern im Kartenstrom (kostet nichts, läuft in make check mit)
	@$(PY) -m tests.feed

ios-device:     ## App aufs iPhone aus apple.env spielen (nur dieses Gerät)
	@ios/device.sh

ios-test:       ## UI-Tests im Simulator gegen eine eigene Testbrücke (kostet etwas Kontingent)
	@ios/uitest.sh

ios-run:        ## iOS-App bauen, im Simulator (iPhone 17 Pro Max) starten, Bildschirmfoto
	@ios/run.sh

install-agent:  ## als LaunchAgent einrichten (startet beim Login)
	@$(PY) -m bridge.launchd install

uninstall-agent:
	@$(PY) -m bridge.launchd uninstall

logs:
	@tail -f ~/Library/Logs/iris.log
