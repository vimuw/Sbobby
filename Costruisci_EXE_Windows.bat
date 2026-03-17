@echo off
setlocal
title Costruttore Sbobby AI per Windows
color 0B
cd /d "%~dp0"
echo =======================================================
echo     COSTRUTTORE ESEGUIBILE WINDOWS SBOBBY AI
echo =======================================================
echo.
echo Creazione/attivazione ambiente virtuale (.venv)...
if not exist ".venv\\Scripts\\python.exe" (
    echo   - Creo .venv...
    py -3 -m venv .venv
)
call ".venv\\Scripts\\activate.bat"

echo Installazione dei requisiti e PyInstaller in corso...
python -m pip install --upgrade pip
if exist requirements.lock (
    python -m pip install -r requirements.lock
) else (
    python -m pip install -r requirements.txt
)
python -m pip install pyinstaller

echo.
echo =======================================================
echo Compilazione in corso... Questo processo richiede 1-2 minuti.
echo Attendi pazientemente, non chiudere la finestra...
echo =======================================================
echo.

python -m PyInstaller --noconfirm --clean --onefile --windowed --collect-all customtkinter --collect-all tkinterdnd2 --collect-all imageio_ffmpeg --collect-all keyring --name "Sbobby" "Sbobby.pyw"

echo.
echo =======================================================
echo COMPILAZIONE COMPLETATA CON SUCCESSO!
echo =======================================================
echo Troverai il tuo programma pronto all'uso "Sbobby.exe" 
echo all'interno della cartella "dist".
echo Ora puoi prendere quel piccolo file .exe e condividerlo
echo con chiunque, non servira' avere Python installato!
echo.
pause
