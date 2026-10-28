@echo off
rem ==============================================================================
rem The Table Autonomous Bridge Daemon Launcher (WF-R10 pythonw)
rem ==============================================================================

set WORKSPACE=c:\Users\c6182\Desktop\folders\DUMEdb-WORK
cd /d "%WORKSPACE%"

rem Terminate any old crawler or daemon instances first
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*the_table/crawler.py*' -or $_.CommandLine -like '*the_table\\crawler.py*' -or $_.CommandLine -like '*bridge_daemon.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" 2>NUL

rem Launch autonomous daemon in background with pythonw
start "" pythonw "%WORKSPACE%\the_table\bridge_daemon.py"
echo [✓] The Table autonomous daemon launched cleanly in background.
exit /b 0
