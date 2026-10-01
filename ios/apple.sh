# Laedt die Apple-Identitaet aus ../apple.env fuer die Skripte in ios/.
# Wird mit `. ./apple.sh` eingebunden, aus ios/ heraus.
#
# XcodeGen setzt ${IRIS_TEAM} und ${IRIS_BUNDLE} in project.yml aus der
# Umgebung ein - fehlt die Datei, entstuende ein Projekt mit leerem Team und
# leerer Bundle-ID, und der Fehler kaeme erst tief im Signieren. Darum hier
# und mit einem Satz, der sagt, was zu tun ist.
if [ ! -f ../apple.env ]; then
  echo "apple.env fehlt. Vorlage kopieren und die eigenen Werte eintragen:" >&2
  echo "  cp apple.env.beispiel apple.env" >&2
  exit 1
fi
. ../apple.env
for v in IRIS_TEAM IRIS_BUNDLE; do
  eval "wert=\${$v}"
  if [ -z "$wert" ]; then echo "apple.env: $v ist leer." >&2; exit 1; fi
done
if [ "$IRIS_TEAM" = "ABCDE12345" ] || [ "$IRIS_BUNDLE" = "org.beispiel.iris" ]; then
  echo "apple.env enthaelt noch die Beispielwerte - die eigenen eintragen." >&2
  exit 1
fi
export IRIS_TEAM IRIS_BUNDLE IRIS_GERAET
