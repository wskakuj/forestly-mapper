' Forestly Mapper - ukladanie opisow na mapach GEO-MAP.
' Uruchamia program BEZ okna cmd (pythonw, ukryte).
Option Explicit
Dim fso, sh, folder
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = folder
' uruchom pythonw (bez konsoli); 0 = okno ukryte, False = nie czekaj
sh.Run "pythonw """ & folder & "\uklad_app.py""", 0, False
