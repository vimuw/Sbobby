# El Sbobinator 🤠

Un'applicazione gratuita e open-source che trasforma le registrazioni audio delle tue lezioni in vere e proprie **sbobine** dettagliate, ordinate e pronte da studiare.

L'intelligenza artificiale (basata sul modello Gemini 2.5 Flash) ascolterà la tua registrazione e scriverà una dispensa eliminando i difetti tipici del parlato (es. ripetizioni, retorica, esitazioni) e strutturando il discorso con paragrafi chiari, elenchi puntati a dizionario e definizioni in grassetto.

L'obiettivo non è una trascrizione "grezza", ma una vera e propria dispensa leggibile!

<p align="center">
  <img src="https://github.com/user-attachments/assets/bb6eaf42-7b03-4e54-ae51-0765fe8b0727" width="48%" alt="Schermata principale">
  <img src="https://github.com/user-attachments/assets/f8117a13-14a4-483b-899f-56ea72122880" width="48%" alt="Editor anteprima">
</p>

---

## 🚀 Come iniziare

### 1) Come Scaricare il programma
1. Clicca sulla sezione **Releases** sulla destra di questa pagina GitHub.
2. Scarica il programma per il tuo sistema operativo:
   - **Per Windows:** Scarica il file `El-Sbobinator-Setup-v*.exe` (installer)
   - **Per Mac:** Scarica il file `El-Sbobinator-v*.dmg`
3. Salva il file dove preferisci (es. sul Desktop).

### 2) Creare la tua Chiave API di Gemini (Gratis)
Essendo Google Gemini il cervello del programma, ti serve una password unica (API Key) per usarlo. Creare la API key è completamente gratis.
1. Vai su: [Google AI Studio](https://aistudio.google.com/app/apikey) e accedi col tuo account Google.
2. Clicca sul bottone azzurro `"Create API Key"`.
3. Seleziona `"Create API key in a new project"`.
4. Compariranno un sacco di lettere e numeri segreti (iniziano solitamente con `AIzaSy...` oppure con `AQ.`). **Questa è la tua chiave. Copiala.**

---

## ▶️ Come Avviare l'App!

È un programma "plug & play", non devi installare Python o altri programmi sul PC.

### 💻 Se usi Windows:
Esegui il file `El-Sbobinator-Setup-v*.exe` e segui il wizard di installazione. Al termine trovi l'app nel menu Start (o tramite il collegamento creato sul Desktop).
*(Nota: Se l'antivirus o la schermata blu di Windows ti bloccano al primo avvio, o se vedi una schermata nera, consulta la sezione FAQ qui sotto per risolvere in un clic).*

### 🍎 Se usi Mac:
Apri il file `.dmg`, trascina `El Sbobinator.app` nella cartella **Applicazioni** e avviala da lì.
*(Nota: Al primissimo avvio, se il Mac dovesse bloccarti dicendo "proveniente da uno sviluppatore non identificato", ti basta fare **clic col tasto destro** — o Control+Clic — sull'icona, e scegliere **Apri** dal menu).*

#### 🔄 Aggiornamenti automatici
Quando esce una nuova versione, l'app mostra direttamente nell'interfaccia un pulsante **"Installa aggiornamento"**. Cliccandolo, l'app scarica e installa il nuovo pacchetto in autonomia — nessun bisogno di tornare su GitHub.

---

## 💻 Requisiti di sistema

| | Windows | macOS |
|---|---|---|
| **Versione minima** | Windows 10 (64-bit) | macOS 11 Big Sur |
| **Connessione internet** | ✅ Richiesta durante l'elaborazione | ✅ Richiesta durante l'elaborazione |
| **Spazio su disco** | ~50 MB (app) + variabile per le sessioni | ~50 MB (app) + variabile per le sessioni |
| **RAM consigliata** | 4 GB | 4 GB |

> ⚠️ Il PC deve rimanere **acceso e connesso a internet** per tutta la durata dell'elaborazione. L'AI gira sui server di Google, non sul tuo processore: la potenza del tuo PC non influisce sulla velocità.
>
> 💾 Lo spazio occupato cresce nel tempo: ogni elaborazione salva i progressi parziali (testo già trascritto, blocchi revisionati) in modo da poter riprendere in caso di interruzione. Puoi liberare spazio con il tasto **"Pulisci sessioni vecchie"** nelle Impostazioni.

---

## � Come si usa passo passo?

1. **Inserisci la chiave:** Nelle impostazioni, incolla la tua Chiave API di Gemini. L'app la salverà in modo sicuro (tramite protezione del profilo su Windows o Portachiavi su macOS), così non dovrai rimetterla mai più. Puoi anche inserire chiavi extra e usare la funzione *Validazione ambiente* per controllare che tutto funzioni.
2. **Carica l'audio:** Seleziona uno o più file audio o video trascinandoli nella finestra oppure cliccando per sfogliarli. Formati supportati: `.mp3`, `.m4a`, `.wav`, `.ogg`, `.flac`, `.aac`, `.mp4`, `.mkv`, `.webm` (funziona anche con le registrazioni schermo di Teams, Zoom, ecc.). L'app li aggiungerà alla **Coda di elaborazione** scartando in automatico eventuali duplicati.
3. **Avvia:** Clicca sul pulsantone "Avvia sbobinatura". L'app ti mostrerà in tempo reale la fase corrente e il progresso. Ad esempio, se l'audio dura un'ora, farà circa 4 estrazioni da 15 minuti l'una.
4. **Rifinisci nell'Editor:** A fine processo si potrai aprire la schermata di anteprima con un editor di testo completo. Puoi:
   - Leggere e modificare il testo liberamente
   - Applicare formattazione: **grassetto**, *corsivo*, sottolineato, elenchi, tabelle
   - Strutturare il documento con titoli (`H1`, `H2`, `H3`...)
   - Usare **Trova & Sostituisci** per correggere in blocco termini tecnici sbagliati
   - Riascoltare l'audio originale col **player integrato**
   - Inserire immagini nel documento

   Se l'audio originale è stato spostato sul PC, usa il tasto **"Ricollega audio"** per ricollegarlo.
5. **Esporta:** Una volta perfetto, usa il tasto **"Copia testo"** per copiare il documento con tutta la formattazione intatta (titoli, grassetti, elenchi) e incollalo direttamente su **Google Docs** o **Word** — il risultato sarà già ben strutturato, senza bisogno di riformattare nulla. Per ottenere un **PDF**, usa la funzione di stampa del browser (`Ctrl+P` → "Salva come PDF") direttamente dall'Editor. Per sicurezza, una copia `.html` viene sempre salvata in automatico sul tuo Desktop.

---

## ⚡ Quanto è veloce?

Molto più di quanto immagini. Anche una registrazione di **3 ore di lezione** viene elaborata in circa **10-12 minuti**.

Il tempo dipende principalmente dalla velocità di risposta delle API di Google, non dalla potenza del tuo PC. Durante l'elaborazione l'app mostra un'ETA aggiornata in tempo reale così sai sempre quanto manca.

---

## 💾 Autosalvataggio e Ripresa (Niente panico!)
El Sbobinator 🤠 salva automaticamente i progressi mentre lavora e le modifiche che fai nell'editor di anteprima.

Se chiudi l'app per sbaglio, se il PC si spegne, o se finisci la quota giornaliera dell'API, **non perdi quasi nulla**.
Quando riaprirai l'app e ricaricherai lo stesso file audio, El Sbobinator 🤠 ti chiederà se vuoi "riutilizzare" i risultati salvati per riprendere esattamente da dove si era interrotto, o se vuoi ricominciare da capo.

I dati di sessione (blocchi di testo già elaborati, progressi parziali) vengono salvati in una cartella nascosta sul tuo computer (`~/.el_sbobinator_sessions/`). Questa cartella può crescere nel tempo se elabori molti file. Nelle **Impostazioni** trovi il tasto **"Pulisci sessioni vecchie"** per eliminare automaticamente i dati più vecchi di 14 giorni e liberare spazio.

---

## 🎯 Cosa aspettarsi dai risultati (Disclaimer sull'AI)
È importante ricordare che l'intelligenza artificiale **non è perfetta**. La sbobina finale potrebbe contenere qualche parola tecnica interpretata male o qualche piccola ripetizione residua.

Il vero vantaggio è che l'app **farà il 90% del lavoro sporco e pesante al posto tuo**. A te basterà dare una rapida rilettura per sistemare quelle due o tre imperfezioni, risparmiando comunque ore e ore di digitazione manuale!

Ricorda la regola d'oro dell'AI: **la qualità del risultato dipende dalla qualità dell'audio di partenza**. Se l'audio è incomprensibile per un umano, lo sarà anche per Gemini.

---

## ❓ FAQ - Domande Frequenti

### È sicuro? Il mio antivirus lo segnala come minaccia!
Assolutamente sì, è sicuro al 100%. Il codice sorgente dell'applicazione è completamente pubblico e verificabile da chiunque su GitHub. Se il tuo antivirus o Windows Defender blocca l'app, si tratta di un **falso positivo**.
Questo succede quasi sempre con i programmi scritti in Python e trasformati in eseguibili `.exe`. Gli antivirus diffidano "di default" dei programmi creati da sviluppatori indipendenti senza una firma digitale commerciale. Per scrupolo, puoi analizzare il file su VirusTotal.

**Come risolvere su Windows:**
- **Schermata blu SmartScreen:** Clicca su `"Ulteriori Informazioni"` e poi `"Esegui Comunque"`.
- **Se l'antivirus lo elimina:** Vai nella Cronologia Protezione di Windows, clicca sulla minaccia rilevata e seleziona `"Consenti nel dispositivo"`.

### Su Windows vedo una finestra nera o l'app non carica l'interfaccia!
Molto probabilmente sul tuo computer manca **Microsoft Edge WebView2 Runtime**, un componente standard di Windows necessario per far funzionare la bellissima interfaccia grafica.
Puoi installarlo ufficialmente e gratuitamente da qui: 👉 [Scarica WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703). Dopo l'installazione, chiudi e riapri l'app.

### Quali sono i limiti giornalieri dell'API?
L'intelligenza artificiale di Google non è illimitata: le quote gratuite dipendono dal tuo account e possono cambiare. In generale, più l'audio è lungo, più richieste servono.
**Se finisci i token (Errore: LIMITE GIORNALIERO RAGGIUNTO):**
L'app si metterà in pausa e ti aprirà un popup. Puoi incollare una nuova chiave API e riprendere subito, oppure premere "Annulla", far chiudere l'app salvando i progressi, e aspettare il reset dei token (che avviene ogni giorno alle 9:00 di mattina circa in Italia).

---

## ☕ Supporta il progetto!
El Sbobinator 🤠 è e sarà sempre **100% gratuito e open-source**.

Tuttavia, se questa app ti ha svoltato la sessione d'esami, ti ha fatto risparmiare decine (o centinaia) di ore di noiosissima sbobinatura manuale e vuoi supportare il mio lavoro, puoi offrirmi un caffè!

* [☕ Offrimi un caffè su Ko-fi](https://ko-fi.com/vimuw)

Grazie e in bocca al lupo per gli esami! 🎉

---

## 🤝 Contribuire al progetto

Hai trovato un bug o vuoi suggerire una nuova funzione? Apri una **[Issue](https://github.com/vimuw/El-Sbobinator/issues)** su GitHub — ogni segnalazione è benvenuta!

For development/contributing, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## ⚖️ Disclaimer Etico e Legale (Importante)
El Sbobinator 🤠 è esclusivamente uno **strumento software locale** che facilita l'interazione tra l'utente e le API pubbliche di Google Gemini.

Scaricando e utilizzando questa applicazione, accetti e comprendi che:
* **Diritto d'autore e Uso Personale:** Le lezioni universitarie sono proprietà intellettuale dei rispettivi docenti. L'uso di questo strumento è inteso **esclusivamente per scopi di studio personale**. La diffusione pubblica, la pubblicazione online o la vendita a terzi delle sbobine generate senza il consenso esplicito del docente è una violazione del diritto d'autore.
* **Privacy e Gestione dei Dati:** Inserendo la tua chiave API personale (BYOK), stabilisci una connessione diretta tra il tuo computer e i server di Google. El Sbobinator 🤠 non ha server propri: non intercetta né salva in cloud i tuoi file audio. Tutto avviene e rimane sul tuo dispositivo.
* **Tassativo Divieto per Dati Clinici Sensibili (Privacy e GDPR):** È assolutamente vietato dare in pasto all'app registrazioni effettuate in ambiente clinico, durante i tirocini in reparto o che contengono conversazioni con pazienti reali. L'elaborazione di dati sanitari sensibili tramite API esterne è una grave violazione della privacy. Usa l'app **solo per trascrivere le lezioni frontali in aula**.
* **Nessuna Garanzia:** Come specificato dalla Licenza MIT allegata al progetto, il software è fornito "così com'è", senza alcuna garanzia.

---

## 📝 Licenza
Questo progetto è open-source e distribuito sotto la **Licenza MIT**.
Per tutti i dettagli, consulta il file `LICENSE` incluso in questa repository.

---

<details>
<summary>🛠️ Costruire l'App dai sorgenti</summary>

Se scarichi il codice sorgente completo e vuoi compilare tu stesso i pacchetti nativi, usa gli script di automazione inclusi. La WebUI è l'unica interfaccia supportata per lo sviluppo e le release (i vecchi entrypoint desktop restano solo come alias di compatibilità).
- **Windows:** usa `packaging/Costruisci_EXE_Windows.bat`.
- **macOS:** dal terminale, avvia `packaging/Costruisci_APP_Mac.command`.

### Developer setup

**Requisiti:** Python 3.11, Node.js 24 (versioni esatte richieste per allineamento con la CI).

```bash
python scripts/build_release.py deps --ui webui --dev
```

**Gestione delle API key — nessuna variabile d'ambiente necessaria.**
Le chiavi Gemini vengono inserite dall'utente direttamente nella schermata **Impostazioni** dell'app desktop. L'app le salva in modo sicuro localmente: tramite DPAPI su Windows, tramite il Portachiavi di sistema su macOS. Non esiste nessun file `.env` da configurare per sviluppare o compilare il progetto.

### Local checks

```bash
# Verifica dipendenze e tooling
python scripts/build_release.py deps --ui webui --dev

# Lint + test (salta npm install se già fatto)
python scripts/build_release.py check --skip-npm-install
```

**Build locale:**

```bash
python scripts/build_release.py build --target windows --ui webui --install-deps --dev-deps
python scripts/build_release.py build --target macos --ui webui --install-deps --dev-deps
```

### Documentazione per sviluppatori

Per i dettagli di architettura, pipeline, formato sessione e contratto del bridge vedi:

- [`docs/architecture.md`](docs/architecture.md) — mappa dei moduli Python/React e flusso a runtime.
- [`docs/pipeline.md`](docs/pipeline.md) — fasi della pipeline, catena di fallback e valori di `last_error`.
- [`docs/session_model.md`](docs/session_model.md) — layout su disco delle sessioni e schema `session.json`.
- [`docs/bridge_protocol.md`](docs/bridge_protocol.md) — eventi Python→JS e API JS→Python.

</details>
