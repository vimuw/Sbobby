import os
import tempfile
import time
import unittest
from unittest.mock import patch

from el_sbobinator import shared
from el_sbobinator.pipeline.pipeline_settings import (
    build_default_pipeline_settings,
    load_and_sanitize_settings,
)


class SharedCleanupTests(unittest.TestCase):
    def test_cleanup_orphan_sessions_respects_cutoff_days(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            expired_dir = os.path.join(tmpdir, "expired")
            recent_dir = os.path.join(tmpdir, "recent")
            os.makedirs(expired_dir, exist_ok=True)
            os.makedirs(recent_dir, exist_ok=True)

            expired_file = os.path.join(expired_dir, "session.json")
            recent_file = os.path.join(recent_dir, "session.json")
            with open(expired_file, "w", encoding="utf-8") as fh:
                fh.write("expired")
            with open(recent_file, "w", encoding="utf-8") as fh:
                fh.write("recent")

            now = time.time()
            os.utime(expired_file, (now - 15 * 86400, now - 15 * 86400))
            os.utime(expired_dir, (now - 15 * 86400, now - 15 * 86400))
            os.utime(recent_file, (now - 13 * 86400, now - 13 * 86400))
            os.utime(recent_dir, (now - 13 * 86400, now - 13 * 86400))

            with patch("el_sbobinator.shared.SESSION_ROOT", tmpdir):
                result = shared.cleanup_orphan_sessions()

            self.assertEqual(result["removed"], 1)
            self.assertEqual(result["errors"], 0)
            self.assertFalse(os.path.exists(expired_dir))
            self.assertTrue(os.path.exists(recent_dir))

    def test_get_session_storage_info_ignores_preconverted_partial_until_promoted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = os.path.join(tmpdir, "active")
            os.makedirs(session_dir, exist_ok=True)

            partial_path = os.path.join(session_dir, shared.PRECONVERTED_AUDIO_PARTIAL)
            final_path = os.path.join(session_dir, shared.PRECONVERTED_AUDIO_FINAL)

            with open(partial_path, "wb") as fh:
                fh.write(b"x" * 4096)

            with patch("el_sbobinator.shared.SESSION_ROOT", tmpdir):
                shared.invalidate_session_storage_cache()
                info = shared.get_session_storage_info()
                self.assertEqual(info["total_sessions"], 1)
                self.assertEqual(info["total_bytes"], 0)

                os.replace(partial_path, final_path)

                shared.invalidate_session_storage_cache()
                info = shared.get_session_storage_info()
                self.assertEqual(info["total_sessions"], 1)
                self.assertEqual(info["total_bytes"], 4096)


class SharedPipelineDefaultsTests(unittest.TestCase):
    def test_build_default_pipeline_settings_uses_10_minutes_for_flash_lite(self):
        settings = build_default_pipeline_settings(
            {"preferred_model": "gemini-2.5-flash-lite", "fallback_models": []}
        )
        self.assertEqual(settings["model"], "gemini-2.5-flash-lite")
        self.assertEqual(settings["chunk_minutes"], 10)

    def test_build_default_pipeline_settings_keeps_15_minutes_for_other_models(self):
        settings = build_default_pipeline_settings(
            {"preferred_model": "gemini-2.5-flash", "fallback_models": []}
        )
        self.assertEqual(settings["model"], "gemini-2.5-flash")
        self.assertEqual(settings["chunk_minutes"], 15)

    def test_load_and_sanitize_settings_defaults_flash_lite_to_10_when_missing(self):
        session = {
            "settings": {
                "model": "gemini-2.5-flash-lite",
                "fallback_models": [],
                "effective_model": "gemini-2.5-flash-lite",
                "audio": {"bitrate": "48k"},
            }
        }

        settings, changed = load_and_sanitize_settings(session)

        self.assertTrue(changed)
        self.assertEqual(settings.chunk_minutes, 10)
        self.assertEqual(session["settings"]["chunk_minutes"], 10)

    def test_load_and_sanitize_settings_preserves_explicit_flash_lite_chunk_minutes(
        self,
    ):
        session = {
            "settings": {
                "model": "gemini-2.5-flash-lite",
                "fallback_models": [],
                "effective_model": "gemini-2.5-flash-lite",
                "chunk_minutes": 15,
                "overlap_seconds": 30,
                "macro_char_limit": 15000,
                "preconvert_audio": True,
                "prefetch_next_chunk": True,
                "inline_audio_max_mb": 6.0,
                "audio": {"bitrate": "48k"},
            }
        }

        settings, changed = load_and_sanitize_settings(session)

        self.assertFalse(changed)
        self.assertEqual(settings.chunk_minutes, 15)
        self.assertEqual(session["settings"]["chunk_minutes"], 15)


if __name__ == "__main__":
    unittest.main()
