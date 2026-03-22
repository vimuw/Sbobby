"""
Settings loading + validation for the pipeline.

Goal: make session.json resilient to manual edits / old versions / weird values,
without changing normal defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from el_sbobinator.shared import DEFAULT_MODEL


@dataclass(frozen=True)
class PipelineSettings:
    model: str
    chunk_minutes: int
    overlap_seconds: int
    macro_char_limit: int
    preconvert_audio: bool
    audio_bitrate: str
    prefetch_next_chunk: bool
    inline_audio_max_mb: float

    @property
    def chunk_seconds(self) -> int:
        return int(self.chunk_minutes) * 60

    @property
    def step_seconds(self) -> int:
        # Must be >= 1 to keep range() sane.
        return max(1, int(self.chunk_seconds) - int(self.overlap_seconds))

    @property
    def inline_max_bytes(self) -> int | None:
        try:
            mb = float(self.inline_audio_max_mb)
        except Exception:
            mb = 0.0
        if mb <= 0:
            return None
        return int(mb * 1024 * 1024)


def _as_bool(v: Any, default: bool) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "y", "on"):
            return True
        if s in ("0", "false", "no", "n", "off"):
            return False
    return bool(default)


def _as_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return int(default)


def _as_float(v: Any, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def load_and_sanitize_settings(session: Dict[str, Any]) -> Tuple[PipelineSettings, bool]:
    """
    Returns (settings, changed).
    - Ensures session['settings'] exists.
    - Clamps unsafe values.
    - Keeps defaults identical to the current app behavior.
    """
    changed = False
    if not isinstance(session.get("settings"), dict):
        session["settings"] = {}
        changed = True
    s = session["settings"]

    # Defaults
    model = str(s.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    chunk_minutes = _as_int(s.get("chunk_minutes", 15), 15)
    overlap_seconds = _as_int(s.get("overlap_seconds", 30), 30)
    macro_char_limit = _as_int(s.get("macro_char_limit", 22000), 22000)
    preconvert_audio = _as_bool(s.get("preconvert_audio", True), True)
    prefetch_next_chunk = _as_bool(s.get("prefetch_next_chunk", True), True)
    inline_audio_max_mb = _as_float(s.get("inline_audio_max_mb", 6), 6.0)

    audio = s.get("audio")
    if not isinstance(audio, dict):
        audio = {}
        s["audio"] = audio
        changed = True
    audio_bitrate = str(audio.get("bitrate") or "48k").strip() or "48k"

    # Clamp / sanitize
    if chunk_minutes < 1:
        chunk_minutes = 15
    if chunk_minutes > 180:
        chunk_minutes = 180

    max_overlap = max(0, (chunk_minutes * 60) - 1)
    if overlap_seconds < 0:
        overlap_seconds = 0
    if overlap_seconds > max_overlap:
        overlap_seconds = max_overlap

    if macro_char_limit < 8000:
        macro_char_limit = 8000
    if macro_char_limit > 90000:
        macro_char_limit = 90000

    if inline_audio_max_mb < 0:
        inline_audio_max_mb = 0.0
    if inline_audio_max_mb > 25:
        inline_audio_max_mb = 25.0

    # Persist sanitized values back (so resume uses the same effective config)
    def _set_if_diff(key: str, value: Any):
        nonlocal changed
        if s.get(key) != value:
            s[key] = value
            changed = True

    _set_if_diff("model", model)
    _set_if_diff("chunk_minutes", int(chunk_minutes))
    _set_if_diff("overlap_seconds", int(overlap_seconds))
    _set_if_diff("macro_char_limit", int(macro_char_limit))
    _set_if_diff("preconvert_audio", bool(preconvert_audio))
    _set_if_diff("prefetch_next_chunk", bool(prefetch_next_chunk))
    _set_if_diff("inline_audio_max_mb", float(inline_audio_max_mb))

    if audio.get("bitrate") != audio_bitrate:
        audio["bitrate"] = audio_bitrate
        changed = True

    settings = PipelineSettings(
        model=model,
        chunk_minutes=int(chunk_minutes),
        overlap_seconds=int(overlap_seconds),
        macro_char_limit=int(macro_char_limit),
        preconvert_audio=bool(preconvert_audio),
        audio_bitrate=audio_bitrate,
        prefetch_next_chunk=bool(prefetch_next_chunk),
        inline_audio_max_mb=float(inline_audio_max_mb),
    )
    return settings, changed

