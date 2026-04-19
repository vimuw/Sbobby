"""
Application entry point for El Sbobinator (pywebview).

Contains: _ConsoleTee, get_dist_path(), has_webview2_runtime(),
build_missing_webview2_html(), and main().
"""

from __future__ import annotations

import os
import sys
import warnings
from html import escape

import webview

from el_sbobinator.media_server import LocalMediaServer

# Suppress benign requests warning about chardet/charset_normalizer failing to import
warnings.filterwarnings(
    "ignore", message="Unable to find acceptable character detection dependency"
)

# ---------------------------------------------------------------------------
# Console interceptor
# ---------------------------------------------------------------------------

_MAX_CONSOLE_LINE_LEN = 2000


class _ConsoleTee:
    """Intercept print() calls and forward to React console too."""

    def __init__(self, original, api: ElSbobinatorApi):  # type: ignore[name-defined]  # noqa: F821
        self._original = original  # May be None for .pyw on Windows
        self._api = api

    def write(self, text):
        if self._original is not None:
            try:
                self._original.write(text)
            except Exception:
                pass
        if text and text.strip():
            line = text.rstrip()
            if len(line) > _MAX_CONSOLE_LINE_LEN:
                line = line[:_MAX_CONSOLE_LINE_LEN] + "… [troncato]"
            self._api._push_console(line)

    def flush(self):
        if self._original is not None:
            try:
                self._original.flush()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Entry-point helpers
# ---------------------------------------------------------------------------


def get_dist_path() -> str:
    """Locate the webui dist folder (works both in dev and PyInstaller)."""
    if getattr(sys, "frozen", False):
        # PyInstaller bundle
        base = sys._MEIPASS  # type: ignore
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist = os.path.join(base, "webui", "dist", "index.html")
    if os.path.exists(dist):
        return dist
    # Fallback: relative to cwd
    alt = os.path.join(os.getcwd(), "webui", "dist", "index.html")
    if os.path.exists(alt):
        return alt
    raise FileNotFoundError(
        f"Non trovo webui/dist/index.html. Esegui 'npm run build' nella cartella webui/.\n"
        f"Cercato in: {dist} e {alt}"
    )


def has_webview2_runtime() -> bool:
    """Mirror pywebview's Windows runtime detection to avoid silent MSHTML fallback."""
    if sys.platform != "win32":
        return True

    try:
        import winreg
    except Exception:
        return False

    runtime_keys = (
        (
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        ),
    )

    for root, key_path in runtime_keys:
        try:
            with winreg.OpenKey(root, key_path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if str(version).strip():
                    return True
        except Exception:
            continue

    return False


def build_missing_webview2_html() -> str:
    download_url = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
    repo_url = "https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
    return f"""<!doctype html>
<html lang="it">
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="X-UA-Compatible" content="IE=11" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>El Sbobinator</title>
    <style>
      body {{
        margin: 0;
        padding: 40px 20px;
        background: #f0f2f5;
        font-family: "Segoe UI", Arial, sans-serif;
        color: #222;
      }}
      .card {{
        max-width: 560px;
        margin: 20px auto;
        background: #ffffff;
        border: 1px solid #dde1e7;
        border-radius: 10px;
        padding: 36px 40px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
      }}
      h1 {{
        margin: 0 0 14px;
        font-size: 20px;
        font-weight: 700;
        color: #111;
        line-height: 1.3;
      }}
      p {{
        margin: 0 0 10px;
        font-size: 14px;
        line-height: 1.65;
        color: #555;
      }}
      code {{
        background: #eef0f3;
        padding: 2px 7px;
        border-radius: 5px;
        font-family: Consolas, monospace;
        font-size: 12.5px;
        color: #333;
      }}
      strong {{ color: #222; }}
      .actions {{
        margin: 22px 0 18px;
      }}
      a.btn {{
        display: inline-block;
        padding: 9px 18px;
        border-radius: 6px;
        font-size: 13.5px;
        font-weight: 600;
        text-decoration: none;
        margin-right: 8px;
      }}
      a.btn-primary {{
        background: #0f62fe;
        color: #ffffff;
        border: 1px solid #0f62fe;
      }}
      a.btn-secondary {{
        background: #ffffff;
        color: #0f62fe;
        border: 1px solid #c6d0e3;
      }}
      hr {{
        border: none;
        border-top: 1px solid #eef0f3;
        margin: 20px 0;
      }}
      ol {{
        margin: 0;
        padding-left: 22px;
        color: #666;
      }}
      li {{
        font-size: 13.5px;
        line-height: 1.75;
        margin: 2px 0;
      }}
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Serve WebView2 per avviare l&apos;interfaccia</h1>
      <p>
        El Sbobinator sta usando il renderer Windows legacy <code>MSHTML</code>,
        che non supporta la WebUI moderna. Per questo la finestra rimane nera.
      </p>
      <p>
        Installa <strong>Microsoft Edge WebView2 Runtime</strong>
        per avviare l&apos;app normalmente.
      </p>
      <div class="actions">
        <a class="btn btn-primary" href="{escape(download_url)}">Scarica WebView2 Runtime</a>
        <a class="btn btn-secondary" href="{escape(repo_url)}">Dettagli tecnici</a>
      </div>
      <hr />
      <ol>
        <li>Chiudi El Sbobinator.</li>
        <li>Installa WebView2 Runtime.</li>
        <li>Riapri l&apos;app.</li>
      </ol>
    </div>
  </body>
</html>
"""


def main():  # noqa: C901
    from el_sbobinator.app_webview import ElSbobinatorApi

    api = ElSbobinatorApi()

    # Intercept stdout/stderr to forward to React console
    sys.stdout = _ConsoleTee(sys.__stdout__, api)
    sys.stderr = _ConsoleTee(sys.__stderr__, api)

    dist_path = get_dist_path()
    webview2_available = has_webview2_runtime()

    # Storage path for WebView2 profile cache (avoids re-init freeze)
    storage_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "El Sbobinator",
        "webview_cache",
    )
    os.makedirs(storage_dir, exist_ok=True)

    # Auto cache-bust: clear WebView2 HTTP caches when a new build/version is detected.
    # In onefile PyInstaller mode the extracted files get a new mtime on every launch
    # (new _MEI temp folder), so we use the EXE's own mtime instead — stable until the
    # user installs a new version.
    # IMPORTANT: only delete Cache dirs, NOT the full EBWebView profile — doing so would
    # destroy localStorage (queue, editor sessions) on every restart.
    try:
        import shutil

        mtime_file = os.path.join(storage_dir, ".build_mtime")
        if getattr(sys, "frozen", False):
            current_mtime = str(os.path.getmtime(sys.executable))
        else:
            current_mtime = str(os.path.getmtime(dist_path))
        stored_mtime = ""
        if os.path.exists(mtime_file):
            with open(mtime_file, "r", encoding="utf-8") as _f:
                stored_mtime = _f.read().strip()
        if stored_mtime != current_mtime:
            default_profile = os.path.join(storage_dir, "EBWebView", "Default")
            _cleared = False
            _failed = False
            for cache_name in ("Cache", "Code Cache"):
                cache_dir = os.path.join(default_profile, cache_name)
                if os.path.exists(cache_dir):
                    try:
                        shutil.rmtree(cache_dir)
                        _cleared = True
                    except Exception as _e:
                        _failed = True
                        print(
                            f"[!] Impossibile svuotare cache WebView2 ({cache_name}): {_e}"
                        )
            if _cleared:
                print("[*] Cache WebView2 svuotata (nuova build rilevata).")
            if not _failed:
                with open(mtime_file, "w", encoding="utf-8") as _f:
                    _f.write(current_mtime)
    except Exception:
        pass

    # Center the window on screen
    win_w, win_h = 900, 820
    try:
        if sys.platform == "win32":
            import ctypes

            scr_w = ctypes.windll.user32.GetSystemMetrics(0)
            scr_h = ctypes.windll.user32.GetSystemMetrics(1)
        else:
            scr_w, scr_h = 1920, 1080
        center_x = max(0, (scr_w - win_w) // 2)
        center_y = max(0, (scr_h - win_h) // 2)
    except Exception:
        center_x, center_y = 100, 50

    if webview2_available:
        window = webview.create_window(
            "El Sbobinator",
            dist_path,
            js_api=api,
            width=win_w,
            height=win_h,
            x=center_x,
            y=center_y,
            min_size=(750, 620),
            background_color="#18181b",
        )
    else:
        print(
            "[!] Microsoft Edge WebView2 Runtime non trovato. Mostro schermata di recupero."
        )
        window = webview.create_window(
            "El Sbobinator",
            html=build_missing_webview2_html(),
            width=win_w,
            height=win_h,
            x=center_x,
            y=center_y,
            min_size=(750, 620),
            background_color="#18181b",
        )
    api.set_window(window)

    def _on_closing():
        LocalMediaServer.shutdown_all()

    window.events.closing += _on_closing

    try:
        from webview.dom import _dnd_state

        _dnd_state["num_listeners"] += 1
    except Exception:
        pass

    webview.start(
        private_mode=False,
        storage_path=storage_dir,
    )


if __name__ == "__main__":
    main()
