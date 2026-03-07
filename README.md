# 🎓 Sbobinatore AI

Un'applicazione gratuita e completamente open-source che trasforma le registrazioni audio delle tue lezioni universitarie in veri e proprie **sbobine** dettagliate.

L'intelligenza artificiale (basata sul modello gemini 2.5 flash) ascolterà la tua registrazione e scriverà una dispensa eliminando i difetti tipici del parlato (es. ripetizioni, retorica, esitazioni) e strutturando il discorso con paragrafi chiari, elenchi puntati a dizionario e definizioni in grassetto.

---

## 🚀 Come iniziare

### 1) Come Scaricare il programma
1. Clicca sulla sezione **Releases** sulla destra di questa pagina GitHub (oppure scarica dai link forniti).
2. Scarica il programma per il tuo sistema operativo:
   - **Per Windows:** Scarica il file `Sbobinatore_AI.exe`
   - **Per Mac:** Scarica il file `Sbobinatore_AI_Mac.zip`
3. Salva il file dove preferisci (es. sul Desktop).

### 2) Creare la tua Chiave API di Gemini (Gratis)
Essendo Google Gemini il cervello del programma, ti serve una password unica (API Key) per usarlo.
1. Vai su: [Google AI Studio](https://aistudio.google.com/app/apikey) e accedi col tuo account Google.
2. Clicca sul bottone azzurro `"Create API Key"`.
3. Seleziona `"Create API key in a new project"`.
4. Compariranno un sacco di lettere e numeri segreti (iniziano solitamente con `AIzaSy...`). **Questa è la tua chiave. Copiala.**

---

## ▶️ Come Avviare l'App!

È un programma "plug & play", non devi installare nulla sul tuo PC.

### 💻 Se usi Windows:
- Fai semplicemente **doppio clic** sul file `Sbobinatore_AI.exe`.

### 🍎 Se usi Mac:
- Estrai l'archivio ZIP e fai **doppio clic** sull'applicazione `Sbobinatore_AI.app` (puoi trascinarla nella cartella Applicazioni).
- *Nota: Al primissimo avvio, se il Mac dovesse bloccarti dicendo "proveniente da uno sviluppatore non identificato", ti basta fare **clic col tasto destro** (o Control+Clic) sull'icona, e scegliere **Apri** dal menu.*

---

## 📖 Come lo uso una volta aperto?
1. Aperta la schermata del programma, l'unica cosa da fare la prima volta in alto è incollare la fantomatica **Chiave API** copiata prima. Il programma se la salverà così non devi rimetterla mai più.
2. Clicca "**Sfoglia / Carica**" e seleziona la registrazione audio della tua lunga lezione.
3. Clicca il pulsantone verde **AVVIA**.
4. Niente panico se l'app sembra bloccarsi: nel terminale dentro al programma leggerai esattamente a che punto è! Se l'audio dura un'ora, farà **4 estrazioni** da 15 minuti l'una, e ci metterà all'incirca 3-5 minuti in base al traffico dei server Google.
5. Quando ha finito, troverai il file `.html` (la Sbobina) pronto direttamente sul tuo **Desktop**, già formattato per il copia-incolla perfetto su Google Docs.

---

## 🛠️ Per gli Sviluppatori (Costruire l'App dai sorgenti)
Se scarichi il codice sorgente completo e vuoi compilare tu stesso i file eseguibili nativi (`.exe` o `.app`), usa gli script di automazione inclusi:
- **Windows:** Fai doppio clic su `Costruisci_EXE_Windows.bat`. Verrà creata la cartella `dist` contenente l'applicativo compilato con PyInstaller.
- **Mac:** Dal terminale, avvia `Costruisci_APP_Mac.command` per generare l'app macOS nativa.
