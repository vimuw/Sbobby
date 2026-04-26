"""
File-system helpers shared by the WebView backend.
"""

from __future__ import annotations

import os
import sys
import threading

from el_sbobinator.utils.html_export import sanitize_html_basic

_html_write_locks: dict[str, threading.Lock] = {}
_html_last_gen: dict[str, int] = {}
_html_write_locks_meta = threading.Lock()


def _html_write_lock(path: str) -> threading.Lock:
    with _html_write_locks_meta:
        if path not in _html_write_locks:
            _html_write_locks[path] = threading.Lock()
        return _html_write_locks[path]


_ALLOWED_OPEN_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".html",
        ".htm",
        ".docx",
        ".doc",
        ".pdf",
        ".txt",
        ".md",
    }
)


def open_path_with_default_app(path: str) -> None:
    if not isinstance(path, str) or not path:
        raise ValueError("Path non valido.")

    # URLs bypass filesystem validation entirely
    if path.startswith("http://") or path.startswith("https://"):
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            import subprocess

            subprocess.Popen(["open", path])
        else:
            import subprocess

            subprocess.Popen(["xdg-open", path])
        return

    real = os.path.realpath(os.path.abspath(path))

    if not os.path.exists(real):
        raise FileNotFoundError(f"Percorso non trovato: {path!r}")

    if os.path.isfile(real):
        ext = os.path.splitext(real)[1].lower()
        if ext not in _ALLOWED_OPEN_EXTENSIONS:
            raise ValueError(f"Tipo di file non consentito: {ext!r}")
    # NOTE: Directories intentionally bypass extension checks.
    # open_file is only called with legitimate session directories from the bridge.

    if sys.platform == "win32":
        os.startfile(real)
        return

    import subprocess

    if sys.platform == "darwin":
        subprocess.Popen(["open", real])
    else:
        subprocess.Popen(["xdg-open", real])


def read_html_content(path: str) -> str:
    if not os.path.exists(path):
        raise FileNotFoundError("File non trovato.")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def extract_html_shell(html: str) -> tuple[str, str] | None:
    """Return (open_tag, close_tag) wrapping the <body> of *html*, or None."""
    html_lower = html.lower()
    body_open_end = html_lower.find("<body")
    if body_open_end == -1:
        return None
    body_open_end = html_lower.find(">", body_open_end)
    body_close = html_lower.rfind("</body>")
    if body_open_end == -1 or body_close == -1 or body_close <= body_open_end:
        return None
    return html[: body_open_end + 1], html[body_close:]


def save_html_body_content(
    path: str,
    content: str,
    shell: tuple[str, str] | None = None,
    generation: int | None = None,
) -> bool:
    """Write body content to *path*. Returns False (without writing) if *generation*
    is provided and an equal-or-newer generation has already been committed."""
    if not path or not os.path.exists(path):
        raise FileNotFoundError("File originale non trovato.")

    body_inner = sanitize_html_basic(str(content or ""))

    tmp_path = path + ".tmp"
    with _html_write_lock(path):
        if generation is not None and generation <= _html_last_gen.get(path, 0):
            return False
        if shell is not None:
            open_tag, close_tag = shell
        else:
            with open(path, encoding="utf-8") as handle:
                original_html = handle.read()
            extracted = extract_html_shell(original_html)
            if extracted is not None:
                open_tag, close_tag = extracted
            else:
                open_tag = close_tag = ""
        if open_tag and close_tag:
            updated_html = f"{open_tag}\n{body_inner}\n{close_tag}"
        else:
            updated_html = (
                "<!DOCTYPE html>\n"
                '<html>\n<head>\n<meta charset="utf-8">\n</head>\n'
                f"<body>\n{body_inner}\n</body>\n</html>\n"
            )
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.write(updated_html)
        os.replace(tmp_path, path)
        if generation is not None:
            _html_last_gen[path] = generation
    return True
