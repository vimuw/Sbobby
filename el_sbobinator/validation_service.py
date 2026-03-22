"""
Environment validation helpers.

Used both by the WebUI "validate environment" action and by build/release smoke
checks to quickly surface missing dependencies or configuration issues.
"""

from __future__ import annotations

import os
import tempfile

from google import genai

from el_sbobinator.audio_service import resolve_ffmpeg
from el_sbobinator.bridge_types import ValidationCheck, ValidationResult
from el_sbobinator.shared import CONFIG_FILE, DEFAULT_MODEL, USER_HOME, get_desktop_dir


def _check_writable_dir(path: str) -> tuple[bool, str]:
    probe_name = os.path.join(path, ".el_sbobinator_write_test")
    try:
        os.makedirs(path, exist_ok=True)
        with open(probe_name, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe_name)
        return True, "Scrittura consentita."
    except Exception as exc:
        return False, str(exc)


def validate_environment(api_key: str | None = None, validate_api_key: bool = False) -> ValidationResult:
    checks: list[ValidationCheck] = []

    try:
        ffmpeg_path = resolve_ffmpeg()
        checks.append(
            {
                "id": "ffmpeg",
                "label": "FFmpeg",
                "status": "ok",
                "message": "FFmpeg disponibile.",
                "details": ffmpeg_path,
            }
        )
    except Exception as exc:
        checks.append(
            {
                "id": "ffmpeg",
                "label": "FFmpeg",
                "status": "error",
                "message": "FFmpeg non trovato o non utilizzabile.",
                "details": str(exc),
            }
        )

    config_dir = os.path.dirname(CONFIG_FILE)
    ok_config, msg_config = _check_writable_dir(config_dir)
    checks.append(
        {
            "id": "config",
            "label": "Config locale",
            "status": "ok" if ok_config else "error",
            "message": "Cartella config scrivibile." if ok_config else "Impossibile scrivere la config.",
            "details": config_dir if ok_config else msg_config,
        }
    )

    output_dir = get_desktop_dir() or USER_HOME or tempfile.gettempdir()
    ok_output, msg_output = _check_writable_dir(output_dir)
    checks.append(
        {
            "id": "output",
            "label": "Cartella output",
            "status": "ok" if ok_output else "error",
            "message": "Cartella output disponibile." if ok_output else "Cartella output non scrivibile.",
            "details": output_dir if ok_output else msg_output,
        }
    )

    if validate_api_key:
        cleaned = str(api_key or "").strip()
        if not cleaned:
            checks.append(
                {
                    "id": "api_key",
                    "label": "API Key Gemini",
                    "status": "warning",
                    "message": "API key assente: controllo remoto saltato.",
                    "details": "Inserisci una chiave se vuoi verificare l'accesso al modello.",
                }
            )
        else:
            try:
                client = genai.Client(api_key=cleaned)
                client.models.get(model=DEFAULT_MODEL)
                checks.append(
                    {
                        "id": "api_key",
                        "label": "API Key Gemini",
                        "status": "ok",
                        "message": "API key valida.",
                        "details": DEFAULT_MODEL,
                    }
                )
            except Exception as exc:
                checks.append(
                    {
                        "id": "api_key",
                        "label": "API Key Gemini",
                        "status": "error",
                        "message": "API key non valida o accesso non disponibile.",
                        "details": str(exc),
                    }
                )

    ok = all(check["status"] != "error" for check in checks)
    summary = "Ambiente pronto." if ok else "Ambiente incompleto: correggi gli errori segnalati."
    return {"ok": ok, "summary": summary, "checks": checks}
