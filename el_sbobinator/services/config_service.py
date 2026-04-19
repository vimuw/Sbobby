"""
Configuration and credential management for El Sbobinator.

Contains:
- User-home and config-file path resolution
- Windows DPAPI and macOS/Linux keyring helpers
- load_config / save_config
- Filesystem helpers: get_desktop_dir, safe_output_basename
- debug_log utility
"""

from __future__ import annotations

import functools
import json
import os
import platform
import re
import threading
import time

from el_sbobinator.model_registry import (
    DEFAULT_FALLBACK_MODELS,
    DEFAULT_MODEL,
    sanitize_fallback_models,
    sanitize_model_name,
)

_KEYRING_SERVICE = "El Sbobinator"
_KEYRING_USER_API = "gemini_api_key"
_config_lock = threading.Lock()
_write_lock = threading.Lock()
_config_cache: dict | None = None
_config_cache_ts: float = 0.0
_config_cache_gen: int = 0
_CONFIG_CACHE_TTL = 30.0


def debug_log(msg: str) -> None:
    # Log opzionale: non sporcare la UI in uso normale.
    # Abilita con: setx EL_SBOBINATOR_DEBUG 1 (Windows) / export EL_SBOBINATOR_DEBUG=1 (macOS/Linux)
    try:
        if str(os.environ.get("EL_SBOBINATOR_DEBUG", "")).strip() not in (
            "1",
            "true",
            "TRUE",
            "yes",
            "YES",
        ):
            return
    except Exception:
        return
    try:
        print(f"[debug] {msg}")
    except Exception:
        pass


def _keyring_get_api_key() -> str:
    for attempt in range(2):
        try:
            if platform.system() == "Windows":
                return ""
            import keyring  # type: ignore

            v = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER_API)
            result = str(v or "").strip()
            if result:
                return result
            break  # keyring reachable but no key stored — no point retrying
        except Exception:
            pass
        if attempt == 0:
            time.sleep(0.5)
    return ""


def _keyring_set_api_key(api_key: str) -> bool:
    try:
        if platform.system() == "Windows":
            return False
        import keyring  # type: ignore

        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER_API, str(api_key or ""))
        return True
    except Exception:
        return False


def _keyring_delete_api_key() -> bool:
    try:
        if platform.system() == "Windows":
            return False
        import keyring  # type: ignore

        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USER_API)
        return True
    except Exception:
        return False


def _resolve_user_home() -> str:
    """
    Resolve the user's home directory robustly across platforms and packaging contexts.
    On some macOS GUI launches the environment can be sparse; fall back to system account info.
    """
    candidates = []
    try:
        candidates.append(os.path.expanduser("~"))
    except Exception:
        pass
    try:
        candidates.append(os.environ.get("HOME"))
    except Exception:
        pass
    if platform.system() != "Windows":
        try:
            import pwd  # type: ignore

            candidates.append(pwd.getpwuid(os.getuid()).pw_dir)  # type: ignore[attr-defined]
        except Exception:
            pass

    for c in candidates:
        if not c:
            continue
        c = str(c).strip()
        if not c or c == "~":
            continue
        if os.path.isabs(c) and os.path.isdir(c):
            return c

    # Last-resort: use current working directory (may not be writable, but prevents "~" bugs).
    try:
        return os.path.abspath(os.getcwd())
    except Exception:
        return "."


def _get_config_file_path(user_home: str) -> str:
    """
    Pick an OS-appropriate, persistent config path.
    - macOS: ~/Library/Application Support/El Sbobinator/config.json
    - Windows: %APPDATA%\\El Sbobinator\\config.json
    - Linux: $XDG_CONFIG_HOME/el_sbobinator/config.json or ~/.config/el_sbobinator/config.json
    """
    system = platform.system()
    if system == "Darwin":
        base = os.path.join(
            user_home, "Library", "Application Support", "El Sbobinator"
        )
    elif system == "Windows":
        appdata = os.environ.get("APPDATA") or os.path.join(
            user_home, "AppData", "Roaming"
        )
        base = os.path.join(appdata, "El Sbobinator")
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(user_home, ".config")
        base = os.path.join(xdg, "el_sbobinator")
    return os.path.join(base, "config.json")


# Usa il profilo utente per salvare la configurazione in modo persistente anche quando è un .exe creato con PyInstaller.
USER_HOME = _resolve_user_home()
CONFIG_FILE = _get_config_file_path(USER_HOME)
LEGACY_CONFIG_FILE = os.path.join(USER_HOME, ".el_sbobinator_config.json")


@functools.lru_cache(maxsize=1)
def _dpapi_make_blob_class(ctypes_mod, wintypes_mod):
    class DATA_BLOB(ctypes_mod.Structure):
        _fields_ = [  # noqa: RUF012
            ("cbData", wintypes_mod.DWORD),
            ("pbData", ctypes_mod.POINTER(ctypes_mod.c_byte)),
        ]

    return DATA_BLOB


def _dpapi_protect_text_windows(text: str) -> str:
    """
    Best-effort encryption for secrets on Windows using DPAPI (CryptProtectData).
    Returns base64 string on success, "" on failure.
    """
    if platform.system() != "Windows":
        return ""
    try:
        import base64
        import ctypes
        from ctypes import wintypes

        DATA_BLOB = _dpapi_make_blob_class(ctypes, wintypes)  # type: ignore[arg-type]

        def _bytes_to_blob(data: bytes) -> DATA_BLOB:  # type: ignore[valid-type]
            buf = ctypes.create_string_buffer(data)
            return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(DATA_BLOB),
            wintypes.LPCWSTR,
            ctypes.POINTER(DATA_BLOB),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(DATA_BLOB),
        ]
        crypt32.CryptProtectData.restype = wintypes.BOOL

        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p

        plain = (text or "").encode("utf-8", errors="strict")
        if not plain:
            return ""
        in_blob = _bytes_to_blob(plain)
        out_blob = DATA_BLOB()
        CRYPTPROTECT_UI_FORBIDDEN = 0x1
        ok = crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            None,
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(out_blob),
        )
        if not ok:
            return ""
        try:
            out_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            try:
                kernel32.LocalFree(out_blob.pbData)
            except Exception:
                pass
        return base64.b64encode(out_bytes).decode("ascii")
    except Exception:
        return ""


def _dpapi_unprotect_text_windows(b64: str) -> str:
    """
    Best-effort decryption for secrets on Windows using DPAPI (CryptUnprotectData).
    Returns plaintext string on success, "" on failure.
    Retries once after 500 ms to tolerate transient service unavailability.
    """
    if platform.system() != "Windows":
        return ""
    for attempt in range(2):
        result = _dpapi_unprotect_text_windows_once(b64)
        if result:
            return result
        if attempt == 0:
            time.sleep(0.5)
    return ""


def _dpapi_unprotect_text_windows_once(b64: str) -> str:
    if platform.system() != "Windows":
        return ""
    try:
        import base64
        import ctypes
        from ctypes import wintypes

        DATA_BLOB = _dpapi_make_blob_class(ctypes, wintypes)  # type: ignore[arg-type]

        def _bytes_to_blob(data: bytes) -> DATA_BLOB:  # type: ignore[valid-type]
            buf = ctypes.create_string_buffer(data)
            return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(DATA_BLOB),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(DATA_BLOB),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(DATA_BLOB),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL

        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p

        raw = base64.b64decode(
            (b64 or "").encode("ascii", errors="ignore"), validate=False
        )
        if not raw:
            return ""
        in_blob = _bytes_to_blob(raw)
        out_blob = DATA_BLOB()
        desc = wintypes.LPWSTR()
        CRYPTPROTECT_UI_FORBIDDEN = 0x1
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            ctypes.byref(desc),
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(out_blob),
        )
        if not ok:
            return ""
        try:
            out_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            try:
                kernel32.LocalFree(out_blob.pbData)
            except Exception:
                pass
            try:
                if desc:
                    kernel32.LocalFree(desc)
            except Exception:
                pass
        return out_bytes.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def get_desktop_dir() -> str:
    # Cross-platform Desktop path (Windows/macOS/Linux). Fallback: home directory.
    try:
        if platform.system() == "Windows":
            # Prefer OneDrive Desktop if present (common on Windows 10/11).
            for env_key in ("OneDriveConsumer", "OneDriveCommercial", "OneDrive"):
                od = os.environ.get(env_key)
                if od:
                    p = os.path.join(od, "Desktop")
                    if os.path.isdir(p):
                        return p
            up = os.environ.get("USERPROFILE") or USER_HOME
            p = os.path.join(up, "Desktop")
            if os.path.isdir(p):
                return p
        # macOS/Linux default
        p = os.path.join(USER_HOME, "Desktop")
        if os.path.isdir(p):
            return p
    except Exception:
        pass
    return USER_HOME


def safe_output_basename(name: str) -> str:
    # Safe across Windows/macOS. Keep it readable.
    s = (name or "").strip() or "Sbobina"
    s = re.sub(r"[<>:\"/\\\\|?*]+", "_", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:140] if len(s) > 140 else s


def load_config() -> dict:  # noqa: C901
    global _config_cache, _config_cache_ts
    with _config_lock:
        if (
            _config_cache is not None
            and time.monotonic() - _config_cache_ts < _CONFIG_CACHE_TTL
        ):
            _hit = dict(_config_cache)
            _hit["fallback_models"] = list(_config_cache.get("fallback_models") or [])
            _hit["fallback_keys"] = list(_config_cache.get("fallback_keys") or [])
            return _hit
        gen_at_start = _config_cache_gen
    # Prefer new location, but migrate from legacy (<= 2026-03) file if present.
    for path in (CONFIG_FILE, LEGACY_CONFIG_FILE):
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # Prefer keyring secret on macOS/Linux (keeps disk config without secrets).
                try:
                    if platform.system() != "Windows":
                        k = _keyring_get_api_key()
                        if k:
                            data["api_key"] = k
                        else:
                            # One-time migration: if plaintext exists on disk, move to keyring.
                            plain = str(data.get("api_key") or "").strip()
                            if plain:
                                if _keyring_set_api_key(plain):
                                    try:
                                        save_config(plain)
                                    except Exception:
                                        pass
                            elif data.get("use_keyring"):
                                data["has_protected_key"] = True
                except Exception:
                    pass
                # Decrypt best-effort on Windows (do not expose protected value to callers).
                try:
                    if platform.system() == "Windows":
                        if not (str(data.get("api_key") or "").strip()):
                            protected = str(data.get("api_key_protected") or "").strip()
                            if protected:
                                dec = _dpapi_unprotect_text_windows(protected)
                                if dec:
                                    data["api_key"] = dec
                                else:
                                    data["has_protected_key"] = True
                except Exception:
                    pass
                # Decrypt fallback keys on Windows.
                try:
                    if platform.system() == "Windows":
                        protected_fk = str(
                            data.get("fallback_keys_protected") or ""
                        ).strip()
                        if protected_fk:
                            dec_fk = _dpapi_unprotect_text_windows(protected_fk)
                            if dec_fk:
                                data["fallback_keys"] = json.loads(dec_fk)
                except Exception:
                    pass
                # Get fallback keys from keyring on macOS/Linux.
                try:
                    if platform.system() != "Windows":
                        import keyring  # type: ignore

                        fk_json = keyring.get_password(
                            _KEYRING_SERVICE, "gemini_fallback_keys"
                        )
                        if fk_json:
                            data["fallback_keys"] = json.loads(fk_json)
                except Exception:
                    pass
                # Best-effort migration forward.
                if path == LEGACY_CONFIG_FILE and data.get("api_key"):
                    try:
                        save_config(
                            str(data.get("api_key") or ""),
                            preferred_model=data.get("preferred_model"),
                            fallback_models=data.get("fallback_models"),
                        )
                    except Exception:
                        pass
                preferred_model = sanitize_model_name(
                    data.get("preferred_model"), DEFAULT_MODEL
                )
                fallback_models = sanitize_fallback_models(
                    data.get("fallback_models"),
                    preferred_model,
                    DEFAULT_FALLBACK_MODELS,
                )
                data["preferred_model"] = preferred_model
                data["fallback_models"] = fallback_models
                with _config_lock:
                    if _config_cache_gen == gen_at_start:
                        _cache_entry = dict(data)
                        _cache_entry["fallback_models"] = list(
                            data.get("fallback_models") or []
                        )
                        _cache_entry["fallback_keys"] = list(
                            data.get("fallback_keys") or []
                        )
                        _config_cache = _cache_entry
                        _config_cache_ts = time.monotonic()
                result = dict(data)
                result["fallback_models"] = list(data.get("fallback_models") or [])
                result["fallback_keys"] = list(data.get("fallback_keys") or [])
                return result
        except Exception:
            pass
    _default = {
        "api_key": "",
        "preferred_model": DEFAULT_MODEL,
        "fallback_models": list(DEFAULT_FALLBACK_MODELS),
    }
    with _config_lock:
        if _config_cache_gen == gen_at_start:
            _cache_entry = dict(_default)
            _cache_entry["fallback_models"] = list(
                _default.get("fallback_models") or []
            )
            _config_cache = _cache_entry
            _config_cache_ts = time.monotonic()
    result = dict(_default)
    result["fallback_models"] = list(_default.get("fallback_models") or [])
    return result


def save_config(  # noqa: C901
    api_key: str | None,
    fallback_keys: list | None = None,
    preferred_model: str | None = None,
    fallback_models: list | None = None,
) -> None:
    global _config_cache, _config_cache_gen
    with _write_lock:
        with _config_lock:
            _config_cache = None
            _config_cache_gen += 1
        api_key_norm = str(api_key or "").strip()
        data: dict = {"api_key": api_key_norm}
        current_cfg: dict = {}
        for _path in (CONFIG_FILE, LEGACY_CONFIG_FILE):
            if not os.path.exists(_path):
                continue
            try:
                with open(_path, encoding="utf-8") as _fh:
                    raw_cfg = json.load(_fh)
                if isinstance(raw_cfg, dict):
                    current_cfg = raw_cfg
                    break
            except Exception:
                pass
        preferred_model_norm = sanitize_model_name(
            preferred_model
            if preferred_model is not None
            else current_cfg.get("preferred_model"),
            DEFAULT_MODEL,
        )
        fallback_models_norm = sanitize_fallback_models(
            fallback_models
            if fallback_models is not None
            else current_cfg.get("fallback_models"),
            preferred_model_norm,
            DEFAULT_FALLBACK_MODELS,
        )
        data["preferred_model"] = preferred_model_norm
        data["fallback_models"] = fallback_models_norm
        # Persist fallback keys (array of riserva) if provided.
        if fallback_keys is not None:
            data["fallback_keys"] = [
                str(k or "").strip() for k in fallback_keys if str(k or "").strip()
            ]
        else:
            # Preserve existing fallback keys without the full DPAPI/keyring overhead
            # of load_config(). On Windows, read raw JSON and carry whatever stored
            # form is already on disk verbatim (no decrypt+re-encrypt cycle needed).
            # On macOS/Linux, do a targeted keyring lookup for fallback keys only.
            try:
                if platform.system() == "Windows":
                    _raw: dict | None = None
                    for _p in (CONFIG_FILE, LEGACY_CONFIG_FILE):
                        if os.path.exists(_p):
                            try:
                                with open(_p, encoding="utf-8") as _f:
                                    _raw = json.load(_f)
                                break
                            except Exception:
                                pass
                    if isinstance(_raw, dict):
                        if _raw.get("fallback_keys_protected"):
                            data["fallback_keys_protected"] = _raw[
                                "fallback_keys_protected"
                            ]
                        elif (
                            isinstance(_raw.get("fallback_keys"), list)
                            and _raw["fallback_keys"]
                        ):
                            data["fallback_keys"] = _raw["fallback_keys"]
                else:
                    try:
                        import keyring as _kr  # type: ignore

                        _fk_json = _kr.get_password(
                            _KEYRING_SERVICE, "gemini_fallback_keys"
                        )
                        if _fk_json:
                            data["fallback_keys"] = json.loads(_fk_json)
                    except Exception:
                        pass
            except Exception:
                pass
        # Store encrypted secret on Windows if possible (avoid plaintext on disk).
        try:
            if platform.system() == "Windows" and api_key_norm:
                protected = _dpapi_protect_text_windows(api_key_norm)
                if protected:
                    data["api_key"] = ""
                    data["api_key_protected"] = protected
                else:
                    debug_log(
                        "dpapi: CryptProtectData failed; API key stored as plaintext in config"
                    )
        except Exception as _dpapi_exc:
            debug_log(
                f"dpapi: exception during protect — API key stored as plaintext in config: {_dpapi_exc}"
            )
        if (
            platform.system() == "Windows"
            and api_key is None
            and "api_key_protected" not in data
        ):
            _existing_protected = current_cfg.get("api_key_protected")
            if _existing_protected:
                data["api_key_protected"] = _existing_protected

        # Store secret in OS keyring on macOS/Linux if available.
        try:
            if platform.system() != "Windows":
                if api_key is None:
                    # No-change: preserve existing keyring flags verbatim.
                    if "use_keyring" in current_cfg:
                        data["use_keyring"] = current_cfg["use_keyring"]
                elif api_key_norm:
                    ok = _keyring_set_api_key(api_key_norm)
                    if ok:
                        data["api_key"] = ""
                        data["use_keyring"] = True
                    else:
                        print(
                            "[!] Avviso: Keyring non disponibile. La chiave API è salvata in chiaro in config.json."
                        )
                        data.setdefault("use_keyring", False)
                else:
                    # If user clears the key, also clear from keyring (best-effort).
                    _keyring_delete_api_key()
                    data["api_key"] = ""
                    data["use_keyring"] = True
        except Exception:
            pass
        # Encrypt fallback keys (same mechanisms as primary key).
        fk = data.get("fallback_keys")
        if fk:
            try:
                if platform.system() == "Windows":
                    protected_fk = _dpapi_protect_text_windows(json.dumps(fk))
                    if protected_fk:
                        data["fallback_keys"] = []
                        data["fallback_keys_protected"] = protected_fk
                    else:
                        debug_log(
                            "dpapi: CryptProtectData failed for fallback keys; stored as plaintext in config"
                        )
            except Exception as _dpapi_fk_exc:
                debug_log(
                    f"dpapi: exception during protect for fallback keys — stored as plaintext in config: {_dpapi_fk_exc}"
                )
            try:
                if platform.system() != "Windows":
                    import keyring  # type: ignore

                    keyring.set_password(
                        _KEYRING_SERVICE, "gemini_fallback_keys", json.dumps(fk)
                    )
                    data["fallback_keys"] = []
            except Exception:
                pass
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        except Exception:
            pass

        try:
            # Atomic write to avoid truncation on crash/force-close.
            tmp_path = CONFIG_FILE + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp_path, CONFIG_FILE)

            # Restrict permissions on POSIX systems (best-effort).
            if platform.system() != "Windows":
                try:
                    os.chmod(CONFIG_FILE, 0o600)
                except Exception:
                    pass
        except Exception:
            # Best-effort: non bloccare l'app se il config non e' scrivibile.
            return

        # Back-compat (opt-in): write legacy file only if explicitly requested.
        # Avoid duplicating secrets (especially on Windows).
        try:
            if str(os.environ.get("EL_SBOBINATOR_WRITE_LEGACY_CONFIG", "")).strip() in (
                "1",
                "true",
                "TRUE",
                "yes",
                "YES",
            ):
                with open(LEGACY_CONFIG_FILE + ".tmp", "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                os.replace(LEGACY_CONFIG_FILE + ".tmp", LEGACY_CONFIG_FILE)
                if platform.system() != "Windows":
                    try:
                        os.chmod(LEGACY_CONFIG_FILE, 0o600)
                    except Exception:
                        pass
        except Exception:
            pass
