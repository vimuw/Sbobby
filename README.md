# El Sbobinator 🤠

Un'applicazione gratuita e open-source che trasforma le registrazioni audio delle tue lezioni in vere e proprie **sbobine** dettagliate, ordinate e pronte da studiare.

L'intelligenza artificiale, basata su **Gemini 2.5 Flash**, ascolta la registrazione e riscrive il contenuto in forma più chiara, eliminando molti difetti tipici del parlato come ripetizioni, esitazioni e frasi spezzate.

L'obiettivo non è ottenere una trascrizione "grezza", ma una **dispensa leggibile**, con paragrafi ben separati, titoli, sottotitoli, elenchi e definizioni in evidenza.

---

## 🚀 Come iniziare

### 1) Scaricare il programma
1. Apri la sezione **Releases** di questa repository GitHub.
2. Scarica il file adatto al tuo sistema operativo:
   - **Windows:** `El Sbobinator.exe`
   - **macOS:** archivio `.zip` con `El Sbobinator.app`
3. Salva il file dove preferisci, ad esempio sul Desktop.

### 2) Creare la tua API Key di Gemini
Per usare l'app serve una **API Key personale** di Google Gemini. La creazione è gratuita.

1. Vai su [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Accedi con il tuo account Google.
3. Clicca su **Create API Key**.
4. Scegli **Create API key in a new project**.
5. Copia la chiave generata. In genere inizia con `AIza...`.

---

## ✨ Funzioni principali

El Sbobinator oggi include queste funzioni:

- **Sbobinatura automatica di audio lunghi** con gestione a blocchi.
- **Pulizia del parlato**: meno ripetizioni, meno riempitivi, testo più leggibile.
- **Generazione di un file HTML finale** pronto da aprire, modificare o copiare su Google Docs.
- **Coda di elaborazione** con più file, riordinamento e gestione degli elementi completati.
- **Anteprima integrata** del risultato finale direttamente dentro l'app.
- **Editor di testo integrato** per correggere e rifinire la sbobina prima dell'uso.
- **Inserimento immagini nell'editor** (WIP)
- **Player audio integrato** nella schermata anteprima, se il file originale è ancora disponibile.
- **Ricollegamento dell'audio** se il file è stato spostato dopo l'elaborazione.
- **Autosalvataggio** delle modifiche nell'anteprima.
- **Ripresa delle sessioni interrotte**, anche in caso di crash o quota esaurita.
- **Supporto a chiavi di fallback** per continuare se una API Key finisce la quota.
- **Tema chiaro/scuro** selezionabile dall'utente.
- **Validazione ambiente** per controllare rapidamente se tutto è configurato bene.

---

## ▶️ Come si usa davvero l'app

Questa è la guida pratica, passo per passo.

### 1) Avvia l'app

#### Su Windows
Fai doppio clic su `El Sbobinator.exe`.

Se al primo avvio Windows SmartScreen ti blocca il file, clicca:
- **Ulteriori informazioni**
- **Esegui comunque**

#### Su macOS
Estrai lo ZIP, poi apri `El Sbobinator.app`.

Se macOS segnala che proviene da uno sviluppatore non identificato:
- fai **clic destro** sull'app
- scegli **Apri**
- conferma di nuovo **Apri**

### 2) Inserisci la tua API Key
Apri le **Impostazioni** e incolla la tua chiave Gemini.

L'app la salva in locale:
- **Windows:** tramite protezione del sistema / profilo utente
- **macOS / Linux:** tramite keyring o portachiavi di sistema

Se vuoi, puoi aggiungere anche più chiavi di riserva, una per riga.

### 3) Carica uno o più file audio
Usa il pulsante di selezione file e scegli la registrazione della lezione.

L'app:
- riconosce i file già presenti in coda
- evita i duplicati
- mostra subito i file nella **Coda di elaborazione**

### 4) Avvia la sbobinatura
Clicca su **Avvia sbobinatura**.

Durante il processo vedrai:
- il file attualmente in lavorazione
- lo stato della fase corrente
- il progresso
- la console con i messaggi principali

### 5) Attendi il completamento
Quando la sbobina è pronta, l'app genera un file HTML finale.

Per impostazione predefinita, il file viene salvato sul **Desktop**:
- su Windows, anche nel Desktop OneDrive se presente
- su macOS/Linux, nel Desktop dell'utente o nella home come fallback

### 6) Apri l'anteprima e rifinisci il testo
Quando un file è completato puoi:
- aprire l'**anteprima**
- modificare direttamente il testo
- aggiungere immagini
- cambiare titoli e sottotitoli
- copiare il contenuto
- aprire il file HTML nel browser

Le modifiche fatte nell'anteprima vengono salvate automaticamente.

### 7) Copia su Google Docs
Dalla schermata anteprima puoi usare **Copia testo**.

L'app copia sia:
- il testo semplice
- l'HTML formattato

Questo rende il copia-incolla su Google Docs molto più pulito rispetto a una semplice trascrizione grezza.

---

## 📝 Come funziona la schermata anteprima

La schermata anteprima serve per rifinire il risultato finale prima di usarlo davvero.

Puoi:
- modificare direttamente il testo
- usare titoli e sottotitoli (`H1`, `H2`, `H3`, `H4`, `H5`)
- inserire immagini
- scegliere il layout delle immagini:
  - in linea
  - sinistra con testo
  - destra con testo
- copiare il contenuto finale
- esportare in Word
- stampare o salvare in PDF

Se il file audio originale è ancora nello stesso percorso, il player compare in basso nella preview.
Se il file è stato spostato, puoi usare **Ricollega audio**.

---

## 💾 Autosalvataggio e ripresa

El Sbobinator salva automaticamente i progressi mentre lavora.

Questo significa che:
- se chiudi l'app
- se il PC si spegne
- se l'elaborazione si interrompe
- se finisci la quota dell'API

... puoi spesso riprendere senza perdere tutto.

### Dove salva i dati temporanei?
In una cartella locale dentro la home utente, ad esempio:
- **Windows:** `C:\Users\TUO_UTENTE\.el_sbobinator_sessions\...`
- **macOS / Linux:** `~/.el_sbobinator_sessions/...`

### Cosa salva?
- blocchi parziali della sbobina
- progressi
- stato della sessione
- HTML finale modificato nell'anteprima

---

## 🎯 Cosa aspettarsi dai risultati

L'intelligenza artificiale non è perfetta.

La sbobina finale può contenere:
- qualche parola tecnica interpretata male
- qualche piccola ripetizione residua
- qualche punto da sistemare a mano

Detto questo, il vantaggio enorme è che l'app fa **quasi tutto il lavoro pesante** al posto tuo.

In pratica:
- non sostituisce del tutto una revisione umana
- ma ti fa risparmiare moltissime ore di lavoro manuale

Regola d'oro: **più l'audio è pulito, migliore sarà il risultato**.

---

## ❓ FAQ

### È sicuro? L'antivirus lo segnala come minaccia
Sì. Il codice sorgente è pubblico e verificabile.

Se Windows Defender o un antivirus segnala l'eseguibile come sospetto, nella maggior parte dei casi si tratta di un **falso positivo**. Succede spesso con gli eseguibili creati con PyInstaller e distribuiti da sviluppatori indipendenti senza firma digitale commerciale.

Se vuoi un controllo in più, puoi caricare il file su VirusTotal e verificare che eventuali segnalazioni siano poche e di tipo euristico/generico.

### Su Windows vedo una finestra nera o l'app non carica la UI
Molto probabilmente manca **Microsoft Edge WebView2 Runtime**.

Puoi installarlo da qui:
[Scarica WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703)

Dopo l'installazione, chiudi e riapri l'app.

### Devo installare Python o altri programmi?
No, se usi i pacchetti già compilati per Windows o macOS.

### Dove finisce il file finale?
Per impostazione predefinita, sul **Desktop** dell'utente.

### Posso modificare la sbobina dentro l'app?
Sì. Apri l'anteprima e modifica direttamente il testo prima di copiarlo o esportarlo.

### Posso inserire immagini?
Sì. Nell'editor puoi inserire immagini e disporle:
- in linea
- a sinistra con testo
- a destra con testo

### Cosa succede se finisco la quota di Gemini?
L'app può:
- mettersi in pausa
- chiederti una nuova chiave
- riprendere dal punto in cui era rimasta

Se premi **Annulla**, i progressi già salvati non vengono persi.

### Quali sono i limiti giornalieri dell'API?
Dipendono da Google e possono cambiare nel tempo.

Se hai dubbi, controlla direttamente in Google AI Studio la tua situazione attuale.

In generale:
- più l'audio è lungo
- più richieste servono
- più alta è la probabilità di raggiungere la quota gratuita

---

## ☕ Supporta il progetto

El Sbobinator è e resterà **100% gratuito e open-source**.

Se però ti ha fatto risparmiare ore di sbobinatura manuale e vuoi supportare il progetto:

- [Offrimi un caffè su Ko-fi](https://ko-fi.com/vimuw)

Grazie davvero e in bocca al lupo per gli esami.

---

## ⚖️ Disclaimer etico e legale

El Sbobinator è uno **strumento software locale** che facilita l'uso delle API pubbliche di Google Gemini.

Usandolo, accetti e comprendi che:

- **Uso personale e diritto d'autore:** le lezioni universitarie restano proprietà intellettuale dei rispettivi docenti. L'app va usata solo per studio personale. La diffusione pubblica o la vendita delle sbobine senza consenso resta responsabilità dell'utente.
- **Privacy:** l'app non ha server propri. Audio, testo e chiavi API non vengono inviati a infrastrutture del progetto. Il collegamento avviene tra il tuo dispositivo e i servizi Google che scegli di usare tramite la tua chiave.
- **Dati clinici sensibili:** non usare l'app con registrazioni che contengano dati sanitari, dati di pazienti o conversazioni cliniche reali.
- **Nessuna garanzia:** il software è distribuito con licenza MIT, quindi viene fornito "così com'è".

---

## 📝 Licenza

Questo progetto è open-source e distribuito sotto **Licenza MIT**.

Per i dettagli, vedi il file [LICENSE](/C:/Users/vimuw/Desktop/El%20Sbobinator/LICENSE).

---

## 🛠️ Costruire l'app dai sorgenti

Se vuoi compilare da solo i pacchetti nativi:

- **Windows:** usa [Costruisci_EXE_Windows.bat](/C:/Users/vimuw/Desktop/El%20Sbobinator/Costruisci_EXE_Windows.bat)
- **Windows (wrapper WebUI):** è presente anche [Costruisci_EXE_WebUI.bat](/C:/Users/vimuw/Desktop/El%20Sbobinator/Costruisci_EXE_WebUI.bat)
- **macOS:** usa [Costruisci_APP_Mac.command](/C:/Users/vimuw/Desktop/El%20Sbobinator/Costruisci_APP_Mac.command)

### Verifiche locali consigliate

```bash
python scripts/build_release.py deps --ui webui --dev
python scripts/build_release.py check --skip-npm-install
```

### Build locale

```bash
python scripts/build_release.py build --target windows --ui webui --install-deps --dev-deps
python scripts/build_release.py build --target macos --ui webui --install-deps --dev-deps
```

### Nota sulla UI

La **WebUI** è oggi l'unica interfaccia supportata per sviluppo, build e release.
I vecchi entrypoint desktop restano solo come alias compatibili verso la WebUI.
