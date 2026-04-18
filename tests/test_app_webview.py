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

    def test_update_model_first_call_sets_primary_model(self):
        adapter = PipelineAdapter(None, cancel_event=__import__("threading").Event())
        adapter.update_model("gemini-2.5-flash")
        self.assertEqual(adapter.last_primary_model, "gemini-2.5-flash")
        self.assertEqual(adapter.last_effective_model, "gemini-2.5-flash")

    def test_update_model_subsequent_call_does_not_change_primary_model(self):
        adapter = PipelineAdapter(None, cancel_event=__import__("threading").Event())
        adapter.update_model("gemini-2.5-flash")
        adapter.update_model("gemini-2.5-flash-lite")
        self.assertEqual(adapter.last_primary_model, "gemini-2.5-flash")
        self.assertEqual(adapter.last_effective_model, "gemini-2.5-flash-lite")

    def test_reset_run_state_clears_primary_model(self):
        adapter = PipelineAdapter(None, cancel_event=__import__("threading").Event())
        adapter.update_model("gemini-2.5-flash")
        adapter.update_model("gemini-2.5-flash-lite")
        adapter.reset_run_state()
        self.assertIsNone(adapter.last_primary_model)
        self.assertIsNone(adapter.last_effective_model)

    def test_primary_model_reset_allows_new_run_to_capture_new_primary(self):
        adapter = PipelineAdapter(None, cancel_event=__import__("threading").Event())
        adapter.update_model("gemini-2.5-flash")
        adapter.update_model("gemini-2.5-flash-lite")
        adapter.reset_run_state()
        adapter.update_model("gemini-3-flash-preview")
        self.assertEqual(adapter.last_primary_model, "gemini-3-flash-preview")
        self.assertEqual(adapter.last_effective_model, "gemini-3-flash-preview")

    def test_save_html_content_preserves_head(self):
        import tempfile as _tempfile

        api = ElSbobinatorApi()
        with _tempfile.NamedTemporaryFile(
            "w+", suffix=".html", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(
                "<!DOCTYPE html><html><head><meta charset='utf-8'><style>body{color:red}</style></head>"
                "<body><p>Old</p></body></html>"
            )
            path = tmp.name

        with patch(
            "el_sbobinator.app_webview.get_desktop_dir",
            return_value=_tempfile.gettempdir(),
        ):
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
        self.assertEqual(
            result["name"], __import__("os").path.basename(window.dialog_result)
        )

    def test_ask_files_accepts_string_dialog_result(self):
        api = ElSbobinatorApi()
        window = _FakeWindow()
        with tempfile.NamedTemporaryFile("wb", suffix=".mp3", delete=False) as tmp:
            window.dialog_result = tmp.name
        api.set_window(window)

        result = api.ask_files()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["path"], window.dialog_result)
        self.assertEqual(
            result[0]["name"], __import__("os").path.basename(window.dialog_result)
        )

    @patch("el_sbobinator.validation_service.validate_environment")
    def test_validate_environment_returns_backend_result(self, mock_validate):
        api = ElSbobinatorApi()
        mock_validate.return_value = {
            "ok": True,
            "summary": "Ambiente pronto.",
            "checks": [
                {"id": "ffmpeg", "label": "FFmpeg", "status": "ok", "message": "ok"}
            ],
        }

        result = api.validate_environment(api_key="fake", check_api_key=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["summary"], "Ambiente pronto.")
        mock_validate.assert_called_once_with(
            api_key="fake",
            validate_api_key=True,
            preferred_model=None,
            fallback_models=None,
        )

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
    def test_process_done_marks_cancelled_when_run_status_is_cancelled(
        self, mock_pipeline_run
    ):
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
                [
                    {
                        "id": "file-1",
                        "path": file_path,
                        "name": "lesson.mp3",
                        "size": 4,
                        "duration": 1,
                    }
                ],
                api_key="fake-key",
                resume_session=True,
            )

            self.assertTrue(result["ok"])
            self.assertIsNotNone(api._processing_thread)
            api._processing_thread.join(timeout=2)
            self.assertFalse(
                api._processing_thread.is_alive(),
                "Il thread di processing non si e' fermato.",
            )
        finally:
            try:
                __import__("os").unlink(file_path)
            except OSError:
                pass

        process_done_events = [
            data for fn_name, data, _batched in emitted if fn_name == "processDone"
        ]
        self.assertEqual(len(process_done_events), 1)
        self.assertTrue(process_done_events[0]["cancelled"])
        self.assertEqual(process_done_events[0]["completed"], 0)
        self.assertEqual(process_done_events[0]["failed"], 0)
        self.assertEqual(process_done_events[0]["total"], 1)

    @patch("el_sbobinator.pipeline.esegui_sbobinatura")
    def test_start_processing_honors_file_level_resume_override(
        self, mock_pipeline_run
    ):
        api = ElSbobinatorApi()
        observed_resume_values = []

        def fake_pipeline_run(_path, _api_key, adapter, resume_session=True):
            observed_resume_values.append(resume_session)
            adapter.set_run_result("completed", "")
            adapter.last_output_html = _path + ".html"
            adapter.last_output_dir = __import__("os").path.dirname(_path)

        mock_pipeline_run.side_effect = fake_pipeline_run

        with tempfile.NamedTemporaryFile("wb", suffix=".mp3", delete=False) as tmp:
            tmp.write(b"fake")
            file_path = tmp.name

        try:
            result = api.start_processing(
                [
                    {
                        "id": "file-1",
                        "path": file_path,
                        "name": "lesson.mp3",
                        "size": 4,
                        "duration": 1,
                        "resume_session": False,
                    }
                ],
                api_key="fake-key",
                resume_session=True,
            )

            self.assertTrue(result["ok"])
            self.assertIsNotNone(api._processing_thread)
            api._processing_thread.join(timeout=2)
            self.assertFalse(api._processing_thread.is_alive())
        finally:
            try:
                __import__("os").unlink(file_path)
            except OSError:
                pass

        self.assertEqual(observed_resume_values, [False])

    def test_read_html_content_falls_back_to_session_dir(self):
        import os

        api = ElSbobinatorApi()
        with (
            tempfile.TemporaryDirectory() as desktop_dir,
            tempfile.TemporaryDirectory() as session_root,
        ):
            session_dir = os.path.join(session_root, "abc123")
            os.makedirs(session_dir)
            html_name = "Lesson_Sbobina.html"
            session_html = os.path.join(session_dir, html_name)
            with open(session_html, "w", encoding="utf-8") as fh:
                fh.write(
                    "<!DOCTYPE html><html><head></head><body><p>ok</p></body></html>"
                )

            desktop_html = os.path.join(desktop_dir, html_name)

            with (
                patch(
                    "el_sbobinator.app_webview.get_desktop_dir",
                    return_value=desktop_dir,
                ),
                patch.object(api, "_get_session_root", return_value=session_root),
            ):
                result = api.read_html_content(desktop_html)

        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("<p>ok</p>", result["content"])

    def test_save_html_content_falls_back_to_session_dir(self):
        import os

        api = ElSbobinatorApi()
        with (
            tempfile.TemporaryDirectory() as desktop_dir,
            tempfile.TemporaryDirectory() as session_root,
        ):
            session_dir = os.path.join(session_root, "abc123")
            os.makedirs(session_dir)
            html_name = "Lesson_Sbobina.html"
            session_html = os.path.join(session_dir, html_name)
            with open(session_html, "w", encoding="utf-8") as fh:
                fh.write(
                    "<!DOCTYPE html><html><head><style>body{}</style></head>"
                    "<body><p>Old</p></body></html>"
                )

            desktop_html = os.path.join(desktop_dir, html_name)

            with (
                patch(
                    "el_sbobinator.app_webview.get_desktop_dir",
                    return_value=desktop_dir,
                ),
                patch.object(api, "_get_session_root", return_value=session_root),
            ):
                result = api.save_html_content(desktop_html, "<p>New</p>")

            self.assertTrue(result["ok"], result.get("error"))
            with open(session_html, "r", encoding="utf-8") as fh:
                saved = fh.read()
            self.assertIn("<p>New</p>", saved)

    def test_read_html_content_rebuilds_from_session_when_file_missing_everywhere(self):
        import json
        import os

        api = ElSbobinatorApi()
        with (
            tempfile.TemporaryDirectory() as desktop_dir,
            tempfile.TemporaryDirectory() as session_root,
            tempfile.TemporaryDirectory() as audio_dir,
        ):
            session_dir = os.path.join(session_root, "abc123")
            phase2_revised_dir = os.path.join(session_dir, "phase2_revised")
            os.makedirs(phase2_revised_dir)

            with open(
                os.path.join(phase2_revised_dir, "rev_000.md"), "w", encoding="utf-8"
            ) as fh:
                fh.write("## Contenuto della sbobina")

            audio_path = os.path.join(audio_dir, "Lesson.mp3")
            with open(audio_path, "wb") as fh:
                fh.write(b"fake")

            html_name = "Lesson_Sbobina.html"
            session_json = {
                "schema_version": 1,
                "stage": "done",
                "input": {"path": audio_path},
                "outputs": {"html": os.path.join(desktop_dir, html_name)},
                "settings": {},
                "phase1": {},
                "phase2": {},
                "boundary": {},
                "last_error": None,
            }
            session_path = os.path.join(session_dir, "session.json")
            with open(session_path, "w", encoding="utf-8") as fh:
                json.dump(session_json, fh)

            desktop_html = os.path.join(desktop_dir, html_name)

            with (
                patch(
                    "el_sbobinator.app_webview.get_desktop_dir",
                    return_value=desktop_dir,
                ),
                patch.object(api, "_get_session_root", return_value=session_root),
            ):
                result = api.read_html_content(desktop_html)

            self.assertTrue(result["ok"], result.get("error"))
            self.assertIn("Contenuto della sbobina", result["content"])

            rebuilt_path = os.path.join(session_dir, html_name)
            self.assertTrue(
                os.path.isfile(rebuilt_path),
                "HTML deve essere scritto nella session dir",
            )

            with open(session_path, "r", encoding="utf-8") as fh:
                updated = json.load(fh)
            self.assertEqual(
                os.path.basename(updated["outputs"]["html"]),
                html_name,
                "session.json deve essere aggiornato con il nuovo path",
            )

    def test_rebuild_html_uses_html_basename_when_input_path_renamed(self):
        """If input_path in session.json produces a different basename than the
        recorded outputs.html, the rebuilt file must still use html_basename."""
        import json
        import os

        api = ElSbobinatorApi()
        with (
            tempfile.TemporaryDirectory() as desktop_dir,
            tempfile.TemporaryDirectory() as session_root,
            tempfile.TemporaryDirectory() as audio_dir,
        ):
            session_dir = os.path.join(session_root, "abc123")
            phase2_revised_dir = os.path.join(session_dir, "phase2_revised")
            os.makedirs(phase2_revised_dir)

            with open(
                os.path.join(phase2_revised_dir, "rev_000.md"), "w", encoding="utf-8"
            ) as fh:
                fh.write("## Contenuto renamed")

            # input_path now points to a file with a *different* stem than html_basename
            renamed_audio = os.path.join(audio_dir, "RenamedLesson.mp3")
            with open(renamed_audio, "wb") as fh:
                fh.write(b"fake")

            original_html_name = "OriginalLesson_Sbobina.html"
            session_json = {
                "schema_version": 1,
                "stage": "done",
                "input": {"path": renamed_audio},
                "outputs": {"html": os.path.join(desktop_dir, original_html_name)},
                "settings": {},
                "phase1": {},
                "phase2": {},
                "boundary": {},
                "last_error": None,
            }
            session_path = os.path.join(session_dir, "session.json")
            with open(session_path, "w", encoding="utf-8") as fh:
                json.dump(session_json, fh)

            desktop_html = os.path.join(desktop_dir, original_html_name)

            with (
                patch(
                    "el_sbobinator.app_webview.get_desktop_dir",
                    return_value=desktop_dir,
                ),
                patch.object(api, "_get_session_root", return_value=session_root),
            ):
                result = api.read_html_content(desktop_html)

            self.assertTrue(result["ok"], result.get("error"))
            self.assertIn("Contenuto renamed", result["content"])

            # The file in session_dir must use the ORIGINAL html basename, not
            # "RenamedLesson_Sbobina.html" (which export would derive from input_path)
            rebuilt_path = os.path.join(session_dir, original_html_name)
            self.assertTrue(
                os.path.isfile(rebuilt_path),
                "Rebuilt HTML must use html_basename, not the name derived from input_path",
            )
            wrong_path = os.path.join(session_dir, "RenamedLesson_Sbobina.html")
            self.assertFalse(
                os.path.isfile(wrong_path),
                "A file with the input_path-derived basename must not exist",
            )

            with open(session_path, "r", encoding="utf-8") as fh:
                updated = json.load(fh)
            self.assertEqual(
                os.path.basename(updated["outputs"]["html"]),
                original_html_name,
                "session.json must record the canonical html_basename",
            )

    def test_rebuild_html_from_session_picks_newest_session(self):
        """Two sessions share the same html basename; the newer one must be rebuilt."""
        import json
        import os
        import time

        api = ElSbobinatorApi()
        with (
            tempfile.TemporaryDirectory() as desktop_dir,
            tempfile.TemporaryDirectory() as session_root,
            tempfile.TemporaryDirectory() as audio_dir,
        ):
            html_name = "Lecture_Sbobina.html"
            audio_path = os.path.join(audio_dir, "Lecture.mp3")
            with open(audio_path, "wb") as fh:
                fh.write(b"fake")

            def _make_session(name, content, mtime_offset):
                sdir = os.path.join(session_root, name)
                p2dir = os.path.join(sdir, "phase2_revised")
                os.makedirs(p2dir)
                with open(
                    os.path.join(p2dir, "rev_000.md"), "w", encoding="utf-8"
                ) as fh:
                    fh.write(content)
                sdata = {
                    "schema_version": 1,
                    "stage": "done",
                    "input": {"path": audio_path},
                    "outputs": {"html": os.path.join(desktop_dir, html_name)},
                    "settings": {},
                    "phase1": {},
                    "phase2": {},
                    "boundary": {},
                    "last_error": None,
                }
                spath = os.path.join(sdir, "session.json")
                with open(spath, "w", encoding="utf-8") as fh:
                    json.dump(sdata, fh)
                t = time.time() + mtime_offset
                os.utime(spath, (t, t))
                return sdir

            _make_session("old_session", "## Vecchia sbobina", -3600)
            _make_session("new_session", "## Nuova sbobina", 0)

            with (
                patch(
                    "el_sbobinator.app_webview.get_desktop_dir",
                    return_value=desktop_dir,
                ),
                patch.object(api, "_get_session_root", return_value=session_root),
            ):
                result = api.read_html_content(os.path.join(desktop_dir, html_name))

            self.assertTrue(result["ok"], result.get("error"))
            self.assertIn("Nuova sbobina", result["content"])
            self.assertNotIn("Vecchia sbobina", result["content"])

    def test_rebuild_html_from_session_skips_incomplete_session(self):
        """Regression: a session whose stage != 'done' must not be used as a
        rebuild candidate even if phase2_revised/ and session.json exist."""
        import json
        import os

        api = ElSbobinatorApi()
        with (
            tempfile.TemporaryDirectory() as desktop_dir,
            tempfile.TemporaryDirectory() as session_root,
            tempfile.TemporaryDirectory() as audio_dir,
        ):
            html_name = "Lecture_Incomplete.html"
            audio_path = os.path.join(audio_dir, "Lecture.mp3")
            with open(audio_path, "wb") as fh:
                fh.write(b"fake")

            sdir = os.path.join(session_root, "incomplete_session")
            p2dir = os.path.join(sdir, "phase2_revised")
            os.makedirs(p2dir)
            with open(os.path.join(p2dir, "rev_000.md"), "w", encoding="utf-8") as fh:
                fh.write("## Partial content")
            sdata = {
                "schema_version": 1,
                "stage": "phase2",
                "input": {"path": audio_path},
                "outputs": {"html": os.path.join(desktop_dir, html_name)},
                "settings": {},
                "phase1": {},
                "phase2": {},
                "boundary": {},
                "last_error": None,
            }
            with open(os.path.join(sdir, "session.json"), "w", encoding="utf-8") as fh:
                json.dump(sdata, fh)

            with (
                patch(
                    "el_sbobinator.app_webview.get_desktop_dir",
                    return_value=desktop_dir,
                ),
                patch.object(api, "_get_session_root", return_value=session_root),
            ):
                result = api.read_html_content(os.path.join(desktop_dir, html_name))

            self.assertFalse(result["ok"])

    def test_html_shell_cache_hit_after_desktop_file_deleted(self):
        """Bug 4 regression: shell cached under Desktop path must be reused when
        save_html_content falls back to the session-dir copy after the Desktop
        file is deleted while the preview modal was open."""
        import os
        from unittest.mock import patch as _patch

        api = ElSbobinatorApi()
        html_name = "Lesson_Cache.html"
        full_html = (
            "<!DOCTYPE html><html>"
            "<head><style>body{color:red}</style></head>"
            "<body><p>Original</p></body>"
            "</html>"
        )

        with (
            tempfile.TemporaryDirectory() as desktop_dir,
            tempfile.TemporaryDirectory() as session_root,
        ):
            session_dir = os.path.join(session_root, "sess1")
            os.makedirs(session_dir)
            session_html = os.path.join(session_dir, html_name)
            desktop_html = os.path.join(desktop_dir, html_name)

            with open(desktop_html, "w", encoding="utf-8") as fh:
                fh.write(full_html)
            with open(session_html, "w", encoding="utf-8") as fh:
                fh.write(full_html)

            with (
                _patch(
                    "el_sbobinator.app_webview.get_desktop_dir",
                    return_value=desktop_dir,
                ),
                _patch.object(api, "_get_session_root", return_value=session_root),
            ):
                read_result = api.read_html_content(desktop_html)
                self.assertTrue(read_result["ok"])

                os.remove(desktop_html)

                with _patch(
                    "el_sbobinator.app_webview.save_html_body_content",
                    wraps=__import__(
                        "el_sbobinator.file_ops", fromlist=["save_html_body_content"]
                    ).save_html_body_content,
                ) as mock_save:
                    result = api.save_html_content(desktop_html, "<p>New</p>")

                self.assertTrue(result["ok"], result.get("error"))
                self.assertIsNotNone(
                    mock_save.call_args, "save_html_body_content must have been called"
                )
                shell_arg = mock_save.call_args.kwargs.get("shell")
                self.assertIsNotNone(
                    shell_arg,
                    "shell must be passed from cache — no extra disk read expected",
                )

            with open(session_html, "r", encoding="utf-8") as fh:
                saved = fh.read()
            self.assertIn("<p>New</p>", saved)
            self.assertIn("<style>body{color:red}</style>", saved)

    def test_save_uses_same_session_dir_as_read_when_background_write_changes_mtime(
        self,
    ):
        """Bug 2 regression: _resolved_path_cache must pin the session dir chosen by
        read_html_content so that a background mtime change cannot redirect
        save_html_content to a different session dir."""
        import os
        import time
        from unittest.mock import patch as _patch

        api = ElSbobinatorApi()
        html_name = "Lecture_Sbobina.html"
        full_html = (
            "<!DOCTYPE html><html>"
            "<head><style>body{color:green}</style></head>"
            "<body><p>Original</p></body>"
            "</html>"
        )

        with (
            tempfile.TemporaryDirectory() as desktop_dir,
            tempfile.TemporaryDirectory() as session_root,
        ):
            sess_a = os.path.join(session_root, "sess_a")
            sess_b = os.path.join(session_root, "sess_b")
            os.makedirs(sess_a)
            os.makedirs(sess_b)

            path_a = os.path.join(sess_a, html_name)
            path_b = os.path.join(sess_b, html_name)
            desktop_html = os.path.join(desktop_dir, html_name)

            with open(path_a, "w", encoding="utf-8") as fh:
                fh.write(full_html.replace("Original", "A"))
            with open(path_b, "w", encoding="utf-8") as fh:
                fh.write(full_html.replace("Original", "B"))

            now = time.time()
            os.utime(path_a, (now - 10, now - 10))
            os.utime(path_b, (now, now))

            with (
                _patch(
                    "el_sbobinator.app_webview.get_desktop_dir",
                    return_value=desktop_dir,
                ),
                _patch.object(api, "_get_session_root", return_value=session_root),
            ):
                read_result = api.read_html_content(desktop_html)
                self.assertTrue(read_result["ok"])
                self.assertIn(
                    "<p>B</p>",
                    read_result["content"],
                    "read must pick sess_b (higher mtime)",
                )

                os.utime(path_a, (now + 20, now + 20))

                result = api.save_html_content(desktop_html, "<p>Edited</p>")

            self.assertTrue(result["ok"], result.get("error"))

            with open(path_b, "r", encoding="utf-8") as fh:
                saved_b = fh.read()
            with open(path_a, "r", encoding="utf-8") as fh:
                saved_a = fh.read()

            self.assertIn(
                "<p>Edited</p>", saved_b, "save must write to sess_b (pinned by cache)"
            )
            self.assertNotIn(
                "<p>Edited</p>",
                saved_a,
                "sess_a must not be touched despite higher mtime now",
            )

    def test_read_html_content_pins_cache_when_file_exists(self):
        """Bug 1 regression: _resolved_path_cache must be populated even when the
        original file exists at read time, so a transient unavailability at save
        time does not cause a mtime-based session-dir mismatch."""
        import os
        from unittest.mock import patch as _patch

        api = ElSbobinatorApi()
        html_name = "Lecture_Sbobina.html"
        full_html = (
            "<!DOCTYPE html><html>"
            "<head><style>body{color:red}</style></head>"
            "<body><p>Original</p></body>"
            "</html>"
        )

        with (
            tempfile.TemporaryDirectory() as desktop_dir,
            tempfile.TemporaryDirectory() as session_root,
        ):
            desktop_html = os.path.join(desktop_dir, html_name)
            with open(desktop_html, "w", encoding="utf-8") as fh:
                fh.write(full_html)

            with (
                _patch(
                    "el_sbobinator.app_webview.get_desktop_dir",
                    return_value=desktop_dir,
                ),
                _patch.object(api, "_get_session_root", return_value=session_root),
            ):
                result = api.read_html_content(desktop_html)
                self.assertTrue(result["ok"])

            real_path = os.path.realpath(os.path.abspath(desktop_html))
            self.assertIn(
                real_path,
                api._resolved_path_cache,
                "_resolved_path_cache must be populated even when file exists at read time",
            )
            self.assertEqual(api._resolved_path_cache[real_path], real_path)

    def test_html_shell_cache_no_poisoning_on_same_basename(self):
        """Bug 2 regression: two files with the same basename in different session
        dirs must not overwrite each other's cache entry.  File A's save must
        receive shell_A even after file B (same basename, different path) was
        read afterwards."""
        import os
        from unittest.mock import patch as _patch

        api = ElSbobinatorApi()
        html_name = "lecture.html"
        shell_a = "<head><style>body{color:red}</style></head>"
        shell_b = "<head><style>body{color:blue}</style></head>"
        html_a = f"<!DOCTYPE html><html>{shell_a}<body><p>A</p></body></html>"
        html_b = f"<!DOCTYPE html><html>{shell_b}<body><p>B</p></body></html>"

        with (
            tempfile.TemporaryDirectory() as desktop_dir,
            tempfile.TemporaryDirectory() as session_root,
        ):
            sess_a = os.path.join(session_root, "sessA")
            sess_b = os.path.join(session_root, "sessB")
            os.makedirs(sess_a)
            os.makedirs(sess_b)
            path_a = os.path.join(sess_a, html_name)
            path_b = os.path.join(sess_b, html_name)

            with open(path_a, "w", encoding="utf-8") as fh:
                fh.write(html_a)
            with open(path_b, "w", encoding="utf-8") as fh:
                fh.write(html_b)

            with (
                _patch(
                    "el_sbobinator.app_webview.get_desktop_dir",
                    return_value=desktop_dir,
                ),
                _patch.object(api, "_get_session_root", return_value=session_root),
            ):
                self.assertTrue(api.read_html_content(path_a)["ok"])
                self.assertTrue(api.read_html_content(path_b)["ok"])

                with _patch(
                    "el_sbobinator.app_webview.save_html_body_content",
                    wraps=__import__(
                        "el_sbobinator.file_ops", fromlist=["save_html_body_content"]
                    ).save_html_body_content,
                ) as mock_save:
                    result = api.save_html_content(path_a, "<p>New A</p>")

            self.assertTrue(result["ok"], result.get("error"))
            shell_arg = mock_save.call_args.kwargs.get("shell")
            self.assertIsNotNone(shell_arg, "shell must be passed from cache")
            self.assertIn(
                "color:red", "".join(shell_arg), "must use shell_A, not shell_B"
            )
            self.assertNotIn("color:blue", "".join(shell_arg))


class TestFallbackAllowedRootsRecheck(unittest.TestCase):
    """Regression tests: fallback path returned by _find_html_in_session_dirs must be
    re-checked against allowed_roots before use (symlink-escape security gap)."""

    def _make_api_with_roots(self, tmp, desktop_dir, session_root):
        from el_sbobinator.app_webview import ElSbobinatorApi

        api = ElSbobinatorApi()
        return api, desktop_dir, session_root

    def test_read_html_content_rejects_fallback_outside_allowed_roots(self):
        import os
        import tempfile

        from unittest.mock import patch
        from el_sbobinator.app_webview import ElSbobinatorApi

        with tempfile.TemporaryDirectory() as tmp:
            desktop_dir = os.path.join(tmp, "desktop")
            session_root = os.path.join(tmp, "sessions")
            outside_dir = os.path.join(tmp, "outside")
            os.makedirs(desktop_dir)
            os.makedirs(session_root)
            os.makedirs(outside_dir)

            outside_html = os.path.join(outside_dir, "note.html")
            with open(outside_html, "w", encoding="utf-8") as fh:
                fh.write("<html><body><p>secret</p></body></html>")

            desktop_html = os.path.join(desktop_dir, "note.html")
            api = ElSbobinatorApi()

            with (
                patch(
                    "el_sbobinator.app_webview.get_desktop_dir",
                    return_value=desktop_dir,
                ),
                patch.object(api, "_get_session_root", return_value=session_root),
                patch.object(
                    api,
                    "_find_html_in_session_dirs",
                    return_value=os.path.realpath(outside_html),
                ),
                patch.object(api, "_rebuild_html_from_session", return_value=None),
            ):
                result = api.read_html_content(desktop_html)

        self.assertFalse(result["ok"])
        self.assertIn("Accesso negato", result["error"])

    def test_save_html_content_rejects_fallback_outside_allowed_roots(self):
        import os
        import tempfile

        from unittest.mock import patch
        from el_sbobinator.app_webview import ElSbobinatorApi

        with tempfile.TemporaryDirectory() as tmp:
            desktop_dir = os.path.join(tmp, "desktop")
            session_root = os.path.join(tmp, "sessions")
            outside_dir = os.path.join(tmp, "outside")
            os.makedirs(desktop_dir)
            os.makedirs(session_root)
            os.makedirs(outside_dir)

            outside_html = os.path.join(outside_dir, "note.html")
            with open(outside_html, "w", encoding="utf-8") as fh:
                fh.write("<html><body><p>original</p></body></html>")

            desktop_html = os.path.join(desktop_dir, "note.html")
            api = ElSbobinatorApi()

            with (
                patch(
                    "el_sbobinator.app_webview.get_desktop_dir",
                    return_value=desktop_dir,
                ),
                patch.object(api, "_get_session_root", return_value=session_root),
                patch.object(
                    api,
                    "_find_html_in_session_dirs",
                    return_value=os.path.realpath(outside_html),
                ),
                patch.object(api, "_rebuild_html_from_session", return_value=None),
            ):
                result = api.save_html_content(desktop_html, "<p>pwned</p>")

            self.assertFalse(result["ok"])
            self.assertIn("Accesso negato", result["error"])
            with open(outside_html, "r", encoding="utf-8") as fh:
                self.assertNotIn(
                    "pwned", fh.read(), "file outside allowed roots must not be written"
                )

    def test_delete_session_removes_folder_when_inside_session_root(self):
        import os

        api = ElSbobinatorApi()
        with tempfile.TemporaryDirectory() as session_root:
            session_dir = os.path.join(session_root, "abc123")
            os.makedirs(session_dir)
            sentinel = os.path.join(session_dir, "session.json")
            with open(sentinel, "w", encoding="utf-8") as fh:
                fh.write("{}")

            with patch.object(api, "_get_session_root", return_value=session_root):
                result = api.delete_session(session_dir)

        self.assertTrue(result["ok"], result.get("error"))
        self.assertFalse(os.path.exists(session_dir))

    def test_delete_session_rejects_path_outside_session_root(self):
        import os

        api = ElSbobinatorApi()
        with (
            tempfile.TemporaryDirectory() as session_root,
            tempfile.TemporaryDirectory() as outside_dir,
        ):
            victim = os.path.join(outside_dir, "important")
            os.makedirs(victim)

            with patch.object(api, "_get_session_root", return_value=session_root):
                result = api.delete_session(victim)

            self.assertFalse(result["ok"])
            self.assertIn("Percorso non valido", result["error"])
            self.assertTrue(os.path.exists(victim))

    def test_delete_session_evicts_resolved_path_cache(self):
        import os

        api = ElSbobinatorApi()
        with tempfile.TemporaryDirectory() as session_root:
            session_dir = os.path.join(session_root, "ses1")
            os.makedirs(session_dir)
            html_path = os.path.join(session_dir, "note.html")
            with open(html_path, "w") as fh:
                fh.write("<html><body></body></html>")

            api._resolved_path_cache["key1"] = html_path
            api._resolved_path_cache["key2"] = session_dir
            api._resolved_path_cache["key3"] = "/unrelated/path"

            with patch.object(api, "_get_session_root", return_value=session_root):
                result = api.delete_session(session_dir)

        self.assertTrue(result["ok"], result.get("error"))
        self.assertNotIn("key1", api._resolved_path_cache)
        self.assertNotIn("key2", api._resolved_path_cache)
        self.assertIn("key3", api._resolved_path_cache)

    def test_download_and_install_update_uses_streaming_urlopen(self):
        import io
        import os
        import sys

        api = ElSbobinatorApi()
        fake_data = b"fake exe payload"

        class _FakeResp:
            def __init__(self):
                self._buf = io.BytesIO(fake_data)

            def read(self, n):
                return self._buf.read(n)

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = os.path.join(tmpdir, "setup.exe")

            class _FakeTmpFile:
                name = tmp_path

                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    pass

            with (
                patch(
                    "urllib.request.urlopen", return_value=_FakeResp()
                ) as mock_urlopen,
                patch("tempfile.NamedTemporaryFile", return_value=_FakeTmpFile()),
                patch.object(sys, "platform", "win32"),
                patch("os.startfile", create=True),
                patch("os.unlink"),
                patch("time.sleep"),
                patch("sys.exit"),
            ):
                api.download_and_install_update("v1.2.3")

            mock_urlopen.assert_called_once()
            _call_args = mock_urlopen.call_args
            self.assertEqual(
                _call_args.kwargs.get("timeout") or _call_args.args[1], 120
            )
            with open(tmp_path, "rb") as fh:
                self.assertEqual(fh.read(), fake_data)

    def test_cleanup_installer_daemon_retries_on_permission_error(self):
        import os
        import sys

        api = ElSbobinatorApi()
        call_counts = [0]
        done_event = threading.Event()

        def flaky_unlink(path):
            call_counts[0] += 1
            if call_counts[0] < 2:
                raise PermissionError("locked")
            done_event.set()

        class _FakeResp:
            def read(self, n):
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

        class _FakeTmpFile:
            name = "/tmp/fake_setup.exe"

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

        with (
            patch("urllib.request.urlopen", return_value=_FakeResp()),
            patch("tempfile.NamedTemporaryFile", return_value=_FakeTmpFile()),
            patch.object(sys, "platform", "win32"),
            patch("os.startfile", create=True),
            patch("os.unlink", side_effect=flaky_unlink),
            patch("time.sleep"),
        ):
            api.download_and_install_update("v1.0.0")
            done_event.wait(timeout=2.0)

        self.assertGreaterEqual(call_counts[0], 2)


if __name__ == "__main__":
    unittest.main()
