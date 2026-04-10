"""
Environment validation helpers.

Used both by the WebUI "validate environment" action and by build/release smoke
checks to quickly surface missing dependencies or configuration issues.
"""

from __future__ import annotations

import os
import platform
import tempfile

from google import genai

from el_sbobinator.model_registry import (
    DEFAULT_FALLBACK_MODELS,
    sanitize_fallback_models,
    sanitize_model_name,
)
from el_sbobinator.audio_service import resolve_ffmpeg
from el_sbobinator.bridge_types import ValidationCheck, ValidationResult
from el_sbobinator.shared import CONFIG_FILE, DEFAULT_MODEL, USER_HOME, get_desktop_dir


def _check_writable_dir(path: str) -> tuple[bool, str]:
    probe_name = os.path.join(path, ".el_sbobinator_write_test")
    try:
        os.makedirs(path, exist_ok=True)
        with open(probe_name, "w", encoding="utf-8") as handle:
            handle.write("ok")
    except Exception as exc:
        return False, str(exc)
    try:
        os.remove(probe_name)
    except Exception:
        pass
    return True, "Scrittura consentita."


def _get_model_capabilities(model_info) -> list[str] | None:
    for field_name in ("supported_actions", "supported_generation_methods"):
        try:
            if isinstance(model_info, dict):
                value = model_info.get(field_name)
            else:
                value = getattr(model_info, field_name, None)
        except Exception:
            value = None
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
    return None


def validate_environment(
    api_key: str | None = None,
    validate_api_key: bool = False,
    preferred_model: str | None = None,
    fallback_models: list[str] | None = None,
) -> ValidationResult:
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
            "message": "Cartella config scrivibile."
            if ok_config
            else "Impossibile scrivere la config.",
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
            "message": "Cartella output disponibile."
            if ok_output
            else "Cartella output non scrivibile.",
            "details": output_dir if ok_output else msg_output,
        }
    )

    if validate_api_key:
        cleaned = str(api_key or "").strip()
        primary_model = sanitize_model_name(preferred_model, DEFAULT_MODEL)
        sanitized_fallbacks = sanitize_fallback_models(
            fallback_models,
            primary_model,
            DEFAULT_FALLBACK_MODELS,
        )
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
            except Exception as exc:
                checks.append(
                    {
                        "id": "api_key",
                        "label": "API Key Gemini",
                        "status": "error",
                        "message": "API key non valida o modello primario non accessibile.",
                        "details": str(exc),
                    }
                )
            else:
                model_chain = [primary_model, *sanitized_fallbacks]
                for idx, model_name in enumerate(model_chain):
                    check_id = "api_key" if idx == 0 else f"api_model_{idx}"
                    check_label = (
                        "API Key Gemini" if idx == 0 else f"Fallback modello {idx}"
                    )
                    try:
                        model_info = client.models.get(model=model_name)
                        capabilities = _get_model_capabilities(model_info)
                        if capabilities is not None and "generatecontent" not in {
                            str(item or "").strip().lower() for item in capabilities
                        }:
                            raise RuntimeError(
                                f"{model_name} non supporta generateContent"
                            )
                        checks.append(
                            {
                                "id": check_id,
                                "label": check_label,
                                "status": "ok",
                                "message": f"Accesso disponibile per {model_name}.",
                                "details": model_name,
                            }
                        )
                    except Exception as exc:
                        checks.append(
                            {
                                "id": check_id,
                                "label": check_label,
                                "status": "error",
                                "message": (
                                    "API key non valida o modello primario non accessibile."
                                    if idx == 0
                                    else f"Modello fallback {idx} non accessibile con questa chiave."
                                ),
                                "details": str(exc)
                                if idx == 0
                                else f"{model_name}: {exc}",
                            }
                        )

    if platform.system() != "Windows":
        keyring_ok = False
        keyring_detail = ""
        try:
            import keyring  # type: ignore

            keyring.get_password("__el_sbobinator_probe__", "__probe__")
            keyring_ok = True
        except Exception as exc:
            keyring_detail = str(exc)
        checks.append(
            {
                "id": "keyring",
                "label": "Keyring",
                "status": "ok" if keyring_ok else "warning",
                "message": "Keyring disponibile: chiave API protetta."
                if keyring_ok
                else "Keyring non disponibile: la chiave API sarà salvata in chiaro.",
                "details": "" if keyring_ok else keyring_detail,
            }
        )

    ok = all(check["status"] != "error" for check in checks)
    summary = (
        "Ambiente pronto."
        if ok
        else "Ambiente incompleto: correggi gli errori segnalati."
    )
    return {"ok": ok, "summary": summary, "checks": checks}
