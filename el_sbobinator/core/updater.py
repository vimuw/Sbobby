"""
Auto-update logic for El Sbobinator.

Downloads the platform-appropriate release asset from GitHub, launches the
installer (Windows) or mounts + copies the DMG (macOS), then schedules
a short-delay quit so the webview window closes cleanly.
"""

from __future__ import annotations

import os
import plistlib
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import certifi


def download_and_install_update(version: str) -> dict:
    """Download the correct installer for this OS, launch it, then quit the app."""
    if not isinstance(version, str) or not version:
        return {"ok": False, "error": "Versione non valida."}

    version_clean = version.lstrip("v")

    if sys.platform == "win32":
        filename = f"El-Sbobinator-Setup-v{version_clean}.exe"
        suffix = ".exe"
    elif sys.platform == "darwin":
        filename = f"El-Sbobinator-v{version_clean}.dmg"
        suffix = ".dmg"
    else:
        return {"ok": False, "error": f"Piattaforma non supportata: {sys.platform}"}

    url = (
        f"https://github.com/vimuw/El-Sbobinator/releases/download/{version}/{filename}"
    )

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
        _ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(url, timeout=120, context=_ssl_ctx) as resp:
            with open(tmp_path, "wb") as fh:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    fh.write(chunk)
    except Exception as e:
        return {"ok": False, "error": f"Download fallito: {e}"}

    try:
        if sys.platform == "win32":
            os.startfile(tmp_path)  # type: ignore[attr-defined]

            def _cleanup_installer(path: str) -> None:
                for _ in range(3):
                    time.sleep(5)
                    try:
                        os.unlink(path)
                        return
                    except PermissionError:
                        pass
                    except OSError:
                        return

            threading.Thread(
                target=_cleanup_installer, args=(tmp_path,), daemon=True
            ).start()
        else:
            try:
                result = subprocess.run(
                    ["hdiutil", "attach", "-nobrowse", "-plist", tmp_path],
                    capture_output=True,
                    check=True,
                    timeout=30,
                )
                plist = plistlib.loads(result.stdout)
                mount_point = None
                for entity in plist.get("system-entities", []):
                    mp = entity.get("mount-point")
                    if mp:
                        mount_point = mp
                        break
                if not mount_point:
                    return {"ok": False, "error": "Impossibile montare il DMG."}
                try:
                    app_src = os.path.join(mount_point, "El Sbobinator.app")
                    app_dst = "/Applications/El Sbobinator.app"
                    subprocess.run(
                        ["cp", "-R", app_src, app_dst], check=True, timeout=30
                    )
                    subprocess.run(
                        ["xattr", "-dr", "com.apple.quarantine", app_dst],
                        check=False,
                        timeout=30,
                    )
                finally:
                    subprocess.run(
                        ["hdiutil", "detach", mount_point], check=False, timeout=30
                    )
                subprocess.Popen(["open", "/Applications/El Sbobinator.app"])
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
    except Exception as e:
        return {"ok": False, "error": f"Installazione fallita: {e}"}

    def _delayed_destroy() -> None:
        time.sleep(0.8)
        try:
            import webview  # type: ignore

            if webview.windows:
                webview.windows[0].destroy()
        except Exception:
            pass

    threading.Thread(target=_delayed_destroy, daemon=True).start()
    return {"ok": True}
