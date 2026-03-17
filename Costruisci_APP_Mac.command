#!/bin/bash
clear
echo "======================================================="
echo "       COSTRUTTORE APP MAC SBOBBY AI"
echo "======================================================="

# Spostati nella cartella d'origine
cd "$(dirname "$0")"

echo "Creazione/attivazione ambiente virtuale (.venv)..."
if [ ! -f ".venv/bin/python" ]; then
  python3 -m venv .venv
fi
source ".venv/bin/activate"

echo "Installazione dei requisiti e PyInstaller in corso..."
python -m pip install --upgrade pip
if [ -f requirements.lock ]; then
  python -m pip install -r requirements.lock
else
  python -m pip install -r requirements.txt
fi
python -m pip install pyinstaller

echo ""
echo "======================================================="
echo "Compilazione in corso... Questo processo richiede 1-2 minuti."
echo "Attendi pazientemente, non chiudere la finestra..."
echo "======================================================="
echo ""

python -m PyInstaller --noconfirm --windowed --collect-all customtkinter --collect-all tkinterdnd2 --collect-all imageio_ffmpeg --collect-all keyring --name "Sbobby" "Sbobby.pyw"

echo ""
echo "======================================================="
echo "COMPILAZIONE COMPLETATA CON SUCCESSO!"
echo "======================================================="
echo "Troverai il tuo programma pronto all'uso 'Sbobby.app'"
echo "all'interno della cartella 'dist'."
echo "Ora puoi zippare quell'app (tasto destro -> Comprimi)"
echo "e condividerla o caricarla su GitHub Releases!"
echo "======================================================="
echo ""
read -p "Premi Invio per chiudere questa finestra..."
