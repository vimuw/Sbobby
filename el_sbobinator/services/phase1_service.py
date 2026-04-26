"""
Phase 1 (chunked transcription) extracted from the main pipeline.

Mirrors the structure of revision_service.py: a single public function
process_phase1_transcription() that contains all chunk-loop logic.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from collections.abc import Callable

from google.genai import types

from el_sbobinator.core.model_registry import ModelState
from el_sbobinator.core.session_store import _update_session
from el_sbobinator.core.shared import _atomic_write_text
from el_sbobinator.pipeline.pipeline_session import record_step_metric
from el_sbobinator.services import generation_service
from el_sbobinator.services.audio_service import cut_audio_chunk_to_mp3
from el_sbobinator.services.config_service import debug_log
from el_sbobinator.services.generation_service import (
    AllModelsUnavailableError,
    DegenerateOutputError,
    PermanentError,
    QuotaDailyLimitError,
    current_model_name,
    detect_degenerate_output,
    extract_response_text,
    retry_with_quota,
    sleep_with_cancel,
)
from el_sbobinator.utils.logging_utils import get_logger


def process_phase1_transcription(  # noqa: C901
    *,
    client,
    model_name: str,
    model_state: ModelState | None = None,
    input_path: str,
    preconv_used_path: str | None,
    ffmpeg_exe: str,
    cancel_event,
    cancelled: Callable[[], bool],
    start_sec: int,
    total_duration_sec: float,
    step_seconds: int,
    chunk_seconds: int,
    bitrate: str,
    inline_max_bytes,
    prefetch_enabled: bool,
    initial_full_transcript: str = "",
    initial_prev_memory: str = "",
    phase1_chunks_dir: str,
    session: dict,
    save_session: Callable[[], bool],
    fallback_keys: list,
    request_fallback_key: Callable[[], str | None],
    system_prompt: str,
    runtime,
    on_model_switched=None,
    logger=None,
) -> tuple[object, str | None, str]:
    """Run the Phase 1 chunk transcription loop.

    Returns (client, full_transcript, prev_memory) on success.
    Returns (client, None, prev_memory) when the pipeline should abort
    (quota exhausted, permanent error, cancelled, or unrecoverable chunk failure).
    The session's last_error is set before returning None for error cases.
    """
    log = logger or get_logger("el_sbobinator.phase1")

    full_transcript = initial_full_transcript
    prev_memory = initial_prev_memory

    dur_int = int(total_duration_sec)
    total_chunks = 0 if dur_int <= 0 else (dur_int + step_seconds - 1) // step_seconds
    start_int = int(start_sec)
    chunk_idx = 0 if start_int <= 0 else (start_int + step_seconds - 1) // step_seconds

    runtime.set_work_totals(chunks_total=total_chunks)
    runtime.update_work_done("chunks", chunk_idx, total=total_chunks)

    next_cut = None  # {"start": int, "end": int, "path": str, "thread": Thread, "result": dict}

    def _cut_chunk_to_path(start_s: int, end_s: float, out_path: str, brate: str):
        duration = float(end_s) - float(start_s)
        if duration <= 0:
            return False, "durata_chunk_non_valida"
        if preconv_used_path and os.path.exists(preconv_used_path):
            ok, err = cut_audio_chunk_to_mp3(
                input_path=preconv_used_path,
                output_path=out_path,
                start_sec=start_s,
                duration_sec=duration,
                ffmpeg_exe=ffmpeg_exe,
                stream_copy=True,
                bitrate=brate,
                stop_event=cancel_event,
            )
            if ok:
                return True, None
            debug_log(f"cut(stream_copy) failed; fallback reencode: {err}")
        return cut_audio_chunk_to_mp3(
            input_path=input_path,
            output_path=out_path,
            start_sec=start_s,
            duration_sec=duration,
            ffmpeg_exe=ffmpeg_exe,
            stream_copy=False,
            bitrate=brate,
            stop_event=cancel_event,
        )

    def _start_prefetch(next_start_s: int, next_end_s: float, brate: str):
        nonlocal next_cut
        if not prefetch_enabled:
            return
        if next_start_s is None or next_end_s is None:
            return
        if next_cut is not None:
            return
        try:
            path_next = os.path.join(
                tempfile.gettempdir(),
                f"el_sbobinator_temp_{int(next_start_s)}_{int(next_end_s)}.mp3",
            )
        except Exception:
            return
        runtime.track_temp_file(path_next)
        result = {"ok": False, "err": None}

        def worker():
            ok, err = _cut_chunk_to_path(
                int(next_start_s), float(next_end_s), path_next, brate=brate
            )
            result["ok"] = bool(ok)
            result["err"] = err

        t = threading.Thread(target=worker, daemon=True)
        next_cut = {
            "start": int(next_start_s),
            "end": int(next_end_s),
            "path": path_next,
            "thread": t,
            "result": result,
        }
        t.start()

    for chunk_start_sec in range(int(start_sec), int(total_duration_sec), step_seconds):
        chunk_idx += 1
        chunk_end_sec = min(chunk_start_sec + chunk_seconds, total_duration_sec)

        print(f"\n======================================")
        print(
            f"-> LAVORAZIONE BLOCCO AUDIO {chunk_idx} DI {total_chunks} (Da {chunk_start_sec}s a {int(chunk_end_sec)}s)"
        )
        runtime.phase(f"Fase 1/3: trascrizione (chunk {chunk_idx}/{total_chunks})")

        if cancelled():
            print("   [*] Operazione annullata dall'utente.")
            return client, None, prev_memory

        chain_exhaustion_recovery_used = False

        while True:
            chunk_step_t0 = time.monotonic()
            chunk_path = os.path.join(
                tempfile.gettempdir(),
                f"el_sbobinator_temp_{chunk_start_sec}_{int(chunk_end_sec)}.mp3",
            )
            runtime.track_temp_file(chunk_path)

            audio_file = None
            file_client = None
            success = False

            try:
                # 1. Taglio
                print("   -> (1/3) Estrazione e taglio in corso...")
                skip_cut = False
                if (
                    next_cut is not None
                    and int(next_cut.get("start", -1)) == int(chunk_start_sec)
                    and int(next_cut.get("end", -1)) == int(chunk_end_sec)
                ):
                    try:
                        next_cut.get("thread").join()
                    except Exception:
                        pass
                    try:
                        r = next_cut.get("result") or {}
                        if (
                            bool(r.get("ok"))
                            and os.path.exists(chunk_path)
                            and os.path.getsize(chunk_path) > 1024
                        ):
                            skip_cut = True
                        else:
                            debug_log(
                                f"prefetch chunk failed; will cut sync: {r.get('err')}"
                            )
                    except Exception as e:
                        debug_log(f"prefetch join/check error: {e}")
                    next_cut = None

                if not skip_cut:
                    ok, err = _cut_chunk_to_path(
                        int(chunk_start_sec),
                        float(chunk_end_sec),
                        chunk_path,
                        brate=bitrate,
                    )
                    if not ok:
                        if str(err or "").strip().lower() == "cancelled" or cancelled():
                            print("   [*] Operazione annullata dall'utente.")
                            return client, None, prev_memory
                        if err:
                            raise RuntimeError(
                                f"FFmpeg ha fallito l'estrazione audio:\n{err}"
                            )
                        raise RuntimeError("FFmpeg ha fallito l'estrazione audio.")

                # 2. Preparazione input audio
                audio_inline = generation_service.make_inline_audio_part(
                    chunk_path, max_bytes=inline_max_bytes
                )
                audio_mode = "inline" if audio_inline is not None else "upload"
                tried_upload_fallback = False
                if audio_mode == "inline":
                    print("   -> (2/3) Preparazione audio (inline)...")

                # 3. Generazione testuale
                print("   -> (3/3) Generazione sbobina in corso...")
                chunk_prompt = generation_service.build_chunk_prompt(prev_memory)

                def _ensure_uploaded_audio_input(current_client):
                    nonlocal audio_file, file_client
                    if audio_file is not None:
                        try:
                            if getattr(audio_file, "uri", None):
                                return types.Part.from_uri(
                                    file_uri=audio_file.uri,
                                    mime_type=(
                                        getattr(audio_file, "mime_type", None)
                                        or "audio/mpeg"
                                    ),
                                )
                        except Exception:
                            return audio_file
                        return audio_file
                    print("   -> (2/3) Caricamento sicuro nei server di google...")
                    audio_file = generation_service.upload_audio_path(
                        current_client,
                        chunk_path,  # noqa: B023
                    )
                    file_client = current_client
                    audio_file = generation_service.wait_for_file_ready(
                        current_client, audio_file, cancelled
                    )
                    if audio_file is None:
                        print("   [*] Operazione annullata dall'utente.")
                        return None
                    try:
                        if getattr(audio_file, "uri", None):
                            return types.Part.from_uri(
                                file_uri=audio_file.uri,
                                mime_type=(
                                    getattr(audio_file, "mime_type", None)
                                    or "audio/mpeg"
                                ),
                            )
                    except Exception:
                        pass
                    return audio_file

                def _on_key_rotated(_new_client):
                    nonlocal audio_file, file_client
                    if audio_mode == "upload":  # noqa: B023
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

                # Prefetch del prossimo chunk
                try:
                    next_start = int(chunk_start_sec + step_seconds)
                    if (
                        next_cut is None
                        and prefetch_enabled
                        and next_start < int(total_duration_sec)
                    ):
                        next_end = min(
                            float(next_start + chunk_seconds), float(total_duration_sec)
                        )
                        _start_prefetch(next_start, next_end, brate=bitrate)
                except Exception as e:
                    debug_log(f"prefetch schedule error: {e}")

                def _call(current_client):
                    nonlocal audio_mode, tried_upload_fallback
                    while True:
                        try:
                            if audio_mode == "inline" and audio_inline is not None:  # noqa: B023
                                audio_input = audio_inline  # noqa: B023
                            else:
                                audio_input = _ensure_uploaded_audio_input(
                                    current_client
                                )
                                if audio_input is None:
                                    return None  # cancelled during upload wait
                            _active_model = current_model_name(model_state, model_name)
                            response = current_client.models.generate_content(
                                model=_active_model,
                                contents=[chunk_prompt, audio_input],  # noqa: B023
                                config=types.GenerateContentConfig(
                                    system_instruction=system_prompt,
                                    temperature=generation_service._phase1_temperature(
                                        _active_model
                                    ),
                                ),
                            )
                            generated_text = extract_response_text(response)
                            if not generated_text:
                                raise RuntimeError(
                                    "Risposta vuota dal modello (text=None)"
                                )
                            degenerate_reason = detect_degenerate_output(generated_text)
                            if degenerate_reason:
                                raise DegenerateOutputError(
                                    degenerate_reason, generated_text
                                )
                            return generated_text
                        except Exception as e:
                            err_txt = str(e)
                            err_lower = err_txt.lower()
                            # inline→upload fallback (no quota involved)
                            if (
                                audio_mode == "inline"
                                and not tried_upload_fallback
                                and any(
                                    k in err_lower
                                    for k in (
                                        "invalid_argument",
                                        "badrequest",
                                        "400",
                                        "payload",
                                        "too large",
                                        "size",
                                    )
                                )
                                and not any(
                                    k in err_lower
                                    for k in ("quota", "resource_exhausted", "429")
                                )
                            ):
                                tried_upload_fallback = True
                                audio_mode = "upload"
                                print(
                                    "      [Inline audio non accettato. Fallback a upload del chunk...]"
                                )
                                continue
                            # 400 / INVALID_ARGUMENT: permanent, do not retry
                            if (
                                "400" in err_txt
                                or "BadRequest" in err_txt
                                or "INVALID_ARGUMENT" in err_txt
                            ):
                                raise PermanentError(err_txt)
                            raise

                try:
                    client, generated_text = retry_with_quota(
                        _call,
                        client=client,
                        fallback_keys=fallback_keys,
                        model_name=model_name,
                        model_state=model_state,
                        runtime=runtime,
                        cancelled=cancelled,
                        request_fallback_key=request_fallback_key,
                        retry_sleep_seconds=30.0,
                        on_key_rotated=_on_key_rotated,
                        on_model_switched=on_model_switched,
                        logger=log,
                        resume_phase_text=f"Fase 1/3: trascrizione (chunk {chunk_idx}/{total_chunks})",
                    )
                    if generated_text is None:
                        success = False
                    else:
                        full_transcript += f"\n\n{generated_text}\n\n"
                        prev_memory = generated_text[-1000:]

                        try:
                            out_chunk_md = os.path.join(
                                phase1_chunks_dir,
                                f"chunk_{chunk_idx:03}_{chunk_start_sec}_{int(chunk_end_sec)}.md",
                            )
                            _atomic_write_text(out_chunk_md, generated_text + "\n")
                            print(
                                f"   [autosave] Chunk salvato: {os.path.basename(out_chunk_md)}"
                            )
                        except Exception as save_err:
                            print(f"   [!] Autosave chunk fallito: {save_err}")

                        _update_session(
                            session,
                            {
                                "stage": "phase1",
                                "phase1": {
                                    **session.get("phase1", {}),
                                    "chunks_done": int(chunk_idx),
                                    "next_start_sec": int(
                                        chunk_start_sec + step_seconds
                                    ),
                                    "memoria_precedente": prev_memory,
                                },
                                "last_error": None,
                            },
                        )
                        save_session()

                        success = True
                        runtime.progress(0.7 * chunk_idx / total_chunks)
                        _step_secs = max(0.0, time.monotonic() - float(chunk_step_t0))
                        runtime.register_step_time(
                            "chunks", _step_secs, done=chunk_idx, total=total_chunks
                        )
                        record_step_metric(
                            session,
                            "chunks",
                            _step_secs,
                            done=chunk_idx,
                            total=total_chunks,
                        )

                except QuotaDailyLimitError:
                    session["last_error"] = "quota_daily_limit_phase1"
                    save_session()
                    print(
                        "[*] Interruzione: progressi salvati. Potrai riprendere piu' tardi."
                    )
                    return client, None, prev_memory

                except PermanentError as pe:
                    print(f"   [!] Richiesta non valida (400). Dettagli:\n{pe}")
                    session["last_error"] = "bad_request_phase1"
                    save_session()
                    return client, None, prev_memory

                except DegenerateOutputError as de:
                    if not chain_exhaustion_recovery_used:
                        chain_exhaustion_recovery_used = True
                        if model_state is not None:
                            old_model = model_state.current
                            model_state.current = model_state.chain[0]
                            if (
                                on_model_switched is not None
                                and old_model != model_state.current
                            ):
                                on_model_switched(old_model, model_state.current)
                        print(
                            f"   [Recovery automatica] chunk={chunk_idx}: catena modelli esaurita ({de}) - un ulteriore pass dal modello primario ({model_state.current if model_state is not None else model_name})..."
                        )
                        continue
                    _excerpt = getattr(de, "rejected_text", "")
                    _excerpt_log = (
                        f"\n      excerpt: {_excerpt[:400]}" if _excerpt else ""
                    )
                    print(
                        f'   [!] Output degenerato nel blocco {chunk_idx}: anche il pass di recovery ha fallito reason="{de}"{_excerpt_log}'
                    )
                    session["last_error"] = "phase1_degenerate_output"
                    save_session()
                    return client, None, prev_memory

                except AllModelsUnavailableError as ue:
                    if not chain_exhaustion_recovery_used:
                        chain_exhaustion_recovery_used = True
                        if model_state is not None:
                            old_model = model_state.current
                            model_state.current = model_state.chain[0]
                            if (
                                on_model_switched is not None
                                and old_model != model_state.current
                            ):
                                on_model_switched(old_model, model_state.current)
                        print(
                            f"   [Recovery automatica] chunk={chunk_idx}: tutti i modelli indisponibili ({ue}) - un ulteriore pass dal modello primario ({model_state.current if model_state is not None else model_name})..."
                        )
                        continue
                    session["last_error"] = "phase1_all_models_unavailable"
                    save_session()
                    return client, None, prev_memory

                except Exception:
                    pass  # success remains False

            except Exception as e:
                print(f"   [!] Errore durante l'elaborazione del blocco: {e}")

            finally:
                if os.path.exists(chunk_path):
                    try:
                        os.remove(chunk_path)
                    except Exception:
                        pass
                if audio_file is not None and file_client is not None:
                    try:
                        file_client.files.delete(name=audio_file.name)
                    except Exception:
                        pass

            if not success:
                session["last_error"] = f"phase1_chunk_failed_{chunk_idx}"
                save_session()
                print(
                    "   [!] Errore critico durante l'elaborazione del blocco. Interrompo (progressi salvati)."
                )
                return client, None, prev_memory
            break

        if not sleep_with_cancel(cancelled, 5):
            print("   [*] Operazione annullata dall'utente.")
            return client, None, prev_memory

    return client, full_transcript, prev_memory
