# Legt die geplante Aufgabe "iris Bewohner" an - Start bei der Anmeldung,
# ohne Konsolenfenster. Braucht KEINE Administratorrechte, weil sie nur fuer
# den angemeldeten Benutzer gilt.
#
#   powershell -ExecutionPolicy Bypass -File aufgabe-einrichten.ps1
#   powershell -ExecutionPolicy Bypass -File aufgabe-einrichten.ps1 -Entfernen

param([switch]$Entfernen)

$Name    = 'iris Bewohner'
$Pythonw = "$env:USERPROFILE\tts-test\venv\Scripts\pythonw.exe"
$Skript  = "$env:USERPROFILE\mcp-test\bewohner.py"
$Ordner  = "$env:USERPROFILE\mcp-test"

if ($Entfernen) {
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Aufgabe '$Name' entfernt."
    return
}

foreach ($p in $Pythonw, $Skript) {
    if (-not (Test-Path $p)) { throw "Nicht gefunden: $p" }
}

# -X utf8 ist Pflicht: pythonw hat sonst keine UTF-8-Ausgabe, und ein print
# mit Umlaut beendet den Vorgang mit UnicodeEncodeError.
$aktion = New-ScheduledTaskAction -Execute $Pythonw `
                                  -Argument "-X utf8 `"$Skript`"" `
                                  -WorkingDirectory $Ordner
$ausloeser = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Kein Fensterschliessen bei Akkubetrieb, kein Zeitlimit, Neustart bei Fehler.
$einstellungen = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew -StartWhenAvailable

Register-ScheduledTask -TaskName $Name -Action $aktion -Trigger $ausloeser `
    -Settings $einstellungen -Description 'Der Bewohner - laeuft still im Hintergrund.' `
    -Force | Out-Null

$t = Get-ScheduledTask -TaskName $Name
Write-Host "Aufgabe '$Name' angelegt."
Write-Host "  Programm : $Pythonw"
Write-Host "  Skript   : $Skript"
Write-Host "  Start    : bei der Anmeldung von $env:USERNAME"
Write-Host "  Zustand  : $($t.State)"
Write-Host ''
Write-Host 'Jetzt starten:  Start-ScheduledTask -TaskName "iris Bewohner"'
Write-Host 'Anhalten     :  Stop-ScheduledTask  -TaskName "iris Bewohner"'
