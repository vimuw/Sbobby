import os
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from el_sbobinator.pipeline import esegui_sbobinatura


class _FakeLogger:
    def info(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


class _FakeModels:
    def get(self, model=None, **kwargs):
        return {"model": model}


class _FakeClient:
    def __init__(self, api_key=None, **kwargs):
        self.api_key = api_key
        self.models = _FakeModels()


class _FakeSessionContext:
    def __init__(self, root: str):
        self.session_dir = root
        self.session_path = os.path.join(root, "session.json")
        self.phase1_chunks_dir = os.path.join(root, "phase1")
        self.phase2_revised_dir = os.path.join(root, "phase2")
        self.boundary_dir = os.path.join(root, "boundary")
        self.macro_path = os.path.join(root, "macro.md")
        self.session = {"stage": "phase1", "phase1": {}, "phase2": {}, "boundary": {}, "outputs": {}}
        self.settings = SimpleNamespace(model="gemini-test", chunk_seconds=60, step_seconds=60, preconvert_audio=False)
        os.makedirs(self.phase1_chunks_dir, exist_ok=True)
        os.makedirs(self.phase2_revised_dir, exist_ok=True)
        os.makedirs(self.boundary_dir, exist_ok=True)

    def save(self):
        return True


class _PromptBlockingApp:
    def __init__(self):
        self.cancel_event = threading.Event()
        self.file_temporanei = []
        self.last_run_status = "idle"
        self.last_run_error = None
        self.effective_api_key = None
        self.prompt_shown = threading.Event()

    def winfo_exists(self):
        return True

    def ask_regenerate(self, filename, callback, mode="resume"):
        self.prompt_shown.set()
        self._callback = callback
        return None

    def aggiorna_progresso(self, value):
        return None

    def aggiorna_fase(self, text):
        return None

    def imposta_output_html(self, path):
        return None

    def processo_terminato(self):
        return None


class PipelineCancellationTests(unittest.TestCase):
    def test_cancel_during_regenerate_prompt_exits_prompt_wait_immediately(self):
        app = _PromptBlockingApp()

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.mp3")
            with open(input_path, "wb") as handle:
                handle.write(b"fake")

            session_ctx = _FakeSessionContext(os.path.join(tmpdir, "session"))

            with patch("google.genai.Client", _FakeClient), \
                 patch("el_sbobinator.pipeline.initialize_session_context", return_value=session_ctx), \
                 patch("el_sbobinator.pipeline.attach_file_handler", return_value=None), \
                 patch("el_sbobinator.pipeline.detach_file_handler"), \
                 patch("el_sbobinator.pipeline.get_logger", return_value=_FakeLogger()), \
                 patch("el_sbobinator.pipeline.load_fallback_keys", return_value=[]), \
                 patch("el_sbobinator.pipeline.resolve_ffmpeg", return_value="ffmpeg"), \
                 patch("el_sbobinator.pipeline.probe_media_duration", return_value=(120.0, None)), \
                 patch("el_sbobinator.pipeline.persist_phase1_metadata"), \
                 patch("el_sbobinator.pipeline.normalize_stage", return_value="phase1"), \
                 patch("el_sbobinator.pipeline.list_phase1_chunks", return_value=[(0, 0, 60, "chunk_000_0_60.md")]), \
                 patch("el_sbobinator.pipeline.phase1_has_progress", return_value=True), \
                 patch("el_sbobinator.pipeline.ensure_preconverted_audio", return_value=(False, None)):
                thread = threading.Thread(
                    target=esegui_sbobinatura,
                    args=(input_path, "fake-key", app),
                    kwargs={"resume_session": True},
                    daemon=True,
                )
                started = time.monotonic()
                thread.start()

                self.assertTrue(app.prompt_shown.wait(timeout=1))
                app.cancel_event.set()

                thread.join(timeout=2)
                elapsed = time.monotonic() - started

            self.assertFalse(thread.is_alive(), "La pipeline e' rimasta bloccata in attesa del prompt di rigenerazione.")
            self.assertLess(elapsed, 2.5)
            self.assertEqual(app.last_run_status, "cancelled")

    def test_dismiss_regenerate_prompt_cancels_before_resuming_work(self):
        app = _PromptBlockingApp()

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.mp3")
            with open(input_path, "wb") as handle:
                handle.write(b"fake")

            session_ctx = _FakeSessionContext(os.path.join(tmpdir, "session"))

            with patch("google.genai.Client", _FakeClient), \
                 patch("el_sbobinator.pipeline.initialize_session_context", return_value=session_ctx), \
                 patch("el_sbobinator.pipeline.attach_file_handler", return_value=None), \
                 patch("el_sbobinator.pipeline.detach_file_handler"), \
                 patch("el_sbobinator.pipeline.get_logger", return_value=_FakeLogger()), \
                 patch("el_sbobinator.pipeline.load_fallback_keys", return_value=[]), \
                 patch("el_sbobinator.pipeline.resolve_ffmpeg", return_value="ffmpeg"), \
                 patch("el_sbobinator.pipeline.probe_media_duration", return_value=(120.0, None)), \
                 patch("el_sbobinator.pipeline.persist_phase1_metadata"), \
                 patch("el_sbobinator.pipeline.normalize_stage", return_value="phase1"), \
                 patch("el_sbobinator.pipeline.list_phase1_chunks", return_value=[(0, 0, 60, "chunk_000_0_60.md")]), \
                 patch("el_sbobinator.pipeline.phase1_has_progress", return_value=True), \
                 patch("el_sbobinator.pipeline.ensure_preconverted_audio") as mock_preconvert:
                thread = threading.Thread(
                    target=esegui_sbobinatura,
                    args=(input_path, "fake-key", app),
                    kwargs={"resume_session": True},
                    daemon=True,
                )
                thread.start()

                self.assertTrue(app.prompt_shown.wait(timeout=1))
                app._callback({"regenerate": None})

                thread.join(timeout=2)

            self.assertFalse(thread.is_alive(), "La pipeline e' rimasta bloccata dopo la chiusura del prompt.")
            self.assertEqual(app.last_run_status, "cancelled")
            mock_preconvert.assert_not_called()


if __name__ == "__main__":
    unittest.main()
