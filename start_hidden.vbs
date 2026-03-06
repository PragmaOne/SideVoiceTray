Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonwPath = baseDir & "\.venv\Scripts\pythonw.exe"
runPywPath = baseDir & "\run.pyw"
startBatPath = baseDir & "\start.bat"

shell.CurrentDirectory = baseDir

If fso.FileExists(pythonwPath) And fso.FileExists(runPywPath) Then
  shell.Run """" & pythonwPath & """ """ & runPywPath & """", 0, False
Else
  shell.Run "cmd.exe /c """ & startBatPath & """", 0, False
End If
