# iris auf dem HAOS-Pi

Ein eigener Stack neben hestia und mushroomos — eigenes Netz, eigener
Ordner, eigener Name im Tailnet (`iris-pi`). Mit hestia teilt er sich nur
die Hardware.

Warum überhaupt: Der Kurier für große Dateien braucht **zwei** Brücken, und
ein Übergabeziel muss immer erreichbar sein. Der Desktop ist es nicht — er
steht zu Hause und ist meistens aus. Der Pi läuft durch.

## Was hier anders ist als am Mac

Am Mac hängt die Brücke an Terminal-Fenstern, in denen Claude Code schon
läuft. Auf dem Pi gibt es keine Fenster: die Brücke **startet Claude Code
selbst**. Deshalb liegt im Bild beides — Python für die Brücke, Node für
Claude Code — und deshalb braucht der Container eine Anmeldung.

Ohne Anmeldung läuft die Brücke zwar, aber es entsteht keine Sitzung. Im
Übergabeblatt stünde dann „Dort läuft keine Sitzung", und es gäbe nichts,
wohin eine Datei fallen könnte.

## Einmalig einrichten

**Ein** Geheimnis, und du erzeugst es — im Repository steht es nie.

Am Mac, in einem gewöhnlichen Terminal:

    claude setup-token

Der Browser öffnet sich einmal, du bestätigst, und heraus kommt ein
langlebiger Token (`sk-ant-oat…`). Der Container braucht ihn, weil dort
niemand einen Browser bedienen kann.

Auf dem Pi ablegen (der SSH-Name steht in `rechner.env` als `IRIS_PI_HOST`):

    ssh <pi>
    cd /mnt/data/supervisor/share/iris
    cat > .env <<'ENDE'
    CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat...
    ENDE
    chmod 600 .env

Die Brücke horcht auf allen Adressen, nicht nur auf der Tailnet-Adresse:
unter Home Assistant OS schreibt eine DNAT-Regel des Wirts alles an die
Tailnet-Adresse auf die LAN-Adresse um, und ein Socket auf der Tailnet-
Adresse bekäme nie ein Paket. Geschützt ist sie durch ihr Token — die
Begründung steht in `tools/pi-ausrollen.sh`.

**Keinen Tailscale-Key**: Der Pi hängt schon im Tailnet. Ein eigener
Sidecar hätte nur einen zweiten Gerätenamen gebracht und dafür einen Key
verlangt, den jemand erzeugt und irgendwann erneuert.

## Ausrollen

Vom Mac aus, aus dem Projektordner:

    tools/pi-ausrollen.sh --bauen     # beim ersten Mal
    tools/pi-ausrollen.sh             # danach: nur Code und Neustart

Ausgerollt wird aus `main` — das Skript zieht auf dem Pi und kopiert von
dort, nicht vom Mac. Was nicht gepusht ist, geht nicht mit; das Skript sagt
es vorher. Für einen schnellen Versuch ohne Commit: `--vom-mac`.

Das Bauen dauert beim ersten Mal, weil npm Claude Code holt.

## In der App eintragen

Die Brücke würfelt beim ersten Start ihren eigenen Token:

    ssh <pi> 'docker exec iris-bridge cat /arbeit/.config/iris/config.json'

In iris dann einen Rechner hinzufügen mit
`http://<tailnet-adresse-des-pi>:8780/?token=…` (`tailscale ip -4` auf dem Pi).

## Was wo liegt

| Pfad auf dem Pi | Inhalt |
|---|---|
| `…/iris/code/` | die Brücke, bei jedem Ausrollen ersetzt |
| `…/iris/arbeit/` | Sitzungen, Verlauf, Token, Arbeitsordner — bleibt |
| `…/iris/.env` | der Claude-Token und die Tailnet-Adresse, `chmod 600` |

Der Code ist **schreibgeschützt** eingehängt: was der Container ändern
will, gehört nach `/arbeit`, und ein Ausrollen darf nie etwas überschreiben,
das nur dort entstanden ist.

## Portainer

Der Stack läuft über die Docker-CLI, weil der Pi kein `docker compose` hat
und Portainers eigene Compose-Maschine von außen nicht erreichbar ist. Die
`docker-compose.yml` liegt trotzdem daneben: wer den Stack später in
Portainer übernehmen will, hat die Beschreibung schon.

⚠️ Container über Portainer markieren HAOS offiziell als *unsupported* —
das gilt für hestia und mushroomos genauso und ist auf diesem Pi längst
entschieden.
