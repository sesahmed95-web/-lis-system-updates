; Inno Setup script - Lab System
; 1) run build.bat first   2) open this file in Inno Setup   3) Ctrl+F9

#define MyAppName "Lab System"
#define MyAppVersion "38"
#define MyAppExe "LabSystem.exe"

[Setup]
AppId={{69721C32-7476-41A8-A602-E38D2B697BD1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName=C:\LabSystem
DefaultGroupName={#MyAppName}
PrivilegesRequired=admin
OutputDir=installer_output
OutputBaseFilename=LabSystem_Setup
SetupIconFile=icon\lab-icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
CloseApplications=force

[Dirs]
; the program writes lis.db, uploads and logs inside its own folder
Name: "{app}"; Permissions: users-modify

[Files]
Source: "dist\LabSystem\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "start_lab.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "stop_lab.bat"; DestDir: "{app}"; Flags: ignoreversion
; optional per-client settings: put portal_preset.json (made by tools\make_portal_preset.py) NEXT TO LabSystem_Setup.exe;
; the installer copies it into the app folder and the program applies it on first start (portal URL/key, lab name...)
Source: "{src}\portal_preset.json"; DestDir: "{app}"; Flags: external skipifsourcedoesntexist ignoreversion

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\start_lab.vbs"""; IconFilename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
Name: "{group}\{#MyAppName}"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\start_lab.vbs"""; IconFilename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
Name: "{group}\Stop {#MyAppName}"; Filename: "{app}\stop_lab.bat"; IconFilename: "{app}\{#MyAppExe}"; Flags: runminimized
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
; open port 9090 so other lab PCs can connect on the local network
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Lab System 9090"" dir=in action=allow protocol=TCP localport=9090"; Flags: runhidden
Filename: "{sys}\wscript.exe"; Parameters: """{app}\start_lab.vbs"""; Description: "Start Lab System now"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Lab System 9090"""; Flags: runhidden
