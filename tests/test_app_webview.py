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
        import tempfile as _tempfile
        api = ElSbobinatorApi()
        with _tempfile.NamedTemporaryFile("w+", suffix=".html", delete=False, encoding="utf-8") as tmp:
            tmp.write(
                "<!DOCTYPE html><html><head><meta charset='utf-8'><style>body{color:red}</style></head>"
                "<body><p>Old</p></body></html>"
            )
            path = tmp.name

        with patch("el_sbobinator.app_webview.get_desktop_dir", return_value=_tempfile.gettempdir()):
            result = api.save_html_content(path, "<p>New</p>")
        self.assertTrue(result["ok"])

        with open(path, "r", encoding="utf-8") as fh:
            saved = fh.read()

        self.assertIn("<style>body{color:red}</style>", saved)
        self.assertIn("<body>\n<p>New</p>\n</body>", saved)

    def test_open_url_rejects_non_allowlisted_url(self):
        api = ElSbobinatorApi()
        result = api.open_url("https://evil.example.com/payload")
        self.assertFalse(result["ok"])

    def test_open_url_rejects_filesystem_path(self):
        api = ElSbobinatorApi()
        result = api.open_url("C:\\Windows\\System32\\cmd.exe")
        self.assertFalse(result["ok"])

    @patch("el_sbobinator.app_webview.open_path_with_default_app")
    def test_open_url_accepts_allowed_github_url(self, mock_open):
        api = ElSbobinatorApi()
        result = api.open_url("https://github.com/vimuw/El-Sbobinator/releases/latest")
        self.assertTrue(result["ok"])
        mock_open.assert_called_once()

    def test_save_html_content_rejects_non_html_path(self):
        api = ElSbobinatorApi()
        result = api.save_html_content("/etc/passwd", "<p>hack</p>")
        self.assertFalse(result["ok"])

    def test_save_html_content_rejects_missing_file(self):
        api = ElSbobinatorApi()
        result = api.save_html_content("/tmp/nonexistent_file_xyz.html", "<p>x</p>")
        self.assertFalse(result["ok"])

    @patch("el_sbobinator.validation_service.validate_environment")
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
