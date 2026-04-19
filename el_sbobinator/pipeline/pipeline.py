"""
Core pipeline for El Sbobinator (no UI widgets touched directly).

This module contains the heavy workflow:
- FFmpeg duration/probe, optional pre-conversion, chunk cutting
- Gemini generation (chunk), macro revision, boundary revision
- Autosave sessions and final HTML export
"""

from __future__ import annotations

import os
import threading
import time

from google import genai

from el_sbobinator.logging_utils import (
    attach_file_handler,
    detach_file_handler,
    get_logger,
)
from el_sbobinator.model_registry import build_model_state
from el_sbobinator.pipeline.pipeline_hooks import PipelineRuntime
from el_sbobinator.pipeline.pipeline_session import (
    ensure_preconverted_audio,
    initialize_session_context,
    list_phase1_chunks,
    normalize_stage,
    persist_phase1_metadata,
    phase1_has_progress,
    read_text_file,
    reset_for_regeneration,
    restore_phase1_progress,
)
from el_sbobinator.prompts import PROMPT_REVISIONE, PROMPT_SISTEMA
from el_sbobinator.services import generation_service
from el_sbobinator.services.audio_service import (
    probe_media_duration,
    resolve_ffmpeg,
)
from el_sbobinator.services.config_service import safe_output_basename
from el_sbobinator.services.export_service import export_final_html_document
from el_sbobinator.services.generation_service import (
    extract_client_api_key,
    load_fallback_keys,
)
from el_sbobinator.services.phase1_service import process_phase1_transcription
from el_sbobinator.services.revision_service import (
    build_macro_blocks,
    process_boundary_revision_phase,
    process_macro_revision_phase,
)
from el_sbobinator.session_store import _update_session
from el_sbobinator.shared import (
    _atomic_write_json,
    _load_json,
    invalidate_session_storage_cache,
)

# Maximum seconds to wait for a user response in the "regenerate?" dialog before
# falling back to "don't regenerate" so the pipeline is never blocked indefinitely.
_REGENERATE_DIALOG_TIMEOUT_SECONDS: int = 120


def _esegui_sbobinatura_impl(  # noqa: C901
    input_path, api_key_value, app_instance, session_dir_hint=None, resume_session=False
):
    runtime = PipelineRuntime(app_instance)
    runtime.reset_temp_files()
    cancel_event = runtime.cancel_event
    log_handler = None
    logger = get_logger("el_sbobinator.pipeline")
    start_time = time.monotonic()  # Track start time for duration calculation

    # ---- Fallback API keys rotation ----
    fallback_keys = load_fallback_keys()

    session = None
    session_ctx = None
    client = None
    try:
        if not api_key_value or api_key_value.strip() == "":
            runtime.set_run_result("failed", "api_key_mancante")
            print("Errore: Formato API Key non valido o assente.")
            logger.error("API key mancante o non valida.", extra={"stage": "startup"})
            return

        client = genai.Client(api_key=api_key_value.strip())
        runtime.set_run_result("failed")
        runtime.set_effective_api_key(api_key_value.strip())

        def request_fallback_key():
            return generation_service.request_new_api_key(runtime, runtime.cancelled)

        # ------------------------------
        # SESSIONE (AUTOSAVE / RIPRESA)
        # ------------------------------
        session_ctx = initialize_session_context(
            input_path,
            session_dir_hint=session_dir_hint,
            resume_session=resume_session,
        )
        session = session_ctx.session
        logger = get_logger(
            "el_sbobinator.pipeline",
            run_id=os.path.basename(session_ctx.session_dir),
            session_dir=session_ctx.session_dir,
            input_file=os.path.basename(input_path),
        )
        log_handler = attach_file_handler(
            os.path.join(session_ctx.session_dir, "run.log")
        )
        phase1_chunks_dir = session_ctx.phase1_chunks_dir
        phase2_revised_dir = session_ctx.phase2_revised_dir
        boundary_dir = session_ctx.boundary_dir
        macro_path = session_ctx.macro_path

        def save_session():
            return session_ctx.save()

        def on_model_switched(previous_model: str, new_model: str):
            assert session is not None
            session.setdefault("settings", {})
            session["settings"]["effective_model"] = new_model
            save_session()
            runtime.update_model(new_model)
            print(f"   [OK] Cambio modello automatico: {previous_model} -> {new_model}")

        def log_model_selection(label: str):
            def _fmt(m: str) -> str:
                t = generation_service._phase1_temperature(m)
                return f"{m} (T={t})"

            fallback_chain = (
                " -> ".join(_fmt(m) for m in settings.fallback_models)
                if settings.fallback_models
                else "nessuno"
            )
            print(
                f"[*] {label}: primario={_fmt(settings.model)}, attivo={_fmt(model_state.current)}, fallback={fallback_chain}"
            )

        print(f"[*] Autosalvataggio attivo. Sessione: {session_ctx.session_dir}")
        logger.info("Sessione inizializzata.", extra={"stage": "startup"})

        # Settings (con fallback per sessioni vecchie) + validazione (resiliente a valori strani).
        settings = session_ctx.settings

        model_name = settings.model
        # Always resume from the primary model. effective_model records which model
        # was active when the previous run stopped (observability only) but is a
        # transient runtime state, not a durable preference. The fallback mechanism
        # will degrade again if the primary is still unavailable.
        model_state = build_model_state(
            settings.model,
            settings.fallback_models,
        )
        runtime.update_model(model_state.current)
        chunk_seconds = settings.chunk_seconds
        step_seconds = settings.step_seconds
        prev_memory = ""
        full_transcript = ""

        system_prompt = PROMPT_SISTEMA
        log_model_selection("Modelli sessione")

        print(
            f"[*] Analisi del file originale in corso:\n{os.path.basename(input_path)}"
        )
        runtime.phase("Fase: analisi file")
        try:
            # Probe robusto della durata (gestisce path non-ASCII e "Duration: N/A").
            ffmpeg_exe = resolve_ffmpeg()
            total_duration_sec, reason = probe_media_duration(
                input_path, ffmpeg_exe=ffmpeg_exe
            )
            if total_duration_sec is None:
                raise ValueError(
                    str(
                        reason
                        or "Impossibile leggere la durata dal file usando FFmpeg."
                    )
                )
        except Exception as e:
            print(
                f"Errore caricamento audio. File corrotto o formato non supportato.\n{e}"
            )
            logger.exception("Analisi file fallita.", extra={"stage": "probe"})
            return

        print(f"[*] Durata totale rilevata: {int(total_duration_sec / 60)} minuti.")

        # Persisti metadati fase1 nella sessione
        persist_phase1_metadata(session_ctx, total_duration_sec, step_seconds)

        previous_stage = str(session.get("stage", "phase1")).strip().lower()
        stage = normalize_stage(session)
        if stage != previous_stage:
            save_session()

        existing_chunks = list_phase1_chunks(phase1_chunks_dir)
        has_progress = phase1_has_progress(session, stage, existing_chunks)

        if has_progress and resume_session:

            def ask_should_regenerate():
                if callable(getattr(app_instance, "ask_regenerate", None)):
                    event = threading.Event()
                    outcome = {"rigenera": False}

                    def on_answer(payload):
                        val = payload.get("regenerate", False)
                        if val is None and cancel_event is not None:
                            cancel_event.set()
                        outcome["rigenera"] = False if val is None else val
                        event.set()

                    regenerate_mode = "completed" if stage == "done" else "resume"
                    if runtime.ask_regenerate(
                        os.path.basename(input_path), on_answer, regenerate_mode
                    ):
                        deadline = time.monotonic() + _REGENERATE_DIALOG_TIMEOUT_SECONDS
                        while not event.is_set():
                            if runtime.cancelled():
                                return False
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                return False  # timeout fallback: don't regenerate
                            event.wait(min(0.2, remaining))
                        return outcome["rigenera"]

                ans = runtime.ask_confirmation(
                    "File gia' completato",
                    f"Il file '{os.path.basename(input_path)}' e' gia' completato.\n"
                    "Vuoi usare il salvataggio vecchio o ricominciare da zero perdendo tutti i progressi pregressi?\n\n"
                    "- Scegli 'OK'/'Si' per RIGENERARE da capo.\n"
                    "- Scegli 'Annulla'/'No' per usare la versione gia' pronta.",
                )
                if ans is not None:
                    return bool(ans)

                return False

            _is_regen = ask_should_regenerate()
            print(f"[*] Risposta Rigenerare dal JS: {_is_regen}")
            if _is_regen:
                print(
                    f"[*] L'utente ha scelto di rigenerare il file {os.path.basename(input_path)}. Pulizia sessione precedente..."
                )
                reset_for_regeneration(session_ctx)
                session = session_ctx.session
                settings = session_ctx.settings
                model_name = settings.model
                chunk_seconds = settings.chunk_seconds
                step_seconds = settings.step_seconds
                model_state = build_model_state(
                    settings.model,
                    settings.fallback_models,
                )
                stage = "phase1"
                log_model_selection("Modelli sessione dopo rigenerazione")
                logger.info(
                    "Sessione rigenerata su richiesta utente.",
                    extra={"stage": "resume"},
                )
            elif stage == "done":
                existing_html = (
                    session.get("outputs", {}).get("html", "")
                    if isinstance(session, dict)
                    else ""
                )
                if existing_html and os.path.exists(str(existing_html)):
                    print(
                        f"[*] File gia' completato, l'utente ha scelto di usare la versione pronta."
                    )
                    runtime.output_html(str(existing_html))
                    runtime.set_run_result("completed")
                    return

        # ------------------------------------------
        # PRE-CONVERSIONE UNICA (piu' veloce)
        # ------------------------------------------
        if runtime.cancelled():
            return
        _, preconv_used_path = ensure_preconverted_audio(
            session_ctx,
            input_path=input_path,
            stage=stage,
            ffmpeg_exe=ffmpeg_exe,
            cancel_event=cancel_event,
            cancelled=runtime.cancelled,
            phase_callback=runtime.phase,
        )
        if runtime.cancelled():
            return

        # Ripristino (se presente) dai chunk gia' salvati
        restored_phase1 = restore_phase1_progress(
            session_ctx, stage=stage, step_seconds=step_seconds
        )
        existing_chunks = restored_phase1.existing_chunks
        start_sec = restored_phase1.start_sec
        full_transcript = restored_phase1.full_transcript
        prev_memory = restored_phase1.prev_memory

        if stage == "phase1":
            print(
                f"[*] INIZIO FASE 1: Trascrizione a blocchi (circa {settings.chunk_minutes} min per blocco)"
            )
            print(
                "    - Cosa fa: taglia l'audio in blocchi e genera una sbobina dettagliata per ogni blocco."
            )
            print(
                "    - Perche': blocchi piu' piccoli aiutano a mantenere alto il dettaglio e ridurre errori."
            )
            runtime.phase("Fase 1/3: trascrizione (chunk)")
        else:
            print(f"[*] Ripresa sessione: stage='{stage}'. Salto Fase 1.")
            if stage == "phase2":
                runtime.phase("Fase 2/3: revisione")
            elif stage == "boundary":
                runtime.phase("Fase 3/3: confini (anti-doppioni)")
            elif stage == "done":
                runtime.phase("Fase: esportazione HTML")
            else:
                runtime.phase(f"Fase: ripresa ({stage})")
            start_sec = int(total_duration_sec)  # skip chunk loop

        if stage == "phase1":
            bitrate_default = str(settings.audio_bitrate or "48k")
            prefetch_enabled = bool(settings.prefetch_next_chunk)
            inline_max_bytes = settings.inline_max_bytes
            client, full_transcript, prev_memory = process_phase1_transcription(
                client=client,
                model_name=model_name,
                model_state=model_state,
                input_path=input_path,
                preconv_used_path=preconv_used_path,
                ffmpeg_exe=ffmpeg_exe,
                cancel_event=cancel_event,
                cancelled=runtime.cancelled,
                start_sec=start_sec,
                total_duration_sec=total_duration_sec,
                step_seconds=step_seconds,
                chunk_seconds=chunk_seconds,
                bitrate=bitrate_default,
                inline_max_bytes=inline_max_bytes,
                prefetch_enabled=prefetch_enabled,
                initial_full_transcript=full_transcript,
                initial_prev_memory=prev_memory,
                phase1_chunks_dir=phase1_chunks_dir,
                session=session,
                save_session=save_session,
                fallback_keys=fallback_keys,
                request_fallback_key=request_fallback_key,
                system_prompt=system_prompt,
                runtime=runtime,
                on_model_switched=on_model_switched,
                logger=logger,
            )
            if full_transcript is None:
                return

        # Se la fase 1 e' terminata senza interruzioni, passa alla fase 2
        if stage == "phase1":
            _update_session(session, {"stage": "phase2", "last_error": None})
            save_session()

        # ==========================================
        # FASE 2: REVISIONE LOGICA E CUCITURA DOPPIONI
        # ==========================================
        print("\n======================================")
        runtime.phase("Fase 2/3: revisione")
        print("[*] INIZIO FASE 2: Revisione e pulizia (macro-blocchi)")
        print(
            "    - Cosa fa: divide il testo in macro-sezioni e le rivede per togliere doppioni e migliorare la leggibilita'."
        )
        print(
            "    - Nota: questa fase usa l'AI su ogni macro-blocco per mantenere coerenza e dettaglio."
        )

        char_limit = int(settings.macro_char_limit or 22000)

        macro_blocks = None
        if os.path.exists(macro_path):
            try:
                macro_data = _load_json(macro_path)
                macro_blocks = list(macro_data.get("blocks") or [])
            except Exception:
                macro_blocks = None

        if not macro_blocks:
            macro_blocks = build_macro_blocks(full_transcript, char_limit)

            try:
                _atomic_write_json(
                    macro_path, {"limit_chars": char_limit, "blocks": macro_blocks}
                )
            except Exception:
                pass

        print(
            f"Il documento è stato diviso in {len(macro_blocks)} macro-sezioni per mantenere il livello di dettaglio. Revisione in corso..."
        )
        _update_session(
            session,
            {
                "phase2": {
                    **session.get("phase2", {}),
                    "macro_total": len(macro_blocks),
                },
            },
        )
        save_session()

        revised_text = ""
        if macro_blocks:
            client, revised_text = process_macro_revision_phase(
                client=client,
                model_name=model_name,
                model_state=model_state,
                macro_blocks=macro_blocks,
                phase2_revised_dir=phase2_revised_dir,
                session=session,
                save_session=save_session,
                runtime=runtime,
                cancelled=runtime.cancelled,
                fallback_keys=fallback_keys,
                request_fallback_key=request_fallback_key,
                prompt_revisione=PROMPT_REVISIONE,
                on_model_switched=on_model_switched,
                logger=logger,
            )
            if (
                runtime.cancelled()
                or session.get("last_error") == "quota_daily_limit_phase2"
            ):
                return

        macro_total = len(macro_blocks)

        # ETA step-based: totali fase 2 + confini (macro_total-1). Imposta anche il done attuale da sessione.
        runtime.set_work_totals(
            macro_total=macro_total, boundary_total=max(0, macro_total - 1)
        )
        try:
            runtime.update_work_done(
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
            print("\n======================================")
            print(
                "[*] INIZIO FASE 3: Revisione dei confini (anti-doppioni tra macro-blocchi)"
            )
            print(
                "    - 'Confine' = fine del macro-blocco N + inizio del macro-blocco N+1."
            )
            print(
                "    - Cosa fa: cerca sovrapposizioni tra i due pezzi e rimuove SOLO le ripetizioni."
            )
            print(
                "    - Come: prima controllo locale (0 richieste), poi AI solo se il caso e' ambiguo."
            )
            runtime.phase("Fase 3/3: confini (anti-doppioni)")
            _next_pair = int(session.get("boundary", {}).get("next_pair", 1) or 1)
            _update_session(
                session,
                {
                    "stage": "boundary",
                    "boundary": {
                        **session.get("boundary", {}),
                        "pairs_total": int(max(0, macro_total - 1)),
                        "next_pair": _next_pair,
                    },
                    "last_error": None,
                },
            )
            save_session()

        current_stage = str(session.get("stage", "phase1")).strip().lower()
        if current_stage == "boundary":
            client = process_boundary_revision_phase(
                client=client,
                model_name=model_name,
                model_state=model_state,
                boundary_dir=boundary_dir,
                phase2_revised_dir=phase2_revised_dir,
                session=session,
                save_session=save_session,
                runtime=runtime,
                cancelled=runtime.cancelled,
                fallback_keys=fallback_keys,
                request_fallback_key=request_fallback_key,
                on_model_switched=on_model_switched,
                logger=logger,
            )
            if runtime.cancelled() or session.get("last_error") in (
                "quota_daily_limit_boundary",
                "boundary_ai_failed",
            ):
                return
            _update_session(session, {"stage": "done", "last_error": None})
            save_session()

        # ==========================================
        # 3. SALVATAGGIO FINALE (MARKDOWN + HTML)
        # ==========================================
        runtime.phase("Fase: esportazione HTML")
        session_html_dir = session_ctx.session_dir

        try:
            title, html_path = export_final_html_document(
                input_path=input_path,
                phase2_revised_dir=phase2_revised_dir,
                fallback_body=revised_text,
                read_text=read_text_file,
                output_dir=session_html_dir,
                fallback_output_dir=session_html_dir,
                safe_output_basename=safe_output_basename,
            )
        except Exception as e:
            print(f"[!] Errore salvataggio HTML: {e}")
            session["last_error"] = "html_export_failed"
            save_session()
            return

        if not os.path.exists(html_path):
            print(
                "[!] Errore salvataggio HTML: file finale non trovato dopo la scrittura."
            )
            session["last_error"] = "html_export_missing"
            save_session()
            return

        try:
            _update_session(
                session,
                {
                    "outputs": {**session.get("outputs", {}), "html": html_path},
                },
            )
            save_session()
        except Exception:
            pass

        try:
            runtime.output_html(html_path)
        except Exception:
            pass

        elapsed = time.monotonic() - start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        print(f"\n======================================")
        print("SBOBINATURA COMPLETATA CON SUCCESSO!")
        print(f"Tempo totale: {minutes}m {seconds}s")
        print(f"File salvato in: {session_html_dir}")
        runtime.phase("Fase: completato")
        runtime.set_run_result("completed")
        logger.info("Pipeline completata con successo.", extra={"stage": "done"})

        # Pulizia: rimuovi il file preconvertito (grande) se presente. I progressi testuali restano nella sessione.
        try:
            if preconv_used_path and os.path.exists(preconv_used_path):
                os.remove(preconv_used_path)
                invalidate_session_storage_cache()
        except Exception:
            pass

    except Exception as e:
        runtime.set_run_result("failed", str(e))
        logger.exception("Errore imprevisto nella pipeline.", extra={"stage": "fatal"})
        print(f"\n[X] ERRORE IMPREVISTO DURANTE L'ESECUZIONE:\n{e}")
    finally:
        runtime.set_effective_api_key(
            extract_client_api_key(locals().get("client"))
            or getattr(app_instance, "effective_api_key", None)
        )
        runtime.cleanup_temp_files()
        if (
            runtime.cancelled()
            or getattr(app_instance, "last_run_status", None) == "cancelled"
        ):
            runtime.phase("Fase: annullato")
            runtime.set_run_result(
                "cancelled",
                getattr(app_instance, "last_run_error", None) or "cancelled",
            )
        else:
            runtime.progress(1.0)
            if getattr(app_instance, "last_run_status", None) != "completed":
                runtime.set_run_result(
                    "failed",
                    getattr(app_instance, "last_run_error", None)
                    or (
                        session.get("last_error") if isinstance(session, dict) else None
                    )
                    or "processing_failed",
                )
        detach_file_handler(log_handler)
        runtime.process_done()


def esegui_sbobinatura(
    input_path, api_key_value, app_instance, session_dir_hint=None, resume_session=False
):
    # Wrapper stabile: mantiene la firma pubblica mentre l'implementazione evolve.
    return _esegui_sbobinatura_impl(
        input_path,
        api_key_value,
        app_instance,
        session_dir_hint=session_dir_hint,
        resume_session=resume_session,
    )
