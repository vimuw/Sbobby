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

# Suppress benign requests warning about chardet/charset_normalizer failing to import
warnings.filterwarnings("ignore", message="Unable to find acceptable character detection dependency")

import webview

# Lazy imports to avoid loading customtkinter/pipeline at startup
# from el_sbobinator.pipeline import esegui_sbobinatura  -- imported lazily in start_processing
# from el_sbobinator.audio_service import probe_media_duration -- imported lazily in ask_files
from el_sbobinator.audio_service import probe_media_duration
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
    open_path_with_default_app,
    read_html_content as read_html_file_content,
    save_html_body_content,
)
from el_sbobinator.logging_utils import configure_logging, get_logger
from el_sbobinator.media_server import LocalMediaServer
from el_sbobinator.shared import (
    DEFAULT_MODEL,
    load_config,
    save_config,
    cleanup_orphan_temp_chunks,
)
from el_sbobinator.validation_service import validate_environment

# ---------------------------------------------------------------------------
# PipelineAdapter: oggetto passato a pipeline.py come "app_instance"
# Implementa la stessa interfaccia duck-typed della UI desktop (CTk).
# ---------------------------------------------------------------------------


class _BridgeDispatcher:
    BATCHABLE = {"updateProgress", "updatePhase", "setWorkTotals", "updateWorkDone", "registerStepTime"}

    def __init__(self, window_getter, flush_interval: float = 0.12):
        self._window_getter = window_getter
        self._flush_interval = flush_interval
        self._lock = threading.Lock()
        self._queue: deque[tuple[str, object]] = deque()
        self._latest: dict[str, object] = {}
        self._timer: threading.Timer | None = None

    def emit(self, fn_name: str, data, batched: bool | None = None):
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
            self._ensure_timer_locked()

    def flush(self):
        with self._lock:
            self._timer = None
            events = list(self._queue)
            self._queue.clear()
            if self._latest:
                events.extend(self._latest.items())
                self._latest.clear()

        if not events:
            return

        window = self._window_getter()
        if window is None:
            return

        js_calls: list[str] = []
        for fn_name, payload in events:
            safe_data = json.dumps(payload, ensure_ascii=False)
            js_calls.append(
                f"if(window.elSbobinatorBridge && window.elSbobinatorBridge.{fn_name}) "
                f"window.elSbobinatorBridge.{fn_name}({safe_data});"
            )

        try:
            window.evaluate_js("\n".join(js_calls))
        except Exception:
            pass

    def _ensure_timer_locked(self):
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
        self.file_temporanei: list[str] = []
        self.is_running = False

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
        self._dispatcher = _BridgeDispatcher(lambda: self.window)

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

    def imposta_output_html(self, path: str):
        self.last_output_html = path
        self.last_output_dir = os.path.dirname(path) if path else None
        self._emit_js("setOutputHtml", path, batched=False)

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

    def register_step_time(self, kind: str, seconds: float, done: int = None, total: int = None):
        # Store for internal ETA calculations and push to frontend
        self._step_times.setdefault(kind, []).append(seconds)
        payload: StepTimePayload = {"kind": kind, "seconds": seconds, "done": done, "total": total}
        self._emit_js("registerStepTime", payload, batched=True)

    def ask_regenerate(self, filename: str, callback, mode: str = "resume"):
        self._regenerate_callback = callback
        self._emit_js("askRegenerate", {"filename": filename, "mode": mode}, batched=False)

    def ask_new_api_key(self, callback):
        self._new_key_callback = callback
        self._emit_js("askNewKey", {}, batched=False)

    def answer_regenerate(self, regenerate: bool):
        cb = getattr(self, "_regenerate_callback", None)
        if cb:
            cb({"regenerate": regenerate})
            self._regenerate_callback = None

    def answer_new_key(self, key: str):
        cb = getattr(self, "_new_key_callback", None)
        if cb:
            cb({"key": key})
            self._new_key_callback = None

    # --- Tkinter-compat stubs (for popup centering in pipeline.py) ---

    def winfo_rootx(self): return 100
    def winfo_rooty(self): return 100
    def winfo_width(self): return 850
    def winfo_height(self): return 800

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
        configure_logging()
        self._logger = get_logger("el_sbobinator.webview")

    def set_window(self, window: webview.Window):
        self._window = window
        self._adapter.window = window

    def show_window(self):
        """Called by React once it's mounted, shows the window instantly."""
        if self._window:
            self._window.show()

    # ---- Settings ----

    def load_settings(self) -> dict:
        """Load saved config from disk."""
        try:
            cfg = load_config()
            return {
                "api_key": cfg.get("api_key", ""),
                "fallback_keys": cfg.get("fallback_keys", []),
            }
        except Exception:
            return {"api_key": "", "fallback_keys": []}

    def save_settings(self, api_key: str, fallback_keys: list[str]) -> dict:
        """Save config to disk."""
        try:
            save_config(api_key, fallback_keys=fallback_keys)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---- File Selection ----

    def ask_files(self) -> list[BridgeFileItem]:
        """Open native file dialog and return file info."""
        if not self._window:
            return []
        try:
            file_paths = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=True,
                file_types=(
                    'Audio (*.mp3;*.m4a;*.wav;*.ogg;*.flac;*.aac)',
                    'Video (*.mp4;*.mkv;*.webm)',
                    'All files (*.*)',
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
        result: list[BridgeFileItem] = []
        for path in file_paths:
            try:
                size = os.path.getsize(path)
            except Exception:
                size = 0
            try:
                dur_val, _reason = probe_media_duration(path)
                duration = dur_val if dur_val else 0
            except Exception:
                duration = 0
            result.append({
                "path": path,
                "name": os.path.basename(path),
                "size": size,
                "duration": duration,
            })
        return result

    def ask_media_file(self) -> BridgeFileItem | None:
        """Open a native file dialog for a single media file."""
        if not self._window:
            return None
        try:
            file_paths = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=(
                    'Audio (*.mp3;*.m4a;*.wav;*.ogg;*.flac;*.aac)',
                    'Video (*.mp4;*.mkv;*.webm)',
                    'All files (*.*)',
                ),
            )
        except Exception:
            file_paths = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
            )
        if not file_paths:
            return None
        path = file_paths[0]
        try:
            size = os.path.getsize(path)
        except Exception:
            size = 0
        try:
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

    def check_path_exists(self, path: str) -> dict:
        """Check whether a persisted source path still exists on disk."""
        normalized_path = str(path or "").strip()
        return {
            "ok": True,
            "exists": bool(normalized_path and os.path.exists(normalized_path)),
        }

    # ---- Processing ----

    def start_processing(self, files: list[BridgeFileItem], api_key: str, resume_session: bool = True) -> dict:
        """Start the pipeline in a background thread."""
        if not files or not api_key:
            return {"ok": False, "error": "File o API key mancanti"}
        if self._adapter.is_running:
            return {"ok": False, "error": "Elaborazione già in corso"}

        # Validate API key
        try:
            from google import genai
            test_client = genai.Client(api_key=api_key)
            test_client.models.get(model=DEFAULT_MODEL)
        except Exception as e:
            return {"ok": False, "error": f"API Key non valida: {e}"}

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
            try:
                for idx, file_info in enumerate(files):
                    if self._cancel_event.is_set():
                        break
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
                        continue

                    self._push_console(f"\n{'='*50}")
                    self._push_console(f"  File {idx+1}/{len(files)}: {os.path.basename(file_path)}")
                    self._push_console(f"{'='*50}")
                    current_payload: SetCurrentFilePayload = {
                        "index": idx,
                        "id": file_info.get("id", ""),
                        "total": len(files),
                    }
                    self._adapter.emit("setCurrentFile", current_payload, batched=False)

                    esegui_sbobinatura(file_path, active_api_key, self._adapter, resume_session=resume_session)
                    if self._adapter.effective_api_key:
                        active_api_key = self._adapter.effective_api_key

                    if self._cancel_event.is_set() or self._adapter.last_run_status == "cancelled":
                        break

                    if self._adapter.last_run_status == "completed":
                        if self._adapter.last_output_html and os.path.exists(self._adapter.last_output_html):
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
                            "error": self._adapter.last_run_error or "Elaborazione non completata.",
                        }
                        self._adapter.emit("fileFailed", payload, batched=False)
                        failed_count += 1
            except Exception as e:
                self._push_console(f"[!] Errore fatale: {e}")
            finally:
                self._adapter.is_running = False
                payload: ProcessDonePayload = {
                    "cancelled": bool(self._cancel_event.is_set()),
                    "completed": completed_count,
                    "failed": failed_count,
                    "total": len(files),
                }
                self._adapter.emit("processDone", payload, batched=False)

        self._processing_thread = threading.Thread(target=_run, daemon=True)
        self._processing_thread.start()
        return {"ok": True}

    def answer_regenerate(self, regenerate: bool) -> dict:
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
        return {"ok": True}

    def validate_environment(self, api_key: str | None = None, check_api_key: bool = False) -> dict:
        """Run an explicit environment validation without starting a full transcription."""
        try:
            result: ValidationResult = validate_environment(api_key=api_key, validate_api_key=bool(check_api_key))
            return {"ok": True, "result": result}
        except Exception as e:
            self._logger.exception("Validazione ambiente fallita.")
            return {"ok": False, "error": str(e)}

    def open_file(self, path: str) -> dict:
        """Open a file/folder with the system default handler."""
        try:
            open_path_with_default_app(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def read_html_content(self, path: str) -> dict:
        """Legge ed estrae il contenuto di un file HTML per l'anteprima."""
        try:
            content = read_html_file_content(path)
            return {"ok": True, "content": content}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_html_content(self, path: str, content: str) -> dict:
        """Aggiorna solo il contenuto del <body>, preservando head, stile e CSP dell'export originale."""
        try:
            save_html_body_content(path, content)
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
                file_types=('Word Document (*.doc)', 'All files (*.*)')
            )
            if not save_path or len(save_path) == 0:
                return {"ok": False, "error": "Annullato dall'utente"}

            path = export_doc_html(save_path[0], docx_html)
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
                title=title,
                message=message,
                app_name="El Sbobinator",
                timeout=5
            )
            return {"ok": True}
        except Exception as e:
            # Fallback a legacy OS script
            if sys.platform == "darwin":
                import subprocess
                subprocess.Popen(['osascript', '-e', f'display notification "{message}" with title "{title}"'])
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
            self._api._push_console(text.rstrip())

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
    if getattr(sys, 'frozen', False):
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


def main():
    api = ElSbobinatorApi()

    # Intercept stdout/stderr to forward to React console
    sys.stdout = _ConsoleTee(sys.__stdout__, api)
    sys.stderr = _ConsoleTee(sys.__stderr__, api)

    dist_path = get_dist_path()

    # Storage path for WebView2 profile cache (avoids re-init freeze)
    storage_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "El Sbobinator", "webview_cache"
    )
    os.makedirs(storage_dir, exist_ok=True)

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
        hidden=True, # Start hidden to prevent click-freezing during WebView2 init
    )
    api.set_window(window)
    
    webview.start(
        private_mode=False,
        storage_path=storage_dir,
    )


if __name__ == "__main__":
    main()
