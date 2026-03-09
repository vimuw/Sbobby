# 🎓 Sbobinatore AI

Un'applicazione gratuita e open-source che trasforma le registrazioni audio delle tue lezioni in vere e proprie **sbobine** dettagliate.

L'intelligenza artificiale (basata sul modello Gemini 2.5 Flash) ascolterà la tua registrazione e scriverà una dispensa eliminando i difetti tipici del parlato (es. ripetizioni, retorica, esitazioni) e strutturando il discorso con paragrafi chiari, elenchi puntati a dizionario e definizioni in grassetto.

---

## 🚀 Come iniziare

### 1) Come Scaricare il programma
1. Clicca sulla sezione **Releases** sulla destra di questa pagina GitHub (oppure scarica dai link forniti).
2. Scarica il programma per il tuo sistema operativo:
   - **Per Windows:** Scarica il file `Sbobinatore_AI.exe`
   - **Per Mac:** Scarica il file `Sbobinatore_AI_Mac.zip`
3. Salva il file dove preferisci (es. sul Desktop).

### 2) Creare la tua Chiave API di Gemini (Gratis)
Essendo Google Gemini il cervello del programma, ti serve una password unica (API Key) per usarlo. L'API key è completamente gratuita.
1. Vai su: [Google AI Studio](https://aistudio.google.com/app/apikey) e accedi col tuo account Google.
2. Clicca sul bottone azzurro `"Create API Key"`.
3. Seleziona `"Create API key in a new project"`.
4. Compariranno un sacco di lettere e numeri segreti (iniziano solitamente con `AIzaSy...`). **Questa è la tua chiave. Copiala.**

---

## ▶️ Come Avviare l'App!

È un programma "plug & play", non devi installare nulla sul PC.

### 💻 Se usi Windows:
Fai semplicemente **doppio clic** sul file `Sbobinatore_AI.exe`.
*(Nota: Se l'antivirus o Windows blocca l'applicazione al primo avvio, non preoccuparti! Consulta la sezione FAQ qui sotto per capire come fare e perché succede).*

### 🍎 Se usi Mac:
Estrai l'archivio ZIP e fai **doppio clic** sull'applicazione `Sbobinatore_AI.app` (puoi trascinarla nella cartella Applicazioni).
*(Nota: Al primissimo avvio, se il Mac dovesse bloccarti dicendo "proveniente da uno sviluppatore non identificato", ti basta fare **clic col tasto destro** — o Control+Clic — sull'icona, e scegliere **Apri** dal menu).*

---

## 📖 Come lo uso una volta aperto?
1. Aperta la schermata del programma, incolla in alto la **Chiave API** copiata prima. Il programma se la salverà, così non dovrai rimetterla mai più.
2. Clicca "**Sfoglia / Carica**" e seleziona la registrazione audio della tua lezione.
3. Clicca il pulsantone verde **AVVIA**.
4. Niente panico se l'app sembra bloccarsi: nel terminale dentro al programma leggerai esattamente a che punto è! Ad esempio, se l'audio dura un'ora, farà **4 estrazioni** da 15 minuti l'una, e ci metterà all'incirca 3-5 minuti in base al traffico dei server Google e alla tua connessione.
5. Quando ha finito, troverai il file `.html` (la Sbobina) pronto direttamente sul tuo **Desktop**, già formattato per il copia-incolla su Google Docs.

---

## 🎯 Cosa aspettarsi dai risultati (Disclaimer sull'AI)
È importante ricordare che l'intelligenza artificiale **non è perfetta**. La sbobina generata potrebbe contenere qualche piccolo errore di trascrizione, parole tecniche interpretate male o, talvolta, piccolissime porzioni di testo sdoppiate (specialmente nel punto di giunzione tra una parte di audio e l'altra). 

Stiamo parlando di una percentuale di imprecisione davvero minuscola rispetto al testo totale. Il vero vantaggio è che l'app **farà il 90% del lavoro sporco e noioso al posto tuo**. A te basterà dare una rapida rilettura per sistemare quelle due o tre imperfezioni, risparmiando comunque ore e ore di digitazione manuale!

## 💡 Consigli per una sbobina perfetta
Ricorda sempre una regola d'oro dell'intelligenza artificiale: **la qualità del risultato dipende dalla qualità dell'audio di partenza**. Se l'audio è incomprensibile per un umano, lo sarà anche per l'AI!

Per ottenere i risultati migliori, segui queste accortezze durante la lezione:
* **Avvicinati alla fonte:** Cerca di sederti nei primi banchi o comunque assicurati che la voce del professore arrivi forte e chiara al tuo dispositivo.
* **Attenzione ai rumori di sottofondo:** L'AI è bravissima a isolare la voce principale, ma se c'è molto chiacchiericcio dei vicini di banco, rumore di fogli, colpi sul tavolo o rimbombi eccessivi, l'audio potrebbe confondersi generando errori o frasi saltate.
* **Non coprire il microfono:** Se registri con lo smartphone, il tablet o il PC, assicurati che il microfono non sia ostruito da oggetti.

---

## ❓ FAQ - Domande Frequenti

### È sicuro? Il mio antivirus lo segnala come minaccia!
Assolutamente sì, è sicuro al 100%. Il codice sorgente dell'applicazione è completamente pubblico e verificabile da chiunque su GitHub. Se il tuo antivirus o Windows Defender blocca l'app (segnalandola magari come *Trojan* o *Malware*), si tratta di un **falso positivo**.

**Cos'è un falso positivo e perché succede?**
Un falso positivo avviene quando un antivirus scambia un file innocuo per un virus. Questo succede quasi sempre con i programmi scritti in Python e trasformati in eseguibili `.exe` tramite un tool chiamato *PyInstaller*. Gli antivirus diffidano "di default" dei programmi creati da sviluppatori indipendenti che non possiedono una firma digitale a pagamento (che costa centinaia di euro l'anno).

Per totale trasparenza, ho fatto analizzare il file a **VirusTotal**: [INSERISCI QUI IL LINK DI VIRUSTOTAL]. Come puoi vedere dai risultati, su 64 motori antivirus mondiali, solo 1 lo segnala come sospetto, confermando che si tratta di un banale errore di rilevamento.

**Come risolvere su Windows:**
- **Se appare la schermata blu di Windows SmartScreen:** Clicca su `"Ulteriori Informazioni"` e poi sul pulsante in basso `"Esegui Comunque"`.
- **Se l'antivirus lo elimina:** Vai nella Cronologia Protezione di Windows, clicca sulla minaccia rilevata e seleziona `"Consenti nel dispositivo"` o `"Ripristina"`.

### Quali sono i limiti giornalieri dell'API (Importante!)
L'intelligenza artificiale di Google non è illimitata: funziona a **"gettoni" (token)**. Il piano gratuito di Gemini 2.5 Flash ti dà un massimo di **20 richieste al giorno** per account.

**Quanto consuma una sbobina?** Una lezione da 2 ore e mezza (o più) consuma circa 10-15 richieste. Questo significa che con una singola chiave API potrai sbobinare in genere **1 lezione lunga al giorno**.

**Ho finito i token (Errore: LIMITE GIORNALIERO RAGGIUNTO), cosa faccio?**
- **Opzione 1 (Aspettare):** I limiti si resettano ogni giorno a mezzanotte ora del Pacifico, che corrisponde circa alle **ore 9:00 di mattina in Italia**.
- **Opzione 2 (Cambiare account):** Crea una nuova chiave API da un **account Google diverso** (es. una seconda email Gmail). I limiti sono legati all'account, non all'app. *(Nota bene: creare una seconda chiave API dallo stesso account Google non azzera il limite).*

---

## 🧠 Dietro le quinte (Come è nata l'app)
Non sono uno sviluppatore professionista. Ho creato questa app partendo da zero, affidandomi a strumenti di intelligenza artificiale. Sono una persona pigra e di spendere 3-4 giorni a fare una sbobina proprio non ne avevo voglia! Ho quindi creato questa app per me e i miei amichetti per risparmiarci la mole di lavoro.

---

## ☕ Supporta il progetto!
Sbobinatore AI è e sarà sempre **100% gratuito e open-source**. 

Tuttavia, se questa app ti ha svoltato la sessione d'esami, ti ha fatto risparmiare decine (o centinaia) di ore di noiosissima sbobinatura manuale e vuoi supportare il mio lavoro, puoi offrirmi un caffè!

* [☕ Offrimi un caffè su Ko-fi](https://ko-fi.com/vimuw)

Grazie e in bocca al lupo per gli esami! 🎉

---

## 🛠️ Costruire l'App dai sorgenti
Se scarichi il codice sorgente completo e vuoi compilare tu stesso i file eseguibili nativi (`.exe` o `.app`), usa gli script di automazione inclusi:
- **Windows:** Fai doppio clic su `Costruisci_EXE_Windows.bat`. Verrà creata la cartella `dist` contenente l'applicativo compilato con PyInstaller.
- **Mac:** Dal terminale, avvia `Costruisci_APP_Mac.command` per generare l'app macOS nativa.
