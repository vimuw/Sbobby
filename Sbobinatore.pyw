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

# Usa il profilo utente per salvare la configurazione in modo persistente anche quando è un .exe creato con PyInstaller
USER_HOME = os.path.expanduser("~")
CONFIG_FILE = os.path.join(USER_HOME, ".sbobinatore_config.json")

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
Agisci come un 'Autore di Libri di Testo Universitari'. Trasforma l'audio della lezione in un MANUALE DI STUDIO formale, strutturato e pronto per la stampa.

REGOLA 1 — ZERO RIPETIZIONI (PRIORITÀ MASSIMA)
1. DIVIETO ASSOLUTO DI RIDONDANZA: Se un concetto, una definizione o un esempio compare più volte nell'audio (perché il docente lo riformula, lo ripete o ci ritorna sopra), scrivi quel concetto UNA SOLA VOLTA, nella posizione più logica del testo, fondendo tutte le formulazioni in un unico paragrafo completo e definitivo.
2. MAI RIFORMULARE: Non scrivere mai la stessa idea con parole diverse in punti diversi del testo. Un concetto = un paragrafo.
3. OVERLAP AUDIO: I blocchi audio si sovrappongono. Se le prime frasi di questo blocco ripetono contenuti già trascritti nel blocco precedente, IGNORALE completamente e riprendi solo dal punto in cui iniziano informazioni nuove.
4. CORREZIONI IN TEMPO REALE: Se il docente sbaglia e si corregge, trascrivi solo la versione corretta finale.

REGOLA 2 — STILE SCIENTIFICO IMPERSONALE
1. Elimina ogni traccia di linguaggio parlato: niente "come dicevamo", "ora vi elenco", "se ricordate bene", "vedete questa slide".
2. Scrivi tutto in terza persona impersonale ("Il sistema nervoso riceve..." non "Oggi parleremo del sistema nervoso").
3. ZERO CONVENEVOLI: Inizia immediatamente col contenuto. Non scrivere mai "Ecco la sbobina" o "In questo testo".
4. Nessun titolo con "(continuazione)" o "(segue)".

REGOLA 3 — STRUTTURA E FORMATTAZIONE
1. GERARCHIA TITOLI: Usa ## per i macro-argomenti e ### per le sotto-sezioni.
2. PARAGRAFI DENSI: Scrivi paragrafi corposi e fluidi, non frasi isolate. Unisci le frasi correlate.
3. ELENCHI PUNTATI (formato obbligatorio): Quando il docente elenca tipologie, componenti o fasi:
   - **Termine chiave:** Spiegazione completa in testo normale.
   Solo il termine è in grassetto, seguìto dai due punti.
4. MASSIMO 2 LIVELLI DI NESTING: Usa al massimo un sotto-elenco (○) sotto un elenco (●). MAI scendere a un terzo livello (■). Se servono più dettagli, integra nel testo della voce superiore.
5. GRASSETTI INLINE: Usa il **grassetto** nei paragrafi solo per i termini tecnici fondamentali quando vengono introdotti per la prima volta.
6. FORMULE MATEMATICHE: NON usare MAI la formattazione LaTeX per le formule (niente simboli $, niente \\frac, niente \\ln). Scrivi le equazioni in puro testo lineare chiaro e leggibile (esempio: E = (RT/zF) * ln(Esterno/Interno)). Se usi il LaTeX l'esportazione in PDF si corromperà.

REGOLA 4 — MASSIMO DETTAGLIO SENZA GONFIARE
Pulizia NON significa riassumere. Mantieni ogni spiegazione tecnica, esempio clinico e dettaglio d'esame. Ciò che devi eliminare sono le RIPETIZIONI e le riformulazioni, non le informazioni uniche.
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
Sei un revisore editoriale accademico. Ti passo una porzione di dispensa universitaria in Markdown.

IL TUO UNICO OBIETTIVO: eliminare ogni ripetizione e ridondanza.

REGOLE INVIOLABILI:
1. SILENZIO ASSOLUTO: Rispondi SOLO con il testo revisionato. Niente frasi introduttive.
2. CACCIA AI DOPPIONI: Cerca concetti, definizioni o spiegazioni che compaiono due o più volte (anche con parole diverse). FONDILI in un unico paragrafo definitivo nella posizione più logica, eliminando tutte le altre occorrenze.
3. FRASI RIDONDANTI: Se una frase non aggiunge informazioni nuove rispetto a quella precedente (es. "Questo processo è fondamentale..." seguito da "L'importanza di questo processo..."), tieni solo la versione migliore.
4. ELIMINA PARLATO RESIDUO: Rimuovi ogni traccia di linguaggio colloquiale rimasto.
5. NON RIASSUMERE MAI: Tutto ciò che NON è un doppione deve restare IDENTICO. Non accorciare spiegazioni tecniche, non eliminare dettagli unici, non semplificare.
6. MANTIENI LA FORMATTAZIONE: Conserva titoli (## e ###), elenchi (- **Termine:** Spiegazione), e la struttura originale.
7. MASSIMO 2 LIVELLI DI NESTING negli elenchi. Se trovi un terzo livello, integra il contenuto nel livello superiore.
8. FORMULE MATEMATICHE: NON usare MAI formattazione LaTeX (niente simboli $, niente \\frac). Scrivi le equazioni esclusivamente in testo lineare (es: V = (RT/F) * ln(Est/Int)).
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
            f.write("<style>body{font-family: Arial, sans-serif; line-height: 1.5; color: #000000; background-color: #ffffff; max-width: 900px; margin: auto; padding: 40px;} h1, h2, h3{color: #000000; margin-top: 1.5em; margin-bottom: 0.5em;} p, li{margin-bottom: 0.5em;}</style>\n")
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
# FIX TASKBAR ICON
# ==========================================
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("sbobinatore.ai.app")
except Exception:
    pass

# ==========================================
# INTERFACCIA GRAFICA CUSTOM-TKINTER
# ==========================================
class SbobinatoreModernApp(ctk.CTk):

    ACCENT = "#6C5CE7"
    ACCENT_HOVER = "#5A4BD1"
    SUCCESS = "#00B894"
    SUCCESS_HOVER = "#00A381"
    CARD_BG = "#1E1E2E"
    TERMINAL_BG = "#11111B"
    TERMINAL_FG = "#89B4FA"
    TEXT_DIM = "#6C7086"
    TEXT_BRIGHT = "#CDD6F4"
    BORDER = "#313244"

    def __init__(self):
        super().__init__()
        
        self.title("Sbobinatore AI PRO")
        self.geometry("850x700")
        self.configure(fg_color="#0F0F14")
        

        
        self.minsize(750, 600)

        self.file_path = None
        self.is_running = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        # TITOLO (centrato)
        self.title_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.title_frame.grid(row=0, column=0, padx=30, pady=(25, 5), sticky="ew")
        self.title_frame.grid_columnconfigure(0, weight=1)
        title_inner = ctk.CTkFrame(self.title_frame, fg_color="transparent")
        title_inner.grid(row=0, column=0)
        ctk.CTkLabel(title_inner, text="🎓 Sbobinatore AI", font=("Segoe UI", 26, "bold"), text_color="#CDD6F4").pack()

        # API KEY CARD
        self.api_card = ctk.CTkFrame(self, fg_color=self.CARD_BG, corner_radius=12, border_width=1, border_color=self.BORDER)
        self.api_card.grid(row=1, column=0, padx=30, pady=(15, 0), sticky="ew")
        self.api_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.api_card, text="🔑  API Key Gemini", font=("Segoe UI", 13, "bold"), text_color=self.TEXT_BRIGHT).grid(row=0, column=0, sticky="w", padx=(18, 12), pady=14)
        self.entry_api = ctk.CTkEntry(self.api_card, placeholder_text="Incolla la tua API Key qui...", show="*", font=("Segoe UI", 13), height=38, corner_radius=8, fg_color=self.TERMINAL_BG, border_color=self.BORDER, text_color=self.TEXT_BRIGHT)
        self.entry_api.grid(row=0, column=1, sticky="ew", padx=(0, 18), pady=14)
        config_data = load_config()
        self.entry_api.insert(0, config_data.get("api_key", ""))

        # DROP ZONE (area cliccabile centrata per caricare file)
        self.drop_zone = ctk.CTkFrame(self, fg_color=self.CARD_BG, corner_radius=12, border_width=2, border_color=self.BORDER, cursor="hand2")
        self.drop_zone.grid(row=2, column=0, padx=30, pady=15, sticky="ew")
        self.drop_zone.grid_columnconfigure(0, weight=1)

        self.drop_icon = ctk.CTkLabel(self.drop_zone, text="📂", font=("Segoe UI", 38), text_color=self.TEXT_DIM)
        self.drop_icon.grid(row=0, column=0, pady=(22, 4))

        self.lbl_file = ctk.CTkLabel(self.drop_zone, text="Clicca qui per caricare un file audio o video", font=("Segoe UI", 14, "bold"), text_color=self.TEXT_DIM)
        self.lbl_file.grid(row=1, column=0, pady=(0, 2))

        self.lbl_file_hint = ctk.CTkLabel(self.drop_zone, text="Formati supportati: MP3, M4A, WAV, MP4, AVI, MOV, MKV", font=("Segoe UI", 11), text_color="#45475A")
        self.lbl_file_hint.grid(row=2, column=0, pady=(0, 22))

        # Tutta la drop zone è cliccabile
        for widget in [self.drop_zone, self.drop_icon, self.lbl_file, self.lbl_file_hint]:
            widget.bind("<Button-1>", lambda e: self.scegli_file())

        # BOTTONE AVVIA
        self.btn_avvia = ctk.CTkButton(self, text="▶  AVVIA GENERAZIONE SBOBINA", height=52, font=("Segoe UI", 16, "bold"), corner_radius=10, fg_color=self.SUCCESS, hover_color=self.SUCCESS_HOVER, command=self.avvia_processo)
        self.btn_avvia.grid(row=3, column=0, padx=30, pady=(0, 15), sticky="ew")

        # TERMINALE OUTPUT
        self.console_card = ctk.CTkFrame(self, fg_color=self.CARD_BG, corner_radius=12, border_width=1, border_color=self.BORDER)
        self.console_card.grid(row=4, column=0, padx=30, pady=(0, 25), sticky="nsew")
        self.console_card.grid_columnconfigure(0, weight=1)
        self.console_card.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self.console_card, text="⚡ Output", font=("Segoe UI", 12, "bold"), text_color=self.TEXT_DIM).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        self.console = ctk.CTkTextbox(self.console_card, font=("Cascadia Code", 12), fg_color=self.TERMINAL_BG, text_color=self.TERMINAL_FG, corner_radius=8, wrap="word", border_width=0)
        self.console.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        sys.stdout = PrintRedirector(self.console)
        sys.stderr = PrintRedirector(self.console)
        print("Sbobinatore AI pronto all'uso.\n")

    def scegli_file(self, event=None):
        if self.is_running: return
        file_selezionato = filedialog.askopenfilename(
            title="Seleziona file multimediale",
            filetypes=[("File MultiMedia", "*.mp3 *.m4a *.mp4 *.wav *.avi *.mov *.mkv"), ("Tutti i file", "*.*")]
        )
        if file_selezionato:
            self.file_path = file_selezionato
            self.drop_icon.configure(text="✅")
            self.lbl_file.configure(text=os.path.basename(self.file_path), text_color=self.TEXT_BRIGHT)
            self.lbl_file_hint.configure(text="Clicca di nuovo per cambiare file")
            self.drop_zone.configure(border_color=self.SUCCESS)
            print(f"[+] File caricato: {os.path.basename(self.file_path)}")

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
        save_config(api_key)
        self.is_running = True
        self.btn_avvia.configure(state="disabled", fg_color=self.BORDER, text="⏳  Elaborazione in corso...")
        for w in [self.drop_zone, self.drop_icon, self.lbl_file, self.lbl_file_hint]:
            w.unbind("<Button-1>")
        self.entry_api.configure(state="disabled")
        print("\n" + "━"*50)
        print("  INIZIO PROCESSO DI ANALISI ED ESTRAZIONE AI")
        print("  Non chiudere l'app durante l'elaborazione.")
        print("━"*50 + "\n")
        thread = threading.Thread(target=esegui_sbobinatura, args=(self.file_path, api_key, self), daemon=True)
        thread.start()

    def processo_terminato(self):
        self.is_running = False
        self.after(0, self._ripristina_ui)

    def _ripristina_ui(self):
        self.btn_avvia.configure(state="normal", fg_color=self.SUCCESS, text="▶  AVVIA GENERAZIONE SBOBINA")
        for w in [self.drop_zone, self.drop_icon, self.lbl_file, self.lbl_file_hint]:
            w.bind("<Button-1>", lambda e: self.scegli_file())
        self.entry_api.configure(state="normal")

if __name__ == "__main__":
    app = SbobinatoreModernApp()
    app.mainloop()

