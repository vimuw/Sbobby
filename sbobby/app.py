"""
Sbobby application (modularized).

Questo file contiene la logica principale dell'app, spostata sotto il package `sbobby/`
per rendere il repository piu' organizzato. L'entrypoint PyInstaller resta `Sbobby.pyw`.
"""

import customtkinter as ctk
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
from tkinter import filedialog, messagebox

from google import genai

from sbobby.ffmpeg_utils import probe_duration_seconds
from sbobby.pipeline import esegui_sbobinatura
from sbobby.shared import (
    DEFAULT_MODEL,
    FONT_MONO,
    FONT_UI,
    FONT_UI_EMOJI,
    _load_json,
    _session_dir_for_file,
    cleanup_orphan_temp_chunks,
    load_config,
    save_config,
)

# ==========================================
# CONFIGURAZIONE UI (CustomTkinter)
# ==========================================
# UI: palette scura ma "soft" (niente neri assoluti / bianchi sparati).
ctk.set_appearance_mode("Dark")  # Supporta "Dark", "Light", "System"
ctk.set_default_color_theme("blue")


# ==========================================
# CLASSE PER REDIRECT DELL'OUTPUT NELLA GUI
# ==========================================
class PrintRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, string):
        if string == '\r' or string == '\n':
            return
        # Usa after() per garantire thread-safety con Tkinter.
        # In chiusura app, il widget puo' essere gia' distrutto: ignora.
        try:
            self.text_widget.after(0, self._append, string)
        except Exception:
            pass

    def _append(self, string):
        try:
            self.text_widget.configure(state="normal")
            self.text_widget.insert(ctk.END, string + "\n")
            self.text_widget.see(ctk.END)
            self.text_widget.configure(state="disabled")
        except Exception:
            # Probabile chiusura finestra (widget distrutto).
            pass

    def flush(self):
        pass


# ==========================================
# LOGICA PRINCIPALE DI SBOBBY
# ==========================================
from tkinterdnd2 import TkinterDnD, DND_FILES

class SbobbyApp(ctk.CTk, TkinterDnD.DnDWrapper):

    # Palette scura neutra "soft" (evita nero puro e contrasti eccessivi).
    ACCENT = "#3B82F6"
    ACCENT_HOVER = "#2563EB"
    SUCCESS = "#16A34A"
    SUCCESS_HOVER = "#15803D"
    BG = "#151A22"
    CARD_BG = "#1C2432"
    TERMINAL_BG = "#111824"
    TERMINAL_FG = "#D7DEE8"
    TEXT_DIM = "#A6B0C0"
    TEXT_BRIGHT = "#E7ECF4"
    BORDER = "#2B3444"

    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)
        
        self.title("Sbobby")
        self.geometry("850x720")
        self.configure(fg_color=self.BG)
        self.minsize(750, 620)

        self.file_path = None
        # Batch queue (max 3): ogni job contiene path + session_dir + resume_session.
        self.queue_jobs = []
        self.current_job = None
        self.session_dir = None
        self.resume_session = False
        self.is_running = False
        self.cancel_event = threading.Event()
        self._is_cancelling = False
        self.file_temporanei = []  # Lista file temp condivisa col thread
        self.last_output_html = None
        self.last_output_dir = None
        self._run_started_monotonic = None
        self._file_loaded_monotonic = None
        self._eta_ema_seconds = None
        # Hint sotto al file selezionato: separa testo base e stima richieste (per comporli senza sovrascriversi).
        self._file_hint_base = ""
        self._file_cost_hint = ""

        # ETA "step-based" (piu' stabile): medie dei tempi per chunk/macro/confine.
        self._work_totals = {"chunks": 0, "macro": 0, "boundary": 0}
        self._work_done = {"chunks": 0, "macro": 0, "boundary": 0}
        self._work_avg = {"chunks": None, "macro": None, "boundary": None}  # seconds

        # Intercetta la chiusura della finestra per pulire i file temporanei
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        # HEADER (solo titolo centrato)
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.grid(row=0, column=0, padx=30, pady=(22, 8), sticky="ew")
        self.header.grid_columnconfigure(0, weight=1)
        self.lbl_title = ctk.CTkLabel(self.header, text="Sbobby", font=(FONT_UI, 26, "bold"), text_color=self.TEXT_BRIGHT)
        # sticky vuoto = centrato nella colonna che si espande.
        self.lbl_title.grid(row=0, column=0, pady=(6, 0))

        # API KEY CARD
        self.api_card = ctk.CTkFrame(self, fg_color=self.TERMINAL_BG, corner_radius=14, border_width=1, border_color=self.BORDER)
        self.api_card.grid(row=1, column=0, padx=30, pady=(10, 0), sticky="ew")
        self.api_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.api_card, text="🔑 API Key Gemini", font=(FONT_UI, 14), text_color=self.TEXT_DIM).grid(row=0, column=0, sticky="w", padx=(18, 12), pady=14)
        self.entry_api = ctk.CTkEntry(self.api_card, placeholder_text="Incolla la tua API Key qui...", show="*", font=(FONT_UI, 13), height=38, corner_radius=8, fg_color=self.CARD_BG, border_color=self.BORDER, text_color=self.TEXT_BRIGHT)
        self.entry_api.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=14)
        
        self.btn_show_api = ctk.CTkButton(self.api_card, text="👁", width=38, height=38, corner_radius=8, fg_color=self.CARD_BG, hover_color=self.BORDER, border_color=self.BORDER, border_width=1, text_color=self.TEXT_BRIGHT, command=self.toggle_api_visibility)
        self.btn_show_api.grid(row=0, column=2, padx=(0, 18), pady=14)
        config_data = load_config()
        self.entry_api.insert(0, config_data.get("api_key", ""))
        # Persist the key even if the user closes the app before starting a run.
        try:
            self._last_saved_api_key = (config_data.get("api_key", "") or "").strip()
        except Exception:
            self._last_saved_api_key = ""
        self.entry_api.bind("<FocusOut>", lambda e: self._persist_api_key_best_effort())

        # DROP ZONE (area cliccabile centrata per caricare file)
        self.drop_zone = ctk.CTkFrame(self, fg_color=self.CARD_BG, corner_radius=18, border_width=2, border_color=self.BORDER, cursor="hand2")
        self.drop_zone.grid(row=2, column=0, padx=30, pady=15, sticky="ew")
        self.drop_zone.grid_columnconfigure(0, weight=1)

        self.drop_icon = ctk.CTkLabel(self.drop_zone, text="📥", font=(FONT_UI, 44), text_color=self.TEXT_DIM)
        self.drop_icon.grid(row=0, column=0, pady=(35, 8))

        self.lbl_file = ctk.CTkLabel(self.drop_zone, text="Carica Lezione Audio/Video", font=(FONT_UI, 18, "bold"), text_color=self.TEXT_BRIGHT)
        self.lbl_file.grid(row=1, column=0, pady=(0, 4))

        self._file_hint_base = "Supporta MP3, M4A, WAV, MP4, MKV"
        self._file_cost_hint = ""
        self.lbl_file_hint = ctk.CTkLabel(self.drop_zone, text=self._file_hint_base, font=(FONT_UI, 12), text_color=self.TEXT_DIM)
        self.lbl_file_hint.grid(row=2, column=0, pady=(0, 35))

        # Tutta la drop zone è cliccabile e accetta il drag&drop
        for widget in [self.drop_zone, self.drop_icon, self.lbl_file, self.lbl_file_hint]:
            widget.bind("<Button-1>", lambda e: self.scegli_file())
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind('<<Drop>>', self._on_file_drop)

        # BOTTONE AVVIA
        self.btn_avvia = ctk.CTkButton(self, text="▶  AVVIA GENERAZIONE SBOBINA", height=52, font=(FONT_UI, 16, "bold"), corner_radius=12, fg_color=self.SUCCESS, hover_color=self.SUCCESS_HOVER, command=self.avvia_processo)
        self.btn_avvia.grid(row=3, column=0, padx=30, pady=(0, 15), sticky="ew")

        # TERMINALE OUTPUT
        self.console_card = ctk.CTkFrame(self, fg_color=self.CARD_BG, corner_radius=14, border_width=1, border_color=self.BORDER)
        self.console_card.grid(row=4, column=0, padx=30, pady=(0, 15), sticky="nsew")
        self.console_card.grid_columnconfigure(0, weight=1)
        self.console_card.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(self.console_card, text="⚡ Log Eventi", font=(FONT_UI, 12, "bold"), text_color=self.TEXT_DIM).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        self.progress_bar = ctk.CTkProgressBar(self.console_card, height=6, corner_radius=3, fg_color=self.TERMINAL_BG, progress_color=self.ACCENT)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        self.progress_bar.set(0)

        # META BAR (fase + ETA) separata dai pulsanti: piu' respiro, meno "appiccicato".
        self.meta_bar = ctk.CTkFrame(self.console_card, fg_color="transparent")
        self.meta_bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 6))
        self.meta_bar.grid_columnconfigure(0, weight=1)

        self.lbl_phase = ctk.CTkLabel(self.meta_bar, text="Fase: pronto", font=(FONT_UI, 11), text_color=self.TEXT_DIM)
        self.lbl_phase.grid(row=0, column=0, sticky="w")

        self.lbl_eta = ctk.CTkLabel(self.meta_bar, text="ETA: —", font=(FONT_UI, 11), text_color=self.TEXT_DIM)
        self.lbl_eta.grid(row=0, column=1, sticky="e")

        self.console = ctk.CTkTextbox(self.console_card, font=(FONT_MONO, 12), fg_color=self.TERMINAL_BG, text_color=self.TERMINAL_FG, corner_radius=8, wrap="word", border_width=0)
        self.console.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 8))
        self.console.configure(state="disabled")

        # Bottoni azione: sotto la console, a sinistra, dentro lo stesso padding.
        self.bottom_actions = ctk.CTkFrame(self.console_card, fg_color="transparent")
        self.bottom_actions.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))

        self.btn_open_folder = ctk.CTkButton(
            self.bottom_actions,
            text="📁 Apri cartella",
            width=110,
            height=28,
            corner_radius=10,
            font=(FONT_UI_EMOJI, 12),
            fg_color=self.CARD_BG,
            hover_color=self.BORDER,
            border_color=self.BORDER,
            border_width=1,
            text_color=self.TEXT_BRIGHT,
            command=self.apri_cartella_output,
            state="disabled",
        )
        self.btn_open_folder.pack(side="left", padx=(0, 8))

        self.btn_open_html = ctk.CTkButton(
            self.bottom_actions,
            text="📄 Apri HTML",
            width=90,
            height=28,
            corner_radius=10,
            font=(FONT_UI_EMOJI, 12),
            fg_color=self.CARD_BG,
            hover_color=self.BORDER,
            border_color=self.BORDER,
            border_width=1,
            text_color=self.TEXT_BRIGHT,
            command=self.apri_file_html,
            state="disabled",
        )
        self.btn_open_html.pack(side="left", padx=(0, 8))

        self.btn_cancel = ctk.CTkButton(
            self.bottom_actions,
            text="Stop",
            width=70,
            height=28,
            corner_radius=10,
            fg_color="#B00020",
            hover_color="#8E001A",
            text_color="white",
            command=self.annulla_processo,
            state="disabled",
        )
        self.btn_cancel.pack(side="right")

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
        lk_gh.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/vimuw/Sbobby"))
        
        ctk.CTkLabel(lbl_center, text=" • ", font=(FONT_UI, 11), text_color=self.TEXT_DIM).pack(side="left", padx=5)
        
        lk_kofi = ctk.CTkLabel(lbl_center, text="☕ Offrimi un caffè su Ko-fi", font=(FONT_UI, 11, "underline"), text_color=self.SUCCESS, cursor="hand2")
        lk_kofi.pack(side="left")
        lk_kofi.bind("<Button-1>", lambda e: webbrowser.open("https://ko-fi.com/vimuw"))

    def _on_file_drop(self, event):
        if self.is_running: return
        paths = self._parse_dnd_paths(getattr(event, "data", "") or "")
        if not paths:
            return
        self._set_queue_or_single(paths)

    def _setta_file(self, percorso_file):
        # Se esiste una sessione incompleta per questo file, proponi ripresa o reset.
        try:
            decided = self._decide_session_for_file(percorso_file)
            if decided is None:
                return
            session_dir, resume = decided
            self.session_dir = session_dir
            self.resume_session = bool(resume)
        except Exception as e:
            self.session_dir = None
            self.resume_session = False
            print(f"[!] Errore controllo sessione: {e}")

        # Single selection resets batch queue.
        self.queue_jobs = []
        self.current_job = None
        self.file_path = percorso_file
        # Timestamp per misurare il tempo totale dalla selezione del file fino alla fine.
        try:
            self._file_loaded_monotonic = time.monotonic()
        except Exception:
            self._file_loaded_monotonic = None
        self.drop_icon.configure(text="✅")
        self.lbl_file.configure(text=os.path.basename(self.file_path), text_color=self.TEXT_BRIGHT)
        # Reset stima precedente (selezione nuovo file).
        self._file_cost_hint = ""
        if self.resume_session:
            self._file_hint_base = "Sessione trovata: riprendero' da dove eri rimasto"
        else:
            self._file_hint_base = "Clicca di nuovo per cambiare file"
        self._refresh_file_hint()
        self.drop_zone.configure(border_color=self.SUCCESS)
        print(f"[+] File caricato: {os.path.basename(self.file_path)}")

        # Stima costo richieste (in background) per mostrare Chunk/Revisioni/Confini prima di avviare.
        self._start_cost_estimate_async([self.file_path])

    def scegli_file(self, event=None):
        if self.is_running: return
        files = filedialog.askopenfilenames(
            title="Seleziona file multimediale",
            filetypes=[("File MultiMedia", "*.mp3 *.m4a *.mp4 *.wav *.avi *.mov *.mkv"), ("Tutti i file", "*.*")]
        )
        if files:
            self._set_queue_or_single(list(files))

    def toggle_api_visibility(self):
        if self.entry_api.cget("show") == "*":
            self.entry_api.configure(show="")
            self.btn_show_api.configure(text="🙈")
        else:
            self.entry_api.configure(show="*")
            self.btn_show_api.configure(text="👁")

    def _parse_dnd_paths(self, data: str):
        # TkinterDnD spesso passa un'unica stringa:
        # - con percorsi tra graffe se contengono spazi: {C:\My File.mp3} {C:\Other.mp3}
        # - oppure separati da spazio.
        s = (data or "").strip()
        if not s:
            return []
        out = []
        i = 0
        n = len(s)
        while i < n:
            if s[i].isspace():
                i += 1
                continue
            if s[i] == "{":
                j = s.find("}", i + 1)
                if j == -1:
                    # fallback: prendi fino a fine
                    out.append(s[i + 1 :].strip())
                    break
                out.append(s[i + 1 : j])
                i = j + 1
                continue
            # token fino a spazio
            j = i
            while j < n and not s[j].isspace():
                j += 1
            out.append(s[i:j])
            i = j
        return [p for p in (x.strip() for x in out) if p]

    def _set_queue_or_single(self, paths):
        # Valida estensioni e gestisce singolo file o batch (max 3).
        estensioni_valide = [".mp3", ".m4a", ".mp4", ".wav", ".avi", ".mov", ".mkv"]
        cleaned = []
        for p in paths or []:
            p = str(p or "").strip()
            if not p:
                continue
            # strip braces if any leftover
            if p.startswith("{") and p.endswith("}"):
                p = p[1:-1]
            if any(p.lower().endswith(ext) for ext in estensioni_valide):
                cleaned.append(p)
        if not cleaned:
            messagebox.showwarning("Formato non valido", "Seleziona o trascina un file multimediale valido (Audio/Video).")
            return

        if len(cleaned) == 1:
            self._setta_file(cleaned[0])
            return

        # Batch queue
        if len(cleaned) > 3:
            messagebox.showwarning("Coda limitata", "Puoi mettere in coda al massimo 3 file per volta. Usero' i primi 3.")
            cleaned = cleaned[:3]
        self._set_batch_queue(cleaned)

    def _decide_session_for_file(self, percorso_file: str):
        # Decide session_dir + resume policy per un file. Ritorna None se l'utente annulla.
        session_dir = _session_dir_for_file(percorso_file)
        session_path = os.path.join(session_dir, "session.json")
        resume = False
        if os.path.exists(session_path):
            sess = _load_json(session_path) or {}
            stage = (sess.get("stage") or "").strip().lower()
            if stage == "done":
                msg = (
                    "Ho trovato una sessione GIA' COMPLETATA per questo file.\n\n"
                    "Vuoi riutilizzare i risultati salvati (riesportare HTML senza consumare token)?\n\n"
                    "Si = Riutilizza\nNo = Ricomincia da zero\nAnnulla = Salta questo file"
                )
            else:
                msg = (
                    "Ho trovato una sessione salvata per questo file.\n\n"
                    "Vuoi riprendere da dove eri rimasto?\n\n"
                    "Si = Riprendi\nNo = Ricomincia da zero\nAnnulla = Salta questo file"
                )

            scelta = messagebox.askyesnocancel("Sessione trovata", msg)
            if scelta is None:
                return None
            if scelta is True:
                resume = True
                print(f"[*] Ripresa sessione: {session_dir}")
            else:
                try:
                    shutil.rmtree(session_dir, ignore_errors=True)
                    print("[*] Sessione precedente eliminata. Riparto da zero.")
                except Exception as e:
                    print(f"[!] Errore durante reset sessione: {e}")
                resume = False
        return session_dir, resume

    def _set_batch_queue(self, paths):
        jobs = []
        for p in paths:
            try:
                decided = self._decide_session_for_file(p)
            except Exception as e:
                print(f"[!] Errore controllo sessione: {e}")
                decided = None
            if decided is None:
                continue
            session_dir, resume = decided
            jobs.append({"path": p, "session_dir": session_dir, "resume_session": bool(resume)})
        if not jobs:
            return
        self.queue_jobs = jobs[1:]
        self.current_job = jobs[0]
        self._apply_job_to_ui(self.current_job, from_batch=True)
        # Start estimate for whole batch (shows queue count)
        self._start_cost_estimate_async([j["path"] for j in jobs])

    def _apply_job_to_ui(self, job, from_batch: bool = False):
        # Aggiorna UI come se avessi selezionato un singolo file.
        self.session_dir = job.get("session_dir")
        self.resume_session = bool(job.get("resume_session"))
        self.file_path = job.get("path")
        try:
            self._file_loaded_monotonic = time.monotonic()
        except Exception:
            self._file_loaded_monotonic = None

        if self.file_path:
            self.drop_icon.configure(text="✅")
            self.lbl_file.configure(text=os.path.basename(self.file_path), text_color=self.TEXT_BRIGHT)
            if self.resume_session:
                hint = "Sessione trovata: riprendero' da dove eri rimasto"
            else:
                hint = "Clicca di nuovo per cambiare file"
            if from_batch:
                extra = 1 + len(self.queue_jobs or [])
                hint = f"Coda: {extra} file • {hint}"
            # Reset stima precedente e aggiorna hint.
            self._file_cost_hint = ""
            self._file_hint_base = hint
            self._refresh_file_hint()
            self.drop_zone.configure(border_color=self.SUCCESS)
            print(f"[+] File caricato: {os.path.basename(self.file_path)}")

    def _refresh_file_hint(self):
        # Compone hint base + stima richieste (se presente) senza farli pestare.
        try:
            base = str(getattr(self, "_file_hint_base", "") or "").strip()
            cost = str(getattr(self, "_file_cost_hint", "") or "").strip()
            txt = base
            if cost:
                txt = f"{base}\n{cost}" if base else cost
            if not txt:
                txt = "Supporta MP3, M4A, WAV, MP4, MKV"
            self.lbl_file_hint.configure(text=txt)
        except Exception:
            pass

    def _estimate_requests_from_duration(self, duration_seconds: float):
        # Stima: Chunk esatto da durata; revisioni/confini stimati da char/min.
        try:
            dur_int = int(max(0.0, float(duration_seconds)))
        except Exception:
            dur_int = 0
        settings = {"chunk_minutes": 15, "overlap_seconds": 30, "macro_char_limit": 22000}
        chunk_minutes = int(settings["chunk_minutes"])
        overlap = int(settings["overlap_seconds"])
        macro_limit = int(settings["macro_char_limit"])
        step = max(1, (chunk_minutes * 60) - overlap)
        chunks_total = 0 if dur_int <= 0 else (dur_int + step - 1) // step

        # Heuristica conservativa: ~800 caratteri/minuto di output Markdown.
        est_chars_per_min = 800
        est_total_chars = int((dur_int / 60.0) * est_chars_per_min)
        macro_total = max(1, (est_total_chars + macro_limit - 1) // macro_limit) if est_total_chars > 0 else 1
        revisions = int(macro_total)
        boundaries = max(0, int(macro_total) - 1)
        return int(chunks_total), int(revisions), int(boundaries)

    def _probe_duration_seconds(self, path: str):
        # Usa helper condiviso (stessa logica della pipeline).
        return probe_duration_seconds(path)

    def _start_cost_estimate_async(self, paths):
        # Aggiorna la hint sotto al file con stima richieste (Chunk/Revisioni/Confini) prima di avviare.
        # Se e' una coda, somma le stime sui file selezionati (best-effort).
        try:
            if not hasattr(self, "lbl_file_hint") or self.lbl_file_hint is None:
                return
        except Exception:
            return

        total_files = len(paths or [])
        if total_files <= 0:
            try:
                self._file_cost_hint = ""
                self._refresh_file_hint()
            except Exception:
                pass
            return

        # Tkinter non e' thread-safe: il worker NON deve mai toccare widget. Usa una queue e polling via after().
        try:
            self._cost_estimate_seq = int(getattr(self, "_cost_estimate_seq", 0) or 0) + 1
        except Exception:
            self._cost_estimate_seq = 1
        seq = int(self._cost_estimate_seq)
        q = queue.Queue(maxsize=1)

        def worker(all_paths, total_n: int):
            tot_chunks = 0
            tot_revs = 0
            tot_bounds = 0
            any_ok = False
            debug_reasons = []
            for p in all_paths or []:
                dur, why = self._probe_duration_seconds(p)
                if dur is None:
                    try:
                        bn = os.path.basename(str(p or "")) or str(p or "")
                    except Exception:
                        bn = str(p or "")
                    if why:
                        debug_reasons.append(f"{bn}: {why}")
                    continue
                any_ok = True
                c, r, b = self._estimate_requests_from_duration(dur)
                tot_chunks += int(c)
                tot_revs += int(r)
                tot_bounds += int(b)

            if not any_ok:
                txt = f"Stima coda ({total_n} file): non disponibile" if total_n > 1 else "Stima richieste: non disponibile"
            else:
                prefix = f"Stima coda ({total_n} file): " if total_n > 1 else "Stima richieste: "
                txt = f"{prefix}Chunk {tot_chunks} • Revisioni ~{tot_revs} • Confini ~{tot_bounds}"
            try:
                q.put_nowait({"txt": txt, "debug": debug_reasons})
            except Exception:
                # Se la queue e' piena o errore, ignora: la UI usera' quanto gia' disponibile.
                pass

        def poll():
            # Eseguito nel main thread via after(): aggiorna la UI se e quando arriva il testo.
            try:
                if int(getattr(self, "_cost_estimate_seq", 0) or 0) != seq:
                    return  # richiesta vecchia (file cambiato)
                try:
                    item = q.get_nowait()
                except Exception:
                    # Non ancora pronto: riprova a breve se il worker e' vivo
                    if t.is_alive():
                        self.after(120, poll)
                    return
                txt = None
                debug_reasons = None
                try:
                    if isinstance(item, dict):
                        txt = item.get("txt")
                        debug_reasons = item.get("debug")
                    else:
                        txt = str(item)
                except Exception:
                    txt = str(item)

                self._file_cost_hint = str(txt or "").strip()
                self._refresh_file_hint()
                # Debug: se non disponibile, logga un motivo utile in console (main thread).
                try:
                    if (not self._file_cost_hint) or ("non disponibile" in self._file_cost_hint.lower()):
                        if debug_reasons:
                            sample = " | ".join(list(debug_reasons)[:2])
                            more = ""
                            if len(debug_reasons) > 2:
                                more = f" (+{len(debug_reasons)-2} altri)"
                            print(f"[stima] non disponibile: {sample}{more}")
                except Exception:
                    pass
            except Exception:
                pass

        try:
            # Mostra subito che stiamo calcolando.
            self._file_cost_hint = (f"Stima coda ({total_files} file): calcolo..." if total_files > 1 else "Stima richieste: calcolo...")
            self._refresh_file_hint()
        except Exception:
            pass

        try:
            t = threading.Thread(target=worker, args=(list(paths), total_files), daemon=True)
            t.start()
            # Avvia polling UI
            self.after(120, poll)
        except Exception:
            pass

    def reset_work_eta(self):
        # Reset per ogni nuova run.
        self._work_totals = {"chunks": 0, "macro": 0, "boundary": 0}
        self._work_done = {"chunks": 0, "macro": 0, "boundary": 0}
        self._work_avg = {"chunks": None, "macro": None, "boundary": None}

    def set_work_totals(self, chunks_total=None, macro_total=None, boundary_total=None):
        # Thread-safe entry: puo' essere chiamato dal worker thread.
        try:
            if chunks_total is not None:
                self._work_totals["chunks"] = int(max(0, chunks_total))
            if macro_total is not None:
                self._work_totals["macro"] = int(max(0, macro_total))
            if boundary_total is not None:
                self._work_totals["boundary"] = int(max(0, boundary_total))
        except Exception:
            pass
        self._update_eta_from_steps()

    def update_work_done(self, kind: str, done: int, total: int = None):
        k = str(kind or "").lower()
        if k not in self._work_done:
            return
        try:
            self._work_done[k] = int(max(0, done))
            if total is not None:
                self._work_totals[k] = int(max(0, total))
        except Exception:
            pass
        self._update_eta_from_steps()

    def register_step_time(self, kind: str, seconds: float, done: int = None, total: int = None):
        k = str(kind or "").lower()
        if k not in self._work_avg:
            return
        try:
            s = float(seconds)
            if s <= 0:
                s = 0.0
        except Exception:
            s = 0.0
        # Update counts first
        if done is not None:
            self.update_work_done(k, done, total=total)
        # EMA average, ignore zeros (e.g., resume skips) to keep it stable.
        if s > 0.2:
            prev = self._work_avg.get(k)
            if prev is None:
                self._work_avg[k] = s
            else:
                alpha = 0.22
                self._work_avg[k] = (alpha * s) + ((1 - alpha) * float(prev))
        self._update_eta_from_steps()

    def _compute_eta_from_steps(self):
        # Usa le medie disponibili; se non ne abbiamo, ritorna None per fallback al metodo percentuale.
        try:
            rem_chunks = max(0, int(self._work_totals["chunks"]) - int(self._work_done["chunks"]))
            rem_macro = max(0, int(self._work_totals["macro"]) - int(self._work_done["macro"]))
            rem_boundary = max(0, int(self._work_totals["boundary"]) - int(self._work_done["boundary"]))
        except Exception:
            return None

        avg_chunk = self._work_avg.get("chunks")
        avg_macro = self._work_avg.get("macro")
        avg_boundary = self._work_avg.get("boundary")

        if avg_chunk is None and avg_macro is None and avg_boundary is None:
            return None

        eta = 0.0
        if avg_chunk is not None:
            eta += float(avg_chunk) * float(rem_chunks)
        if avg_macro is not None:
            eta += float(avg_macro) * float(rem_macro)
        if avg_boundary is not None:
            eta += float(avg_boundary) * float(rem_boundary)
        # Clamp: evita numeri assurdi se mancano medie per alcune fasi (non mostrare).
        if eta <= 0.0 or eta > 48 * 3600:
            return None
        return eta

    def _update_eta_from_steps(self):
        # Aggiorna ETA in UI usando le medie step-based (se disponibili).
        try:
            if not self.is_running:
                return
            eta = self._compute_eta_from_steps()
            if eta is None:
                return
            # Thread-safe: puo' essere chiamato anche dal worker thread.
            self.after(0, self._set_eta_ui, int(eta))
        except Exception:
            pass

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
        # Validazione rapida della API Key (Senza consumare token di generazione)
        try:
            test_client = genai.Client(api_key=api_key)
            test_client.models.get(model=DEFAULT_MODEL)
        except Exception as e:
            messagebox.showerror("API Key non valida", f"La chiave API non è valida o non hai accesso ai server Google.\nControlla di averla copiata correttamente, senza spazi extra.\n\nErrore: {e}")
            return
        save_config(api_key)
        try:
            self._last_saved_api_key = api_key
        except Exception:
            pass

        # Best-effort: pulizia file temporanei rimasti da crash/chiusure forzate precedenti.
        try:
            removed = cleanup_orphan_temp_chunks()
            if removed > 0:
                print(f"[*] Pulizia: rimossi {removed} file temporanei rimasti in sospeso.")
        except Exception:
            pass

        self.is_running = True
        self.cancel_event.clear()
        self._run_started_monotonic = time.monotonic()
        if not self._file_loaded_monotonic:
            # Fallback: se per qualche motivo non e' stato settato in _setta_file.
            self._file_loaded_monotonic = self._run_started_monotonic
        self._eta_ema_seconds = None
        self.reset_work_eta()
        self.last_output_html = None
        self.last_output_dir = None
        self._set_phase_ui("Fase: avvio...")
        self._set_eta_ui(None)
        self._update_output_buttons()
        self.btn_cancel.configure(state="normal")
        self.progress_bar.set(0)
        self.btn_avvia.configure(state="disabled", fg_color=self.BORDER, text="⏳  Elaborazione in corso...")
        for w in [self.drop_zone, self.drop_icon, self.lbl_file, self.lbl_file_hint]:
            w.unbind("<Button-1>")
        self.entry_api.configure(state="disabled")
        print("\n" + "━"*50)
        print("  INIZIO PROCESSO DI ANALISI ED ESTRAZIONE AI")
        print("  Non chiudere l'app durante l'elaborazione.")
        print("━"*50 + "\n")
        thread = threading.Thread(
            target=esegui_sbobinatura,
            args=(self.file_path, api_key, self),
            kwargs={"session_dir_hint": self.session_dir, "resume_session": self.resume_session},
            daemon=True,
        )
        thread.start()

    def processo_terminato(self):
        self.is_running = False
        self.after(0, self._log_tempo_totale)
        self.after(0, self._ripristina_ui)
        self.after(0, self._maybe_start_next_job)

    def _maybe_start_next_job(self):
        # Se siamo in batch e il file corrente e' stato completato con successo, avvia il prossimo.
        try:
            if self.cancel_event.is_set():
                return
            if not self.queue_jobs:
                return
            if not (self.last_output_html and os.path.exists(self.last_output_html)):
                # Se non abbiamo output, consideriamo la run non completata: non proseguiamo in batch.
                return
        except Exception:
            return

        try:
            nxt = self.queue_jobs.pop(0)
        except Exception:
            return
        self.current_job = nxt
        try:
            print("\n" + "=" * 52)
            print(f"Batch: avvio prossimo file ({1 + len(self.queue_jobs)} rimanenti): {os.path.basename(nxt.get('path') or '')}")
            print("=" * 52 + "\n")
        except Exception:
            pass
        self._apply_job_to_ui(nxt, from_batch=True)
        self._start_cost_estimate_async([nxt.get("path")] + [j.get("path") for j in (self.queue_jobs or [])])
        # Piccolo delay per far aggiornare UI, poi avvia.
        try:
            self.after(250, self.avvia_processo)
        except Exception:
            pass

    def _log_tempo_totale(self):
        # Mostra il tempo totale impiegato dall'app dalla selezione del file alla fine.
        try:
            if not self._file_loaded_monotonic:
                return
            elapsed = max(0.0, time.monotonic() - float(self._file_loaded_monotonic))
            print("\n" + "=" * 44)
            print(f"Tempo totale (da file caricato): {self._format_duration(int(elapsed))}")
            print("=" * 44 + "\n")
        except Exception:
            pass

    def _ripristina_ui(self):
        self._is_cancelling = False
        self.btn_avvia.configure(state="normal", fg_color=self.SUCCESS, text="▶  AVVIA GENERAZIONE SBOBINA")
        self.progress_bar.set(0)
        self.btn_cancel.configure(state="disabled", text="Stop")
        self._run_started_monotonic = None
        self._eta_ema_seconds = None
        if not self.last_output_html:
            if self.cancel_event.is_set():
                self._set_phase_ui("Fase: annullato")
            else:
                self._set_phase_ui("Fase: pronto")
            self._set_eta_ui(None)
        self._update_output_buttons()
        for w in [self.drop_zone, self.drop_icon, self.lbl_file, self.lbl_file_hint]:
            w.bind("<Button-1>", lambda e: self.scegli_file())
        self.entry_api.configure(state="normal")

    def _enter_cancel_state_ui(self, source: str = "Stop"):
        # Feedback immediato: l'annullamento reale avviene al termine dello step corrente (API/ffmpeg).
        try:
            if self._is_cancelling:
                return
            self._is_cancelling = True
        except Exception:
            pass

        try:
            self.cancel_event.set()
        except Exception:
            pass

        try:
            self._set_phase_ui("Fase: annullamento in corso... (attendo fine operazione)")
        except Exception:
            pass

        try:
            print(f"[*] Annullamento richiesto ({source}). Attendo la fine dell'operazione corrente per fermarmi in sicurezza...")
        except Exception:
            pass

        # Disabilita comandi interattivi: durante annullamento non vogliamo altri click.
        try:
            self.btn_cancel.configure(state="disabled", text="Annullamento...")
        except Exception:
            pass
        try:
            self.btn_open_folder.configure(state="disabled")
            self.btn_open_html.configure(state="disabled")
        except Exception:
            pass

    def aggiorna_progresso(self, valore):
        """Aggiorna la barra di progresso in modo thread-safe."""
        self.after(0, self._apply_progress, min(valore, 1.0))

    def aggiorna_fase(self, fase_testo: str):
        """Aggiorna l'indicatore di fase in modo thread-safe."""
        self.after(0, self._set_phase_ui, fase_testo)

    def imposta_output_html(self, html_path: str):
        """Salva il path dell'output e abilita i pulsanti di apertura (thread-safe)."""
        self.after(0, self._set_output_ui, html_path)

    def _set_output_ui(self, html_path: str):
        try:
            p = os.path.abspath(html_path) if html_path else None
            if p and os.path.exists(p):
                self.last_output_html = p
                self.last_output_dir = os.path.dirname(p)
                self._update_output_buttons()
        except Exception:
            pass

    def _update_output_buttons(self):
        try:
            has_html = bool(self.last_output_html and os.path.exists(self.last_output_html))
            has_dir = bool(self.last_output_dir and os.path.isdir(self.last_output_dir))
            self.btn_open_html.configure(state=("normal" if has_html else "disabled"))
            self.btn_open_folder.configure(state=("normal" if has_dir else "disabled"))
        except Exception:
            pass

    def _set_phase_ui(self, text: str):
        try:
            self.lbl_phase.configure(text=str(text or "Fase: —"))
        except Exception:
            pass

    def _set_eta_ui(self, seconds_remaining):
        try:
            if seconds_remaining is None:
                self.lbl_eta.configure(text="ETA: —")
            else:
                self.lbl_eta.configure(text=f"ETA: {self._format_duration(seconds_remaining)}")
        except Exception:
            pass

    def _apply_progress(self, value: float):
        try:
            v = float(value)
        except Exception:
            v = 0.0
        v = max(0.0, min(v, 1.0))
        try:
            self.progress_bar.set(v)
        except Exception:
            pass

        if not self.is_running or not self._run_started_monotonic:
            return

        # ETA "step-based": se abbiamo abbastanza dati, e' piu' stabile del metodo percentuale.
        try:
            eta_steps = self._compute_eta_from_steps()
            if eta_steps is not None:
                self._set_eta_ui(int(eta_steps))
                return
        except Exception:
            pass

        if v <= 0.02:
            self._set_eta_ui(None)
            return
        elapsed = max(0.0, time.monotonic() - float(self._run_started_monotonic))
        if elapsed < 1.0:
            self._set_eta_ui(None)
            return
        est_total = elapsed / max(v, 1e-6)
        remaining = max(0.0, est_total - elapsed)

        # Smoothing per evitare ETA ballerina.
        if self._eta_ema_seconds is None:
            self._eta_ema_seconds = remaining
        else:
            alpha = 0.18
            self._eta_ema_seconds = (alpha * remaining) + ((1 - alpha) * float(self._eta_ema_seconds))

        self._set_eta_ui(int(self._eta_ema_seconds))

    def _format_duration(self, seconds: int) -> str:
        try:
            s = int(max(0, seconds))
        except Exception:
            s = 0
        h = s // 3600
        m = (s % 3600) // 60
        sec = s % 60
        if h > 0:
            return f"{h:d}:{m:02d}:{sec:02d}"
        return f"{m:d}:{sec:02d}"

    def annulla_processo(self):
        if not self.is_running:
            return
        try:
            self._enter_cancel_state_ui(source="Stop")
        except Exception:
            pass

    def _open_path(self, path: str):
        p = os.path.abspath(path)
        if not os.path.exists(p):
            raise FileNotFoundError(p)
        sysname = platform.system()
        if sysname == "Windows":
            os.startfile(p)  # type: ignore[attr-defined]
            return
        if sysname == "Darwin":
            subprocess.run(["open", p], check=False)
            return
        subprocess.run(["xdg-open", p], check=False)

    def apri_file_html(self):
        try:
            if not self.last_output_html:
                return
            self._open_path(self.last_output_html)
        except Exception as e:
            messagebox.showerror("Impossibile aprire", f"Non riesco ad aprire il file HTML.\n\nErrore: {e}")

    def apri_cartella_output(self):
        try:
            if not self.last_output_dir:
                return
            self._open_path(self.last_output_dir)
        except Exception as e:
            messagebox.showerror("Impossibile aprire", f"Non riesco ad aprire la cartella di output.\n\nErrore: {e}")

    def _persist_api_key_best_effort(self):
        try:
            value = (self.entry_api.get() or "").strip()
            if not value:
                return
            if value == getattr(self, "_last_saved_api_key", ""):
                return
            save_config(value)
            self._last_saved_api_key = value
        except Exception:
            pass

    def _on_close(self):
        """Pulisce i file temporanei rimasti prima di chiudere l'applicazione."""
        if self.is_running:
            if not messagebox.askokcancel(
                "Chiudi",
                "L'elaborazione e' ancora in corso.\n\n"
                "Nota: Sbobby salva automaticamente dopo ogni chunk e dopo ogni revisione.\n"
                "Se chiudi ora potresti perdere solo l'ultimo step non ancora salvato.\n\n"
                "Vuoi chiudere comunque?"
            ):
                return
            try:
                self._enter_cancel_state_ui(source="Chiusura finestra")
            except Exception:
                pass
        # Salva la API Key anche se l'utente chiude prima di avviare una run.
        self._persist_api_key_best_effort()
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

