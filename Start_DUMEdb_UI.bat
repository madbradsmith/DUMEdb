@echo off
set DUME_PORT=%1
if "%DUME_PORT%"=="" set DUME_PORT=8095
set DUME_HOST=0.0.0.0
start "" "%~dp0start_dumedb_silent.vbs"
timeout /t 1 /nobreak >nul
start http://localhost:%DUME_PORT%/inspector/index.html

