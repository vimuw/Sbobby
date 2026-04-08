import os
import tempfile
import unittest
from unittest.mock import patch

from el_sbobinator.pipeline_session import (
    ensure_preconverted_audio,
    normalize_stage,
    phase1_has_progress,
    record_step_metric,
    restore_phase1_progress,
)
from el_sbobinator.pipeline_settings import PipelineSettings
from el_sbobinator.shared import PRECONVERTED_AUDIO_FINAL, PRECONVERTED_AUDIO_PARTIAL


class _DummyContext:
    def __init__(self, session, phase1_chunks_dir):
        self.session = session
        self.phase1_chunks_dir = phase1_chunks_dir


class _DummyPreconvContext:
    def __init__(self, session_dir):
        self.session = {}
        self.session_dir = session_dir
        self.settings = PipelineSettings(
            model="gemini-2.5-flash",
            chunk_minutes=15,
            overlap_seconds=30,
            macro_char_limit=22000,
            preconvert_audio=True,
            audio_bitrate="48k",
            prefetch_next_chunk=True,
            inline_audio_max_mb=6.0,
        )
        self.save_calls = 0

    def save(self):
        self.save_calls += 1
        return True


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
            self.assertIn("Chunk 1 body", restored.full_transcript)
            self.assertEqual(restored.prev_memory, "Chunk 1 body")

    def test_record_step_metric_accumulates_elapsed_time(self):
        session = {}
        record_step_metric(session, "chunks", 2.5, done=1, total=3)
        record_step_metric(session, "chunks", 1.5, done=2, total=3)

        metric = session["metrics"]["chunks"]
        self.assertEqual(metric["count"], 2)
        self.assertEqual(metric["done"], 2)
        self.assertEqual(metric["total"], 3)
        self.assertAlmostEqual(metric["elapsed_seconds"], 4.0)

    def test_ensure_preconverted_audio_promotes_partial_and_saves_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            context = _DummyPreconvContext(tmpdir)
            partial_path = os.path.join(tmpdir, PRECONVERTED_AUDIO_PARTIAL)
            final_path = os.path.join(tmpdir, PRECONVERTED_AUDIO_FINAL)
            phases = []
            seen_output_paths = []

            def fake_preconvert(**kwargs):
                seen_output_paths.append(kwargs["output_path"])
                with open(kwargs["output_path"], "wb") as handle:
                    handle.write(b"x" * 4096)
                return True, None

            with patch("el_sbobinator.pipeline_session.preconvert_media_to_mp3", side_effect=fake_preconvert):
                enabled, result_path = ensure_preconverted_audio(
                    context,
                    input_path="lesson.mp3",
                    stage="phase1",
                    ffmpeg_exe="ffmpeg",
                    cancel_event=None,
                    cancelled=lambda: False,
                    phase_callback=phases.append,
                )

            self.assertTrue(enabled)
            self.assertEqual(result_path, final_path)
            self.assertEqual(seen_output_paths, [partial_path])
            self.assertFalse(os.path.exists(partial_path))
            self.assertTrue(os.path.exists(final_path))
            self.assertEqual(context.save_calls, 1)
            self.assertEqual(context.session["phase1"]["preconverted_path"], final_path)
            self.assertTrue(context.session["phase1"]["preconverted_done"])
            self.assertEqual(phases, ["Fase 0/3: pre-conversione audio"])

    def test_ensure_preconverted_audio_removes_stale_partial_before_retry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            context = _DummyPreconvContext(tmpdir)
            partial_path = os.path.join(tmpdir, PRECONVERTED_AUDIO_PARTIAL)

            with open(partial_path, "wb") as handle:
                handle.write(b"stale")

            def fake_preconvert(**kwargs):
                self.assertFalse(os.path.exists(kwargs["output_path"]))
                with open(kwargs["output_path"], "wb") as handle:
                    handle.write(b"y" * 4096)
                return True, None

            with patch("el_sbobinator.pipeline_session.preconvert_media_to_mp3", side_effect=fake_preconvert):
                enabled, result_path = ensure_preconverted_audio(
                    context,
                    input_path="lesson.mp3",
                    stage="phase1",
                    ffmpeg_exe="ffmpeg",
                    cancel_event=None,
                    cancelled=lambda: False,
                    phase_callback=lambda _phase: None,
                )

            self.assertTrue(enabled)
            self.assertEqual(result_path, os.path.join(tmpdir, PRECONVERTED_AUDIO_FINAL))
            self.assertFalse(os.path.exists(partial_path))

    def test_ensure_preconverted_audio_cleans_partial_on_cancel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            context = _DummyPreconvContext(tmpdir)
            partial_path = os.path.join(tmpdir, PRECONVERTED_AUDIO_PARTIAL)

            def fake_preconvert(**kwargs):
                with open(kwargs["output_path"], "wb") as handle:
                    handle.write(b"z" * 4096)
                return False, "cancelled"

            with patch("el_sbobinator.pipeline_session.preconvert_media_to_mp3", side_effect=fake_preconvert):
                enabled, result_path = ensure_preconverted_audio(
                    context,
                    input_path="lesson.mp3",
                    stage="phase1",
                    ffmpeg_exe="ffmpeg",
                    cancel_event=None,
                    cancelled=lambda: True,
                    phase_callback=lambda _phase: None,
                )

            self.assertTrue(enabled)
            self.assertIsNone(result_path)
            self.assertFalse(os.path.exists(partial_path))
            self.assertEqual(context.save_calls, 0)
            self.assertNotIn("phase1", context.session)

    def test_ensure_preconverted_audio_cleans_partial_when_promotion_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            context = _DummyPreconvContext(tmpdir)
            partial_path = os.path.join(tmpdir, PRECONVERTED_AUDIO_PARTIAL)

            def fake_preconvert(**kwargs):
                with open(kwargs["output_path"], "wb") as handle:
                    handle.write(b"k" * 4096)
                return True, None

            with patch("el_sbobinator.pipeline_session.preconvert_media_to_mp3", side_effect=fake_preconvert):
                with patch("el_sbobinator.pipeline_session.os.replace", side_effect=PermissionError("locked")):
                    enabled, result_path = ensure_preconverted_audio(
                        context,
                        input_path="lesson.mp3",
                        stage="phase1",
                        ffmpeg_exe="ffmpeg",
                        cancel_event=None,
                        cancelled=lambda: False,
                        phase_callback=lambda _phase: None,
                    )

            self.assertFalse(enabled)
            self.assertIsNone(result_path)
            self.assertFalse(os.path.exists(partial_path))
            self.assertEqual(context.save_calls, 0)
            self.assertNotIn("phase1", context.session)


if __name__ == "__main__":
    unittest.main()
