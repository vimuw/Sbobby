# 🎓 Sbobinatore AI

Un'applicazione gratuita e completamente open-source che trasforma le registrazioni audio delle tue lezioni universitarie in veri e proprie **sbobine** dettagliate.

L'intelligenza artificiale (basata sul modello gemini 2.5 flash) ascolterà la tua registrazione e scriverà una dispensa eliminando i difetti tipici del parlato (es. ripetizioni, retorica, esitazioni) e strutturando il discorso con paragrafi chiari, elenchi puntati a dizionario e definizioni in grassetto.

---

## 🚀 Come iniziare (Per chi non è un programmatore)

### 1) Come Scaricare il programma
1. Clicca sul grande pulsante verde **`<> Code`** in alto a destra in questa pagina.
2. Clicca su **`Download ZIP`**.
3. Estrai la cartella appena scaricata e spostala dove preferisci (es. sul Desktop o nei Documenti).

### 2) Prerequisito Unico: Python
Se non hai mai programmato sul tuo computer, serve scaricare il "motore" che fa funzionare questo piccolo programma.
- Vai sul sito ufficiale e scarica Python: [python.org/downloads](https://www.python.org/downloads/)
- ⚠️ **MOLTO IMPORTANTE (Solo per Windows):** Appena apri il file di installazione di Python, prima di cliccare "Install Now", **IN BASSO troverai una casellina vuota che dice "Add Python to PATH". DEVI cliccarci sopra.** Poi procedi con l'installazione normale.

### 3) Creare la tua Chiave API di Gemini (Gratis)
Essendo Google Gemini il cervello del programma, ti serve una password unica (API Key) per usarlo.
1. Vai su: [Google AI Studio](https://aistudio.google.com/app/apikey) e accedi col tuo account Google.
2. Clicca sul bottone azzurro `"Create API Key"`.
3. Seleziona `"Create API key in a new project"`.
4. Compariranno un sacco di lettere e numeri segreti (iniziano solitamente con `AIzaSy...`). **Questa è la tua chiave. Copiala.**

---

## ▶️ Come Avviare l'App!

Apri la cartella dello Sbobinatore che hai estratto e fai **doppio clic** sul file corretto, in base al PC che possiedi:

### 💻 Se usi Windows:
- Fai doppio clic su **`Avvia_Sbobinatore_Windows.bat`**.
- La primissima volta, si aprirà una finestra nera per qualche secondo per scaricare gli strumenti necessari; lasciala lavorare in pace. Poi, scomparirà e comparirà l'app! (Usa sempre questo file per lanciarla).

### 🍎 Se usi Mac:
- Fai doppio clic su **`Avvia_Sbobinatore_Mac.command`**.
- *Nota: Se il Mac ti dice che per sicurezza il file non può essere aperto perché proviene da uno sviluppatore non identificato, fai **clic col tasto destro** (o Control+Clic) sul file, e scegli **Apri** dal menu.*

---

## 📖 Come lo uso una volta aperto?
1. Aperta la schermata nera del programma, l'unica cosa da fare la prima volta in alto è incollare la fantomatica **Chiave API** copiata prima. Il programma se la salverà così non devi rimetterla mai più.
2. Clicca "**Sfoglia / Carica**" e seleziona la registrazione audio (o anche direttamente il video MP4!) della tua lunga lezione.
3. Clicca il pulsantone verde **AVVIA**.
4. Niente panico se l'app sembra bloccarsi: nel terminale dentro al programma leggerai esattamente a che punto è! Se l'audio dura un'ora, farà **4 estrazioni** da 15 minuti l'una, e ci metterà all'incirca 3-5 minuti in base al traffico dei server Google.
5. Quando ha finito, troverai il file `.html` (la Sbobina) pronto direttamente sul tuo **Desktop**. Doppio clic per aprirlo.
