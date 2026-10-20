@echo off
echo Starting Diag > C:\Users\c6182\Desktop\folders\DUMEdb-WORK\diag.txt
tasklist /FI "IMAGENAME eq powershell.exe" >> C:\Users\c6182\Desktop\folders\DUMEdb-WORK\diag.txt
tasklist /FI "IMAGENAME eq python.exe" >> C:\Users\c6182\Desktop\folders\DUMEdb-WORK\diag.txt
dir "%APPDATA%\Microsoft\Windows\PowerShell\PSReadLine" >> C:\Users\c6182\Desktop\folders\DUMEdb-WORK\diag.txt 2>&1
dir "%USERPROFILE%\Documents\WindowsPowerShell" >> C:\Users\c6182\Desktop\folders\DUMEdb-WORK\diag.txt 2>&1
echo Done >> C:\Users\c6182\Desktop\folders\DUMEdb-WORK\diag.txt
