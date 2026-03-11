@echo off
title Costruttore Sbobby AI per Windows
color 0B
echo =======================================================
echo     COSTRUTTORE ESEGUIBILE WINDOWS SBOBBY AI
echo =======================================================
echo.
echo Installazione dei requisiti e PyInstaller in corso...
pip install -r requirements.txt
pip install pyinstaller

echo.
echo =======================================================
echo Compilazione in corso... Questo processo richiede 1-2 minuti.
echo Attendi pazientemente, non chiudere la finestra...
echo =======================================================
echo.

pyinstaller --noconfirm --onefile --windowed --collect-all customtkinter --collect-all tkinterdnd2 --collect-all imageio_ffmpeg --name "Sbobby" "Sbobby.pyw"

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
