"""
Entrypoint principale compatibile con PyInstaller.

La UI legacy CustomTkinter e' stata ritirata: questo launcher apre la WebUI.
"""

from el_sbobinator.app_webview import main


if __name__ == "__main__":
    main()

