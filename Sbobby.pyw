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
import re
import hashlib
import shutil
import difflib
from datetime import datetime
from google import genai
from google.genai import types
import imageio_ffmpeg
import subprocess


def cleanup_orphan_temp_chunks(max_age_seconds: int = 12 * 3600) -> int:
    """
    Best-effort cleanup of temp chunk files left behind by crashes/forced closes.
    Only touches files matching our own prefix in the OS temp directory.
    """
    removed = 0
    try:
        tmpdir = tempfile.gettempdir()
        now = time.time()
        for name in os.listdir(tmpdir):
            low = name.lower()
            if not low.startswith("sbobby_temp_"):
                continue
            if not (low.endswith(".mp3") or low.endswith(".wav") or low.endswith(".m4a")):
                continue
            path = os.path.join(tmpdir, name)
            try:
                age = now - float(os.path.getmtime(path))
                if age < max(0, int(max_age_seconds)):
                    continue
                os.remove(path)
                removed += 1
            except Exception:
                pass
    except Exception:
        pass
    return removed

# ==========================================
# CONFIGURAZIONE UI E FILE
# ==========================================
ctk.set_appearance_mode("Dark")  # Supporta "Dark", "Light", "System"
ctk.set_default_color_theme("blue")

# Usa il profilo utente per salvare la configurazione in modo persistente anche quando è un .exe creato con PyInstaller
USER_HOME = os.path.expanduser("~")
CONFIG_FILE = os.path.join(USER_HOME, ".sbobby_config.json")

def get_desktop_dir():
    # Cross-platform Desktop path (Windows/macOS/Linux). Fallback: home directory.
    try:
        if platform.system() == "Windows":
            # Prefer OneDrive Desktop if present (common on Windows 10/11).
            for env_key in ("OneDriveConsumer", "OneDriveCommercial", "OneDrive"):
                od = os.environ.get(env_key)
                if od:
                    p = os.path.join(od, "Desktop")
                    if os.path.isdir(p):
                        return p
            up = os.environ.get("USERPROFILE") or USER_HOME
            p = os.path.join(up, "Desktop")
            if os.path.isdir(p):
                return p
        # macOS/Linux default
        p = os.path.join(USER_HOME, "Desktop")
        if os.path.isdir(p):
            return p
    except Exception:
        pass
    return USER_HOME

def safe_output_basename(name: str) -> str:
    # Safe across Windows/macOS. Keep it readable.
    s = (name or "").strip() or "Sbobina"
    s = re.sub(r"[<>:\"/\\\\|?*]+", "_", s)
    s = re.sub(r"\\s+", " ", s).strip()
    return s[:140] if len(s) > 140 else s

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
# SESSIONI (AUTOSAVE / RIPRESA)
# ==========================================
SESSION_SCHEMA_VERSION = 1
SESSION_ROOT = os.path.join(USER_HOME, ".sbobby_sessions")

def _now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _safe_mkdir(path):
    os.makedirs(path, exist_ok=True)

def _atomic_write_text(path, text):
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp_path, path)

def _atomic_write_json(path, data):
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)

def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _file_fingerprint(path):
    abs_path = os.path.abspath(path)
    st = os.stat(abs_path)
    return {
        "path": abs_path,
        "size": int(getattr(st, "st_size", 0)),
        "mtime": float(getattr(st, "st_mtime", 0.0)),
    }

def _session_id_for_file(path):
    fp = _file_fingerprint(path)
    blob = json.dumps(fp, sort_keys=True).encode("utf-8", errors="ignore")
    return hashlib.sha256(blob).hexdigest()

def _session_dir_for_file(path):
    return os.path.join(SESSION_ROOT, _session_id_for_file(path))


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
1. DIVIETO ASSOLUTO DI RIDONDANZA: Se un concetto, una definizione o un esempio compare più volte nell'audio (perché il docente lo riformula, lo ripete o ci ritorna sopra), scrivi quel concetto UNA SOLA VOLTA, nella posizione più logica del testo, fondendo tutte le formulazioni in un unico paragrafo completo e definitivo. IMPORTANTISSIMO: quando fondi, conserva e integra la SOMMA di tutti i dettagli unici comparsi nelle ripetizioni. Non perdere mai un dettaglio che appare una sola volta.
2. MAI RIFORMULARE: Non scrivere mai la stessa idea con parole diverse in punti diversi del testo. Un concetto = un paragrafo.
3. OVERLAP AUDIO: I blocchi audio si sovrappongono. Se le prime frasi di questo blocco ripetono contenuti già trascritti nel blocco precedente, ignora solo le parti chiaramente identiche o puramente ripetitive. Se nella sovrapposizione c'è ANCHE SOLO un'informazione nuova (numero, termine, definizione, correzione, esempio), includila.
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

PROMPT_REVISIONE_CONFINE = """
Sei un revisore editoriale accademico.
Ti passo DUE estratti in Markdown: la FINE del blocco N e l'INIZIO del blocco N+1, separati dal marker:
<<<SBOBBY_SPLIT>>>

IL TUO UNICO OBIETTIVO: eliminare ripetizioni e ridondanze che stanno tra i due estratti (doppioni che scappano tra macro-blocchi).

REGOLE INVIOLABILI:
1. SILENZIO ASSOLUTO: Rispondi SOLO con i due estratti revisionati.
2. OUTPUT OBBLIGATORIO: Mantieni ESATTAMENTE lo stesso marker <<<SBOBBY_SPLIT>>> tra i due testi revisionati.
3. NON RIASSUMERE MAI: Elimina solo i doppioni. Tutto il resto resta.
4. MANTIENI LA FORMATTAZIONE Markdown: titoli (## / ###), elenchi, grassetti, ecc.
5. FORMULE MATEMATICHE: niente LaTeX, solo testo lineare.
"""


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
def _esegui_sbobinatura_legacy(nome_file_video, api_key_value, app_instance, session_dir_hint=None, resume_session=False):
    app_instance.file_temporanei = []  # Condiviso con l'app per pulizia alla chiusura
    cancel_event = getattr(app_instance, "cancel_event", None)

    def cancelled():
        return cancel_event is not None and cancel_event.is_set()

    def ui_alive():
        try:
            return bool(app_instance.winfo_exists())
        except Exception:
            return False

    def safe_after(delay_ms, callback, *args):
        if not ui_alive():
            return False
        try:
            app_instance.after(delay_ms, callback, *args)
            return True
        except Exception:
            return False

    def safe_progress(value):
        try:
            if ui_alive():
                app_instance.aggiorna_progresso(value)
        except Exception:
            pass

    def safe_phase(text):
        try:
            if ui_alive():
                app_instance.aggiorna_fase(text)
        except Exception:
            pass

    def safe_output_html(path):
        try:
            if ui_alive():
                app_instance.imposta_output_html(path)
        except Exception:
            pass

    def safe_process_done():
        try:
            if ui_alive():
                app_instance.processo_terminato()
        except Exception:
            pass

    def sleep_with_cancel(seconds, step=0.2):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if cancelled():
                return False
            time.sleep(min(step, deadline - time.monotonic()))
        return True

    def wait_for_file_ready(client_for_file, file_obj, max_wait_seconds=900, poll_seconds=3):
        start_time = time.monotonic()
        while True:
            state = str(getattr(file_obj, "state", "")).upper()
            # Alcune versioni SDK ritornano state vuoto/STATE_UNSPECIFIED subito dopo l'upload.
            # Aspettiamo finche' non diventa ACTIVE (o FAILED).
            if "ACTIVE" not in state and "FAILED" not in state:
                if time.monotonic() - start_time > max_wait_seconds:
                    raise TimeoutError("Timeout durante l'elaborazione del file audio sui server Google.")
                if not sleep_with_cancel(poll_seconds):
                    return None
                file_obj = client_for_file.files.get(name=file_obj.name)
                continue
            if "FAILED" in state:
                raise RuntimeError(f"Caricamento fallito (state={state}).")
            return file_obj

    def upload_audio_path(client_for_upload, path_str):
        # Compatibilita' tra versioni diverse di google-genai:
        # alcune usano upload(path=...), altre upload(file=...).
        try:
            return client_for_upload.files.upload(path=path_str)
        except TypeError:
            return client_for_upload.files.upload(file=path_str)

    def _make_inline_audio_part(path_str: str):
        # Prova a inviare l'audio inline (bytes) per evitare upload+polling.
        # Fallback automatico a files.upload se fallisce.
        try:
            with open(path_str, "rb") as f:
                data = f.read()
            # I chunk sono esportati in MP3 (vedi ffmpeg -b:a 48k)
            return types.Part.from_bytes(data=data, mime_type="audio/mpeg")
        except Exception:
            return None
    try:
        if not api_key_value or api_key_value.strip() == "":
            print("Errore: Formato API Key non valido o assente.")
            return

        client = genai.Client(api_key=api_key_value.strip())
        
        def richiedi_chiave_riserva():
            evento = threading.Event()
            esito = {"nuova_chiave": None}

            def mostra_popup():
                try:
                    dialog = ctk.CTkInputDialog(
                        text="Hai esaurito la Quota Gratuita limitata di Google per questo account.\n\nInserisci un'altra API Key appartenente a un account Google DIVERSO per riprendere il processo senza perdere progressi.\n\nLascia vuoto o clicca Annulla per interrompere definitivamente e salvare a metà.",
                        title="🔌 Esaurimento Quota",
                    )
                    esito["nuova_chiave"] = dialog.get_input()
                finally:
                    evento.set()

            if not safe_after(0, mostra_popup):
                evento.set()

            print("   [In attesa di una nuova chiave API dall'utente nel popup...]")
            while not evento.is_set():
                if cancelled():
                    return None
                evento.wait(0.2)
            return esito["nuova_chiave"]

        # ------------------------------
        # SESSIONE (AUTOSAVE / RIPRESA)
        # ------------------------------
        try:
            _safe_mkdir(SESSION_ROOT)
        except Exception:
            pass

        try:
            session_dir = os.path.abspath(session_dir_hint) if session_dir_hint else _session_dir_for_file(nome_file_video)
        except Exception:
            session_dir = os.path.join(tempfile.gettempdir(), "sbobby_session_fallback")

        session_path = os.path.join(session_dir, "session.json")
        phase1_chunks_dir = os.path.join(session_dir, "phase1_chunks")
        phase2_revised_dir = os.path.join(session_dir, "phase2_revised")
        boundary_dir = os.path.join(session_dir, "phase2_boundary")
        macro_path = os.path.join(session_dir, "phase2_macro_blocks.json")

        try:
            _safe_mkdir(session_dir)
            _safe_mkdir(phase1_chunks_dir)
            _safe_mkdir(phase2_revised_dir)
            _safe_mkdir(boundary_dir)
        except Exception:
            pass

        session = None
        if resume_session and os.path.exists(session_path):
            try:
                session = _load_json(session_path)
            except Exception:
                session = None

        if session is None:
            try:
                fp = _file_fingerprint(nome_file_video)
            except Exception:
                fp = {"path": os.path.abspath(nome_file_video), "size": None, "mtime": None}

            session = {
                "schema_version": SESSION_SCHEMA_VERSION,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
                "stage": "phase1",
                "input": fp,
                "settings": {
                    "model": "gemini-2.5-flash",
                    "chunk_minutes": 15,
                    "overlap_seconds": 30,
                    # Macro-blocchi piu' grandi = meno chiamate di revisione (senza riassumere).
                    "macro_char_limit": 22000,
                    # Pre-conversione unica dell'audio per velocizzare taglio/upload dei chunk.
                    "preconvert_audio": True,
                    "audio": {"channels": 1, "sample_rate_hz": 16000, "bitrate": "48k", "format": "mp3"},
                },
                "phase1": {"next_start_sec": 0, "chunks_done": 0, "memoria_precedente": ""},
                "phase2": {"macro_total": 0, "revised_done": 0},
                "boundary": {"pairs_total": 0, "next_pair": 1},
                "outputs": {},
                "last_error": None,
            }
            try:
                _atomic_write_json(session_path, session)
            except Exception:
                pass
        else:
            session.setdefault("schema_version", SESSION_SCHEMA_VERSION)
            session.setdefault("stage", "phase1")
            session.setdefault("phase1", {})
            session.setdefault("phase2", {})
            session.setdefault("boundary", {})
            session.setdefault("outputs", {})

        def save_session():
            try:
                session["updated_at"] = _now_iso()
                _atomic_write_json(session_path, session)
                return True
            except Exception as e:
                print(f"   [!] Autosave sessione fallito: {e}")
                return False

        print(f"[*] Autosalvataggio attivo. Sessione: {session_dir}")

        # Settings (con fallback per sessioni vecchie)
        session.setdefault("settings", {})
        session["settings"].setdefault("chunk_minutes", 15)
        session["settings"].setdefault("overlap_seconds", 30)
        session["settings"].setdefault("macro_char_limit", 22000)
        session["settings"].setdefault("preconvert_audio", True)
        session["settings"].setdefault("audio", {"channels": 1, "sample_rate_hz": 16000, "bitrate": "48k", "format": "mp3"})
        save_session()

        blocco_minuti = int(session.get("settings", {}).get("chunk_minutes", 15) or 15)
        blocco_secondi = blocco_minuti * 60
        sovrapposizione_secondi = int(session.get("settings", {}).get("overlap_seconds", 30) or 30)
        passo_secondi = blocco_secondi - sovrapposizione_secondi
        memoria_precedente = ""
        testo_completo_sbobina = ""

        istruzioni_sistema = PROMPT_SISTEMA

        CHUNK_MD_RE = re.compile(r"^chunk_(\d{3})_(\d+)_(\d+)\.md$", re.IGNORECASE)

        def _list_phase1_chunks():
            items = []
            try:
                for name in os.listdir(phase1_chunks_dir):
                    m = CHUNK_MD_RE.match(name)
                    if not m:
                        continue
                    idx = int(m.group(1))
                    start_sec = int(m.group(2))
                    end_sec = int(m.group(3))
                    items.append((idx, start_sec, end_sec, os.path.join(phase1_chunks_dir, name)))
            except Exception:
                return []
            return sorted(items, key=lambda t: (t[0], t[1], t[2]))

        def _read_text(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()

        def _load_phase1_text():
            chunks = _list_phase1_chunks()
            parts = []
            for _, _, _, p in chunks:
                try:
                    txt = _read_text(p).strip()
                    if txt:
                        parts.append(txt)
                except Exception:
                    continue
            return "\n\n".join(parts).strip()
 
        print(f"[*] Analisi del file originale in corso:\n{os.path.basename(nome_file_video)}")
        safe_phase("Fase: analisi file")
        try:
            # Ricava durata audio leggendo l'output di ffmpeg (ffprobe non è garantito in imageio_ffmpeg)
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            comando_probe = [ffmpeg_exe, "-i", nome_file_video]
            
            # subprocess restituisce un errore intenzionale perché non forniamo un file di output a ffmpeg
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            risultato = subprocess.run(comando_probe, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creation_flags)
            output = risultato.stderr
            match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", output)
            if not match:
                raise ValueError("Impossibile leggere la durata dal file usando FFmpeg.")
            
            ore, minuti, secondi = float(match.group(1)), float(match.group(2)), float(match.group(3))
            durata_totale_secondi = ore * 3600 + minuti * 60 + secondi
        except Exception as e:
            print(f"Errore caricamento audio. File corrotto o formato non supportato.\n{e}")
            return

        print(f"[*] Durata totale rilevata: {int(durata_totale_secondi / 60)} minuti.")

        # Persisti metadati fase1 nella sessione
        session.setdefault("phase1", {})
        session["phase1"]["duration_seconds"] = float(durata_totale_secondi)
        session["phase1"]["step_seconds"] = int(passo_secondi)
        save_session()

        stage = str(session.get("stage", "phase1")).strip().lower()
        if stage not in ("phase1", "phase2", "boundary", "done"):
            stage = "phase1"
            session["stage"] = "phase1"
            save_session()

        # ------------------------------------------
        # PRE-CONVERSIONE UNICA (piu' veloce)
        # ------------------------------------------
        preconv_enabled = bool(session.get("settings", {}).get("preconvert_audio", True))
        preconv_path = os.path.join(session_dir, "sbobby_preconverted_mono16k.mp3")

        def _ensure_preconverted():
            nonlocal preconv_enabled
            if not preconv_enabled:
                return None
            # Se siamo gia' oltre la fase 1, non serve.
            if stage != "phase1":
                return None
            try:
                if os.path.exists(preconv_path) and os.path.getsize(preconv_path) > 1024:
                    print("[*] Pre-conversione: file gia' presente. Riutilizzo.")
                    return preconv_path
            except Exception:
                pass

            safe_phase("Fase 0/3: pre-conversione audio")
            print("[*] Pre-conversione unica dell'audio (mono, 16kHz) in corso...")
            audio_cfg = session.get("settings", {}).get("audio", {}) or {}
            bitrate = str(audio_cfg.get("bitrate") or "48k")

            cmd = [
                ffmpeg_exe, "-y", "-i", nome_file_video,
                "-vn", "-ac", "1", "-ar", "16000", "-b:a", bitrate,
                "-map", "a:0", preconv_path
            ]
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creation_flags)
            if res.returncode != 0:
                stderr = (res.stderr or "").strip()
                if stderr:
                    stderr = "\n".join(stderr.splitlines()[-12:])
                print("[!] Pre-conversione fallita. Continuo senza pre-conversione.")
                if stderr:
                    print(stderr)
                preconv_enabled = False
                return None
            try:
                if os.path.exists(preconv_path) and os.path.getsize(preconv_path) > 1024:
                    print("[*] Pre-conversione completata.")
                    session.setdefault("phase1", {})
                    session["phase1"]["preconverted_path"] = preconv_path
                    session["phase1"]["preconverted_done"] = True
                    save_session()
                    return preconv_path
            except Exception:
                pass
            preconv_enabled = False
            return None

        preconv_used_path = _ensure_preconverted()

        # Ripristino (se presente) dai chunk gia' salvati
        existing_chunks = _list_phase1_chunks()
        start_sec = int(session.get("phase1", {}).get("next_start_sec", 0) or 0)
        if existing_chunks:
            try:
                last_start = max(s for _, s, _, _ in existing_chunks)
                start_sec = max(start_sec, int(last_start + passo_secondi))
            except Exception:
                pass
            testo_completo_sbobina = _load_phase1_text()
            try:
                _, _, _, last_path = existing_chunks[-1]
                memoria_precedente = _read_text(last_path).strip()[-1000:]
            except Exception:
                memoria_precedente = (testo_completo_sbobina or "")[-1000:]
        else:
            # Se stiamo riprendendo direttamente dalla fase2 (o oltre), carica comunque il testo
            if stage != "phase1":
                testo_completo_sbobina = _load_phase1_text()
                memoria_precedente = (testo_completo_sbobina or "")[-1000:]
            else:
                memoria_precedente = str(session.get("phase1", {}).get("memoria_precedente", "") or "")

        if stage == "phase1":
            print("[*] INIZIO FASE 1: Trascrizione a blocchi (Ogni blocco circa 15 min)")
            safe_phase("Fase 1/3: trascrizione")
        else:
            print(f"[*] Ripresa sessione: stage='{stage}'. Salto Fase 1.")
            if stage == "phase2":
                safe_phase("Fase 2/3: revisione")
            elif stage == "boundary":
                safe_phase("Fase 3/3: confine")
            elif stage == "done":
                safe_phase("Fase: esportazione HTML")
            else:
                safe_phase(f"Fase: ripresa ({stage})")
            start_sec = int(durata_totale_secondi)  # skip chunk loop

        blocchi_totali = len(list(range(0, int(durata_totale_secondi), passo_secondi)))
        blocco_corrente_idx = len(list(range(0, int(start_sec), passo_secondi)))

        for inizio_sec in range(int(start_sec), int(durata_totale_secondi), passo_secondi):
            blocco_corrente_idx += 1
            fine_sec = min(inizio_sec + blocco_secondi, durata_totale_secondi)
            
            print(f"\n======================================")
            print(f"-> LAVORAZIONE BLOCCO AUDIO {blocco_corrente_idx} DI {blocchi_totali} (Da {inizio_sec}s a {int(fine_sec)}s)")
            safe_phase(f"Fase 1/3: trascrizione ({blocco_corrente_idx}/{blocchi_totali})")

            if cancelled():
                print("   [*] Operazione annullata dall'utente.")
                return
             
            # Salva i pezzi temporanei nella cartella TEMP del sistema operativo
            nome_chunk = os.path.join(tempfile.gettempdir(), f"sbobby_temp_{inizio_sec}_{int(fine_sec)}.mp3")
            app_instance.file_temporanei.append(nome_chunk)

            audio_file = None
            file_client = None
            successo = False
            rate_limit = False

            try:
                # 1. Taglio
                # Spiegazione per l'utente loggata direttamente in app
                print("   -> (1/3) Estrazione e taglio in corso...")
                durata_cut = fine_sec - inizio_sec
                audio_cfg = session.get("settings", {}).get("audio", {}) or {}
                bitrate = str(audio_cfg.get("bitrate") or "48k")

                # Preferisci taglio dal file preconvertito (piu' veloce) usando stream copy.
                if preconv_used_path and os.path.exists(preconv_used_path):
                    comando_cut = [
                        ffmpeg_exe, "-y",
                        "-ss", str(inizio_sec), "-t", str(durata_cut),
                        "-i", preconv_used_path,
                        "-vn", "-c:a", "copy",
                        "-map", "a:0",
                        "-reset_timestamps", "1",
                        "-avoid_negative_ts", "make_zero",
                        nome_chunk
                    ]
                else:
                    comando_cut = [
                        ffmpeg_exe, "-y", "-i", nome_file_video,
                        "-ss", str(inizio_sec), "-t", str(durata_cut),
                        "-vn", "-ac", "1", "-ar", "16000", "-b:a", bitrate,
                        "-map", "a:0", nome_chunk
                    ]

                creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                risultato_cut = subprocess.run(
                    comando_cut,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=creation_flags,
                )
                if risultato_cut.returncode != 0:
                    # Se il taglio veloce dal preconvertito fallisce, riprova con il metodo classico.
                    if preconv_used_path and os.path.exists(preconv_used_path):
                        comando_cut_fallback = [
                            ffmpeg_exe, "-y", "-i", nome_file_video,
                            "-ss", str(inizio_sec), "-t", str(durata_cut),
                            "-vn", "-ac", "1", "-ar", "16000", "-b:a", bitrate,
                            "-map", "a:0", nome_chunk
                        ]
                        risultato_cut2 = subprocess.run(
                            comando_cut_fallback,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            creationflags=creation_flags,
                        )
                        if risultato_cut2.returncode == 0:
                            risultato_cut = risultato_cut2
                        else:
                            stderr = (risultato_cut2.stderr or "").strip()
                            if stderr:
                                stderr = "\n".join(stderr.splitlines()[-12:])
                                raise RuntimeError(f"FFmpeg ha fallito l'estrazione audio:\n{stderr}")
                            raise RuntimeError("FFmpeg ha fallito l'estrazione audio.")
                    else:
                        stderr = (risultato_cut.stderr or "").strip()
                        if stderr:
                            stderr = "\n".join(stderr.splitlines()[-12:])
                            raise RuntimeError(f"FFmpeg ha fallito l'estrazione audio:\n{stderr}")
                        raise RuntimeError("FFmpeg ha fallito l'estrazione audio.")
                if (not os.path.exists(nome_chunk)) or os.path.getsize(nome_chunk) < 1024:
                    raise RuntimeError("FFmpeg non ha prodotto un chunk audio valido.")

                # 2. Preparazione input audio (preferisci inline bytes, fallback a upload se serve)
                audio_inline = _make_inline_audio_part(nome_chunk)
                audio_mode = "inline" if audio_inline is not None else "upload"
                tried_upload_fallback = False
                if audio_mode == "inline":
                    print("   -> (2/3) Preparazione audio (inline)...")

                # 3. Generazione testuale
                print("   -> (3/3) Generazione sbobina in corso...")
                prompt_dinamico = "Ascolta questo blocco di lezione e crea la sbobina seguendo rigorosamente le istruzioni di sistema."
                if memoria_precedente:
                    prompt_dinamico += f"\n\nATTENZIONE: Stai continuando una stesura. Questo è l'ultimo paragrafo che hai generato nel blocco precedente:\n\"...{memoria_precedente}\"\n\nRiprendi il discorso da qui IN MODO FLUIDO. Usa la stessa grandezza per i titoli. Se all'inizio di questo blocco c'e' sovrapposizione, NON ripetere testualmente le frasi gia' dette, ma se compare anche solo un dettaglio nuovo includilo."

                def _ensure_uploaded_audio_input():
                    nonlocal audio_file, file_client
                    if audio_file is not None:
                        # gia' caricato
                        try:
                            if getattr(audio_file, "uri", None):
                                return types.Part.from_uri(
                                    file_uri=audio_file.uri,
                                    mime_type=(getattr(audio_file, "mime_type", None) or "audio/mpeg"),
                                )
                        except Exception:
                            return audio_file
                        return audio_file

                    print("   -> (2/3) Caricamento sicuro nei server di google...")
                    audio_file = upload_audio_path(client, nome_chunk)
                    file_client = client  # il file e' legato alla chiave che l'ha caricato
                    audio_file = wait_for_file_ready(client, audio_file)
                    if audio_file is None:
                        print("   [*] Operazione annullata dall'utente.")
                        return None
                    try:
                        if getattr(audio_file, "uri", None):
                            return types.Part.from_uri(
                                file_uri=audio_file.uri,
                                mime_type=(getattr(audio_file, "mime_type", None) or "audio/mpeg"),
                            )
                    except Exception:
                        pass
                    return audio_file

                tent = 0
                while tent < 4:
                    try:
                        if audio_mode == "inline" and audio_inline is not None:
                            audio_input = audio_inline
                        else:
                            audio_input = _ensure_uploaded_audio_input()
                            if audio_input is None:
                                return

                        risposta = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=[prompt_dinamico, audio_input],
                            config=types.GenerateContentConfig(
                                system_instruction=istruzioni_sistema,
                                temperature=0.35
                            )
                        )
                        testo_generato = risposta.text.strip()
                        testo_completo_sbobina += f"\n\n{testo_generato}\n\n"
                        memoria_precedente = testo_generato[-1000:]

                        # Autosave: salva il chunk su disco e aggiorna la sessione
                        try:
                            out_chunk_md = os.path.join(
                                phase1_chunks_dir,
                                f"chunk_{blocco_corrente_idx:03}_{inizio_sec}_{int(fine_sec)}.md",
                            )
                            _atomic_write_text(out_chunk_md, testo_generato + "\n")
                            print(f"   [autosave] Chunk salvato: {os.path.basename(out_chunk_md)}")
                        except Exception as save_err:
                            print(f"   [!] Autosave chunk fallito: {save_err}")

                        session["stage"] = "phase1"
                        session.setdefault("phase1", {})
                        session["phase1"]["chunks_done"] = int(blocco_corrente_idx)
                        session["phase1"]["next_start_sec"] = int(inizio_sec + passo_secondi)
                        session["phase1"]["memoria_precedente"] = memoria_precedente
                        session["last_error"] = None
                        save_session()

                        successo = True
                        safe_progress(0.7 * blocco_corrente_idx / blocchi_totali)
                        break
                    except Exception as e:
                        err_txt = str(e)
                        errore = err_txt.lower()

                        # Fallback: se l'inline fallisce per motivi tecnici/dimensione, prova upload+URI per questo chunk.
                        if (
                            audio_mode == "inline"
                            and not tried_upload_fallback
                            and ("invalid_argument" in errore or "badrequest" in errore or "400" in errore or "payload" in errore or "too large" in errore or "size" in errore)
                            and ("quota" not in errore and "resource_exhausted" not in errore and "429" not in errore)
                        ):
                            tried_upload_fallback = True
                            audio_mode = "upload"
                            print("      [Inline audio non accettato. Fallback a upload del chunk...]")
                            # riprova subito senza consumare un tentativo
                            continue

                        # Quota / rate limit
                        if '429' in errore or 'resource_exhausted' in errore or 'quota' in errore:
                            is_daily_limit = (
                                'per day' in errore
                                or 'quota_exceeded' in errore
                                or 'daily' in errore
                                or ('429' in errore and 'minute' not in errore and 'rpm' not in errore)
                            )

                            # Rate limit temporaneo (al minuto)
                            if not is_daily_limit and tent < 3:
                                print("      [Rilevato limite temporaneo. Attesa di 65s per il reset quota al minuto...]")
                                if not sleep_with_cancel(65):
                                    print("   [*] Operazione annullata dall'utente.")
                                    return
                                tent += 1
                                continue

                            # Daily limit: prova cambio chiave
                            print("\n" + "="*50)
                            print("⛔ LIMITE GIORNALIERO RAGGIUNTO!")
                            nuova_api = richiedi_chiave_riserva()
                            if nuova_api and nuova_api.strip():
                                try:
                                    test_c = genai.Client(api_key=nuova_api.strip())
                                    test_c.models.get(model='gemini-2.5-flash')
                                except Exception as err:
                                    print(f"   [!] Chiave non valida fornita: {err}")
                                else:
                                    client = test_c
                                    if audio_mode == "upload":
                                        # Best-effort: elimina il file caricato con la chiave vecchia, poi ricarica con la nuova.
                                        if audio_file is not None and file_client is not None:
                                            try:
                                                file_client.files.delete(name=audio_file.name)
                                            except Exception:
                                                pass
                                        audio_file = None
                                        file_client = None
                                        print("   ✅ Nuova API Key valida! Ricarico questo blocco con la nuova chiave...")
                                        try:
                                            # il nuovo upload verra' eseguito al prossimo tentativo (_ensure_uploaded_audio_input)
                                            pass
                                        except Exception:
                                            pass
                                    else:
                                        print("   ✅ Nuova API Key valida! Ripresa automatica (inline audio).")

                                    tent = 0  # reset tentativi
                                    continue

                            print("="*50)
                            print("Hai esaurito le richieste.")
                            print("="*50)
                            rate_limit = True
                            break

                        # Errore non quota: se e' 400, non ha senso riprovare.
                        if "400" in err_txt or "BadRequest" in err_txt or "INVALID_ARGUMENT" in err_txt:
                            print(f"   [!] Richiesta non valida (400). Dettagli:\n{err_txt}")
                            session["last_error"] = "bad_request_phase1"
                            save_session()
                            return

                        print(f"      [Server occupati o errore: {err_txt}]")
                        print("      [Riprovo in 30 secondi...]")
                        if not sleep_with_cancel(30):
                            print("   [*] Operazione annullata dall'utente.")
                            return
                        tent += 1

            except Exception as e:
                print(f"   [!] Errore durante l'elaborazione del blocco: {e}")

            finally:
                # Pulizia: locale + file remoto, anche in caso di rate limit/errori
                if os.path.exists(nome_chunk):
                    try:
                        os.remove(nome_chunk)
                    except Exception:
                        pass
                if audio_file is not None and file_client is not None:
                    try:
                        file_client.files.delete(name=audio_file.name)
                    except Exception:
                        pass

            if rate_limit:
                session["last_error"] = "rate_limit_phase1"
                save_session()
                print("[*] Interruzione: progressi salvati. Potrai riprendere piu' tardi.")
                return
            if not successo:
                session["last_error"] = f"phase1_chunk_failed_{blocco_corrente_idx}"
                save_session()
                print("   [!] Errore critico durante l'elaborazione del blocco. Interrompo (progressi salvati).")
                return

            # Piccola pausa tra chiamate per evitare rate limit
            if not sleep_with_cancel(5):
                print("   [*] Operazione annullata dall'utente.")
                return

        # Se la fase 1 e' terminata senza interruzioni, passa alla fase 2
        if stage == "phase1":
            session["stage"] = "phase2"
            session["last_error"] = None
            save_session()

        # ==========================================
        # FASE 2: REVISIONE LOGICA E CUCITURA DOPPIONI
        # ==========================================
        print("\n======================================")
        safe_phase("Fase 2/3: revisione")
        print("[*] INIZIO FASE 2: REVISIONE FINALE (Eliminazione Doppioni, Correzione grammaticale, Miglioramento leggibilità, etc.)")

        limite_caratteri = int(session.get("settings", {}).get("macro_char_limit", 22000) or 22000)

        macro_blocchi = None
        if os.path.exists(macro_path):
            try:
                macro_data = _load_json(macro_path)
                macro_blocchi = list(macro_data.get("blocks") or [])
            except Exception:
                macro_blocchi = None

        if not macro_blocchi:
            paragrafi = testo_completo_sbobina.split("\n\n")
            macro_blocchi = []
            blocco_corrente = ""

            for p in paragrafi:
                if len(blocco_corrente) + len(p) > limite_caratteri:
                    if blocco_corrente.strip():
                        macro_blocchi.append(blocco_corrente)
                    blocco_corrente = p + "\n\n"
                else:
                    blocco_corrente += p + "\n\n"
            if blocco_corrente.strip():
                macro_blocchi.append(blocco_corrente)

            try:
                _atomic_write_json(macro_path, {"limit_chars": limite_caratteri, "blocks": macro_blocchi})
            except Exception:
                pass
            
        print(f"Il documento è stato diviso in {len(macro_blocchi)} macro-sezioni per mantenere il livello di dettaglio. Revisione in corso...")
        session.setdefault("phase2", {})
        session["phase2"]["macro_total"] = int(len(macro_blocchi))
        save_session()

        testo_finale_revisionato = ""

        prompt_revisione = PROMPT_REVISIONE
        macro_total = len(macro_blocchi)
        revised_done = 0

        def _norm_for_dedup(txt: str) -> str:
            t = (txt or "").replace("\u00A0", " ").strip().lower()
            t = re.sub(r"\s+", " ", t)
            # Normalizza un minimo la punteggiatura per ridurre falsi negativi.
            t = re.sub(r"\s*([,.;:!?])\s*", r"\1", t)
            return t

        def _local_macro_cleanup(md: str):
            # Rimuove SOLO duplicati certi (identici dopo normalizzazione) e near-duplicati adiacenti molto forti.
            # Non riassume e non elimina contenuti "nuovi": e' conservativo per preservare dettaglio.
            src = (md or "").strip()
            if not src:
                return "", 0, 0, 0, 0

            paras = [p.strip() for p in re.split(r"\n\s*\n+", src) if p and p.strip()]
            if not paras:
                return src, 0, 0, 0, 0

            kept = []
            seen = set()
            removed_exact = 0
            removed_adj = 0
            near_adj = 0
            prev_norm = ""

            for p in paras:
                is_heading = bool(re.match(r"^\s*#{1,6}\s+", p))
                # Evita di deduplicare "a vuoto" stringhe minuscole (rischio di falsi positivi).
                min_len = 20 if is_heading else 60
                norm = _norm_for_dedup(p)

                if len(norm) >= min_len and norm in seen:
                    removed_exact += 1
                    continue

                if prev_norm and len(norm) >= 100 and len(prev_norm) >= 100:
                    r = difflib.SequenceMatcher(None, prev_norm, norm).ratio()
                    if r >= 0.995:
                        removed_adj += 1
                        continue
                    if r >= 0.975:
                        near_adj += 1

                kept.append(p)
                if len(norm) >= min_len:
                    seen.add(norm)
                prev_norm = norm

            cleaned = "\n\n".join(kept).strip()
            total = len(paras)
            return cleaned, removed_exact, removed_adj, near_adj, total

        for i, blocco in enumerate(macro_blocchi, 1):
            if cancelled():
                print("   [*] Operazione annullata dall'utente.")
                return
            safe_phase(f"Fase 2/3: revisione ({i}/{macro_total})")

            # Ripresa: se il macro-blocco e' gia' stato revisionato e salvato, lo ri-usa
            rev_path = os.path.join(phase2_revised_dir, f"rev_{i:03}.md")
            if os.path.exists(rev_path):
                try:
                    testo_rev_esistente = _read_text(rev_path).strip()
                    if testo_rev_esistente:
                        testo_finale_revisionato += f"\n\n{testo_rev_esistente}\n\n"
                        revised_done += 1
                        session["stage"] = "phase2"
                        session.setdefault("phase2", {})
                        session["phase2"]["revised_done"] = int(revised_done)
                        session["last_error"] = None
                        save_session()
                        safe_progress(0.7 + 0.2 * (revised_done / max(1, macro_total)))
                        continue
                except Exception:
                    pass

            blocco_src = (blocco or "").strip()
            blocco_local, removed_exact, removed_adj, near_adj, total_paras = _local_macro_cleanup(blocco_src)
            blocco_for_ai = (blocco_local or blocco_src).strip()
            if removed_exact or removed_adj:
                print(f"   -> Pre-clean locale Macro-blocco {i}/{macro_total}: duplicati rimossi={removed_exact+removed_adj} (sospetti={near_adj}).")

            print(f"   -> Revisione Macro-blocco {i} di {macro_total}...")
            successo_revisione = False
            tent = 0
            while tent < 4:
                try:
                    risposta_rev = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[blocco_for_ai, prompt_revisione],
                        config=types.GenerateContentConfig(
                            temperature=0.1 
                        )
                    )
                    testo_rev = (risposta_rev.text or "").strip()
                    if not testo_rev:
                        raise RuntimeError("Risposta vuota dal modello in revisione.")

                    testo_finale_revisionato += f"\n\n{testo_rev}\n\n"

                    # Autosave: salva la revisione su disco e aggiorna la sessione
                    try:
                        _atomic_write_text(rev_path, testo_rev + "\n")
                        print(f"   [autosave] Revisione salvata: {os.path.basename(rev_path)}")
                    except Exception as save_err:
                        print(f"   [!] Autosave revisione fallito: {save_err}")

                    revised_done += 1
                    session["stage"] = "phase2"
                    session.setdefault("phase2", {})
                    session["phase2"]["revised_done"] = int(revised_done)
                    session["last_error"] = None
                    save_session()

                    successo_revisione = True
                    safe_progress(0.7 + 0.2 * (revised_done / max(1, macro_total)))
                    break
                except Exception as e:
                    errore = str(e).lower()
                    if '429' in errore or 'resource_exhausted' in errore or 'quota' in errore:
                        is_daily_limit = 'per day' in errore or 'quota_exceeded' in errore or 'daily' in errore or ('429' in errore and 'minute' not in errore and 'rpm' not in errore)
                        if not is_daily_limit and tent < 3:
                            print(f"      [Rilevato limite temporaneo. Attesa di 65s per il reset quota al minuto...]")
                            if not sleep_with_cancel(65):
                                print("   [*] Operazione annullata dall'utente.")
                                return
                            tent += 1
                            continue
                        else:
                            print("\n⛔ LIMITE GIORNALIERO RAGGIUNTO durante la revisione!")
                            nuova_api = richiedi_chiave_riserva()
                            if nuova_api and nuova_api.strip():
                                try:
                                    test_c = genai.Client(api_key=nuova_api.strip())
                                    test_c.models.get(model='gemini-2.5-flash')
                                    client = test_c
                                    print("   ✅ Nuova API Key valida! Ripresa automatica della revisione...")
                                    tent = 0
                                    continue
                                except Exception as err:
                                    print(f"   [!] Chiave non valida fornita: {err}")
                            
                            print("   Interruzione: progressi salvati. Potrai riprendere piu' tardi.")
                            session["last_error"] = "quota_daily_limit_phase2"
                            save_session()
                            return
                    print(f"      [Server occupati o errore. Riprovo in 20 secondi...]")
                    if not sleep_with_cancel(20):
                        print("   [*] Operazione annullata dall'utente.")
                        return
                    tent += 1
                    
            if not successo_revisione:
                print(f"   [!] Errore prolungato nella revisione. Salvo il blocco {i} cosi' com'e' per evitare perdite di dati.")
                testo_rev_fallback = (blocco or "").strip()
                testo_finale_revisionato += f"\n\n{testo_rev_fallback}\n\n"
                try:
                    _atomic_write_text(rev_path, testo_rev_fallback + "\n")
                    print(f"   [autosave] Revisione (fallback) salvata: {os.path.basename(rev_path)}")
                except Exception as save_err:
                    print(f"   [!] Autosave revisione fallito: {save_err}")

                revised_done += 1
                session["stage"] = "phase2"
                session.setdefault("phase2", {})
                session["phase2"]["revised_done"] = int(revised_done)
                session["last_error"] = None
                save_session()
            safe_progress(0.7 + 0.2 * (revised_done / max(1, macro_total)))
            if not sleep_with_cancel(5):
                print("   [*] Operazione annullata dall'utente.")
                return

        # ------------------------------------------
        # FASE 2B: REVISIONE DI CONFINE (AUTOSAVE)
        # ------------------------------------------
        if str(session.get("stage", "phase2")).strip().lower() == "phase2":
            session["stage"] = "boundary"
            safe_phase("Fase 3/3: confine")
            session.setdefault("boundary", {})
            session["boundary"]["pairs_total"] = int(max(0, macro_total - 1))
            session["boundary"]["next_pair"] = int(session.get("boundary", {}).get("next_pair", 1) or 1)
            session["last_error"] = None
            save_session()

        stage2 = str(session.get("stage", "phase1")).strip().lower()
        if stage2 == "boundary":
            pairs_total = int(session.get("boundary", {}).get("pairs_total", max(0, macro_total - 1)) or 0)
            if pairs_total > 0:
                try:
                    done_files = [n for n in os.listdir(boundary_dir) if n.lower().startswith("boundary_") and n.lower().endswith(".done")]
                except Exception:
                    done_files = []

                done_idxs = set()
                for n in done_files:
                    m = re.match(r"^boundary_(\d{3})\.done$", n, flags=re.IGNORECASE)
                    if m:
                        try:
                            done_idxs.add(int(m.group(1)))
                        except Exception:
                            pass

                next_pair = int(session.get("boundary", {}).get("next_pair", 1) or 1)
                if done_idxs:
                    next_pair = max(next_pair, max(done_idxs) + 1)

                def _split_paras(t):
                    return [p for p in (t or "").split("\n\n") if p.strip()]

                def _join_paras(parts):
                    return "\n\n".join([p.strip() for p in parts if p and p.strip()]).strip()

                k_par = 6
                MIN_NORM_CHARS_STRICT = 80
                MIN_NORM_CHARS_SUSPECT = 120
                SUSPECT_RATIO = 0.975

                def _is_heading_para(p: str) -> bool:
                    first = (p or "").lstrip()
                    return bool(re.match(r"^#{1,6}\s+\\S", first))

                def _norm_para(p: str) -> str:
                    s = (p or "").strip()
                    # Rimuovi marker Markdown comuni per confronti piu' stabili
                    s = s.replace("**", "")
                    s = re.sub(r"(?m)^\\s*([*+-]|\\d+\\.)\\s+", "", s)  # bullet/numero a inizio riga
                    s = re.sub(r"[^\\w\\s]", " ", s, flags=re.UNICODE)  # rimuove punteggiatura, preserva lettere accentate
                    s = re.sub(r"\\s+", " ", s).strip().lower()
                    return s

                def _strict_dup(tail_p: str, head_p: str) -> bool:
                    # Conservativo: elimina solo duplicati certi (uguali o quasi uguali per contenimento forte).
                    if _is_heading_para(head_p):
                        return False
                    a = _norm_para(tail_p)
                    b = _norm_para(head_p)
                    if len(b) < MIN_NORM_CHARS_STRICT or len(a) < MIN_NORM_CHARS_STRICT:
                        return False
                    if a == b:
                        return True
                    # Se la testa del blocco N+1 e' praticamente contenuta nella coda del blocco N (stesso contenuto),
                    # possiamo rimuovere il duplicato nel blocco N+1 senza perdere dettaglio.
                    if b in a and (len(b) / max(1, len(a))) >= 0.92:
                        return True
                    return False

                def _max_similarity(tail_list, head_list) -> float:
                    best = 0.0
                    for tp in tail_list:
                        na = _norm_para(tp)
                        if len(na) < MIN_NORM_CHARS_SUSPECT:
                            continue
                        for hp in head_list:
                            if _is_heading_para(hp):
                                continue
                            nb = _norm_para(hp)
                            if len(nb) < MIN_NORM_CHARS_SUSPECT:
                                continue
                            r = difflib.SequenceMatcher(a=na, b=nb).ratio()
                            if r > best:
                                best = r
                    return best

                for pair_idx in range(next_pair, pairs_total + 1):
                    if cancelled():
                        print("   [*] Operazione annullata dall'utente.")
                        return
                    safe_phase(f"Fase 3/3: confine ({pair_idx}/{pairs_total})")

                    try:
                        a = _read_text(os.path.join(phase2_revised_dir, f"rev_{pair_idx:03}.md")).strip()
                        b = _read_text(os.path.join(phase2_revised_dir, f"rev_{pair_idx+1:03}.md")).strip()
                    except Exception:
                        a = ""
                        b = ""

                    a_parts = _split_paras(a)
                    b_parts = _split_paras(b)
                    if not a_parts or not b_parts:
                        done_path = os.path.join(boundary_dir, f"boundary_{pair_idx:03}.done")
                        try:
                            _atomic_write_text(done_path, "")
                        except Exception:
                            pass
                        session["boundary"]["next_pair"] = int(pair_idx + 1)
                        save_session()
                        continue

                    tail_count = min(k_par, len(a_parts))
                    head_count = min(k_par, len(b_parts))
                    tail_list = a_parts[-tail_count:]
                    head_list = b_parts[:head_count]

                    # ------------------------------------------
                    # Confine "intelligente" (locale + AI fallback)
                    # ------------------------------------------
                    # 1) Deduplica locale (solo duplicati certi, per non perdere dettaglio)
                    overlap = 0
                    max_try = min(len(tail_list), len(head_list))
                    for L in range(max_try, 0, -1):
                        ok = True
                        for j in range(L):
                            if not _strict_dup(tail_list[-L + j], head_list[j]):
                                ok = False
                                break
                        if ok:
                            overlap = L
                            break

                    if overlap > 0:
                        print(f"   -> Confine {pair_idx}/{pairs_total}: duplicati certi trovati (locale). Rimuovo {overlap} paragrafo/i duplicati dal blocco N+1.")
                        new_b_parts = b_parts[overlap:]
                        new_b = _join_paras(new_b_parts)
                        path_b = os.path.join(phase2_revised_dir, f"rev_{pair_idx+1:03}.md")
                        try:
                            _atomic_write_text(path_b, (new_b + "\n") if new_b else "")
                        except Exception:
                            pass
                        done_path = os.path.join(boundary_dir, f"boundary_{pair_idx:03}.done")
                        try:
                            _atomic_write_text(done_path, "")
                        except Exception:
                            pass
                        session["boundary"]["next_pair"] = int(pair_idx + 1)
                        session["last_error"] = None
                        save_session()
                        safe_progress(0.9 + 0.08 * (pair_idx / max(1, pairs_total)))
                        continue

                    # 2) Se non ci sono segnali di sovrapposizione, salta la chiamata AI
                    sim = _max_similarity(tail_list, head_list)
                    if sim < SUSPECT_RATIO:
                        print(f"   -> Confine {pair_idx}/{pairs_total}: nessuna sovrapposizione evidente (locale). Skip AI.")
                        done_path = os.path.join(boundary_dir, f"boundary_{pair_idx:03}.done")
                        try:
                            _atomic_write_text(done_path, "")
                        except Exception:
                            pass
                        session["boundary"]["next_pair"] = int(pair_idx + 1)
                        session["last_error"] = None
                        save_session()
                        safe_progress(0.9 + 0.08 * (pair_idx / max(1, pairs_total)))
                        continue

                    # 3) Caso ambiguo: fallback all'AI (manteniamo dettaglio, ma consumiamo richieste solo quando serve)
                    tail = _join_paras(tail_list)
                    head = _join_paras(head_list)
                    print(f"   -> Confine {pair_idx}/{pairs_total}: sovrapposizione sospetta (sim={sim:.3f}). Fallback AI...")

                    payload = (
                        "FINE BLOCCO N:\n"
                        + tail
                        + "\n\n<<<SBOBBY_SPLIT>>>\n\n"
                        + "INIZIO BLOCCO N+1:\n"
                        + head
                    )

                    tent = 0
                    while tent < 4:
                        try:
                            resp = client.models.generate_content(
                                model="gemini-2.5-flash",
                                contents=[payload, PROMPT_REVISIONE_CONFINE],
                                config=types.GenerateContentConfig(temperature=0.1),
                            )
                            out = (resp.text or "").strip()
                            if "<<<SBOBBY_SPLIT>>>" not in out:
                                raise RuntimeError("Marker non trovato nell'output di revisione confine.")

                            left, right = out.split("<<<SBOBBY_SPLIT>>>", 1)
                            new_tail = left.strip()
                            new_head = right.strip()
                            if not new_tail or not new_head:
                                raise RuntimeError("Output confine vuoto.")

                            a_prefix = _join_paras(a_parts[:-tail_count])
                            b_suffix = _join_paras(b_parts[head_count:])

                            new_a = (a_prefix + "\n\n" + new_tail).strip() if a_prefix else new_tail
                            new_b = (new_head + "\n\n" + b_suffix).strip() if b_suffix else new_head

                            path_a = os.path.join(phase2_revised_dir, f"rev_{pair_idx:03}.md")
                            path_b = os.path.join(phase2_revised_dir, f"rev_{pair_idx+1:03}.md")
                            _atomic_write_text(path_a, new_a + "\n")
                            _atomic_write_text(path_b, new_b + "\n")

                            done_path = os.path.join(boundary_dir, f"boundary_{pair_idx:03}.done")
                            try:
                                _atomic_write_text(done_path, "")
                            except Exception:
                                pass

                            session["boundary"]["next_pair"] = int(pair_idx + 1)
                            session["last_error"] = None
                            save_session()

                            safe_progress(0.9 + 0.08 * (pair_idx / max(1, pairs_total)))
                            break
                        except Exception as e:
                            errore = str(e).lower()
                            if "429" in errore or "resource_exhausted" in errore or "quota" in errore:
                                is_daily_limit = (
                                    "per day" in errore
                                    or "quota_exceeded" in errore
                                    or "daily" in errore
                                    or ("429" in errore and "minute" not in errore and "rpm" not in errore)
                                )
                                if not is_daily_limit and tent < 3:
                                    print("      [Limite temporaneo. Attesa di 65s...]")
                                    if not sleep_with_cancel(65):
                                        print("   [*] Operazione annullata dall'utente.")
                                        return
                                    tent += 1
                                    continue

                                print("\n[!] LIMITE GIORNALIERO durante revisione confine!")
                                nuova_api = richiedi_chiave_riserva()
                                if nuova_api and nuova_api.strip():
                                    try:
                                        test_c = genai.Client(api_key=nuova_api.strip())
                                        test_c.models.get(model="gemini-2.5-flash")
                                    except Exception as err:
                                        print(f"   [!] Chiave non valida fornita: {err}")
                                    else:
                                        client = test_c
                                        print("   [*] Nuova API Key valida! Ripresa automatica...")
                                        tent = 0
                                        continue

                                print("[*] Interruzione: progressi salvati. Potrai riprendere piu' tardi.")
                                session["last_error"] = "quota_daily_limit_boundary"
                                save_session()
                                return

                            print("      [Errore confine. Riprovo in 20 secondi...]")
                            if not sleep_with_cancel(20):
                                print("   [*] Operazione annullata dall'utente.")
                                return
                            tent += 1

            session["stage"] = "done"
            session["last_error"] = None
            save_session()

        # ==========================================
        # 3. SALVATAGGIO FINALE (MARKDOWN + HTML)
        # ==========================================
        safe_phase("Fase: esportazione HTML")
        base_name = os.path.basename(nome_file_video)
        nome_puro = os.path.splitext(base_name)[0] if base_name else ""
        titolo = safe_output_basename(nome_puro) if nome_puro else "Sbobina"

        # Salva SEMPRE sul Desktop (cross-platform). Fallback: home.
        cartella_origine = get_desktop_dir()
        try:
            os.makedirs(cartella_origine, exist_ok=True)
        except Exception:
            cartella_origine = USER_HOME

        nome_file_html = os.path.join(cartella_origine, f"{titolo}_Sbobina.html")
        if not base_name:
            nome_file_html = os.path.join(cartella_origine, "Sbobina_Definitiva.html")

        def _sanitize_html_basic(html: str) -> str:
            # Sanitizzazione di base (difensiva) nel caso l'AI inserisca HTML pericoloso.
            html = re.sub(r"(?is)<script\b.*?>.*?</script>", "", html)
            html = re.sub(r"(?is)<(iframe|object|embed)\b.*?>.*?</\1>", "", html)
            html = re.sub(r"(?i)\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", html)
            html = re.sub(r"(?i)javascript:", "", html)
            return html
        
        def _normalize_inline_star_lists(md: str) -> str:
            # Normalizza elenchi che a volte l'AI produce in modo non-standard.
            # Obiettivo: farli diventare liste Markdown reali, senza interpretare '*' come testo.
            src = (md or "").replace("\u00A0", " ")

            list_line_re = r"^\s*([*+-]|\d+\.)\s+"
            # Bullet unicode che il modello usa spesso (e che Markdown non interpreta come liste).
            bullet_top = ("\u25cf", "\u2022", "\u25aa", "\u2023")  # ● • ▪ ‣
            bullet_sub = ("\u25e6", "\u25cb", "\u2219")  # ◦ ○ ∙

            # 1) Trasforma elenchi in-line tipo "Esempi: * Voce1 ... * Voce2 ..."
            out_lines = []
            in_fence = False
            for line in src.splitlines():
                s = line.strip()
                if s.startswith("```"):
                    in_fence = not in_fence
                    out_lines.append(line)
                    continue
                if in_fence:
                    out_lines.append(line)
                    continue

                # Caso A: riga che INIZIA con bullet unicode -> lista Markdown.
                if not re.match(list_line_re, line):
                    m = re.match(r"^(\s*)([\u25cf\u2022\u25aa\u2023\u25e6\u25cb\u2219])\s+(.*)$", line)
                    if m:
                        bullet = m.group(2)
                        rest = m.group(3).strip()
                        if rest:
                            prefix = "- " if bullet in bullet_top else "    - "
                            out_lines.append(prefix + rest)
                            continue

                # Caso B: bullet unicode "in mezzo" a una riga -> spezza in lista.
                # Esempio: "Testo introduttivo. ● **Voce:** ... ● **Voce2:** ..."
                if not re.match(list_line_re, line) and re.search(r"[\u25cf\u2022\u25aa\u2023]\s+(\*\*|[A-ZÀ-ÖØ-Ý])", line):
                    if re.search(r"\s[\u25cf\u2022\u25aa\u2023]\s+", line):
                        parts = re.split(r"\s*[\u25cf\u2022\u25aa\u2023]\s+", line)
                        if len(parts) > 1:
                            first = (parts[0] or "").rstrip()
                            if first:
                                out_lines.append(first)
                                out_lines.append("")
                            for item in parts[1:]:
                                item = (item or "").strip()
                                if item:
                                    out_lines.append("- " + item)
                            continue

                # Converti solo se:
                # - c'e' un ":" seguito da "* " (tipico "Esempi: * ... * ...")
                # - non e' gia' una lista/numero
                if not re.match(r"^\s*([*+-]|\d+\.)\s+", line) and re.search(r":[ \t]*\*[ \t]+(\*\*|[A-ZÀ-ÖØ-Ý])", line):
                    if line.count("* ") >= 1:
                        line2 = re.sub(r":[ \t]*\*[ \t]+", ":\n\n- ", line, count=1)
                        line2 = re.sub(r"[ \t]+\*[ \t]+", "\n- ", line2)
                        out_lines.extend(line2.splitlines())
                        continue

                out_lines.append(line)

            mid = "\n".join(out_lines)

            # 2) Python-Markdown spesso richiede una riga vuota prima di una lista per riconoscerla.
            # Se la lista parte subito dopo una riga di testo, aggiungiamo una blank line.
            fixed = []
            in_fence = False
            for line in mid.splitlines():
                s = line.strip()
                if s.startswith("```"):
                    in_fence = not in_fence
                    fixed.append(line)
                    continue
                if in_fence:
                    fixed.append(line)
                    continue

                is_list = bool(re.match(r"^\s{0,3}([*+-]|\d+\.)\s+", line))
                if is_list and fixed:
                    prev = fixed[-1]
                    prev_is_list = bool(re.match(r"^\s{0,3}([*+-]|\d+\.)\s+", prev))
                    if prev.strip() != "" and not prev_is_list:
                        fixed.append("")

                fixed.append(line)

            return "\n".join(fixed)

        # Ricostruisci il testo finale dai file revisionati (include la revisione di confine).
        blocchi_finali = []
        try:
            if os.path.isdir(phase2_revised_dir):
                rev_files = []
                for fn in os.listdir(phase2_revised_dir):
                    if re.match(r"^rev_\\d{3}\\.md$", fn):
                        rev_files.append(os.path.join(phase2_revised_dir, fn))
                for p in sorted(rev_files):
                    blocchi_finali.append(_read_text(p))
        except Exception:
            blocchi_finali = []
        if not blocchi_finali:
            blocchi_finali = [testo_finale_revisionato]

        body_md = "\n\n".join([b.strip() for b in blocchi_finali if b and b.strip()]).strip()

        # Indice semplice: elenca le sezioni "## ..." se presenti
        headings = []
        seen = set()
        for line in body_md.splitlines():
            m = re.match(r"^##\\s+(.+?)\\s*$", line.strip())
            if not m:
                continue
            h = re.sub(r"\\s+#.*$", "", m.group(1)).strip()
            if h and h not in seen:
                headings.append(h)
                seen.add(h)

        if headings:
            index_md = "## Indice\n" + "\n".join([f"- {h}" for h in headings]) + "\n\n"
        else:
            index_md = ""

        final_md = f"# {titolo}\n\n{index_md}{body_md}\n"
        final_md = _normalize_inline_star_lists(final_md)

        # Export HTML: serve per copia-incolla su Google Docs (file locale, stile leggibile).
        html_body = markdown.markdown(final_md, extensions=["extra", "sane_lists"], output_format="html5")
        html_body = _sanitize_html_basic(html_body)
        html_doc = f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{titolo} - Sbobina</title>
  <style>
    :root {{
      --text: #111;
      --muted: #444;
      --bg: #fff;
      --rule: #e6e6e6;
    }}
    body {{
      font-family: Georgia, "Times New Roman", serif;
      line-height: 1.6;
      color: var(--text);
      background: var(--bg);
      max-width: 980px;
      margin: 0 auto;
      padding: 48px 22px;
    }}
    h1 {{ font-size: 2.0rem; margin: 0 0 0.9rem; }}
    h2 {{ font-size: 1.35rem; margin: 1.6rem 0 0.6rem; padding-top: 0.2rem; border-top: 1px solid var(--rule); }}
    h3 {{ font-size: 1.15rem; margin: 1.1rem 0 0.45rem; }}
    p, li {{ margin: 0.55rem 0; }}
    ul, ol {{ padding-left: 1.25rem; }}
    strong {{ font-weight: 700; }}
    hr {{ border: 0; border-top: 1px solid var(--rule); margin: 1.2rem 0; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; font-size: 0.95em; }}
    blockquote {{ margin: 0.9rem 0; padding: 0.1rem 0 0.1rem 1rem; border-left: 3px solid var(--rule); color: var(--muted); }}
  </style>
</head>
<body>
{html_body}
</body>
</html>
"""
        try:
            _atomic_write_text(nome_file_html, html_doc)
        except Exception as e:
            print(f"[!] Errore salvataggio HTML: {e}")

        try:
            if os.path.exists(nome_file_html):
                safe_output_html(nome_file_html)
        except Exception:
            pass

        try:
            session.setdefault("outputs", {})
            session["outputs"]["html"] = nome_file_html
            save_session()
        except Exception:
            pass

        print(f"\n======================================")
        print("SBOBINATURA COMPLETATA CON SUCCESSO!")
        print(f"File salvato in: {cartella_origine}")
        safe_phase("Fase: completato")

        # Pulizia: rimuovi il file preconvertito (grande) se presente. I progressi testuali restano nella sessione.
        try:
            if preconv_used_path and os.path.exists(preconv_used_path):
                os.remove(preconv_used_path)
        except Exception:
            pass
        
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
        if cancelled():
            safe_phase("Fase: annullato")
        else:
            safe_progress(1.0)
        safe_process_done()


def esegui_sbobinatura(nome_file_video, api_key_value, app_instance, session_dir_hint=None, resume_session=False):
    # Wrapper stabile: mantiene la firma pubblica mentre l'implementazione evolve.
    return _esegui_sbobinatura_legacy(
        nome_file_video,
        api_key_value,
        app_instance,
        session_dir_hint=session_dir_hint,
        resume_session=resume_session,
    )


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
        self.session_dir = None
        self.resume_session = False
        self.is_running = False
        self.cancel_event = threading.Event()
        self.file_temporanei = []  # Lista file temp condivisa col thread
        self.last_output_html = None
        self.last_output_dir = None
        self._run_started_monotonic = None
        self._file_loaded_monotonic = None
        self._eta_ema_seconds = None

        # Intercetta la chiusura della finestra per pulire i file temporanei
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        # SPACING TOP
        ctk.CTkFrame(self, fg_color="transparent", height=15).grid(row=0, column=0)

        # API KEY CARD
        self.api_card = ctk.CTkFrame(self, fg_color=self.TERMINAL_BG, corner_radius=12, border_width=1, border_color=self.BORDER)
        self.api_card.grid(row=1, column=0, padx=30, pady=(15, 0), sticky="ew")
        self.api_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.api_card, text="🔑 API Key Gemini", font=(FONT_UI, 14), text_color=self.TEXT_DIM).grid(row=0, column=0, sticky="w", padx=(18, 12), pady=14)
        self.entry_api = ctk.CTkEntry(self.api_card, placeholder_text="Incolla la tua API Key qui...", show="*", font=(FONT_UI, 13), height=38, corner_radius=8, fg_color=self.CARD_BG, border_color=self.BORDER, text_color=self.TEXT_BRIGHT)
        self.entry_api.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=14)
        
        self.btn_show_api = ctk.CTkButton(self.api_card, text="👁", width=38, height=38, corner_radius=8, fg_color=self.CARD_BG, hover_color=self.BORDER, border_color=self.BORDER, border_width=1, text_color=self.TEXT_BRIGHT, command=self.toggle_api_visibility)
        self.btn_show_api.grid(row=0, column=2, padx=(0, 18), pady=14)
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
        self.console_card.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(self.console_card, text="⚡ Log Eventi", font=(FONT_UI, 12, "bold"), text_color=self.TEXT_DIM).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        self.progress_bar = ctk.CTkProgressBar(self.console_card, height=6, corner_radius=3, fg_color=self.TERMINAL_BG, progress_color=self.ACCENT)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))
        self.progress_bar.set(0)

        # STATUS BAR (fase + ETA + azioni rapide)
        self.status_bar = ctk.CTkFrame(self.console_card, fg_color="transparent")
        self.status_bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        self.status_bar.grid_columnconfigure(1, weight=1)

        self.lbl_phase = ctk.CTkLabel(self.status_bar, text="Fase: pronto", font=(FONT_UI, 11), text_color=self.TEXT_DIM)
        self.lbl_phase.grid(row=0, column=0, sticky="w")

        self.lbl_eta = ctk.CTkLabel(self.status_bar, text="ETA: —", font=(FONT_UI, 11), text_color=self.TEXT_DIM)
        self.lbl_eta.grid(row=0, column=1, sticky="e", padx=(8, 0))

        self.btn_open_folder = ctk.CTkButton(
            self.status_bar,
            text="Apri cartella",
            width=110,
            height=28,
            corner_radius=8,
            fg_color=self.CARD_BG,
            hover_color=self.BORDER,
            border_color=self.BORDER,
            border_width=1,
            text_color=self.TEXT_BRIGHT,
            command=self.apri_cartella_output,
            state="disabled",
        )
        self.btn_open_folder.grid(row=0, column=2, padx=(10, 6), sticky="e")

        self.btn_open_html = ctk.CTkButton(
            self.status_bar,
            text="Apri HTML",
            width=90,
            height=28,
            corner_radius=8,
            fg_color=self.CARD_BG,
            hover_color=self.BORDER,
            border_color=self.BORDER,
            border_width=1,
            text_color=self.TEXT_BRIGHT,
            command=self.apri_file_html,
            state="disabled",
        )
        self.btn_open_html.grid(row=0, column=3, padx=(0, 6), sticky="e")

        self.btn_cancel = ctk.CTkButton(
            self.status_bar,
            text="Stop",
            width=70,
            height=28,
            corner_radius=8,
            fg_color="#B00020",
            hover_color="#8E001A",
            text_color="white",
            command=self.annulla_processo,
            state="disabled",
        )
        self.btn_cancel.grid(row=0, column=4, sticky="e")

        self.console = ctk.CTkTextbox(self.console_card, font=(FONT_MONO, 12), fg_color=self.TERMINAL_BG, text_color=self.TERMINAL_FG, corner_radius=8, wrap="word", border_width=0)
        self.console.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 12))
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
        lk_gh.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/vimuw/Sbobby"))
        
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
        # Se esiste una sessione incompleta per questo file, proponi ripresa o reset.
        try:
            session_dir = _session_dir_for_file(percorso_file)
            session_path = os.path.join(session_dir, "session.json")
            resume = False
            if os.path.exists(session_path):
                sess = _load_json(session_path) or {}
                stage = (sess.get("stage") or "").strip().lower()
                msg = None
                if stage == "done":
                    msg = (
                        "Ho trovato una sessione GIA' COMPLETATA per questo file.\n\n"
                        "Vuoi riutilizzare i risultati salvati (riesportare HTML/MD senza consumare token)?\n\n"
                        "Si = Riutilizza\nNo = Ricomincia da zero\nAnnulla = Non cambiare file"
                    )
                else:
                    msg = (
                        "Ho trovato una sessione salvata per questo file.\n\n"
                        "Vuoi riprendere da dove eri rimasto?\n\n"
                        "Si = Riprendi\nNo = Ricomincia da zero\nAnnulla = Non cambiare file"
                    )

                scelta = messagebox.askyesnocancel("Sessione trovata", msg)
                if scelta is None:
                    return
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

            self.session_dir = session_dir
            self.resume_session = resume
        except Exception as e:
            self.session_dir = None
            self.resume_session = False
            print(f"[!] Errore controllo sessione: {e}")

        self.file_path = percorso_file
        # Timestamp per misurare il tempo totale dalla selezione del file fino alla fine.
        try:
            self._file_loaded_monotonic = time.monotonic()
        except Exception:
            self._file_loaded_monotonic = None
        self.drop_icon.configure(text="✅")
        self.lbl_file.configure(text=os.path.basename(self.file_path), text_color=self.TEXT_BRIGHT)
        if self.resume_session:
            self.lbl_file_hint.configure(text="Sessione trovata: riprendero' da dove eri rimasto")
        else:
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

    def toggle_api_visibility(self):
        if self.entry_api.cget("show") == "*":
            self.entry_api.configure(show="")
            self.btn_show_api.configure(text="🙈")
        else:
            self.entry_api.configure(show="*")
            self.btn_show_api.configure(text="👁")

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
            test_client.models.get(model='gemini-2.5-flash')
        except Exception as e:
            messagebox.showerror("API Key non valida", f"La chiave API non è valida o non hai accesso ai server Google.\nControlla di averla copiata correttamente, senza spazi extra.\n\nErrore: {e}")
            return
        save_config(api_key)

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
        self.btn_avvia.configure(state="normal", fg_color=self.SUCCESS, text="▶  AVVIA GENERAZIONE SBOBINA")
        self.progress_bar.set(0)
        self.btn_cancel.configure(state="disabled")
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
            self.cancel_event.set()
            self.btn_cancel.configure(state="disabled")
            self._set_phase_ui("Fase: annullamento...")
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
            self.cancel_event.set()
            try:
                self.btn_cancel.configure(state="disabled")
                self._set_phase_ui("Fase: annullamento...")
            except Exception:
                pass
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

