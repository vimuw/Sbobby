"""
Shared Python-side types for the PyWebView bridge.

Keeping these payload shapes in one place makes the backend/frontend contract
clearer and reduces silent drift when the React app evolves.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


class BridgeFileItem(TypedDict):
    id: str
    path: str
    name: str
    size: NotRequired[int]
    duration: NotRequired[float]
    resume_session: NotRequired[bool]


class ProcessDonePayload(TypedDict, total=False):
    cancelled: bool
    completed: int
    failed: int
    total: int


class SetCurrentFilePayload(TypedDict):
    index: int
    id: str
    total: int


class FileDonePayload(TypedDict):
    index: int
    id: str
    output_html: str
    output_dir: str
    effective_model: str
    primary_model: NotRequired[str]


class FileFailedPayload(TypedDict):
    index: int
    id: str
    error: str


class WorkTotalsPayload(TypedDict, total=False):
    chunks: int | None
    macro: int | None


class WorkDonePayload(TypedDict, total=False):
    kind: Literal["chunks", "macro"]
    done: int
    total: int | None


class StepTimePayload(TypedDict, total=False):
    kind: Literal["chunks", "macro"]
    seconds: float
    done: int | None
    total: int | None


class ValidationCheck(TypedDict):
    id: str
    label: str
    status: Literal["ok", "warning", "error"]
    message: str
    details: NotRequired[str]


class ValidationResult(TypedDict):
    ok: bool
    summary: str
    checks: list[ValidationCheck]
