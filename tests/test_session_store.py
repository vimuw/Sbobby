import os
import unittest
from unittest.mock import patch

from el_sbobinator.core.session_store import (
    clone_session_settings,
    new_session,
    resolve_session_paths,
)


class SessionStoreTests(unittest.TestCase):
    def test_new_session_has_expected_defaults(self):
        with patch(
            "el_sbobinator.core.session_store.build_default_pipeline_settings",
            return_value={
                "model": "gemini-2.5-flash",
                "fallback_models": ["gemini-2.5-flash-lite"],
                "effective_model": "gemini-2.5-flash",
                "chunk_minutes": 15,
                "overlap_seconds": 30,
                "macro_char_limit": 22000,
                "preconvert_audio": True,
                "prefetch_next_chunk": True,
                "inline_audio_max_mb": 6.0,
                "audio": {"bitrate": "48k"},
            },
        ):
            session = new_session("lesson.mp3")
        self.assertEqual(session["stage"], "phase1")
        self.assertIn("phase1", session)
        self.assertIn("outputs", session)
        self.assertEqual(session["settings"]["model"], "gemini-2.5-flash")
        self.assertEqual(session["settings"]["effective_model"], "gemini-2.5-flash")
        self.assertEqual(
            session["settings"]["fallback_models"], ["gemini-2.5-flash-lite"]
        )
        self.assertEqual(session["settings"]["audio"]["bitrate"], "48k")

    def test_clone_session_settings_is_deep_copy(self):
        session = {"settings": {"audio": {"bitrate": "48k"}}}
        cloned = clone_session_settings(session)
        cloned["audio"]["bitrate"] = "64k"
        self.assertEqual(session["settings"]["audio"]["bitrate"], "48k")

    def test_resolve_session_paths_builds_consistent_layout(self):
        paths = resolve_session_paths("lesson.mp3")
        self.assertTrue(paths.session_path.endswith("session.json"))
        self.assertTrue(paths.phase1_chunks_dir.endswith("phase1_chunks"))
        self.assertTrue(paths.phase2_revised_dir.endswith("phase2_revised"))


class EnsureSessionDirsTests(unittest.TestCase):
    def test_ensure_session_dirs_creates_all_dirs(self):
        import tempfile

        from el_sbobinator.core.session_store import SessionPaths, ensure_session_dirs

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = SessionPaths(
                session_dir=tmpdir,
                session_path=tmpdir + "/session.json",
                phase1_chunks_dir=tmpdir + "/phase1_chunks",
                phase2_revised_dir=tmpdir + "/phase2_revised",
                macro_path=tmpdir + "/macro.json",
            )
            ensure_session_dirs(paths)

            for d in (
                paths.phase1_chunks_dir,
                paths.phase2_revised_dir,
            ):
                self.assertTrue(os.path.isdir(d), f"Expected dir to exist: {d}")

    def test_reset_session_dirs_wipes_and_recreates(self):
        import tempfile

        from el_sbobinator.core.session_store import SessionPaths, reset_session_dirs

        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = os.path.join(tmpdir, "session")
            paths = SessionPaths(
                session_dir=session_dir,
                session_path=session_dir + "/session.json",
                phase1_chunks_dir=session_dir + "/phase1_chunks",
                phase2_revised_dir=session_dir + "/phase2_revised",
                macro_path=session_dir + "/macro.json",
            )
            # Create the dir with a file inside
            os.makedirs(paths.phase1_chunks_dir, exist_ok=True)
            sentinel = os.path.join(paths.phase1_chunks_dir, "chunk_000.md")
            with open(sentinel, "w") as fh:
                fh.write("data")

            reset_session_dirs(paths)

            self.assertFalse(os.path.exists(sentinel), "Old file should be gone")
            self.assertTrue(
                os.path.isdir(paths.phase1_chunks_dir), "Dir should exist again"
            )


class SaveLoadSessionTests(unittest.TestCase):
    def test_save_load_round_trip_and_sets_updated_at(self):
        import tempfile

        from el_sbobinator.core.session_store import load_session, save_session

        session = {"stage": "phase2", "custom_key": "hello"}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "session.json")
            save_session(path, session)
            loaded = load_session(path)

        self.assertEqual(loaded["stage"], "phase2")
        self.assertEqual(loaded["custom_key"], "hello")
        self.assertIn("updated_at", loaded)

    def test_update_session_returns_old_snapshot(self):
        from el_sbobinator.core.session_store import _update_session

        session = {"stage": "phase1", "value": 1}
        snapshot = _update_session(session, {"stage": "phase2", "value": 2})

        self.assertEqual(snapshot["stage"], "phase1")
        self.assertEqual(snapshot["value"], 1)
        self.assertEqual(session["stage"], "phase2")
        self.assertEqual(session["value"], 2)


class NewSessionCustomSettingsTests(unittest.TestCase):
    def test_new_session_custom_settings_used_verbatim(self):
        from el_sbobinator.core.session_store import new_session

        custom = {"model": "custom-model", "chunk_minutes": 5}
        session = new_session("lesson.mp3", settings=custom)
        self.assertEqual(session["settings"]["model"], "custom-model")
        self.assertEqual(session["settings"]["chunk_minutes"], 5)


class ResolveSessionPathsHintTests(unittest.TestCase):
    def test_hint_overrides_default_path(self):
        import tempfile

        from el_sbobinator.core.session_store import resolve_session_paths

        with tempfile.TemporaryDirectory() as tmpdir:
            hint_dir = os.path.join(tmpdir, "my_session")
            paths = resolve_session_paths("lesson.mp3", session_dir_hint=hint_dir)

        self.assertTrue(paths.session_dir.endswith("my_session"))


if __name__ == "__main__":
    unittest.main()
