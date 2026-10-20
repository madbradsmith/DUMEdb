Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\c6182\Desktop\folders\DUMEdb-WORK"
WshShell.Run """C:\Users\c6182\Desktop\folders\DUMEdb-WORK\.venv\Scripts\pythonw.exe"" -m dume", 0, False
