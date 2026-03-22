"""
Revision helpers extracted from the main pipeline.
"""

from __future__ import annotations

import difflib
import os
import re
import time
from typing import Callable

from google import genai
from google.genai import types

from el_sbobinator.dedup_utils import local_macro_cleanup
from el_sbobinator.generation_service import extract_response_text, sleep_with_cancel, try_rotate_key
from el_sbobinator.logging_utils import get_logger
from el_sbobinator.shared import PROMPT_REVISIONE_CONFINE, _atomic_write_text


def build_macro_blocks(text: str, macro_char_limit: int) -> list[str]:
    paragraphs = text.split("\n\n")
    blocks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) > macro_char_limit:
            if current.strip():
                blocks.append(current)
            current = paragraph + "\n\n"
        else:
            current += paragraph + "\n\n"
    if current.strip():
        blocks.append(current)
    return blocks


def process_macro_revision_phase(
    *,
    client,
    model_name: str,
    macro_blocks: list[str],
    phase2_revised_dir: str,
    session: dict,
    save_session: Callable[[], bool],
    safe_phase: Callable[[str], None],
    safe_progress: Callable[[float], None],
    safe_set_work_totals: Callable[..., None],
    safe_update_work_done: Callable[..., None],
    safe_register_step_time: Callable[..., None],
    safe_set_effective_api_key: Callable[[str | None], None],
    cancelled: Callable[[], bool],
    fallback_keys: list[str],
    richiedi_chiave_riserva: Callable[[], str | None],
    is_empty_model_response_error: Callable[[str], bool],
    prompt_revisione: str,
    logger=None,
) -> tuple[object, str]:
    log = logger or get_logger("el_sbobinator.revision", stage="phase2")
    revised_text = ""
    macro_total = len(macro_blocks)
    revised_done = 0

    safe_set_work_totals(macro_total=macro_total, boundary_total=max(0, macro_total - 1))
    try:
        safe_update_work_done("macro", int(session.get("phase2", {}).get("revised_done", 0) or 0), total=macro_total)
    except Exception:
        pass

    for index, block in enumerate(macro_blocks, 1):
        if cancelled():
            print("   [*] Operazione annullata dall'utente.")
            return client, revised_text

        safe_phase(f"Fase 2/3: revisione ({index}/{macro_total})")
        rev_path = os.path.join(phase2_revised_dir, f"rev_{index:03}.md")
        if os.path.exists(rev_path):
            try:
                existing = open(rev_path, "r", encoding="utf-8").read().strip()
            except Exception:
                existing = ""
            if existing:
                revised_text += f"\n\n{existing}\n\n"
                revised_done += 1
                safe_update_work_done("macro", revised_done, total=macro_total)
                session["stage"] = "phase2"
                session.setdefault("phase2", {})
                session["phase2"]["revised_done"] = int(revised_done)
                session["last_error"] = None
                save_session()
                safe_progress(0.7 + 0.2 * (revised_done / max(1, macro_total)))
                continue

        block_src = (block or "").strip()
        block_local, removed_exact, removed_adj, near_adj, _ = local_macro_cleanup(block_src)
        block_for_ai = (block_local or block_src).strip()
        if removed_exact or removed_adj:
            print(f"   -> Pre-clean locale Macro-blocco {index}/{macro_total}: duplicati rimossi={removed_exact + removed_adj} (sospetti={near_adj}).")

        step_t0 = time.monotonic()
        print(f"   -> Revisione Macro-blocco {index} di {macro_total}...")
        success = False
        attempts = 0
        while attempts < 4:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[block_for_ai, prompt_revisione],
                    config=types.GenerateContentConfig(temperature=0.1),
                )
                current_text = extract_response_text(response)
                if not current_text:
                    raise RuntimeError("Risposta vuota dal modello in revisione.")

                revised_text += f"\n\n{current_text}\n\n"
                _atomic_write_text(rev_path, current_text + "\n")
                print(f"   [autosave] Revisione salvata: {os.path.basename(rev_path)}")

                revised_done += 1
                session["stage"] = "phase2"
                session.setdefault("phase2", {})
                session["phase2"]["revised_done"] = int(revised_done)
                session["last_error"] = None
                save_session()

                success = True
                safe_progress(0.7 + 0.2 * (revised_done / max(1, macro_total)))
                safe_register_step_time("macro", max(0.0, time.monotonic() - float(step_t0)), done=revised_done, total=macro_total)
                break
            except Exception as exc:
                error = str(exc).lower()
                if "429" in error or "resource_exhausted" in error or "quota" in error:
                    is_daily_limit = "per day" in error or "quota_exceeded" in error or "daily" in error or ("429" in error and "minute" not in error and "rpm" not in error)
                    if not is_daily_limit and attempts < 3:
                        print("      [Rilevato limite temporaneo. Attesa di 65s per il reset quota al minuto...]")
                        if not sleep_with_cancel(cancelled, 65):
                            print("   [*] Operazione annullata dall'utente.")
                            return client, revised_text
                        attempts += 1
                        continue

                    print("\n⛔ LIMITE GIORNALIERO RAGGIUNTO durante la revisione!")
                    client, rotated, rotated_key = try_rotate_key(client, fallback_keys, model_name, logger=log)
                    if rotated:
                        safe_set_effective_api_key(rotated_key)
                        print("   Ripresa automatica della revisione...")
                        attempts = 0
                        continue

                    nuova_api = richiedi_chiave_riserva()
                    if nuova_api and nuova_api.strip():
                        try:
                            test_client = genai.Client(api_key=nuova_api.strip())
                            test_client.models.get(model=model_name)
                            client = test_client
                            safe_set_effective_api_key(nuova_api.strip())
                            print("   ✅ Nuova API Key valida! Ripresa automatica della revisione...")
                            attempts = 0
                            continue
                        except Exception as err:
                            print(f"   [!] Chiave non valida fornita: {err}")

                    print("   Interruzione: progressi salvati. Potrai riprendere più tardi.")
                    session["last_error"] = "quota_daily_limit_phase2"
                    save_session()
                    return client, revised_text

                if is_empty_model_response_error(str(exc)):
                    print("      [Risposta vuota/filtrata dal modello in revisione. Riprovo in 20 secondi...]")
                else:
                    print("      [Server occupati o errore. Riprovo in 20 secondi...]")
                if not sleep_with_cancel(cancelled, 20):
                    print("   [*] Operazione annullata dall'utente.")
                    return client, revised_text
                attempts += 1

        if not success:
            print(f"   [!] Errore prolungato nella revisione. Salvo il blocco {index} così com'è per evitare perdite di dati.")
            fallback_text = block_src
            revised_text += f"\n\n{fallback_text}\n\n"
            _atomic_write_text(rev_path, fallback_text + "\n")
            revised_done += 1
            session["stage"] = "phase2"
            session.setdefault("phase2", {})
            session["phase2"]["revised_done"] = int(revised_done)
            session["last_error"] = None
            save_session()
            safe_register_step_time("macro", max(0.0, time.monotonic() - float(step_t0)), done=revised_done, total=macro_total)

        safe_progress(0.7 + 0.2 * (revised_done / max(1, macro_total)))
        if not sleep_with_cancel(cancelled, 5):
            print("   [*] Operazione annullata dall'utente.")
            return client, revised_text

    return client, revised_text


def process_boundary_revision_phase(
    *,
    client,
    model_name: str,
    boundary_dir: str,
    phase2_revised_dir: str,
    session: dict,
    save_session: Callable[[], bool],
    safe_phase: Callable[[str], None],
    safe_progress: Callable[[float], None],
    safe_set_work_totals: Callable[..., None],
    safe_update_work_done: Callable[..., None],
    safe_register_step_time: Callable[..., None],
    safe_set_effective_api_key: Callable[[str | None], None],
    cancelled: Callable[[], bool],
    fallback_keys: list[str],
    richiedi_chiave_riserva: Callable[[], str | None],
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

    safe_set_work_totals(boundary_total=pairs_total)
    safe_update_work_done("boundary", max(0, int(next_pair) - 1), total=pairs_total)

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
        return head in tail and (len(head) / max(1, len(tail))) >= 0.92

    def max_similarity(tail_list: list[str], head_list: list[str]) -> float:
        best = 0.0
        for tail_p in tail_list:
            tail = normalize_paragraph(tail_p)
            if len(tail) < 120:
                continue
            for head_p in head_list:
                if is_heading(head_p):
                    continue
                head = normalize_paragraph(head_p)
                if len(head) < 120:
                    continue
                best = max(best, difflib.SequenceMatcher(a=tail, b=head).ratio())
        return best

    for pair_idx in range(next_pair, pairs_total + 1):
        if cancelled():
            print("   [*] Operazione annullata dall'utente.")
            return client

        safe_phase(f"Fase 3/3: confine ({pair_idx}/{pairs_total})")
        step_t0 = time.monotonic()
        done_path = os.path.join(boundary_dir, f"boundary_{pair_idx:03}.done")
        if os.path.exists(done_path):
            session["boundary"]["next_pair"] = int(pair_idx + 1)
            save_session()
            safe_register_step_time("boundary", 0.0, done=pair_idx, total=pairs_total)
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
            safe_register_step_time("boundary", max(0.0, time.monotonic() - float(step_t0)), done=pair_idx, total=pairs_total)
            continue

        tail_count = min(6, len(left_parts))
        head_count = min(6, len(right_parts))
        tail_list = left_parts[-tail_count:]
        head_list = right_parts[:head_count]

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
            session["boundary"]["next_pair"] = int(pair_idx + 1)
            session["last_error"] = None
            save_session()
            safe_progress(0.9 + 0.08 * (pair_idx / max(1, pairs_total)))
            safe_register_step_time("boundary", max(0.0, time.monotonic() - float(step_t0)), done=pair_idx, total=pairs_total)
            continue

        similarity = max_similarity(tail_list, head_list)
        if similarity < 0.975:
            print(f"   -> Confine {pair_idx}/{pairs_total}: nessuna sovrapposizione evidente (locale). Skip AI.")
            _atomic_write_text(done_path, "")
            session["boundary"]["next_pair"] = int(pair_idx + 1)
            session["last_error"] = None
            save_session()
            safe_progress(0.9 + 0.08 * (pair_idx / max(1, pairs_total)))
            safe_register_step_time("boundary", max(0.0, time.monotonic() - float(step_t0)), done=pair_idx, total=pairs_total)
            continue

        tail = join_paragraphs(tail_list)
        head = join_paragraphs(head_list)
        payload = "FINE BLOCCO N:\n" + tail + "\n\n<<<EL_SBOBINATOR_SPLIT>>>\n\nINIZIO BLOCCO N+1:\n" + head
        print(f"   -> Confine {pair_idx}/{pairs_total}: sovrapposizione sospetta (sim={similarity:.3f}). Fallback AI...")

        attempts = 0
        while attempts < 4:
            try:
                response = client.models.generate_content(
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
                session["boundary"]["next_pair"] = int(pair_idx + 1)
                session["last_error"] = None
                save_session()
                safe_progress(0.9 + 0.08 * (pair_idx / max(1, pairs_total)))
                safe_register_step_time("boundary", max(0.0, time.monotonic() - float(step_t0)), done=pair_idx, total=pairs_total)
                break
            except Exception as exc:
                error = str(exc).lower()
                if "429" in error or "resource_exhausted" in error or "quota" in error:
                    is_daily_limit = "per day" in error or "quota_exceeded" in error or "daily" in error or ("429" in error and "minute" not in error and "rpm" not in error)
                    if not is_daily_limit and attempts < 3:
                        print("      [Limite temporaneo. Attesa di 65s...]")
                        if not sleep_with_cancel(cancelled, 65):
                            print("   [*] Operazione annullata dall'utente.")
                            return client
                        attempts += 1
                        continue

                    print("\n[!] LIMITE GIORNALIERO durante revisione confine!")
                    client, rotated, rotated_key = try_rotate_key(client, fallback_keys, model_name, logger=log)
                    if rotated:
                        safe_set_effective_api_key(rotated_key)
                        print("   Ripresa automatica...")
                        attempts = 0
                        continue

                    nuova_api = richiedi_chiave_riserva()
                    if nuova_api and nuova_api.strip():
                        try:
                            test_client = genai.Client(api_key=nuova_api.strip())
                            test_client.models.get(model=model_name)
                            client = test_client
                            safe_set_effective_api_key(nuova_api.strip())
                            print("   [*] Nuova API Key valida! Ripresa automatica...")
                            attempts = 0
                            continue
                        except Exception as err:
                            print(f"   [!] Chiave non valida fornita: {err}")

                    print("[*] Interruzione: progressi salvati. Potrai riprendere più tardi.")
                    session["last_error"] = "quota_daily_limit_boundary"
                    save_session()
                    return client

                print("      [Errore confine. Riprovo in 20 secondi...]")
                if not sleep_with_cancel(cancelled, 20):
                    print("   [*] Operazione annullata dall'utente.")
                    return client
                attempts += 1

    return client
