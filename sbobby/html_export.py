"""
Markdown -> HTML export utilities for Sbobby.

Used for local HTML output (copy/paste into Docs) with basic sanitization.
"""

from __future__ import annotations

import html as _html
import re

import markdown


def sanitize_html_basic(html: str) -> str:
    # Sanitizzazione di base (difensiva) nel caso l'AI inserisca HTML pericoloso.
    html = re.sub(r"(?is)<script\b.*?>.*?</script>", "", html or "")
    html = re.sub(r"(?is)<(iframe|object|embed)\b.*?>.*?</\1>", "", html)
    html = re.sub(r"(?is)<(style)\b.*?>.*?</\1>", "", html)
    html = re.sub(r"(?is)<(meta|link|base)\b.*?>", "", html)
    html = re.sub(r"(?i)\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", html)
    html = re.sub(r"(?i)javascript:", "", html)
    return html


def normalize_inline_star_lists(md: str) -> str:
    # Normalizza elenchi che a volte l'AI produce in modo non-standard.
    # Obiettivo: farli diventare liste Markdown reali, senza interpretare '*' come testo.
    src = (md or "").replace("\u00A0", " ")

    list_line_re = r"^\s*([*+-]|\d+\.)\s+"
    # Bullet unicode che il modello usa spesso (e che Markdown non interpreta come liste).
    bullet_top = ("\u25cf", "\u2022", "\u25aa", "\u2023")  # ● • ▪ ‣
    bullet_sub = ("\u25e6", "\u25cb", "\u2219")  # ◦ ○ ∙

    # 1) Trasforma elenchi in-line tipo "Esempi: * Voce1 ... * Voce2 ..."
    out_lines = []
    in_fence = False
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence:
            out_lines.append(line)
            continue

        # Caso A: riga che INIZIA con bullet unicode -> lista Markdown.
        if not re.match(list_line_re, line):
            m = re.match(r"^(\s*)([\u25cf\u2022\u25aa\u2023\u25e6\u25cb\u2219])\s+(.*)$", line)
            if m:
                bullet = m.group(2)
                rest = m.group(3).strip()
                if rest:
                    prefix = "- " if bullet in bullet_top else "    - "
                    out_lines.append(prefix + rest)
                    continue

        # Caso B: bullet unicode "in mezzo" a una riga -> spezza in lista.
        if not re.match(list_line_re, line) and re.search(r"[\u25cf\u2022\u25aa\u2023]\s+(\*\*|[A-ZÀ-ÖØ-Ý])", line):
            if re.search(r"\s[\u25cf\u2022\u25aa\u2023]\s+", line):
                parts = re.split(r"\s*[\u25cf\u2022\u25aa\u2023]\s+", line)
                if len(parts) > 1:
                    first = (parts[0] or "").rstrip()
                    if first:
                        out_lines.append(first)
                    for item in parts[1:]:
                        item = (item or "").strip()
                        if item:
                            out_lines.append("- " + item)
                    continue

        # Converti solo se:
        # - c'e' un ":" seguito da "* " (tipico "Esempi: * ... * ...")
        if not re.match(r"^\s*([*+-]|\d+\.)\s+", line) and re.search(r":[ \t]*\*[ \t]+(\*\*|[A-ZÀ-ÖØ-Ý])", line):
            if line.count("* ") >= 1:
                line2 = re.sub(r":[ \t]*\*[ \t]+", ":\n\n- ", line, count=1)
                line2 = re.sub(r"[ \t]+\*[ \t]+", "\n- ", line2)
                out_lines.extend(line2.splitlines())
                continue

        out_lines.append(line)

    mid = "\n".join(out_lines)

    # 2) Python-Markdown spesso richiede una riga vuota prima di una lista per riconoscerla.
    fixed = []
    in_fence = False
    for line in mid.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            fixed.append(line)
            continue
        if in_fence:
            fixed.append(line)
            continue

        is_list = bool(re.match(r"^\s{0,3}([*+-]|\d+\.)\s+", line))
        if is_list and fixed:
            prev = fixed[-1]
            prev_is_list = bool(re.match(r"^\s{0,3}([*+-]|\d+\.)\s+", prev))
            if prev.strip() != "" and not prev_is_list:
                fixed.append("")

        fixed.append(line)

    return "\n".join(fixed)


def build_html_document(title: str, markdown_text: str) -> str:
    html_body = markdown.markdown(markdown_text or "", extensions=["extra", "sane_lists"], output_format="html5")
    html_body = sanitize_html_basic(html_body)
    safe_title = (title or "Sbobina").strip()
    safe_title_html = _html.escape(safe_title, quote=True)
    # CSP: evita script e richieste di rete anche se l'AI inserisse tag HTML.
    csp = (
        "default-src 'none'; "
        "base-uri 'none'; "
        "form-action 'none'; "
        "frame-ancestors 'none'; "
        "connect-src 'none'; "
        "img-src data:; "
        "font-src data:; "
        "media-src 'none'; "
        "style-src 'unsafe-inline'"
    )
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="Content-Security-Policy" content="{csp}" />
  <meta http-equiv="Referrer-Policy" content="no-referrer" />
  <title>{safe_title_html} - Sbobina</title>
  <style>
    :root {{
      --text: #111;
      --muted: #444;
      --bg: #fff;
      --rule: #e6e6e6;
    }}
    body {{
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.6;
      color: var(--text);
      background: var(--bg);
      max-width: 980px;
      margin: 0 auto;
      padding: 48px 22px;
    }}
    h1 {{ font-size: 2.0rem; margin: 0 0 0.9rem; }}
    h2 {{ font-size: 1.35rem; margin: 1.6rem 0 0.6rem; }}
    h3 {{ font-size: 1.15rem; margin: 1.1rem 0 0.45rem; }}
    p, li {{ margin: 0.55rem 0; }}
    ul, ol {{ padding-left: 1.25rem; }}
    strong {{ font-weight: 700; }}
    hr {{ display: none; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; font-size: 0.95em; }}
    blockquote {{ margin: 0.9rem 0; padding: 0.1rem 0 0.1rem 1rem; border-left: 3px solid var(--rule); color: var(--muted); }}
  </style>
</head>
<body>
{html_body}
</body>
</html>
"""
