@echo off
title Avvio Sbobinatore AI

echo ===================================================
echo   SBOBINATORE AI - Avvio e Installazione
echo ===================================================
echo.

:: Controlla se Python e' installato
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [X] IMPOSSIBILE AVVIARE: Python non e' installato!
    echo.
    echo Per usare questo programma devi prima scaricare e installare Python.
    echo Puoi farlo gratis da: https://www.python.org/downloads/
    echo.
    echo IMPORTANTE: Durante l'installazione di Python, assicurati di spuntare la casella 
    echo "Add Python to PATH" (Aggiungi Python al PATH) che trovi nella primissima schermata!
    echo.
    pause
    exit /b
)

echo [*] Python rilevato. Controllo aggiornamenti necessari...
echo.

:: Installa/Aggiorna le librerie necessarie (la prima volta ci mette un po', poi e' istantaneo)
pip install -r requirements.txt | findstr /V "already satisfied"

echo.
echo [*] Tutto pronto. Sto avviando lo Sbobinatore!
echo.

:: Avvia l'interfaccia grafica vera e propria. Usa pythonw per non tenere aperto un brutto terminale nero.
start "" pythonw Sbobinatore.pyw

:: Piccola attesa e poi chiude questo script
timeout /t 2 /nobreak >nul
exit
