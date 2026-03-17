"""
Core pipeline for Sbobby (no UI widgets touched directly).

This module contains the heavy workflow:
- FFmpeg duration/probe, optional pre-conversion, chunk cutting
- Gemini generation (chunk), macro revision, boundary revision
- Autosave sessions and final HTML export
"""

from __future__ import annotations

import difflib
import json
import os
import platform
import re
import shutil
import tempfile
import threading
import time

import customtkinter as ctk
from google import genai
from google.genai import types

from sbobby.dedup_utils import local_macro_cleanup
from sbobby.ffmpeg_utils import cut_chunk_to_mp3, get_ffmpeg_exe, preconvert_to_mono16k_mp3, probe_duration_seconds
from sbobby.html_export import build_html_document, normalize_inline_star_lists
from sbobby.pipeline_settings import load_and_sanitize_settings
from sbobby.shared import (
    DEFAULT_MODEL,
    FONT_UI,
    PROMPT_REVISIONE,
    PROMPT_REVISIONE_CONFINE,
    PROMPT_SISTEMA,
    SESSION_SCHEMA_VERSION,
    USER_HOME,
    _atomic_write_json,
    _atomic_write_text,
    _load_json,
    _now_iso,
    _safe_mkdir,
    _session_dir_for_file,
    debug_log,
    get_desktop_dir,
    safe_output_basename,
)


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

    # ---- ETA step-based (thread-safe hooks) ----
    def safe_set_work_totals(chunks_total=None, macro_total=None, boundary_total=None):
        try:
            if ui_alive() and hasattr(app_instance, "set_work_totals"):
                app_instance.set_work_totals(
                    chunks_total=chunks_total,
                    macro_total=macro_total,
                    boundary_total=boundary_total,
                )
        except Exception:
            pass

    def safe_update_work_done(kind: str, done: int, total: int = None):
        try:
            if ui_alive() and hasattr(app_instance, "update_work_done"):
                app_instance.update_work_done(kind, done, total=total)
        except Exception:
            pass

    def safe_register_step_time(kind: str, seconds: float, done: int = None, total: int = None):
        try:
            if ui_alive() and hasattr(app_instance, "register_step_time"):
                app_instance.register_step_time(kind, seconds, done=done, total=total)
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

    def _make_inline_audio_part(path_str: str, max_bytes: int | None = None):
        # Prova a inviare l'audio inline (bytes) per evitare upload+polling.
        # Fallback automatico a files.upload se fallisce.
        try:
            if max_bytes is not None:
                try:
                    size = int(os.path.getsize(path_str))
                    if size > int(max_bytes):
                        debug_log(f"inline_audio skip: size={size} > max_bytes={int(max_bytes)} ({os.path.basename(path_str)})")
                        return None
                except Exception:
                    # Se non riusciamo a stimare la size, proviamo comunque.
                    pass
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
                # CTkInputDialog tende a essere "topmost" e non sempre minimizzabile.
                # Usiamo un CTkToplevel standard: non topmost (non resta sopra al browser) e minimizzabile.
                win = None
                try:
                    if not ui_alive():
                        return

                    win = ctk.CTkToplevel(app_instance)
                    try:
                        win.configure(fg_color=getattr(app_instance, "CARD_BG", "#1C2432"))
                    except Exception:
                        pass
                    try:
                        win.title("🔌 Esaurimento Quota")
                    except Exception:
                        pass

                    try:
                        # Larghezza fissa, altezza dinamica: la calcoliamo dopo aver creato i widget
                        # cosi' non rimane spazio vuoto e cresce se aggiungi testo.
                        win.geometry("440x200")
                    except Exception:
                        pass
                    try:
                        win.resizable(False, False)
                    except Exception:
                        pass

                    # Mantieni la finestra "legata" all'app (modal solo per l'app), ma NON topmost globale.
                    try:
                        win.transient(app_instance)
                    except Exception:
                        pass
                    try:
                        win.attributes("-topmost", False)
                    except Exception:
                        pass

                    msg = (
                        "La quota del tuo account Google per le API Gemini sembra esaurita (o temporaneamente limitata).\n\n"
                        "Se hai un'altra API Key con quota disponibile, incollala qui per continuare da dove eri rimasto, "
                        "senza perdere i progressi.\n\n"
                        "In alternativa, premi Annulla: i progressi restano salvati e potrai riprendere piu' tardi."
                    )
                    ctk.CTkLabel(
                        win,
                        text=msg,
                        font=(FONT_UI, 12),
                        text_color=getattr(app_instance, "TEXT_BRIGHT", "#E7ECF4"),
                        justify="left",
                        wraplength=400,
                    ).pack(padx=18, pady=(18, 10), anchor="w")

                    entry = ctk.CTkEntry(
                        win,
                        placeholder_text="Incolla qui la nuova API Key...",
                        show="*",
                        font=(FONT_UI, 13),
                        height=34,
                    )
                    try:
                        entry.configure(
                            fg_color=getattr(app_instance, "TERMINAL_BG", "#111824"),
                            border_color=getattr(app_instance, "BORDER", "#2B3444"),
                            text_color=getattr(app_instance, "TEXT_BRIGHT", "#E7ECF4"),
                            placeholder_text_color=getattr(app_instance, "TEXT_DIM", "#A6B0C0"),
                        )
                    except Exception:
                        pass
                    entry.pack(fill="x", padx=18, pady=(0, 12))

                    btns = ctk.CTkFrame(win, fg_color="transparent")
                    btns.pack(fill="x", padx=18, pady=(0, 14))

                    def _close_and_set(value):
                        try:
                            esito["nuova_chiave"] = value
                        except Exception:
                            pass
                        try:
                            if win is not None and win.winfo_exists():
                                try:
                                    win.grab_release()
                                except Exception:
                                    pass
                                win.destroy()
                        finally:
                            evento.set()

                    def on_ok():
                        v = None
                        try:
                            v = (entry.get() or "").strip() or None
                        except Exception:
                            v = None
                        _close_and_set(v)

                    def on_cancel():
                        _close_and_set(None)

                    b_cancel = ctk.CTkButton(
                        btns,
                        text="Annulla",
                        width=110,
                        height=30,
                        corner_radius=10,
                        fg_color=getattr(app_instance, "BTN_SECONDARY_BG", "#253043"),
                        hover_color=getattr(app_instance, "BTN_SECONDARY_HOVER", "#2D3A52"),
                        border_width=1,
                        border_color=getattr(app_instance, "BORDER", "#2B3444"),
                        text_color=getattr(app_instance, "TEXT_BRIGHT", "#E7ECF4"),
                        command=on_cancel,
                    )
                    b_cancel.pack(side="left")
                    b_ok = ctk.CTkButton(
                        btns,
                        text="Continua",
                        width=110,
                        height=30,
                        corner_radius=10,
                        fg_color=getattr(app_instance, "SUCCESS", "#16A34A"),
                        hover_color=getattr(app_instance, "SUCCESS_HOVER", "#15803D"),
                        text_color="white",
                        command=on_ok,
                    )
                    b_ok.pack(side="right")

                    try:
                        win.protocol("WM_DELETE_WINDOW", on_cancel)
                    except Exception:
                        pass

                    # Auto-size: usa l'altezza "richiesta" dai widget, evitando spazio vuoto.
                    # Facciamo 2 passate (subito e dopo un attimo) perche' su alcuni sistemi
                    # la reqheight si stabilizza solo dopo che Tk ha disegnato tutto.
                    def _apply_autosize():
                        try:
                            target_w = 440
                            win.update_idletasks()
                            req_h = int(win.winfo_reqheight())
                            # clamp per evitare finestre troppo grandi su schermi piccoli
                            max_h = int(max(260, win.winfo_screenheight() * 0.80))
                            # piccolo margine per safety (evita tagli ai bottoni), ma non aggiunge "vuoto" evidente.
                            target_h = min(req_h + 6, max_h)
                            # Se per qualche motivo la reqheight e' zero/strana, non stringere troppo.
                            if target_h < 240:
                                target_h = 240
                            win.geometry(f"{target_w}x{target_h}")
                        except Exception:
                            pass

                    _apply_autosize()
                    try:
                        win.after(120, _apply_autosize)
                    except Exception:
                        pass

                    # Modal solo per l'app: blocca click sulla UI finche' non rispondi, ma non forza topmost sul sistema.
                    try:
                        win.grab_set()
                    except Exception:
                        pass

                    try:
                        entry.focus_set()
                    except Exception:
                        pass

                    # Centra grossolanamente rispetto alla finestra principale.
                    try:
                        win.update_idletasks()
                        px = int(app_instance.winfo_rootx())
                        py = int(app_instance.winfo_rooty())
                        pw = int(app_instance.winfo_width())
                        ph = int(app_instance.winfo_height())
                        w = int(win.winfo_width())
                        h = int(win.winfo_height())
                        x = max(0, px + (pw // 2) - (w // 2))
                        y = max(0, py + (ph // 2) - (h // 2))
                        # Sposta soltanto: non riscrivere w/h, altrimenti rischiamo di perdere l'auto-size.
                        win.geometry(f"+{x}+{y}")
                    except Exception:
                        pass
                except Exception:
                    # In caso di problemi, non bloccare il worker thread.
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
                    "model": DEFAULT_MODEL,
                    "chunk_minutes": 15,
                    "overlap_seconds": 30,
                    # Macro-blocchi piu' grandi = meno chiamate di revisione (senza riassumere).
                    "macro_char_limit": 22000,
                    # Pre-conversione unica dell'audio per velocizzare taglio/upload dei chunk.
                    "preconvert_audio": True,
                    # Unico setting effettivamente usato oggi: bitrate MP3 dei chunk/preconvert.
                    "audio": {"bitrate": "48k"},
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

        # Settings (con fallback per sessioni vecchie) + validazione (resiliente a valori strani).
        settings, settings_changed = load_and_sanitize_settings(session)
        if settings_changed:
            save_session()

        model_name = settings.model
        blocco_minuti = settings.chunk_minutes
        blocco_secondi = settings.chunk_seconds
        sovrapposizione_secondi = settings.overlap_seconds
        passo_secondi = settings.step_seconds
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
            # Probe robusto della durata (gestisce path non-ASCII e "Duration: N/A").
            ffmpeg_exe = get_ffmpeg_exe()
            durata_totale_secondi, reason = probe_duration_seconds(nome_file_video, ffmpeg_exe=ffmpeg_exe)
            if durata_totale_secondi is None:
                raise ValueError(str(reason or "Impossibile leggere la durata dal file usando FFmpeg."))
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
        preconv_enabled = bool(settings.preconvert_audio)
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
            bitrate = str(settings.audio_bitrate or "48k")

            ok, err = preconvert_to_mono16k_mp3(
                input_path=nome_file_video,
                output_path=preconv_path,
                bitrate=bitrate,
                ffmpeg_exe=ffmpeg_exe,
                stop_event=cancel_event,
            )
            if not ok:
                if str(err or "").strip().lower() == "cancelled" or cancelled():
                    print("   [*] Operazione annullata dall'utente.")
                    return None
                print("[!] Pre-conversione fallita. Continuo senza pre-conversione.")
                if err:
                    print(err)
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
        if cancelled():
            return

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
            print("[*] INIZIO FASE 1: Trascrizione a blocchi (circa 15 min per blocco)")
            print("    - Cosa fa: taglia l'audio in blocchi e genera una sbobina dettagliata per ogni blocco.")
            print("    - Perche': blocchi piu' piccoli aiutano a mantenere alto il dettaglio e ridurre errori.")
            safe_phase("Fase 1/3: trascrizione (chunk)")
        else:
            print(f"[*] Ripresa sessione: stage='{stage}'. Salto Fase 1.")
            if stage == "phase2":
                safe_phase("Fase 2/3: revisione")
            elif stage == "boundary":
                safe_phase("Fase 3/3: confini (anti-doppioni)")
            elif stage == "done":
                safe_phase("Fase: esportazione HTML")
            else:
                safe_phase(f"Fase: ripresa ({stage})")
            start_sec = int(durata_totale_secondi)  # skip chunk loop

        dur_int = int(durata_totale_secondi)
        # range(0, n, step) ha lunghezza: 0 se n<=0, altrimenti ceil(n/step)
        blocchi_totali = 0 if dur_int <= 0 else (dur_int + passo_secondi - 1) // passo_secondi
        start_int = int(start_sec)
        blocco_corrente_idx = 0 if start_int <= 0 else (start_int + passo_secondi - 1) // passo_secondi

        # Per ETA stabile: imposta totali e progresso corrente (utile anche in ripresa).
        safe_set_work_totals(chunks_total=blocchi_totali)
        safe_update_work_done("chunks", blocco_corrente_idx, total=blocchi_totali)

        bitrate_default = str(settings.audio_bitrate or "48k")
        prefetch_enabled = bool(settings.prefetch_next_chunk)
        inline_max_bytes = settings.inline_max_bytes

        next_cut = None  # {"start": int, "end": int, "path": str, "thread": Thread, "result": dict}

        def _cut_chunk_to_path(start_s: int, end_s: float, out_path: str, bitrate: str):
            durata = float(end_s) - float(start_s)
            if durata <= 0:
                return False, "durata_chunk_non_valida"
            # Preferisci taglio dal file preconvertito (piu' veloce) usando stream copy.
            if preconv_used_path and os.path.exists(preconv_used_path):
                ok, err = cut_chunk_to_mp3(
                    input_path=preconv_used_path,
                    output_path=out_path,
                    start_sec=start_s,
                    duration_sec=durata,
                    ffmpeg_exe=ffmpeg_exe,
                    stream_copy=True,
                    bitrate=bitrate,
                    stop_event=cancel_event,
                )
                if ok:
                    return True, None
                debug_log(f"cut(stream_copy) failed; fallback reencode: {err}")

            return cut_chunk_to_mp3(
                input_path=nome_file_video,
                output_path=out_path,
                start_sec=start_s,
                duration_sec=durata,
                ffmpeg_exe=ffmpeg_exe,
                stream_copy=False,
                bitrate=bitrate,
                stop_event=cancel_event,
            )

        def _start_prefetch(next_start_s: int, next_end_s: float, bitrate: str):
            nonlocal next_cut
            if not prefetch_enabled:
                return
            if next_start_s is None or next_end_s is None:
                return
            if next_cut is not None:
                return
            try:
                path_next = os.path.join(tempfile.gettempdir(), f"sbobby_temp_{int(next_start_s)}_{int(next_end_s)}.mp3")
            except Exception:
                return
            app_instance.file_temporanei.append(path_next)
            result = {"ok": False, "err": None}

            def worker():
                ok, err = _cut_chunk_to_path(int(next_start_s), float(next_end_s), path_next, bitrate=bitrate)
                result["ok"] = bool(ok)
                result["err"] = err

            t = threading.Thread(target=worker, daemon=True)
            next_cut = {"start": int(next_start_s), "end": int(next_end_s), "path": path_next, "thread": t, "result": result}
            t.start()

        for inizio_sec in range(int(start_sec), int(durata_totale_secondi), passo_secondi):
            blocco_corrente_idx += 1
            fine_sec = min(inizio_sec + blocco_secondi, durata_totale_secondi)

            print(f"\n======================================")
            print(f"-> LAVORAZIONE BLOCCO AUDIO {blocco_corrente_idx} DI {blocchi_totali} (Da {inizio_sec}s a {int(fine_sec)}s)")
            safe_phase(f"Fase 1/3: trascrizione (chunk {blocco_corrente_idx}/{blocchi_totali})")

            if cancelled():
                print("   [*] Operazione annullata dall'utente.")
                return

            # Timing per ETA step-based: include taglio+generazione (esclude la sleep finale).
            chunk_step_t0 = time.monotonic()

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
                # Se il chunk era stato pre-tagliato in background (FFmpeg mentre Gemini lavorava),
                # riusalo per evitare attese inutili.
                skip_cut = False
                if next_cut is not None and int(next_cut.get("start", -1)) == int(inizio_sec) and int(next_cut.get("end", -1)) == int(fine_sec):
                    try:
                        next_cut.get("thread").join()
                    except Exception:
                        pass
                    try:
                        r = next_cut.get("result") or {}
                        if bool(r.get("ok")) and os.path.exists(nome_chunk) and os.path.getsize(nome_chunk) > 1024:
                            skip_cut = True
                        else:
                            debug_log(f"prefetch chunk failed; will cut sync: {r.get('err')}")
                    except Exception as e:
                        debug_log(f"prefetch join/check error: {e}")
                    next_cut = None

                if not skip_cut:
                    ok, err = _cut_chunk_to_path(int(inizio_sec), float(fine_sec), nome_chunk, bitrate=bitrate)
                    if not ok:
                        if str(err or "").strip().lower() == "cancelled" or cancelled():
                            print("   [*] Operazione annullata dall'utente.")
                            return
                        if err:
                            raise RuntimeError(f"FFmpeg ha fallito l'estrazione audio:\n{err}")
                        raise RuntimeError("FFmpeg ha fallito l'estrazione audio.")

                # 2. Preparazione input audio (preferisci inline bytes, fallback a upload se serve)
                audio_inline = _make_inline_audio_part(nome_chunk, max_bytes=inline_max_bytes)
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

                # Prefetch del prossimo chunk: mentre Gemini elabora questo blocco, FFmpeg prepara il successivo.
                try:
                    next_start = int(inizio_sec + passo_secondi)
                    if next_cut is None and prefetch_enabled and next_start < int(durata_totale_secondi):
                        next_end = min(float(next_start + blocco_secondi), float(durata_totale_secondi))
                        _start_prefetch(next_start, next_end, bitrate=bitrate)
                except Exception as e:
                    debug_log(f"prefetch schedule error: {e}")

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
                            model=model_name,
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
                        safe_register_step_time(
                            "chunks",
                            max(0.0, time.monotonic() - float(chunk_step_t0)),
                            done=blocco_corrente_idx,
                            total=blocchi_totali,
                        )
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
                                    test_c.models.get(model=model_name)
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
        print("[*] INIZIO FASE 2: Revisione e pulizia (macro-blocchi)")
        print("    - Cosa fa: divide il testo in macro-sezioni e le rivede per togliere doppioni e migliorare la leggibilita'.")
        print("    - Nota: questa fase usa l'AI su ogni macro-blocco per mantenere coerenza e dettaglio.")

        limite_caratteri = int(settings.macro_char_limit or 22000)

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

        # ETA step-based: totali fase 2 + confini (macro_total-1). Imposta anche il done attuale da sessione.
        safe_set_work_totals(macro_total=macro_total, boundary_total=max(0, macro_total - 1))
        try:
            safe_update_work_done(
                "macro",
                int(session.get("phase2", {}).get("revised_done", 0) or 0),
                total=macro_total,
            )
        except Exception:
            pass

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
                        safe_update_work_done("macro", revised_done, total=macro_total)
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
            blocco_local, removed_exact, removed_adj, near_adj, total_paras = local_macro_cleanup(blocco_src)
            blocco_for_ai = (blocco_local or blocco_src).strip()
            if removed_exact or removed_adj:
                print(f"   -> Pre-clean locale Macro-blocco {i}/{macro_total}: duplicati rimossi={removed_exact+removed_adj} (sospetti={near_adj}).")

            macro_step_t0 = time.monotonic()
            print(f"   -> Revisione Macro-blocco {i} di {macro_total}...")
            successo_revisione = False
            tent = 0
            while tent < 4:
                try:
                    risposta_rev = client.models.generate_content(
                        model=model_name,
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
                    safe_register_step_time(
                        "macro",
                        max(0.0, time.monotonic() - float(macro_step_t0)),
                        done=revised_done,
                        total=macro_total,
                    )
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
                                    test_c.models.get(model=model_name)
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
                safe_register_step_time(
                    "macro",
                    max(0.0, time.monotonic() - float(macro_step_t0)),
                    done=revised_done,
                    total=macro_total,
                )
            safe_progress(0.7 + 0.2 * (revised_done / max(1, macro_total)))
            if not sleep_with_cancel(5):
                print("   [*] Operazione annullata dall'utente.")
                return

        # ------------------------------------------
        # FASE 2B: REVISIONE DI CONFINE (AUTOSAVE)
        # ------------------------------------------
        if str(session.get("stage", "phase2")).strip().lower() == "phase2":
            session["stage"] = "boundary"
            print("\n======================================")
            print("[*] INIZIO FASE 3: Revisione dei confini (anti-doppioni tra macro-blocchi)")
            print("    - 'Confine' = fine del macro-blocco N + inizio del macro-blocco N+1.")
            print("    - Cosa fa: cerca sovrapposizioni tra i due pezzi e rimuove SOLO le ripetizioni.")
            print("    - Come: prima controllo locale (0 richieste), poi AI solo se il caso e' ambiguo.")
            safe_phase("Fase 3/3: confini (anti-doppioni)")
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

                # ETA step-based: totali e progresso attuale (utile in ripresa).
                safe_set_work_totals(boundary_total=pairs_total)
                safe_update_work_done("boundary", max(0, int(next_pair) - 1), total=pairs_total)

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

                    boundary_step_t0 = time.monotonic()
                    done_path = os.path.join(boundary_dir, f"boundary_{pair_idx:03}.done")
                    if os.path.exists(done_path):
                        session["boundary"]["next_pair"] = int(pair_idx + 1)
                        save_session()
                        safe_register_step_time("boundary", 0.0, done=pair_idx, total=pairs_total)
                        continue

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
                        safe_register_step_time(
                            "boundary",
                            max(0.0, time.monotonic() - float(boundary_step_t0)),
                            done=pair_idx,
                            total=pairs_total,
                        )
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
                        safe_register_step_time(
                            "boundary",
                            max(0.0, time.monotonic() - float(boundary_step_t0)),
                            done=pair_idx,
                            total=pairs_total,
                        )
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
                        safe_register_step_time(
                            "boundary",
                            max(0.0, time.monotonic() - float(boundary_step_t0)),
                            done=pair_idx,
                            total=pairs_total,
                        )
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
                                model=model_name,
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
                            safe_register_step_time(
                                "boundary",
                                max(0.0, time.monotonic() - float(boundary_step_t0)),
                                done=pair_idx,
                                total=pairs_total,
                            )
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
                                        test_c.models.get(model=model_name)
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
        final_md = normalize_inline_star_lists(final_md)
        html_doc = build_html_document(titolo, final_md)
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
