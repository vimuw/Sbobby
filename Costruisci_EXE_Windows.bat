@echo off
setlocal
title Costruttore El Sbobinator per Windows
color 0B
cd /d "%~dp0"
echo =======================================================
echo     COSTRUTTORE ESEGUIBILE WINDOWS EL SBOBINATOR
echo =======================================================
echo.
where node >nul 2>nul
if errorlevel 1 (
    echo [ERRORE] Node.js non trovato! Installa Node.js da https://nodejs.org
    echo          Serve solo per compilare la WebUI, non agli utenti finali.
    pause
    exit /b 1
)

echo Creazione/attivazione ambiente virtuale (.venv)...
if not exist ".venv\\Scripts\\python.exe" (
    echo   - Creo .venv...
    py -3 -m venv .venv
)
call ".venv\\Scripts\\activate.bat"

echo.
echo =======================================================
echo Compilazione WebUI in corso... Questo processo richiede 1-2 minuti.
echo Attendi pazientemente, non chiudere la finestra...
echo =======================================================
echo.

python scripts\build_release.py build --target windows --ui webui --install-deps --dev-deps

echo.
echo =======================================================
echo COMPILAZIONE COMPLETATA CON SUCCESSO!
echo =======================================================
echo Troverai il tuo programma pronto all'uso "El Sbobinator.exe" 
echo all'interno della cartella "dist".
echo Ora puoi prendere quel piccolo file .exe e condividerlo
echo con chiunque, non servira' avere Python installato!
echo.
pause
