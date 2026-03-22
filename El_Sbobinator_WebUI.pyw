"""
Entrypoint PyWebView (compatibile con PyInstaller).

La logica dell'app vive in `el_sbobinator/app_webview.py` per mantenere il progetto modulare.
"""

from el_sbobinator.app_webview import main


if __name__ == "__main__":
    main()
