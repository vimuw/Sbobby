"""
Session/bootstrap helpers for the main pipeline.

These helpers isolate autosave, resume, pre-conversion and per-phase metadata so
the core generation loop can stay focused on the Gemini workflow.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from el_sbobinator.audio_service import preconvert_media_to_mp3
from el_sbobinator.pipeline_settings import PipelineSettings, load_and_sanitize_settings
from el_sbobinator.session_store import (
    clone_session_settings,
    ensure_session_dirs,
    load_session as load_saved_session,
    new_session,
    reset_session_dirs,
    resolve_session_paths,
    save_session as save_session_data,
)


CHUNK_MD_RE = re.compile(r"^chunk_(\d{3})_(\d+)_(\d+)\.md$", re.IGNORECASE)
ChunkEntry = tuple[int, int, int, str]


@dataclass
class PipelineSessionContext:
    input_path: str
    session_dir_hint: str | None
    resume_session: bool
    session_paths: object
    session: dict
    settings: PipelineSettings
    settings_changed: bool

    @property
    def session_dir(self) -> str:
        return self.session_paths.session_dir

    @property
    def session_path(self) -> str:
        return self.session_paths.session_path

    @property
    def phase1_chunks_dir(self) -> str:
        return self.session_paths.phase1_chunks_dir

    @property
    def phase2_revised_dir(self) -> str:
        return self.session_paths.phase2_revised_dir

    @property
    def boundary_dir(self) -> str:
        return self.session_paths.boundary_dir

    @property
    def macro_path(self) -> str:
        return self.session_paths.macro_path

    def save(self) -> bool:
        try:
            save_session_data(self.session_path, self.session)
            return True
        except Exception as exc:
            print(f"   [!] Autosave sessione fallito: {exc}")
            return False


@dataclass(frozen=True)
class Phase1RestoreState:
    existing_chunks: list[ChunkEntry]
    start_sec: int
    testo_completo_sbobina: str
    memoria_precedente: str


def read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def list_phase1_chunks(phase1_chunks_dir: str) -> list[ChunkEntry]:
    items: list[ChunkEntry] = []
    try:
        for name in os.listdir(phase1_chunks_dir):
            match = CHUNK_MD_RE.match(name)
            if not match:
                continue
            idx = int(match.group(1))
            start_sec = int(match.group(2))
            end_sec = int(match.group(3))
            items.append((idx, start_sec, end_sec, os.path.join(phase1_chunks_dir, name)))
    except Exception:
        return []
    return sorted(items, key=lambda item: (item[0], item[1], item[2]))


def load_phase1_text(phase1_chunks_dir: str) -> str:
    parts: list[str] = []
    for _, _, _, path in list_phase1_chunks(phase1_chunks_dir):
        try:
            text = read_text_file(path).strip()
        except Exception:
            continue
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()


def initialize_session_context(
    input_path: str,
    session_dir_hint: str | None = None,
    resume_session: bool = False,
) -> PipelineSessionContext:
    session_paths = resolve_session_paths(input_path, session_dir_hint=session_dir_hint)

    if not resume_session and os.path.exists(session_paths.session_dir):
        try:
            reset_session_dirs(session_paths)
        except Exception:
            pass
    else:
        try:
            ensure_session_dirs(session_paths)
        except Exception:
            pass

    session = None
    if resume_session and os.path.exists(session_paths.session_path):
        try:
            session = load_saved_session(session_paths.session_path)
        except Exception:
            session = None

    if session is None:
        session = new_session(input_path)
        try:
            save_session_data(session_paths.session_path, session)
        except Exception:
            pass
    else:
        session.setdefault("schema_version", session.get("schema_version", 1))
        session.setdefault("stage", "phase1")
        session.setdefault("phase1", {})
        session.setdefault("phase2", {})
        session.setdefault("boundary", {})
        session.setdefault("outputs", {})

    settings, settings_changed = load_and_sanitize_settings(session)
    context = PipelineSessionContext(
        input_path=input_path,
        session_dir_hint=session_dir_hint,
        resume_session=resume_session,
        session_paths=session_paths,
        session=session,
        settings=settings,
        settings_changed=settings_changed,
    )
    if settings_changed:
        context.save()
    return context


def normalize_stage(session: dict) -> str:
    stage = str(session.get("stage", "phase1")).strip().lower()
    if stage not in ("phase1", "phase2", "boundary", "done"):
        stage = "phase1"
        session["stage"] = "phase1"
    return stage


def phase1_has_progress(session: dict, stage: str, existing_chunks: list[ChunkEntry]) -> bool:
    phase1_state = session.get("phase1", {}) if isinstance(session.get("phase1"), dict) else {}
    outputs_state = session.get("outputs", {}) if isinstance(session.get("outputs"), dict) else {}
    return (
        stage != "phase1"
        or bool(existing_chunks)
        or int(phase1_state.get("chunks_done", 0) or 0) > 0
        or int(phase1_state.get("next_start_sec", 0) or 0) > 0
        or bool(str(outputs_state.get("html") or "").strip())
        or bool(session.get("last_error"))
    )


def reset_for_regeneration(context: PipelineSessionContext) -> None:
    try:
        reset_session_dirs(context.session_paths)
    except Exception:
        pass
    context.session = new_session(
        context.input_path,
        settings=clone_session_settings(context.session),
    )
    context.save()


def persist_phase1_metadata(context: PipelineSessionContext, duration_seconds: float, step_seconds: int) -> None:
    context.session.setdefault("phase1", {})
    context.session["phase1"]["duration_seconds"] = float(duration_seconds)
    context.session["phase1"]["step_seconds"] = int(step_seconds)
    context.save()


def restore_phase1_progress(context: PipelineSessionContext, stage: str, step_seconds: int) -> Phase1RestoreState:
    session = context.session
    existing_chunks = list_phase1_chunks(context.phase1_chunks_dir)
    start_sec = int(session.get("phase1", {}).get("next_start_sec", 0) or 0)

    if existing_chunks:
        try:
            last_start = max(start for _, start, _, _ in existing_chunks)
            start_sec = max(start_sec, int(last_start + step_seconds))
        except Exception:
            pass
        testo_completo_sbobina = load_phase1_text(context.phase1_chunks_dir)
        try:
            _, _, _, last_path = existing_chunks[-1]
            memoria_precedente = read_text_file(last_path).strip()[-1000:]
        except Exception:
            memoria_precedente = testo_completo_sbobina[-1000:]
    elif stage != "phase1":
        testo_completo_sbobina = load_phase1_text(context.phase1_chunks_dir)
        memoria_precedente = testo_completo_sbobina[-1000:]
    else:
        testo_completo_sbobina = ""
        memoria_precedente = str(session.get("phase1", {}).get("memoria_precedente", "") or "")

    return Phase1RestoreState(
        existing_chunks=existing_chunks,
        start_sec=start_sec,
        testo_completo_sbobina=testo_completo_sbobina,
        memoria_precedente=memoria_precedente,
    )


def ensure_preconverted_audio(
    context: PipelineSessionContext,
    input_path: str,
    stage: str,
    ffmpeg_exe: str,
    cancel_event,
    cancelled,
    phase_callback,
) -> tuple[bool, str | None]:
    preconv_enabled = bool(context.settings.preconvert_audio)
    preconv_path = os.path.join(context.session_dir, "el_sbobinator_preconverted_mono16k.mp3")
    if not preconv_enabled or stage != "phase1":
        return preconv_enabled, None

    try:
        if os.path.exists(preconv_path) and os.path.getsize(preconv_path) > 1024:
            print("[*] Pre-conversione: file gia' presente. Riutilizzo.")
            return preconv_enabled, preconv_path
    except Exception:
        pass

    phase_callback("Fase 0/3: pre-conversione audio")
    print("[*] Pre-conversione unica dell'audio (mono, 16kHz) in corso...")
    ok, err = preconvert_media_to_mp3(
        input_path=input_path,
        output_path=preconv_path,
        bitrate=str(context.settings.audio_bitrate or "48k"),
        ffmpeg_exe=ffmpeg_exe,
        stop_event=cancel_event,
    )
    if not ok:
        if str(err or "").strip().lower() == "cancelled" or cancelled():
            print("   [*] Operazione annullata dall'utente.")
            return preconv_enabled, None
        print("[!] Pre-conversione fallita. Continuo senza pre-conversione.")
        if err:
            print(err)
        return False, None

    try:
        if os.path.exists(preconv_path) and os.path.getsize(preconv_path) > 1024:
            print("[*] Pre-conversione completata.")
            context.session.setdefault("phase1", {})
            context.session["phase1"]["preconverted_path"] = preconv_path
            context.session["phase1"]["preconverted_done"] = True
            context.save()
            return preconv_enabled, preconv_path
    except Exception:
        pass
    return False, None


def record_step_metric(
    session: dict | None,
    kind: str,
    seconds: float,
    done: int | None = None,
    total: int | None = None,
) -> None:
    if not isinstance(session, dict):
        return

    metrics = session.setdefault("metrics", {})
    entry = metrics.setdefault(
        str(kind or "unknown"),
        {
            "count": 0,
            "elapsed_seconds": 0.0,
            "last_seconds": 0.0,
            "done": 0,
            "total": 0,
        },
    )

    try:
        value = max(0.0, float(seconds))
    except Exception:
        value = 0.0

    if value > 0:
        entry["count"] = int(entry.get("count", 0) or 0) + 1
        entry["elapsed_seconds"] = float(entry.get("elapsed_seconds", 0.0) or 0.0) + value
        entry["last_seconds"] = value
        entry["avg_seconds"] = entry["elapsed_seconds"] / max(1, entry["count"])

    if done is not None:
        entry["done"] = int(done)
    if total is not None:
        entry["total"] = int(total)
