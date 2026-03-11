# Sbobby 🤖

Un'applicazione gratuita e open-source che trasforma le registrazioni audio delle tue lezioni in vere e proprie **sbobine** dettagliate.

L'intelligenza artificiale (basata sul modello Gemini 2.5 Flash) ascolterà la tua registrazione e scriverà una dispensa eliminando i difetti tipici del parlato (es. ripetizioni, retorica, esitazioni) e strutturando il discorso con paragrafi chiari, elenchi puntati a dizionario e definizioni in grassetto.

---

## 🚀 Come iniziare

### 1) Come Scaricare il programma
1. Clicca sulla sezione **Releases** sulla destra di questa pagina GitHub (oppure scarica dai link forniti).
2. Scarica il programma per il tuo sistema operativo:
   - **Per Windows:** Scarica il file `Sbobby.exe`
   - **Per Mac:** Scarica il file `Sbobby_Mac.zip`
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
Fai semplicemente **doppio clic** sul file `Sbobby.exe`.
*(Nota: Se l'antivirus o Windows blocca l'applicazione al primo avvio, non preoccuparti! Consulta la sezione FAQ qui sotto per capire come fare e perché succede).*

> ⏳ **Pazienza all'avvio (Non cliccare mille volte!):** > Sbobby pesa circa 65 MB perché contiene al suo interno tutto il "motore" necessario per funzionare senza farti installare Python. Ogni volta che lo apri, il tuo computer deve "scompattare" questo motore in background. Per questo motivo, **l'avvio richiederà sempre qualche secondo (il tempo esatto dipende dalla velocità e dalla potenza del tuo PC)**. Dagli quindi un attimo di tempo per caricarsi.

### 🍎 Se usi Mac:
Estrai l'archivio ZIP e fai **doppio clic** sull'applicazione `Sbobby.app` (puoi trascinarla nella cartella Applicazioni).
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

**Quanto consuma una sbobina?** L'app divide l'audio in blocchi da 15 minuti. Per ogni blocco effettua in media 1.6 richieste (una di trascrizione, e proporzionalmente una di revisione su macro-blocchi di testo uniti). Avendo a disposizione 20 token (richieste) gratuiti al giorno con Gemini 2.5 Flash, **la lunghezza massima consigliata per l'audio in una singola giornata è di circa 3 ore (180 minuti)**. Oltre questa soglia temporale, l'app supererà le 20 richieste e il processo verrà interrotto per esaurimento del limite gratuito giornaliero di Google.

**Ho finito i token (Errore: ⛔ LIMITE GIORNALIERO RAGGIUNTO!), cosa faccio?**
- **Opzione 1 (Aspettare):** I limiti si resettano ogni giorno a mezzanotte ora del Pacifico, che corrisponde circa alle **ore 9:00 di mattina in Italia**.
- **Opzione 2 (Cambiare account):** Crea una nuova chiave API da un **account Google diverso** (es. una seconda email Gmail). I limiti sono legati all'account, non all'app. *(Nota bene: creare una seconda chiave API dallo stesso account Google non azzera il limite).*

---

## ☕ Supporta il progetto!
Sbobby 🤖 è e sarà sempre **100% gratuito e open-source**.

Tuttavia, se questa app ti ha svoltato la sessione d'esami, ti ha fatto risparmiare decine (o centinaia) di ore di noiosissima sbobinatura manuale e vuoi supportare il mio lavoro, puoi offrirmi un caffè!

* [☕ Offrimi un caffè su Ko-fi](https://ko-fi.com/vimuw)

Grazie e in bocca al lupo per gli esami! 🎉

---

## ⚖️ Disclaimer Etico e Legale (Importante)
Sbobby 🤖 è esclusivamente uno **strumento software locale** che facilita l'interazione tra l'utente e le API pubbliche di Google Gemini.

Scaricando e utilizzando questa applicazione, accetti e comprendi che:
* **Diritto d'autore e Uso Personale:** Le lezioni universitarie sono proprietà intellettuale dei rispettivi docenti. L'uso di questo strumento è inteso **esclusivamente per scopi di studio personale**. La diffusione pubblica, la pubblicazione online o la vendita a terzi delle sbobine generate senza il consenso esplicito del docente è una violazione del diritto d'autore. L'autore di questo software declina ogni responsabilità per l'uso improprio o illecito dei testi generati.
* **Privacy e Gestione dei Dati:** Inserendo la tua chiave API personale (BYOK), stabilisci una connessione diretta tra il tuo computer e i server di Google, accettando i [Termini di Servizio di Google](https://policies.google.com/terms). Sbobby 🤖 non ha server propri: non intercetta, non salva in cloud e non condivide con nessuno (nemmeno con il creatore dell'app) i tuoi file audio, le tue sbobine o la tua chiave API. Tutto avviene e rimane sul tuo dispositivo.
* **Tassativo Divieto per Dati Clinici Sensibili (Privacy e GDPR):** Sbobby elabora i file audio inviandoli tramite API per la trascrizione. Per questo motivo, è assolutamente vietato dare in pasto all'app registrazioni effettuate in ambiente clinico, durante i tirocini in reparto o che contengono conversazioni con pazienti reali. L'elaborazione di dati sanitari sensibili o informazioni che possano identificare un paziente tramite API esterne è una grave violazione della privacy. Usa l'app **solo per trascrivere le lezioni frontali in aula**.
* **Nessuna Garanzia:** Come specificato dalla Licenza MIT allegata al progetto, il software è fornito "così com'è", senza alcuna garanzia. L'autore non è responsabile per eventuali crash, perdita di dati, esami andati male o inesattezze nelle trascrizioni. 😉

---
## 📝 Licenza
Questo progetto è open-source e distribuito sotto la **Licenza MIT**.
Per tutti i dettagli, consulta il file `LICENSE` incluso in questa repository.

---

## 🛠️ Costruire l'App dai sorgenti
Se scarichi il codice sorgente completo e vuoi compilare tu stesso i file eseguibili nativi (`.exe` o `.app`), usa gli script di automazione inclusi:
- **Windows:** Fai doppio clic su `Costruisci_EXE_Windows.bat`. Verrà creata la cartella `dist` contenente l'applicativo compilato con PyInstaller.
- **Mac:** Dal terminale, avvia `Costruisci_APP_Mac.command` per generare l'app macOS nativa.