"""
PyWebView backend bridge for El Sbobinator.

This module contains ElSbobinatorApi, the JS-facing API class.
Supporting infrastructure lives in dedicated modules:
  - bridge_dispatcher.py  (_BridgeDispatcher)
  - pipeline_adapter.py   (_drain_dnd_paths, PipelineAdapter)
  - webview_entry.py      (_ConsoleTee, get_dist_path, has_webview2_runtime,
                           build_missing_webview2_html, main)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import ClassVar

import webview

# Lazy imports to avoid loading heavy deps at startup:
# from el_sbobinator.pipeline.pipeline import esegui_sbobinatura  -- imported lazily in start_processing
# from el_sbobinator.services.audio_service import probe_media_duration -- imported lazily in _build_file_descriptor
# from el_sbobinator.services.validation_service import validate_environment -- imported lazily in validate_environment
from el_sbobinator.bridge.bridge_types import (
    BridgeFileItem,
    FileDonePayload,
    FileFailedPayload,
    ProcessDonePayload,
    SetCurrentFilePayload,
    ValidationResult,
)
from el_sbobinator.core.media_server import LocalMediaServer
from el_sbobinator.core.model_registry import DEFAULT_FALLBACK_MODELS, MODEL_OPTIONS
from el_sbobinator.core.shared import (
    DEFAULT_MODEL,
    SESSION_CLEANUP_MAX_AGE_DAYS,
    _atomic_write_json,
    cleanup_orphan_sessions,
    cleanup_orphan_temp_chunks,
    get_session_storage_info,
)
from el_sbobinator.core.updater import (
    download_and_install_update as _download_and_install_update,
)
from el_sbobinator.pipeline.pipeline_adapter import PipelineAdapter, _drain_dnd_paths
from el_sbobinator.services.config_service import (
    THEME_PREF_FILE,
    get_desktop_dir,
    load_config,
    save_config,
)
from el_sbobinator.utils.file_ops import (
    extract_html_shell,
    open_path_with_default_app,
    save_html_body_content,
)
from el_sbobinator.utils.file_ops import (
    read_html_content as read_html_file_content,
)
from el_sbobinator.utils.logging_utils import configure_logging, get_logger

_ALLOWED_URL_PREFIXES: tuple[str, ...] = (
    "https://github.com/",
    "https://ko-fi.com/",
    "https://go.microsoft.com/fwlink/p/?LinkId=2124703",
    "https://aistudio.google.com/",
)


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
        self._sessions_cache: dict | None = None
        self._sessions_cache_ts: float = 0.0
        self._sessions_cache_gen: int = 0
        self._sessions_cache_lock = threading.Lock()
        configure_logging()
        self._logger = get_logger("el_sbobinator.webview")
        self._prewarm_thread = threading.Thread(
            target=self.get_completed_sessions,
            daemon=True,
            name="sessions-prewarm",
        )
        self._prewarm_thread.start()

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
                "has_protected_key": bool(cfg.get("has_protected_key")),
            }
        except Exception:
            return {
                "api_key": "",
                "fallback_keys": [],
                "preferred_model": DEFAULT_MODEL,
                "fallback_models": list(DEFAULT_FALLBACK_MODELS),
                "available_models": list(MODEL_OPTIONS),
                "has_protected_key": False,
            }

    def save_settings(
        self,
        api_key: str | None,
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

    def save_theme_preference(self, theme: str) -> None:
        """Persist theme preference to disk so the native window gets the right background on next launch."""
        try:
            if theme not in ("light", "dark"):
                return
            os.makedirs(os.path.dirname(THEME_PREF_FILE), exist_ok=True)
            with open(THEME_PREF_FILE, "w", encoding="utf-8") as fh:
                fh.write(theme)
        except Exception:
            pass

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

    def get_completed_sessions(self, limit: int = 20) -> dict:
        """Return the most recent completed sessions for the archive UI."""
        import json as _json

        with self._sessions_cache_lock:
            if (
                self._sessions_cache is not None
                and time.time() - self._sessions_cache_ts < 5.0
            ):
                cached = self._sessions_cache
                return {**cached, "sessions": list(cached["sessions"])}
            gen_at_start = self._sessions_cache_gen

        session_root = self._get_session_root()
        if not os.path.isdir(session_root):
            return {"ok": True, "sessions": []}
        try:
            candidates: list[tuple[str, dict, str]] = []
            for entry in os.scandir(session_root):
                if not entry.is_dir():
                    continue
                session_path = os.path.join(entry.path, "session.json")
                if not os.path.isfile(session_path):
                    continue
                try:
                    with open(session_path, encoding="utf-8") as fh:
                        data = _json.load(fh)
                    if data.get("stage") != "done":
                        continue
                    html_path = data.get("outputs", {}).get("html", "")
                    if not html_path:
                        continue
                    candidates.append((data.get("updated_at", ""), data, entry.path))
                except Exception:
                    continue
            candidates.sort(key=lambda c: c[0], reverse=True)
            sessions = []
            for _ts, data, session_dir in candidates[: max(0, int(limit))]:
                html_path = data.get("outputs", {}).get("html", "")
                # Migration: if the stored path (e.g. old Desktop copy) is gone,
                # look for the same filename inside the session dir and fix session.json.
                if html_path and not os.path.isfile(str(html_path)):
                    session_copy = os.path.join(
                        session_dir, os.path.basename(str(html_path))
                    )
                    if not os.path.isfile(session_copy):
                        continue  # HTML truly missing, no fallback candidate; skip
                    html_path = session_copy
                    try:
                        from el_sbobinator.core.shared import (
                            _atomic_write_json,
                        )

                        data["outputs"]["html"] = html_path
                        _atomic_write_json(
                            os.path.join(session_dir, "session.json"), data
                        )
                    except Exception:
                        pass
                input_path = data.get("input", {}).get("path", "")
                name = (
                    os.path.basename(input_path)
                    if input_path
                    else os.path.basename(str(html_path))
                )
                effective_model = data.get("settings", {}).get("effective_model", "")
                sessions.append(
                    {
                        "name": name,
                        "completed_at_iso": data.get("updated_at", ""),
                        "html_path": str(html_path),
                        "effective_model": effective_model,
                        "input_path": str(input_path),
                        "session_dir": str(session_dir),
                    }
                )
            result = {"ok": True, "sessions": sessions}
            with self._sessions_cache_lock:
                if self._sessions_cache_gen == gen_at_start:
                    self._sessions_cache = result
                    self._sessions_cache_ts = time.time()
            return {**result, "sessions": list(sessions)}
        except Exception as e:
            return {"ok": False, "error": str(e), "sessions": []}

    def delete_session(self, session_dir: str) -> dict:
        """Permanently delete a single session folder from disk."""
        import shutil

        try:
            session_root = self._get_session_root()
            abs_dir = os.path.abspath(session_dir)
            abs_root = os.path.abspath(session_root)
            if not abs_dir.startswith(abs_root + os.sep):
                return {"ok": False, "error": "Percorso non valido"}
            if not os.path.isdir(abs_dir):
                return {"ok": False, "error": "Cartella non trovata"}
            shutil.rmtree(abs_dir)
            with self._sessions_cache_lock:
                self._sessions_cache = None
                self._sessions_cache_gen += 1
            _prefix = abs_dir + os.sep
            _evict = [
                k
                for k, v in self._resolved_path_cache.items()
                if v == abs_dir or v.startswith(_prefix)
            ]
            for k in _evict:
                del self._resolved_path_cache[k]
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def update_session_input_path(self, session_dir: str, new_path: str) -> dict:
        """Persist a relinked audio path to session.json."""
        import json as _json

        try:
            session_root = self._get_session_root()
            abs_dir = os.path.abspath(session_dir)
            abs_root = os.path.abspath(session_root)
            if not abs_dir.startswith(abs_root + os.sep):
                return {"ok": False, "error": "Percorso non valido"}
            session_path = os.path.join(abs_dir, "session.json")
            if not os.path.isfile(session_path):
                return {"ok": False, "error": "session.json non trovato"}
            with open(session_path, encoding="utf-8") as fh:
                data = _json.load(fh)
            if not isinstance(data, dict):
                return {"ok": False, "error": "session.json non valido"}
            norm_path = str(new_path or "").strip()
            if not norm_path:
                return {"ok": False, "error": "Percorso vuoto"}
            if not isinstance(data.get("input"), dict):
                data["input"] = {}
            data["input"]["path"] = norm_path
            data["input"]["name"] = os.path.basename(norm_path)
            try:
                data["input"]["size"] = os.path.getsize(norm_path)
            except Exception:
                pass
            _atomic_write_json(session_path, data)
            with self._sessions_cache_lock:
                self._sessions_cache = None
                self._sessions_cache_gen += 1
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def cleanup_old_sessions(
        self, max_age_days: int = SESSION_CLEANUP_MAX_AGE_DAYS
    ) -> dict:
        """Delete session folders older than max_age_days days."""
        try:
            result = cleanup_orphan_sessions(max(1, int(max_age_days)))
            if result["removed"] > 0:
                with self._sessions_cache_lock:
                    self._sessions_cache = None
                    self._sessions_cache_gen += 1
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

    def open_session_folder(self) -> dict:
        """Open the session storage folder in the system file manager."""
        import subprocess
        import sys

        try:
            session_root = self._get_session_root()
            os.makedirs(session_root, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(session_root)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", session_root])
            else:
                subprocess.Popen(["xdg-open", session_root])
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---- File Selection ----

    @staticmethod
    def _build_file_descriptor(path: str) -> BridgeFileItem:
        try:
            size = os.path.getsize(path)
        except Exception:
            size = 0
        try:
            from el_sbobinator.services.audio_service import probe_media_duration

            dur_val, _reason = probe_media_duration(path)
            duration = dur_val if dur_val else 0
        except Exception:
            duration = 0
        return {
            "id": path,
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
            [str(p) for p in file_paths]
            if isinstance(file_paths, list | tuple)
            else [str(file_paths)]
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
        selected_path = str(
            file_paths[0] if isinstance(file_paths, list | tuple) else file_paths
        )
        return self._build_file_descriptor(selected_path)

    def check_path_exists(self, path: str) -> dict:
        """Check whether a persisted source path still exists on disk."""
        normalized_path = str(path or "").strip()
        return {
            "ok": True,
            "exists": bool(normalized_path and os.path.exists(normalized_path)),
        }

    _ALLOWED_DROP_EXTS: ClassVar[set[str]] = {
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
        for _basename, fullpath in _drain_dnd_paths(name_set):
            ext = os.path.splitext(fullpath)[1].lower()
            if ext in self._ALLOWED_DROP_EXTS and os.path.isfile(fullpath):
                descriptors.append(self._build_file_descriptor(fullpath))
        if descriptors:
            self._adapter.emit("filesDropped", descriptors, batched=False)
        return {"ok": True}

    # ---- Processing ----

    def start_processing(
        self,
        files: list[BridgeFileItem],
        api_key: str,
        resume_session: bool = True,
        preferred_model: str | None = None,
        fallback_models: list[str] | None = None,
    ) -> dict:
        """Start the pipeline in a background thread."""
        if not files or not api_key:
            return {"ok": False, "error": "File o API key mancanti"}
        if self._adapter.is_running:
            return {"ok": False, "error": "Elaborazione già in corso"}

        # Save config (including model so the pipeline always uses what's selected in the UI)
        try:
            save_config(
                api_key,
                preferred_model=preferred_model or None,
                fallback_models=fallback_models
                if isinstance(fallback_models, list)
                else None,
            )
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
            from el_sbobinator.pipeline.pipeline import esegui_sbobinatura

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
                        ff_payload: FileFailedPayload = {
                            "index": idx,
                            "id": file_info.get("id", ""),
                            "error": "File non trovato.",
                        }
                        self._adapter.emit("fileFailed", ff_payload, batched=False)
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
                    file_resume_session = (
                        bool(file_info.get("resume_session"))
                        if "resume_session" in file_info
                        else resume_session
                    )

                    esegui_sbobinatura(
                        file_path,
                        active_api_key,
                        self._adapter,
                        resume_session=file_resume_session,
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
                            fd_payload: FileDonePayload = {
                                "index": idx,
                                "id": file_info.get("id", ""),
                                "output_html": self._adapter.last_output_html,
                                "output_dir": self._adapter.last_output_dir or "",
                                "primary_model": self._adapter.last_primary_model or "",
                                "effective_model": self._adapter.last_effective_model
                                or "",
                            }
                            self._adapter.emit("fileDone", fd_payload, batched=False)
                            completed_count += 1
                        else:
                            ff_payload2: FileFailedPayload = {
                                "index": idx,
                                "id": file_info.get("id", ""),
                                "error": "Output HTML non generato.",
                            }
                            self._adapter.emit("fileFailed", ff_payload2, batched=False)
                            failed_count += 1
                    else:
                        ff_payload3: FileFailedPayload = {
                            "index": idx,
                            "id": file_info.get("id", ""),
                            "error": self._adapter.last_run_error
                            or "Elaborazione non completata.",
                        }
                        self._adapter.emit("fileFailed", ff_payload3, batched=False)
                        failed_count += 1
                    current_index = None
                    current_file_id = ""
            except Exception as e:
                if current_index is not None:
                    ff_payload4: FileFailedPayload = {
                        "index": current_index,
                        "id": current_file_id,
                        "error": str(e) or "Errore fatale.",
                    }
                    self._adapter.set_run_result("failed", str(e))
                    self._adapter.emit("fileFailed", ff_payload4, batched=False)
                    failed_count += 1
                self._push_console(f"[!] Errore fatale: {e}")
            finally:
                self._adapter.is_running = False
                with self._sessions_cache_lock:
                    self._sessions_cache = None
                    self._sessions_cache_gen += 1
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
            from el_sbobinator.services.validation_service import (
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
        else:
            self._resolved_path_cache[requested_real_path] = real_path
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
        from el_sbobinator.core.shared import SESSION_ROOT

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
        from el_sbobinator.core.shared import _atomic_write_json
        from el_sbobinator.pipeline.pipeline_session import read_text_file
        from el_sbobinator.services.config_service import safe_output_basename
        from el_sbobinator.services.export_service import export_final_html_document

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
                    with open(session_path, encoding="utf-8") as fh:
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
                        continue
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

    def show_notification(self, title: str, message: str) -> dict:
        """Mostra una notifica toast nativa di sistema tramite plyer."""
        try:
            from plyer import notification

            # On windows, notify requires an absolute path to a .ico file if we want an icon.
            # We'll omit the app_icon for simplicity and cross-platform compatibility.
            notification.notify(  # type: ignore[operator]
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

    def download_and_install_update(self, version: str) -> dict:
        """Download the correct installer for this OS, launch it, then quit the app."""
        return _download_and_install_update(version)

    # ---- Console push helper ----

    def _push_console(self, msg: str):
        self._adapter.emit("appendConsole", msg, batched=False)


# ---------------------------------------------------------------------------
# Re-exports for backward compatibility
# ---------------------------------------------------------------------------

from el_sbobinator.webview_entry import main

if __name__ == "__main__":
    main()
