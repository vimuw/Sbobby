@echo off
setlocal
title Costruttore El Sbobinator per Windows (WebUI)
color 0B
cd /d "%~dp0"
echo =======================================================
echo     COSTRUTTORE ESEGUIBILE WINDOWS EL SBOBINATOR (WebUI)
echo =======================================================
echo.
echo Questo script ora delega al builder principale Windows.
echo.
call "%~dp0Costruisci_EXE_Windows.bat"
