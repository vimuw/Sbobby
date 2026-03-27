"""
Core pipeline for El Sbobinator (no UI widgets touched directly).

This module contains the heavy workflow:
- FFmpeg duration/probe, optional pre-conversion, chunk cutting
- Gemini generation (chunk), macro revision, boundary revision
- Autosave sessions and final HTML export
"""

from __future__ import annotations

import os
import platform
import tempfile
import threading
import time
from google import genai
from google.genai import types

from el_sbobinator import generation_service
from el_sbobinator.audio_service import (
    cut_audio_chunk_to_mp3,
    probe_media_duration,
    resolve_ffmpeg,
)
from el_sbobinator.dedup_utils import local_macro_cleanup
from el_sbobinator.export_service import export_final_html_document
from el_sbobinator.generation_service import (
    build_chunk_prompt,
    extract_client_api_key,
    extract_response_text,
    load_fallback_keys,
)
from el_sbobinator.logging_utils import attach_file_handler, detach_file_handler, get_logger
from el_sbobinator.pipeline_hooks import PipelineRuntime
from el_sbobinator.pipeline_session import (
    ensure_preconverted_audio,
    initialize_session_context,
    list_phase1_chunks,
    normalize_stage,
    persist_phase1_metadata,
    phase1_has_progress,
    read_text_file,
    record_step_metric,
    reset_for_regeneration,
    restore_phase1_progress,
)
from el_sbobinator.revision_service import (
    build_macro_blocks,
    process_boundary_revision_phase,
    process_macro_revision_phase,
)
from el_sbobinator.shared import (
    PROMPT_REVISIONE,
    PROMPT_SISTEMA,
    USER_HOME,
    _atomic_write_json,
    _atomic_write_text,
    _load_json,
    debug_log,
    get_desktop_dir,
    safe_output_basename,
)


def _esegui_sbobinatura_legacy(nome_file_video, api_key_value, app_instance, session_dir_hint=None, resume_session=False):
    runtime = PipelineRuntime(app_instance)
    runtime.reset_temp_files()
    cancel_event = runtime.cancel_event
    log_handler = None
    logger = get_logger("el_sbobinator.pipeline")

    def cancelled():
        return runtime.cancelled()

    def _is_empty_model_response_error(err_txt: str) -> bool:
        try:
            low = str(err_txt or "").lower()
        except Exception:
            return False
        return (
            "risposta vuota dal modello" in low
            or "text=none" in low
            or ("nonetype" in low and "has no attribute" in low and "strip" in low)
        )

    def ui_alive():
        return runtime.ui_alive()

    def safe_after(delay_ms, callback, *args):
        return runtime.schedule(delay_ms, callback, *args)

    def safe_progress(value):
        runtime.progress(value)

    def safe_phase(text):
        runtime.phase(text)

    def safe_output_html(path):
        runtime.output_html(path)

    def safe_process_done():
        runtime.process_done()

    # ---- ETA step-based (thread-safe hooks) ----
    def safe_set_work_totals(chunks_total=None, macro_total=None, boundary_total=None):
        runtime.set_work_totals(
            chunks_total=chunks_total,
            macro_total=macro_total,
            boundary_total=boundary_total,
        )

    def safe_update_work_done(kind: str, done: int, total: int = None):
        runtime.update_work_done(kind, done, total=total)

    def safe_register_step_time(kind: str, seconds: float, done: int = None, total: int = None):
        runtime.register_step_time(kind, seconds, done=done, total=total)
        record_step_metric(session, kind, seconds, done=done, total=total)

    def safe_set_run_result(status: str, error: str | None = None):
        runtime.set_run_result(status, error)

    def safe_set_effective_api_key(api_key: str | None):
        runtime.set_effective_api_key(api_key)

    # ---- Fallback API keys rotation ----
    fallback_keys = load_fallback_keys()

    session = None
    session_ctx = None
    client = None
    try:
        if not api_key_value or api_key_value.strip() == "":
            safe_set_run_result("failed", "api_key_mancante")
            print("Errore: Formato API Key non valido o assente.")
            logger.error("API key mancante o non valida.", extra={"stage": "startup"})
            return

        client = genai.Client(api_key=api_key_value.strip())
        safe_set_run_result("failed")
        safe_set_effective_api_key(api_key_value.strip())
        
        def richiedi_chiave_riserva():
            return generation_service.request_new_api_key(runtime, cancelled)

        # ------------------------------
        # SESSIONE (AUTOSAVE / RIPRESA)
        # ------------------------------
        session_ctx = initialize_session_context(
            nome_file_video,
            session_dir_hint=session_dir_hint,
            resume_session=resume_session,
        )
        session = session_ctx.session
        logger = get_logger(
            "el_sbobinator.pipeline",
            run_id=os.path.basename(session_ctx.session_dir),
            session_dir=session_ctx.session_dir,
            input_file=os.path.basename(nome_file_video),
        )
        log_handler = attach_file_handler(os.path.join(session_ctx.session_dir, "run.log"))
        phase1_chunks_dir = session_ctx.phase1_chunks_dir
        phase2_revised_dir = session_ctx.phase2_revised_dir
        boundary_dir = session_ctx.boundary_dir
        macro_path = session_ctx.macro_path

        def save_session():
            return session_ctx.save()

        print(f"[*] Autosalvataggio attivo. Sessione: {session_ctx.session_dir}")
        logger.info("Sessione inizializzata.", extra={"stage": "startup"})

        # Settings (con fallback per sessioni vecchie) + validazione (resiliente a valori strani).
        settings = session_ctx.settings

        model_name = settings.model
        blocco_secondi = settings.chunk_seconds
        passo_secondi = settings.step_seconds
        memoria_precedente = ""
        testo_completo_sbobina = ""

        istruzioni_sistema = PROMPT_SISTEMA
 
        print(f"[*] Analisi del file originale in corso:\n{os.path.basename(nome_file_video)}")
        safe_phase("Fase: analisi file")
        try:
            # Probe robusto della durata (gestisce path non-ASCII e "Duration: N/A").
            ffmpeg_exe = resolve_ffmpeg()
            durata_totale_secondi, reason = probe_media_duration(nome_file_video, ffmpeg_exe=ffmpeg_exe)
            if durata_totale_secondi is None:
                raise ValueError(str(reason or "Impossibile leggere la durata dal file usando FFmpeg."))
        except Exception as e:
            print(f"Errore caricamento audio. File corrotto o formato non supportato.\n{e}")
            logger.exception("Analisi file fallita.", extra={"stage": "probe"})
            return

        print(f"[*] Durata totale rilevata: {int(durata_totale_secondi / 60)} minuti.")

        # Persisti metadati fase1 nella sessione
        persist_phase1_metadata(session_ctx, durata_totale_secondi, passo_secondi)

        previous_stage = str(session.get("stage", "phase1")).strip().lower()
        stage = normalize_stage(session)
        if stage != previous_stage:
            save_session()

        existing_chunks = list_phase1_chunks(phase1_chunks_dir)
        has_progress = phase1_has_progress(session, stage, existing_chunks)

        if has_progress and resume_session:
            def chiedi_se_rigenerare():
                if callable(getattr(app_instance, "ask_regenerate", None)):
                    evento = threading.Event()
                    esito = {"rigenera": False}
                    def on_answer(payload):
                        esito["rigenera"] = payload.get("regenerate", False)
                        evento.set()
                    
                    regenerate_mode = "completed" if stage == "done" else "resume"
                    if runtime.ask_regenerate(os.path.basename(nome_file_video), on_answer, regenerate_mode):
                        evento.wait()
                        return esito["rigenera"]

                ans = runtime.ask_confirmation(
                    "File gia' completato",
                    f"Il file '{os.path.basename(nome_file_video)}' e' gia' completato.\n"
                    "Vuoi usare il salvataggio vecchio o ricominciare da zero perdendo tutti i progressi pregressi?\n\n"
                    "- Scegli 'OK'/'Si' per RIGENERARE da capo.\n"
                    "- Scegli 'Annulla'/'No' per usare la versione gia' pronta.",
                )
                if ans is not None:
                    return bool(ans)

                return False

            _is_regen = chiedi_se_rigenerare()
            print(f"[*] Risposta Rigenerare dal JS: {_is_regen}")
            if _is_regen:
                print(f"[*] L'utente ha scelto di rigenerare il file {os.path.basename(nome_file_video)}. Pulizia sessione precedente...")
                reset_for_regeneration(session_ctx)
                session = session_ctx.session
                stage = "phase1"
                logger.info("Sessione rigenerata su richiesta utente.", extra={"stage": "resume"})
            elif stage == "done":
                existing_html = session.get("outputs", {}).get("html", "") if isinstance(session, dict) else ""
                if existing_html and os.path.exists(str(existing_html)):
                    print(f"[*] File gia' completato, l'utente ha scelto di usare la versione pronta.")
                    safe_output_html(str(existing_html))
                    safe_set_run_result("completed")
                    return

        # ------------------------------------------
        # PRE-CONVERSIONE UNICA (piu' veloce)
        # ------------------------------------------
        _, preconv_used_path = ensure_preconverted_audio(
            session_ctx,
            input_path=nome_file_video,
            stage=stage,
            ffmpeg_exe=ffmpeg_exe,
            cancel_event=cancel_event,
            cancelled=cancelled,
            phase_callback=safe_phase,
        )
        if cancelled():
            return

        # Ripristino (se presente) dai chunk gia' salvati
        restored_phase1 = restore_phase1_progress(session_ctx, stage=stage, step_seconds=passo_secondi)
        existing_chunks = restored_phase1.existing_chunks
        start_sec = restored_phase1.start_sec
        testo_completo_sbobina = restored_phase1.testo_completo_sbobina
        memoria_precedente = restored_phase1.memoria_precedente

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
                ok, err = cut_audio_chunk_to_mp3(
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

            return cut_audio_chunk_to_mp3(
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
                path_next = os.path.join(tempfile.gettempdir(), f"el_sbobinator_temp_{int(next_start_s)}_{int(next_end_s)}.mp3")
            except Exception:
                return
            runtime.track_temp_file(path_next)
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
            nome_chunk = os.path.join(tempfile.gettempdir(), f"el_sbobinator_temp_{inizio_sec}_{int(fine_sec)}.mp3")
            runtime.track_temp_file(nome_chunk)

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
                audio_inline = generation_service.make_inline_audio_part(nome_chunk, max_bytes=inline_max_bytes)
                audio_mode = "inline" if audio_inline is not None else "upload"
                tried_upload_fallback = False
                if audio_mode == "inline":
                    print("   -> (2/3) Preparazione audio (inline)...")

                # 3. Generazione testuale
                print("   -> (3/3) Generazione sbobina in corso...")
                prompt_dinamico = build_chunk_prompt(memoria_precedente)

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
                    audio_file = generation_service.upload_audio_path(client, nome_chunk)
                    file_client = client  # il file e' legato alla chiave che l'ha caricato
                    audio_file = generation_service.wait_for_file_ready(client, audio_file, cancelled)
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
                        testo_generato = extract_response_text(risposta)
                        # Alcune risposte possono avere `text=None` (es. output bloccato/struttura diversa).
                        if not testo_generato:
                            raise RuntimeError("Risposta vuota dal modello (text=None)")
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
                                if not generation_service.sleep_with_cancel(cancelled, 65):
                                    print("   [*] Operazione annullata dall'utente.")
                                    return
                                tent += 1
                                continue

                            # Daily limit: prova cambio chiave automatico
                            print("\n" + "="*50)
                            print("⛔ LIMITE GIORNALIERO RAGGIUNTO!")
                            new_c, rotated, rotated_key = generation_service.try_rotate_key(
                                client,
                                fallback_keys,
                                model_name,
                                logger=logger,
                            )
                            if rotated:
                                client = new_c
                                safe_set_effective_api_key(rotated_key)
                                if audio_mode == "upload":
                                    if audio_file is not None and file_client is not None:
                                        try:
                                            file_client.files.delete(name=audio_file.name)
                                        except Exception:
                                            pass
                                    audio_file = None
                                    file_client = None
                                    print("   Ricarico questo blocco con la nuova chiave...")
                                else:
                                    print("   Ripresa automatica (inline audio).")
                                tent = 0
                                continue

                            # Nessuna chiave automatica: popup manuale.
                            nuova_api = richiedi_chiave_riserva()
                            if nuova_api and nuova_api.strip():
                                try:
                                    test_c = genai.Client(api_key=nuova_api.strip())
                                    test_c.models.get(model=model_name)
                                except Exception as err:
                                    print(f"   [!] Chiave non valida fornita: {err}")
                                else:
                                    client = test_c
                                    safe_set_effective_api_key(nuova_api.strip())
                                    if audio_mode == "upload":
                                        if audio_file is not None and file_client is not None:
                                            try:
                                                file_client.files.delete(name=audio_file.name)
                                            except Exception:
                                                pass
                                        audio_file = None
                                        file_client = None
                                        print("   ✅ Nuova API Key valida! Ricarico questo blocco con la nuova chiave...")
                                    else:
                                        print("   ✅ Nuova API Key valida! Ripresa automatica (inline audio).")
                                    tent = 0
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

                        if _is_empty_model_response_error(err_txt):
                            debug_log(f"empty model response: {err_txt}")
                            print("      [Risposta vuota/filtrata dal modello. Riprovo in 30 secondi...]")
                        else:
                            print(f"      [Server occupati o errore: {err_txt}]")
                            print("      [Riprovo in 30 secondi...]")
                        if not generation_service.sleep_with_cancel(cancelled, 30):
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
            if not generation_service.sleep_with_cancel(cancelled, 5):
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
            macro_blocchi = build_macro_blocks(testo_completo_sbobina, limite_caratteri)

            try:
                _atomic_write_json(macro_path, {"limit_chars": limite_caratteri, "blocks": macro_blocchi})
            except Exception:
                pass
            
        print(f"Il documento è stato diviso in {len(macro_blocchi)} macro-sezioni per mantenere il livello di dettaglio. Revisione in corso...")
        session.setdefault("phase2", {})
        session["phase2"]["macro_total"] = int(len(macro_blocchi))
        save_session()

        testo_finale_revisionato = ""
        if macro_blocchi:
            client, testo_finale_revisionato = process_macro_revision_phase(
                client=client,
                model_name=model_name,
                macro_blocks=macro_blocchi,
                phase2_revised_dir=phase2_revised_dir,
                session=session,
                save_session=save_session,
                safe_phase=safe_phase,
                safe_progress=safe_progress,
                safe_set_work_totals=safe_set_work_totals,
                safe_update_work_done=safe_update_work_done,
                safe_register_step_time=safe_register_step_time,
                safe_set_effective_api_key=safe_set_effective_api_key,
                cancelled=cancelled,
                fallback_keys=fallback_keys,
                richiedi_chiave_riserva=richiedi_chiave_riserva,
                is_empty_model_response_error=_is_empty_model_response_error,
                prompt_revisione=PROMPT_REVISIONE,
                logger=logger,
            )
            if cancelled() or session.get("last_error") == "quota_daily_limit_phase2":
                return

        macro_total = len(macro_blocchi)

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
            client = process_boundary_revision_phase(
                client=client,
                model_name=model_name,
                boundary_dir=boundary_dir,
                phase2_revised_dir=phase2_revised_dir,
                session=session,
                save_session=save_session,
                safe_phase=safe_phase,
                safe_progress=safe_progress,
                safe_set_work_totals=safe_set_work_totals,
                safe_update_work_done=safe_update_work_done,
                safe_register_step_time=safe_register_step_time,
                safe_set_effective_api_key=safe_set_effective_api_key,
                cancelled=cancelled,
                fallback_keys=fallback_keys,
                richiedi_chiave_riserva=richiedi_chiave_riserva,
                logger=logger,
            )
            if cancelled() or session.get("last_error") == "quota_daily_limit_boundary":
                return
            session["stage"] = "done"
            session["last_error"] = None
            save_session()


        # ==========================================
        # 3. SALVATAGGIO FINALE (MARKDOWN + HTML)
        # ==========================================
        safe_phase("Fase: esportazione HTML")
        cartella_origine = get_desktop_dir()
        try:
            os.makedirs(cartella_origine, exist_ok=True)
        except Exception:
            cartella_origine = USER_HOME

        try:
            titolo, nome_file_html = export_final_html_document(
                input_path=nome_file_video,
                phase2_revised_dir=phase2_revised_dir,
                fallback_body=testo_finale_revisionato,
                read_text=read_text_file,
                output_dir=cartella_origine,
                fallback_output_dir=cartella_origine,
                safe_output_basename=safe_output_basename,
            )
        except Exception as e:
            print(f"[!] Errore salvataggio HTML: {e}")
            session["last_error"] = "html_export_failed"
            save_session()
            return

        try:
            if os.path.exists(nome_file_html):
                safe_output_html(nome_file_html)
        except Exception:
            pass

        if not os.path.exists(nome_file_html):
            print("[!] Errore salvataggio HTML: file finale non trovato dopo la scrittura.")
            session["last_error"] = "html_export_missing"
            save_session()
            return

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
        safe_set_run_result("completed")
        logger.info("Pipeline completata con successo.", extra={"stage": "done"})

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
        safe_set_run_result("failed", str(e))
        logger.exception("Errore imprevisto nella pipeline.", extra={"stage": "fatal"})
        print(f"\n[X] ERRORE IMPREVISTO DURANTE L'ESECUZIONE:\n{e}")
    finally:
        safe_set_effective_api_key(extract_client_api_key(locals().get("client")) or getattr(app_instance, "effective_api_key", None))
        runtime.cleanup_temp_files()
        if cancelled():
            safe_phase("Fase: annullato")
            safe_set_run_result("cancelled", getattr(app_instance, "last_run_error", None) or "cancelled")
        else:
            safe_progress(1.0)
            if getattr(app_instance, "last_run_status", None) != "completed":
                safe_set_run_result(
                    "failed",
                    getattr(app_instance, "last_run_error", None)
                    or (session.get("last_error") if isinstance(session, dict) else None)
                    or "processing_failed",
                )
        detach_file_handler(log_handler)
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
