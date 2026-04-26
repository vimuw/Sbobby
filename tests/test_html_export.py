import unittest

from el_sbobinator.utils.html_export import (
    build_html_document,
    normalize_heading_levels,
    normalize_inline_star_lists,
)


class NormalizeInlineStarListsTests(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(normalize_inline_star_lists(""), "")

    def test_none_treated_as_empty(self):
        self.assertEqual(normalize_inline_star_lists(None), "")  # type: ignore[arg-type]

    def test_plain_text_unchanged(self):
        text = "Hello world\nAnother line"
        self.assertEqual(normalize_inline_star_lists(text), text)

    def test_unicode_bullet_at_line_start_converted_to_list(self):
        md = "\u25cf Voce uno\n\u25cf Voce due"
        result = normalize_inline_star_lists(md)
        self.assertIn("- Voce uno", result)
        self.assertIn("- Voce due", result)

    def test_unicode_sub_bullet_at_line_start(self):
        md = "\u25e6 Sub-voce"
        result = normalize_inline_star_lists(md)
        self.assertIn("- Sub-voce", result)

    def test_unicode_bullet_with_empty_rest_not_converted(self):
        md = "\u25cf "
        result = normalize_inline_star_lists(md)
        self.assertNotIn("- ", result)

    def test_inline_bullets_split_into_separate_lines(self):
        md = "Esempi: \u25cf Alpha \u25cf Beta"
        result = normalize_inline_star_lists(md)
        self.assertIn("- Alpha", result)
        self.assertIn("- Beta", result)

    def test_colon_star_normalization(self):
        md = "Esempi: * Voce1 * Voce2"
        result = normalize_inline_star_lists(md)
        self.assertIn("- Voce1", result)
        self.assertIn("- Voce2", result)

    def test_blank_line_inserted_before_list_after_text(self):
        md = "Testo normale\n- Voce lista"
        result = normalize_inline_star_lists(md)
        lines = result.splitlines()
        list_idx = next(i for i, l in enumerate(lines) if l.startswith("- "))
        self.assertEqual(lines[list_idx - 1], "")

    def test_no_blank_line_inserted_between_consecutive_list_items(self):
        md = "- Voce uno\n- Voce due\n- Voce tre"
        result = normalize_inline_star_lists(md)
        lines = result.splitlines()
        self.assertNotIn("", lines)

    def test_fenced_code_block_preserved_unchanged(self):
        md = "```\n\u25cf non convertire\n* non convertire\n```"
        result = normalize_inline_star_lists(md)
        self.assertIn("\u25cf non convertire", result)
        self.assertIn("* non convertire", result)

    def test_nbsp_replaced_before_processing(self):
        md = "\u00a0testo"
        result = normalize_inline_star_lists(md)
        self.assertIn(" testo", result)


class NormalizeHeadingLevelsTests(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(normalize_heading_levels(""), "")

    def test_none_treated_as_empty(self):
        self.assertEqual(normalize_heading_levels(None), "")  # type: ignore[arg-type]

    def test_h1_to_h5_unchanged(self):
        for level in range(1, 6):
            hashes = "#" * level
            md = f"{hashes} Titolo"
            result = normalize_heading_levels(md)
            self.assertIn(f"{hashes} Titolo", result)

    def test_h6_clamped_to_h5(self):
        result = normalize_heading_levels("###### Profondo")
        self.assertIn("##### Profondo", result)
        self.assertNotIn("######", result)

    def test_h7_clamped_to_h5(self):
        result = normalize_heading_levels("####### Molto profondo")
        self.assertIn("##### Molto profondo", result)

    def test_indented_heading_preserved(self):
        result = normalize_heading_levels("  ## Titolo indentato")
        self.assertIn("## Titolo indentato", result)

    def test_non_heading_lines_unchanged(self):
        md = "Testo normale\n**grassetto**\n- lista"
        result = normalize_heading_levels(md)
        self.assertEqual(result, md)

    def test_fenced_code_block_skipped(self):
        md = "```\n###### non toccare\n```"
        result = normalize_heading_levels(md)
        self.assertIn("###### non toccare", result)

    def test_fence_toggle_with_content_after(self):
        md = "```\n###### dentro\n```\n###### fuori"
        result = normalize_heading_levels(md)
        self.assertIn("###### dentro", result)
        self.assertIn("##### fuori", result)

    def test_trailing_spaces_stripped_from_heading_content(self):
        result = normalize_heading_levels("## Titolo  ")
        self.assertIn("## Titolo", result)
        self.assertNotIn("Titolo  ", result)


class BuildHtmlDocumentTests(unittest.TestCase):
    def test_output_is_valid_html_shell(self):
        result = build_html_document("Test", "# Ciao")
        self.assertTrue(result.strip().startswith("<!DOCTYPE html>"))
        self.assertIn("<html", result)
        self.assertIn("</html>", result)

    def test_title_appears_in_head(self):
        result = build_html_document("Lezione 1", "contenuto")
        self.assertIn("Lezione 1", result)

    def test_empty_title_defaults_to_sbobina(self):
        result = build_html_document("", "contenuto")
        self.assertIn("Sbobina", result)

    def test_none_title_defaults_to_sbobina(self):
        result = build_html_document(None, "contenuto")  # type: ignore[arg-type]
        self.assertIn("Sbobina", result)

    def test_markdown_heading_rendered_as_html(self):
        result = build_html_document("T", "## Sezione\n\nTesto qui.")
        self.assertIn("<h2>", result)
        self.assertIn("Sezione", result)

    def test_xss_title_escaped(self):
        result = build_html_document('<script>alert("xss")</script>', "body")
        self.assertNotIn("<script>", result)

    def test_csp_meta_present(self):
        result = build_html_document("T", "body")
        self.assertIn("Content-Security-Policy", result)

    def test_body_content_in_output(self):
        result = build_html_document("T", "Paragrafo semplice")
        self.assertIn("Paragrafo semplice", result)

    def test_none_markdown_produces_empty_body(self):
        result = build_html_document("T", None)  # type: ignore[arg-type]
        self.assertIn("<body>", result)


if __name__ == "__main__":
    unittest.main()
