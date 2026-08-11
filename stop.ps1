# Al-Karama LIS - stop the background server (PowerShell version, no VBScript)
$ErrorActionPreference = "SilentlyContinue"
$AppDir = $PSScriptRoot
$PidFile = Join-Path $AppDir "server.pid"

function Show-Msg($text) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($text, "Al-Karama LIS") | Out-Null
}

$stopped = $false
if (Test-Path $PidFile) {
    $savedPid = (Get-Content $PidFile -TotalCount 1).Trim()
    if ($savedPid) {
        $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -match "python") {
            Stop-Process -Id $savedPid -Force
            $stopped = $true
        }
    }
    Remove-Item $PidFile -Force
}

if ($stopped) { Show-Msg "تم ايقاف البرنامج." }
else { Show-Msg "البرنامج مو شغال حاليا (او انسكرت اصلا)." }
