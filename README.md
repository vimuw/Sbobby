# Sbobby 🤖

Sbobby e' un'app gratuita e open-source che trasforma le registrazioni audio delle lezioni in **sbobine** dettagliate.

L'intelligenza artificiale (basata sul modello Gemini 2.5 Flash) ascolta la registrazione e scrive una dispensa eliminando i difetti tipici del parlato (ripetizioni, esitazioni, retorica) e strutturando il discorso con paragrafi chiari ed elenchi puntati.

---

## 🚀 Come iniziare

### 1) Scaricare il programma
1. Apri la sezione **Releases** di GitHub.
2. Scarica il file giusto per il tuo sistema operativo:
   - Windows: `Sbobby-Windows.exe`
   - macOS: `Sbobby-MacOS.zip`
3. Salva il file dove preferisci (ad esempio sul Desktop).

Nota: su Windows il programma puo' anche chiamarsi `Sbobby.exe` (e' lo stesso). Se vuoi, puoi rinominare `Sbobby-Windows.exe` in `Sbobby.exe`.

### 2) Creare la tua chiave API di Gemini (gratis)
Per usare Sbobby serve una API key di Google Gemini.

Creare la API key e' gratis. L'uso delle API ha dei limiti (quota): vedi la sezione FAQ piu' sotto.

1. Vai su [Google AI Studio](https://aistudio.google.com/app/apikey) e accedi con il tuo account Google.
2. Clicca `Create API Key`.
3. Seleziona `Create API key in a new project`.
4. Copia la chiave (di solito inizia con `AIzaSy...`).

---

## ✅ Requisiti
- Connessione Internet.
- Un account Google per creare la API key.
- Un file audio/video supportato (MP3, M4A, WAV, MP4, MKV e simili).

---

## ▶️ Come avviare l'app
E' un programma plug and play: non devi installare Python.

### 💻 Windows
1. Fai doppio clic su `Sbobby-Windows.exe` (o `Sbobby.exe`).
2. Se Windows SmartScreen/antivirus lo blocca al primo avvio, vedi FAQ.

Nota: al primo avvio puo' metterci qualche secondo (il file contiene tutto il necessario per funzionare).

### 🍎 macOS
1. Estrai `Sbobby-MacOS.zip`.
2. Avvia `Sbobby.app` (puoi trascinarla in Applicazioni).
3. Se macOS blocca l'avvio per "sviluppatore non identificato": tasto destro sull'app, poi **Apri**.

---

## 📚 Come si usa
1. Incolla in alto la tua **API key** (l'app la salva, quindi non devi reinserirla ogni volta).
2. Seleziona il file audio/video.
3. Premi **AVVIA**.
4. Segui l'avanzamento nel log dentro l'app.
5. A fine processo troverai un file `.html` sul tuo **Desktop**, pronto per il copia-incolla su Google Docs.

---

## 💾 Autosalvataggio e ripresa (importante)
Sbobby salva automaticamente i progressi mentre lavora. Se chiudi l'app, crasha il PC o finisci la quota giornaliera puoi riprendere senza perdere tutto.

- Dove salva: in una cartella locale nella home utente (es. `C:\Users\TUO_UTENTE\.sbobby_sessions\...` su Windows o `~/.sbobby_sessions/...` su macOS).
- Cosa salva: testi parziali (sbobine per chunk), progressi e stati di avanzamento.
- Quando riprendi: se selezioni lo stesso file audio, Sbobby puo' proporti di:
  - riutilizzare i risultati gia' pronti (riesporta l'HTML senza consumare richieste)
  - ricominciare da zero (cancella la sessione e rifa' tutto da capo)

---

## 🎯 Cosa aspettarsi dai risultati (nota sull'AI)
L'intelligenza artificiale non e' perfetta. La sbobina puo' contenere piccoli errori di trascrizione o termini tecnici interpretati male. In rari casi possono comparire piccole ripetizioni, soprattutto vicino alle giunzioni tra blocchi.

L'obiettivo e' farti risparmiare la maggior parte del lavoro: una rapida rilettura finale e' comunque consigliata.

---

## ❓ FAQ

### Windows SmartScreen o antivirus blocca l'app
E' comune per applicazioni nuove/non firmate.

- SmartScreen: clicca `Ulteriori informazioni` e poi `Esegui comunque`.
- Antivirus: controlla la cronologia delle minacce e scegli `Consenti nel dispositivo` o `Ripristina`.

### Limiti giornalieri dell'API (quota)
Google Gemini ha limiti/quote di utilizzo che possono cambiare nel tempo (dipendono dal tuo account/progetto).

In generale, Sbobby divide l'audio in blocchi da circa 15 minuti: 1 richiesta per ogni blocco, piu' alcune richieste extra di revisione/merge (dipende dalla durata totale).

Se vedi l'errore di limite giornaliero, puoi:
- inserire un'altra API key (di un account Google diverso) quando l'app te la chiede
- fermarti e riprendere piu' tardi: l'app salva i progressi e puoi continuare

---

## ⚖️ Disclaimer etico e legale (importante)
Sbobby e' uno strumento locale che facilita l'interazione tra il tuo PC e le API pubbliche di Google Gemini.

Usando l'app, accetti che:
- Diritto d'autore e uso personale: le lezioni possono essere protette da diritto d'autore; usa le sbobine solo per studio personale.
- Privacy: l'audio viene inviato ai server di Google tramite API per la trascrizione/generazione. Sbobby non ha server propri e non carica nulla su server dell'autore; l'autosalvataggio salva testi localmente in `~/.sbobby_sessions`.
- Divieto per dati clinici/pazienti: non usare l'app con audio contenente dati sanitari o conversazioni con pazienti reali.
- Nessuna garanzia: il software e' fornito "cosi' com'e'", senza garanzie (Licenza MIT).

---

## 📝 Licenza
Questo progetto e' open-source e distribuito sotto Licenza MIT. Vedi [LICENSE](LICENSE).

---

## 🛠️ Costruire l'app dai sorgenti
Se vuoi compilare da sorgenti i file eseguibili nativi (`.exe` o `.app`), usa gli script inclusi:
- Windows: `Costruisci_EXE_Windows.bat` (crea `dist\Sbobby.exe`)
- macOS: `Costruisci_APP_Mac.command` (crea `dist/Sbobby.app`)

---

## ☕ Supporta il progetto
Se ti e' stato utile e vuoi supportare lo sviluppo:
- [Offrimi un caffe' su Ko-fi](https://ko-fi.com/vimuw)
