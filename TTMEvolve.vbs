Option Explicit

Dim shell, fso, root, launcher, command, logDir, logFile
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = fso.BuildPath(root, "start-tauri.bat")
logDir = fso.BuildPath(root, "logs\gui")
If Not fso.FolderExists(logDir) Then
  If Not fso.FolderExists(fso.BuildPath(root, "logs")) Then
    fso.CreateFolder(fso.BuildPath(root, "logs"))
  End If
  fso.CreateFolder(logDir)
End If
logFile = fso.BuildPath(logDir, "launcher.log")

If Not fso.FileExists(launcher) Then
  MsgBox "start-tauri.bat not found: " & launcher, vbCritical, "TTMEvolve"
  WScript.Quit 1
End If

shell.CurrentDirectory = root
AppendLog logFile, "launch gui: " & launcher
command = Chr(34) & launcher & Chr(34)
shell.Run command, 0, False

Sub AppendLog(path, text)
  Dim file
  Set file = fso.OpenTextFile(path, 8, True)
  file.WriteLine Now & " " & text
  file.Close
End Sub
