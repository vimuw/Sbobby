@echo off
:: Questo file crea o aggiorna l'icona sul Desktop!
:: Sposta liberamente l'intera cartella "Sbobinatore" dove vuoi tu.
:: Se la sposti, basta fare doppio clic su QUESTO file per sistemare l'icona sul Desktop.

set SCRIPT_DIR=%~dp0
set TARGET="%SCRIPT_DIR%Sbobinatore.pyw"
set SHORTCUT="%USERPROFILE%\Desktop\Sbobinatore AI.lnk"
set PWS=powershell.exe -ExecutionPolicy Bypass -NoProfile -Command

%PWS% "$wshell = New-Object -ComObject WScript.Shell; $s = $wshell.CreateShortcut('%SHORTCUT:"=%'); $s.TargetPath = '%TARGET:"=%'; $s.WorkingDirectory = '%SCRIPT_DIR:"=%'; $s.IconLocation = '%SystemRoot%\system32\shell32.dll,22'; $s.Save()"

echo.
echo ========================================================
echo [OK] Il collegamento "Sbobinatore AI" sul Desktop e' stato
echo      creato / aggiornato con l'icona corretta!
echo ========================================================
echo.
timeout /t 4
