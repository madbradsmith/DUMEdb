@echo off
rem ==============================================================================
rem Stop The Table Background Crawler
rem ==============================================================================

powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*the_table/crawler.py*' -or $_.CommandLine -like '*the_table\\crawler.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('[✓] Stopped process ' + $_.ProcessId) }"
echo [✓] The Table crawler stopped.
exit /b 0

