import tempfile
import unittest
from unittest.mock import patch

from el_sbobinator.app_webview import ElSbobinatorApi, PipelineAdapter


class _FakeWindow:
    def __init__(self):
        self.calls = []

    def evaluate_js(self, script):
        self.calls.append(script)


class AppWebviewTests(unittest.TestCase):
    def test_dispatcher_batches_js_calls(self):
        window = _FakeWindow()
        adapter = PipelineAdapter(window, cancel_event=__import__("threading").Event())

        adapter.aggiorna_progresso(0.5)
        adapter.aggiorna_fase("fase 1")
        adapter.emit("fileDone", {"id": "abc"}, batched=False)
        adapter._dispatcher.flush()

        joined = "\n".join(window.calls)
        self.assertIn("updateProgress", joined)
        self.assertIn("updatePhase", joined)
        self.assertIn("fileDone", joined)

    def test_save_html_content_preserves_head(self):
        api = ElSbobinatorApi()
        with tempfile.NamedTemporaryFile("w+", suffix=".html", delete=False, encoding="utf-8") as tmp:
            tmp.write(
                "<!DOCTYPE html><html><head><meta charset='utf-8'><style>body{color:red}</style></head>"
                "<body><p>Old</p></body></html>"
            )
            path = tmp.name

        result = api.save_html_content(path, "<p>New</p>")
        self.assertTrue(result["ok"])

        with open(path, "r", encoding="utf-8") as fh:
            saved = fh.read()

        self.assertIn("<style>body{color:red}</style>", saved)
        self.assertIn("<body>\n<p>New</p>\n</body>", saved)

    @patch("el_sbobinator.app_webview.validate_environment")
    def test_validate_environment_returns_backend_result(self, mock_validate):
        api = ElSbobinatorApi()
        mock_validate.return_value = {
            "ok": True,
            "summary": "Ambiente pronto.",
            "checks": [{"id": "ffmpeg", "label": "FFmpeg", "status": "ok", "message": "ok"}],
        }

        result = api.validate_environment(api_key="fake", check_api_key=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["summary"], "Ambiente pronto.")
        mock_validate.assert_called_once_with(api_key="fake", validate_api_key=True)


if __name__ == "__main__":
    unittest.main()
