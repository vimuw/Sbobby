#!/bin/bash
clear
echo "======================================================="
echo "       COSTRUTTORE APP MAC SBOBINATORE AI"
echo "======================================================="

# Spostati nella cartella d'origine
cd "$(dirname "$0")"

echo "Installazione dei requisiti e PyInstaller in corso..."
pip3 install -r requirements.txt
pip3 install pyinstaller

echo ""
echo "======================================================="
echo "Compilazione in corso... Questo processo richiede 1-2 minuti."
echo "Attendi pazientemente, non chiudere la finestra..."
echo "======================================================="
echo ""

pyinstaller --noconfirm --windowed --collect-all customtkinter --copy-metadata imageio --name "Sbobinatore_AI" "Sbobinatore.pyw"

echo ""
echo "======================================================="
echo "COMPILAZIONE COMPLETATA CON SUCCESSO!"
echo "======================================================="
echo "Troverai il tuo programma pronto all'uso 'Sbobinatore_AI.app'"
echo "all'interno della cartella 'dist'."
echo "Ora puoi zippare quell'app (tasto destro -> Comprimi)"
echo "e condividerla o caricarla su GitHub Releases!"
echo "======================================================="
echo ""
read -p "Premi Invio per chiudere questa finestra..."
