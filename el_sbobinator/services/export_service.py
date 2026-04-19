"""
Final export helpers for El Sbobinator.

This keeps the HTML/Markdown assembly logic out of the main pipeline loop.
"""

from __future__ import annotations

import os
import re

from el_sbobinator.html_export import build_html_document, normalize_inline_star_lists
from el_sbobinator.shared import _atomic_write_text


def load_revised_blocks(phase2_revised_dir: str, read_text) -> list[str]:
    blocks: list[str] = []
    try:
        if os.path.isdir(phase2_revised_dir):
            rev_files = []
            for filename in os.listdir(phase2_revised_dir):
                if re.match(r"^rev_\d{3}\.md$", filename):
                    rev_files.append(os.path.join(phase2_revised_dir, filename))
            for path in sorted(rev_files):
                blocks.append(read_text(path))
    except Exception:
        return []
    return blocks


def build_final_markdown(title: str, blocks: list[str], fallback_body: str) -> str:
    normalized_blocks = [block.strip() for block in blocks if block and block.strip()]
    if not normalized_blocks:
        normalized_blocks = [str(fallback_body or "").strip()]

    body_md = "\n\n".join(normalized_blocks).strip()
    final_md = f"# {title}\n\n{body_md}\n"
    return normalize_inline_star_lists(final_md)


def write_final_html(html_path: str, title: str, final_markdown: str) -> None:
    html_doc = build_html_document(title, final_markdown)
    _atomic_write_text(html_path, html_doc)


def resolve_output_html_path(
    input_path: str,
    output_dir: str,
    fallback_output_dir: str,
    safe_output_basename,
) -> tuple[str, str]:
    base_name = os.path.basename(input_path)
    nome_puro = os.path.splitext(base_name)[0] if base_name else ""
    titolo = safe_output_basename(nome_puro) if nome_puro else "Sbobina"
    html_path = os.path.join(output_dir, f"{titolo}_Sbobina.html")
    if not base_name:
        html_path = os.path.join(fallback_output_dir, "Sbobina_Definitiva.html")
    return titolo, html_path


def export_final_html_document(
    input_path: str,
    phase2_revised_dir: str,
    fallback_body: str,
    read_text,
    output_dir: str,
    fallback_output_dir: str,
    safe_output_basename,
) -> tuple[str, str]:
    titolo, html_path = resolve_output_html_path(
        input_path=input_path,
        output_dir=output_dir,
        fallback_output_dir=fallback_output_dir,
        safe_output_basename=safe_output_basename,
    )
    blocks = load_revised_blocks(phase2_revised_dir, read_text)
    final_md = build_final_markdown(titolo, blocks, fallback_body)
    write_final_html(html_path, titolo, final_md)
    return titolo, html_path
