' Lab System launcher - starts the server hidden (no black window), waits until it is ready, then opens the browser.
Option Explicit
Dim fso, sh, dir, wmi, procs, i
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir

Function ServerUp()
  Dim h
  On Error Resume Next
  Set h = CreateObject("MSXML2.ServerXMLHTTP.6.0")
  h.setTimeouts 1000, 1000, 1000, 1000
  h.open "GET", "http://127.0.0.1:9090/", False
  h.send
  ServerUp = (Err.Number = 0)
  Err.Clear
  On Error GoTo 0
End Function

Set wmi = GetObject("winmgmts:\\.\root\cimv2")
Set procs = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name='LabSystem.exe'")
If procs.Count = 0 Then
  sh.Run Chr(34) & dir & "\LabSystem.exe" & Chr(34), 0, False
End If

For i = 1 To 60
  If ServerUp() Then Exit For
  WScript.Sleep 1000
Next

Dim edge
edge = ""
On Error Resume Next
edge = sh.RegRead("HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe\")
Err.Clear
On Error GoTo 0

If edge <> "" Then
  If fso.FileExists(edge) Then
    ' Edge app mode: own window, no tabs, no address bar
    sh.Run Chr(34) & edge & Chr(34) & " --app=http://127.0.0.1:9090 --start-maximized", 1, False
    WScript.Quit
  End If
End If
' fallback: default browser
sh.Run "http://127.0.0.1:9090"
