# Al-Karama LIS - one-time installer.
# Copies the program to a permanent folder and creates ONE desktop icon.
# After this runs once, the source folder/zip can be deleted — everything
# the program needs lives in $Dest from now on.

$ErrorActionPreference = "Stop"
$Source = $PSScriptRoot
$Dest   = Join-Path $env:LOCALAPPDATA "HematologistLIS"

Write-Host "Installing to $Dest ..."
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Copy-Item -Path (Join-Path $Source '*') -Destination $Dest -Recurse -Force -Exclude @('install.ps1','install.bat')

$WshShell = New-Object -ComObject WScript.Shell
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) "برنامج مختبر أمراض الدم.lnk"
$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "powershell.exe"
$runPath = Join-Path $Dest 'run.ps1'
$shortcut.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $runPath + '"'
$shortcut.WindowStyle = 7
$shortcut.WorkingDirectory = $Dest
$shortcut.Description = "برنامج مختبر أمراض الدم التخصصي"
$iconPath = Join-Path $Dest 'static\icon\lab-icon.ico'
if (Test-Path $iconPath) {
    $shortcut.IconLocation = $iconPath
}
$shortcut.Save()

Write-Host ""
Write-Host "تم التثبيت بنجاح."
Write-Host "راح تلكى ايقونة جديدة على سطح المكتب اسمها: برنامج مختبر أمراض الدم"
Write-Host "من الحين وطالع، افتح البرنامج من هذه الايقونة بس."
