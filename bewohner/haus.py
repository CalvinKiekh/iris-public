"""haus - was in seinem Haus los ist. Reine Messung, nur lesend.

Calvin am 12.09.2026:

    "Ich moechte, dass er alles ueberwacht [...] Er ist Bewohner dieses
    Rechners. Er weiss, was passiert. Er weiss, wer wann was auf dem Rechner
    macht, was wann installiert wurde, was umgebaut wurde, was gerade laeuft,
    was nicht laeuft. Er weiss, wie viel CPU er hat, GPU, Arbeitsspeicher,
    Speicher. Weil er Bewohner dieses Systems ist. Er kuemmert sich um das,
    wo er wohnt."

Bis heute kannte er den Flur: `lage.py` (Uhrzeit, Geraete im Netz, Platte)
und `selbst.py` (Ollama, Tempo, GPU-Speicher, Waisen, Ticks). Er wusste
nicht, welche Prozesse laufen und seit wann, wie ausgelastet die Maschine
ist, welcher Dienst gestorben ist.

Hier steht das Haus:

    maschine()   Kerne, Auslastung, Arbeitsspeicher, Laufzeit seit dem
                 Hochfahren
    platten()    jedes Laufwerk mit frei, gesamt, wie voll
    gpu()        Auslastung, Speicher, Temperatur - nicht nur Speicher
    prozesse()   die groessten zehn: Name, PID, seit wann, Speicher, Rechenzeit
    dienste()    was laeuft; und was laufen SOLL und nicht laeuft

Und, das ist der Kern: `veraenderungen(alt, neu)`. "Was ist passiert" ist
eine Frage nach Veraenderung, nicht nach Zustand. Ohne ein Vorher kann er nur
aufzaehlen, was gerade ist - und das interessiert niemanden.

KEIN MODELL. Kein gpt-oss, keine Deutung, keine Bewertung. Nur Zahlen und
Namen. Das Modell formuliert spaeter daraus; die Messung liefert.

NUR LESEN. Kein Prozess wird beendet, kein Dienst angefasst, nichts
installiert. Was er aendern will, geht ueber einen Antrag an Calvin.

Alles ueber EINEN PowerShell-Aufruf. Einzelaufrufe kosten je 0,3 bis 1 s, und
das hier soll jede halbe Minute laufen koennen.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"
HAUS_DATEI = WERKSTATT / "haus.json"

# Die groessten so vielen Prozesse. Mehr macht den Blick nicht klarer: Auf
# diesem Rechner laufen ueber 300, und die Haelfte davon sind Dienste, die
# seit dem Hochfahren nichts getan haben.
PROZESSE_HOECHSTENS = 12
# Ab so viel Arbeitsspeicher ist ein Prozess ueberhaupt der Rede wert.
PROZESS_MB_AB = 100

# Stufen, in denen verglichen wird. Ohne sie ist jede Messung eine
# "Veraenderung": Der freie Speicher schwankt im Sekundentakt um Megabyte,
# die CPU-Last um Prozentpunkte. Dieselbe Lehre wie bei Beobachter._platte,
# die den Platz in 5-GB-Stufen meldet.
STUFE_RAM_PROZENT = 10
STUFE_PLATTE_GB = 5
STUFE_GPU_SPEICHER_GB = 1
STUFE_CPU_PROZENT = 25
# Erst so lange laeuft ein Prozess, bevor er als "neu da" gilt. Ein Aufruf,
# der zwei Sekunden dauert, ist kein Ereignis im Haus.
PROZESS_JUNG_S = 20
# So oft darf etwas kommen und gehen, bevor es als Bedarfsdienst gilt und
# nicht mehr gemeldet wird. Zwei heisst: einmal weg, einmal wieder da - ein
# ganzer Umlauf. Der erste wird gemeldet, der zweite nicht mehr.
#
# EINE Zahl fuer Dienste UND Prozessnamen, und das ist kein Zufall: Es ist
# dieselbe Regel. Bis 12.09. abends galt sie nur fuer Dienste, und das Ergebnis
# hat Calvin gezaehlt - von 21 Beobachtungen waren 17 Rauschen, davon zwoelf
# Zeilen "smartscreen laeuft / laeuft nicht mehr". smartscreen startet, wenn
# Edge eine Datei prueft, und endet nach ein paar Minuten Ruhe. Das IST sein
# Normalzustand.
#
# Und der eigentliche Fehler war nicht, dass die Regel fehlte, sondern dass
# ich sie um 15:35 schon selbst formuliert hatte: "Der Dienst TrustedInstaller
# kommt und geht von selbst; ich nehme ihn als Bedarfsdienst und melde ihn
# nicht mehr." Richtig gedacht - und dann fuer GENAU EINEN Namen gebaut. Eine
# Regel, die von der Gattung handelt, gehoert nicht an einen Namen.
DIENST_WECHSEL_BIS_BEDARF = 2
# So weit zurueck wird gezaehlt. Calvins Regel handelt von einem TAG: "Ein
# Prozess, der innerhalb eines Tages mehrfach kommt und geht, ist ein
# Bedarfsdienst." Aelteres zaehlt nicht mehr mit - sonst wuerde ein Name, der
# vor drei Wochen zweimal flackerte, fuer immer verschwiegen.
BEDARF_FENSTER_H = 24
# Um so viel muss die aelteste Startzeit eines Namens nach vorn springen,
# damit es ein Neustart ist und nicht ein zweites Fenster. Die Zahl stand
# zweimal als 60 im Modul; sie gehoert an eine Stelle, weil der Zaehler fuer
# Bedarfsdienste dieselbe Frage stellt wie die Meldung.
NEUSTART_SPRUNG_S = 60

# Das sind WIR beide bei der Arbeit: der Mac ueber SSH, die Sitzungen, die
# Werkzeuge, die Messbefehle. Er darf sie sehen und auf Nachfrage nennen -
# aber sie sind keine Veraenderung im Haus und loesen nichts aus.
#
# Dieselbe Ausnahme wie die Werkstatt bei den Dateien, und aus demselben
# Grund: Sonst reagiert er auf seine eigenen Spuren. Am 12.09. sind daraus
# 44 Journalzeilen in 90 Minuten geworden und ein Antrag an Calvin um 11:54,
# der fuer ein Phantom genehmigt wurde.
#
# ollama und llama-server stehen bewusst NICHT hier. Wenn der Dienst
# verschwindet, mit dem er denkt, will er das wissen.
UNSERE_WERKZEUGE = frozenset({
    "python", "pythonw", "python3", "pythonw3.10", "py",
    "claude", "node", "bash", "sh", "git",
    "ssh", "sshd", "scp",
    "powershell", "pwsh", "cmd", "conhost", "tasklist", "where",
    "WindowsTerminal", "OpenConsole", "timeout", "chcp",
})


def _unsere_orte() -> list[str]:
    """WOHER unsere Werkzeuge kommen - gemessen, nicht aufgezaehlt.

    Die Namensliste oben hat eine Luecke, die sie nicht schliessen kann: Am
    12.09. um 18:49 stand "tail laeuft, seit 18:49." im Journal und zwei
    Minuten spaeter "tail laeuft nicht mehr." - das war unser eigenes tail,
    waehrend ich an sitzung.py arbeitete. Er meldet, dass unsere Werkzeuge
    fertig werden.

    `tail` in die Liste zu schreiben loest genau diesen einen Fall. Dahinter
    stehen grep, sed, head, wc, sort, uniq, cut, tr, xargs, jq und alles
    andere, was in einer Git-Bash steckt - und beim naechsten Befehl ist es
    ein Name, der nicht drinsteht. Wer eine Liste pflegt, pflegt die Luecken
    mit; das steht schon dreimal in diesem Haus, zuletzt heute nachmittag in
    wissen._VERGAENGLICH.

    Der Ort ist messbar: Was aus der Git-Installation, aus unserem venv oder
    aus dem Projektordner laeuft, sind WIR. Gefunden wird er ueber das
    Programm selbst (`shutil.which`), nicht geraten.

    Die Schranke von drei Teilen ist wichtig: Gaebe `which` je einen kurzen
    Pfad zurueck, stuende hier "C:\\" - und dann waere jeder Prozess im Haus
    unser eigener und er meldete nie wieder etwas.
    """
    orte = {HIER.resolve(),                 # das Projekt selbst
            # sys.prefix und nicht das Verzeichnis des Programms: Beim
            # Bewohner ist das ...\tts-test\venv, bei einem Aufruf aus der
            # Konsole das Verzeichnis des Store-Python. Beides ist genau die
            # Python-Installation und nichts darueber hinaus - mit
            # parent.parent stand hier ...\Microsoft\WindowsApps, und damit
            # waere jede Store-Anwendung unser eigenes Werkzeug gewesen.
            Path(sys.prefix).resolve(),
            # Und die Installation, auf der das venv aufsitzt. Gemessen: Der
            # Bewohner selbst heisst im Haus `pythonw3.10`, und diese Datei
            # liegt nicht im venv, sondern in der Python-Installation. Ohne
            # base_prefix erkennt er jeden Prozess als unseren - ausser sich
            # selbst.
            Path(sys.base_prefix).resolve(),
            Path(sys.executable).resolve().parent}
    for befehl in ("git", "bash"):
        wo = shutil.which(befehl)
        if not wo:
            continue
        # Ein Verzeichnis hoeher als der Ordner des Programms: aus
        # ...\Git\usr\bin\bash.exe wird ...\Git\usr, und damit ist
        # usr\bin\tail.exe mitgefasst, ohne tail zu kennen.
        orte.add(Path(wo).resolve().parent.parent)
    return sorted(str(o).lower() for o in orte if len(o.parts) >= 3)


def _ohne_fenster(befehl: list[str], frist: int = 40) -> str:
    try:
        r = subprocess.run(befehl, capture_output=True, text=True,
                           timeout=frist, encoding="utf-8", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _ps_json(befehl: str, frist: int = 40):
    """PowerShell einmal aufrufen und JSON zurueckbekommen.

    Die Ausgabe wird ausdruecklich auf UTF-8 gestellt. Ohne das kommen
    Laufwerksbezeichnungen und Dienstnamen mit Umlauten als Fragezeichen an.
    """
    kopf = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ErrorActionPreference='SilentlyContinue'; "
    roh = _ohne_fenster(["powershell", "-NoProfile", "-NonInteractive",
                         "-Command", kopf + befehl], frist)
    roh = roh.strip()
    if not roh:
        return None
    try:
        return json.loads(roh)
    except json.JSONDecodeError:
        return None


# ------------------------------------------------------------------ Messung


# Ein Aufruf fuer Maschine, Platten, Prozesse und Dienste. Get-CimInstance
# statt Get-WmiObject: schneller und ohne DCOM.
_MESSEN = r"""
$os  = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$hoch = $os.LastBootUpTime

# Win32_Processor.LoadPercentage ist ein Mittel ueber ein Messintervall und
# kommt regelmaessig leer zurueck - gemessen am 12.09., da stand dann
# "16 Kerne bei None Prozent" im Satz. Der Leistungsindikator antwortet
# immer; LoadPercentage bleibt der Rueckfall.
$last = (Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'").PercentProcessorTime
if ($null -eq $last) { $last = $cpu.LoadPercentage }

$platten = @(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" |
  ForEach-Object {
    [pscustomobject]@{
      laufwerk  = $_.DeviceID
      name      = $_.VolumeName
      frei_gb   = [math]::Round($_.FreeSpace/1GB, 1)
      gesamt_gb = [math]::Round($_.Size/1GB, 1)
    }})

$alle = @(Get-Process)

$prozesse = @($alle | Where-Object { $_.WorkingSet64 -gt %(mb)dMB } |
  Sort-Object WorkingSet64 -Descending | Select-Object -First %(n)d |
  ForEach-Object {
    $s = $null
    try { $s = $_.StartTime } catch {}
    [pscustomobject]@{
      name   = $_.ProcessName
      pid    = $_.Id
      ram_mb = [math]::Round($_.WorkingSet64/1MB)
      cpu_s  = [math]::Round($_.CPU, 1)
      seit   = if ($s) { [math]::Round(($s).ToUniversalTime().Subtract([datetime]'1970-01-01').TotalSeconds) } else { $null }
    }})

# JEDER Name, nicht nur die groessten. Wer aus der Bestenliste faellt, weil
# ein anderer mehr Speicher belegt, laeuft trotzdem weiter - "X laeuft nicht
# mehr" waere dann schlicht gelogen. Je Name der aelteste Start: springt der
# nach vorn, wurde neu gestartet.
# Woher die Programme kommen, die WIR benutzen. Der Pfad wird NICHT
# mitgeschickt - 156 Namen mit Pfad waeren 18 KB mehr in haus.json, jede
# Minute neu geschrieben. Es genuegt die Antwort auf die eine Frage.
$unsere = @(%(orte)s)

$namen = @($alle | Group-Object ProcessName | ForEach-Object {
    $aeltester = $null
    $pfad = $null
    foreach ($p in $_.Group) {
      try { $s = $p.StartTime } catch { $s = $null }
      if ($s -and (-not $aeltester -or $s -lt $aeltester)) { $aeltester = $s }
      if (-not $pfad) { try { $pfad = $p.Path } catch {} }
    }
    $unser = $false
    if ($pfad) {
      $klein = $pfad.ToLower()
      foreach ($o in $unsere) { if ($klein.StartsWith($o)) { $unser = $true } }
    }
    [pscustomobject]@{
      name    = $_.Name
      anzahl  = $_.Count
      seit    = if ($aeltester) { [math]::Round(($aeltester).ToUniversalTime().Subtract([datetime]'1970-01-01').TotalSeconds) } else { $null }
      unser   = $unser
    }} | Sort-Object name)

$dienste = Get-CimInstance Win32_Service
$sollen  = @($dienste | Where-Object { $_.StartMode -eq 'Auto' -and $_.State -ne 'Running' -and $_.Name -notmatch '^(RemoteRegistry|sppsvc|MapsBroker|gupdate|edgeupdate|dbupdate|CDPUserSvc|OneSyncSvc|WpnUserService|cbdhsvc|BluetoothUserService|PimIndexMaintenanceSvc|UserDataSvc|UnistoreSvc|DevicePickerUserSvc|PrintWorkflowUserSvc|MessagingService|DeviceAssociationBrokerSvc|CaptureService|WpnService)' } |
  ForEach-Object { $_.Name } | Sort-Object)

[pscustomobject]@{
  maschine = [pscustomobject]@{
    rechner        = $env:COMPUTERNAME
    cpu_name       = $cpu.Name
    cpu_kerne      = $cpu.NumberOfCores
    cpu_threads    = $cpu.NumberOfLogicalProcessors
    cpu_last       = $last
    ram_gesamt_gb  = [math]::Round($os.TotalVisibleMemorySize/1MB, 1)
    ram_frei_gb    = [math]::Round($os.FreePhysicalMemory/1MB, 1)
    hochgefahren   = [math]::Round(($hoch).ToUniversalTime().Subtract([datetime]'1970-01-01').TotalSeconds)
    windows        = $os.Caption
  }
  platten   = $platten
  prozesse  = $prozesse
  namen     = $namen
  dienste   = [pscustomobject]@{
    laufen          = @($dienste | Where-Object { $_.State -eq 'Running' }).Count
    insgesamt       = @($dienste).Count
    sollen_aber_aus = $sollen
  }
} | ConvertTo-Json -Depth 4 -Compress
"""


def _orte_fuer_ps() -> str:
    """Die Orte als PowerShell-Liste. Einfache Anfuehrungszeichen, damit der
    Backslash ein Backslash bleibt."""
    return ",".join("'%s'" % o.replace("'", "''") for o in _unsere_orte())


def messen() -> dict:
    """Maschine, Platten, Prozesse, Dienste - in einem Aufruf."""
    d = _ps_json(_MESSEN % {"mb": PROZESS_MB_AB, "n": PROZESSE_HOECHSTENS,
                            "orte": _orte_fuer_ps()}, 60)
    if not isinstance(d, dict):
        return {}
    # ConvertTo-Json macht aus einer einelementigen Liste ein Objekt.
    for schluessel in ("platten", "prozesse", "namen"):
        wert = d.get(schluessel)
        if isinstance(wert, dict):
            d[schluessel] = [wert]
        elif wert is None:
            d[schluessel] = []
    dienste = d.get("dienste") or {}
    aus = dienste.get("sollen_aber_aus")
    if isinstance(aus, str):
        dienste["sollen_aber_aus"] = [aus]
    elif aus is None:
        dienste["sollen_aber_aus"] = []
    return d


def gpu() -> dict:
    """Auslastung, Speicher und Temperatur - nicht nur Speicher.

    selbst.py misst den geteilten Speicher je Prozess, weil dort ein echter
    Fehler steckte. Was fehlte, war die Auslastung: Eine GPU kann voll belegt
    und trotzdem unbeschaeftigt sein.
    """
    roh = _ohne_fenster(
        ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,"
                       "memory.total,temperature.gpu",
         "--format=csv,noheader,nounits"], 20)
    zeile = roh.strip().splitlines()[0] if roh.strip() else ""
    teile = [t.strip() for t in zeile.split(",")]
    if len(teile) != 5:
        return {}

    def zahl(t):
        try:
            return int(float(t))
        except ValueError:
            return None

    return {"name": teile[0], "last_prozent": zahl(teile[1]),
            "speicher_mb": zahl(teile[2]), "speicher_gesamt_mb": zahl(teile[3]),
            "temperatur_c": zahl(teile[4])}


# ------------------------------------------------------- was installiert ist


# Die drei Stellen, an denen Windows installierte Programme fuehrt. Ohne den
# WOW6432Node fehlen alle 32-Bit-Programme, ohne HKCU alles, was nur fuer
# diesen Benutzer installiert wurde - und das ist auf einem Arbeitsrechner
# die Haelfte.
_PROGRAMME = r"""
$orte = @(
  'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*')
@(Get-ItemProperty $orte |
  Where-Object { $_.DisplayName -and -not $_.SystemComponent -and
                 -not $_.ParentKeyName -and $_.DisplayName -notmatch '^KB\d' } |
  ForEach-Object {
    [pscustomobject]@{
      name    = $_.DisplayName
      fassung = $_.DisplayVersion
    }} | Sort-Object name -Unique) | ConvertTo-Json -Depth 2 -Compress
"""


def programme() -> list[dict]:
    """Was installiert ist. Nur die Namensliste - Fassungen inklusive, damit
    ein Update als Update sichtbar wird und nicht als Neuinstallation."""
    d = _ps_json(_PROGRAMME, 60)
    if isinstance(d, dict):
        return [d]
    return d if isinstance(d, list) else []


def bild(mit_programmen: bool = False) -> dict:
    """Das ganze Haus auf einmal. Reine Zahlen, keine Deutung.

    Die Programmliste kostet den Registry-Durchlauf und aendert sich selten -
    sie kommt nur, wenn ausdruecklich danach gefragt wird. Der Haus-Faden holt
    sie seltener als den Rest.
    """
    d = messen()
    d["gpu"] = gpu()
    if mit_programmen:
        d["programme"] = programme()
    d["ts"] = time.time()
    return d


# ------------------------------------------------------------------ Vorher


def lesen(pfad: Path = HAUS_DATEI) -> dict:
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def schreiben(d: dict, pfad: Path = HAUS_DATEI) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    # Die vorlaeufige Datei traegt die Prozessnummer. Ohne sie benutzen zwei
    # Prozesse denselben Namen, und der eine tauscht um, waehrend der andere
    # noch schreibt - dann liegt eine halbe Datei als haus.json da. Genau so
    # ist es am 12.09. um 21:05 passiert: Ich habe fortschreiben() aus der
    # Konsole gemessen, waehrend der Bewohner lief, und kontext_test.py meldete
    # 39 von 43, weil der Rechnerblock aus einem unlesbaren haus.json nicht
    # gebaut werden konnte. Der Austausch selbst ist atomar, das Schreiben
    # davor war es nicht.
    vorlaeufig = pfad.with_suffix(".json.%d.tmp" % os.getpid())
    vorlaeufig.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    vorlaeufig.replace(pfad)


def _sprung(alt, neu, breite) -> bool:
    """Hat sich der Wert um mindestens eine Stufe bewegt?

    Der Abstand, nicht der Eimer. Mit Eimern (wert // breite) meldete ein
    Sprung von 1500 auf 1498 GB eine Veraenderung, weil zufaellig eine
    Fuenfergrenze dazwischenlag - zwei Gigabyte auf einer Vier-Terabyte-Platte.
    Wer an Grenzen quantisiert, meldet Rauschen und verschweigt Bewegung.

    Langsames Wandern faengt das hier nicht - das ist Absicht. haus.py meldet
    SPRUENGE; den schleichenden Verlauf ueber Stunden hat platzverlauf, und
    anlaesse.platz_muster macht daraus einen Redeanlass.
    """
    if alt is None or neu is None:
        return False
    try:
        return abs(float(neu) - float(alt)) >= breite
    except (TypeError, ValueError):
        return False


def _uhr(ts) -> str:
    try:
        return time.strftime("%H:%M", time.localtime(float(ts)))
    except (TypeError, ValueError, OSError):
        return "?"


def _dauer(sekunden) -> str:
    try:
        s = int(float(sekunden))
    except (TypeError, ValueError):
        return "?"
    if s < 3600:
        n = s // 60
        return f"{n} Minute" if n == 1 else f"{n} Minuten"
    if s < 86400:
        n = s // 3600
        return f"{n} Stunde" if n == 1 else f"{n} Stunden"
    n = s // 86400
    return f"{n} Tag" if n == 1 else f"{n} Tagen"


def _unser(p: dict | None, name: str) -> bool:
    """Sind wir das selbst? Zuerst am ORT gemessen, dann am Namen geraten.

    Der Name ist der schwaechere Weg und bleibt nur fuer die Faelle, in denen
    Windows den Pfad nicht herausgibt - bei Systemprozessen wirft `.Path` eine
    Ausnahme, und `claude` laeuft nicht immer aus demselben Verzeichnis.
    """
    if (p or {}).get("unser"):
        return True
    return name in UNSERE_WERKZEUGE


def veraenderungen(alt: dict, neu: dict) -> list[str]:
    """Was hat sich geaendert? Das ist der eigentliche Zweck dieses Moduls.

    Verglichen wird in STUFEN, nicht auf die Nachkommastelle. Der freie
    Arbeitsspeicher schwankt im Sekundentakt; ohne Stufen waere jede Messung
    eine Veraenderung und er haette rund um die Uhr etwas zu melden - genau
    die Rueckkopplung, die gedaechtnis.db schon einmal ausgeloest hat.

    Ohne Vorher gibt es KEINE Veraenderung, nur eine Feststellung. Derselbe
    erste Blick wie bei Beobachter.letzter is None.
    """
    if not alt:
        return []
    raus = []
    am = alt.get("maschine") or {}
    nm = neu.get("maschine") or {}

    # Der Rechner war aus. Das ist die groesste Veraenderung, die es gibt,
    # und bisher hat er sie nie bemerkt.
    if am.get("hochgefahren") and nm.get("hochgefahren") \
            and abs(float(nm["hochgefahren"]) - float(am["hochgefahren"])) > 60:
        raus.append(f"Der Rechner wurde neu gestartet, um "
                    f"{_uhr(nm['hochgefahren'])}.")

    if _sprung(_prozent_frei(am), _prozent_frei(nm), STUFE_RAM_PROZENT):
        raus.append(f"Vom Arbeitsspeicher sind jetzt {nm.get('ram_frei_gb')} "
                    f"von {nm.get('ram_gesamt_gb')} GB frei, vorher "
                    f"{am.get('ram_frei_gb')} GB.")

    if _sprung(am.get("cpu_last"), nm.get("cpu_last"), STUFE_CPU_PROZENT):
        raus.append(f"Die CPU liegt bei {nm.get('cpu_last')} Prozent, "
                    f"vorher {am.get('cpu_last')}.")

    # Platten
    ap = {p.get("laufwerk"): p for p in (alt.get("platten") or [])}
    for p in neu.get("platten") or []:
        v = ap.get(p.get("laufwerk"))
        if not v:
            raus.append(f"Ein Laufwerk ist dazugekommen: {p.get('laufwerk')} "
                        f"mit {p.get('gesamt_gb')} GB.")
            continue
        if _sprung(v.get("frei_gb"), p.get("frei_gb"), STUFE_PLATTE_GB):
            weg = round(float(v.get("frei_gb", 0)) - float(p.get("frei_gb", 0)), 1)
            raus.append(f"Auf {p.get('laufwerk')} sind "
                        f"{abs(weg)} GB {'weniger' if weg > 0 else 'mehr'} "
                        f"frei, jetzt {p.get('frei_gb')} GB.")
    for laufwerk in ap:
        if laufwerk not in {p.get("laufwerk") for p in neu.get("platten") or []}:
            raus.append(f"Das Laufwerk {laufwerk} ist nicht mehr da.")

    # Prozesse - ueber ALLE Namen, nicht ueber die Bestenliste. Wer aus den
    # groessten zwoelf faellt, weil ein anderer mehr Speicher belegt, laeuft
    # weiter; "X laeuft nicht mehr" waere dann falsch.
    an = {p.get("name"): p for p in alt.get("namen") or []}
    nn = {p.get("name"): p for p in neu.get("namen") or []}
    jetzt_ = time.time()

    # Wer gerade als Bedarfsdienst erkannt wurde, wird EINMAL genannt - und
    # danach nie wieder. Etwas, das stillschweigend aus der Meldung faellt,
    # sieht aus wie etwas, das nie da war. Genau dieselbe Zeile hat er um
    # 15:35 fuer TrustedInstaller geschrieben; jetzt gilt sie fuer alles, was
    # sich so verhaelt.
    bedarf = dict(neu.get("namen_bedarf") or {})
    for name in sorted(set(bedarf) - set(alt.get("namen_bedarf") or {})):
        if _unser(nn.get(name) or an.get(name), name):
            continue
        raus.append(f"{name} kommt und geht von selbst; ich nehme es als "
                    f"Bedarfsdienst und melde es nicht mehr.")

    for name, p in sorted(nn.items()):
        if _unser(p, name) or name in bedarf:
            continue
        vorher = an.get(name)
        if vorher is None:
            # Nicht jeden Aufruf melden, der zwei Sekunden dauert.
            if p.get("seit") and jetzt_ - float(p["seit"]) < PROZESS_JUNG_S:
                continue
            # Ohne lesbare Startzeit gar nicht melden. Bei Systemprozessen
            # ist sie nicht zugaenglich, und im Journal stand dann
            # "MoUsoCoreWorker laeuft, seit ?." - eine Meldung, die ihre
            # eigene Luecke vorzeigt. Wer nicht sagen kann, seit wann etwas
            # laeuft, hat auch nicht gemessen, dass es neu ist.
            if not p.get("seit"):
                continue
            raus.append(f"{name} laeuft, seit {_uhr(p.get('seit'))}.")
        elif p.get("seit") and vorher.get("seit") \
                and float(p["seit"]) - float(vorher["seit"]) > NEUSTART_SPRUNG_S:
            # Der aelteste Start ist nach vorn gesprungen: Der alte ist weg,
            # ein neuer da. Das ist ein Neustart, kein zweites Fenster.
            raus.append(f"{name} wurde neu gestartet, um "
                        f"{_uhr(p.get('seit'))}.")
    for name in sorted(set(an) - set(nn)):
        if _unser(an.get(name), name) or name in bedarf:
            continue
        # Was nie mit Startzeit gemeldet wurde, verschwindet auch nicht.
        if not (an[name] or {}).get("seit"):
            continue
        raus.append(f"{name} laeuft nicht mehr.")

    # Dienste, die laufen sollen und nicht laufen.
    da = alt.get("dienste") or {}
    dn = neu.get("dienste") or {}
    if da.get("aus_roh") is not None:
        # Ohne Rohmessung im Vorher gibt es nichts zu vergleichen - derselbe
        # erste Blick wie oben. Das greift genau einmal, beim Umstieg auf die
        # Entprellung: die alte haus.json kennt das Feld noch nicht.
        ad = set(da.get("sollen_aber_aus") or [])
        nd = set(dn.get("sollen_aber_aus") or [])
        bedarf = set(dn.get("bedarf") or [])

        # Wer gerade als Bedarfsdienst erkannt wurde, wird einmal genannt -
        # und danach nie wieder. Ein Dienst, der stillschweigend aus der
        # Meldung faellt, sieht aus wie einer, der nie ein Problem hatte.
        for name in sorted(bedarf - set(da.get("bedarf") or [])):
            raus.append(f"Der Dienst {name} kommt und geht von selbst; ich "
                        f"nehme ihn als Bedarfsdienst und melde ihn nicht "
                        f"mehr.")

        for name in sorted(nd - ad - bedarf):
            raus.append(f"Der Dienst {name} soll automatisch laufen, tut es "
                        f"aber nicht.")
        for name in sorted(ad - nd - bedarf):
            raus.append(f"Der Dienst {name} laeuft wieder.")

    # GPU: der Speicher in Gigabyte-Stufen. Die Auslastung schwankt zu stark,
    # um sie zu vergleichen - ein Blick darauf sagt nur, was gerade ist.
    ag, ng = alt.get("gpu") or {}, neu.get("gpu") or {}
    if _sprung(ag.get("speicher_mb"), ng.get("speicher_mb"),
               1024 * STUFE_GPU_SPEICHER_GB):
        raus.append(f"Auf der Grafikkarte sind {ng.get('speicher_mb')} von "
                    f"{ng.get('speicher_gesamt_mb')} MB belegt, vorher "
                    f"{ag.get('speicher_mb')}.")
    return raus


def _prozent_frei(m: dict):
    try:
        return float(m["ram_frei_gb"]) / float(m["ram_gesamt_gb"]) * 100.0
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


def _ohne_junge(neu: dict, jung_s: int = PROZESS_JUNG_S) -> dict:
    """Eben erst gestartete Namen gar nicht erst ins Vorher schreiben.

    veraenderungen() meldet einen jungen Prozess nicht als "laeuft" - aber
    schreiben() legte ihn trotzdem in haus.json ab. Die Sperre wirkte also
    nur beim Auftauchen, nicht beim Verschwinden. Ein Aufruf, der zwei
    Sekunden lebt und zufaellig einmal in die Messung geriet, stand damit im
    Vorher, und die naechste Messung meldete "python.exe laeuft nicht mehr".

    Das ist derselbe Fehlalarm, den Beobachter._dienste() erzeugt hat: am
    12.09. zwischen 11:23 und 11:36 vier Funde und zwei Auftraege an Claude,
    ohne dass etwas passiert war. Quelle waren die haus.py-Testlaeufe selbst
    und die Messbefehle, die danach suchten.

    Was nie als vorhanden galt, kann auch nicht verschwinden. Ein echter
    neuer Dienst wird dadurch einen Durchgang spaeter gemeldet - beim
    naechsten Blick ist er alt genug.
    """
    jetzt_ = time.time()
    behalten = []
    for p in neu.get("namen") or []:
        try:
            if p.get("seit") is not None \
                    and jetzt_ - float(p["seit"]) < jung_s:
                continue
        except (TypeError, ValueError):
            pass
        behalten.append(p)
    return {**neu, "namen": behalten}


def _zwei_blicke(roh_neu: set, roh_alt: set, war: set, erster: bool) -> set:
    """Die Entprellung selbst, ohne zu wissen, woran sie hängt.

    Sie steht zweimal im Modul: einmal fuer Prozessnamen, einmal fuer
    Dienste, die laufen sollen und nicht laufen. Zweimal derselbe Fehlalarm,
    zweimal dieselbe Antwort - deshalb hier nur einmal geschrieben. Wer sie
    aendert, aendert beide, und das ist gewollt.

    Zweimal hintereinander gesehen heisst da. Einmal gefehlt ist noch kein
    Weg - erst zweimal.
    """
    if erster:
        # Der erste Blick stellt fest, er vergleicht nicht.
        return set(roh_neu)
    return (roh_neu & roh_alt) | (war & (roh_neu | roh_alt))


def _dienste_bestaetigt(alt: dict, neu: dict) -> dict:
    """Dieselbe Entprellung wie bei den Prozessnamen, anderes Feld.

    Gemessen am 12.09. im Journal, vier Zeilen in zwei Minuten:

        12:05:56  Der Dienst GoogleUpdaterService152.0.7933.0 laeuft wieder.
        12:06:58  Der Dienst GoogleUpdaterService152.0.7933.0 soll
                  automatisch laufen, tut es aber nicht.

    Ein Updater, der eine Minute lebt, erzeugt zwei Meldungen: eine beim
    Starten, eine beim Aufhoeren. Nichts davon ist ein Ereignis - das IST
    ein Updater. `sollen_aber_aus` war das letzte Feld ohne Entprellung.

    Dazu die zweite Haelfte, die eine Entprellung allein nicht loest: Laeuft
    der Updater einmal drei Minuten, ueberlebt er zwei Blicke und meldet sich
    trotzdem. Ein Dienst, der KOMMT UND GEHT, ist kein ausgefallener Dienst,
    sondern einer, der bei Bedarf startet. Das laesst sich messen statt
    raten: Wir zaehlen mit, wie oft ein Dienst den bestaetigten Zustand
    wechselt. Ab DIENST_WECHSEL_BIS_BEDARF gilt er als Bedarfsdienst und
    faellt aus der Meldung - einmal angesagt, damit es nicht still geschieht.

    Bewusst NICHT ueber eine Namensliste: `gupdate` und `edgeupdate` stehen
    schon in der Messabfrage, `GoogleUpdaterService152.0.7933.0` nicht - die
    Versionsnummer steckt im Namen, die Liste ist beim naechsten Update
    veraltet. Was der Rechner tut, weiss der Rechner besser als wir.
    """
    d_alt = alt.get("dienste") or {}
    d_neu = dict(neu.get("dienste") or {})

    roh_neu = set(d_neu.get("sollen_aber_aus") or [])
    roh_alt = set(d_alt.get("aus_roh") or [])
    war = set(d_alt.get("sollen_aber_aus") or [])

    # Auf den WERT geprueft, nicht auf den Schluessel: eine haus.json von
    # vor dieser Aenderung hat das Feld gar nicht, eine halb geschriebene
    # hat es mit None. Beide Male gibt es keine Rohmessung zu vergleichen.
    bestaetigt = _zwei_blicke(roh_neu, roh_alt, war,
                              erster=d_alt.get("aus_roh") is None)

    # Jeder Wechsel des bestaetigten Zustands ist genau die Meldung, die
    # veraenderungen() gleich schreiben wuerde. Wir zaehlen also Meldungen,
    # nicht Messungen - Flackern unterhalb der Entprellung zaehlt nicht mit.
    wechsel = dict(d_alt.get("wechsel") or {})
    if d_alt.get("aus_roh") is not None:
        for name in bestaetigt ^ war:
            wechsel[name] = wechsel.get(name, 0) + 1

    d_neu["sollen_aber_aus"] = sorted(bestaetigt)
    d_neu["aus_roh"] = sorted(roh_neu)
    d_neu["wechsel"] = wechsel
    d_neu["bedarf"] = sorted(n for n, z in wechsel.items()
                             if z >= DIENST_WECHSEL_BIS_BEDARF)
    return {**neu, "dienste": d_neu}


def _bestaetigt(alt: dict, neu: dict) -> dict:
    """Nur was zwei Messungen ueberdauert, gilt als da - und als weg.

    _ohne_junge() faengt den Zwei-Sekunden-Aufruf. Es faengt NICHT den, der
    fuenfundzwanzig Sekunden lebt: der ist beim Auftauchen alt genug, steht im
    Vorher, und die naechste Messung meldet ihn als verschwunden.

    Gemessen am 12.09.: 44 Journalzeilen in 90 Minuten ueber python.exe, und
    daraus ein Antrag an Calvin um 11:54, den er um 11:54:50 genehmigt hat -
    fuer ein Phantom. Jede SSH-Messung vom Mac und jeder Testlauf von hier
    erzeugt kurz ein python.exe; er bemerkte es, prueft, es verschwindet, er
    bemerkt das Verschwinden, und faengt von vorn an.

    Die Regel: Ein Name muss in ZWEI Messungen hintereinander vorkommen, um
    als laufend zu gelten, und in zwei hintereinander fehlen, um als weg zu
    gelten. Das ist dieselbe Entprellung, die Beobachter._dienste() bekommen
    hat, und derselbe Grund, aus dem die Werkstatt aus der Dateibeobachtung
    ausgenommen ist: Was wir beide beim Arbeiten erzeugen, ist keine
    Veraenderung der Lage.

    Ein echter neuer Dienst wird dadurch eine Minute spaeter gemeldet.
    """
    roh_neu = {p.get("name"): p for p in (neu.get("namen") or [])}
    roh_alt = {p.get("name") for p in (alt.get("namen_roh") or [])}
    war = {p.get("name") for p in (alt.get("namen") or [])}

    bestaetigt = _zwei_blicke(
        set(roh_neu), roh_alt, war,
        erster=not alt.get("namen_roh") and not alt.get("namen"))

    # Waehrend der Gnadenmessung - einmal gefehlt, aber noch nicht weg -
    # steht der Eintrag nicht mehr in der aktuellen Messung. Er muss
    # trotzdem in "namen" bleiben, sonst meldet veraenderungen() ihn genau
    # dann als verschwunden, wovor die Gnadenfrist schuetzen soll.
    vorher = {p.get("name"): p for p in (alt.get("namen") or [])}
    bekannt = dict(vorher)
    bekannt.update(roh_neu)

    # Ein Neustart ist auch ein Kommen und Gehen - nur zu schnell, um
    # zwischen zwei Blicke zu passen. Calvin hat "msedge wurde neu gestartet"
    # und "OneDrive.Sync.Service neu gestartet" in derselben Liste gezaehlt
    # wie smartscreen, und zu Recht: Beide starten staendig Unterprozesse neu.
    # Wuerde nur der bestaetigte Wechsel zaehlen, blieben diese drei Zeilen
    # uebrig, nachdem zwoelf verschwunden sind.
    neustarts = set()
    for name in bestaetigt & war:
        neu_seit = (roh_neu.get(name) or {}).get("seit")
        alt_seit = (vorher.get(name) or {}).get("seit")
        try:
            if neu_seit and alt_seit \
                    and float(neu_seit) - float(alt_seit) > NEUSTART_SPRUNG_S:
                neustarts.add(name)
        except (TypeError, ValueError):
            pass

    wechsel, bedarf = _bedarf_zaehlen(alt, bestaetigt, war, neustarts,
                                      erster=not alt.get("namen_roh")
                                      and not alt.get("namen"))

    return {**neu,
            "namen": [bekannt[n] for n in sorted(bestaetigt) if n in bekannt],
            # Die Rohmessung wandert mit, damit der naechste Blick weiss, was
            # beim vorletzten Mal wirklich dastand.
            "namen_roh": list(roh_neu.values()),
            "namen_wechsel": wechsel,
            "namen_bedarf": bedarf}


def _bedarf_zaehlen(alt: dict, bestaetigt: set, war: set, neustarts: set,
                    erster: bool) -> tuple[dict, dict]:
    """Wer kommt und geht, ist ein Bedarfsdienst - gemessen, nicht benannt.

    Die Entprellung aus _bestaetigt() faengt den Kurzlaeufer. Sie faengt NICHT
    den, der sich regelmaessig richtig verhaelt: smartscreen lebt ein paar
    Minuten, ueberdauert zwei Blicke und wird zu Recht als "laeuft" erkannt.
    Gemeldet werden darf er trotzdem nicht, denn sein Kommen und Gehen IST
    sein Normalzustand. Gezaehlt hat das Calvin: zwoelf von einundzwanzig
    Beobachtungen waren smartscreen.

    Gezaehlt werden BESTAETIGTE Wechsel, also genau die Zeilen, die
    veraenderungen() schreiben wuerde - nicht die Rohmessungen. Flackern
    unterhalb der Entprellung zaehlt nicht zweimal.

    Das Fenster ist ein Tag (BEDARF_FENSTER_H), die Erkenntnis selbst bleibt.
    Das ist Absicht und die einzige Stelle, an der ich von Calvins Wortlaut
    abweiche: Wuerde auch die Einordnung verfallen, kaeme smartscreen jeden
    Tag einmal durch, bevor er wieder auffaellt - dreihundertfuenfundsechzig
    Zeilen im Jahr fuer eine Sache, die wir im September verstanden haben.
    Was er einmal begriffen hat, soll er behalten; "kommt und geht" ist eine
    Eigenschaft, kein Zustand.
    """
    jetzt_ = time.time()
    frueheste = jetzt_ - BEDARF_FENSTER_H * 3600

    wechsel = {}
    for name, stempel in (alt.get("namen_wechsel") or {}).items():
        frisch = [t for t in stempel if isinstance(t, (int, float))
                  and t >= frueheste]
        if frisch:
            wechsel[name] = frisch
    if not erster:
        for name in (bestaetigt ^ war) | set(neustarts):
            wechsel.setdefault(name, []).append(jetzt_)

    bedarf = dict(alt.get("namen_bedarf") or {})
    for name, stempel in wechsel.items():
        if len(stempel) >= DIENST_WECHSEL_BIS_BEDARF and name not in bedarf:
            bedarf[name] = jetzt_
    return wechsel, bedarf


def fortschreiben(pfad: Path = HAUS_DATEI) -> tuple[dict, list[str]]:
    """Einmal messen, mit dem Vorher vergleichen, das Neue festhalten."""
    alt = lesen(pfad)
    neu = bild()
    if not neu:
        return {}, []
    # Vor dem Vergleich UND vor dem Schreiben - sonst steht der Kurzlaeufer
    # im Vorher und verschwindet beim naechsten Mal.
    neu = _ohne_junge(neu)
    neu = _bestaetigt(alt, neu)
    neu = _dienste_bestaetigt(alt, neu)
    aenderungen = veraenderungen(alt, neu)
    schreiben(neu, pfad)
    return neu, aenderungen


# --------------------------------------------------------------- Ereignisse


# Das Windows-Ereignisprotokoll, nur lesend. Was hier steht, schreibt Windows
# ohnehin mit - wir fragen es nur ab. Kein Dienst wird eingerichtet, nichts
# mitgeschnitten, keine Datei angelegt.
#
# Die Kennungen:
#   6005/6006  Protokolldienst gestartet/beendet = hoch- und runtergefahren
#   6008       das letzte Herunterfahren war unerwartet
#   41         Kernel-Power: der Rechner ging aus, ohne sich abzumelden
#   1074       jemand hat Neustart oder Herunterfahren angestossen
#   7031/7034  ein Dienst ist unerwartet beendet worden
#   1000/1002  ein Programm ist abgestuerzt bzw. haengt
#   1033/1034  MsiInstaller: installiert / deinstalliert
# Drei Abfragen, nicht eine. Eine Kennung allein ist nicht eindeutig: Mit
# {LogName='System','Application'; Id=...,1033,...} kamen 13 Meldungen der
# Art "Die Richtliniendefinition ist doppelt vorhanden" als "Ein Programm
# wurde installiert" zurueck - dieselbe 1033, andere Quelle. Erst Quelle UND
# Kennung zusammen sagen, was ein Ereignis ist.
#
# Drei Abfragen in EINEM PowerShell-Aufruf kosten kaum mehr als eine; was
# kostet, ist das Starten der Sitzung.
_EREIGNISSE = r"""
$seit = (Get-Date).AddHours(-%(h)d)
function hole($h) {
  Get-WinEvent -FilterHashtable $h -MaxEvents %(n)d -ErrorAction SilentlyContinue
}
$e = @()
$e += hole @{LogName='System'; Id=6005,6006,6008,41,1074,7031,7034; StartTime=$seit}
$e += hole @{LogName='Application'; ProviderName='Application Error','Application Hang'; Id=1000,1002; StartTime=$seit}
$e += hole @{LogName='Application'; ProviderName='MsiInstaller'; Id=1033,1034; StartTime=$seit}
@($e | ForEach-Object {
    $m = ($_.Message -replace '\s+',' ')
    [pscustomobject]@{
      ts      = [math]::Round(($_.TimeCreated).ToUniversalTime().Subtract([datetime]'1970-01-01').TotalSeconds)
      id      = $_.Id
      quelle  = $_.ProviderName
      text    = $m.Substring(0, [Math]::Min(240, $m.Length))
    }}) | ConvertTo-Json -Depth 2 -Compress
"""

# Anmeldungen liegen im Sicherheitsprotokoll. Das ist oft nur mit erhoehten
# Rechten lesbar - faellt es aus, fehlt dieser eine Punkt und sonst nichts.
#
# LogonType 2 ist die Anmeldung an der Tastatur, 7 das Entsperren, 10 und 11
# Remotedesktop und zwischengespeicherte Anmeldung. Alles andere sind
# Dienstanmeldungen, und davon gibt es hunderte je Stunde.
#
# Der Filter muss fuer 4624 UND 4634 gelten. Beim ersten Lauf galt er nur
# fuer die Anmeldung, und dann standen in 48 Stunden 148 "Anmeldungen" - fast
# alle davon Abmeldungen von sshd_13268 und aehnlichen Dienstkonten. Das ist
# keine Auskunft darueber, wer am Rechner war, das ist Rauschen mit Uhrzeit.
_ANMELDUNGEN = r"""
$seit = (Get-Date).AddHours(-%(h)d)
@(Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4624,4634;
        StartTime=$seit} -MaxEvents %(n)d -ErrorAction SilentlyContinue |
  ForEach-Object {
    $x = [xml]$_.ToXml()
    $benutzer = ($x.Event.EventData.Data | Where-Object { $_.Name -eq 'TargetUserName' }).'#text'
    $art      = ($x.Event.EventData.Data | Where-Object { $_.Name -eq 'LogonType' }).'#text'
    if ($benutzer -and $benutzer -notmatch '\$$' -and
        $benutzer -notmatch '^(sshd_|DWM-|UMFD-)' -and
        $benutzer -notin @('SYSTEM','LOCAL SERVICE','NETWORK SERVICE','ANONYMOUS LOGON') -and
        $art -in @('2','7','10','11')) {
      [pscustomobject]@{
        ts       = [math]::Round(($_.TimeCreated).ToUniversalTime().Subtract([datetime]'1970-01-01').TotalSeconds)
        id       = $_.Id
        benutzer = $benutzer
        art      = $art
      }}}) | ConvertTo-Json -Depth 2 -Compress
"""

# Was die Kennungen in seiner Sprache heissen. Die Windows-Meldung selbst ist
# ein Absatz Amtsdeutsch; Calvin bekommt einen Satz.
_WAS = {
    6005: "Der Rechner ist hochgefahren",
    6006: "Der Rechner wurde heruntergefahren",
    6008: "Der Rechner ging unerwartet aus",
    41: "Der Rechner ging aus, ohne sich ordentlich abzumelden",
    1074: "Jemand hat einen Neustart oder das Herunterfahren angestossen",
    7031: "Ein Dienst ist unerwartet beendet worden",
    7034: "Ein Dienst ist unerwartet beendet worden",
    1000: "Ein Programm ist abgestuerzt",
    1002: "Ein Programm hat nicht mehr geantwortet",
    1033: "Ein Programm wurde installiert",
    1034: "Ein Programm wurde deinstalliert",
}


def _liste(d) -> list:
    if isinstance(d, dict):
        return [d]
    return d if isinstance(d, list) else []


# Worum es in der Windows-Meldung geht. Ohne das bleibt "Ein Programm ist
# abgestuerzt" eine Auskunft, mit der niemand etwas anfangen kann - und
# einundsiebzig Installationsmeldungen lassen sich nicht zu einem Vorgang
# zusammenfassen, wenn man nicht weiss, welches Produkt gemeint ist.
_GEGENSTAND = (
    re.compile(r"Fehlerhafter Anwendungsname:\s*([^,]+)"),
    re.compile(r"Faulting application name:\s*([^,]+)"),
    # Bis zur Produktversion, nicht bis zum ersten Punkt: Aus "Produktname:
    # Microsoft .NET Runtime. Produktversion: 8.0.1." wurde sonst
    # "Microsoft", und siebenundvierzig verschiedene Pakete hiessen gleich.
    re.compile(r"Produktname:\s*(.+?)\.\s*Produktversion:"),
    re.compile(r"Product Name:\s*(.+?)\.\s*Product Version:"),
    re.compile(r"Der Dienst \"?([^\"]+?)\"? wurde unerwartet beendet"),
    re.compile(r"The ([^ ]+) service terminated unexpectedly"),
)


def _gegenstand(text: str) -> str:
    for ausdruck in _GEGENSTAND:
        t = ausdruck.search(text or "")
        if t:
            return t.group(1).strip()
    return ""


def ereignisse(stunden: int = 24, hoechstens: int = 300) -> list[dict]:
    """Was Windows selbst mitgeschrieben hat: hoch, runter, abgestuerzt,
    installiert, an- und abgemeldet.

    Nicht im Minutentakt und nicht ins Journal gespiegelt - das Protokoll IST
    der Speicher. Gefragt wird, wenn jemand wissen will, was passiert ist.
    """
    raus = []
    for e in _liste(_ps_json(_EREIGNISSE % {"h": stunden, "n": hoechstens}, 90)):
        kennung = e.get("id")
        gegenstand = _gegenstand(e.get("text") or "")
        was = _WAS.get(kennung, "Ereignis %s" % kennung)
        # "Ein Programm ist abgestuerzt" ist keine Auskunft.
        # "llama-server.exe ist abgestuerzt" ist eine.
        if gegenstand and kennung in (1000, 1002, 7031, 7034):
            was = f"{gegenstand} {was.split(' ist ')[-1] if ' ist ' in was else was}"
        elif gegenstand and kennung in (1033, 1034):
            was = (f"{gegenstand} wurde "
                   f"{'installiert' if kennung == 1033 else 'entfernt'}")
        raus.append({
            "ts": e.get("ts"),
            "art": ("neustart" if kennung in (6005, 6006, 6008, 41, 1074)
                    else "installiert" if kennung in (1033, 1034)
                    else "absturz"),
            "was": was,
            "gegenstand": gegenstand,
            # Die Windows-Meldung bleibt dabei. Wer genauer wissen will, was
            # los war, findet es nur dort.
            "windows": e.get("text"),
            "quelle": e.get("quelle"),
        })
    for e in _liste(_ps_json(_ANMELDUNGEN % {"h": stunden, "n": hoechstens},
                             90)):
        raus.append({
            "ts": e.get("ts"),
            "art": "anmeldung",
            "was": ("%s hat sich angemeldet" % e.get("benutzer")
                    if e.get("id") == 4624
                    else "%s hat sich abgemeldet" % e.get("benutzer")),
            "gegenstand": e.get("benutzer") or "",
            "windows": None,
            "quelle": "Security",
        })
    raus.sort(key=lambda e: e.get("ts") or 0)
    return raus


def programm_unterschiede(alt: list[dict], neu: list[dict]) -> list[str]:
    """Was installiert, entfernt oder aktualisiert wurde.

    Ohne ein Vorher gibt es nichts zu melden - er zaehlt nicht beim ersten
    Blick alle 180 installierten Programme auf.
    """
    if not alt:
        return []
    a = {p.get("name"): p.get("fassung") for p in alt if p.get("name")}
    n = {p.get("name"): p.get("fassung") for p in neu if p.get("name")}
    raus = []
    for name in sorted(set(n) - set(a)):
        raus.append(f"{name} wurde installiert"
                    + (f", Fassung {n[name]}." if n[name] else "."))
    for name in sorted(set(a) - set(n)):
        raus.append(f"{name} wurde deinstalliert.")
    for name in sorted(set(a) & set(n)):
        if a[name] != n[name] and a[name] and n[name]:
            raus.append(f"{name} wurde von Fassung {a[name]} auf {n[name]} "
                        f"aktualisiert.")
    return raus


# ------------------------------------------------------------------ Auskunft


def satz(d: dict | None = None) -> str:
    """Ein Satz ueber den Zustand des Hauses - fuer "was laeuft gerade".

    Ohne Modell. Ein Sprachmodell ist kein Messgeraet; solche Fakten gehoeren
    eingesetzt, nicht erfragt. Dieselbe Regel wie bei lage.netz_antwort().
    """
    d = d if d is not None else bild()
    m = d.get("maschine") or {}
    g = d.get("gpu") or {}
    teile = []
    if m.get("cpu_kerne"):
        # Nie "bei None Prozent" sagen. Fehlt die Messung, nennt er die
        # Kerne und schweigt ueber die Last - eine fehlende Zahl ist kein
        # Grund, eine zu behaupten.
        teile.append(f"{m.get('cpu_kerne')} Kerne bei "
                     f"{m.get('cpu_last')} Prozent"
                     if m.get("cpu_last") is not None
                     else f"{m.get('cpu_kerne')} Kerne")
    if m.get("ram_gesamt_gb"):
        teile.append(f"{m.get('ram_frei_gb')} von {m.get('ram_gesamt_gb')} GB "
                     f"Arbeitsspeicher frei")
    if g.get("last_prozent") is not None:
        teile.append(f"die Grafikkarte bei {g.get('last_prozent')} Prozent "
                     f"und {g.get('temperatur_c')} Grad")
    if m.get("hochgefahren"):
        teile.append(f"der Rechner laeuft seit "
                     f"{_dauer(time.time() - float(m['hochgefahren']))}")
    return ", ".join(teile) + "." if teile else "Ich kann das Haus gerade nicht messen."


# Welche Frage welchen Teil des Hauses meint. Der Reihe nach geprueft, der
# erste Treffer gewinnt - deshalb steht das Genaue vor dem Allgemeinen.
#
# Grund fuer diese Tabelle: Vorher gab es nur satz(), und auf JEDE Hausfrage
# kam die ganze Zustandszeile. "Wie lange laeuft der Rechner schon?" wurde mit
# Kernen, Arbeitsspeicher und Temperatur beantwortet. Eine abrufbare Liste ist
# noch keine Auskunft - er muss auswaehlen, was zur Frage passt.
_TEILE = (
    ("prozesse", r"prozess|programme|was\s*l(ä|ae)uft|wer\s*(belegt|braucht|"
                 r"frisst|zieht)|besch(ä|ae)ftigt"),
    ("laufzeit", r"wie\s*lange|seit\s*wann|hochgefahren|laufzeit|"
                 r"l(ä|ae)uft\s*(der|dein)\s*rechner|neu\s*gestartet"),
    ("temperatur", r"temperatur|wie\s*warm|wie\s*hei(ß|ss)|grad\b"),
    ("gpu", r"grafikkarte|\bgpu\b|grafik\b"),
    ("ram", r"arbeitsspeicher|\bram\b|speicher\s*(frei|belegt)"),
    ("cpu", r"\bcpu\b|prozessor|\bkerne\b|auslastung|ausgelastet|belastet"),
    ("platten", r"laufwerk|festplatte|\bplatte\b|speicherplatz"),
)


def antwort(frage: str, d: dict | None = None) -> str | None:
    """Die Antwort auf GENAU diese Frage - nicht die ganze Zustandszeile.

    Ohne Modell, wie lage.netz_antwort(). Gibt None zurueck, wenn die Frage
    nichts mit dem Haus zu tun hat.
    """
    f = str(frage or "")
    welcher = None
    for name, ausdruck in _TEILE:
        if re.search(ausdruck, f, re.IGNORECASE):
            welcher = name
            break
    if welcher is None:
        return None

    d = d if d is not None else bild()
    m = d.get("maschine") or {}
    g = d.get("gpu") or {}

    if welcher == "prozesse":
        # Zwei Namen und eine Groessenordnung. Der Rest kommt auf Nachfrage -
        # dem Modell steht er als Kontext zur Verfuegung (gespraech.py,
        # "groesste_prozesse").
        #
        # OHNE ZAHL DER UEBRIGEN, und das ist kein Vergessen: `prozesse` ist
        # die Bestenliste der zwoelf groessten (siehe veraendert(), "ueber
        # ALLE Namen, nicht ueber die Bestenliste"), nach Namen
        # zusammengezaehlt neun. "Sieben weitere sind kleiner" hiesse, der
        # Rechner habe neun Prozesse - er hat Hunderte. Eine Zahl, die nur
        # die eigene Liste zaehlt und wie eine Gesamtzahl klingt, ist
        # schlimmer als keine.
        alle = nach_namen(d)
        if not alle:
            return "Ich sehe gerade keine Prozesse."
        satz_teil = f"Am meisten Speicher belegen {groesste(d)}."
        if len(alle) > NAMEN_GESPROCHEN:
            satz_teil += " Dahinter wird es kleiner."
        return satz_teil
    if welcher == "laufzeit":
        if not m.get("hochgefahren"):
            return None
        return (f"Der Rechner laeuft seit "
                f"{_dauer(time.time() - float(m['hochgefahren']))}, "
                f"hochgefahren um {_uhr(m['hochgefahren'])}.")
    if welcher == "temperatur":
        if g.get("temperatur_c") is None:
            return None
        return f"Die Grafikkarte ist {g['temperatur_c']} Grad warm."
    if welcher == "gpu":
        if not g:
            return None
        teile = [f"Die Grafikkarte ist eine {g.get('name')}"]
        if g.get("last_prozent") is not None:
            teile.append(f"gerade zu {g['last_prozent']} Prozent ausgelastet")
        if g.get("speicher_mb") is not None:
            teile.append(f"{g['speicher_mb']} von "
                         f"{g.get('speicher_gesamt_mb')} MB belegt")
        if g.get("temperatur_c") is not None:
            teile.append(f"{g['temperatur_c']} Grad warm")
        return ", ".join(teile) + "."
    if welcher == "ram":
        if not m.get("ram_gesamt_gb"):
            return None
        return (f"Von {m['ram_gesamt_gb']} GB Arbeitsspeicher sind "
                f"{m.get('ram_frei_gb')} GB frei.")
    if welcher == "cpu":
        if not m.get("cpu_kerne"):
            return None
        if m.get("cpu_last") is None:
            return (f"Der Prozessor hat {m['cpu_kerne']} Kerne. Wie stark er "
                    f"gerade ausgelastet ist, kann ich nicht messen.")
        return (f"Der Prozessor hat {m['cpu_kerne']} Kerne und ist gerade zu "
                f"{m['cpu_last']} Prozent ausgelastet.")
    if welcher == "platten":
        p = d.get("platten") or []
        if not p:
            return None
        return "Auf " + ", ".join(
            f"{x.get('laufwerk')} sind {x.get('frei_gb')} von "
            f"{x.get('gesamt_gb')} GB frei" for x in p) + "."
    return None


# So viele Namen kommen in eine gesprochene Antwort. Der Mac hat am 12.09.
# gemessen, was fuenf ergeben: "Memory Compression mit 1394 MB, llama-server
# mit 1073 MB, explorer mit 790 MB, llama-server mit 643 MB, chrome mit 565
# MB" - fuenf Posten und zwei Zahlen je Posten in einem Atemzug. Vorgelesen
# merkt sich das niemand.
NAMEN_GESPROCHEN = 2
# Fuer den Modellkontext dagegen mehr: Dort ist es kein Atemzug, sondern
# Stoff fuer eine Nachfrage.
NAMEN_KONTEXT = 6

_ZAHLWORT_KLEIN = {2: "zwei", 3: "drei", 4: "vier", 5: "fünf", 6: "sechs",
                   7: "sieben", 8: "acht", 9: "neun", 10: "zehn",
                   11: "elf", 12: "zwölf"}


def _menge(mb: float) -> str:
    """Eine Groessenordnung, keine Stelle zu viel.

    "1394 MB" ist eine Messung, "1,4 GB" ist eine Auskunft. Vorgelesen zaehlt
    der Unterschied: Vier Ziffern hintereinander sind nicht hoerbar.
    """
    if mb >= 1000:
        # Ohne die Null hinter dem Komma: 1032 MB wurden zu "1,0 GB", und
        # vorgelesen ist das "eins komma null Gigabyte". "1 GB" ist dieselbe
        # Auskunft in einem Wort.
        gb = f"{mb / 1024:.1f}".rstrip("0").rstrip(".")
        return gb.replace(".", ",") + " GB"
    return f"{int(round(mb))} MB"


def nach_namen(d: dict | None = None) -> list[dict]:
    """Prozesse mit demselben Namen zusammengezaehlt.

    Der Mac am 12.09.: llama-server stand zweimal in derselben Antwort, mit
    1073 und 643 MB. Das ist nicht nur haesslich, es macht die Auskunft
    FALSCH: zusammen sind es 1716 MB, also mehr als die 1394 von Memory
    Compression, die davor als groesster Posten genannt wurden. Wer gleiche
    Namen nicht zusammenzaehlt, nennt den zweitgroessten zuerst.
    """
    d = d if d is not None else bild()
    zusammen: dict[str, dict] = {}
    for x in (d.get("prozesse") or []):
        name = str(x.get("name") or "?")
        e = zusammen.setdefault(name, {"name": name, "ram_mb": 0.0,
                                       "anzahl": 0})
        try:
            e["ram_mb"] += float(x.get("ram_mb") or 0)
        except (TypeError, ValueError):
            pass
        e["anzahl"] += 1
    return sorted(zusammen.values(), key=lambda e: -e["ram_mb"])


def groesste(d: dict | None = None, n: int = NAMEN_GESPROCHEN) -> str:
    """Wer belegt den Speicher? Ebenfalls ohne Modell.

    Zusammengezaehlt und auf `n` Namen gekuerzt. Mehrere Prozesse desselben
    Namens werden als solche benannt ("in zwei Prozessen") - sonst sieht eine
    zusammengezaehlte Zahl aus wie eine einzelne Messung.
    """
    d = d if d is not None else bild()
    alle = nach_namen(d)
    if not alle:
        return "Ich sehe gerade keine Prozesse."
    teile = []
    for e in alle[:n]:
        stueck = f"{e['name']} mit {_menge(e['ram_mb'])}"
        if e["anzahl"] > 1:
            wort = _ZAHLWORT_KLEIN.get(e["anzahl"], str(e["anzahl"]))
            stueck += f" in {wort} Prozessen"
        teile.append(stueck)
    if len(teile) == 1:
        return teile[0]
    # "und" vor dem letzten, nicht noch ein Komma: Eine Aufzaehlung mit
    # Kommas bis zum Ende klingt vorgelesen wie ein Formular.
    return ", ".join(teile[:-1]) + " und " + teile[-1]


def main() -> int:
    """python haus.py - messen, vergleichen, aber nichts festschreiben."""
    t0 = time.time()
    neu = bild()
    dauer = round(time.time() - t0, 1)
    if not neu:
        print("Keine Messung moeglich.")
        return 1
    m = neu.get("maschine") or {}
    print(f"{m.get('rechner')} - {m.get('windows')}")
    print(f"{m.get('cpu_name')}")
    print(f"\n{satz(neu)}\n")
    print("Platten:")
    for p in neu.get("platten") or []:
        voll = 100 - round(float(p.get("frei_gb", 0))
                           / max(float(p.get("gesamt_gb", 1)), 1) * 100)
        print(f"  {p.get('laufwerk')} {p.get('name') or ''} "
              f"{p.get('frei_gb')} von {p.get('gesamt_gb')} GB frei "
              f"({voll} Prozent voll)")
    print(f"\nDie {len(neu.get('prozesse') or [])} groessten Prozesse:")
    for p in neu.get("prozesse") or []:
        print(f"  {p.get('name'):24} PID {str(p.get('pid')):>6}  "
              f"{str(p.get('ram_mb')):>6} MB  {str(p.get('cpu_s')):>8} s CPU  "
              f"seit {_uhr(p.get('seit'))}")
    d = neu.get("dienste") or {}
    print(f"\nDienste: {d.get('laufen')} von {d.get('insgesamt')} laufen")
    aus = d.get("sollen_aber_aus") or []
    print(f"  sollen automatisch laufen, tun es nicht: "
          f"{', '.join(aus) if aus else 'keiner'}")

    alt = lesen()
    if alt:
        aenderungen = veraenderungen(alt, neu)
        print(f"\nSeit der letzten Messung ({_uhr(alt.get('ts'))}):")
        for z in aenderungen or ["  (nichts, was eine Stufe ueberschritten hat)"]:
            print(f"  {z}")
    else:
        print("\n(noch kein Vorher - der erste Blick stellt fest, "
              "er vergleicht nicht)")
    print(f"\nGemessen in {dauer} s. Nichts geschrieben.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
