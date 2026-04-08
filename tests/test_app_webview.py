import tempfile
import threading
import unittest
from unittest.mock import patch

from el_sbobinator.app_webview import ElSbobinatorApi, PipelineAdapter


class _FakeWindow:
    def __init__(self):
        self.calls = []
        self.dialog_result = None

    def evaluate_js(self, script):
        self.calls.append(script)

    def create_file_dialog(self, *_args, **_kwargs):
        return self.dialog_result


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

    def test_ask_media_file_accepts_string_dialog_result(self):
        api = ElSbobinatorApi()
        window = _FakeWindow()
        with tempfile.NamedTemporaryFile("wb", suffix=".mp3", delete=False) as tmp:
            window.dialog_result = tmp.name
        api.set_window(window)

        result = api.ask_media_file()

        self.assertIsNotNone(result)
        self.assertEqual(result["path"], window.dialog_result)
        self.assertEqual(result["name"], __import__("os").path.basename(window.dialog_result))

    def test_ask_files_accepts_string_dialog_result(self):
        api = ElSbobinatorApi()
        window = _FakeWindow()
        with tempfile.NamedTemporaryFile("wb", suffix=".mp3", delete=False) as tmp:
            window.dialog_result = tmp.name
        api.set_window(window)

        result = api.ask_files()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["path"], window.dialog_result)
        self.assertEqual(result[0]["name"], __import__("os").path.basename(window.dialog_result))

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

    @patch("el_sbobinator.app_webview.cleanup_orphan_sessions")
    def test_cleanup_old_sessions_uses_14_day_default(self, mock_cleanup):
        api = ElSbobinatorApi()
        mock_cleanup.return_value = {"removed": 2, "freed_bytes": 4096, "errors": 0}

        result = api.cleanup_old_sessions()

        self.assertTrue(result["ok"])
        self.assertEqual(result["removed"], 2)
        mock_cleanup.assert_called_once_with(14)

    def test_stop_processing_unblocks_pending_prompts(self):
        api = ElSbobinatorApi()
        regenerate_event = threading.Event()
        new_key_event = threading.Event()
        received = {}

        def on_regenerate(payload):
            received["regenerate"] = payload
            regenerate_event.set()

        def on_new_key(payload):
            received["new_key"] = payload
            new_key_event.set()

        api._adapter.ask_regenerate("lesson.mp3", on_regenerate, "resume")
        api._adapter.ask_new_api_key(on_new_key)

        result = api.stop_processing()

        self.assertTrue(result["ok"])
        self.assertTrue(api._cancel_event.is_set())
        self.assertTrue(regenerate_event.wait(timeout=1))
        self.assertTrue(new_key_event.wait(timeout=1))
        self.assertEqual(received["regenerate"], {"regenerate": False})
        self.assertEqual(received["new_key"], {"key": ""})

    def test_answer_regenerate_none_cancels_processing_and_preserves_null(self):
        api = ElSbobinatorApi()
        regenerate_event = threading.Event()
        received = {}

        def on_regenerate(payload):
            received["regenerate"] = payload
            regenerate_event.set()

        api._adapter.ask_regenerate("lesson.mp3", on_regenerate, "resume")

        result = api.answer_regenerate(None)

        self.assertTrue(result["ok"])
        self.assertTrue(api._cancel_event.is_set())
        self.assertTrue(regenerate_event.wait(timeout=1))
        self.assertEqual(received["regenerate"], {"regenerate": None})

    @patch("el_sbobinator.pipeline.esegui_sbobinatura")
    def test_process_done_marks_cancelled_when_run_status_is_cancelled(self, mock_pipeline_run):
        api = ElSbobinatorApi()
        emitted = []

        def fake_emit(fn_name, data, batched=None):
            emitted.append((fn_name, data, batched))

        def fake_pipeline_run(_path, _api_key, adapter, resume_session=True):
            self.assertTrue(resume_session)
            adapter.set_run_result("cancelled", "Prompt di ripresa chiuso.")

        mock_pipeline_run.side_effect = fake_pipeline_run
        api._adapter.emit = fake_emit

        with tempfile.NamedTemporaryFile("wb", suffix=".mp3", delete=False) as tmp:
            tmp.write(b"fake")
            file_path = tmp.name

        try:
            result = api.start_processing(
                [{
                    "id": "file-1",
                    "path": file_path,
                    "name": "lesson.mp3",
                    "size": 4,
                    "duration": 1,
                }],
                api_key="fake-key",
                resume_session=True,
            )

            self.assertTrue(result["ok"])
            self.assertIsNotNone(api._processing_thread)
            api._processing_thread.join(timeout=2)
            self.assertFalse(api._processing_thread.is_alive(), "Il thread di processing non si e' fermato.")
        finally:
            try:
                __import__("os").unlink(file_path)
            except OSError:
                pass

        process_done_events = [data for fn_name, data, _batched in emitted if fn_name == "processDone"]
        self.assertEqual(len(process_done_events), 1)
        self.assertTrue(process_done_events[0]["cancelled"])
        self.assertEqual(process_done_events[0]["completed"], 0)
        self.assertEqual(process_done_events[0]["failed"], 0)
        self.assertEqual(process_done_events[0]["total"], 1)


if __name__ == "__main__":
    unittest.main()
