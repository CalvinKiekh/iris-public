"""Was sich auf diesem Rechner STARTEN laesst - und was davon ein Spiel ist.

    python programme.py                  das Verzeichnis zeigen
    python programme.py --merken         die Saetze ins Gedaechtnis legen
    python programme.py --finden "arc"   nachschlagen, was gemeint ist
    python programme_test.py             die Probe

WARUM ES DIESE DATEI GIBT. Calvins Satz am 13.09.: "Wenn ich jetzt zum
Beispiel zu dem Bewohner sage, starte das und das Spiel, soll er das am Ende
ja auch koennen. Das kann er aber nur, wenn er weiss, wo das und das Spiel ist
und dass das ueberhaupt ein Spiel ist."

`rechner.py` ZAEHLT - 121 Programme, 320 Dienste. Das beantwortet "was ist da",
nicht "wo ist es". Zum Starten braucht es beides, und dazu die Einordnung:
"ARC Raiders" ist ein Spiel, "Audacity" ist ein Werkzeug, und ohne diesen
Unterschied kann er auf "starte mein Spiel" nur raten.

WOHER DAS WISSEN KOMMT - vier Quellen, und die Herkunft entscheidet mit:

    Steam        steamapps\\appmanifest_*.acf - jedes ist ein Spiel, ohne
                 Raten, mit seiner AppID zum Starten
    Epic         die Manifeste des Launchers - dasselbe
    Startmenue   die Verknuepfungen, die Windows selbst anzeigt
    Desktop      was Calvin sich dorthin gelegt hat

GERATEN WIRD NUR, WO NICHTS BESSERES DA IST. Ein Steam-Eintrag ist ein Spiel,
weil er aus Steam kommt - nicht, weil sein Name danach klingt. Fuer die
Verknuepfungen im Startmenue entscheidet der Ordner, in dem sie liegt. Bleibt
beides stumm, heisst die Art "programm" und nicht "wahrscheinlich ein Spiel":
Eine Vermutung, die wie Wissen aussieht, ist schlimmer als eine Luecke.

NICHTS WIRD GESTARTET. Diese Datei liest und schreibt ein Verzeichnis, mehr
nicht. Ob und wie etwas gestartet werden darf, entscheidet Calvin - dafuer
gibt es den Antragsweg, und der fuehrt nicht durch diese Datei.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import haus

HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"
VERZEICHNIS = WERKSTATT / "programme.json"

# Wie oft neu gesehen wird. Ein Spiel wird nicht stuendlich installiert.
STUNDEN = 6.0

# Wie viele Namen ein Satz nennt - dieselbe Ueberlegung wie in rechner.py.
NAMEN_MAX = 8

# Zwei Arten, weil die Daten zwei hergeben. Eine dritte ("werkzeug") stand
# hier und wurde nie vergeben - eine Art, die niemand setzt, ist keine Art,
# sondern eine leere Ueberschrift.
ARTEN = ("spiel", "programm")

_SUCHEN = r"""
function Ziel($lnk) {
  try {
    $sh = New-Object -ComObject WScript.Shell
    $z = $sh.CreateShortcut($lnk)
    return $z.TargetPath
  } catch { return '' }
}

$gefunden = @()

# --- Steam: jedes Manifest ist ein Spiel, mit AppID.
$bibliotheken = @()
foreach ($wurzel in @('C:\Program Files (x86)\Steam','C:\Program Files\Steam',
                      "$env:ProgramFiles\Steam")) {
  if (Test-Path (Join-Path $wurzel 'steamapps')) { $bibliotheken += (Join-Path $wurzel 'steamapps') }
}
$vdf = 'C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf'
if (Test-Path $vdf) {
  foreach ($zeile in Get-Content $vdf) {
    if ($zeile -match '"path"\s+"([^"]+)"') {
      $p = $matches[1] -replace '\\\\','\'
      $p = Join-Path $p 'steamapps'
      if ((Test-Path $p) -and ($bibliotheken -notcontains $p)) { $bibliotheken += $p }
    }
  }
}
foreach ($b in $bibliotheken) {
  foreach ($m in Get-ChildItem $b -Filter 'appmanifest_*.acf' -ErrorAction SilentlyContinue) {
    $text = Get-Content $m.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    $name = ''; $id = ''; $ordner = ''
    if ($text -match '"name"\s+"([^"]+)"')      { $name = $matches[1] }
    if ($text -match '"appid"\s+"([^"]+)"')     { $id = $matches[1] }
    if ($text -match '"installdir"\s+"([^"]+)"'){ $ordner = $matches[1] }
    if ($name) {
      $gefunden += [pscustomobject]@{
        name = $name; art = 'spiel'; quelle = 'steam'
        pfad = (Join-Path (Join-Path $b 'common') $ordner)
        start = "steam://rungameid/$id"
      }
    }
  }
}

# --- Epic: die Manifeste des Launchers.
$epic = 'C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests'
if (Test-Path $epic) {
  foreach ($m in Get-ChildItem $epic -Filter '*.item' -ErrorAction SilentlyContinue) {
    try {
      $j = Get-Content $m.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
      if ($j.DisplayName) {
        $gefunden += [pscustomobject]@{
          name = $j.DisplayName; art = 'spiel'; quelle = 'epic'
          pfad = $j.InstallLocation
          start = "com.epicgames.launcher://apps/$($j.AppName)?action=launch&silent=true"
        }
      }
    } catch {}
  }
}

# --- Startmenue und Desktop: was Windows selbst anbietet.
$orte = @(
  @{ pfad = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"; quelle = 'startmenue' },
  @{ pfad = 'C:\ProgramData\Microsoft\Windows\Start Menu\Programs'; quelle = 'startmenue' },
  @{ pfad = "$env:USERPROFILE\Desktop"; quelle = 'desktop' })
foreach ($o in $orte) {
  if (-not (Test-Path $o.pfad)) { continue }
  foreach ($l in Get-ChildItem $o.pfad -Recurse -Filter '*.lnk' -ErrorAction SilentlyContinue) {
    $ziel = Ziel $l.FullName
    $gefunden += [pscustomobject]@{
      name = $l.BaseName; art = ''; quelle = $o.quelle
      pfad = $ziel; start = $l.FullName
      ordner = $l.Directory.Name
    }
  }
}

$gefunden | ConvertTo-Json -Depth 4 -Compress
"""

# Woran ein Spiel im Startmenue zu erkennen ist: an dem Ordner, in dem seine
# Verknuepfung liegt, oder an dem Pfad, auf den sie zeigt. NICHT am Namen -
# "Battlefield" im Namen macht einen Ordner zu keinem Spiel, und ein Spiel,
# das "Audacity" heisst, gaebe es auch.
_SPIEL_ORDNER = re.compile(r"\b(steam|epic\s*games|gog|ubisoft|origin|ea\s*app|"
                           r"battle\.?net|riot|xbox|games?|spiele)\b", re.IGNORECASE)
_SPIEL_PFAD = re.compile(r"[\\/](steamapps|epic\s*games|gog galaxy|ubisoft|"
                         r"ea games|riot games|battle\.net)[\\/]", re.IGNORECASE)

# Was gar nicht in das Verzeichnis gehoert: Deinstallation, Hilfe, Handbuecher.
# Sie sind startbar und nie gemeint - "starte die Deinstallation von X" ist
# kein Satz, den Calvin sagt, und ein Treffer darauf waere schlimmer als keiner.
# Die Wortstaemme, nicht die ganzen Woerter: "Audacity deinstallieren" ging
# durch, weil nach "deinstall" keine Wortgrenze steht. Ein Riegel, der nur die
# Grundform kennt, faengt im Deutschen fast nichts.
_NICHT = re.compile(r"\b(uninstall\w*|deinstall\w*|entfern\w*|readme|liesmich|"
                    r"hilfe|help|handbuch|manual|dokumentation|website|"
                    r"homepage|support|lizenz|license|changelog|"
                    r"release\s*notes)\b",
                    re.IGNORECASE)


def _art_raten(eintrag: dict) -> str:
    """Die Art aus der HERKUNFT, nicht aus dem Namen."""
    if eintrag.get("art"):
        return str(eintrag["art"])
    ordner = str(eintrag.get("ordner") or "")
    pfad = str(eintrag.get("pfad") or "")
    if _SPIEL_ORDNER.search(ordner) or _SPIEL_PFAD.search(pfad):
        return "spiel"
    return "programm"


def _saeubern(roh) -> list[dict]:
    """Aus der Messung ein Verzeichnis: eingeordnet, entdoppelt, sortiert."""
    if isinstance(roh, dict):
        roh = [roh]
    if not isinstance(roh, list):
        return []
    nach_name: dict[str, dict] = {}
    for e in roh:
        if not isinstance(e, dict):
            continue
        name = " ".join(str(e.get("name") or "").split())
        if not name or _NICHT.search(name):
            continue
        eintrag = {"name": name, "art": _art_raten(e),
                   "pfad": str(e.get("pfad") or ""),
                   "start": str(e.get("start") or ""),
                   "quelle": str(e.get("quelle") or "")}
        schluessel = name.lower()
        alt = nach_name.get(schluessel)
        # Steam und Epic wissen es besser als eine Verknuepfung: Ihr Eintrag
        # traegt die AppID und die gesicherte Art. Er sticht.
        if alt and alt.get("quelle") in ("steam", "epic"):
            continue
        nach_name[schluessel] = eintrag
    return sorted(nach_name.values(), key=lambda e: (e["art"], e["name"].lower()))


def sehen(lauf=None) -> list[dict]:
    """Einmal nachsehen, was startbar ist. `lauf` nur fuer die Probe."""
    roh = lauf() if lauf is not None else haus._ps_json(_SUCHEN, frist=180)
    return _saeubern(roh)


def lesen() -> list[dict]:
    """Das gespeicherte Verzeichnis - oder eine leere Liste."""
    try:
        d = json.loads(VERZEICHNIS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    eintraege = d.get("eintraege") if isinstance(d, dict) else d
    return eintraege if isinstance(eintraege, list) else []


def schreiben(eintraege: list[dict], jetzt: float | None = None) -> None:
    try:
        import probenort
        probenort.schreiben_pruefen(VERZEICHNIS, "programme.schreiben")
    except ImportError:
        pass
    WERKSTATT.mkdir(parents=True, exist_ok=True)
    d = {"zuletzt": time.time() if jetzt is None else jetzt,
         "eintraege": eintraege}
    tmp = VERZEICHNIS.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, VERZEICHNIS)


def _woerter(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", str(text).lower()) if len(w) > 1]


def finden(gesucht: str, eintraege=None, art: str | None = None) -> list[dict]:
    """Was koennte gemeint sein? Die besten Treffer, bestes zuerst.

    Woertlich und ueber Wortanfaenge, ohne Modell: "arc" soll "ARC Raiders"
    finden, "battlefield" soll "Battlefield 6" finden. Wer hier ein Modell
    fragt, bekommt an manchen Tagen ein Spiel, das es nicht gibt.

    ES WIRD NIE GERATEN, WENN ES MEHRDEUTIG IST. Die Liste kommt vollstaendig
    zurueck; wer sie benutzt, muss nachfragen, statt den ersten zu nehmen.
    """
    eintraege = lesen() if eintraege is None else eintraege
    worte = _woerter(gesucht)
    if not worte:
        return []
    treffer = []
    for e in eintraege:
        if art and e.get("art") != art:
            continue
        name = str(e.get("name") or "").lower()
        namensworte = _woerter(name)
        punkte = 0.0
        if name == " ".join(worte):
            punkte += 10
        for w in worte:
            if w in namensworte:
                punkte += 3
            elif any(n.startswith(w) for n in namensworte):
                punkte += 2
            elif w in name:
                punkte += 1
        if punkte:
            # Ein Spiel ist bei gleicher Punktzahl das wahrscheinlichere Ziel:
            # Nach "starte X" ist X selten ein Treiberdienstprogramm.
            treffer.append((punkte + (0.5 if e.get("art") == "spiel" else 0), e))
    treffer.sort(key=lambda t: (-t[0], t[1]["name"].lower()))
    return [e for _, e in treffer[:8]]


def saetze(eintraege: list[dict]) -> list[dict]:
    """Was davon ins Gedaechtnis gehoert - je Art ein Satz."""
    heraus = []
    for art, wort in (("spiel", "Spiele"), ("programm", "startbare Programme")):
        dran = [e for e in eintraege if e.get("art") == art]
        if not dran:
            continue
        namen = [e["name"] for e in dran]
        if len(namen) > NAMEN_MAX:
            letzte = len(namen) - 1
            plaetze = sorted({round(i * letzte / (NAMEN_MAX - 1))
                              for i in range(NAMEN_MAX)})
            namen = [namen[i] for i in plaetze]
        heraus.append({
            "schluessel": "programme:%s" % art,
            "satz": "Auf dem Rechner sind %d %s installiert, darunter %s."
                    % (len(dran), wort, ", ".join(namen))})
    return heraus


def faellig(jetzt: float | None = None) -> bool:
    jetzt = time.time() if jetzt is None else jetzt
    try:
        d = json.loads(VERZEICHNIS.read_text(encoding="utf-8"))
        zuletzt = float(d.get("zuletzt") or 0)
    except (OSError, ValueError, TypeError):
        zuletzt = 0.0
    return jetzt - zuletzt >= STUNDEN * 3600


def durchgang(jetzt: float | None = None, lauf=None, merken=None,
              journal=None) -> dict:
    """Einmal nachsehen, das Verzeichnis schreiben, die Saetze merken."""
    jetzt = time.time() if jetzt is None else jetzt
    eintraege = sehen(lauf=lauf)
    if not eintraege:
        if journal:
            journal("fehler", "Es liess sich nichts Startbares finden.")
        return {"gefunden": 0, "gemerkt": 0, "saetze": []}

    neue = saetze(eintraege)
    if merken is None:
        return {"gefunden": len(eintraege), "gemerkt": 0,
                "saetze": [e["satz"] for e in neue], "trocken": True}

    schreiben(eintraege, jetzt)
    alt = {e["schluessel"]: e for e in []}
    gemerkt = 0
    for e in neue:
        if merken("zuhause", e["satz"], e["schluessel"], None):
            gemerkt += 1
    if journal:
        import abschluss
        abschluss.schreiben(
            journal,
            "Ich habe nachgesehen, was sich starten laesst: %d Eintraege, "
            "davon %d Spiele." % (len(eintraege),
                                  sum(1 for e in eintraege if e["art"] == "spiel")),
            woran="Startbares",
            belegt_durch="programme.json: %d Eintraege" % len(eintraege))
    return {"gefunden": len(eintraege), "gemerkt": gemerkt,
            "saetze": [e["satz"] for e in neue]}


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--merken", action="store_true")
    p.add_argument("--finden", default="")
    a = p.parse_args()

    if a.finden:
        for e in finden(a.finden):
            print("  %-9s %-40s %s" % (e["art"], e["name"][:40],
                                       e.get("start") or e.get("pfad")))
        return 0

    if a.merken:
        import bestand
        b = durchgang(merken=bestand.merker())
    else:
        b = durchgang()
    eintraege = lesen() if a.merken else sehen()
    for art in ARTEN:
        dran = [e for e in eintraege if e["art"] == art]
        print("\n== %s (%d) ==" % (art, len(dran)))
        for e in dran[:12]:
            print("   %-42s %s" % (e["name"][:42], (e.get("start") or e.get("pfad"))[:70]))
    print()
    for s in b["saetze"]:
        print(" -", s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
