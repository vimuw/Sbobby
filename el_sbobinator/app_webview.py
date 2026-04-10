"""
PyWebView backend bridge for El Sbobinator.

This module replaces app.py's Tkinter UI with a pywebview-based adapter that
exposes a JS API and implements the exact same duck-typed interface that
pipeline.py expects from app_instance.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import warnings
from collections import deque
from typing import Literal, get_args
from html import escape

# Suppress benign requests warning about chardet/charset_normalizer failing to import
warnings.filterwarnings(
    "ignore", message="Unable to find acceptable character detection dependency"
)

import webview

_ALLOWED_URL_PREFIXES: tuple[str, ...] = (
    "https://github.com/",
    "https://ko-fi.com/",
    "https://go.microsoft.com/fwlink/p/?LinkId=2124703",
    "https://aistudio.google.com/",
)

# Lazy imports to avoid loading heavy deps at startup:
# from el_sbobinator.pipeline import esegui_sbobinatura  -- imported lazily in start_processing
# from el_sbobinator.audio_service import probe_media_duration -- imported lazily in _build_file_descriptor
# from el_sbobinator.validation_service import validate_environment -- imported lazily in validate_environment
from el_sbobinator.bridge_types import (
    BridgeFileItem,
    FileDonePayload,
    FileFailedPayload,
    ProcessDonePayload,
    SetCurrentFilePayload,
    StepTimePayload,
    ValidationResult,
    WorkDonePayload,
    WorkTotalsPayload,
)
from el_sbobinator.file_ops import (
    export_doc_html,
    extract_html_shell,
    open_path_with_default_app,
    read_html_content as read_html_file_content,
    save_html_body_content,
)
from el_sbobinator.logging_utils import configure_logging, get_logger
from el_sbobinator.media_server import LocalMediaServer
from el_sbobinator.model_registry import DEFAULT_FALLBACK_MODELS, MODEL_OPTIONS
from el_sbobinator.shared import (
    DEFAULT_MODEL,
    cleanup_orphan_temp_chunks,
    cleanup_orphan_sessions,
    get_desktop_dir,
    get_session_storage_info,
    load_config,
    save_config,
    SESSION_CLEANUP_MAX_AGE_DAYS,
)

# ---------------------------------------------------------------------------
# DnD helper
# ---------------------------------------------------------------------------


def _drain_dnd_paths(names: set[str]) -> list[tuple[str, str]]:
    """Return and consume (basename, fullpath) pairs matching *names* from
    pywebview's internal DnD state.

    ``webview.dom._dnd_state`` is an undocumented private implementation
    detail. All access is intentionally confined here so that a future
    pywebview refactor breaks only this one function and always produces a
    safe empty-list fallback.
    """
    try:
        from webview.dom import _dnd_state  # noqa: PLC2701

        paths: list = list(_dnd_state.get("paths", []))
        matched, remaining = [], []
        for item in paths:
            (matched if item[0] in names else remaining).append(item)
        _dnd_state["paths"] = remaining
        return matched
    except Exception:
        return []


# ---------------------------------------------------------------------------
# PipelineAdapter: oggetto passato a pipeline.py come "app_instance"
# Implementa la stessa interfaccia duck-typed della UI desktop (CTk).
# ---------------------------------------------------------------------------


class _BridgeDispatcher:
    _BridgeEvent = Literal[
        "updateProgress",
        "updatePhase",
        "setWorkTotals",
        "updateWorkDone",
        "registerStepTime",
        "setCurrentFile",
        "fileDone",
        "fileFailed",
        "filesDropped",
        "processDone",
        "appendConsole",
        "askRegenerate",
        "askNewKey",
    ]
    _ALL_EVENTS: frozenset[str] = frozenset(get_args(_BridgeEvent))
    BATCHABLE: frozenset[str] = frozenset(
        {
            "updateProgress",
            "updatePhase",
            "setWorkTotals",
            "updateWorkDone",
            "registerStepTime",
        }
    )
    MAX_RETRIES = 3

    def __init__(self, window_getter, flush_interval: float = 0.12):
        self._window_getter = window_getter
        self._flush_interval = flush_interval
        self._lock = threading.Lock()
        self._queue: deque[tuple[str, object]] = deque()
        self._latest: dict[str, object] = {}
        self._pending: deque[tuple[str, object, int]] = (
            deque()
        )  # (fn_name, data, retry_count)
        self._timer: threading.Timer | None = None

    def emit(self, fn_name: str, data, batched: bool | None = None):
        assert fn_name in self._ALL_EVENTS, f"Unknown bridge event: {fn_name!r}"
        should_batch = fn_name in self.BATCHABLE if batched is None else batched
        with self._lock:
            if should_batch:
                self._latest[fn_name] = data
            else:
                # Preserve event ordering across file boundaries: flush any pending
                # batched progress/phase updates before lifecycle events like
                # setCurrentFile/fileDone, otherwise stale progress can land on the
                # next file currently marked as processing in the frontend.
                if self._latest:
                    self._queue.extend(self._latest.items())
                    self._latest.clear()
                self._queue.append((fn_name, data))
        self._ensure_timer()

    def flush(self):
        with self._lock:
            self._timer = None
            events: list[tuple[str, object, int]] = []
            # New queued events first (maintain causal order)
            for fn_name, data in self._queue:
                events.append((fn_name, data, 0))
            self._queue.clear()
            # Merge latest batched values as new events with retry_count=0
            if self._latest:
                for fn_name, data in self._latest.items():
                    events.append((fn_name, data, 0))
                self._latest.clear()
            # Retries appended last — they're stale and must not precede newer lifecycle events
            while self._pending:
                fn_name, data, retry_count = self._pending.popleft()
                events.append((fn_name, data, retry_count))

        if not events:
            return

        window = self._window_getter()
        if window is None:
            # Re-queue all events if window not ready
            with self._lock:
                for fn_name, data, retry_count in events:
                    if retry_count < self.MAX_RETRIES:
                        self._pending.append((fn_name, data, retry_count + 1))
            self._ensure_timer()
            return

        js_calls: list[str] = []
        for fn_name, payload, _retry_count in events:
            safe_data = json.dumps(payload, ensure_ascii=False)
            js_calls.append(
                f"if(window.elSbobinatorBridge && window.elSbobinatorBridge.{fn_name}) "
                f"window.elSbobinatorBridge.{fn_name}({safe_data});"
            )

        try:
            window.evaluate_js("\n".join(js_calls))
        except Exception:
            # Re-queue unsent events for retry (respecting max retries)
            with self._lock:
                for fn_name, data, retry_count in events:
                    if retry_count < self.MAX_RETRIES:
                        self._pending.append((fn_name, data, retry_count + 1))
            self._ensure_timer()

    def _ensure_timer(self):
        """Schedule next flush attempt."""
        with self._lock:
            if self._timer is not None:
                return
            self._timer = threading.Timer(self._flush_interval, self.flush)
            self._timer.daemon = True
            self._timer.start()


class PipelineAdapter:
    """Thin adapter mimicking the attributes/methods that pipeline.py reads."""

    def __init__(self, window: webview.Window | None, cancel_event: threading.Event):
        self.window = window
        self.cancel_event = cancel_event
        self._lock = threading.Lock()
        self.file_temporanei: list[str] = []
        self._is_running = False

        # Output info (set by pipeline)
        self.last_output_html: str | None = None
        self.last_output_dir: str | None = None
        self.last_run_status: str = "idle"
        self.last_run_error: str | None = None
        self.effective_api_key: str | None = None

        # For ETA
        self._run_started_monotonic: float | None = None
        self._eta_ema_seconds: float | None = None
        self._step_times: dict = {}

        # Pending UI-answer callbacks (written by pipeline thread, read by UI thread)
        self._regenerate_callback = None
        self._new_key_callback = None

        self._dispatcher = _BridgeDispatcher(lambda: self.window)

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    @is_running.setter
    def is_running(self, value: bool) -> None:
        with self._lock:
            self._is_running = value

    # --- Methods called by pipeline.py's safe_* wrappers ---

    def winfo_exists(self) -> bool:
        try:
            return self.window is not None
        except Exception:
            return False

    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def after(self, delay_ms: int, callback, *args):
        """Schedule a callback. We just run it in a timer thread."""

        def _run():
            time.sleep(delay_ms / 1000.0)
            try:
                callback(*args)
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()

    def aggiorna_progresso(self, value: float):
        self._emit_js("updateProgress", value, batched=True)

    def aggiorna_fase(self, text: str):
        self._emit_js("updatePhase", text, batched=True)

    def imposta_output_html(self, path: str, output_dir: str | None = None):
        self.last_output_html = path
        if output_dir is not None:
            self.last_output_dir = output_dir
        else:
            self.last_output_dir = os.path.dirname(path) if path else None

    def processo_terminato(self):
        # Hook per fine file: il lifecycle del batch e' gestito da ElSbobinatorApi.start_processing.
        return None

    def reset_run_state(self, api_key: str | None = None):
        self.last_output_html = None
        self.last_output_dir = None
        self.last_run_status = "failed"
        self.last_run_error = None
        self.effective_api_key = str(api_key or "").strip() or None

    def set_run_result(self, status: str, error: str | None = None):
        self.last_run_status = str(status or "failed").strip() or "failed"
        self.last_run_error = str(error).strip() if error else None

    def set_effective_api_key(self, api_key: str | None):
        self.effective_api_key = str(api_key or "").strip() or None

    def set_work_totals(self, chunks_total=None, macro_total=None, boundary_total=None):
        payload: WorkTotalsPayload = {
            "chunks": chunks_total,
            "macro": macro_total,
            "boundary": boundary_total,
        }
        self._emit_js("setWorkTotals", payload, batched=True)

    def update_work_done(self, kind: str, done: int, total: int = None):
        payload: WorkDonePayload = {"kind": kind, "done": done, "total": total}
        self._emit_js("updateWorkDone", payload, batched=True)

    def register_step_time(
        self, kind: str, seconds: float, done: int = None, total: int = None
    ):
        # Store for internal ETA calculations and push to frontend
        with self._lock:
            self._step_times.setdefault(kind, []).append(seconds)
        payload: StepTimePayload = {
            "kind": kind,
            "seconds": seconds,
            "done": done,
            "total": total,
        }
        self._emit_js("registerStepTime", payload, batched=True)

    def ask_regenerate(self, filename: str, callback, mode: str = "resume"):
        with self._lock:
            self._regenerate_callback = callback
        self._emit_js(
            "askRegenerate", {"filename": filename, "mode": mode}, batched=False
        )

    def ask_new_api_key(self, callback):
        with self._lock:
            self._new_key_callback = callback
        self._emit_js("askNewKey", {}, batched=False)

    def answer_regenerate(self, regenerate: bool | None):
        with self._lock:
            cb = self._regenerate_callback
            self._regenerate_callback = None
        if regenerate is None:
            self.cancel_event.set()
        if cb:
            cb({"regenerate": regenerate})

    def answer_new_key(self, key: str):
        with self._lock:
            cb = self._new_key_callback
            self._new_key_callback = None
        if cb:
            cb({"key": key})

    def cancel_pending_prompts(self):
        with self._lock:
            regenerate_cb = self._regenerate_callback
            new_key_cb = self._new_key_callback
            self._regenerate_callback = None
            self._new_key_callback = None
        if regenerate_cb:
            regenerate_cb({"regenerate": False})
        if new_key_cb:
            new_key_cb({"key": ""})

    # --- Internal helper ---

    def emit(self, fn_name: str, data, batched: bool | None = None):
        self._emit_js(fn_name, data, batched=batched)

    def _emit_js(self, fn_name: str, data, batched: bool | None = None):
        self._dispatcher.emit(fn_name, data, batched=batched)


# ---------------------------------------------------------------------------
# ElSbobinatorApi: exposed to JS via pywebview js_api
# ---------------------------------------------------------------------------


class ElSbobinatorApi:
    """Methods callable from React via window.pywebview.api.*"""

    def __init__(self):
        self._window: webview.Window | None = None
        self._cancel_event = threading.Event()
        self._adapter = PipelineAdapter(None, self._cancel_event)
        self._processing_thread: threading.Thread | None = None
        self._html_shell_cache: dict[str, tuple[str, str]] = {}
        self._resolved_path_cache: dict[str, str] = {}
        configure_logging()
        self._logger = get_logger("el_sbobinator.webview")

    def set_window(self, window: webview.Window):
        self._window = window
        self._adapter.window = window

    # ---- Settings ----

    def load_settings(self) -> dict:
        """Load saved config from disk."""
        try:
            cfg = load_config()
            return {
                "api_key": cfg.get("api_key", ""),
                "fallback_keys": cfg.get("fallback_keys", []),
                "preferred_model": cfg.get("preferred_model", DEFAULT_MODEL),
                "fallback_models": cfg.get("fallback_models", []),
                "available_models": list(MODEL_OPTIONS),
            }
        except Exception:
            return {
                "api_key": "",
                "fallback_keys": [],
                "preferred_model": DEFAULT_MODEL,
                "fallback_models": list(DEFAULT_FALLBACK_MODELS),
                "available_models": list(MODEL_OPTIONS),
            }

    def save_settings(
        self,
        api_key: str,
        fallback_keys: list[str],
        preferred_model: str,
        fallback_models: list[str],
    ) -> dict:
        """Save config to disk."""
        try:
            save_config(
                api_key,
                fallback_keys=fallback_keys,
                preferred_model=preferred_model,
                fallback_models=fallback_models,
            )
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_session_storage_info(self) -> dict:
        """Return total size and count of session folders in SESSION_ROOT."""
        try:
            info = get_session_storage_info()
            return {
                "ok": True,
                "total_bytes": info["total_bytes"],
                "total_sessions": info["total_sessions"],
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "total_bytes": 0, "total_sessions": 0}

    def cleanup_old_sessions(
        self, max_age_days: int = SESSION_CLEANUP_MAX_AGE_DAYS
    ) -> dict:
        """Delete session folders older than max_age_days days."""
        try:
            result = cleanup_orphan_sessions(max(1, int(max_age_days)))
            return {
                "ok": True,
                "removed": result["removed"],
                "freed_bytes": result["freed_bytes"],
                "errors": result["errors"],
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "removed": 0,
                "freed_bytes": 0,
                "errors": 0,
            }

    # ---- File Selection ----

    @staticmethod
    def _build_file_descriptor(path: str) -> BridgeFileItem:
        try:
            size = os.path.getsize(path)
        except Exception:
            size = 0
        try:
            from el_sbobinator.audio_service import probe_media_duration

            dur_val, _reason = probe_media_duration(path)
            duration = dur_val if dur_val else 0
        except Exception:
            duration = 0
        return {
            "path": path,
            "name": os.path.basename(path),
            "size": size,
            "duration": duration,
        }

    def ask_files(self) -> list[BridgeFileItem]:
        """Open native file dialog and return file info."""
        if not self._window:
            return []
        try:
            file_paths = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=True,
                file_types=(
                    "Audio (*.mp3;*.m4a;*.wav;*.ogg;*.flac;*.aac)",
                    "Video (*.mp4;*.mkv;*.webm)",
                    "All files (*.*)",
                ),
            )
        except Exception:
            # Fallback without filters if the format is still rejected
            file_paths = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=True,
            )
        if not file_paths:
            return []
        selected_paths = (
            list(file_paths) if isinstance(file_paths, (list, tuple)) else [file_paths]
        )
        return [self._build_file_descriptor(path) for path in selected_paths]

    def ask_media_file(self) -> BridgeFileItem | None:
        """Open a native file dialog for a single media file."""
        if not self._window:
            return None
        try:
            file_paths = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=(
                    "Audio (*.mp3;*.m4a;*.wav;*.ogg;*.flac;*.aac)",
                    "Video (*.mp4;*.mkv;*.webm)",
                    "All files (*.*)",
                ),
            )
        except Exception:
            file_paths = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
            )
        if not file_paths:
            return None
        selected_path = (
            file_paths[0] if isinstance(file_paths, (list, tuple)) else file_paths
        )
        return self._build_file_descriptor(selected_path)

    def check_path_exists(self, path: str) -> dict:
        """Check whether a persisted source path still exists on disk."""
        normalized_path = str(path or "").strip()
        return {
            "ok": True,
            "exists": bool(normalized_path and os.path.exists(normalized_path)),
        }

    _ALLOWED_DROP_EXTS = {
        ".mp3",
        ".m4a",
        ".wav",
        ".mp4",
        ".mkv",
        ".webm",
        ".ogg",
        ".flac",
        ".aac",
    }

    def collect_dropped_files(self, names: list) -> dict:
        """Called by JS after postMessageWithAdditionalObjects('FilesDropped') to retrieve OS paths."""
        name_set = {str(n) for n in (names or [])}
        descriptors = []
        for basename, fullpath in _drain_dnd_paths(name_set):
            ext = os.path.splitext(fullpath)[1].lower()
            if ext in self._ALLOWED_DROP_EXTS and os.path.isfile(fullpath):
                descriptors.append(self._build_file_descriptor(fullpath))
        if descriptors:
            self._adapter.emit("filesDropped", descriptors, batched=False)
        return {"ok": True}

    # ---- Processing ----

    def start_processing(
        self, files: list[BridgeFileItem], api_key: str, resume_session: bool = True
    ) -> dict:
        """Start the pipeline in a background thread."""
        if not files or not api_key:
            return {"ok": False, "error": "File o API key mancanti"}
        if self._adapter.is_running:
            return {"ok": False, "error": "Elaborazione già in corso"}

        # Save config
        try:
            save_config(api_key)
        except Exception:
            pass

        # Cleanup orphan temp files
        try:
            removed = cleanup_orphan_temp_chunks()
            if removed > 0:
                self._push_console(f"[*] Pulizia: rimossi {removed} file temporanei.")
        except Exception:
            pass

        # Setup adapter
        self._cancel_event.clear()
        self._adapter.is_running = True
        self._adapter.file_temporanei = []
        self._adapter._run_started_monotonic = time.monotonic()
        self._adapter._step_times = {}
        self._adapter.reset_run_state(api_key)

        # Process files sequentially in background
        def _run():
            from el_sbobinator.pipeline import esegui_sbobinatura

            active_api_key = api_key
            completed_count = 0
            failed_count = 0
            current_index: int | None = None
            current_file_id = ""
            try:
                for idx, file_info in enumerate(files):
                    if self._cancel_event.is_set():
                        break
                    current_index = idx
                    current_file_id = str(file_info.get("id", "") or "")
                    self._adapter.reset_run_state(active_api_key)
                    file_path = file_info.get("path", "")
                    if not file_path or not os.path.exists(file_path):
                        self._push_console(f"[!] File non trovato: {file_path}")
                        payload: FileFailedPayload = {
                            "index": idx,
                            "id": file_info.get("id", ""),
                            "error": "File non trovato.",
                        }
                        self._adapter.emit("fileFailed", payload, batched=False)
                        failed_count += 1
                        current_index = None
                        current_file_id = ""
                        continue

                    self._push_console(f"\n{'=' * 50}")
                    self._push_console(
                        f"  File {idx + 1}/{len(files)}: {os.path.basename(file_path)}"
                    )
                    self._push_console(f"{'=' * 50}")
                    current_payload: SetCurrentFilePayload = {
                        "index": idx,
                        "id": file_info.get("id", ""),
                        "total": len(files),
                    }
                    self._adapter.emit("setCurrentFile", current_payload, batched=False)

                    esegui_sbobinatura(
                        file_path,
                        active_api_key,
                        self._adapter,
                        resume_session=resume_session,
                    )
                    if self._adapter.effective_api_key:
                        active_api_key = self._adapter.effective_api_key

                    if (
                        self._cancel_event.is_set()
                        or self._adapter.last_run_status == "cancelled"
                    ):
                        break

                    if self._adapter.last_run_status == "completed":
                        if self._adapter.last_output_html and os.path.exists(
                            self._adapter.last_output_html
                        ):
                            payload: FileDonePayload = {
                                "index": idx,
                                "id": file_info.get("id", ""),
                                "output_html": self._adapter.last_output_html,
                                "output_dir": self._adapter.last_output_dir,
                            }
                            self._adapter.emit("fileDone", payload, batched=False)
                            completed_count += 1
                        else:
                            payload = {
                                "index": idx,
                                "id": file_info.get("id", ""),
                                "error": "Output HTML non generato.",
                            }
                            self._adapter.emit("fileFailed", payload, batched=False)
                            failed_count += 1
                    else:
                        payload = {
                            "index": idx,
                            "id": file_info.get("id", ""),
                            "error": self._adapter.last_run_error
                            or "Elaborazione non completata.",
                        }
                        self._adapter.emit("fileFailed", payload, batched=False)
                        failed_count += 1
                    current_index = None
                    current_file_id = ""
            except Exception as e:
                if current_index is not None:
                    payload = {
                        "index": current_index,
                        "id": current_file_id,
                        "error": str(e) or "Errore fatale.",
                    }
                    self._adapter.set_run_result("failed", str(e))
                    self._adapter.emit("fileFailed", payload, batched=False)
                    failed_count += 1
                self._push_console(f"[!] Errore fatale: {e}")
            finally:
                self._adapter.is_running = False
                payload: ProcessDonePayload = {
                    "cancelled": bool(
                        self._cancel_event.is_set()
                        or self._adapter.last_run_status == "cancelled"
                    ),
                    "completed": completed_count,
                    "failed": failed_count,
                    "total": len(files),
                }
                self._adapter.emit("processDone", payload, batched=False)

        self._processing_thread = threading.Thread(target=_run, daemon=True)
        self._processing_thread.start()
        return {"ok": True}

    def answer_regenerate(self, regenerate: bool | None) -> dict:
        """Called by React when user clicks Use Saved or Regenerate."""
        self._adapter.answer_regenerate(regenerate)
        return {"ok": True}

    def answer_new_key(self, key: str | None) -> dict:
        """Called by React when user submits a replacement API key."""
        self._adapter.answer_new_key(key or "")
        return {"ok": True}

    def stop_processing(self) -> dict:
        """Request cancellation."""
        self._cancel_event.set()
        self._adapter.cancel_pending_prompts()
        thread = self._processing_thread
        if not self._adapter.is_running and (thread is None or not thread.is_alive()):
            payload: ProcessDonePayload = {
                "cancelled": True,
                "completed": 0,
                "failed": 0,
                "total": 0,
            }
            self._adapter.emit("processDone", payload, batched=False)
        return {"ok": True}

    def validate_environment(
        self,
        api_key: str | None = None,
        check_api_key: bool = False,
        preferred_model: str | None = None,
        fallback_models: list[str] | None = None,
    ) -> dict:
        """Run an explicit environment validation without starting a full transcription."""
        try:
            from el_sbobinator.validation_service import (
                validate_environment as _validate_env,
            )

            result: ValidationResult = _validate_env(
                api_key=api_key,
                validate_api_key=bool(check_api_key),
                preferred_model=preferred_model,
                fallback_models=fallback_models,
            )
            return {"ok": True, "result": result}
        except Exception as e:
            self._logger.exception("Validazione ambiente fallita.")
            return {"ok": False, "error": str(e)}

    def open_file(self, path: str) -> dict:
        """Open a local file/folder with the system default handler."""
        if isinstance(path, str) and (
            path.startswith("http://") or path.startswith("https://")
        ):
            return {"ok": False, "error": "Usa open_url per aprire URL."}
        try:
            open_path_with_default_app(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def open_url(self, url: str) -> dict:
        """Open an external URL in the system browser (allowlist only)."""
        if not isinstance(url, str) or not any(
            url.startswith(p) for p in _ALLOWED_URL_PREFIXES
        ):
            return {"ok": False, "error": "URL non consentito."}
        try:
            open_path_with_default_app(url)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def read_html_content(self, path: str) -> dict:
        """Legge ed estrae il contenuto di un file HTML per l'anteprima."""
        if not isinstance(path, str) or not path.lower().endswith(".html"):
            return {"ok": False, "error": "Path non valido: deve essere un file .html."}
        # Path traversal protection: resolve and check against allowed roots
        real_path = os.path.realpath(os.path.abspath(path))
        allowed_roots = [
            os.path.realpath(get_desktop_dir()),  # Desktop / OneDrive Desktop
            os.path.realpath(self._get_session_root()),  # Session storage
        ]
        if not any(
            real_path.startswith(root + os.sep) or real_path == root
            for root in allowed_roots
        ):
            return {
                "ok": False,
                "error": "Accesso negato: path fuori dai percorsi consentiti.",
            }
        requested_real_path = real_path
        self._resolved_path_cache[requested_real_path] = real_path
        if not os.path.isfile(real_path):
            _basename = os.path.basename(real_path)
            fallback = self._find_html_in_session_dirs(_basename)
            if not fallback:
                fallback = self._rebuild_html_from_session(_basename)
            if fallback and os.path.isfile(fallback):
                real_path = fallback
                if not any(
                    real_path.startswith(root + os.sep) or real_path == root
                    for root in allowed_roots
                ):
                    return {
                        "ok": False,
                        "error": "Accesso negato: path fuori dai percorsi consentiti.",
                    }
                self._resolved_path_cache[requested_real_path] = real_path
            else:
                return {"ok": False, "error": "File non trovato."}
        try:
            content = read_html_file_content(real_path)
            shell = extract_html_shell(content)
            if shell is not None:
                self._html_shell_cache[real_path] = shell
            return {"ok": True, "content": content}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _get_session_root(self) -> str:
        """Return the session storage root directory."""
        from el_sbobinator.shared import SESSION_ROOT

        return SESSION_ROOT

    def _find_html_in_session_dirs(self, basename: str) -> str | None:
        """Cerca un file HTML con lo stesso nome nelle cartelle di sessione.

        Usato come fallback quando il path originale (es. Desktop) non esiste piu'.
        Restituisce il path piu' recente per modifiche tra piu' sessioni candidate.
        """
        session_root = self._get_session_root()
        if not os.path.isdir(session_root):
            return None
        candidates: list[tuple[float, str]] = []
        try:
            for entry in os.scandir(session_root):
                if not entry.is_dir():
                    continue
                candidate = os.path.join(entry.path, basename)
                try:
                    st = os.stat(candidate)
                    candidates.append((st.st_mtime, os.path.realpath(candidate)))
                except (FileNotFoundError, OSError):
                    continue
        except Exception:
            return None
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][1]

    def _rebuild_html_from_session(self, html_basename: str) -> str | None:
        """Ricostruisce l'HTML dai blocchi .md della sessione come ultimo fallback.

        Usato quando l'HTML manca sia al path originale sia nelle session dirs
        (es. sessioni create prima che l'HTML venisse salvato nella session dir).
        """
        from el_sbobinator.export_service import export_final_html_document
        from el_sbobinator.pipeline_session import read_text_file
        from el_sbobinator.shared import _atomic_write_json, safe_output_basename

        session_root = self._get_session_root()
        if not os.path.isdir(session_root):
            return None
        try:
            candidates: list[tuple[float, str, dict]] = []
            for entry in os.scandir(session_root):
                if not entry.is_dir():
                    continue
                session_path = os.path.join(entry.path, "session.json")
                if not os.path.isfile(session_path):
                    continue
                try:
                    with open(session_path, "r", encoding="utf-8") as fh:
                        session_data = json.load(fh)
                    existing_html = session_data.get("outputs", {}).get("html", "")
                    if not existing_html:
                        continue
                    if os.path.basename(str(existing_html)) != html_basename:
                        continue
                    phase2_revised_dir = os.path.join(entry.path, "phase2_revised")
                    if not os.path.isdir(phase2_revised_dir):
                        continue
                    if not session_data.get("input", {}).get("path", ""):
                        continue
                    if session_data.get("stage") != "done":
                        continue
                    mtime = os.path.getmtime(session_path)
                    candidates.append((mtime, entry.path, session_data))
                except Exception:
                    continue
            candidates.sort(key=lambda c: c[0], reverse=True)
            for _mtime, entry_path, session_data in candidates:
                session_path = os.path.join(entry_path, "session.json")
                phase2_revised_dir = os.path.join(entry_path, "phase2_revised")
                input_path = session_data["input"]["path"]
                try:
                    _, html_path = export_final_html_document(
                        input_path=input_path,
                        phase2_revised_dir=phase2_revised_dir,
                        fallback_body="",
                        read_text=read_text_file,
                        output_dir=entry_path,
                        fallback_output_dir=entry_path,
                        safe_output_basename=safe_output_basename,
                    )
                    if not os.path.isfile(html_path):
                        break
                    # export derives its filename from input_path; if input_path
                    # was renamed after session creation the basename will differ
                    # from html_basename. Rename to the canonical basename so
                    # _find_html_in_session_dirs and save_html_content always
                    # resolve the same name.
                    if os.path.basename(html_path) != html_basename:
                        canonical_path = os.path.join(
                            os.path.dirname(html_path), html_basename
                        )
                        os.replace(html_path, canonical_path)
                        html_path = canonical_path
                    try:
                        session_data["outputs"]["html"] = html_path
                        _atomic_write_json(session_path, session_data)
                    except Exception:
                        pass
                    return os.path.realpath(html_path)
                except Exception:
                    continue
        except Exception:
            return None
        return None

    def save_html_content(
        self, path: str, content: str, generation: int | None = None
    ) -> dict:
        """Aggiorna solo il contenuto del <body>, preservando head, stile e CSP dell'export originale."""
        if not isinstance(path, str) or not path.lower().endswith(".html"):
            return {"ok": False, "error": "Path non valido: deve essere un file .html."}
        # Path traversal protection: resolve and check against allowed roots
        real_path = os.path.realpath(os.path.abspath(path))
        original_real_path = real_path
        allowed_roots = [
            os.path.realpath(get_desktop_dir()),  # Desktop / OneDrive Desktop
            os.path.realpath(self._get_session_root()),  # Session storage
        ]
        if not any(
            real_path.startswith(root + os.sep) or real_path == root
            for root in allowed_roots
        ):
            return {
                "ok": False,
                "error": "Accesso negato: path fuori dai percorsi consentiti.",
            }
        if not os.path.isfile(real_path):
            _basename = os.path.basename(real_path)
            cached_resolution = self._resolved_path_cache.get(original_real_path)
            if cached_resolution and os.path.isfile(cached_resolution):
                fallback = cached_resolution
            else:
                fallback = self._find_html_in_session_dirs(_basename)
                if not fallback:
                    fallback = self._rebuild_html_from_session(_basename)
            if fallback and os.path.isfile(fallback):
                real_path = fallback
                if not any(
                    real_path.startswith(root + os.sep) or real_path == root
                    for root in allowed_roots
                ):
                    return {
                        "ok": False,
                        "error": "Accesso negato: path fuori dai percorsi consentiti.",
                    }
                self._resolved_path_cache[original_real_path] = real_path
            else:
                return {"ok": False, "error": "File non trovato."}
        try:
            shell = self._html_shell_cache.get(real_path) or self._html_shell_cache.get(
                original_real_path
            )
            gen = int(generation) if generation is not None else None
            save_html_body_content(real_path, content, shell=shell, generation=gen)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def export_docx(self, filename: str, docx_html: str) -> dict:
        """Salva un file stringa tramite un dialog nativo bypassando eventuali blocchi di download in WebView2/macOS."""
        if not self._window:
            return {"ok": False, "error": "Finestra non trovata."}
        try:
            save_path = self._window.create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=filename,
                file_types=("Word Document (*.docx)", "All files (*.*)"),
            )
            # Gestisci sia lista che stringa (pywebview può restituire entrambi)
            if not save_path:
                return {"ok": False, "error": "Annullato dall'utente"}
            if isinstance(save_path, list):
                if len(save_path) == 0:
                    return {"ok": False, "error": "Annullato dall'utente"}
                selected_path = save_path[0]
            else:
                selected_path = save_path  # È già una stringa

            path = export_doc_html(os.path.normpath(selected_path), docx_html)
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def show_notification(self, title: str, message: str) -> dict:
        """Mostra una notifica toast nativa di sistema tramite plyer."""
        try:
            from plyer import notification

            # On windows, notify requires an absolute path to a .ico file if we want an icon.
            # We'll omit the app_icon for simplicity and cross-platform compatibility.
            notification.notify(
                title=title, message=message, app_name="El Sbobinator", timeout=5
            )
            return {"ok": True}
        except Exception as e:
            # Fallback a legacy OS script
            if sys.platform == "darwin":
                import shlex
                import subprocess

                script = (
                    f"display notification {shlex.quote(str(message or ''))}"
                    f" with title {shlex.quote(str(title or ''))}"
                )
                subprocess.Popen(["osascript", "-e", script])
                return {"ok": True}
            return {"ok": False, "error": str(e)}

    def stream_media_file(self, file_path: str) -> dict:
        """Avvia o riavvia un micro-server HTTP per inviare l'audio nativo a React via streaming byte-range."""
        try:
            return {"ok": True, "url": LocalMediaServer.stream_url_for_file(file_path)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---- Console push helper ----

    def _push_console(self, msg: str):
        self._adapter.emit("appendConsole", msg, batched=False)


# ---------------------------------------------------------------------------
# Monkey-patch print per catturare output della pipeline nella console React
# ---------------------------------------------------------------------------

_MAX_CONSOLE_LINE_LEN = 2000


class _ConsoleTee:
    """Intercept print() calls and forward to React console too."""

    def __init__(self, original, api: ElSbobinatorApi):
        self._original = original  # May be None for .pyw on Windows
        self._api = api

    def write(self, text):
        if self._original is not None:
            try:
                self._original.write(text)
            except Exception:
                pass
        if text and text.strip():
            line = text.rstrip()
            if len(line) > _MAX_CONSOLE_LINE_LEN:
                line = line[:_MAX_CONSOLE_LINE_LEN] + "… [troncato]"
            self._api._push_console(line)

    def flush(self):
        if self._original is not None:
            try:
                self._original.flush()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def get_dist_path() -> str:
    """Locate the webui dist folder (works both in dev and PyInstaller)."""
    if getattr(sys, "frozen", False):
        # PyInstaller bundle
        base = sys._MEIPASS  # type: ignore
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist = os.path.join(base, "webui", "dist", "index.html")
    if os.path.exists(dist):
        return dist
    # Fallback: relative to cwd
    alt = os.path.join(os.getcwd(), "webui", "dist", "index.html")
    if os.path.exists(alt):
        return alt
    raise FileNotFoundError(
        f"Non trovo webui/dist/index.html. Esegui 'npm run build' nella cartella webui/.\n"
        f"Cercato in: {dist} e {alt}"
    )


def has_webview2_runtime() -> bool:
    """Mirror pywebview's Windows runtime detection to avoid silent MSHTML fallback."""
    if sys.platform != "win32":
        return True

    try:
        import winreg
    except Exception:
        return False

    runtime_keys = (
        (
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        ),
    )

    for root, key_path in runtime_keys:
        try:
            with winreg.OpenKey(root, key_path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if str(version).strip():
                    return True
        except Exception:
            continue

    return False


def build_missing_webview2_html() -> str:
    download_url = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
    repo_url = "https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
    return f"""<!doctype html>
<html lang="it">
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="X-UA-Compatible" content="IE=11" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>El Sbobinator</title>
    <style>
      body {{
        margin: 0;
        padding: 40px 20px;
        background: #f0f2f5;
        font-family: "Segoe UI", Arial, sans-serif;
        color: #222;
      }}
      .card {{
        max-width: 560px;
        margin: 20px auto;
        background: #ffffff;
        border: 1px solid #dde1e7;
        border-radius: 10px;
        padding: 36px 40px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
      }}
      h1 {{
        margin: 0 0 14px;
        font-size: 20px;
        font-weight: 700;
        color: #111;
        line-height: 1.3;
      }}
      p {{
        margin: 0 0 10px;
        font-size: 14px;
        line-height: 1.65;
        color: #555;
      }}
      code {{
        background: #eef0f3;
        padding: 2px 7px;
        border-radius: 5px;
        font-family: Consolas, monospace;
        font-size: 12.5px;
        color: #333;
      }}
      strong {{ color: #222; }}
      .actions {{
        margin: 22px 0 18px;
      }}
      a.btn {{
        display: inline-block;
        padding: 9px 18px;
        border-radius: 6px;
        font-size: 13.5px;
        font-weight: 600;
        text-decoration: none;
        margin-right: 8px;
      }}
      a.btn-primary {{
        background: #0f62fe;
        color: #ffffff;
        border: 1px solid #0f62fe;
      }}
      a.btn-secondary {{
        background: #ffffff;
        color: #0f62fe;
        border: 1px solid #c6d0e3;
      }}
      hr {{
        border: none;
        border-top: 1px solid #eef0f3;
        margin: 20px 0;
      }}
      ol {{
        margin: 0;
        padding-left: 22px;
        color: #666;
      }}
      li {{
        font-size: 13.5px;
        line-height: 1.75;
        margin: 2px 0;
      }}
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Serve WebView2 per avviare l&apos;interfaccia</h1>
      <p>
        El Sbobinator sta usando il renderer Windows legacy <code>MSHTML</code>,
        che non supporta la WebUI moderna. Per questo la finestra rimane nera.
      </p>
      <p>
        Installa <strong>Microsoft Edge WebView2 Runtime</strong>
        per avviare l&apos;app normalmente.
      </p>
      <div class="actions">
        <a class="btn btn-primary" href="{escape(download_url)}">Scarica WebView2 Runtime</a>
        <a class="btn btn-secondary" href="{escape(repo_url)}">Dettagli tecnici</a>
      </div>
      <hr />
      <ol>
        <li>Chiudi El Sbobinator.</li>
        <li>Installa WebView2 Runtime.</li>
        <li>Riapri l&apos;app.</li>
      </ol>
    </div>
  </body>
</html>
"""


def main():  # noqa: C901
    api = ElSbobinatorApi()

    # Intercept stdout/stderr to forward to React console
    sys.stdout = _ConsoleTee(sys.__stdout__, api)
    sys.stderr = _ConsoleTee(sys.__stderr__, api)

    dist_path = get_dist_path()
    webview2_available = has_webview2_runtime()

    # Storage path for WebView2 profile cache (avoids re-init freeze)
    storage_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "El Sbobinator",
        "webview_cache",
    )
    os.makedirs(storage_dir, exist_ok=True)

    # Auto cache-bust: clear WebView2 HTTP caches when a new build/version is detected.
    # In onefile PyInstaller mode the extracted files get a new mtime on every launch
    # (new _MEI temp folder), so we use the EXE's own mtime instead — stable until the
    # user installs a new version.
    # IMPORTANT: only delete Cache dirs, NOT the full EBWebView profile — doing so would
    # destroy localStorage (queue, editor sessions) on every restart.
    try:
        import shutil

        mtime_file = os.path.join(storage_dir, ".build_mtime")
        if getattr(sys, "frozen", False):
            current_mtime = str(os.path.getmtime(sys.executable))
        else:
            current_mtime = str(os.path.getmtime(dist_path))
        stored_mtime = ""
        if os.path.exists(mtime_file):
            with open(mtime_file, "r", encoding="utf-8") as _f:
                stored_mtime = _f.read().strip()
        if stored_mtime != current_mtime:
            default_profile = os.path.join(storage_dir, "EBWebView", "Default")
            _cleared = False
            _failed = False
            for cache_name in ("Cache", "Code Cache"):
                cache_dir = os.path.join(default_profile, cache_name)
                if os.path.exists(cache_dir):
                    try:
                        shutil.rmtree(cache_dir)
                        _cleared = True
                    except Exception as _e:
                        _failed = True
                        print(
                            f"[!] Impossibile svuotare cache WebView2 ({cache_name}): {_e}"
                        )
            if _cleared:
                print("[*] Cache WebView2 svuotata (nuova build rilevata).")
            if not _failed:
                with open(mtime_file, "w", encoding="utf-8") as _f:
                    _f.write(current_mtime)
    except Exception:
        pass

    # Center the window on screen
    win_w, win_h = 900, 820
    try:
        if sys.platform == "win32":
            import ctypes

            scr_w = ctypes.windll.user32.GetSystemMetrics(0)
            scr_h = ctypes.windll.user32.GetSystemMetrics(1)
        else:
            scr_w, scr_h = 1920, 1080
        center_x = max(0, (scr_w - win_w) // 2)
        center_y = max(0, (scr_h - win_h) // 2)
    except Exception:
        center_x, center_y = 100, 50

    if webview2_available:
        window = webview.create_window(
            "El Sbobinator",
            dist_path,
            js_api=api,
            width=win_w,
            height=win_h,
            x=center_x,
            y=center_y,
            min_size=(750, 620),
            background_color="#18181b",
            hidden=True,
        )
    else:
        print(
            "[!] Microsoft Edge WebView2 Runtime non trovato. Mostro schermata di recupero."
        )
        window = webview.create_window(
            "El Sbobinator",
            html=build_missing_webview2_html(),
            width=win_w,
            height=win_h,
            x=center_x,
            y=center_y,
            min_size=(750, 620),
            background_color="#18181b",
            hidden=False,
        )
    api.set_window(window)

    def _on_closing():
        LocalMediaServer.shutdown_all()

    window.events.closing += _on_closing

    try:
        from webview.dom import _dnd_state

        _dnd_state["num_listeners"] += 1
    except Exception:
        pass

    if webview2_available:
        window_shown = threading.Event()

        def _show_when_loaded(*_args):
            if window_shown.is_set():
                return
            window_shown.set()
            try:
                if api._window is not None:
                    api._window.show()
            except Exception:
                pass

        window.events.loaded += _show_when_loaded

        def _show_window_fallback():
            time.sleep(4.0)
            if window_shown.is_set():
                return
            window_shown.set()
            try:
                if api._window is not None:
                    api._window.show()
            except Exception:
                pass

        threading.Thread(target=_show_window_fallback, daemon=True).start()

    webview.start(
        private_mode=False,
        storage_path=storage_dir,
    )


if __name__ == "__main__":
    main()
