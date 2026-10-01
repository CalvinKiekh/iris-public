# Laedt rechner.env aus der Wurzel des Projekts, wenn es sie gibt.
# Einbinden mit `. tools/rechner.sh`, aus der Wurzel heraus.
#
# Eine Umgebungsvariable, die schon gesetzt ist, gewinnt - so laesst sich
# ein Ziel fuer einen Aufruf umbiegen, ohne die Datei anzufassen.
if [ -f rechner.env ]; then
  _vorher=$(env | grep '^IRIS_' || true)
  . ./rechner.env
  # Was vorher schon in der Umgebung stand, wieder durchsetzen.
  [ -n "$_vorher" ] && eval "$(printf '%s\n' "$_vorher" | sed "s/^\([^=]*\)=\(.*\)$/\1='\2'/")"
fi

# brauche NAME "was tun"  -  bricht mit einem Satz ab, wenn NAME leer ist.
brauche() {
  eval "_w=\${$1}"
  if [ -z "$_w" ]; then
    echo "$1 fehlt. In rechner.env eintragen (Vorlage: rechner.env.beispiel) - $2" >&2
    exit 1
  fi
}
