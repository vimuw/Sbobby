"""
Gemini-centric helpers for the transcription pipeline.

This keeps transport/retry/prompt helpers out of pipeline.py so the remaining
module can focus more on orchestration.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Callable

from google import genai
from google.genai import types

from el_sbobinator.logging_utils import get_logger
from el_sbobinator.shared import load_config

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_FILE_UPLOAD_TIMEOUT_SECONDS: int = 900  # 15-minute ceiling for Google to finish processing an uploaded audio file
_FILE_UPLOAD_POLL_SECONDS: int = 3  # How often (seconds) to re-query file state while waiting

_MAX_RETRY_ATTEMPTS: int = 4  # Maximum Gemini API call attempts before propagating the error
_RETRY_SLEEP_SECONDS: float = 30.0  # Back-off pause between generic transient errors
# Gemini enforces a per-minute request quota that resets after ~60 s; sleeping
# 65 s adds a small buffer to ensure the window has fully elapsed before retry.
_RATE_LIMIT_SLEEP_SECONDS: float = 65.0


def extract_client_api_key(client_obj) -> str | None:
    try:
        direct = getattr(client_obj, "api_key", None) or getattr(client_obj, "_api_key", None)
        if direct:
            return str(direct).strip() or None
    except Exception:
        pass
    try:
        api_client = getattr(client_obj, "_api_client", None)
        nested = getattr(api_client, "api_key", None) or getattr(api_client, "_api_key", None)
        if nested:
            return str(nested).strip() or None
    except Exception:
        pass
    return None


def sleep_with_cancel(cancelled: Callable[[], bool], seconds: float, step: float = 0.2) -> bool:
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


def try_rotate_key(current_client, fallback_keys: list[str], model_name: str, logger=None):
    log = logger or get_logger("el_sbobinator.generation")
    while fallback_keys:
        key = fallback_keys.pop(0).strip()
        if not key:
            continue
        try:
            new_client = genai.Client(api_key=key)
            new_client.models.get(model=model_name)
            log.info("Chiave di fallback valida, rotazione completata.", extra={"stage": "key_rotation"})
            print(f"   [OK] Chiave di riserva valida! ({len(fallback_keys)} rimanenti)")
            return new_client, True, key
        except Exception as err:
            log.warning("Chiave di fallback non valida.", extra={"stage": "key_rotation"})
            print(f"   [!] Chiave di riserva non valida: {err}")
    return current_client, False, None


def wait_for_file_ready(client_for_file, file_obj, cancelled: Callable[[], bool], max_wait_seconds: int = _FILE_UPLOAD_TIMEOUT_SECONDS, poll_seconds: int = _FILE_UPLOAD_POLL_SECONDS):
    start_time = time.monotonic()
    while True:
        state = str(getattr(file_obj, "state", "")).upper()
        if "ACTIVE" not in state and "FAILED" not in state:
            if time.monotonic() - start_time > max_wait_seconds:
                raise TimeoutError("Timeout durante l'elaborazione del file audio sui server Google.")
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
    """Raised when daily API quota is exhausted and no fallback key is available."""


class PermanentError(Exception):
    """Raised for non-retryable failures (e.g. HTTP 400 / INVALID_ARGUMENT)."""


def retry_with_quota(
    callable_fn,
    *,
    client,
    fallback_keys: list,
    model_name: str,
    cancelled,
    runtime,
    request_fallback_key,
    max_attempts: int = _MAX_RETRY_ATTEMPTS,
    retry_sleep_seconds: float = _RETRY_SLEEP_SECONDS,
    rate_limit_sleep_seconds: float = _RATE_LIMIT_SLEEP_SECONDS,
    on_key_rotated=None,
    logger=None,
):
    """Execute callable_fn(client) with automatic quota/rate-limit retry and key rotation.

    Returns (new_client, result) where result is the return value of callable_fn(client).
    Raises QuotaDailyLimitError if daily quota is exhausted with no fallback.
    Raises the original exception after max_attempts for non-quota errors.
    callable_fn receives the current client as its sole argument.
    on_key_rotated(new_client) is called after each successful key rotation.
    """
    log = logger or get_logger("el_sbobinator.generation")
    attempts = 0
    while attempts < max_attempts:
        try:
            result = callable_fn(client)
            return client, result
        except Exception as exc:
            error = str(exc).lower()
            if "429" in error or "resource_exhausted" in error or "quota" in error:
                is_daily = (
                    "per day" in error
                    or "per_day" in error
                    or "perday" in error
                    or "quota_exceeded" in error
                    or "daily" in error
                    or "requests_per_day" in error
                )
                if not is_daily and attempts < max_attempts - 1:
                    print("      [Rilevato limite temporaneo. Attesa di 65s per il reset quota al minuto...]")
                    runtime.phase("⏳ Rate limit: attesa 65s...")
                    if not sleep_with_cancel(cancelled, rate_limit_sleep_seconds):
                        print("   [*] Operazione annullata dall'utente.")
                        return client, None
                    attempts += 1
                    continue
                elif not is_daily:
                    raise

                print("\n[!!] LIMITE GIORNALIERO RAGGIUNTO!")
                new_c, rotated, rotated_key = try_rotate_key(client, fallback_keys, model_name, logger=log)
                if rotated:
                    client = new_c
                    runtime.set_effective_api_key(rotated_key)
                    if on_key_rotated is not None:
                        on_key_rotated(client)
                    attempts = 0
                    continue

                new_api_key = request_fallback_key()
                if new_api_key and new_api_key.strip():
                    try:
                        test_c = genai.Client(api_key=new_api_key.strip())
                        test_c.models.get(model=model_name)
                        client = test_c
                        runtime.set_effective_api_key(new_api_key.strip())
                        if on_key_rotated is not None:
                            on_key_rotated(client)
                        attempts = 0
                        print("   [OK] Nuova API Key valida! Ripresa automatica...")
                        continue
                    except Exception as err:
                        print(f"   [!] Chiave non valida fornita: {err}")

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
            merged = "\n".join([str(getattr(part, "text", "") or "") for part in parts]).strip()
            if merged:
                return merged
    except Exception:
        pass
    return ""


def build_chunk_prompt(previous_tail: str) -> str:
    prompt = (
        "Trascrivi TUTTO il contenuto di questo blocco audio seguendo rigorosamente le istruzioni di sistema. "
        "Non omettere nessun concetto, esempio, cifra o termine tecnico. "
        "Non riassumere: la lunghezza dell'output deve essere proporzionale a quella dell'audio."
    )
    if previous_tail:
        prompt += (
            "\n\nATTENZIONE: Stai continuando una stesura. Questo è l'ultimo paragrafo che hai generato nel blocco precedente:\n"
            f"\"...{previous_tail}\"\n\n"
            "Riprendi il discorso da qui IN MODO FLUIDO. Usa la stessa grandezza per i titoli. "
            "Se all'inizio di questo blocco c'è sovrapposizione, NON ripetere testualmente le frasi già dette, "
            "ma se compare anche solo un dettaglio nuovo includilo."
        )
    return prompt
