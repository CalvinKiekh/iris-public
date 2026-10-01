"""Was auf diesem Rechner ist - jenseits der Dateien, die er einzeln ansieht.

    python rechner.py            zeigen, was daraus wuerde (nichts merken)
    python rechner.py --merken   die Saetze ins Gedaechtnis legen
    python rechner_test.py       die Probe

WARUM ES DIESE DATEI GIBT. Sein Zuhause bestand aus zwei Ordnern. Am 13.09.
lagen zehn `zuhause`-Saetze im Gedaechtnis, und alle zehn handelten von
Downloads und Desktop: `wahrnehmung.MITLESEN` sieht nur dorthin, und
`bestand.py` schaut zusammen, was die Wahrnehmung gesehen hat. Auf die Frage,
welche Dienste laufen oder was installiert ist, hatte er nichts - nicht weil
er es vergessen haette, sondern weil es nie jemand aufgeschrieben hat.

ZWEI EBENEN, und die Grenze ist eine Zahl. `Dokumente` enthaelt auf diesem
Rechner 455.299 Dateien. Jede einzeln anzusehen, wie es die Wahrnehmung mit
Desktop und Downloads tut, waere ein Modellaufruf je Datei - das ist nicht
langsam, das ist unmoeglich. Also:

    beschrieben   wo es wenige sind (Desktop, Downloads) - wahrnehmung.py
    GEZAEHLT      wo es viele sind (der ganze Rechner) - diese Datei

DIE SAETZE ENTSTEHEN OHNE MODELL. Eine Volkszaehlung besteht aus Zahlen, und
`wissen.mangel()` weist jede Zahl zurueck, die nicht im Wortlaut steht - zu
Recht. Ein Modell, das aus "1534 GB frei" einen Satz baut, kann sich
verzaehlen; hier kann es das nicht, weil es nicht gefragt wird. Das ist auch
der Grund, warum diese Saetze pruefbar sind: Zu jedem gehoert die Messung,
aus der er stammt.

NUR LESEN. Kein Dienst wird angefasst, kein Programm gestartet, nichts
geaendert. Dieselbe Zusage wie in haus.py.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import haus

HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"
ZUSTAND = WERKSTATT / "rechner.json"

# Wie oft. Eine Volkszaehlung aendert sich nicht im Minutentakt: Programme
# werden nicht stuendlich installiert, und der Lauf kostet mehrere Sekunden
# PowerShell. Sechs Stunden heisst: viermal am Tag, und jede Aenderung ist
# spaetestens am naechsten Tageslauf im Gedaechtnis.
STUNDEN = 6.0

# Wie viele Namen ein Satz nennt. Mehr liest niemand, und eine Aufzaehlung von
# dreissig Diensten ist keine Auskunft - sie ist eine Liste. Dieselbe
# Ueberlegung wie bei `bestand`, wo achtzehn Erkenntnisse je Nacht absichtlich
# unter `fund` gewichtet sind.
NAMEN_MAX = 6

# Die Ordner im Benutzerprofil, die eine Auskunft wert sind. `AppData` steht
# nicht dabei: Dort liegt nichts, was Calvin je gesucht hat, und es sind
# Hunderttausende Dateien.
PROFIL_ORDNER = ("Desktop", "Downloads", "Documents", "Pictures", "Videos",
                 "Music")

_ZAEHLEN = r"""
$profil = $env:USERPROFILE
$ordner = @()
foreach ($name in @(%(ordner)s)) {
  $pfad = Join-Path $profil $name
  if (-not (Test-Path $pfad)) { continue }
  $direkt = @(Get-ChildItem -LiteralPath $pfad -File -ErrorAction SilentlyContinue)
  $unter  = @(Get-ChildItem -LiteralPath $pfad -Directory -ErrorAction SilentlyContinue)
  $ordner += [pscustomobject]@{
    name    = $name
    dateien = $direkt.Count
    ordner  = $unter.Count
    groesste = @($unter | Select-Object -First 6 | ForEach-Object { $_.Name })
  }
}

# Installierte Programme: die Deinstallationseintraege der Registrierung. Das
# ist dieselbe Liste, die Windows unter "Apps" zeigt.
$schluessel = @(
  'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*')
$roh = @(Get-ItemProperty $schluessel -ErrorAction SilentlyContinue |
         Where-Object { $_.DisplayName -and -not $_.SystemComponent -and -not $_.ParentKeyName })
$programme = @($roh | Select-Object -ExpandProperty DisplayName -Unique | Sort-Object)

$dienste = Get-CimInstance Win32_Service
$laufen  = @($dienste | Where-Object { $_.State -eq 'Running' })
$autostart = @(Get-CimInstance Win32_StartupCommand |
               Select-Object -ExpandProperty Caption -Unique)

$platten = @(Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -eq 3 } |
  ForEach-Object {
    [pscustomobject]@{
      name = $_.DeviceID
      frei_gb = [math]::Round($_.FreeSpace/1GB)
      gross_gb = [math]::Round($_.Size/1GB)
    }
  })

[pscustomobject]@{
  ordner    = $ordner
  programme = [pscustomobject]@{ anzahl = $programme.Count; namen = @($programme | Select-Object -First 40) }
  dienste   = [pscustomobject]@{
    insgesamt = @($dienste).Count
    laufen    = $laufen.Count
    namen     = @($laufen | Select-Object -ExpandProperty DisplayName -First 40)
  }
  autostart = [pscustomobject]@{ anzahl = $autostart.Count; namen = @($autostart | Select-Object -First 20) }
  platten   = $platten
} | ConvertTo-Json -Depth 5 -Compress
"""


def _befehl() -> str:
    """Der PowerShell-Block, mit der Ordnerliste aus PROFIL_ORDNER.

    Eine Quelle fuer die Liste: Stuende sie zweimal da, wuerde eines Tages die
    eine geaendert und die andere nicht - und der Satz ueber einen Ordner
    bliebe fuer immer stehen, weil ihn nie wieder etwas ersetzt.
    """
    liste = ",".join("'%s'" % o for o in PROFIL_ORDNER)
    return _ZAEHLEN % {"ordner": liste}


def messen(lauf=None) -> dict | None:
    """Die Volkszaehlung. `lauf` nur, damit die Probe nicht PowerShell braucht."""
    if lauf is not None:
        return lauf()
    return haus._ps_json(_befehl(), frist=120)


def _namen(liste, wie_viele: int = NAMEN_MAX) -> str:
    """Eine Auswahl QUER durch die Liste, nicht ihr Anfang.

    Die Listen kommen sortiert. Die ersten sechs von 121 Programmen waren
    darum "AMD Application Compatibility Database File, AMD Chipset Software,
    AMD Install Manager, AMD Ryzen Master, AMD Software, AnyDesk" - das sagt
    ueber den Rechner nichts, ausser dass sein Hersteller mit A anfaengt. Quer
    durch die Liste gegriffen steht Steam neben dem Treiber, und man sieht,
    wofuer die Maschine benutzt wird.
    """
    namen = [str(x).strip() for x in (liste or []) if str(x).strip()]
    if len(namen) <= wie_viele:
        return ", ".join(namen)
    # Erster UND letzter gehoeren dazu: Ein Griff, der bei 0 anfaengt und mit
    # fester Schrittweite geht, erreicht das Ende der Liste nie - und dann
    # stehen wieder sechs Namen aus derselben Ecke da.
    letzte = len(namen) - 1
    plaetze = sorted({round(i * letzte / (wie_viele - 1))
                      for i in range(wie_viele)})
    return ", ".join(namen[i] for i in plaetze)


def saetze(mess: dict) -> list[dict]:
    """Aus der Messung ein paar Saetze - je Gruppe einer, mit seinem Beleg.

    Der Schluessel ist die Gruppe: Beim naechsten Lauf ersetzt der neue Satz
    den alten derselben Gruppe, statt neben ihn zu treten. Dieselbe Regel wie
    in bestand.py, und sie steht dort aus einem gemessenen Grund: Nach einer
    Woche lagen sieben Saetze ueber denselben Desktop im Gedaechtnis.
    """
    if not isinstance(mess, dict):
        return []
    heraus: list[dict] = []

    platten = mess.get("platten") or []
    if isinstance(platten, dict):
        platten = [platten]
    teile = ["Laufwerk %s hat %d von %d GB frei"
             % (p.get("name"), p.get("frei_gb") or 0, p.get("gross_gb") or 0)
             for p in platten if isinstance(p, dict) and p.get("name")]
    if teile:
        heraus.append({"schluessel": "rechner:platten",
                       "satz": "%s." % "; ".join(teile),
                       "beleg": "Win32_LogicalDisk"})

    p = mess.get("programme") or {}
    if p.get("anzahl"):
        heraus.append({
            "schluessel": "rechner:programme",
            "satz": "Auf dem Rechner sind %d Programme installiert, darunter %s."
                    % (p["anzahl"], _namen(p.get("namen"))),
            "beleg": "Registrierung, Deinstallationseintraege"})

    d = mess.get("dienste") or {}
    if d.get("insgesamt"):
        heraus.append({
            "schluessel": "rechner:dienste",
            # "Von 320 eingerichteten DIENSTEN" - im Dativ. Auf "Wie viele
            # Dienste laufen?" fand der Volltext ihn nicht, und der Vektor
            # stellte drei Saetze ueber Installiertes davor. Das Wort, nach
            # dem gefragt wird, gehoert in der Form hinein, in der gefragt
            # wird.
            "satz": "Auf dem Rechner sind %d Dienste eingerichtet; %d Dienste "
                    "laufen gerade, darunter %s."
                    % (d["insgesamt"], d.get("laufen") or 0, _namen(d.get("namen"))),
            "beleg": "Win32_Service"})

    a = mess.get("autostart") or {}
    if a.get("anzahl"):
        heraus.append({
            "schluessel": "rechner:autostart",
            "satz": "Beim Start (Autostart) laufen %d Programme mit, darunter %s."
                    % (a["anzahl"], _namen(a.get("namen"))),
            "beleg": "Win32_StartupCommand"})

    ordner = mess.get("ordner") or []
    if isinstance(ordner, dict):
        ordner = [ordner]
    for o in ordner:
        if not isinstance(o, dict) or not o.get("name"):
            continue
        dateien, unter = o.get("dateien") or 0, o.get("ordner") or 0
        if not dateien and not unter:
            continue
        satz = "In %s liegen %d Dateien und %d Ordner" % (o["name"], dateien, unter)
        if o.get("groesste"):
            satz += ", darunter %s" % _namen(o.get("groesste"))
        heraus.append({"schluessel": "rechner:ordner:%s" % str(o["name"]).lower(),
                       "satz": satz + ".", "beleg": "Verzeichnis %s" % o["name"]})
    return heraus


def _zustand() -> dict:
    try:
        return json.loads(ZUSTAND.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _zustand_schreiben(z: dict) -> None:
    try:
        import probenort
        probenort.schreiben_pruefen(ZUSTAND, "rechner._zustand_schreiben")
    except ImportError:
        pass
    WERKSTATT.mkdir(parents=True, exist_ok=True)
    tmp = ZUSTAND.with_suffix(".tmp")
    tmp.write_text(json.dumps(z, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ZUSTAND)


def faellig(jetzt: float | None = None) -> bool:
    jetzt = time.time() if jetzt is None else jetzt
    return jetzt - float(_zustand().get("zuletzt") or 0) >= STUNDEN * 3600


def durchgang(jetzt: float | None = None, lauf=None, merken=None,
              veralten=None, journal=None) -> dict:
    """Einmal zaehlen und das Ergebnis ins Gedaechtnis legen.

    Ohne `merken` ist es ein TROCKENLAUF: rechnen, zeigen, nichts behalten -
    und dann wird auch der Zustand nicht fortgeschrieben. Ein Trockenlauf, der
    den Zustand aendert, ist keiner; genau dieser Fehler hat in bestand.py
    sieben Saetze nie ins Gedaechtnis kommen lassen.
    """
    jetzt = time.time() if jetzt is None else jetzt
    mess = messen(lauf=lauf)
    if not mess:
        if journal:
            journal("fehler", "Der Rechner liess sich nicht zaehlen - "
                              "PowerShell hat nichts geliefert.")
        return {"gemessen": False, "gemerkt": 0, "saetze": []}

    neue = saetze(mess)
    trocken = merken is None
    z = _zustand()
    bekannt = dict(z.get("gruppen") or {})
    gemerkt, unveraendert = 0, 0

    for e in neue:
        schluessel = e["schluessel"]
        alt = bekannt.get(schluessel) or {}
        if alt.get("satz") == e["satz"] and alt.get("id"):
            unveraendert += 1
            continue
        kennung = None
        if not trocken:
            kennung = merken("zuhause", e["satz"], schluessel, alt.get("id"))
        gemerkt += 1
        bekannt[schluessel] = {"satz": e["satz"], "ts": jetzt, "id": kennung}

    # Eine Gruppe, die es nicht mehr gibt - ein entferntes Laufwerk, ein
    # geloeschter Ordner - darf ihren Satz nicht behalten. Ueberholen, nicht
    # loeschen: Calvin soll sehen koennen, was galt.
    jetzige = {e["schluessel"] for e in neue}
    veraltet = []
    for schluessel in list(bekannt):
        if schluessel in jetzige:
            continue
        veraltet.append(schluessel)
        if not trocken:
            if veralten is not None and (bekannt[schluessel] or {}).get("id"):
                veralten(bekannt[schluessel]["id"])
            bekannt.pop(schluessel, None)

    if not trocken:
        z["gruppen"] = bekannt
        z["zuletzt"] = jetzt
        _zustand_schreiben(z)
        if journal:
            import abschluss
            abschluss.schreiben(
                journal,
                "Ich habe meinen Rechner gezaehlt: %d neue Auskuenfte ueber "
                "Programme, Dienste und Ordner." % gemerkt,
                woran="Volkszaehlung",
                belegt_durch="rechner.json: %d Gruppen, %d unveraendert"
                             % (len(bekannt), unveraendert)
                if gemerkt else "")
    return {"gemessen": True, "gemerkt": gemerkt,
            "unveraendert": unveraendert, "veraltet": veraltet,
            "saetze": [e["satz"] for e in neue]}


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--merken", action="store_true",
                   help="die Saetze wirklich ins Gedaechtnis legen")
    a = p.parse_args()
    if a.merken:
        import bestand
        b = durchgang(merken=bestand.merker(), veralten=bestand.veralter())
    else:
        b = durchgang()
    if not b["gemessen"]:
        print("nichts gemessen")
        return 1
    for s in b["saetze"]:
        print(" -", s)
    print("\n%d gemerkt, %d unveraendert" % (b["gemerkt"], b.get("unveraendert", 0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
