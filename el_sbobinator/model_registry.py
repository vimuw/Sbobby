"""
Supported Gemini model registry and helpers.

This keeps model allowlists, defaults and small sanitization helpers in one
place so config/session/UI logic stay aligned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SUPPORTED_MODELS: tuple[str, ...] = (
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
)

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_FALLBACK_MODELS: tuple[str, ...] = (
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
)

MODEL_OPTIONS: tuple[dict[str, str | int], ...] = (
    {
        "id": "gemini-3-flash-preview",
        "label": "Gemini 3 Flash (Preview)",
        "summary": "Qualita superiore ma traffico elevato tra le 15:00 e le 20:00: possibili errori 503 e rallentamenti significativi.",
        "default_chunk_minutes": 15,
    },
    {
        "id": "gemini-2.5-flash",
        "label": "Gemini 2.5 Flash",
        "summary": "Primario consigliato: ottimo equilibrio qualita/velocita, stabile e ampiamente testato.",
        "default_chunk_minutes": 15,
    },
    {
        "id": "gemini-2.5-flash-lite",
        "label": "Gemini 2.5 Flash-Lite",
        "summary": "Fallback leggero: piu veloce, RPM doppio (10 RPM), buon compromesso velocita/qualita.",
        "default_chunk_minutes": 10,
    },
)


@dataclass
class ModelState:
    chain: tuple[str, ...]
    current: str


def is_supported_model(model_name: Any) -> bool:
    return str(model_name or "").strip() in SUPPORTED_MODELS


def sanitize_model_name(model_name: Any, default: str = DEFAULT_MODEL) -> str:
    candidate = str(model_name or "").strip()
    if candidate in SUPPORTED_MODELS:
        return candidate
    return str(default or DEFAULT_MODEL)


def sanitize_fallback_models(
    raw_models: Any,
    primary_model: str,
    default_models: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    if isinstance(raw_models, (list, tuple)):
        source = list(raw_models)
    else:
        source = list(default_models or [])

    sanitized: list[str] = []
    seen: set[str] = set()
    for item in source:
        model_name = str(item or "").strip()
        if not model_name or model_name == primary_model:
            continue
        if model_name not in SUPPORTED_MODELS:
            continue
        if model_name in seen:
            continue
        seen.add(model_name)
        sanitized.append(model_name)
    return sanitized


def model_chain(
    primary_model: str, fallback_models: list[str] | tuple[str, ...] | None = None
) -> tuple[str, ...]:
    primary = sanitize_model_name(primary_model)
    fallbacks = sanitize_fallback_models(fallback_models or [], primary)
    return tuple([primary, *fallbacks])


def build_model_state(
    primary_model: str,
    fallback_models: list[str] | tuple[str, ...] | None = None,
    effective_model: Any = None,
) -> ModelState:
    chain = model_chain(primary_model, fallback_models)
    current = str(effective_model or "").strip()
    if current not in chain:
        current = chain[0]
    return ModelState(chain=chain, current=current)


def next_model_in_chain(state: ModelState) -> str | None:
    try:
        current_idx = state.chain.index(state.current)
    except ValueError:
        return state.chain[0] if state.chain else None
    next_idx = current_idx + 1
    if next_idx >= len(state.chain):
        return None
    return state.chain[next_idx]
