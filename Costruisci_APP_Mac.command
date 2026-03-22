#!/bin/bash
clear
echo "======================================================="
echo "       COSTRUTTORE APP MAC EL SBOBINATOR"
echo "======================================================="

# Spostati nella cartella d'origine
cd "$(dirname "$0")"

echo "Creazione/attivazione ambiente virtuale (.venv)..."
if [ ! -f ".venv/bin/python" ]; then
  python3 -m venv .venv
fi
source ".venv/bin/activate"

echo ""
echo "======================================================="
echo "Compilazione WebUI in corso... Questo processo richiede 1-2 minuti."
echo "Attendi pazientemente, non chiudere la finestra..."
echo "======================================================="
echo ""

python scripts/build_release.py build --target macos --ui webui --install-deps --dev-deps

echo ""
echo "======================================================="
echo "COMPILAZIONE COMPLETATA CON SUCCESSO!"
echo "======================================================="
echo "Troverai il tuo programma pronto all'uso 'El Sbobinator.app'"
echo "all'interno della cartella 'dist'."
echo "Ora puoi zippare quell'app (tasto destro -> Comprimi)"
echo "e condividerla o caricarla su GitHub Releases!"
echo "======================================================="
echo ""
read -p "Premi Invio per chiudere questa finestra..."
