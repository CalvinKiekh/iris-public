# iris einrichten

Für jemanden, der iris zum ersten Mal auf einem eigenen Rechner aufsetzt.
Von null bis zu dem Punkt, an dem du vom Handy aus eine Claude-Code-Sitzung
auf deinem Rechner bedienst.

Es gibt drei Stufen, und jede ist für sich brauchbar:

1. **Die Brücke und die Weboberfläche** — ein Rechner, jeder Browser,
   kein Apple-Konto nötig.
2. **Die eigenen Apps** für iPhone, Watch und Mac — nur mit
   Apple-Entwicklerkonto.
3. **Weitere Rechner** — ein Raspberry Pi, der immer läuft, ein Windows-PC,
   ein Assistent, der sie alle sieht.

Alles Persönliche steht in drei Dateien, keine davon im Git. Am Ende dieser
Anleitung steht, welche das sind.

---

## Stufe 1 — Brücke und Weboberfläche

### Was du brauchst

- **Python 3.10 oder neuer.**
- **Claude Code**, installiert und angemeldet: einmal `claude` im Terminal
  starten und dem Anmelden folgen. Die Brücke steuert Claude Code nur — sie
  bringt kein eigenes mit.
- **Tailscale** auf dem Rechner und auf dem Handy, beide im selben Tailnet.
  Darüber erreichst du den Rechner von überall, ohne eine Portfreigabe im
  Router.

### Holen und starten

```bash
git clone <adresse-des-repos> iris && cd iris
python3 -m pip install -r requirements.txt
make run
```

Beim ersten Start legt die Brücke `~/.config/iris/config.json` an und füllt
drei Dinge selbst aus:

- **`token`** — der Schlüssel zu deiner Brücke. Wer ihn hat, kann auf diesem
  Rechner Claude-Code-Sitzungen starten und damit Befehle ausführen. Behandle
  ihn wie ein Passwort.
- **`host`** — die Tailnet-Adresse des Rechners. Darauf horcht die Brücke,
  nicht auf dem lokalen Netz.
- **`nutzer.name`** — dein Vorname, geraten aus deinem Benutzerkonto.

**Prüf den Namen.** Er ist nicht Dekoration: er steht in den Anweisungen,
die einem Modell sagen, für wen es arbeitet („nur Anna entscheidet"). Aus
einem Konto namens `anna.m` oder `iris` wird kein richtiger Name. Öffne
`~/.config/iris/config.json` und trag ihn ein:

```json
"nutzer": {"name": "Anna"}
```

Dann die Brücke neu starten (`Ctrl+C`, `make run`).

### Prüfen, ob alles läuft

```bash
make check
```

Das ist kein reiner Selbsttest, sondern eine Probe an einer **eingerichteten**
Maschine: er startet echte Claude-Sitzungen, liest deine Projekte ein und
fragt nach deinen GitHub-Konten. Direkt nach dem Einrichten schlagen deshalb
bis zu acht Prüfungen fehl, ohne dass etwas kaputt ist — solange Claude Code
nicht angemeldet ist (Sitzung, Freigabe, Werkzeugaufrufe, geänderte Datei),
solange unter deinem Benutzerordner keine Projekte liegen (Inventar, Suche,
Dienste) und ohne `gh auth login` (GitHub-Konten). Sind die drei Dinge da,
muss alles grün sein.

### Aufs Handy

```bash
make token
```

zeigt:

```
Token: …
URL:   http://100.x.y.z:8780/?token=…
```

Die **URL** auf dem Handy öffnen und über „Teilen → Zum Home-Bildschirm"
ablegen. Dann läuft iris dort wie eine App.

### Sitzungen aus dem Terminal sichtbar machen

Bis hierher siehst du nur Sitzungen, die du *über iris* startest. Damit auch
die erscheinen, die du am Rechner selbst im Terminal öffnest:

```bash
make install-hooks
```

Das trägt iris in `~/.claude/settings.json` ein (mit Sicherung der alten
Datei). Es gilt für jede Claude-Code-Sitzung auf diesem Rechner, auch für
bereits laufende.

### Beim Anmelden mitstarten

- **Mac:** `make install-agent` — ein LaunchAgent startet die Brücke bei der
  Anmeldung und nach einem Absturz neu.
- **Linux:** ein systemd-Nutzerdienst mit `python3 -m bridge` im
  Projektordner.
- **Windows:** eine geplante Aufgabe „bei Anmeldung", die
  `python run_bridge.py` startet. `tools/pc-ausrollen.sh` erwartet sie unter
  dem Namen `iris Bruecke`.

Die Brücke wartet beim Start bis zu drei Minuten auf ihre Tailnet-Adresse.
Das ist Absicht: nach einem Neustart meldet sich die Aufgabe oft, bevor
Tailscale verbunden ist.

---

## Stufe 2 — Die eigenen Apps

Nur nötig, wenn du die native iPhone-, Watch- oder Mac-App willst und
Push-Nachrichten. Du brauchst ein **Apple-Entwicklerkonto**, Xcode und
[XcodeGen](https://github.com/yonaskolb/XcodeGen) (`brew install xcodegen`).

### Deine Apple-Identität

```bash
cp apple.env.beispiel apple.env
```

und darin eintragen:

| Zeile | Was | Woher |
|---|---|---|
| `IRIS_TEAM` | deine Team-ID, zehn Zeichen | developer.apple.com → Membership |
| `IRIS_BUNDLE` | eine Bundle-ID, die dir gehört | frei wählbar, z. B. `de.anna.iris` |
| `IRIS_GERAET` | dein iPhone | `xcrun devicectl list devices` |

**Die Bundle-ID nicht mehr ändern, sobald etwas installiert ist.** Sie ist
zugleich der Name, unter dem die Apps ihre Token im Schlüsselbund ablegen,
und das launchd-Label der Brücke. Eine neue lässt gespeicherte Token
verschwinden und legt einen zweiten Agenten an, der mit dem ersten um den
Port streitet.

### Bauen

```bash
make ios-device          # iPhone, per Kabel oder im selben WLAN
cd mac && make install   # Mac-App nach /Applications
```

`make ios-device` baut die Watch-App mit und spielt nur auf das Gerät aus
`apple.env` — nie auf ein anderes in deinem Konto.

### In der App einen Rechner eintragen

Die Apps kennen keine Brücke von selbst. In der App einen Rechner hinzufügen
mit der Adresse aus `make token` (`http://100.x.y.z:8780`) und dem Token.
Das ist bewusst pro Gerät: die Brücken wissen nichts voneinander, das
Vertrauen liegt beim Klienten.

### Push-Nachrichten

Dafür braucht die Brücke den APNs-Schlüssel deines Teams — eine `.p8`-Datei
aus developer.apple.com → Keys. Sie gehört **nie** ins Repo. Ablegen, zum
Beispiel unter `~/.config/iris/`, und in `config.json` eintragen:

```json
"push": {
  "key_path": "~/.config/iris/AuthKey_ABC123.p8",
  "key_id":   "ABC123",
  "team_id":  "ABCDE12345",
  "topic":    "de.anna.iris"
}
```

`topic` ist deine Bundle-ID. Für schnellere Zustellung
`python3 -m pip install "httpx[http2]"`; ohne das nimmt die Brücke curl und
openssl.

---

## Stufe 3 — Weitere Rechner

Jeder Rechner bekommt seine eigene Brücke mit eigenem Token und wird in der
App einzeln eingetragen. Die Skripte in `tools/` rollen auf deine Rechner
aus; wohin, steht in einer Datei:

```bash
cp rechner.env.beispiel rechner.env
```

Nur die Abschnitte ausfüllen, deren Rechner du hast. Ein Skript, dem ein
Ziel fehlt, sagt, welche Zeile es braucht.

### Ein Raspberry Pi, der immer läuft

Gebaut für einen Pi mit Home Assistant OS, als eigener Container.
Einzelheiten und die zwei Eigenheiten dieses Systems stehen in
`pi/README.md`. Kurz:

```bash
tools/pi-ausrollen.sh --bauen     # beim ersten Mal
tools/pi-ausrollen.sh             # danach
```

Ausgerollt wird aus `main`: das Skript zieht auf dem Pi und kopiert von
dort. Was du nicht gepusht hast, geht nicht mit — das Skript sagt es vorher.

**Trag auf dem Pi den Namen von Hand ein**, bevor die Brücke dort das erste
Mal startet. Der Container läuft unter einem Konto namens `iris`, und genau
das würde sonst als dein Name in der Konfiguration landen.

### Ein Windows-PC

Braucht den OpenSSH-Server von Windows. Dann:

```bash
tools/pc-ausrollen.sh
```

Kopiert Brücke und Oberfläche, startet die geplante Aufgabe neu und prüft
danach, ob die Oberfläche wirklich antwortet.

### Der Assistent

Eine Claude-Sitzung mit der Rolle `vorarbeiter`, die andere Sitzungen auf
allen deinen Rechnern sieht, beauftragt und beaufsichtigt. Sinnvoll auf dem
Rechner, der immer läuft. Welche Rechner er erreicht, legst du fest — er
kann die Liste nicht selbst erweitern. Sie steht auf *seinem* Rechner in
`~/.config/iris/maschinen.json`:

```json
[{"name": "mac", "base": "http://100.x.y.z:8780", "token": "…"}]
```

Nur der Assistent bekommt die Werkzeuge, mit denen man fremde Sitzungen
steuert. Eine gewöhnliche Sitzung hat sie nicht.

**Einen Rechner, der dich nicht steuern soll** — etwa einen Firmenrechner —
richtest du ohne `maschinen.json` ein und legst dort keine fremden Token und
keinen privaten SSH- oder GitHub-Schlüssel ab. Dann kannst du ihn bedienen,
er kommt aber an nichts von dir.

### Der Bewohner

Ein dauerhaft laufender Begleiter auf einem Windows-PC mit Grafikkarte, mit
eigenem Gedächtnis und lokalem Sprachmodell (gpt-oss über Ollama).
Experimentell und aufwendig einzurichten; die Schnittstelle beschreibt
`docs/BEWOHNER.md`, was er braucht und was er selbst anlegt
`bewohner/GEDAECHTNIS.md`. Er beginnt mit leerem Gedächtnis — das eines
anderen Menschen gehört nie dazu. Er liest seinen Namen für dich aus derselben
`config.json` und, optional, den Ort seiner Sprachausgabe:

```json
"bewohner": {"tts": "C:\\Users\\anna\\tts-test"}
```

---

## Wo das Persönliche steht

Nichts davon ist im Git. Wer iris von dir bekommt, legt diese drei Dateien
selbst an.

| Datei | Was | Vorlage |
|---|---|---|
| `~/.config/iris/config.json` | Token, Adresse, dein Name, Push | entsteht beim ersten Start |
| `apple.env` | Team, Bundle-ID, iPhone | `apple.env.beispiel` |
| `rechner.env` | deine weiteren Rechner | `rechner.env.beispiel` |

Dazu, falls benutzt: `~/.config/iris/maschinen.json` für den Assistenten,
der APNs-Schlüssel, und `.env` mit dem Claude-Token auf dem Pi.

---

## Fallen, die schon Zeit gekostet haben

- **„iris geht nicht mehr" liegt meist an Tailscale auf dem Handy**, nicht
  an der Brücke. Erst vom Rechner aus prüfen, ob sie antwortet
  (`curl http://100.x.y.z:8780/`); tut sie das, Tailscale auf dem Handy
  einmal aus- und einschalten.
- **Ein Dienst auf einer Tailnet-Adresse, der jede Verbindung abweist**,
  obwohl er laut `netstat` horcht: der Wirt schreibt Pakete an diese Adresse
  um. Unter Home Assistant OS so; dort `0.0.0.0` binden.
- **`ssh` findet seine Konfiguration nicht, obwohl sie unter `$HOME/.ssh`
  liegt:** OpenSSH liest `~` aus der passwd-Datei, nicht aus `$HOME`.
- **Ein GitHub-Repo „existiert nicht"**, obwohl es da ist: mit dem falschen
  Konto angemeldet. Ein Konto sieht die privaten Repos eines anderen nicht,
  und GitHub antwortet dann mit „not found", nicht mit „kein Zugriff".
- **Eine Schleife in zsh, die für jede Adresse 000 meldet:** zsh zerlegt
  `$variable` nicht in Wörter. Das sieht aus wie ein Totalausfall und ist ein
  Fehler im Test.
