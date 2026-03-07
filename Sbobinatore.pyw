import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import sys
import time
import markdown
import os
import json
import tempfile
from google import genai
from google.genai import types
from moviepy.editor import AudioFileClip

# ==========================================
# CONFIGURAZIONE UI E FILE
# ==========================================
ctk.set_appearance_mode("Dark")  # Supporta "Dark", "Light", "System"
ctk.set_default_color_theme("blue")

# Usa il percorso assoluto della cartella dello script per evitare errori di permessi
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"api_key": ""}

def save_config(api_key):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"api_key": api_key}, f)


# ==========================================
# CLASSE PER REDIRECT DELL'OUTPUT NELLA GUI
# ==========================================
class PrintRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, string):
        # Evita le stringhe vuote o solo ritorni a capo per evitare glitch grafici con moviepy
        if string == '\r' or string == '\n': return
        self.text_widget.insert(ctk.END, string + "\n")
        self.text_widget.see(ctk.END)
        self.text_widget.update()

    def flush(self):
        pass


# ==========================================
# LOGICA PRINCIPALE DELLO SBOBINATORE
# ==========================================
def esegui_sbobinatura(nome_file_video, api_key_value, app_instance):
    try:
        if not api_key_value or api_key_value.strip() == "":
            print("Errore: Formato API Key non valido o assente.")
            return

        client = genai.Client(api_key=api_key_value.strip())
        
        blocco_minuti = 15
        blocco_secondi = blocco_minuti * 60
        sovrapposizione_secondi = 30
        passo_secondi = blocco_secondi - sovrapposizione_secondi
        memoria_precedente = ""
        testo_completo_sbobina = ""

        istruzioni_sistema = """
Agisci come un 'Autore di Libri di Testo Universitari'. Il tuo compito è prendere l'audio di una lezione e TRASFORMARLO in un MANUALE DI STUDIO eccellente, formale e strutturato, pronto per la stampa. L'output deve essere identico allo stile delle migliori dispense di Medicina.

REGOLA SUPREMA 1: LA PULIZIA DEL TESTO E L'ASSENZA DEL "PARLATO"
1. DIVIETO DI DOPPIONI: Fondi in un unico paragrafo fluido tutte le frasi ripetute, i giri di parole o i concetti ri-spiegati più volte dal docente.
2. ELIMINA LA RETORICA E IL PARLATO: Rimuovi frasi discorsive ("Ora vi elenco", "Oggi parleremo di", "Come vedete in questa slide"). Trasforma il discorso parlato in un testo scientifico oggettivo e distaccato ("Il sistema nervoso riceve...").
3. NESSUN TITOLO CON "(CONTINUAZIONE)": Vietate queste diciture.
4. CORREZIONI IN TEMPO REALE: Se chi parla sbaglia e si corregge, scrivi solo l'ultima versione corretta.
5. ZERO CONVENEVOLI: Inizia subito con il contenuto. Non usare mai frasi come "Ecco la sbobina", "In questo testo".

REGOLA SUPREMA 2: STRUTTURA E FORMATTAZIONE (STILE DISPENSA/MANUALE)
1. GERARCHIA TITOLI: Usa "## Titolo Argomento" per i macro-argomenti e "### Sotto-argomento" per le sezioni interne.
2. PARAGRAFI: Scrivi paragrafi densi ma separati. Non fare muri di testo.
3. ELENCHI A DIZIONARIO (FONDAMENTALE): Quando il docente elenca tipologie, componenti o fasi, usa rigorosamente gli elenchi puntati con questa esatta formattazione Markdown:
   - **Concetto Chiave:** Spiegazione estesa e dettagliata del concetto.
   (Metti in grassetto SOLO la parola/frase chiave all'inizio, seguita dai due punti, e lascia il resto in testo normale).
4. SOTTO-ELENCHI: Se un concetto ha delle sotto-categorie, indenta l'elenco puntato (usando pallini vuoti).
5. FORMULE E PRINCIPI: Se viene enunciata una legge importante o una regola, dedicale una riga a sé stante.
6. GRASSETTI INLINE: Usa il **grassetto** all'interno dei paragrafi normali SOLO per evidenziare i termini medici fondamentali o i concetti chiave quando vengono introdotti per la prima volta.

OBIETTIVO DI CONTENUTO: MASSIMO DETTAGLIO
Attenzione: la pulizia del testo NON significa riassumere! Tutto ciò che è un concetto unico è 'oggetto d'esame'. Mantieni ogni singola spiegazione tecnica, clinica, teorica o esempio con la massima profondità. Non tagliare le informazioni.

GESTIONE DELL'OVERLAP:
Se riprendi un discorso dal blocco precedente e senti frasi ripetute a causa dell'overlap temporale dell'audio, IGNORALE e unisci il nuovo testo in modo fluido al vecchio.
"""


        print(f"[*] Analisi del file originale in corso:\n{os.path.basename(nome_file_video)}")
        try:
            audio_completo = AudioFileClip(nome_file_video)
            durata_totale_secondi = audio_completo.duration
        except Exception as e:
            print(f"Errore caricamento audio. File corrotto o formato non supportato.\n{e}")
            return

        print(f"[*] Durata totale rilevata: {int(durata_totale_secondi / 60)} minuti.")
        print("[*] INIZIO FASE 1: Trascrizione a blocchi (Ogni blocco circa 15 min)")

        blocchi_totali = len(list(range(0, int(durata_totale_secondi), passo_secondi)))
        blocco_corrente_idx = 0

        for inizio_sec in range(0, int(durata_totale_secondi), passo_secondi):
            blocco_corrente_idx += 1
            fine_sec = min(inizio_sec + blocco_secondi, durata_totale_secondi)
            
            print(f"\n======================================")
            print(f"-> LAVORAZIONE BLOCCO AUDIO {blocco_corrente_idx} DI {blocchi_totali} (Da {inizio_sec}s a {int(fine_sec)}s)")
            
            # Salva i pezzi temporanei nella STESSA CARTELLA del file audio originale
            cartella_audio = os.path.dirname(os.path.abspath(nome_file_video))
            nome_chunk = os.path.join(cartella_audio, f"pezzo_temp_{inizio_sec}_{int(fine_sec)}.mp3")
            
            # 1. Taglio
            # Spiegazione per l'utente loggata direttamente in app
            print("   -> (1/3) Estrazione e taglio in corso (Può richiedere qualche secondo)...")
            chunk = audio_completo.subclip(inizio_sec, fine_sec)
            chunk.write_audiofile(nome_chunk, logger=None)
            chunk.close()
            
            # 2. Upload
            print("   -> (2/3) Caricamento sicuro nei server dell'Intelligenza Artificiale...")
            audio_file = client.files.upload(file=nome_chunk)
            while "PROCESSING" in str(audio_file.state):
                time.sleep(3)
                audio_file = client.files.get(name=audio_file.name)
                
            # 3. Generazione testuale
            print("   -> (3/3) Generazione sbobina dettagliata in corso (La fase più lunga)...")
            prompt_dinamico = "Ascolta questo blocco di lezione e crea la sbobina seguendo rigorosamente le istruzioni di sistema."
            if memoria_precedente:
                prompt_dinamico += f"\n\nATTENZIONE: Stai continuando una stesura. Questo è l'ultimo paragrafo che hai generato nel blocco precedente:\n\"...{memoria_precedente}\"\n\nRiprendi il discorso da qui IN MODO FLUIDO. Usa la stessa grandezza per i titoli e NON RIPETERE testualmente i concetti in sovrapposizione."
                
            successo = False
            for tent in range(3):
                try:
                    risposta = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[audio_file, prompt_dinamico],
                        config=types.GenerateContentConfig(
                            system_instruction=istruzioni_sistema,
                            temperature=0.35 
                        )
                    )
                    testo_generato = risposta.text.strip()
                    testo_completo_sbobina += f"\n\n{testo_generato}\n\n"
                    memoria_precedente = testo_generato[-1000:]
                    successo = True
                    break
                except Exception as e:
                    print(f"      [Server occupati. Riprovo in 30 secondi...]")
                    time.sleep(30)
                    
            if not successo:
                print("   [!] Errore critico sui server. Interrompo e passo alla Fase 2 con il lavoro fatto.")
                break
                
            # 4. Pulizia
            if os.path.exists(nome_chunk):
                try: os.remove(nome_chunk)
                except: pass
            client.files.delete(name=audio_file.name)
            
            # Piccola pausa tra chiamate
            time.sleep(15)

        audio_completo.close()

        # ==========================================
        # FASE 2: REVISIONE LOGICA E CUCITURA DOPPIONI
        # ==========================================
        print("\n======================================")
        print("[*] INIZIO FASE 2: REVISIONE FINALE E CUCITURA DOPPIONI")

        paragrafi = testo_completo_sbobina.split("\n\n")
        macro_blocchi = []
        blocco_corrente = ""
        limite_caratteri = 15000

        for p in paragrafi:
            if len(blocco_corrente) + len(p) > limite_caratteri:
                macro_blocchi.append(blocco_corrente)
                blocco_corrente = p + "\n\n"
            else:
                blocco_corrente += p + "\n\n"
        if blocco_corrente.strip():
            macro_blocchi.append(blocco_corrente)
            
        print(f"Il documento è stato diviso in {len(macro_blocchi)} macro-sezioni. Revisione grammaticale in corso...")

        testo_finale_revisionato = ""

        prompt_revisione = """
Sei un correttore di bozze accademico, un automa precisissimo. Ti sto passando una grossa porzione di una dispensa universitaria in formato Markdown.
Il tuo UNICO scopo è trovare e fondere ripetizioni, frasi sdoppiate o concetti identici ripetuti a breve distanza, perfezionando la fluidità e innalzando il tono.

REGOLE ASSOLUTE:
1. SILENZIO ASSOLUTO: Rispondi ESCLUSIVAMENTE con il testo revisionato. Niente convenevoli o frasi introduttive (es. "Ecco la dispensa").
2. FUSIONE DOPPIONI: Se trovi concetti ripetuti o prolissi, FONDILI in un unico paragrafo fluido ed elegante.
3. ELIMINA IL PARLATO RESIDUO: Se sono rimaste frasi tipiche del parlato sciolto ("come dicevamo prima"), rimuovile. Il testo deve sembrare un libro stampato.
4. COPIA-INCOLLA DEL RESTO: Tutto ciò che NON è un doppione deve rimanere ESATTAMENTE IDENTICO al testo originale, senza riassumere o tagliare dettagli tecnici o clinici.
5. MANTIENI LA FORMATTAZIONE ORIGINALE: Conserva rigorosamente i titoli (## e ###), i paragrafi e gli elenchi con l'esatto formato "- **Termine:** Spiegazione".
"""

        for i, blocco in enumerate(macro_blocchi, 1):
            print(f"   -> Revisione Macro-blocco {i} di {len(macro_blocchi)}...")
            successo_revisione = False
            for tent in range(3):
                try:
                    risposta_rev = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[blocco, prompt_revisione],
                        config=types.GenerateContentConfig(
                            temperature=0.1 
                        )
                    )
                    testo_finale_revisionato += f"\n\n{risposta_rev.text.strip()}\n\n"
                    successo_revisione = True
                    break
                except Exception as e:
                    print(f"      [Errore di coda. Riprovo in 20 secondi...]")
                    time.sleep(20)
                    
            if not successo_revisione:
                print(f"   [!] Errore prolungato nella revisione. Salvo il blocco {i} così com'è per evitare perdite di dati.")
                testo_finale_revisionato += f"\n\n{blocco}\n\n"
            time.sleep(15)

        # ==========================================
        # 3. SALVATAGGIO FINALE IN HTML
        # ==========================================
        base_name = os.path.basename(nome_file_video)
        nome_puro = os.path.splitext(base_name)[0]
        
        # Salva la sbobina finita sempre sul Desktop
        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        nome_file_output = os.path.join(desktop_dir, f"{nome_puro}_Sbobina.html")

        if not base_name: 
            nome_file_output = os.path.join(desktop_dir, "Sbobina_Definitiva.html")

        with open(nome_file_output, "w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html>\n<html>\n<head>\n<meta charset='utf-8'>\n")
            f.write("<style>body{font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height:1.6; padding: 30px; max-width: 900px; margin: auto; background-color: #fcfcfc;} h2, h3{color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px;}</style>\n")
            f.write("</head>\n<body>\n")
            f.write(markdown.markdown(testo_finale_revisionato))
            f.write("\n</body>\n</html>")

        print(f"\n======================================")
        print("SBOBINATURA COMPLETATA CON SUCCESSO!")
        print(f"File salvato in: {nome_file_output}")
    
    except Exception as e:
        print(f"\n[X] ERRORE IMPREVISTO DURANTE L'ESECUZIONE:\n{e}")
    finally:
        app_instance.processo_terminato()


# ==========================================
# INTERFACCIA GRAFICA CUSTOM-TKINTER (PREMIUM UI)
# ==========================================
class SbobinatoreModernApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Configurazione finestra
        self.title("Sbobinatore AI Premium")
        self.geometry("800x650")
        self.minsize(700, 550)
        
        self.file_path = None
        self.is_running = False

        # Configurazione layout griglia
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # ------------------------
        # 1. HEADER (API KEY)
        # ------------------------
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=20, pady=(20, 0), sticky="ew")
        self.header_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.header_frame, text="⚙️ INSERISCI LA TUA API KEY GEMINI:", font=("Roboto", 13, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        self.entry_api = ctk.CTkEntry(self.header_frame, placeholder_text="Incolla l'API Key qui (inizia spesso con AIzaSy...)", show="*")
        self.entry_api.grid(row=0, column=1, sticky="ew")
        
        # Carica eventuale chiave precedente
        config_data = load_config()
        self.entry_api.insert(0, config_data.get("api_key", ""))

        # ------------------------
        # 2. SELEZIONE FILE
        # ------------------------
        self.file_frame = ctk.CTkFrame(self, corner_radius=15)
        self.file_frame.grid(row=1, column=0, padx=20, pady=20, sticky="ew")
        self.file_frame.grid_columnconfigure(0, weight=1)

        self.lbl_file = ctk.CTkLabel(self.file_frame, text="Nessun file selezionato.\nScegli la registrazione audio o il file video della lezione.", font=("Roboto", 14), text_color="gray")
        self.lbl_file.grid(row=0, column=0, pady=(20, 10))

        self.btn_sfoglia = ctk.CTkButton(self.file_frame, text="Carica Audio / Video...", font=("Roboto", 14, "bold"), fg_color="#3498db", hover_color="#2980b9", command=self.scegli_file)
        self.btn_sfoglia.grid(row=1, column=0, pady=(0, 20))

        # ------------------------
        # 3. AVVIO
        # ------------------------
        self.btn_avvia = ctk.CTkButton(self, text="▶ AVVIA GENERAZIONE SBOBINA", height=50, font=("Roboto", 18, "bold"), fg_color="#2ecc71", hover_color="#27ae60", command=self.avvia_processo)
        self.btn_avvia.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="ew")

        # ------------------------
        # 4. CONSOLE E LOGS
        # ------------------------
        self.console_frame = ctk.CTkFrame(self)
        self.console_frame.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.console_frame.grid_columnconfigure(0, weight=1)
        self.console_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.console_frame, text="TERMINALE PROCESSI AI:", font=("Roboto", 12, "bold"), text_color="gray").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        
        self.console = ctk.CTkTextbox(self.console_frame, font=("Consolas", 13), fg_color="#1e1e1e", text_color="#00ff00", wrap="word")
        self.console.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        sys.stdout = PrintRedirector(self.console)
        sys.stderr = PrintRedirector(self.console)

        print("Sbobinatore AI Inizializzato (Modalità Premium).")
        print("Tutte le operazioni verranno loggate in dettaglio in questa finestra.")
        print("Nessuna fastidiosa finestra del CMD in background.\n")

    def scegli_file(self):
        if self.is_running: return
        file_selezionato = filedialog.askopenfilename(
            title="Seleziona file multimediale",
            filetypes=[("File MultiMedia", "*.mp3 *.m4a *.mp4 *.wav *.avi *.mov *.mkv"), ("Tutti i file", "*.*")]
        )
        if file_selezionato:
            self.file_path = file_selezionato
            self.lbl_file.configure(text=os.path.basename(self.file_path), text_color="white")
            print(f"[*] FILE CARICATO CON SUCCESSO: {os.path.basename(self.file_path)}")

    def avvia_processo(self):
        api_key = self.entry_api.get().strip()
        
        if not api_key:
            messagebox.showwarning("Errore API", "Devi inserire la tua chiave API Gemini prima di iniziare!")
            return
            
        if not self.file_path:
            messagebox.showwarning("Errore File", "Devi prima selezionare un file audio o video dal computer!")
            return
            
        if self.is_running:
            return
            
        # Salva la chiave API per le prossime volte
        save_config(api_key)

        self.is_running = True
        self.btn_avvia.configure(state="disabled", fg_color="gray", text="⏳ ELABORAZIONE IN CORSO... (Guarda il terminale in basso)")
        self.btn_sfoglia.configure(state="disabled")
        self.entry_api.configure(state="disabled")

        print("\n" + "="*50)
        print("INIZIO PROCESSO DI ANALISI ED ESTRAZIONE AI")
        print("Mettiti comodo. Puoi rimpicciolire l'app se vuoi, ma NON CHIUdERLA.")
        print("="*50 + "\n")

        thread = threading.Thread(target=esegui_sbobinatura, args=(self.file_path, api_key, self), daemon=True)
        thread.start()

    def processo_terminato(self):
        self.is_running = False
        self.after(0, self._ripristina_ui)

    def _ripristina_ui(self):
        self.btn_avvia.configure(state="normal", fg_color="#2ecc71", text="▶ AVVIA GENERAZIONE SBOBINA")
        self.btn_sfoglia.configure(state="normal")
        self.entry_api.configure(state="normal")

if __name__ == "__main__":
    app = SbobinatoreModernApp()
    app.mainloop()
