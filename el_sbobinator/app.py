"""
Legacy compatibility shim.

The old CustomTkinter desktop UI has been retired. This module intentionally
keeps the import path alive so existing launchers do not break, but it now
delegates to the WebUI runtime.
"""

from __future__ import annotations

from el_sbobinator.app_webview import main as run_webui


def main() -> None:
    run_webui()


class ElSbobinatorApp:
    """
    Backward-compatible shim for callers still importing ElSbobinatorApp.

    `mainloop()` simply starts the WebUI version of the application.
    """

    def mainloop(self) -> None:
        run_webui()
