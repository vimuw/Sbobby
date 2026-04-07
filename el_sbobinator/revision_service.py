"""
Revision helpers extracted from the main pipeline.
"""

from __future__ import annotations

import difflib
import os
import re
import time
from typing import Callable

from google.genai import types

from el_sbobinator.dedup_utils import local_macro_cleanup
from el_sbobinator.generation_service import (
    QuotaDailyLimitError,
    extract_response_text,
    retry_with_quota,
    sleep_with_cancel,
)
from el_sbobinator.logging_utils import get_logger
from el_sbobinator.pipeline_session import record_step_metric
from el_sbobinator.session_store import _update_session
from el_sbobinator.shared import PROMPT_REVISIONE_CONFINE, _atomic_write_text

BOUNDARY_CHAR_BUDGET = 3000


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


def process_macro_revision_phase(
    *,
    client,
    model_name: str,
    macro_blocks: list[str],
    phase2_revised_dir: str,
    session: dict,
    save_session: Callable[[], bool],
    runtime,
    cancelled: Callable[[], bool],
    fallback_keys: list[str],
    request_fallback_key: Callable[[], str | None],
    prompt_revisione: str,
    logger=None,
) -> tuple[object, str]:
    log = logger or get_logger("el_sbobinator.revision", stage="phase2")
    revised_text = ""
    macro_total = len(macro_blocks)
    revised_done = 0

    runtime.set_work_totals(macro_total=macro_total, boundary_total=max(0, macro_total - 1))
    try:
        runtime.update_work_done("macro", int(session.get("phase2", {}).get("revised_done", 0) or 0), total=macro_total)
    except Exception:
        pass

    for index, block in enumerate(macro_blocks, 1):
        if cancelled():
            print("   [*] Operazione annullata dall'utente.")
            return client, revised_text

        runtime.phase(f"Fase 2/3: revisione ({index}/{macro_total})")
        rev_path = os.path.join(phase2_revised_dir, f"rev_{index:03}.md")
        if os.path.exists(rev_path):
            try:
                with open(rev_path, "r", encoding="utf-8") as _fh:
                    existing = _fh.read().strip()
            except Exception:
                existing = ""
            if existing:
                revised_text += f"\n\n{existing}\n\n"
                revised_done += 1
                runtime.update_work_done("macro", revised_done, total=macro_total)
                _update_session(session, {
                    "stage": "phase2",
                    "phase2": {**session.get("phase2", {}), "revised_done": int(revised_done)},
                    "last_error": None,
                })
                save_session()
                runtime.progress(0.7 + 0.2 * (revised_done / max(1, macro_total)))
                continue

        block_src = (block or "").strip()
        block_local, removed_exact, removed_adj, near_adj, _ = local_macro_cleanup(block_src)
        block_for_ai = (block_local or block_src).strip()
        if removed_exact or removed_adj:
            print(f"   -> Pre-clean locale Macro-blocco {index}/{macro_total}: duplicati rimossi={removed_exact + removed_adj} (sospetti={near_adj}).")

        step_t0 = time.monotonic()
        print(f"   -> Revisione Macro-blocco {index} di {macro_total}...")
        success = False

        def _call(current_client):
            response = current_client.models.generate_content(
                model=model_name,
                contents=[block_for_ai, prompt_revisione],
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
                cancelled=cancelled,
                runtime=runtime,
                request_fallback_key=request_fallback_key,
                retry_sleep_seconds=20.0,
                logger=log,
            )
            if current_text is None:
                return client, revised_text
            revised_text += f"\n\n{current_text}\n\n"
            _atomic_write_text(rev_path, current_text + "\n")
            print(f"   [autosave] Revisione salvata: {os.path.basename(rev_path)}")

            revised_done += 1
            _update_session(session, {
                "stage": "phase2",
                "phase2": {**session.get("phase2", {}), "revised_done": int(revised_done)},
                "last_error": None,
            })
            save_session()

            success = True
            runtime.progress(0.7 + 0.2 * (revised_done / max(1, macro_total)))
            _macro_secs = max(0.0, time.monotonic() - float(step_t0))
            runtime.register_step_time("macro", _macro_secs, done=revised_done, total=macro_total)
            record_step_metric(session, "macro", _macro_secs, done=revised_done, total=macro_total)
        except QuotaDailyLimitError:
            print("   Interruzione: progressi salvati. Potrai riprendere più tardi.")
            session["last_error"] = "quota_daily_limit_phase2"
            save_session()
            return client, revised_text
        except Exception as exc:
            log.warning(
                "Errore revisione blocco %d/%d: %s", index, macro_total, exc,
                extra={"stage": "phase2"},
            )

        if not success:
            print(f"   [!] Errore prolungato nella revisione. Salvo il blocco {index} così com'è per evitare perdite di dati.")
            fallback_text = block_src
            revised_text += f"\n\n{fallback_text}\n\n"
            _atomic_write_text(rev_path, fallback_text + "\n")
            revised_done += 1
            _update_session(session, {
                "stage": "phase2",
                "phase2": {**session.get("phase2", {}), "revised_done": int(revised_done)},
                "last_error": None,
            })
            save_session()
            _macro_secs = max(0.0, time.monotonic() - float(step_t0))
            runtime.register_step_time("macro", _macro_secs, done=revised_done, total=macro_total)
            record_step_metric(session, "macro", _macro_secs, done=revised_done, total=macro_total)

        runtime.progress(0.7 + 0.2 * (revised_done / max(1, macro_total)))
        if not sleep_with_cancel(cancelled, 5):
            print("   [*] Operazione annullata dall'utente.")
            return client, revised_text

    return client, revised_text


def _paragraphs_within_budget(parts: list[str], budget: int, *, from_end: bool) -> list[str]:
    """Return paragraphs from parts that fit within a character budget.

    If from_end=True, collects from the end of the list (tail window).
    If from_end=False, collects from the start (head window).
    Always returns paragraphs in their original order.
    """
    selected: list[str] = []
    total = 0
    source = reversed(parts) if from_end else iter(parts)
    for p in source:
        if total + len(p) > budget and selected:
            break
        selected.append(p)
        total += len(p)
    return list(reversed(selected)) if from_end else selected


def process_boundary_revision_phase(  # noqa: C901
    *,
    client,
    model_name: str,
    boundary_dir: str,
    phase2_revised_dir: str,
    session: dict,
    save_session: Callable[[], bool],
    runtime,
    cancelled: Callable[[], bool],
    fallback_keys: list[str],
    request_fallback_key: Callable[[], str | None],
    logger=None,
) -> object:
    log = logger or get_logger("el_sbobinator.revision", stage="boundary")
    pairs_total = int(session.get("boundary", {}).get("pairs_total", 0) or 0)
    if pairs_total <= 0:
        return client

    try:
        done_files = [name for name in os.listdir(boundary_dir) if name.lower().startswith("boundary_") and name.lower().endswith(".done")]
    except Exception:
        done_files = []

    done_indexes: set[int] = set()
    for name in done_files:
        match = re.match(r"^boundary_(\d{3})\.done$", name, flags=re.IGNORECASE)
        if match:
            try:
                done_indexes.add(int(match.group(1)))
            except Exception:
                pass

    next_pair = int(session.get("boundary", {}).get("next_pair", 1) or 1)
    if done_indexes:
        next_pair = max(next_pair, max(done_indexes) + 1)

    runtime.set_work_totals(boundary_total=pairs_total)
    runtime.update_work_done("boundary", max(0, int(next_pair) - 1), total=pairs_total)

    def split_paragraphs(text: str) -> list[str]:
        return [paragraph for paragraph in (text or "").split("\n\n") if paragraph.strip()]

    def join_paragraphs(parts: list[str]) -> str:
        return "\n\n".join([part.strip() for part in parts if part and part.strip()]).strip()

    def is_heading(paragraph: str) -> bool:
        first = (paragraph or "").lstrip()
        return bool(re.match(r"^#{1,6}\s+\S", first))

    def normalize_paragraph(paragraph: str) -> str:
        text = (paragraph or "").strip()
        text = text.replace("**", "")
        text = re.sub(r"(?m)^\s*([*+-]|\d+\.)\s+", "", text)
        text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
        return re.sub(r"\s+", " ", text).strip().lower()

    def strict_duplicate(tail_p: str, head_p: str) -> bool:
        if is_heading(head_p):
            return False
        tail = normalize_paragraph(tail_p)
        head = normalize_paragraph(head_p)
        if len(head) < 80 or len(tail) < 80:
            return False
        if tail == head:
            return True
        if head in tail and (len(head) / max(1, len(tail))) >= 0.92:
            return True
        return tail in head and (len(tail) / max(1, len(head))) >= 0.92

    def max_similarity(tail_list: list[str], head_list: list[str]) -> float:
        best = 0.0
        max_window = min(len(tail_list), len(head_list))
        for length in range(1, max_window + 1):
            tail_window = tail_list[-length:]
            head_window = head_list[:length]
            weighted_sum = 0.0
            total_weight = 0.0
            for tp, hp in zip(tail_window, head_window):
                if is_heading(tp) or is_heading(hp):
                    continue
                t = normalize_paragraph(tp)
                h = normalize_paragraph(hp)
                if len(t) < 120 or len(h) < 120:
                    continue
                weight = float(len(t) + len(h))
                weighted_sum += difflib.SequenceMatcher(a=t, b=h).ratio() * weight
                total_weight += weight
            if total_weight > 0.0:
                best = max(best, weighted_sum / total_weight)
        return best

    for pair_idx in range(next_pair, pairs_total + 1):
        if cancelled():
            print("   [*] Operazione annullata dall'utente.")
            return client

        runtime.phase(f"Fase 3/3: confine ({pair_idx}/{pairs_total})")
        step_t0 = time.monotonic()
        done_path = os.path.join(boundary_dir, f"boundary_{pair_idx:03}.done")
        if os.path.exists(done_path):
            session["boundary"]["next_pair"] = int(pair_idx + 1)
            save_session()
            runtime.register_step_time("boundary", 0.0, done=pair_idx, total=pairs_total)
            record_step_metric(session, "boundary", 0.0, done=pair_idx, total=pairs_total)
            continue

        try:
            with open(os.path.join(phase2_revised_dir, f"rev_{pair_idx:03}.md"), "r", encoding="utf-8") as handle_a:
                left_text = handle_a.read().strip()
            with open(os.path.join(phase2_revised_dir, f"rev_{pair_idx + 1:03}.md"), "r", encoding="utf-8") as handle_b:
                right_text = handle_b.read().strip()
        except Exception:
            left_text = ""
            right_text = ""

        left_parts = split_paragraphs(left_text)
        right_parts = split_paragraphs(right_text)
        if not left_parts or not right_parts:
            _atomic_write_text(done_path, "")
            session["boundary"]["next_pair"] = int(pair_idx + 1)
            save_session()
            _bsecs = max(0.0, time.monotonic() - float(step_t0))
            runtime.register_step_time("boundary", _bsecs, done=pair_idx, total=pairs_total)
            record_step_metric(session, "boundary", _bsecs, done=pair_idx, total=pairs_total)
            continue

        tail_list = _paragraphs_within_budget(left_parts, BOUNDARY_CHAR_BUDGET, from_end=True)
        head_list = _paragraphs_within_budget(right_parts, BOUNDARY_CHAR_BUDGET, from_end=False)
        tail_count = len(tail_list)
        head_count = len(head_list)

        overlap = 0
        max_try = min(len(tail_list), len(head_list))
        for length in range(max_try, 0, -1):
            if all(strict_duplicate(tail_list[-length + offset], head_list[offset]) for offset in range(length)):
                overlap = length
                break

        if overlap > 0:
            print(f"   -> Confine {pair_idx}/{pairs_total}: duplicati certi trovati (locale). Rimuovo {overlap} paragrafo/i duplicati dal blocco N+1.")
            new_right = join_paragraphs(right_parts[overlap:])
            _atomic_write_text(os.path.join(phase2_revised_dir, f"rev_{pair_idx + 1:03}.md"), (new_right + "\n") if new_right else "")
            _atomic_write_text(done_path, "")
            _update_session(session, {
                "boundary": {**session.get("boundary", {}), "next_pair": int(pair_idx + 1)},
                "last_error": None,
            })
            save_session()
            runtime.progress(0.9 + 0.08 * (pair_idx / max(1, pairs_total)))
            _bsecs = max(0.0, time.monotonic() - float(step_t0))
            runtime.register_step_time("boundary", _bsecs, done=pair_idx, total=pairs_total)
            record_step_metric(session, "boundary", _bsecs, done=pair_idx, total=pairs_total)
            continue

        similarity = max_similarity(tail_list, head_list)
        if similarity < 0.975:
            print(f"   -> Confine {pair_idx}/{pairs_total}: nessuna sovrapposizione evidente (locale). Skip AI.")
            _atomic_write_text(done_path, "")
            _update_session(session, {
                "boundary": {**session.get("boundary", {}), "next_pair": int(pair_idx + 1)},
                "last_error": None,
            })
            save_session()
            runtime.progress(0.9 + 0.08 * (pair_idx / max(1, pairs_total)))
            _bsecs = max(0.0, time.monotonic() - float(step_t0))
            runtime.register_step_time("boundary", _bsecs, done=pair_idx, total=pairs_total)
            record_step_metric(session, "boundary", _bsecs, done=pair_idx, total=pairs_total)
            continue

        tail = join_paragraphs(tail_list)
        head = join_paragraphs(head_list)
        payload = "FINE BLOCCO N:\n" + tail + "\n\n<<<EL_SBOBINATOR_SPLIT>>>\n\nINIZIO BLOCCO N+1:\n" + head
        print(f"   -> Confine {pair_idx}/{pairs_total}: sovrapposizione sospetta (sim={similarity:.3f}). Fallback AI...")

        def _call(current_client):
            response = current_client.models.generate_content(
                model=model_name,
                contents=[payload, PROMPT_REVISIONE_CONFINE],
                config=types.GenerateContentConfig(temperature=0.1),
            )
            output = extract_response_text(response)
            if "<<<EL_SBOBINATOR_SPLIT>>>" not in output:
                raise RuntimeError("Marker non trovato nell'output di revisione confine.")

            new_left_tail, new_right_head = output.split("<<<EL_SBOBINATOR_SPLIT>>>", 1)
            new_left_tail = new_left_tail.strip()
            new_right_head = new_right_head.strip()
            if not new_left_tail or not new_right_head:
                raise RuntimeError("Output confine vuoto.")

            left_prefix = join_paragraphs(left_parts[:-tail_count])
            right_suffix = join_paragraphs(right_parts[head_count:])
            new_left = (left_prefix + "\n\n" + new_left_tail).strip() if left_prefix else new_left_tail
            new_right = (new_right_head + "\n\n" + right_suffix).strip() if right_suffix else new_right_head

            _atomic_write_text(os.path.join(phase2_revised_dir, f"rev_{pair_idx:03}.md"), new_left + "\n")
            _atomic_write_text(os.path.join(phase2_revised_dir, f"rev_{pair_idx + 1:03}.md"), new_right + "\n")
            _atomic_write_text(done_path, "")
            _update_session(session, {
                "boundary": {**session.get("boundary", {}), "next_pair": int(pair_idx + 1)},
                "last_error": None,
            })
            save_session()
            return True

        try:
            client, result = retry_with_quota(
                _call,
                client=client,
                fallback_keys=fallback_keys,
                model_name=model_name,
                cancelled=cancelled,
                runtime=runtime,
                request_fallback_key=request_fallback_key,
                retry_sleep_seconds=20.0,
                logger=log,
            )
            if result is None:
                return client
            runtime.progress(0.9 + 0.08 * (pair_idx / max(1, pairs_total)))
            _bsecs = max(0.0, time.monotonic() - float(step_t0))
            runtime.register_step_time("boundary", _bsecs, done=pair_idx, total=pairs_total)
            record_step_metric(session, "boundary", _bsecs, done=pair_idx, total=pairs_total)
        except QuotaDailyLimitError:
            print("[*] Interruzione: progressi salvati. Potrai riprendere più tardi.")
            session["last_error"] = "quota_daily_limit_boundary"
            save_session()
            return client
        except Exception as exc:
            print(f"      [Errore confine {pair_idx} dopo tutti i tentativi: {exc}]")
            log.error(
                "Boundary revision failed for pair %d/%d: %s",
                pair_idx, pairs_total, exc,
                extra={"stage": "boundary"},
            )
            _update_session(session, {
                "boundary": {**session.get("boundary", {}), "next_pair": int(pair_idx)},
                "last_error": "boundary_ai_failed",
            })
            save_session()
            return client

    return client
