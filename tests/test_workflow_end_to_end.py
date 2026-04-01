import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from el_sbobinator.app_webview import ElSbobinatorApi


class _FakeWindow:
    def __init__(self):
        self.calls = []

    def evaluate_js(self, script):
        self.calls.append(script)


class _FakeModels:
    def get(self, model=None, **kwargs):
        return {"model": model}


class _FakeClient:
    def __init__(self, api_key=None, **kwargs):
        self.api_key = api_key
        self.models = _FakeModels()


class WorkflowEndToEndTests(unittest.TestCase):
    def test_start_processing_emits_file_done_and_process_done(self):
        api = ElSbobinatorApi()
        window = _FakeWindow()
        api.set_window(window)

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.mp3")
            output_path = os.path.join(tmpdir, "output.html")
            with open(input_path, "wb") as handle:
                handle.write(b"fake")

            def fake_pipeline(file_path, api_key, adapter, **kwargs):
                with open(output_path, "w", encoding="utf-8") as handle:
                    handle.write("<html><body>ok</body></html>")
                adapter.imposta_output_html(output_path)
                adapter.set_run_result("completed")

            files = [{"id": "file-1", "path": input_path, "name": "input.mp3", "size": 4, "duration": 1.0}]
            with patch("google.genai.Client", _FakeClient), patch("el_sbobinator.pipeline.esegui_sbobinatura", side_effect=fake_pipeline):
                result = api.start_processing(files, "fake-key", resume_session=True)
                self.assertTrue(result["ok"])
                self.assertIsNotNone(api._processing_thread)
                api._processing_thread.join(timeout=5)
                api._adapter._dispatcher.flush()

            joined = "\n".join(window.calls)
            self.assertIn("fileDone", joined)
            self.assertIn("processDone", joined)

    def test_start_processing_marks_current_file_failed_on_fatal_exception(self):
        api = ElSbobinatorApi()
        window = _FakeWindow()
        api.set_window(window)

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.mp3")
            with open(input_path, "wb") as handle:
                handle.write(b"fake")

            files = [{"id": "file-1", "path": input_path, "name": "input.mp3", "size": 4, "duration": 1.0}]
            with patch("google.genai.Client", _FakeClient), patch(
                "el_sbobinator.pipeline.esegui_sbobinatura",
                side_effect=RuntimeError("boom"),
            ):
                result = api.start_processing(files, "fake-key", resume_session=True)
                self.assertTrue(result["ok"])
                self.assertIsNotNone(api._processing_thread)
                api._processing_thread.join(timeout=5)
                api._adapter._dispatcher.flush()

            joined = "\n".join(window.calls)
            self.assertIn("fileFailed", joined)
            self.assertIn("\"error\": \"boom\"", joined)
            self.assertIn("\"failed\": 1", joined)


if __name__ == "__main__":
    unittest.main()
