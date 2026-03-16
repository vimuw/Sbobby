"""
Shared utilities/constants for Sbobby.

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
    "FONT_UI",
    "FONT_UI_EMOJI",
    "FONT_MONO",
    "PROMPT_SISTEMA",
    "PROMPT_REVISIONE",
    "PROMPT_REVISIONE_CONFINE",
]


def debug_log(msg: str) -> None:
    # Log opzionale: non sporcare la UI in uso normale.
    # Abilita con: setx SBOBBY_DEBUG 1 (Windows) / export SBOBBY_DEBUG=1 (macOS/Linux)
    try:
        if str(os.environ.get("SBOBBY_DEBUG", "")).strip() not in ("1", "true", "TRUE", "yes", "YES"):
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
            if not low.startswith("sbobby_temp_"):
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
    - macOS: ~/Library/Application Support/Sbobby/config.json
    - Windows: %APPDATA%\\Sbobby\\config.json
    - Linux: $XDG_CONFIG_HOME/sbobby/config.json or ~/.config/sbobby/config.json
    """
    system = platform.system()
    if system == "Darwin":
        base = os.path.join(user_home, "Library", "Application Support", "Sbobby")
    elif system == "Windows":
        appdata = os.environ.get("APPDATA") or os.path.join(user_home, "AppData", "Roaming")
        base = os.path.join(appdata, "Sbobby")
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(user_home, ".config")
        base = os.path.join(xdg, "sbobby")
    return os.path.join(base, "config.json")


# Usa il profilo utente per salvare la configurazione in modo persistente anche quando è un .exe creato con PyInstaller.
USER_HOME = _resolve_user_home()
CONFIG_FILE = _get_config_file_path(USER_HOME)
LEGACY_CONFIG_FILE = os.path.join(USER_HOME, ".sbobby_config.json")


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


def save_config(api_key: str) -> None:
    data = {"api_key": api_key}
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

    # Back-compat: also write legacy file if possible (best-effort).
    try:
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
SESSION_ROOT = os.path.join(USER_HOME, ".sbobby_sessions")


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
# FONT CROSS-PLATFORM
# ==========================================
if platform.system() == "Darwin":  # macOS
    FONT_UI = "Helvetica"
    FONT_UI_EMOJI = "Apple Color Emoji"
    FONT_MONO = "Menlo"
else:
    FONT_UI = "Segoe UI"
    # Windows: font dedicato agli emoji. Linux: fallback ragionevole.
    FONT_UI_EMOJI = "Segoe UI Emoji" if platform.system() == "Windows" else "Noto Color Emoji"
    FONT_MONO = "Cascadia Code"

# Font che include emoji senza sballare l'allineamento con il testo (soprattutto su Windows).
if platform.system() == "Windows":
    FONT_UI_EMOJI = "Segoe UI Emoji"
else:
    FONT_UI_EMOJI = FONT_UI


# ==========================================
# PROMPT AI (estratti per facilità di modifica)
# ==========================================
PROMPT_SISTEMA = """
Agisci come un 'Autore di Libri di Testo Universitari'. Trasforma l'audio della lezione in un MANUALE DI STUDIO formale, strutturato e pronto per la stampa.

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
<<<SBOBBY_SPLIT>>>

IL TUO UNICO OBIETTIVO: eliminare ripetizioni e ridondanze che stanno tra i due estratti (doppioni che scappano tra macro-blocchi).

REGOLE INVIOLABILI:
1. SILENZIO ASSOLUTO: Rispondi SOLO con i due estratti revisionati.
2. OUTPUT OBBLIGATORIO: Mantieni ESATTAMENTE lo stesso marker <<<SBOBBY_SPLIT>>> tra i due testi revisionati.
3. NON RIASSUMERE MAI: Elimina solo i doppioni. Tutto il resto resta.
4. MANTIENI LA FORMATTAZIONE Markdown: titoli (## / ###), elenchi, grassetti, ecc.
5. FORMULE MATEMATICHE: niente LaTeX, solo testo lineare.
"""
