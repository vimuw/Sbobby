import os
import tempfile
import unittest

from el_sbobinator.pipeline_session import (
    normalize_stage,
    phase1_has_progress,
    record_step_metric,
    restore_phase1_progress,
)


class _DummyContext:
    def __init__(self, session, phase1_chunks_dir):
        self.session = session
        self.phase1_chunks_dir = phase1_chunks_dir


class PipelineSessionHelpersTests(unittest.TestCase):
    def test_normalize_stage_falls_back_to_phase1(self):
        session = {"stage": "wat"}
        stage = normalize_stage(session)
        self.assertEqual(stage, "phase1")
        self.assertEqual(session["stage"], "phase1")

    def test_phase1_progress_detects_saved_output(self):
        session = {"outputs": {"html": "ready.html"}}
        self.assertTrue(phase1_has_progress(session, "done", []))

    def test_restore_phase1_progress_loads_existing_chunks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chunk_path = os.path.join(tmpdir, "chunk_001_0_60.md")
            with open(chunk_path, "w", encoding="utf-8") as handle:
                handle.write("Chunk 1 body")

            session = {"phase1": {"next_start_sec": 0, "memoria_precedente": ""}}
            context = _DummyContext(session, tmpdir)
            restored = restore_phase1_progress(context, stage="phase1", step_seconds=30)

            self.assertEqual(len(restored.existing_chunks), 1)
            self.assertEqual(restored.start_sec, 30)
            self.assertIn("Chunk 1 body", restored.testo_completo_sbobina)
            self.assertEqual(restored.memoria_precedente, "Chunk 1 body")

    def test_record_step_metric_accumulates_elapsed_time(self):
        session = {}
        record_step_metric(session, "chunks", 2.5, done=1, total=3)
        record_step_metric(session, "chunks", 1.5, done=2, total=3)

        metric = session["metrics"]["chunks"]
        self.assertEqual(metric["count"], 2)
        self.assertEqual(metric["done"], 2)
        self.assertEqual(metric["total"], 3)
        self.assertAlmostEqual(metric["elapsed_seconds"], 4.0)


if __name__ == "__main__":
    unittest.main()
