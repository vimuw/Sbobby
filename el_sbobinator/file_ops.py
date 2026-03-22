"""
File-system helpers shared by the WebView backend.
"""

from __future__ import annotations

import os
import re
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
    body_re = re.compile(r"(?is)(<body\b[^>]*>)(.*?)(</body>)")
    if body_re.search(original_html):
        updated_html = body_re.sub(
            lambda match: f"{match.group(1)}\n{body_inner}\n{match.group(3)}",
            original_html,
            count=1,
        )
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
    if not target_path.lower().endswith(".doc") and not target_path.lower().endswith(".docx"):
        target_path += ".doc"

    with open(target_path, "w", encoding="utf-8") as handle:
        handle.write(doc_html)
    return target_path
