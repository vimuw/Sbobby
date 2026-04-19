"""
Shared utilities/constants for El Sbobinator.

Questo modulo raccoglie configurazione, sessioni/autosave, prompt e helper di I/O
che vengono usati sia dalla pipeline che dalla UI.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
from datetime import datetime

from el_sbobinator.model_registry import DEFAULT_FALLBACK_MODELS, DEFAULT_MODEL
from el_sbobinator.services.config_service import USER_HOME

SESSION_CLEANUP_MAX_AGE_DAYS = 14
PRECONVERTED_AUDIO_FINAL = "el_sbobinator_preconverted_mono16k.mp3"
PRECONVERTED_AUDIO_PARTIAL = "el_sbobinator_preconverted_mono16k.partial.mp3"

__all__ = [
    "DEFAULT_FALLBACK_MODELS",
    "DEFAULT_MODEL",
    "PRECONVERTED_AUDIO_FINAL",
    "PRECONVERTED_AUDIO_PARTIAL",
    "SESSION_CLEANUP_MAX_AGE_DAYS",
    "SESSION_ROOT",
    "SESSION_SCHEMA_VERSION",
    "_atomic_write_json",
    "_atomic_write_text",
    "_file_fingerprint",
    "_load_json",
    "_now_iso",
    "_safe_mkdir",
    "_session_dir_for_file",
    "_session_id_for_file",
    "cleanup_orphan_sessions",
    "cleanup_orphan_temp_chunks",
    "get_session_storage_info",
    "invalidate_session_storage_cache",
]

_storage_info_cache: dict | None = None
_storage_info_cache_time: float = 0.0
_STORAGE_INFO_TTL: float = 30.0
_storage_info_lock = threading.Lock()
_storage_info_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="storage_info"
)


def cleanup_orphan_temp_chunks(max_age_seconds: int = 12 * 3600) -> int:
    """
    Best-effort cleanup of temp chunk files left behind by crashes/forced closes.
    Only touches files matching our own prefix in the OS temp directory.
    """
    removed = 0
    try:
        tmpdir = tempfile.gettempdir()
        now = time.time()
        for name in os.listdir(tmpdir):
            low = name.lower()
            if not low.startswith("el_sbobinator_temp_"):
                continue
            if not (
                low.endswith(".mp3") or low.endswith(".wav") or low.endswith(".m4a")
            ):
                continue
            path = os.path.join(tmpdir, name)
            try:
                age = now - float(os.path.getmtime(path))
                if age < max(0, int(max_age_seconds)):
                    continue
                os.remove(path)
                removed += 1
            except Exception:
                pass
    except Exception:
        pass
    return removed


# ==========================================
# SESSIONI (AUTOSAVE / RIPRESA)
# ==========================================
SESSION_SCHEMA_VERSION = 1
SESSION_ROOT = os.path.join(USER_HOME, ".el_sbobinator_sessions")


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_mkdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _atomic_write_text(path: str, text: str) -> None:
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp_path, path)


def _atomic_write_json(path: str, data) -> None:
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _file_fingerprint(path: str) -> dict:
    abs_path = os.path.abspath(path)
    st = os.stat(abs_path)
    return {
        "path": abs_path,
        "size": int(getattr(st, "st_size", 0)),
        "mtime": float(getattr(st, "st_mtime", 0.0)),
    }


def _partial_file_hash(path: str, max_bytes: int = 65536) -> str:
    """
    Calcola SHA256 dei primi max_bytes del file.
    Usato per identificare file identici indipendentemente dal path.
    Leggere solo i primi 64KB è veloce anche per file multi-gigabyte.
    """
    try:
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            chunk = f.read(max_bytes)
            hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""


_session_id_cache: dict[tuple, str] = {}
_MAX_SESSION_CACHE_SIZE = 500  # LRU cap: at ~200 bytes per entry this stays well under 100 KB; prevents unbounded growth in long-running processes


def _session_id_for_file(path: str) -> str:
    """
    Genera ID sessione basato su: size + mtime + hash parziale contenuto.
    Rileva file spostati/ rinominati ma con stesso contenuto.
    """
    abs_path = os.path.abspath(path)
    st = os.stat(abs_path)
    size = int(getattr(st, "st_size", 0))
    mtime = float(getattr(st, "st_mtime", 0.0))

    cache_key = (abs_path, size, mtime)
    _cached = _session_id_cache.get(cache_key)
    if _cached is not None:
        return _cached

    # LRU eviction: remove oldest entry if at capacity
    if len(_session_id_cache) >= _MAX_SESSION_CACHE_SIZE:
        _session_id_cache.pop(next(iter(_session_id_cache)))

    content_hash = _partial_file_hash(abs_path)
    blob = json.dumps(
        {
            "size": size,
            "mtime": mtime,
            "content_hash": content_hash,
        },
        sort_keys=True,
    ).encode("utf-8", errors="ignore")
    result = hashlib.sha256(blob).hexdigest()
    _session_id_cache[cache_key] = result
    return result


def _session_dir_for_file(path: str) -> str:
    return os.path.join(SESSION_ROOT, _session_id_for_file(path))


def _folder_size(path: str) -> int:
    """Recursively compute folder size in bytes. Best-effort: skips unreadable files."""
    total = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for fname in filenames:
                if fname == PRECONVERTED_AUDIO_PARTIAL:
                    continue
                try:
                    total += os.path.getsize(os.path.join(dirpath, fname))
                except Exception:
                    pass
    except Exception:
        pass
    return total


def _folder_newest_mtime(path: str) -> float:
    """
    Return the newest mtime of any file inside the folder (recursive).
    Falls back to the directory mtime itself if no files found.
    Cross-platform: on Windows, directory mtime is NOT updated when files inside
    change, so scanning file mtimes is necessary for correctness.
    """
    newest = 0.0
    try:
        for dirpath, _, filenames in os.walk(path):
            for fname in filenames:
                try:
                    mtime = os.path.getmtime(os.path.join(dirpath, fname))
                    if mtime > newest:
                        newest = mtime
                except Exception:
                    pass
        if newest == 0.0:
            try:
                newest = os.path.getmtime(path)
            except Exception:
                pass
    except Exception:
        pass
    return newest


def _compute_session_storage_info() -> dict:
    """
    Blocking FS traversal - call via get_session_storage_info() which caches
    the result and offloads the work to a background thread.
    """
    total_bytes = 0
    total_sessions = 0
    try:
        if not os.path.isdir(SESSION_ROOT):
            return {"total_bytes": 0, "total_sessions": 0}
        for name in os.listdir(SESSION_ROOT):
            session_dir = os.path.join(SESSION_ROOT, name)
            if not os.path.isdir(session_dir):
                continue
            total_sessions += 1
            total_bytes += _folder_size(session_dir)
    except Exception:
        pass
    return {"total_bytes": total_bytes, "total_sessions": total_sessions}


def get_session_storage_info() -> dict:
    """
    Return total size in bytes and count of session folders in SESSION_ROOT.
    Result is cached for _STORAGE_INFO_TTL seconds.  The FS traversal runs in
    a dedicated single-worker thread so the caller is never blocked for longer
    than the OS I/O takes (bounded by a 10-second timeout).
    """
    global _storage_info_cache, _storage_info_cache_time
    now = time.time()
    with _storage_info_lock:
        if (
            _storage_info_cache is not None
            and (now - _storage_info_cache_time) < _STORAGE_INFO_TTL
        ):
            return dict(_storage_info_cache)
    future = _storage_info_executor.submit(_compute_session_storage_info)
    try:
        result = future.result(timeout=10.0)
    except Exception:
        result = {"total_bytes": 0, "total_sessions": 0}
    with _storage_info_lock:
        _storage_info_cache = result
        _storage_info_cache_time = time.time()
    return dict(result)


def invalidate_session_storage_cache() -> None:
    """Bust the get_session_storage_info cache (call after deleting sessions)."""
    global _storage_info_cache, _storage_info_cache_time
    with _storage_info_lock:
        _storage_info_cache = None
        _storage_info_cache_time = 0.0


def cleanup_orphan_sessions(max_age_days: int = SESSION_CLEANUP_MAX_AGE_DAYS) -> dict:
    """
    Delete session folders in SESSION_ROOT whose newest file mtime is older
    than max_age_days days.  Returns a summary dict with keys:
      removed     - number of folders successfully deleted
      freed_bytes - total bytes freed
      errors      - number of folders that could not be deleted
    Best-effort: individual folder errors do not abort the whole sweep.
    """
    removed = 0
    freed_bytes = 0
    errors = 0
    try:
        if not os.path.isdir(SESSION_ROOT):
            return {"removed": 0, "freed_bytes": 0, "errors": 0}
        now = time.time()
        cutoff = now - max(1, int(max_age_days)) * 86400
        for name in os.listdir(SESSION_ROOT):
            session_dir = os.path.join(SESSION_ROOT, name)
            if not os.path.isdir(session_dir):
                continue
            try:
                newest_mtime = _folder_newest_mtime(session_dir)
                if newest_mtime >= cutoff:
                    continue
                size = _folder_size(session_dir)
                shutil.rmtree(session_dir)
                removed += 1
                freed_bytes += size
            except Exception:
                errors += 1
    except Exception:
        pass
    invalidate_session_storage_cache()
    return {"removed": removed, "freed_bytes": freed_bytes, "errors": errors}
