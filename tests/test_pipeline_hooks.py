import os
import tempfile
import threading
import unittest

from el_sbobinator.pipeline_hooks import PipelineRuntime


class _DummyTarget:
    def __init__(self):
        self.cancel_event = threading.Event()
        self.file_temporanei = []
        self.events = []
        self.last_run_status = "idle"
        self.last_run_error = None
        self.effective_api_key = None

    def winfo_exists(self):
        return True

    def aggiorna_progresso(self, value):
        self.events.append(("progress", value))

    def aggiorna_fase(self, text):
        self.events.append(("phase", text))

    def imposta_output_html(self, path, output_dir=None):
        self.events.append(("output", path, output_dir))

    def processo_terminato(self):
        self.events.append(("done", None))

    def set_work_totals(self, **kwargs):
        self.events.append(("totals", kwargs))

    def update_work_done(self, kind, done, total=None):
        self.events.append(("work_done", kind, done, total))

    def register_step_time(self, kind, seconds, done=None, total=None):
        self.events.append(("step_time", kind, seconds, done, total))


class PipelineRuntimeTests(unittest.TestCase):
    def test_runtime_forwards_callbacks_and_state(self):
        target = _DummyTarget()
        runtime = PipelineRuntime(target)

        runtime.progress(0.4)
        runtime.phase("fase test")
        runtime.output_html("out.html")
        runtime.output_html("out2.html", output_dir="/some/dir")
        runtime.set_work_totals(chunks_total=3)
        runtime.update_work_done("chunks", 1, total=3)
        runtime.register_step_time("chunks", 2.5, done=1, total=3)
        runtime.set_run_result("completed", None)
        runtime.set_effective_api_key("  key-123  ")
        runtime.process_done()

        self.assertIn(("progress", 0.4), target.events)
        self.assertIn(("phase", "fase test"), target.events)
        self.assertIn(("output", "out.html", None), target.events)
        self.assertIn(("output", "out2.html", "/some/dir"), target.events)
        self.assertEqual(target.last_run_status, "completed")
        self.assertEqual(target.effective_api_key, "key-123")

    def test_runtime_cleans_temp_files(self):
        target = _DummyTarget()
        runtime = PipelineRuntime(target)

        fd, path = tempfile.mkstemp()
        os.close(fd)
        runtime.track_temp_file(path)
        self.assertTrue(os.path.exists(path))

        runtime.cleanup_temp_files()

        self.assertFalse(os.path.exists(path))
        self.assertEqual(target.file_temporanei, [])


if __name__ == "__main__":
    unittest.main()
