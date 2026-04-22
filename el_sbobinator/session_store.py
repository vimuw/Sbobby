"""
Session and autosave helpers for El Sbobinator.

The pipeline still owns the orchestration, but session persistence lives here
so resume/autosave behavior is easier to reason about and test in isolation.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import dataclass

from el_sbobinator.pipeline.pipeline_settings import build_default_pipeline_settings
from el_sbobinator.shared import (
    SESSION_ROOT,
    SESSION_SCHEMA_VERSION,
    _atomic_write_json,
    _file_fingerprint,
    _load_json,
    _now_iso,
    _safe_mkdir,
    _session_dir_for_file,
)


@dataclass(frozen=True)
class SessionPaths:
    session_dir: str
    session_path: str
    phase1_chunks_dir: str
    phase2_revised_dir: str
    macro_path: str


def resolve_session_paths(
    input_path: str, session_dir_hint: str | None = None
) -> SessionPaths:
    try:
        _safe_mkdir(SESSION_ROOT)
    except Exception:
        pass

    try:
        session_dir = (
            os.path.abspath(session_dir_hint)
            if session_dir_hint
            else _session_dir_for_file(input_path)
        )
    except Exception:
        session_dir = os.path.join(
            tempfile.gettempdir(), "el_sbobinator_session_fallback"
        )

    return SessionPaths(
        session_dir=session_dir,
        session_path=os.path.join(session_dir, "session.json"),
        phase1_chunks_dir=os.path.join(session_dir, "phase1_chunks"),
        phase2_revised_dir=os.path.join(session_dir, "phase2_revised"),
        macro_path=os.path.join(session_dir, "phase2_macro_blocks.json"),
    )


def ensure_session_dirs(paths: SessionPaths) -> None:
    _safe_mkdir(paths.session_dir)
    _safe_mkdir(paths.phase1_chunks_dir)
    _safe_mkdir(paths.phase2_revised_dir)


def reset_session_dirs(paths: SessionPaths) -> None:
    if os.path.exists(paths.session_dir):
        import shutil

        shutil.rmtree(paths.session_dir, ignore_errors=True)
    ensure_session_dirs(paths)


def load_session(session_path: str):
    return _load_json(session_path)


def save_session(session_path: str, session: dict) -> None:
    session["updated_at"] = _now_iso()
    _atomic_write_json(session_path, session)


def _update_session(session: dict, updates: dict) -> dict:
    """Return a deep copy of the session before applying updates."""
    snapshot = copy.deepcopy(session)
    session.update(updates)
    return snapshot


def new_session(input_path: str, settings: dict | None = None) -> dict:
    try:
        fp = _file_fingerprint(input_path)
    except Exception:
        fp = {"path": os.path.abspath(input_path), "size": None, "mtime": None}

    return {
        "schema_version": SESSION_SCHEMA_VERSION,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "stage": "phase1",
        "input": fp,
        "settings": settings or build_default_pipeline_settings(),
        "phase1": {"next_start_sec": 0, "chunks_done": 0, "memoria_precedente": ""},
        "phase2": {"macro_total": 0, "revised_done": 0},
        "outputs": {},
        "last_error": None,
    }


def clone_session_settings(session: dict) -> dict:
    try:
        return json.loads(json.dumps(session.get("settings", {}), ensure_ascii=False))
    except Exception:
        return dict(session.get("settings", {}))
