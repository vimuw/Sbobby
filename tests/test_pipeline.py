import contextlib
import os
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from el_sbobinator.pipeline.pipeline import esegui_sbobinatura


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
        self.session = {
            "stage": "phase1",
            "phase1": {},
            "phase2": {},
            "boundary": {},
            "outputs": {},
        }
        self.settings = SimpleNamespace(
            model="gemini-test",
            fallback_models=["gemini-2.5-flash-lite"],
            effective_model="gemini-test",
            chunk_minutes=15,
            chunk_seconds=60,
            step_seconds=60,
            preconvert_audio=False,
            audio_bitrate="48k",
            prefetch_next_chunk=True,
            inline_max_bytes=None,
            macro_char_limit=22000,
        )
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

    def imposta_output_html(self, path, output_dir=None):
        return None

    def processo_terminato(self):
        return None


class PipelineCancellationTests(unittest.TestCase):
    def test_regenerate_rebinds_model_state_from_reset_session_settings(self):
        app = _PromptBlockingApp()

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.mp3")
            with open(input_path, "wb") as handle:
                handle.write(b"fake")

            session_ctx = _FakeSessionContext(os.path.join(tmpdir, "session"))
            session_ctx.session = {
                "stage": "phase1",
                "phase1": {},
                "phase2": {},
                "boundary": {},
                "outputs": {},
            }
            session_ctx.settings = SimpleNamespace(
                model="gemini-2.5-flash",
                fallback_models=["gemini-2.5-flash-lite"],
                effective_model="gemini-2.5-flash",
                chunk_minutes=15,
                chunk_seconds=60,
                step_seconds=60,
                preconvert_audio=False,
                audio_bitrate="48k",
                prefetch_next_chunk=True,
                inline_max_bytes=None,
                macro_char_limit=22000,
            )

            seen = {}

            def fake_phase1(**kwargs):
                seen["current_model"] = kwargs["model_state"].current
                seen["chain"] = kwargs["model_state"].chain
                return kwargs["client"], None, ""

            def fake_reset(context):
                context.session = {
                    "stage": "phase1",
                    "phase1": {},
                    "phase2": {},
                    "boundary": {},
                    "outputs": {},
                }
                context.settings = SimpleNamespace(
                    model="gemini-2.5-flash",
                    fallback_models=["gemini-2.5-flash-lite"],
                    effective_model="gemini-2.5-flash-lite",
                    chunk_minutes=10,
                    chunk_seconds=60,
                    step_seconds=60,
                    preconvert_audio=False,
                    audio_bitrate="48k",
                    prefetch_next_chunk=True,
                    inline_max_bytes=None,
                    macro_char_limit=22000,
                )

            with (
                patch("google.genai.Client", _FakeClient),
                patch(
                    "el_sbobinator.pipeline.pipeline.initialize_session_context",
                    return_value=session_ctx,
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.attach_file_handler",
                    return_value=None,
                ),
                patch("el_sbobinator.pipeline.pipeline.detach_file_handler"),
                patch(
                    "el_sbobinator.pipeline.pipeline.get_logger",
                    return_value=_FakeLogger(),
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.load_fallback_keys",
                    return_value=[],
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.resolve_ffmpeg",
                    return_value="ffmpeg",
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.probe_media_duration",
                    return_value=(120.0, None),
                ),
                patch("el_sbobinator.pipeline.pipeline.persist_phase1_metadata"),
                patch(
                    "el_sbobinator.pipeline.pipeline.normalize_stage",
                    return_value="phase1",
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.list_phase1_chunks",
                    return_value=[(0, 0, 60, "chunk_000_0_60.md")],
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.phase1_has_progress",
                    return_value=True,
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.ensure_preconverted_audio",
                    return_value=(False, None),
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.reset_for_regeneration",
                    side_effect=fake_reset,
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.process_phase1_transcription",
                    side_effect=fake_phase1,
                ),
            ):
                thread = threading.Thread(
                    target=esegui_sbobinatura,
                    args=(input_path, "fake-key", app),
                    kwargs={"resume_session": True},
                    daemon=True,
                )
                thread.start()
                self.assertTrue(app.prompt_shown.wait(timeout=1))
                app._callback({"regenerate": True})
                thread.join(timeout=2)

        self.assertEqual(seen.get("current_model"), "gemini-2.5-flash")
        self.assertIn("gemini-2.5-flash-lite", seen.get("chain", ()))

    def test_resume_always_starts_from_primary_ignoring_stale_effective_model(self):
        """On resume, model_state.current must be the primary model, even when the session
        recorded a different effective_model from a previous fallback switch.
        effective_model is kept for observability but must not drive the resume start."""
        app = _PromptBlockingApp()

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.mp3")
            with open(input_path, "wb") as handle:
                handle.write(b"fake")

            session_ctx = _FakeSessionContext(os.path.join(tmpdir, "session"))
            session_ctx.settings = SimpleNamespace(
                model="gemini-2.5-flash",
                fallback_models=["gemini-2.5-flash-lite"],
                effective_model="gemini-2.5-flash-lite",
                chunk_minutes=15,
                chunk_seconds=60,
                step_seconds=60,
                preconvert_audio=False,
                audio_bitrate="48k",
                prefetch_next_chunk=True,
                inline_max_bytes=None,
                macro_char_limit=22000,
            )

            seen = {}

            def fake_phase1(**kwargs):
                seen["current_model"] = kwargs["model_state"].current
                seen["chain"] = kwargs["model_state"].chain
                return kwargs["client"], None, ""

            with (
                patch("google.genai.Client", _FakeClient),
                patch(
                    "el_sbobinator.pipeline.pipeline.initialize_session_context",
                    return_value=session_ctx,
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.attach_file_handler",
                    return_value=None,
                ),
                patch("el_sbobinator.pipeline.pipeline.detach_file_handler"),
                patch(
                    "el_sbobinator.pipeline.pipeline.get_logger",
                    return_value=_FakeLogger(),
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.load_fallback_keys",
                    return_value=[],
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.resolve_ffmpeg",
                    return_value="ffmpeg",
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.probe_media_duration",
                    return_value=(120.0, None),
                ),
                patch("el_sbobinator.pipeline.pipeline.persist_phase1_metadata"),
                patch(
                    "el_sbobinator.pipeline.pipeline.normalize_stage",
                    return_value="phase1",
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.list_phase1_chunks",
                    return_value=[],
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.phase1_has_progress",
                    return_value=False,
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.ensure_preconverted_audio",
                    return_value=(False, None),
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.process_phase1_transcription",
                    side_effect=fake_phase1,
                ),
            ):
                esegui_sbobinatura(input_path, "fake-key", app, resume_session=True)

        self.assertEqual(seen.get("current_model"), "gemini-2.5-flash")
        self.assertIn("gemini-2.5-flash-lite", seen.get("chain", ()))

    def test_cancel_during_regenerate_prompt_exits_prompt_wait_immediately(self):
        app = _PromptBlockingApp()

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.mp3")
            with open(input_path, "wb") as handle:
                handle.write(b"fake")

            session_ctx = _FakeSessionContext(os.path.join(tmpdir, "session"))

            with (
                patch("google.genai.Client", _FakeClient),
                patch(
                    "el_sbobinator.pipeline.pipeline.initialize_session_context",
                    return_value=session_ctx,
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.attach_file_handler",
                    return_value=None,
                ),
                patch("el_sbobinator.pipeline.pipeline.detach_file_handler"),
                patch(
                    "el_sbobinator.pipeline.pipeline.get_logger",
                    return_value=_FakeLogger(),
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.load_fallback_keys",
                    return_value=[],
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.resolve_ffmpeg",
                    return_value="ffmpeg",
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.probe_media_duration",
                    return_value=(120.0, None),
                ),
                patch("el_sbobinator.pipeline.pipeline.persist_phase1_metadata"),
                patch(
                    "el_sbobinator.pipeline.pipeline.normalize_stage",
                    return_value="phase1",
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.list_phase1_chunks",
                    return_value=[(0, 0, 60, "chunk_000_0_60.md")],
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.phase1_has_progress",
                    return_value=True,
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.ensure_preconverted_audio",
                    return_value=(False, None),
                ),
            ):
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

            self.assertFalse(
                thread.is_alive(),
                "La pipeline e' rimasta bloccata in attesa del prompt di rigenerazione.",
            )
            self.assertLess(elapsed, 2.5)
            self.assertEqual(app.last_run_status, "cancelled")

    def test_dismiss_regenerate_prompt_cancels_before_resuming_work(self):
        app = _PromptBlockingApp()

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.mp3")
            with open(input_path, "wb") as handle:
                handle.write(b"fake")

            session_ctx = _FakeSessionContext(os.path.join(tmpdir, "session"))

            with (
                patch("google.genai.Client", _FakeClient),
                patch(
                    "el_sbobinator.pipeline.pipeline.initialize_session_context",
                    return_value=session_ctx,
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.attach_file_handler",
                    return_value=None,
                ),
                patch("el_sbobinator.pipeline.pipeline.detach_file_handler"),
                patch(
                    "el_sbobinator.pipeline.pipeline.get_logger",
                    return_value=_FakeLogger(),
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.load_fallback_keys",
                    return_value=[],
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.resolve_ffmpeg",
                    return_value="ffmpeg",
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.probe_media_duration",
                    return_value=(120.0, None),
                ),
                patch("el_sbobinator.pipeline.pipeline.persist_phase1_metadata"),
                patch(
                    "el_sbobinator.pipeline.pipeline.normalize_stage",
                    return_value="phase1",
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.list_phase1_chunks",
                    return_value=[(0, 0, 60, "chunk_000_0_60.md")],
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.phase1_has_progress",
                    return_value=True,
                ),
                patch(
                    "el_sbobinator.pipeline.pipeline.ensure_preconverted_audio"
                ) as mock_preconvert,
            ):
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

            self.assertFalse(
                thread.is_alive(),
                "La pipeline e' rimasta bloccata dopo la chiusura del prompt.",
            )
            self.assertEqual(app.last_run_status, "cancelled")
            mock_preconvert.assert_not_called()


class PipelineCleanupCacheTests(unittest.TestCase):
    def _make_session_ctx(self, session_dir):
        ctx = _FakeSessionContext(session_dir)
        ctx.settings = SimpleNamespace(
            model="gemini-test",
            fallback_models=[],
            effective_model="gemini-test",
            chunk_minutes=15,
            chunk_seconds=60,
            step_seconds=60,
            preconvert_audio=True,
            audio_bitrate="48k",
            prefetch_next_chunk=False,
            inline_max_bytes=None,
            macro_char_limit=22000,
        )
        return ctx

    def _make_pipeline_patches(self, session_ctx, preconv_path, html_path, tmpdir):
        """Base patches that drive the pipeline through to the final cleanup block."""

        def fake_export(**kwargs):
            with open(html_path, "w") as fh:
                fh.write("<html></html>")
            return "Test Title", html_path

        return [
            patch("google.genai.Client", _FakeClient),
            patch(
                "el_sbobinator.pipeline.pipeline.initialize_session_context",
                return_value=session_ctx,
            ),
            patch(
                "el_sbobinator.pipeline.pipeline.attach_file_handler", return_value=None
            ),
            patch("el_sbobinator.pipeline.pipeline.detach_file_handler"),
            patch(
                "el_sbobinator.pipeline.pipeline.get_logger", return_value=_FakeLogger()
            ),
            patch(
                "el_sbobinator.pipeline.pipeline.load_fallback_keys", return_value=[]
            ),
            patch(
                "el_sbobinator.pipeline.pipeline.resolve_ffmpeg", return_value="ffmpeg"
            ),
            patch(
                "el_sbobinator.pipeline.pipeline.probe_media_duration",
                return_value=(120.0, None),
            ),
            patch("el_sbobinator.pipeline.pipeline.persist_phase1_metadata"),
            patch(
                "el_sbobinator.pipeline.pipeline.normalize_stage", return_value="phase1"
            ),
            patch(
                "el_sbobinator.pipeline.pipeline.list_phase1_chunks", return_value=[]
            ),
            patch(
                "el_sbobinator.pipeline.pipeline.phase1_has_progress",
                return_value=False,
            ),
            patch(
                "el_sbobinator.pipeline.pipeline.ensure_preconverted_audio",
                return_value=(True, preconv_path),
            ),
            patch(
                "el_sbobinator.pipeline.pipeline.restore_phase1_progress",
                return_value=SimpleNamespace(
                    existing_chunks=[], start_sec=0, full_transcript="", prev_memory=""
                ),
            ),
            patch(
                "el_sbobinator.pipeline.pipeline.process_phase1_transcription",
                return_value=(_FakeClient(), "transcript", ""),
            ),
            patch(
                "el_sbobinator.pipeline.pipeline.build_macro_blocks",
                return_value=["block"],
            ),
            patch("el_sbobinator.pipeline.pipeline._atomic_write_json"),
            patch(
                "el_sbobinator.pipeline.pipeline.process_macro_revision_phase",
                return_value=(_FakeClient(), "revised"),
            ),
            patch(
                "el_sbobinator.pipeline.pipeline.process_boundary_revision_phase",
                return_value=_FakeClient(),
            ),
            patch(
                "el_sbobinator.pipeline.pipeline.export_final_html_document",
                side_effect=fake_export,
            ),
        ]

    def test_cleanup_path_invalidates_cache_and_bytes_drop_immediately(self):
        from el_sbobinator import shared as _shared
        from el_sbobinator.shared import PRECONVERTED_AUDIO_FINAL

        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = os.path.join(tmpdir, "session")
            session_ctx = self._make_session_ctx(session_dir)

            preconv_path = os.path.join(session_dir, PRECONVERTED_AUDIO_FINAL)
            with open(preconv_path, "wb") as fh:
                fh.write(b"x" * 8192)
            preconv_size = os.path.getsize(preconv_path)

            html_path = os.path.join(tmpdir, "output.html")
            input_path = os.path.join(tmpdir, "input.mp3")
            with open(input_path, "wb") as fh:
                fh.write(b"fake")

            with patch("el_sbobinator.shared.SESSION_ROOT", tmpdir):
                _shared.invalidate_session_storage_cache()
                info_before = _shared.get_session_storage_info()
                self.assertGreaterEqual(
                    info_before["total_bytes"],
                    preconv_size,
                    "preconv file must be visible before pipeline runs",
                )

                base_patches = self._make_pipeline_patches(
                    session_ctx, preconv_path, html_path, tmpdir
                )
                spy = patch(
                    "el_sbobinator.pipeline.pipeline.invalidate_session_storage_cache",
                    wraps=_shared.invalidate_session_storage_cache,
                )

                app = _PromptBlockingApp()
                with contextlib.ExitStack() as stack:
                    for p in base_patches:
                        stack.enter_context(p)
                    mock_invalidate = stack.enter_context(spy)
                    esegui_sbobinatura(input_path, "fake-key", app)

                mock_invalidate.assert_called_once()
                self.assertFalse(
                    os.path.exists(preconv_path),
                    "preconv file must be deleted by pipeline cleanup",
                )
                info_after = _shared.get_session_storage_info()
                self.assertEqual(
                    info_after["total_bytes"],
                    info_before["total_bytes"] - preconv_size,
                    "storage must reflect deletion immediately without manual invalidation",
                )

    def test_cleanup_failed_removal_does_not_invalidate_cache(self):
        from el_sbobinator.shared import PRECONVERTED_AUDIO_FINAL

        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = os.path.join(tmpdir, "session")
            session_ctx = self._make_session_ctx(session_dir)

            preconv_path = os.path.join(session_dir, PRECONVERTED_AUDIO_FINAL)
            with open(preconv_path, "wb") as fh:
                fh.write(b"x" * 8192)

            html_path = os.path.join(tmpdir, "output.html")
            input_path = os.path.join(tmpdir, "input.mp3")
            with open(input_path, "wb") as fh:
                fh.write(b"fake")

            base_patches = self._make_pipeline_patches(
                session_ctx, preconv_path, html_path, tmpdir
            )
            spy = patch(
                "el_sbobinator.pipeline.pipeline.invalidate_session_storage_cache"
            )
            _real_remove = os.remove

            def _selective_remove(p):
                if os.path.basename(str(p)) == PRECONVERTED_AUDIO_FINAL:
                    raise PermissionError("locked")
                return _real_remove(p)

            remove_fail = patch("os.remove", side_effect=_selective_remove)

            app = _PromptBlockingApp()
            with contextlib.ExitStack() as stack:
                for p in base_patches:
                    stack.enter_context(p)
                mock_invalidate = stack.enter_context(spy)
                stack.enter_context(remove_fail)
                esegui_sbobinatura(input_path, "fake-key", app)

            mock_invalidate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
