"""
Revision helpers extracted from the main pipeline.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable

from google.genai import types

from el_sbobinator.dedup_utils import local_macro_cleanup
from el_sbobinator.logging_utils import get_logger
from el_sbobinator.model_registry import ModelState
from el_sbobinator.pipeline.pipeline_session import record_step_metric
from el_sbobinator.services.generation_service import (
    QuotaDailyLimitError,
    current_model_name,
    extract_response_text,
    retry_with_quota,
    sleep_with_cancel,
)
from el_sbobinator.session_store import _update_session
from el_sbobinator.shared import _atomic_write_text


def build_macro_blocks(text: str, macro_char_limit: int) -> list[str]:
    paragraphs = text.split("\n\n")
    blocks: list[str] = []
    current_parts: list[str] = []
    current_len = 0
    _h_re = re.compile(r"^\s*#{1,3}\s+\S")
    for paragraph in paragraphs:
        seg = paragraph + "\n\n"
        is_h = bool(_h_re.match(paragraph))
        past_soft = current_len > macro_char_limit * 0.70
        has_content = current_len > 500
        if current_len + len(paragraph) > macro_char_limit and current_parts:
            blocks.append("".join(current_parts))
            current_parts = [seg]
            current_len = len(seg)
        elif is_h and past_soft and has_content and current_parts:
            blocks.append("".join(current_parts))
            current_parts = [seg]
            current_len = len(seg)
        else:
            current_parts.append(seg)
            current_len += len(seg)
    if current_parts:
        joined = "".join(current_parts)
        if joined.strip():
            blocks.append(joined)
    return blocks


def process_macro_revision_phase(  # noqa: C901
    *,
    client,
    model_name: str,
    model_state: ModelState | None = None,
    macro_blocks: list[str],
    phase2_revised_dir: str,
    session: dict,
    save_session: Callable[[], bool],
    runtime,
    cancelled: Callable[[], bool],
    fallback_keys: list[str],
    request_fallback_key: Callable[[], str | None],
    prompt_revisione: str,
    on_model_switched=None,
    logger=None,
) -> tuple[object, str]:
    log = logger or get_logger("el_sbobinator.revision", stage="phase2")
    revised_text = ""
    macro_total = len(macro_blocks)
    revised_done = 0
    pending_retry: list[tuple[int, str, str]] = []  # (index, raw_path, rev_path)

    runtime.set_work_totals(macro_total=macro_total)
    try:
        runtime.update_work_done(
            "macro",
            int(session.get("phase2", {}).get("revised_done", 0) or 0),
            total=macro_total,
        )
    except Exception:
        pass

    for index, block in enumerate(macro_blocks, 1):
        if cancelled():
            print("   [*] Operazione annullata dall'utente.")
            return client, revised_text

        runtime.phase(f"Fase 2/3: revisione ({index}/{macro_total})")
        rev_path = os.path.join(phase2_revised_dir, f"rev_{index:03}.md")
        raw_path = os.path.join(phase2_revised_dir, f"rev_{index:03}.raw.md")

        if os.path.exists(rev_path):
            try:
                with open(rev_path, encoding="utf-8") as _fh:
                    existing = _fh.read().strip()
            except Exception:
                existing = ""
            if existing:
                revised_text += f"\n\n{existing}\n\n"
                revised_done += 1
                runtime.update_work_done("macro", revised_done, total=macro_total)
                _update_session(
                    session,
                    {
                        "stage": "phase2",
                        "phase2": {
                            **session.get("phase2", {}),
                            "revised_done": int(revised_done),
                        },
                        "last_error": None,
                    },
                )
                save_session()
                runtime.progress(0.7 + 0.2 * (revised_done / max(1, macro_total)))
                continue

        if os.path.exists(raw_path):
            pending_retry.append((index, raw_path, rev_path))
            continue

        block_src = (block or "").strip()
        block_local, removed_exact, removed_adj, near_adj, _ = local_macro_cleanup(
            block_src
        )
        block_for_ai = (block_local or block_src).strip()
        if removed_exact or removed_adj:
            print(
                f"   -> Pre-clean locale Macro-blocco {index}/{macro_total}: duplicati rimossi={removed_exact + removed_adj} (sospetti={near_adj})."
            )

        step_t0 = time.monotonic()
        print(f"   -> Revisione Macro-blocco {index} di {macro_total}...")
        success = False

        def _call(current_client):
            response = current_client.models.generate_content(
                model=current_model_name(model_state, model_name),
                contents=[block_for_ai, prompt_revisione],  # noqa: B023
                config=types.GenerateContentConfig(temperature=0.1),
            )
            current_text = extract_response_text(response)
            if not current_text:
                raise RuntimeError("Risposta vuota dal modello in revisione.")
            return current_text

        try:
            client, current_text = retry_with_quota(
                _call,
                client=client,
                fallback_keys=fallback_keys,
                model_name=model_name,
                model_state=model_state,
                cancelled=cancelled,
                runtime=runtime,
                request_fallback_key=request_fallback_key,
                retry_sleep_seconds=20.0,
                on_model_switched=on_model_switched,
                logger=log,
                resume_phase_text=f"Fase 2/3: revisione ({index}/{macro_total})",
            )
            if current_text is None:
                return client, revised_text
            revised_text += f"\n\n{current_text}\n\n"
            _atomic_write_text(rev_path, current_text + "\n")
            print(f"   [autosave] Revisione salvata: {os.path.basename(rev_path)}")

            revised_done += 1
            _update_session(
                session,
                {
                    "stage": "phase2",
                    "phase2": {
                        **session.get("phase2", {}),
                        "revised_done": int(revised_done),
                    },
                    "last_error": None,
                },
            )
            save_session()

            success = True
            runtime.progress(0.7 + 0.2 * (revised_done / max(1, macro_total)))
            _macro_secs = max(0.0, time.monotonic() - float(step_t0))
            runtime.register_step_time(
                "macro", _macro_secs, done=revised_done, total=macro_total
            )
            record_step_metric(
                session, "macro", _macro_secs, done=revised_done, total=macro_total
            )
        except QuotaDailyLimitError:
            print("   Interruzione: progressi salvati. Potrai riprendere più tardi.")
            session["last_error"] = "quota_daily_limit_phase2"
            save_session()
            return client, revised_text
        except Exception as exc:
            log.warning(
                "Errore revisione blocco %d/%d: %s",
                index,
                macro_total,
                exc,
                extra={"stage": "phase2"},
            )

        if not success:
            print(
                f"   [!] Revisione blocco {index} fallita. Salvo provvisoriamente come raw (sarà riprovato)."
            )
            _atomic_write_text(raw_path, block_src + "\n")
            pending_retry.append((index, raw_path, rev_path))
            _macro_secs = max(0.0, time.monotonic() - float(step_t0))
            runtime.register_step_time(
                "macro", _macro_secs, done=revised_done, total=macro_total
            )
            record_step_metric(
                session, "macro", _macro_secs, done=revised_done, total=macro_total
            )

        runtime.progress(0.7 + 0.2 * (revised_done / max(1, macro_total)))
        if not sleep_with_cancel(cancelled, 5):
            print("   [*] Operazione annullata dall'utente.")
            return client, revised_text

    # ---- RETRY PASS: second attempt on provisionally-failed blocks ----
    if pending_retry:
        print(
            f"\n[*] Retry pass: {len(pending_retry)} blocco/i senza revisione. Riprovo..."
        )
        _update_session(
            session, {"revision_pending_blocks": [idx for idx, _, _ in pending_retry]}
        )
        save_session()

        failed_blocks: list[int] = []

        for index, raw_path, rev_path in pending_retry:
            if cancelled():
                print("   [*] Operazione annullata dall'utente (retry pass).")
                return client, revised_text

            try:
                with open(raw_path, encoding="utf-8") as _fh:
                    block_src = _fh.read().rstrip("\n")
            except Exception:
                block_src = ""

            if not block_src:
                _atomic_write_text(rev_path, "")
                try:
                    os.remove(raw_path)
                except Exception:
                    pass
                revised_done += 1
                _update_session(
                    session,
                    {
                        "stage": "phase2",
                        "phase2": {
                            **session.get("phase2", {}),
                            "revised_done": int(revised_done),
                        },
                    },
                )
                save_session()
                failed_blocks.append(index)
                continue

            block_local, removed_exact, removed_adj, _, _ = local_macro_cleanup(
                block_src
            )
            block_for_ai_retry = (block_local or block_src).strip()

            runtime.phase(f"Fase 2/3: retry revisione (blocco {index}/{macro_total})")
            print(f"   -> Retry revisione blocco {index}/{macro_total}...")
            step_t0 = time.monotonic()
            retry_success = False

            def _call_retry(current_client, _block=block_for_ai_retry):
                response = current_client.models.generate_content(
                    model=current_model_name(model_state, model_name),
                    contents=[_block, prompt_revisione],
                    config=types.GenerateContentConfig(temperature=0.1),
                )
                current_text = extract_response_text(response)
                if not current_text:
                    raise RuntimeError("Risposta vuota dal modello in revisione.")
                return current_text

            try:
                client, current_text = retry_with_quota(
                    _call_retry,
                    client=client,
                    fallback_keys=fallback_keys,
                    model_name=model_name,
                    model_state=model_state,
                    cancelled=cancelled,
                    runtime=runtime,
                    request_fallback_key=request_fallback_key,
                    retry_sleep_seconds=20.0,
                    on_model_switched=on_model_switched,
                    logger=log,
                    resume_phase_text=f"Fase 2/3: retry revisione (blocco {index}/{macro_total})",
                )
                if current_text is None:
                    return client, revised_text
                _atomic_write_text(rev_path, current_text + "\n")
                try:
                    os.remove(raw_path)
                except Exception:
                    pass
                print(f"   [OK] Retry blocco {index}: revisione completata.")
                retry_success = True
                revised_done += 1
                _update_session(
                    session,
                    {
                        "stage": "phase2",
                        "phase2": {
                            **session.get("phase2", {}),
                            "revised_done": int(revised_done),
                        },
                        "last_error": None,
                    },
                )
                save_session()
                _macro_secs = max(0.0, time.monotonic() - float(step_t0))
                runtime.register_step_time(
                    "macro", _macro_secs, done=revised_done, total=macro_total
                )
                record_step_metric(
                    session, "macro", _macro_secs, done=revised_done, total=macro_total
                )
            except QuotaDailyLimitError:
                print(
                    "   Interruzione: quota giornaliera raggiunta durante retry pass."
                )
                session["last_error"] = "quota_daily_limit_phase2"
                save_session()
                return client, revised_text
            except Exception as exc:
                log.warning(
                    "Retry revisione blocco %d/%d fallita: %s",
                    index,
                    macro_total,
                    exc,
                    extra={"stage": "phase2"},
                )

            if not retry_success:
                print(
                    f"   [!!] Blocco {index}: revisione definitivamente fallita. Incluso non revisionato."
                )
                try:
                    os.rename(raw_path, rev_path)
                except Exception:
                    _atomic_write_text(rev_path, block_src + "\n")
                    try:
                        os.remove(raw_path)
                    except Exception:
                        pass
                revised_done += 1
                failed_blocks.append(index)
                _update_session(
                    session,
                    {
                        "stage": "phase2",
                        "phase2": {
                            **session.get("phase2", {}),
                            "revised_done": int(revised_done),
                        },
                    },
                )
                save_session()
                _macro_secs = max(0.0, time.monotonic() - float(step_t0))
                runtime.register_step_time(
                    "macro", _macro_secs, done=revised_done, total=macro_total
                )
                record_step_metric(
                    session, "macro", _macro_secs, done=revised_done, total=macro_total
                )

            runtime.progress(0.7 + 0.2 * (revised_done / max(1, macro_total)))

        session_update: dict = {"revision_pending_blocks": []}
        if failed_blocks:
            session_update["revision_failed_blocks"] = failed_blocks
        _update_session(session, session_update)
        save_session()
        if failed_blocks:
            print(
                f"\n[!!] ATTENZIONE: i seguenti blocchi sono stati inclusi non revisionati: {failed_blocks}"
            )

    # Rebuild revised_text from all final .md files (authoritative source of truth)
    revised_text = ""
    for idx in range(1, macro_total + 1):
        rpath = os.path.join(phase2_revised_dir, f"rev_{idx:03}.md")
        if os.path.exists(rpath):
            try:
                with open(rpath, encoding="utf-8") as _fh:
                    content = _fh.read().strip()
                if content:
                    revised_text += f"\n\n{content}\n\n"
            except Exception:
                pass

    return client, revised_text
