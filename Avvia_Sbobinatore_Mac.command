#!/bin/bash

# ===================================================
# SBOBINATORE AI - Avvio Mac
# ===================================================

# Si posiziona nella cartella corretta dove si trova il file .command
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "==================================================="
echo "  SBOBINATORE AI - Controllo e Avvio"
echo "==================================================="
echo ""

# Controlla se python3 è disponibile (Mac lo ha spesso di default, ma a volte chiede l'installazione dei command line tools)
if ! command -v python3 &> /dev/null
then
    echo "[X] Python3 non è installato o non è nel PATH."
    echo "Il Mac ti dovrebbe aver appena chiesto di installare i 'Command Line Tools'."
    echo "Conferma l'installazione, aspetta che finisca, poi riapri questo file."
    echo "Altrimenti, scarica Python da: https://www.python.org/downloads/macos/"
    exit 1
fi

echo "[*] Controllo delle librerie necessarie..."
python3 -m pip install -r requirements.txt --break-system-packages 2>/dev/null || python3 -m pip install -r requirements.txt

echo ""
echo "[*] Tutto pronto. Avvio dell'Interfaccia Grafica..."
echo "    Puoi chiudere questa finestra del Terminale appena si apre l'App."

# Avvia lo sbobinatore
python3 Sbobinatore.pyw
