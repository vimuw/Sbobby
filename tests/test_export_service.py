import os
import tempfile
import unittest

from el_sbobinator.services.export_service import (
    export_final_html_document,
    resolve_output_html_path,
)


class ExportServiceTests(unittest.TestCase):
    def test_resolve_output_html_path_uses_audio_name(self):
        titolo, html_path = resolve_output_html_path(
            input_path="lesson.mp3",
            output_dir="C:/tmp",
            fallback_output_dir="C:/fallback",
            safe_output_basename=lambda value: value,
        )
        self.assertEqual(titolo, "lesson")
        self.assertTrue(html_path.endswith("lesson_Sbobina.html"))

    def test_export_final_html_document_writes_html(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            revised_dir = os.path.join(tmpdir, "revised")
            os.makedirs(revised_dir, exist_ok=True)
            with open(
                os.path.join(revised_dir, "rev_001.md"), "w", encoding="utf-8"
            ) as handle:
                handle.write("## Titolo\n\nCorpo di test")

            def read_text(path: str) -> str:
                with open(path, encoding="utf-8") as handle:
                    return handle.read()

            _, html_path = export_final_html_document(
                input_path="lesson.mp3",
                phase2_revised_dir=revised_dir,
                fallback_body="fallback",
                read_text=read_text,
                output_dir=tmpdir,
                fallback_output_dir=tmpdir,
                safe_output_basename=lambda value: value,
            )

            self.assertTrue(os.path.exists(html_path))


if __name__ == "__main__":
    unittest.main()
