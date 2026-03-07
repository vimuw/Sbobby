import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import sys
import time
import markdown
import os
from google import genai
from google.genai import types
from moviepy.editor import AudioFileClip

# ==========================================
# CLASSE PER REDIRECT DELL'OUTPUT NELLA GUI
# ==========================================
class PrintRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, string):
        self.text_widget.insert(tk.END, string)
        self.text_widget.see(tk.END)
        self.text_widget.update_idletasks() # Forza l'aggiornamento della UI

    def flush(self):
        pass

# ==========================================
# LOGICA PRINCIPALE DELLO SBOBINATORE
# ==========================================
def esegui_sbobinatura(nome_file_video, app_instance):
    try:
        # INSERISCI QUI LA TUA API KEY
        api_key_value = "AIzaSyAxpO1k6YLjtGBhgL34PXCAoqBdLWk0N-w"
        
        if not api_key_value:
            print("Errore: Chiave API mancante nel codice.")
            return

        client = genai.Client(api_key=api_key_value)
        
        blocco_minuti = 15
        blocco_secondi = blocco_minuti * 60
        sovrapposizione_secondi = 30
        passo_secondi = blocco_secondi - sovrapposizione_secondi
        memoria_precedente = ""
        testo_completo_sbobina = ""

        istruzioni_sistema = """
Agisci come un 'Redattore Accademico Universitario' esperto. Il tuo compito è prendere l'audio frammentato di una lezione universitaria e TRASFORMARLO in una DISPENSA DI STUDIO (sbobina) eccellente, pronta per Google Docs.

REGOLA SUPREMA E PRECEDENZA ASSOLUTA: LA PULIZIA DEL TESTO
Prima di applicare qualsiasi altra regola, DEVI filtrare il testo grezzo. Le seguenti rimozioni NON sono considerate "omissioni", ma "correzioni editoriali obbligatorie":
1. DIVIETO DI DOPPIONI: Se un concetto o un paragrafo viene ripetuto nel testo originale (es. il professore ripete per chiarezza, o il software balbetta), SCRIVILO UNA SOLA VOLTA. Fondere le ripetizioni è un obbligo assoluto.
2. NESSUNA "(CONTINUAZIONE)": È severamente vietato creare titoli o paragrafi che contengano la parola "(continuazione)".
3. ELIMINA LA RETORICA: Rimuovi frasi inutili come "Ora vi elenco", "Come vedremo tra poco", "Si consiglia di".
4. CORREZIONI IN TEMPO REALE: Se chi parla sbaglia e si corregge subito dopo, scrivi solo l'ultima versione corretta.

OBIETTIVO DI CONTENUTO: MASSIMO DETTAGLIO (POST-PULIZIA)
Tutto ciò che è un concetto unico è 'oggetto d'esame'. Mantieni ogni singola spiegazione tecnica, medica o teorica con la massima profondità. Non riassumere i concetti unici.

STRUTTURA E FORMATTAZIONE:
1. GERARCHIA TITOLI IMMUTABILE: Usa ESCLUSIVAMENTE "## Titolo Argomento" e "### Sotto-argomento". Non usare MAI un singolo cancelletto (#). 
2. ELENCHI E PARAGRAFI: Usa elenchi puntati (-) per le enumerazioni. Dividi il testo in paragrafi.
3. STILE: Linguaggio formale e oggettivo. Evidenzia in **grassetto** tutte le parole chiave.

GESTIONE DELL'OVERLAP (MEMORIA TRA I BLOCCHI):
Se stai continuando un discorso dal blocco precedente e senti ripetere le identiche frasi finali a causa della sovrapposizione temporale dell'audio, IGNORA LA RIPETIZIONE. Unisci il testo nuovo a quello vecchio in modo fluido.
"""

        print(f"Analisi del file originale in corso:\n{nome_file_video}")
        try:
            audio_completo = AudioFileClip(nome_file_video)
            durata_totale_secondi = audio_completo.duration
        except Exception as e:
            print(f"Errore caricamento audio: {e}")
            return

        print(f"Durata totale rilevata: {int(durata_totale_secondi / 60)} minuti.")
        print("INIZIO FASE 1: Estrazione fisica a blocchi con sovrapposizione.\n")

        for inizio_sec in range(0, int(durata_totale_secondi), passo_secondi):
            fine_sec = min(inizio_sec + blocco_secondi, durata_totale_secondi)
            
            print(f"======================================")
            print(f"-> LAVORAZIONE AUDIO: Da {inizio_sec}s a {int(fine_sec)}s")
            
            import tempfile
            temp_dir = tempfile.gettempdir()
            nome_chunk = os.path.join(temp_dir, f"pezzo_temp_{inizio_sec}_{int(fine_sec)}.mp3")
            
            # 1. Taglio
            chunk = audio_completo.subclip(inizio_sec, fine_sec)
            chunk.write_audiofile(nome_chunk, logger=None)
            chunk.close()
            
            # 2. Upload
            print("   -> Caricamento su server...")
            audio_file = client.files.upload(file=nome_chunk)
            while "PROCESSING" in str(audio_file.state):
                time.sleep(3)
                audio_file = client.files.get(name=audio_file.name)
                
            # 3. Generazione testuale
            print("   -> Generazione sbobina in corso...")
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
                    print(f"      [Errore di traffico. Riprovo in 30 secondi...]")
                    time.sleep(30)
                    
            if not successo:
                print("   [!] Errore critico sui server. Interrompo e passo alla Fase 2 con il lavoro fatto.")
                break
                
            # 4. Pulizia
            if os.path.exists(nome_chunk):
                os.remove(nome_chunk)
            client.files.delete(name=audio_file.name)
            time.sleep(20)

        audio_completo.close()

        # ==========================================
        # FASE 2: REVISIONE LOGICA E CUCITURA DOPPIONI
        # ==========================================
        print("\n======================================")
        print("INIZIO FASE 2: REVISIONE CHIRURGICA E RIMOZIONE DOPPIONI...")

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
            
        print(f"Testo grezzo diviso in {len(macro_blocchi)} macro-blocchi. Revisione in corso...")

        testo_finale_revisionato = ""

        prompt_revisione = """
Sei un correttore di bozze accademico, un automa precisissimo. Ti sto passando una grossa porzione di una sbobina universitaria.
Il tuo UNICO scopo è trovare ripetizioni, frasi sdoppiate (es. glitch copia-incolla) o concetti identici ripetuti a breve distanza.

REGOLE ASSOLUTE:
1. Se trovi un concetto ripetuto, FONDILO in un unico paragrafo fluido e ben scritto. Elimina i doppioni.
2. DIVIETO ASSOLUTO DI RIASSUMERE IL RESTO: Tutto ciò che NON è un doppione deve rimanere ESATTAMENTE IDENTICO (copia-incolla totale) al testo originale, con lo stesso identico livello di dettaglio medico/tecnico. Non tagliare le informazioni uniche.
3. Rimuovi frasi o titoli inutili come "(continuazione)". Attacca i paragrafi.
4. Mantieni la stessa identica formattazione Markdown originale (##, ###, elenchi, grassetti).
"""

        for i, blocco in enumerate(macro_blocchi, 1):
            print(f"   -> Pulitura Macro-blocco {i}/{len(macro_blocchi)}...")
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
                    print(f"      [Errore. Riprovo in 20 secondi...]")
                    time.sleep(20)
                    
            if not successo_revisione:
                print(f"   [!] Errore nella revisione. Salvo il blocco {i} allo stato grezzo.")
                testo_finale_revisionato += f"\n\n{blocco}\n\n"
            time.sleep(15)

        # ==========================================
        # 3. SALVATAGGIO FINALE IN HTML
        # ==========================================
        # Salva nella stessa cartella del file originale per comodità
        dir_name = os.path.dirname(nome_file_video)
        base_name = os.path.basename(nome_file_video)
        nome_puro = os.path.splitext(base_name)[0]
        nome_file_output = os.path.join(dir_name, f"{nome_puro}_Sbobina.html")

        if not base_name: 
            nome_file_output = "Sbobina_Definitiva.html"

        with open(nome_file_output, "w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html>\n<html>\n<head>\n<meta charset='utf-8'>\n</head>\n<body>\n")
            f.write(markdown.markdown(testo_finale_revisionato))
            f.write("\n</body>\n</html>")

        print(f"======================================")
        print(f"FINITO! La tua sbobina perfetta è salvata in:\n{nome_file_output}")
    
    except Exception as e:
        print(f"\nERRORE IMPREVISTO IN ESECUZIONE: {e}")
    finally:
        app_instance.processo_terminato()

# ==========================================
# INTERFACCIA GRAFICA T-KINTER
# ==========================================
class SbobinatoreApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Sbobinatore Automatico AI")
        self.root.geometry("700x550")
        self.root.minsize(500, 450)
        
        self.file_path = None
        self.is_running = False

        # Configurazione Layout
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        # Frame Selezione File
        frame_top = tk.Frame(root, pady=15, padx=15)
        frame_top.grid(row=0, column=0, sticky="ew")
        frame_top.columnconfigure(1, weight=1)

        tk.Label(frame_top, text="Seleziona Audio/Video:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w")
        
        self.lbl_file = tk.Label(frame_top, text="Nessun file selezionato...", fg="gray", relief="sunken", anchor="w", padx=5, bg="white")
        self.lbl_file.grid(row=0, column=1, sticky="ew", padx=10, ipady=3)
        
        btn_scegli = tk.Button(frame_top, text="Sfoglia...", command=self.scegli_file, cursor="hand2")
        btn_scegli.grid(row=0, column=2, sticky="e")

        # Frame Avvio
        frame_mid = tk.Frame(root, pady=10)
        frame_mid.grid(row=1, column=0, sticky="ew")
        
        self.btn_avvia = tk.Button(frame_mid, text="▶ AVVIA GENERAZIONE SBOBINA", font=("Arial", 12, "bold"), bg="#4CAF50", fg="white", command=self.avvia_processo, cursor="hand2")
        self.btn_avvia.pack(pady=5, ipadx=20, ipady=10)

        # Frame Console
        frame_bot = tk.Frame(root, padx=15, pady=15)
        frame_bot.grid(row=2, column=0, sticky="nsew")
        frame_bot.rowconfigure(1, weight=1)
        frame_bot.columnconfigure(0, weight=1)

        tk.Label(frame_bot, text="Log di avanzamento:", font=("Arial", 10)).grid(row=0, column=0, sticky="w", pady=(0, 5))

        self.console = scrolledtext.ScrolledText(frame_bot, wrap=tk.WORD, state=tk.NORMAL, bg="#1e1e1e", fg="#00ff00", font=("Consolas", 10))
        self.console.grid(row=1, column=0, sticky="nsew")
        
        # Redirigo sys.stdout sulla console della GUI
        sys.stdout = PrintRedirector(self.console)
        sys.stderr = PrintRedirector(self.console)
        
        print("="*50)
        print("Sbobinatore Automatico AI Inizializzato.")
        print("="*50)
        print("1. Clicca su 'Sfoglia...' per caricare il tuo file audio (o video).")
        print("2. Clicca 'Avvia' per iniziare.")
        print("\nPronto.\n")

    def scegli_file(self):
        if self.is_running: return
        file_selezionato = filedialog.askopenfilename(
            title="Seleziona il file da sbobinare",
            filetypes=[("File Audio/Video", "*.mp3 *.m4a *.mp4 *.wav *.avi *.mov *.mkv"), ("Tutti i file", "*.*")]
        )
        if file_selezionato:
            self.file_path = file_selezionato
            self.lbl_file.config(text=self.file_path, fg="black")
            print(f"[+] SELEZIONATO: {os.path.basename(self.file_path)}")

    def avvia_processo(self):
        if not self.file_path:
            messagebox.showwarning("Attenzione", "Devi prima selezionare un file audio o video dal computer!")
            return
            
        if self.is_running:
            return
            
        self.is_running = True
        self.btn_avvia.config(state=tk.DISABLED, bg="gray", text="⏳ ELABORAZIONE IN CORSO...")
        
        # Avvia il processo in un thread separato per non bloccare la grafica
        thread = threading.Thread(target=esegui_sbobinatura, args=(self.file_path, self), daemon=True)
        thread.start()

    def processo_terminato(self):
        self.is_running = False
        self.root.after(0, self._ripristina_ui)

    def _ripristina_ui(self):
        self.btn_avvia.config(state=tk.NORMAL, bg="#4CAF50", text="▶ AVVIA GENERAZIONE SBOBINA")

if __name__ == "__main__":
    root = tk.Tk()
    app = SbobinatoreApp(root)
    root.mainloop()