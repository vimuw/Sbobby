import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from el_sbobinator.core.shared import (
    PRECONVERTED_AUDIO_FINAL,
    PRECONVERTED_AUDIO_PARTIAL,
)
from el_sbobinator.pipeline.pipeline_session import (
    ensure_preconverted_audio,
    initialize_session_context,
    normalize_stage,
    phase1_has_progress,
    record_step_metric,
    reset_for_regeneration,
    restore_phase1_progress,
)
from el_sbobinator.pipeline.pipeline_settings import PipelineSettings


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
            fallback_models=["gemini-2.5-flash-lite"],
            effective_model="gemini-2.5-flash",
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


class _DummyRegenContext:
    def __init__(self, input_path: str, session_dir: str):
        self.input_path = input_path
        self.session_paths = SimpleNamespace(session_dir=session_dir)
        self.session = {
            "settings": {
                "model": "gemini-2.5-flash",
                "fallback_models": ["gemini-2.5-flash-lite"],
                "effective_model": "gemini-2.5-flash",
            }
        }
        self.settings = PipelineSettings(
            model="gemini-2.5-flash",
            fallback_models=["gemini-2.5-flash-lite"],
            effective_model="gemini-2.5-flash",
            chunk_minutes=15,
            overlap_seconds=30,
            macro_char_limit=22000,
            preconvert_audio=True,
            audio_bitrate="48k",
            prefetch_next_chunk=True,
            inline_audio_max_mb=6.0,
        )
        self.settings_changed = False
        self.save_calls = 0

    def save(self):
        self.save_calls += 1
        return True


class PipelineSessionHelpersTests(unittest.TestCase):
    def test_reset_for_regeneration_uses_current_config_not_old_session_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "lesson.mp3")
            with open(input_path, "wb") as handle:
                handle.write(b"fake")

            context = _DummyRegenContext(input_path, os.path.join(tmpdir, "session"))
            fresh_settings = {
                "model": "gemini-2.5-flash-lite",
                "fallback_models": [],
                "effective_model": "gemini-2.5-flash-lite",
                "chunk_minutes": 15,
                "overlap_seconds": 30,
                "macro_char_limit": 22000,
                "preconvert_audio": True,
                "prefetch_next_chunk": True,
                "inline_audio_max_mb": 6.0,
                "audio": {"bitrate": "48k"},
            }

            with (
                patch("el_sbobinator.pipeline.pipeline_session.reset_session_dirs"),
                patch(
                    "el_sbobinator.pipeline.pipeline_session.load_config",
                    return_value={"preferred_model": "gemini-2.5-flash-lite"},
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline_session.build_default_pipeline_settings",
                    return_value=fresh_settings,
                ),
            ):
                reset_for_regeneration(context)  # type: ignore[arg-type]

            self.assertEqual(
                context.session["settings"]["model"], "gemini-2.5-flash-lite"
            )
            self.assertEqual(
                context.session["settings"]["effective_model"], "gemini-2.5-flash-lite"
            )
            self.assertEqual(context.settings.model, "gemini-2.5-flash-lite")
            self.assertEqual(context.settings.effective_model, "gemini-2.5-flash-lite")
            self.assertEqual(context.save_calls, 1)

    def test_normalize_stage_falls_back_to_phase1(self):
        session = {"stage": "wat"}
        stage = normalize_stage(session)
        self.assertEqual(stage, "phase1")
        self.assertEqual(session["stage"], "phase1")

    def test_preconverted_audio_partial_has_mp3_extension(self):
        self.assertTrue(PRECONVERTED_AUDIO_PARTIAL.endswith(".mp3"))

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
            restored = restore_phase1_progress(context, stage="phase1", step_seconds=30)  # type: ignore[arg-type]

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

            with patch(
                "el_sbobinator.pipeline.pipeline_session.preconvert_media_to_mp3",
                side_effect=fake_preconvert,
            ):
                with patch(
                    "el_sbobinator.pipeline.pipeline_session.invalidate_session_storage_cache"
                ) as mock_invalidate:
                    enabled, result_path = ensure_preconverted_audio(  # type: ignore[arg-type]
                        context,  # type: ignore[arg-type]
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
            mock_invalidate.assert_called_once()

    def test_ensure_preconverted_audio_cache_reflects_promoted_bytes_immediately(self):
        from el_sbobinator.core import shared as _shared

        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = os.path.join(tmpdir, "session")
            os.makedirs(session_dir, exist_ok=True)
            context = _DummyPreconvContext(session_dir)
            partial_path = os.path.join(session_dir, PRECONVERTED_AUDIO_PARTIAL)
            final_path = os.path.join(session_dir, PRECONVERTED_AUDIO_FINAL)

            with open(partial_path, "wb") as handle:
                handle.write(b"p" * 4096)

            def fake_preconvert(**kwargs):
                with open(kwargs["output_path"], "wb") as handle:
                    handle.write(b"f" * 8192)
                return True, None

            with patch("el_sbobinator.core.shared.SESSION_ROOT", tmpdir):
                _shared.invalidate_session_storage_cache()
                info_before = _shared.get_session_storage_info()
                self.assertEqual(
                    info_before["total_bytes"],
                    0,
                    "partial file must not count toward storage",
                )

                with patch(
                    "el_sbobinator.pipeline.pipeline_session.preconvert_media_to_mp3",
                    side_effect=fake_preconvert,
                ):
                    enabled, result_path = ensure_preconverted_audio(  # type: ignore[arg-type]
                        context,  # type: ignore[arg-type]
                        input_path="lesson.mp3",
                        stage="phase1",
                        ffmpeg_exe="ffmpeg",
                        cancel_event=None,
                        cancelled=lambda: False,
                        phase_callback=lambda _: None,
                    )

                self.assertTrue(enabled)
                self.assertEqual(result_path, final_path)
                self.assertTrue(os.path.exists(final_path))
                self.assertFalse(os.path.exists(partial_path))

                info_after = _shared.get_session_storage_info()
                self.assertEqual(
                    info_after["total_bytes"],
                    8192,
                    "promoted final MP3 must be visible immediately without manual cache invalidation",
                )

    def test_ensure_preconverted_audio_cache_not_invalidated_on_cancel(self):
        from el_sbobinator.core import shared as _shared

        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = os.path.join(tmpdir, "session")
            os.makedirs(session_dir, exist_ok=True)
            context = _DummyPreconvContext(session_dir)

            def fake_preconvert(**kwargs):
                with open(kwargs["output_path"], "wb") as handle:
                    handle.write(b"z" * 4096)
                return False, "cancelled"

            with patch("el_sbobinator.core.shared.SESSION_ROOT", tmpdir):
                _shared.invalidate_session_storage_cache()
                _shared.get_session_storage_info()

                with patch(
                    "el_sbobinator.pipeline.pipeline_session.preconvert_media_to_mp3",
                    side_effect=fake_preconvert,
                ):
                    with patch(
                        "el_sbobinator.pipeline.pipeline_session.invalidate_session_storage_cache"
                    ) as mock_invalidate:
                        ensure_preconverted_audio(  # type: ignore[arg-type]
                            context,  # type: ignore[arg-type]
                            input_path="lesson.mp3",
                            stage="phase1",
                            ffmpeg_exe="ffmpeg",
                            cancel_event=None,
                            cancelled=lambda: True,
                            phase_callback=lambda _: None,
                        )

                mock_invalidate.assert_not_called()

    def test_ensure_preconverted_audio_cache_not_invalidated_on_failed_promotion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            context = _DummyPreconvContext(tmpdir)

            def fake_preconvert(**kwargs):
                with open(kwargs["output_path"], "wb") as handle:
                    handle.write(b"k" * 4096)
                return True, None

            with patch(
                "el_sbobinator.pipeline.pipeline_session.preconvert_media_to_mp3",
                side_effect=fake_preconvert,
            ):
                with patch(
                    "el_sbobinator.pipeline.pipeline_session.os.replace",
                    side_effect=PermissionError("locked"),
                ):
                    with patch(
                        "el_sbobinator.pipeline.pipeline_session.invalidate_session_storage_cache"
                    ) as mock_invalidate:
                        ensure_preconverted_audio(  # type: ignore[arg-type]
                            context,  # type: ignore[arg-type]
                            input_path="lesson.mp3",
                            stage="phase1",
                            ffmpeg_exe="ffmpeg",
                            cancel_event=None,
                            cancelled=lambda: False,
                            phase_callback=lambda _: None,
                        )

            mock_invalidate.assert_not_called()

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

            with patch(
                "el_sbobinator.pipeline.pipeline_session.preconvert_media_to_mp3",
                side_effect=fake_preconvert,
            ):
                enabled, result_path = ensure_preconverted_audio(  # type: ignore[arg-type]
                    context,  # type: ignore[arg-type]
                    input_path="lesson.mp3",
                    stage="phase1",
                    ffmpeg_exe="ffmpeg",
                    cancel_event=None,
                    cancelled=lambda: False,
                    phase_callback=lambda _phase: None,
                )

            self.assertTrue(enabled)
            self.assertEqual(
                result_path, os.path.join(tmpdir, PRECONVERTED_AUDIO_FINAL)
            )
            self.assertFalse(os.path.exists(partial_path))

    def test_ensure_preconverted_audio_cleans_partial_on_cancel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            context = _DummyPreconvContext(tmpdir)
            partial_path = os.path.join(tmpdir, PRECONVERTED_AUDIO_PARTIAL)

            def fake_preconvert(**kwargs):
                with open(kwargs["output_path"], "wb") as handle:
                    handle.write(b"z" * 4096)
                return False, "cancelled"

            with patch(
                "el_sbobinator.pipeline.pipeline_session.preconvert_media_to_mp3",
                side_effect=fake_preconvert,
            ):
                enabled, result_path = ensure_preconverted_audio(  # type: ignore[arg-type]
                    context,  # type: ignore[arg-type]
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

            with patch(
                "el_sbobinator.pipeline.pipeline_session.preconvert_media_to_mp3",
                side_effect=fake_preconvert,
            ):
                with patch(
                    "el_sbobinator.pipeline.pipeline_session.os.replace",
                    side_effect=PermissionError("locked"),
                ):
                    enabled, result_path = ensure_preconverted_audio(  # type: ignore[arg-type]
                        context,  # type: ignore[arg-type]
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


class InitializeSessionContextTests(unittest.TestCase):
    def test_resume_overrides_model_from_current_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            import json

            input_path = os.path.join(tmpdir, "lesson.mp3")
            with open(input_path, "wb") as fh:
                fh.write(b"fake")

            session_dir = os.path.join(tmpdir, "session")
            os.makedirs(os.path.join(session_dir, "phase1_chunks"), exist_ok=True)
            os.makedirs(os.path.join(session_dir, "phase2_revised"), exist_ok=True)
            session_data = {
                "schema_version": 1,
                "created_at": "2024-01-01 00:00:00",
                "updated_at": "2024-01-01 00:00:00",
                "stage": "phase1",
                "input": {"path": input_path, "size": 4, "mtime": 0.0},
                "settings": {
                    "model": "gemini-2.5-flash",
                    "fallback_models": [],
                    "effective_model": "gemini-2.5-flash",
                    "chunk_minutes": 15,
                    "overlap_seconds": 30,
                    "macro_char_limit": 22000,
                    "preconvert_audio": True,
                    "prefetch_next_chunk": True,
                    "inline_audio_max_mb": 6.0,
                    "audio": {"bitrate": "48k"},
                },
                "phase1": {
                    "next_start_sec": 0,
                    "chunks_done": 0,
                    "memoria_precedente": "",
                },
                "phase2": {"macro_total": 0, "revised_done": 0},
                "outputs": {},
                "last_error": None,
            }
            session_path = os.path.join(session_dir, "session.json")
            with open(session_path, "w", encoding="utf-8") as fh:
                json.dump(session_data, fh)

            with (
                patch(
                    "el_sbobinator.pipeline.pipeline_session.load_config",
                    return_value={
                        "preferred_model": "gemini-2.5-flash-lite",
                        "fallback_models": [],
                    },
                ),
                patch(
                    "el_sbobinator.core.session_store._session_dir_for_file",
                    return_value=session_dir,
                ),
            ):
                ctx = initialize_session_context(input_path, resume_session=True)

            self.assertEqual(ctx.settings.model, "gemini-2.5-flash-lite")
            self.assertEqual(
                ctx.session["settings"]["effective_model"], "gemini-2.5-flash-lite"
            )

    def _make_session_file(self, tmpdir, model, chunk_minutes, chunks_done):
        import json

        input_path = os.path.join(tmpdir, "lesson.mp3")
        with open(input_path, "wb") as fh:
            fh.write(b"fake")

        session_dir = os.path.join(tmpdir, "session")
        os.makedirs(os.path.join(session_dir, "phase1_chunks"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "phase2_revised"), exist_ok=True)
        session_data = {
            "schema_version": 1,
            "created_at": "2024-01-01 00:00:00",
            "updated_at": "2024-01-01 00:00:00",
            "stage": "phase1",
            "input": {"path": input_path, "size": 4, "mtime": 0.0},
            "settings": {
                "model": model,
                "fallback_models": [],
                "effective_model": model,
                "chunk_minutes": chunk_minutes,
                "overlap_seconds": 30,
                "macro_char_limit": 22000,
                "preconvert_audio": True,
                "prefetch_next_chunk": True,
                "inline_audio_max_mb": 6.0,
                "audio": {"bitrate": "48k"},
            },
            "phase1": {
                "next_start_sec": chunks_done * (chunk_minutes * 60 - 30),
                "chunks_done": chunks_done,
                "memoria_precedente": "",
            },
            "phase2": {"macro_total": 0, "revised_done": 0},
            "outputs": {},
            "last_error": None,
        }
        session_path = os.path.join(session_dir, "session.json")
        with open(session_path, "w", encoding="utf-8") as fh:
            json.dump(session_data, fh)
        return input_path, session_dir

    def test_chunk_minutes_resets_to_new_model_default_when_no_chunks_done(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path, session_dir = self._make_session_file(
                tmpdir, model="gemini-2.5-flash-lite", chunk_minutes=10, chunks_done=0
            )
            new_defaults = {
                "model": "gemini-2.5-flash",
                "fallback_models": [],
                "effective_model": "gemini-2.5-flash",
                "chunk_minutes": 15,
                "overlap_seconds": 30,
                "macro_char_limit": 22000,
                "preconvert_audio": True,
                "prefetch_next_chunk": True,
                "inline_audio_max_mb": 6.0,
                "audio": {"bitrate": "48k"},
            }
            with (
                patch(
                    "el_sbobinator.pipeline.pipeline_session.load_config",
                    return_value={
                        "preferred_model": "gemini-2.5-flash",
                        "fallback_models": [],
                    },
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline_session.build_default_pipeline_settings",
                    return_value=new_defaults,
                ),
                patch(
                    "el_sbobinator.core.session_store._session_dir_for_file",
                    return_value=session_dir,
                ),
            ):
                ctx = initialize_session_context(input_path, resume_session=True)

            self.assertEqual(ctx.settings.model, "gemini-2.5-flash")
            self.assertEqual(ctx.settings.chunk_minutes, 15)

    def test_chunk_minutes_preserved_when_model_changes_but_chunks_already_done(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path, session_dir = self._make_session_file(
                tmpdir, model="gemini-2.5-flash-lite", chunk_minutes=10, chunks_done=3
            )
            new_defaults = {
                "model": "gemini-2.5-flash",
                "fallback_models": [],
                "effective_model": "gemini-2.5-flash",
                "chunk_minutes": 15,
                "overlap_seconds": 30,
                "macro_char_limit": 22000,
                "preconvert_audio": True,
                "prefetch_next_chunk": True,
                "inline_audio_max_mb": 6.0,
                "audio": {"bitrate": "48k"},
            }
            with (
                patch(
                    "el_sbobinator.pipeline.pipeline_session.load_config",
                    return_value={
                        "preferred_model": "gemini-2.5-flash",
                        "fallback_models": [],
                    },
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline_session.build_default_pipeline_settings",
                    return_value=new_defaults,
                ),
                patch(
                    "el_sbobinator.core.session_store._session_dir_for_file",
                    return_value=session_dir,
                ),
            ):
                ctx = initialize_session_context(input_path, resume_session=True)

            self.assertEqual(ctx.settings.model, "gemini-2.5-flash")
            self.assertEqual(ctx.settings.chunk_minutes, 10)


if __name__ == "__main__":
    unittest.main()
