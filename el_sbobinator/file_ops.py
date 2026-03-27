"""
File-system helpers shared by the WebView backend.
"""

from __future__ import annotations

import os
import sys


def open_path_with_default_app(path: str) -> None:
    if sys.platform == "win32":
        os.startfile(path)
        return

    import subprocess

    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def read_html_content(path: str) -> str:
    if not os.path.exists(path):
        raise FileNotFoundError("File non trovato.")
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def save_html_body_content(path: str, content: str) -> None:
    if not path or not os.path.exists(path):
        raise FileNotFoundError("File originale non trovato.")

    with open(path, "r", encoding="utf-8") as handle:
        original_html = handle.read()

    body_inner = str(content or "")
    html_lower = original_html.lower()
    body_open_end = html_lower.find("<body")
    body_close = -1
    if body_open_end != -1:
        body_open_end = html_lower.find(">", body_open_end)
        body_close = html_lower.rfind("</body>")
    if body_open_end != -1 and body_close != -1 and body_close > body_open_end:
        open_tag = original_html[: body_open_end + 1]
        close_tag = original_html[body_close:]
        updated_html = f"{open_tag}\n{body_inner}\n{close_tag}"
    else:
        updated_html = (
            "<!DOCTYPE html>\n"
            "<html>\n<head>\n<meta charset=\"utf-8\">\n</head>\n"
            f"<body>\n{body_inner}\n</body>\n</html>\n"
        )

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(updated_html)


def export_doc_html(path: str, doc_html: str) -> str:
    target_path = path
    if not target_path.lower().endswith(".docx"):
        if target_path.lower().endswith(".doc"):
            target_path += "x"
        else:
            target_path += ".docx"

    from html2docx import html2docx
    buf = html2docx(doc_html, title="Sbobina")
    with open(target_path, "wb") as handle:
        handle.write(buf.getvalue())
    return target_path
