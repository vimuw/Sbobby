"""
Gemini-centric helpers for the transcription pipeline.

This keeps transport/retry/prompt helpers out of pipeline.py so the remaining
module can focus more on orchestration.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import Counter
from collections.abc import Callable

from google import genai
from google.genai import types

from el_sbobinator.logging_utils import get_logger
from el_sbobinator.model_registry import MODEL_OPTIONS, ModelState, next_model_in_chain
from el_sbobinator.services.config_service import load_config

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_FILE_UPLOAD_TIMEOUT_SECONDS: int = (
    900  # 15-minute ceiling for Google to finish processing an uploaded audio file
)
_FILE_UPLOAD_POLL_SECONDS: int = (
    3  # How often (seconds) to re-query file state while waiting
)

_MAX_RETRY_ATTEMPTS: int = (
    4  # Maximum Gemini API call attempts before propagating the error
)
_RETRY_SLEEP_SECONDS: float = 30.0  # Back-off pause between generic transient errors
_MODEL_UNAVAILABLE_RETRY_DELAYS: tuple[float, ...] = (
    3.0,
    6.0,
    15.0,
)  # Progressive back-off before switching model on 503/UNAVAILABLE (4 total attempts)
# Gemini enforces a per-minute request quota that resets after ~60 s; sleeping
# 65 s adds a small buffer to ensure the window has fully elapsed before retry.
_RATE_LIMIT_SLEEP_SECONDS: float = 65.0


def _error_text(exc: Exception) -> str:
    """Flatten structured SDK errors into a searchable lowercase string."""
    parts: list[str] = []
    for attr in ("message", "status"):
        value = getattr(exc, attr, None)
        if value:
            parts.append(str(value))
    details = getattr(exc, "details", None)
    if details:
        try:
            parts.append(json.dumps(details, ensure_ascii=False, sort_keys=True))
        except TypeError:
            parts.append(str(details))
    response = getattr(exc, "response", None)
    if response is not None:
        for attr in ("text", "reason_phrase", "reason"):
            value = getattr(response, attr, None)
            if value:
                parts.append(str(value))
    parts.append(str(exc))
    return " ".join(part for part in parts if part).lower()


def _error_code(exc: Exception) -> int | None:
    raw_candidates = [
        getattr(exc, "code", None),
        getattr(getattr(exc, "response", None), "status_code", None),
        getattr(getattr(exc, "response", None), "status", None),
    ]
    for raw in raw_candidates:
        try:
            if raw is None or raw == "":
                continue
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def _is_minute_scoped_rate_limit(
    error_text: str, error_code: int | None = None
) -> bool:
    markers = (
        "per minute",
        "per-minute",
        "per_minute",
        "rate limit",
        "too many requests",
        "requests_per_minute",
        "requests per minute",
        "retry-after",
        "retry after",
        "rpm",
    )
    return error_code == 429 or any(marker in error_text for marker in markers)


def _is_daily_or_key_exhausted(error_text: str, error_code: int | None) -> bool:
    hard_limit_markers = (
        "per day",
        "per-day",
        "per_day",
        "perday",
        "daily",
        "quota_exceeded",
        "requests_per_day",
        "requests per day",
        "insufficient_quota",
        "insufficient quota",
        "insufficient_balance",
        "insufficient balance",
        "billing",
        "credit",
        "balance",
    )
    if any(marker in error_text for marker in hard_limit_markers):
        return True

    if _is_minute_scoped_rate_limit(error_text, error_code):
        return False

    token_markers = ("token", "tokens")
    token_exhaustion_markers = (
        "exhaust",
        "exceeded",
        "finished",
        "ended",
        "insufficient",
        "unavailable",
        "depleted",
    )
    if any(marker in error_text for marker in token_markers) and any(
        marker in error_text for marker in token_exhaustion_markers
    ):
        return True

    # Some Gemini quota failures are surfaced as plain HTTP 503 / UNAVAILABLE,
    # but the structured payload still says RESOURCE_EXHAUSTED.
    if error_code == 503 and "resource_exhausted" in error_text:
        return True

    return False


def _is_model_unavailable(error_text: str, error_code: int | None) -> bool:
    if error_code != 503:
        return False
    markers = (
        "service unavailable",
        "backend error",
        "model is overloaded",
        "overloaded",
        "temporarily unavailable",
    )
    return any(marker in error_text for marker in markers)


def _is_quota_related(error_text: str, error_code: int | None) -> bool:
    return (
        error_code == 429
        or "resource_exhausted" in error_text
        or "quota" in error_text
        or "rate limit" in error_text
        or "too many requests" in error_text
    )


def _is_model_not_found(error_text: str, error_code: int | None) -> bool:
    if error_code != 404:
        return False
    markers = (
        "not_found",
        "not found",
        "not supported for generatecontent",
        "unsupported for generatecontent",
        "models/",
    )
    return any(marker in error_text for marker in markers)


def current_model_name(model_state: ModelState | None, default_model: str) -> str:
    if model_state is None:
        return str(default_model or "").strip()
    current = str(getattr(model_state, "current", "") or "").strip()
    return current or str(default_model or "").strip()


def extract_client_api_key(client_obj) -> str | None:
    try:
        direct = getattr(client_obj, "api_key", None) or getattr(
            client_obj, "_api_key", None
        )
        if direct:
            return str(direct).strip() or None
    except Exception:
        pass
    try:
        api_client = getattr(client_obj, "_api_client", None)
        nested = getattr(api_client, "api_key", None) or getattr(
            api_client, "_api_key", None
        )
        if nested:
            return str(nested).strip() or None
    except Exception:
        pass
    return None


def sleep_with_cancel(
    cancelled: Callable[[], bool], seconds: float, step: float = 0.2
) -> bool:
    deadline = time.monotonic() + float(seconds)
    while time.monotonic() < deadline:
        if cancelled():
            return False
        time.sleep(min(step, deadline - time.monotonic()))
    return True


def load_fallback_keys() -> list[str]:
    try:
        config = load_config()
        raw = config.get("fallback_keys", [])
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
    except Exception:
        pass
    return []


def try_rotate_key(
    current_client,
    fallback_keys: list[str],
    model_name: str,
    logger=None,
    cancelled: Callable[[], bool] | None = None,
):
    log = logger or get_logger("el_sbobinator.generation")
    while fallback_keys:
        if cancelled is not None and cancelled():
            return current_client, False, None
        key = fallback_keys[0].strip()
        if not key:
            fallback_keys.pop(0)
            continue
        try:
            new_client = genai.Client(api_key=key)
            new_client.models.get(model=model_name)
            if cancelled is not None and cancelled():
                return current_client, False, None
            fallback_keys.pop(0)
            log.info(
                "Chiave di fallback valida, rotazione completata.",
                extra={"stage": "key_rotation"},
            )
            print(f"   [OK] Chiave di riserva valida! ({len(fallback_keys)} rimanenti)")
            return new_client, True, key
        except Exception as err:
            fallback_keys.pop(0)
            log.warning(
                "Chiave di fallback non valida.", extra={"stage": "key_rotation"}
            )
            print(f"   [!] Chiave di riserva non valida: {err}")
    return current_client, False, None


def wait_for_file_ready(
    client_for_file,
    file_obj,
    cancelled: Callable[[], bool],
    max_wait_seconds: int = _FILE_UPLOAD_TIMEOUT_SECONDS,
    poll_seconds: int = _FILE_UPLOAD_POLL_SECONDS,
):
    start_time = time.monotonic()
    while True:
        state = str(getattr(file_obj, "state", "")).upper()
        if "ACTIVE" not in state and "FAILED" not in state:
            if time.monotonic() - start_time > max_wait_seconds:
                raise TimeoutError(
                    "Timeout durante l'elaborazione del file audio sui server Google."
                )
            if not sleep_with_cancel(cancelled, poll_seconds):
                return None
            file_obj = client_for_file.files.get(name=file_obj.name)
            continue
        if "FAILED" in state:
            raise RuntimeError(f"Caricamento fallito (state={state}).")
        return file_obj


def upload_audio_path(client_for_upload, path_str: str):
    try:
        return client_for_upload.files.upload(path=path_str)
    except TypeError:
        return client_for_upload.files.upload(file=path_str)


def make_inline_audio_part(path_str: str, max_bytes: int | None = None):
    try:
        if max_bytes is not None:
            try:
                size = int(os.path.getsize(path_str))
                if size > int(max_bytes):
                    return None
            except Exception:
                pass
        with open(path_str, "rb") as handle:
            data = handle.read()
        return types.Part.from_bytes(data=data, mime_type="audio/mpeg")
    except Exception:
        return None


def request_new_api_key(runtime, cancelled: Callable[[], bool]):
    print("   [In attesa di una nuova chiave API dall'utente nel popup...]")
    event = threading.Event()
    result = {"new_key": None}

    def handler(response):
        result["new_key"] = response.get("key", None)
        event.set()

    if not runtime.ask_new_api_key(handler):
        print("ERRORE: Funzione webview non trovata per il popup.")
        return None

    while not event.is_set():
        if cancelled():
            return None
        event.wait(0.2)
    return result["new_key"]


class QuotaDailyLimitError(Exception):
    """Raised when the active API key is exhausted and no fallback key is available."""


class PermanentError(Exception):
    """Raised for non-retryable failures (e.g. HTTP 400 / INVALID_ARGUMENT)."""


class DegenerateOutputError(RuntimeError):
    """Raised when a model returns repetitive/runaway text that must be discarded."""

    def __init__(self, reason: str, rejected_text: str = "") -> None:
        super().__init__(reason)
        self.rejected_text: str = (rejected_text or "")[:500]


class AllModelsUnavailableError(RuntimeError):
    """Raised when all models in the fallback chain are 503-unavailable."""


def _normalize_guardrail_text(text: str) -> str:
    normalized = str(text or "").replace("\u00a0", " ").strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s*([,.;:!?])\s*", r"\1", normalized)
    return normalized


def detect_degenerate_output(text: str) -> str | None:
    raw = str(text or "").strip()
    if not raw:
        return None

    paragraphs = [
        segment.strip()
        for segment in re.split(r"\n\s*\n+", raw)
        if segment and segment.strip()
    ]
    if not paragraphs:
        return None

    if any(len(paragraph) > 12000 for paragraph in paragraphs):
        longest = max(len(paragraph) for paragraph in paragraphs)
        return f"paragrafo troppo lungo ({longest} caratteri)"

    normalized_paragraphs = [
        _normalize_guardrail_text(paragraph) for paragraph in paragraphs
    ]
    paragraph_candidates = [
        paragraph for paragraph in normalized_paragraphs if len(paragraph) >= 80
    ]
    if paragraph_candidates:
        paragraph_counts = Counter(paragraph_candidates)
        repeated_paragraph = max(paragraph_counts.values(), default=0)
        if repeated_paragraph >= 4:
            return f"paragrafo ripetuto {repeated_paragraph} volte"
        duplicate_paragraphs = sum(
            count - 1 for count in paragraph_counts.values() if count > 1
        )
        if (
            duplicate_paragraphs >= 8
            and duplicate_paragraphs / max(1, len(paragraph_candidates)) >= 0.20
        ):
            return f"troppi paragrafi duplicati ({duplicate_paragraphs} duplicati)"

    sentence_candidates: list[str] = []
    for paragraph in paragraphs:
        parts = re.split(r"(?<=[.!?])\s+|\n+", paragraph)
        for sentence in parts:
            normalized = _normalize_guardrail_text(sentence)
            if len(normalized) >= 40:
                sentence_candidates.append(normalized)
    if sentence_candidates:
        sentence_counts = Counter(sentence_candidates)
        repeated_sentence = max(sentence_counts.values(), default=0)
        if repeated_sentence >= 8:
            return f"frase ripetuta {repeated_sentence} volte"

    if len(raw) > 120000 and len(paragraphs) <= 5:
        return f"output eccessivo e poco segmentato ({len(raw)} caratteri)"

    return None


def _switch_to_next_model(
    model_state: ModelState,
    *,
    on_model_switched,
    error_message: str,
    cause: Exception,
    exc_type: type[Exception] = RuntimeError,
) -> None:
    next_model = next_model_in_chain(model_state)
    if next_model:
        old_model = model_state.current
        model_state.current = next_model
        print(f"      [Fallback modello] {old_model} -> {next_model}")
        if on_model_switched is not None:
            on_model_switched(old_model, next_model)
        return
    tried = ", ".join(model_state.chain)
    raise exc_type(
        f"{error_message} Ho provato tutti i fallback configurati: {tried}."
    ) from cause


def _phase1_temperature(model_name: str) -> float:
    for opt in MODEL_OPTIONS:
        if opt["id"] == model_name:
            return float(opt.get("phase1_temperature", 0.35))
    return 0.35


def retry_with_quota(  # noqa: C901
    callable_fn,
    *,
    client,
    fallback_keys: list,
    model_name: str,
    model_state: ModelState | None = None,
    cancelled,
    runtime,
    request_fallback_key,
    max_attempts: int = _MAX_RETRY_ATTEMPTS,
    retry_sleep_seconds: float = _RETRY_SLEEP_SECONDS,
    model_unavailable_retry_delays: tuple[float, ...] = _MODEL_UNAVAILABLE_RETRY_DELAYS,
    rate_limit_sleep_seconds: float = _RATE_LIMIT_SLEEP_SECONDS,
    on_key_rotated=None,
    on_model_switched=None,
    logger=None,
    resume_phase_text: str | None = None,
):
    """Execute callable_fn(client) with automatic quota/rate-limit retry and key rotation.

    Returns (new_client, result) where result is the return value of callable_fn(client).
    Raises QuotaDailyLimitError if daily quota is exhausted with no fallback.
    Raises the original exception after max_attempts for non-quota errors.
    callable_fn receives the current client as its sole argument.
    on_key_rotated(new_client) is called after each successful key rotation.
    """
    log = logger or get_logger("el_sbobinator.generation")

    def _restore_phase() -> None:
        if runtime is not None and resume_phase_text:
            runtime.phase(resume_phase_text)

    attempts = 0
    while attempts < max_attempts:
        if cancelled():
            return client, None
        try:
            result = callable_fn(client)
            return client, result
        except Exception as exc:
            if cancelled():
                print("   [*] Operazione annullata dall'utente.")
                return client, None
            error = _error_text(exc)
            error_code = _error_code(exc)
            is_quota_related = _is_quota_related(error, error_code)
            current_model = current_model_name(model_state, model_name)

            if model_state is not None and isinstance(exc, DegenerateOutputError):
                _rejected_len = len(getattr(exc, "rejected_text", ""))
                print(
                    f'      [Output degenerato] model={current_model} reason="{exc}" ({_rejected_len} chars) - provo fallback...'
                )
                _switch_to_next_model(
                    model_state,
                    on_model_switched=on_model_switched,
                    error_message="Tutti i modelli della chain hanno prodotto output degenerato o non valido.",
                    cause=exc,
                    exc_type=DegenerateOutputError,
                )
                attempts = 0
                continue

            if model_state is not None and _is_model_not_found(error, error_code):
                print(
                    f"      [Modello {current_model} non supportato o non trovato. Provo il fallback successivo...]"
                )
                _switch_to_next_model(
                    model_state,
                    on_model_switched=on_model_switched,
                    error_message="Modello Gemini non supportato o non trovato.",
                    cause=exc,
                )
                attempts = 0
                continue

            if (
                not is_quota_related
                and _is_model_unavailable(error, error_code)
                and model_state is not None
            ):
                _switched = False
                _total = len(model_unavailable_retry_delays)
                for _retry_idx, _wait in enumerate(
                    model_unavailable_retry_delays, start=1
                ):
                    print(
                        f"      [Modello {current_model} temporaneamente indisponibile."
                        f" Riprovo tra {int(_wait)}s... (retry {_retry_idx}/{_total})]"
                    )
                    runtime.phase(
                        f"Modello non disponibile: attesa {int(_wait)}s... (retry {_retry_idx}/{_total})"
                    )
                    if not sleep_with_cancel(cancelled, _wait):
                        print("   [*] Operazione annullata dall'utente.")
                        return client, None
                    _restore_phase()
                    try:
                        result = callable_fn(client)
                        return client, result
                    except Exception as retry_exc:
                        if cancelled():
                            print("   [*] Operazione annullata dall'utente.")
                            return client, None
                        retry_error = _error_text(retry_exc)
                        retry_code = _error_code(retry_exc)
                        if _is_model_unavailable(retry_error, retry_code):
                            if _retry_idx == _total:
                                _switch_to_next_model(
                                    model_state,
                                    on_model_switched=on_model_switched,
                                    error_message="Modello Gemini indisponibile.",
                                    cause=retry_exc,
                                    exc_type=AllModelsUnavailableError,
                                )
                                _switched = True
                                break
                            # not yet exhausted: inner for-loop continues to next delay
                        else:
                            exc = retry_exc
                            error = retry_error
                            error_code = retry_code
                            is_quota_related = _is_quota_related(
                                retry_error, retry_code
                            )
                            current_model = current_model_name(model_state, model_name)
                            break
                if _switched:
                    attempts = 0
                    continue

            if is_quota_related:
                is_minute_rate_limit = _is_minute_scoped_rate_limit(error, error_code)
                is_exhausted_key = _is_daily_or_key_exhausted(error, error_code)
                if (
                    is_minute_rate_limit
                    and not is_exhausted_key
                    and attempts < max_attempts - 1
                ):
                    print(
                        "      [Rilevato limite temporaneo. Attesa di 65s per il reset quota al minuto...]"
                    )
                    runtime.phase("⏳ Rate limit: attesa 65s...")
                    if not sleep_with_cancel(cancelled, rate_limit_sleep_seconds):
                        print("   [*] Operazione annullata dall'utente.")
                        return client, None
                    _restore_phase()
                    attempts += 1
                    continue
                elif is_minute_rate_limit and not is_exhausted_key:
                    raise exc

                print("\n[!!] CHIAVE API ESAURITA O QUOTA GIORNALIERA RAGGIUNTA!")
                if cancelled():
                    print("   [*] Operazione annullata dall'utente.")
                    return client, None
                new_c, rotated, rotated_key = try_rotate_key(
                    client,
                    fallback_keys,
                    current_model,
                    logger=log,
                    cancelled=cancelled,
                )
                if rotated:
                    client = new_c
                    runtime.set_effective_api_key(rotated_key)
                    if on_key_rotated is not None:
                        on_key_rotated(client)
                    attempts = 0
                    continue

                if cancelled():
                    print("   [*] Operazione annullata dall'utente.")
                    return client, None
                new_api_key = request_fallback_key()
                if new_api_key and new_api_key.strip():
                    try:
                        test_c = genai.Client(api_key=new_api_key.strip())
                        test_c.models.get(model=current_model)
                        client = test_c
                        runtime.set_effective_api_key(new_api_key.strip())
                        if on_key_rotated is not None:
                            on_key_rotated(client)
                        attempts = 0
                        print("   [OK] Nuova API Key valida! Ripresa automatica...")
                        continue
                    except Exception as err:
                        print(f"   [!] Chiave non valida fornita: {err}")

                if model_state is not None:
                    _switch_to_next_model(
                        model_state,
                        on_model_switched=on_model_switched,
                        error_message="Quota giornaliera esaurita su tutte le chiavi disponibili.",
                        cause=exc,
                        exc_type=QuotaDailyLimitError,
                    )
                    attempts = 0
                    continue

                raise QuotaDailyLimitError(str(exc)) from exc

            # Non-retryable: propagate immediately
            if isinstance(exc, PermanentError):
                raise

            # Non-quota error: retry with sleep
            attempts += 1
            if attempts >= max_attempts:
                raise
            print(f"      [Errore: {exc}. Riprovo in {int(retry_sleep_seconds)}s...]")
            if not sleep_with_cancel(cancelled, retry_sleep_seconds):
                print("   [*] Operazione annullata dall'utente.")
                return client, None
    return client, None


def extract_response_text(response) -> str:
    raw = getattr(response, "text", None)
    if raw is None:
        text = ""
    elif isinstance(raw, str):
        text = raw.strip()
    else:
        text = str(raw).strip()

    if text:
        return text

    try:
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            merged = "\n".join(
                [str(getattr(part, "text", "") or "") for part in parts]
            ).strip()
            if merged:
                return merged
    except Exception:
        pass
    return ""


def build_chunk_prompt(previous_tail: str) -> str:
    prompt = (
        "Trascrivi TUTTO il contenuto di questo blocco audio seguendo rigorosamente le istruzioni di sistema. "
        "Non omettere nessun concetto, esempio, cifra o termine tecnico. "
        "Non riassumere: la lunghezza dell'output deve essere proporzionale a quella dell'audio. "
        "Ogni paragrafo generato deve essere unico: non ripetere mai lo stesso paragrafo o frase."
    )
    if previous_tail:
        prompt += (
            "\n\nATTENZIONE: Stai continuando una stesura. Questo è l'ultimo paragrafo che hai generato nel blocco precedente:\n"
            f'"...{previous_tail}"\n\n'
            "Riprendi il discorso da qui IN MODO FLUIDO. Usa la stessa grandezza per i titoli. "
            "Se all'inizio di questo blocco c'è sovrapposizione, NON ripetere testualmente le frasi già dette, "
            "ma se compare anche solo un dettaglio nuovo includilo."
        )
    return prompt
