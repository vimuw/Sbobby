import customtkinter as ctk

from tkinter import filedialog, messagebox
import threading
import sys
import time
import platform
import tempfile
import markdown
import os
import json
from google import genai
from google.genai import types
import imageio_ffmpeg
import subprocess

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
# FONT CROSS-PLATFORM
# ==========================================
if platform.system() == "Darwin":  # macOS
    FONT_UI = "Helvetica"
    FONT_MONO = "Menlo"
else:
    FONT_UI = "Segoe UI"
    FONT_MONO = "Cascadia Code"

# ==========================================
# PROMPT AI (estratti per facilità di modifica)
# ==========================================
PROMPT_SISTEMA = """
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

PROMPT_REVISIONE = """
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


# ==========================================
# CLASSE PER REDIRECT DELL'OUTPUT NELLA GUI
# ==========================================
class PrintRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, string):
        if string == '\r' or string == '\n': return
        # Usa after() per garantire thread-safety con Tkinter
        self.text_widget.after(0, self._append, string)

    def _append(self, string):
        self.text_widget.configure(state="normal")
        self.text_widget.insert(ctk.END, string + "\n")
        self.text_widget.see(ctk.END)
        self.text_widget.configure(state="disabled")

    def flush(self):
        pass


# ==========================================
# LOGICA PRINCIPALE DELLO SBOBINATORE
# ==========================================
def esegui_sbobinatura(nome_file_video, api_key_value, app_instance):
    audio_completo = None
    app_instance.file_temporanei = []  # Condiviso con l'app per pulizia alla chiusura
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

        istruzioni_sistema = PROMPT_SISTEMA

        print(f"[*] Analisi del file originale in corso:\n{os.path.basename(nome_file_video)}")
        try:
            # Ricava durata audio con ffprobe leggero
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            comando_probe = [
                ffmpeg_exe, "-v", "error", "-show_entries",
                "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                nome_file_video
            ]
            risultato = subprocess.run(comando_probe, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
            durata_totale_secondi = float(risultato.stdout.strip())
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
            
            # Salva i pezzi temporanei nella cartella TEMP del sistema operativo
            nome_chunk = os.path.join(tempfile.gettempdir(), f"sbobinatore_temp_{inizio_sec}_{int(fine_sec)}.mp3")
            app_instance.file_temporanei.append(nome_chunk)
            
            # 1. Taglio
            # Spiegazione per l'utente loggata direttamente in app
            print("   -> (1/3) Estrazione e taglio in corso (Può richiedere qualche secondo)...")
            durata_cut = fine_sec - inizio_sec
            comando_cut = [
                ffmpeg_exe, "-y", "-i", nome_file_video,
                "-ss", str(inizio_sec), "-t", str(durata_cut),
                "-q:a", "0", "-map", "a", nome_chunk
            ]
            subprocess.run(comando_cut, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 2. Upload
            print("   -> (2/3) Caricamento sicuro nei server di google...")
            audio_file = client.files.upload(file=nome_chunk)
            while "PROCESSING" in str(audio_file.state):
                time.sleep(3)
                audio_file = client.files.get(name=audio_file.name)
                
            # 3. Generazione testuale
            print("   -> (3/3) Generazione sbobina in corso (La fase più lunga)...")
            prompt_dinamico = "Ascolta questo blocco di lezione e crea la sbobina seguendo rigorosamente le istruzioni di sistema."
            if memoria_precedente:
                prompt_dinamico += f"\n\nATTENZIONE: Stai continuando una stesura. Questo è l'ultimo paragrafo che hai generato nel blocco precedente:\n\"...{memoria_precedente}\"\n\nRiprendi il discorso da qui IN MODO FLUIDO. Usa la stessa grandezza per i titoli e NON RIPETERE testualmente i concetti in sovrapposizione."
                
            successo = False
            rate_limit = False
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
                    app_instance.aggiorna_progresso(0.7 * blocco_corrente_idx / blocchi_totali)
                    break
                except Exception as e:
                    errore = str(e).lower()
                    if '429' in errore or 'resource_exhausted' in errore or 'quota' in errore:
                        print("\n" + "="*50)
                        print("⛔ LIMITE GIORNALIERO RAGGIUNTO!")
                        print("="*50)
                        print("Hai esaurito le richieste gratuite di oggi.")
                        print("Cosa puoi fare:")
                        print("  1. Aspetta domani mattina (~ore 9:00 italiane)")
                        print("  2. Usa una API Key di un altro account Google")
                        print("="*50)
                        rate_limit = True
                        break
                    print(f"      [Server occupati. Riprovo in 30 secondi...]")
                    time.sleep(30)
                    
            if rate_limit:
                break
            if not successo:
                print("   [!] Errore critico sui server. Interrompo e passo alla Fase 2 con il lavoro fatto.")
                break
                
            # 4. Pulizia
            if os.path.exists(nome_chunk):
                try: os.remove(nome_chunk)
                except: pass
            client.files.delete(name=audio_file.name)
            
            # Piccola pausa tra chiamate per evitare rate limit
            time.sleep(5)

        # ==========================================
        # FASE 2: REVISIONE LOGICA E CUCITURA DOPPIONI
        # ==========================================
        print("\n======================================")
        print("[*] INIZIO FASE 2: REVISIONE FINALE (Eliminazione Doppioni, Correzione grammaticale, Miglioramento leggibilità, etc.)")

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
            
        print(f"Il documento è stato diviso in {len(macro_blocchi)} macro-sezioni per mantenere il livello di dettaglio. Revisione in corso...")

        testo_finale_revisionato = ""

        prompt_revisione = PROMPT_REVISIONE

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
                    errore = str(e).lower()
                    if '429' in errore or 'resource_exhausted' in errore or 'quota' in errore:
                        print("\n⛔ LIMITE GIORNALIERO RAGGIUNTO durante la revisione!")
                        print("   Salvo tutto il lavoro fatto finora senza revisione.")
                        # Salva tutti i blocchi rimanenti senza revisione
                        testo_finale_revisionato += f"\n\n{blocco}\n\n"
                        for j, b_rimanente in enumerate(macro_blocchi[i:], i+1):
                            testo_finale_revisionato += f"\n\n{b_rimanente}\n\n"
                        successo_revisione = True  # Evita il doppio salvataggio sotto
                        break
                    print(f"      [Errore di coda. Riprovo in 20 secondi...]")
                    time.sleep(20)
                    
            if '429' in str(locals().get('e', '')).lower() or 'resource_exhausted' in str(locals().get('e', '')).lower():
                break  # Esci dal loop dei macro_blocchi
                
            if not successo_revisione:
                print(f"   [!] Errore prolungato nella revisione. Salvo il blocco {i} così com'è per evitare perdite di dati.")
                testo_finale_revisionato += f"\n\n{blocco}\n\n"
            app_instance.aggiorna_progresso(0.7 + 0.3 * (i / len(macro_blocchi)))
            time.sleep(5)

        # ==========================================
        # 3. SALVATAGGIO FINALE IN HTML
        # ==========================================
        base_name = os.path.basename(nome_file_video)
        nome_puro = os.path.splitext(base_name)[0]
        
        # Salva la sbobina finita *nella stessa cartella* del file multimediale analizzato
        cartella_origine = os.path.dirname(os.path.abspath(nome_file_video))
        nome_file_output = os.path.join(cartella_origine, f"{nome_puro}_Sbobina.html")

        if not base_name: 
            nome_file_output = os.path.join(cartella_origine, "Sbobina_Definitiva.html")

        with open(nome_file_output, "w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html>\n<html>\n<head>\n<meta charset='utf-8'>\n")
            f.write("<style>body{font-family: Arial, sans-serif; line-height: 1.5; color: #000000; background-color: #ffffff; max-width: 900px; margin: auto; padding: 40px;} h1, h2, h3{color: #000000; margin-top: 1.5em; margin-bottom: 0.5em;} p, li{margin-bottom: 0.5em;}</style>\n")
            f.write("</head>\n<body>\n")
            f.write(markdown.markdown(testo_finale_revisionato))
            f.write("\n</body>\n</html>")

        print(f"\n======================================")
        print("SBOBINATURA COMPLETATA CON SUCCESSO!")
        print(f"File salvato in: {cartella_origine}")
        
        # Forza l'aggiornamento visivo del file sul Desktop in Windows
        if platform.system() == "Windows":
            try:
                import ctypes
                ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
            except Exception:
                pass
    
    except Exception as e:
        print(f"\n[X] ERRORE IMPREVISTO DURANTE L'ESECUZIONE:\n{e}")
    finally:
        for f in app_instance.file_temporanei:
            try:
                if os.path.exists(f): os.remove(f)
            except: pass
        app_instance.file_temporanei = []
        app_instance.aggiorna_progresso(1.0)
        app_instance.processo_terminato()


# ==========================================
# INTERFACCIA GRAFICA CUSTOM-TKINTER
# ==========================================
from tkinterdnd2 import TkinterDnD, DND_FILES

class SbobbyApp(ctk.CTk, TkinterDnD.DnDWrapper):

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
        self.TkdndVersion = TkinterDnD._require(self)
        
        self.title("Sbobby")
        self.geometry("850x720")
        self.configure(fg_color="#0F0F14")
        self.minsize(750, 620)
        
        self.minsize(750, 620)

        self.file_path = None
        self.is_running = False
        self.file_temporanei = []  # Lista file temp condivisa col thread

        # Intercetta la chiusura della finestra per pulire i file temporanei
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # SPACING TOP
        ctk.CTkFrame(self, fg_color="transparent", height=15).grid(row=0, column=0)

        # API KEY CARD
        self.api_card = ctk.CTkFrame(self, fg_color=self.TERMINAL_BG, corner_radius=12, border_width=1, border_color=self.BORDER)
        self.api_card.grid(row=1, column=0, padx=30, pady=(15, 0), sticky="ew")
        self.api_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.api_card, text="🔑 API Key Gemini", font=(FONT_UI, 14), text_color=self.TEXT_DIM).grid(row=0, column=0, sticky="w", padx=(18, 12), pady=14)
        self.entry_api = ctk.CTkEntry(self.api_card, placeholder_text="Incolla la tua API Key qui...", show="*", font=(FONT_UI, 13), height=38, corner_radius=8, fg_color=self.CARD_BG, border_color=self.BORDER, text_color=self.TEXT_BRIGHT)
        self.entry_api.grid(row=0, column=1, sticky="ew", padx=(0, 18), pady=14)
        config_data = load_config()
        self.entry_api.insert(0, config_data.get("api_key", ""))

        # DROP ZONE (area cliccabile centrata per caricare file)
        self.drop_zone = ctk.CTkFrame(self, fg_color=self.CARD_BG, corner_radius=16, border_width=2, border_color=self.BORDER, cursor="hand2")
        self.drop_zone.grid(row=2, column=0, padx=30, pady=15, sticky="ew")
        self.drop_zone.grid_columnconfigure(0, weight=1)

        self.drop_icon = ctk.CTkLabel(self.drop_zone, text="📥", font=(FONT_UI, 44), text_color=self.TEXT_DIM)
        self.drop_icon.grid(row=0, column=0, pady=(35, 8))

        self.lbl_file = ctk.CTkLabel(self.drop_zone, text="Carica Lezione Audio/Video", font=(FONT_UI, 18, "bold"), text_color=self.TEXT_BRIGHT)
        self.lbl_file.grid(row=1, column=0, pady=(0, 4))

        self.lbl_file_hint = ctk.CTkLabel(self.drop_zone, text="Supporta MP3, M4A, WAV, MP4, MKV", font=(FONT_UI, 12), text_color=self.TEXT_DIM)
        self.lbl_file_hint.grid(row=2, column=0, pady=(0, 35))

        # Tutta la drop zone è cliccabile e accetta il drag&drop
        for widget in [self.drop_zone, self.drop_icon, self.lbl_file, self.lbl_file_hint]:
            widget.bind("<Button-1>", lambda e: self.scegli_file())
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind('<<Drop>>', self._on_file_drop)

        # BOTTONE AVVIA
        self.btn_avvia = ctk.CTkButton(self, text="▶  AVVIA GENERAZIONE SBOBINA", height=52, font=(FONT_UI, 16, "bold"), corner_radius=10, fg_color=self.SUCCESS, hover_color=self.SUCCESS_HOVER, command=self.avvia_processo)
        self.btn_avvia.grid(row=3, column=0, padx=30, pady=(0, 15), sticky="ew")

        # TERMINALE OUTPUT
        self.console_card = ctk.CTkFrame(self, fg_color=self.CARD_BG, corner_radius=12, border_width=1, border_color=self.BORDER)
        self.console_card.grid(row=4, column=0, padx=30, pady=(0, 15), sticky="nsew")
        self.console_card.grid_columnconfigure(0, weight=1)
        self.console_card.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(self.console_card, text="⚡ Log Eventi", font=(FONT_UI, 12, "bold"), text_color=self.TEXT_DIM).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        self.progress_bar = ctk.CTkProgressBar(self.console_card, height=6, corner_radius=3, fg_color=self.TERMINAL_BG, progress_color=self.ACCENT)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))
        self.progress_bar.set(0)
        self.console = ctk.CTkTextbox(self.console_card, font=(FONT_MONO, 12), fg_color=self.TERMINAL_BG, text_color=self.TERMINAL_FG, corner_radius=8, wrap="word", border_width=0)
        self.console.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.console.configure(state="disabled")

        sys.stdout = PrintRedirector(self.console)
        sys.stderr = PrintRedirector(self.console)
        print("Sbobby pronto all'uso. 🎓\n")
        
        # CREDITS FOOTER
        self.footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.footer_frame.grid(row=5, column=0, pady=(0, 10), sticky="ew")
        
        # Testo e link affiancati manualmente simulando un testo
        import webbrowser
        lbl_center = ctk.CTkFrame(self.footer_frame, fg_color="transparent")
        lbl_center.pack(expand=True)
        
        ctk.CTkLabel(lbl_center, text="Sbobby — Progetto open-source | ", font=(FONT_UI, 11), text_color=self.TEXT_DIM).pack(side="left")
        
        lk_gh = ctk.CTkLabel(lbl_center, text="GitHub", font=(FONT_UI, 11, "underline"), text_color=self.ACCENT, cursor="hand2")
        lk_gh.pack(side="left")
        lk_gh.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/vimuw/Sbobinatore-AI"))
        
        ctk.CTkLabel(lbl_center, text=" • ", font=(FONT_UI, 11), text_color=self.TEXT_DIM).pack(side="left", padx=5)
        
        lk_kofi = ctk.CTkLabel(lbl_center, text="☕ Offrimi un caffè su Ko-fi", font=(FONT_UI, 11, "underline"), text_color=self.SUCCESS, cursor="hand2")
        lk_kofi.pack(side="left")
        lk_kofi.bind("<Button-1>", lambda e: webbrowser.open("https://ko-fi.com/vimuw"))

    def _on_file_drop(self, event):
        if self.is_running: return
        file_path = event.data
        if file_path.startswith('{') and file_path.endswith('}'):
            file_path = file_path[1:-1]
            
        estensioni_valide = [".mp3", ".m4a", ".mp4", ".wav", ".avi", ".mov", ".mkv"]
        if any(file_path.lower().endswith(ext) for ext in estensioni_valide):
            self._setta_file(file_path)
        else:
            messagebox.showwarning("Formato non valido", "Trascina un file multimediale valido (Audio/Video).")

    def _setta_file(self, percorso_file):
        self.file_path = percorso_file
        self.drop_icon.configure(text="✅")
        self.lbl_file.configure(text=os.path.basename(self.file_path), text_color=self.TEXT_BRIGHT)
        self.lbl_file_hint.configure(text="Clicca di nuovo per cambiare file")
        self.drop_zone.configure(border_color=self.SUCCESS)
        print(f"[+] File caricato: {os.path.basename(self.file_path)}")

    def scegli_file(self, event=None):
        if self.is_running: return
        file_selezionato = filedialog.askopenfilename(
            title="Seleziona file multimediale",
            filetypes=[("File MultiMedia", "*.mp3 *.m4a *.mp4 *.wav *.avi *.mov *.mkv"), ("Tutti i file", "*.*")]
        )
        if file_selezionato:
            self._setta_file(file_selezionato)

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
        # Validazione rapida della API Key
        try:
            test_client = genai.Client(api_key=api_key)
            test_client.models.generate_content(
                model='gemini-2.5-flash',
                contents='test',
                config=types.GenerateContentConfig(max_output_tokens=1)
            )
        except Exception as e:
            messagebox.showerror("API Key non valida", f"La chiave API non funziona.\nControlla di averla copiata correttamente.\n\nErrore: {e}")
            return
        save_config(api_key)
        self.is_running = True
        self.progress_bar.set(0)
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
        self.progress_bar.set(0)
        for w in [self.drop_zone, self.drop_icon, self.lbl_file, self.lbl_file_hint]:
            w.bind("<Button-1>", lambda e: self.scegli_file())
        self.entry_api.configure(state="normal")

    def aggiorna_progresso(self, valore):
        """Aggiorna la barra di progresso in modo thread-safe."""
        self.after(0, self.progress_bar.set, min(valore, 1.0))

    def _on_close(self):
        """Pulisce i file temporanei rimasti prima di chiudere l'applicazione."""
        if self.is_running:
            if not messagebox.askokcancel("Chiudi", "L'elaborazione è ancora in corso.\nSe chiudi ora, il lavoro fatto andrà perso.\n\nVuoi chiudere comunque?"):
                return
        # Pulizia sicura di tutti i file temporanei
        for f in self.file_temporanei:
            try:
                if os.path.exists(f): os.remove(f)
            except: pass
        self.file_temporanei = []
        self.destroy()

if __name__ == "__main__":
    app = SbobbyApp()
    app.mainloop()

