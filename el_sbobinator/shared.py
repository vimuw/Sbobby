"""
Shared utilities/constants for El Sbobinator.

Questo modulo raccoglie configurazione, sessioni/autosave, prompt e helper di I/O
che vengono usati sia dalla pipeline che dalla UI.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import tempfile
import time
from datetime import datetime


DEFAULT_MODEL = "gemini-2.5-flash"

__all__ = [
    "DEFAULT_MODEL",
    "debug_log",
    "cleanup_orphan_temp_chunks",
    "USER_HOME",
    "CONFIG_FILE",
    "get_desktop_dir",
    "safe_output_basename",
    "load_config",
    "save_config",
    "SESSION_SCHEMA_VERSION",
    "SESSION_ROOT",
    "_now_iso",
    "_safe_mkdir",
    "_atomic_write_text",
    "_atomic_write_json",
    "_load_json",
    "_file_fingerprint",
    "_session_id_for_file",
    "_session_dir_for_file",
    "PROMPT_SISTEMA",
    "PROMPT_REVISIONE",
    "PROMPT_REVISIONE_CONFINE",
]

_KEYRING_SERVICE = "El Sbobinator"
_KEYRING_USER_API = "gemini_api_key"


def _keyring_get_api_key() -> str:
    try:
        if platform.system() == "Windows":
            return ""
        import keyring  # type: ignore

        v = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER_API)
        return str(v or "").strip()
    except Exception:
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


def debug_log(msg: str) -> None:
    # Log opzionale: non sporcare la UI in uso normale.
    # Abilita con: setx EL_SBOBINATOR_DEBUG 1 (Windows) / export EL_SBOBINATOR_DEBUG=1 (macOS/Linux)
    try:
        if str(os.environ.get("EL_SBOBINATOR_DEBUG", "")).strip() not in ("1", "true", "TRUE", "yes", "YES"):
            return
    except Exception:
        return
    try:
        print(f"[debug] {msg}")
    except Exception:
        pass


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
            if not (low.endswith(".mp3") or low.endswith(".wav") or low.endswith(".m4a")):
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
# CONFIGURAZIONE UI E FILE
# ==========================================
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

            candidates.append(pwd.getpwuid(os.getuid()).pw_dir)
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
        base = os.path.join(user_home, "Library", "Application Support", "El Sbobinator")
    elif system == "Windows":
        appdata = os.environ.get("APPDATA") or os.path.join(user_home, "AppData", "Roaming")
        base = os.path.join(appdata, "El Sbobinator")
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(user_home, ".config")
        base = os.path.join(xdg, "el_sbobinator")
    return os.path.join(base, "config.json")


# Usa il profilo utente per salvare la configurazione in modo persistente anche quando è un .exe creato con PyInstaller.
USER_HOME = _resolve_user_home()
CONFIG_FILE = _get_config_file_path(USER_HOME)
LEGACY_CONFIG_FILE = os.path.join(USER_HOME, ".el_sbobinator_config.json")


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

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_byte)),
            ]

        def _bytes_to_blob(data: bytes) -> DATA_BLOB:
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
    """
    if platform.system() != "Windows":
        return ""
    try:
        import base64
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_byte)),
            ]

        def _bytes_to_blob(data: bytes) -> DATA_BLOB:
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

        raw = base64.b64decode((b64 or "").encode("ascii", errors="ignore"), validate=False)
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


def load_config() -> dict:
    # Prefer new location, but migrate from legacy (<= 2026-03) file if present.
    for path in (CONFIG_FILE, LEGACY_CONFIG_FILE):
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
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
                except Exception:
                    pass
                # Best-effort migration forward.
                if path == LEGACY_CONFIG_FILE and data.get("api_key"):
                    try:
                        save_config(str(data.get("api_key") or ""))
                    except Exception:
                        pass
                return data
        except Exception:
            pass
    return {"api_key": ""}


def save_config(api_key: str, fallback_keys: list | None = None) -> None:
    api_key_norm = str(api_key or "").strip()
    data: dict = {"api_key": api_key_norm}
    # Persist fallback keys (array of riserva) if provided.
    if fallback_keys is not None:
        data["fallback_keys"] = [str(k or "").strip() for k in fallback_keys if str(k or "").strip()]
    else:
        # Preserve existing fallback keys from current config.
        try:
            existing = load_config()
            fk = existing.get("fallback_keys")
            if isinstance(fk, list) and fk:
                data["fallback_keys"] = fk
        except Exception:
            pass
    # Store encrypted secret on Windows if possible (avoid plaintext on disk).
    try:
        if platform.system() == "Windows" and api_key_norm:
            protected = _dpapi_protect_text_windows(api_key_norm)
            if protected:
                data["api_key"] = ""
                data["api_key_protected"] = protected
    except Exception:
        pass

    # Store secret in OS keyring on macOS/Linux if available.
    try:
        if platform.system() != "Windows":
            if api_key_norm:
                ok = _keyring_set_api_key(api_key_norm)
                if ok:
                    data["api_key"] = ""
                    data["use_keyring"] = True
                else:
                    debug_log("keyring: set_password failed; fallback to plaintext config")
            else:
                # If user clears the key, also clear from keyring (best-effort).
                _keyring_delete_api_key()
                data["api_key"] = ""
                data["use_keyring"] = True
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
        if str(os.environ.get("EL_SBOBINATOR_WRITE_LEGACY_CONFIG", "")).strip() in ("1", "true", "TRUE", "yes", "YES"):
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
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _file_fingerprint(path: str) -> dict:
    abs_path = os.path.abspath(path)
    st = os.stat(abs_path)
    return {
        "path": abs_path,
        "size": int(getattr(st, "st_size", 0)),
        "mtime": float(getattr(st, "st_mtime", 0.0)),
    }


def _session_id_for_file(path: str) -> str:
    fp = _file_fingerprint(path)
    blob = json.dumps(fp, sort_keys=True).encode("utf-8", errors="ignore")
    return hashlib.sha256(blob).hexdigest()


def _session_dir_for_file(path: str) -> str:
    return os.path.join(SESSION_ROOT, _session_id_for_file(path))


# ==========================================
# PROMPT AI (estratti per facilità di modifica)
# ==========================================
PROMPT_SISTEMA = """Agisci come un 'Autore di Libri di Testo Universitari'. Trasforma l'audio della lezione in un MANUALE DI STUDIO formale, strutturato e pronto per la stampa.

REGOLA 1 — ZERO RIPETIZIONI (PRIORITÀ MASSIMA)
1. DIVIETO ASSOLUTO DI RIDONDANZA: Se un concetto, una definizione o un esempio compare più volte nell'audio (perché il docente lo riformula, lo ripete o ci ritorna sopra), scrivi quel concetto UNA SOLA VOLTA, nella posizione più logica del testo, fondendo tutte le formulazioni in un unico paragrafo completo e definitivo. IMPORTANTISSIMO: quando fondi, conserva e integra la SOMMA di tutti i dettagli unici comparsi nelle ripetizioni. Non perdere mai un dettaglio che appare una sola volta.
2. MAI RIFORMULARE: Non scrivere mai la stessa idea con parole diverse in punti diversi del testo. Un concetto = un paragrafo.
3. OVERLAP AUDIO: I blocchi audio si sovrappongono. Se le prime frasi di questo blocco ripetono contenuti già trascritti nel blocco precedente, ignora solo le parti chiaramente identiche o puramente ripetitive. Se nella sovrapposizione c'è ANCHE SOLO un'informazione nuova (numero, termine, definizione, correzione, esempio), includila.
4. CORREZIONI IN TEMPO REALE: Se il docente sbaglia e si corregge, trascrivi solo la versione corretta finale.

REGOLA 2 — STILE SCIENTIFICO IMPERSONALE
1. Elimina ogni traccia di linguaggio parlato: niente "come dicevamo", "ora vi elenco", "se ricordate bene", "vedete questa slide".
2. Scrivi tutto in terza persona impersonale ("Il sistema nervoso riceve..." non "Oggi parleremo del sistema nervoso").
3. ZERO CONVENEVOLI: Inizia immediatamente col contenuto. Non scrivere mai "Ecco la sbobina" o "In questo testo".
4. Nessun titolo con "(continuazione)" o "(segue)".

REGOLA 3 — STRUTTURA E FORMATTAZIONE
1. GERARCHIA TITOLI: Usa ## per i macro-argomenti e ### per le sotto-sezioni.
2. PARAGRAFI DENSI: Scrivi paragrafi corposi e fluidi, non frasi isolate. Unisci le frasi correlate.
3. ELENCHI PUNTATI (formato obbligatorio): Quando il docente elenca tipologie, componenti o fasi:
   - **Termine chiave:** Spiegazione completa in testo normale.
   Solo il termine è in grassetto, seguìto dai due punti.
4. MASSIMO 2 LIVELLI DI NESTING: Usa al massimo un sotto-elenco (○) sotto un elenco (●). MAI scendere a un terzo livello (■). Se servono più dettagli, integra nel testo della voce superiore.
5. GRASSETTI INLINE: Usa il **grassetto** nei paragrafi solo per i termini tecnici fondamentali quando vengono introdotti per la prima volta.
6. FORMULE MATEMATICHE: NON usare MAI la formattazione LaTeX per le formule (niente simboli $, niente \\frac, niente \\ln). Scrivi le equazioni in puro testo lineare chiaro e leggibile (esempio: E = (RT/zF) * ln(Esterno/Interno)). Se usi il LaTeX l'esportazione in PDF si corromperà.

REGOLA 4 — MASSIMO DETTAGLIO SENZA GONFIARE
Pulizia NON significa riassumere. Mantieni ogni spiegazione tecnica, esempio clinico e dettaglio d'esame. Ciò che devi eliminare sono le RIPETIZIONI e le riformulazioni, non le informazioni uniche.
"""


PROMPT_REVISIONE = """
Sei un revisore editoriale accademico. Ti passo una porzione di dispensa universitaria in Markdown.

IL TUO UNICO OBIETTIVO: eliminare ogni ripetizione e ridondanza.

REGOLE INVIOLABILI:
1. SILENZIO ASSOLUTO: Rispondi SOLO con il testo revisionato. Niente frasi introduttive.
2. CACCIA AI DOPPIONI: Cerca concetti, definizioni o spiegazioni che compaiono due o più volte (anche con parole diverse). FONDILI in un unico paragrafo definitivo nella posizione più logica, eliminando tutte le altre occorrenze.
3. FRASI RIDONDANTI: Se una frase non aggiunge informazioni nuove rispetto a quella precedente (es. "Questo processo è fondamentale..." seguito da "L'importanza di questo processo..."), tieni solo la versione migliore.
4. ELIMINA PARLATO RESIDUO: Rimuovi ogni traccia di linguaggio colloquiale rimasto.
5. NON RIASSUMERE MAI: Tutto ciò che NON è un doppione deve restare IDENTICO. Non accorciare spiegazioni tecniche, non eliminare dettagli unici, non semplificare.
6. MANTIENI LA FORMATTAZIONE: Conserva titoli (## e ###), elenchi (- **Termine:** Spiegazione), e la struttura originale.
7. MASSIMO 2 LIVELLI DI NESTING negli elenchi. Se trovi un terzo livello, integra il contenuto nel livello superiore.
8. FORMULE MATEMATICHE: NON usare MAI formattazione LaTeX (niente simboli $, niente \\frac). Scrivi le equazioni esclusivamente in testo lineare (es: V = (RT/F) * ln(Est/Int)).
"""


PROMPT_REVISIONE_CONFINE = """
Sei un revisore editoriale accademico.
Ti passo DUE estratti in Markdown: la FINE del blocco N e l'INIZIO del blocco N+1, separati dal marker:
<<<EL_SBOBINATOR_SPLIT>>>

IL TUO UNICO OBIETTIVO: eliminare ripetizioni e ridondanze che stanno tra i due estratti (doppioni che scappano tra macro-blocchi).

REGOLE INVIOLABILI:
1. SILENZIO ASSOLUTO: Rispondi SOLO con i due estratti revisionati.
2. OUTPUT OBBLIGATORIO: Mantieni ESATTAMENTE lo stesso marker <<<EL_SBOBINATOR_SPLIT>>> tra i due testi revisionati.
3. NON RIASSUMERE MAI: Elimina solo i doppioni. Tutto il resto resta.
4. MANTIENI LA FORMATTAZIONE Markdown: titoli (## / ###), elenchi, grassetti, ecc.
5. FORMULE MATEMATICHE: niente LaTeX, solo testo lineare.
"""
