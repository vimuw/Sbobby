import os
import tempfile
import time
import unittest
from unittest.mock import patch

from el_sbobinator.core import shared
from el_sbobinator.core.shared import (
    _folder_newest_mtime,
    _folder_size,
    _partial_file_hash,
    cleanup_orphan_temp_chunks,
)
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

            with patch("el_sbobinator.core.shared.SESSION_ROOT", tmpdir):
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

            with patch("el_sbobinator.core.shared.SESSION_ROOT", tmpdir):
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


class CleanupOrphanTempChunksTests(unittest.TestCase):
    def test_removes_old_matching_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_file = os.path.join(tmpdir, "el_sbobinator_temp_old.mp3")
            fresh_file = os.path.join(tmpdir, "el_sbobinator_temp_fresh.mp3")
            unrelated = os.path.join(tmpdir, "other_file.mp3")

            for p in (old_file, fresh_file, unrelated):
                with open(p, "w") as f:
                    f.write("x")

            now = time.time()
            past = now - 13 * 3600
            os.utime(old_file, (past, past))

            with patch("tempfile.gettempdir", return_value=tmpdir):
                removed = cleanup_orphan_temp_chunks(max_age_seconds=12 * 3600)

            self.assertEqual(removed, 1)
            self.assertFalse(os.path.exists(old_file))
            self.assertTrue(os.path.exists(fresh_file))
            self.assertTrue(os.path.exists(unrelated))

    def test_non_matching_extensions_not_removed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            non_audio = os.path.join(tmpdir, "el_sbobinator_temp_x.txt")
            with open(non_audio, "w") as f:
                f.write("x")
            now = time.time()
            old = now - 25 * 3600
            os.utime(non_audio, (old, old))

            with patch("tempfile.gettempdir", return_value=tmpdir):
                removed = cleanup_orphan_temp_chunks(max_age_seconds=12 * 3600)

            self.assertEqual(removed, 0)
            self.assertTrue(os.path.exists(non_audio))


class PartialFileHashTests(unittest.TestCase):
    def test_existing_file_returns_hex_string(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello world")
            path = f.name
        try:
            result = _partial_file_hash(path)
            self.assertIsInstance(result, str)
            self.assertEqual(len(result), 64)
        finally:
            os.unlink(path)

    def test_nonexistent_file_returns_empty_string(self):
        result = _partial_file_hash("/nonexistent/does/not/exist.bin")
        self.assertEqual(result, "")

    def test_same_content_same_hash(self):
        with tempfile.NamedTemporaryFile(delete=False) as f1:
            f1.write(b"identical content")
            p1 = f1.name
        with tempfile.NamedTemporaryFile(delete=False) as f2:
            f2.write(b"identical content")
            p2 = f2.name
        try:
            self.assertEqual(_partial_file_hash(p1), _partial_file_hash(p2))
        finally:
            os.unlink(p1)
            os.unlink(p2)


class FolderSizeTests(unittest.TestCase):
    def test_counts_file_bytes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "data.bin")
            with open(path, "wb") as f:
                f.write(b"x" * 1024)
            size = _folder_size(tmpdir)
            self.assertEqual(size, 1024)

    def test_excludes_preconverted_partial(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            partial = os.path.join(tmpdir, shared.PRECONVERTED_AUDIO_PARTIAL)
            real = os.path.join(tmpdir, "real.bin")
            with open(partial, "wb") as f:
                f.write(b"x" * 2048)
            with open(real, "wb") as f:
                f.write(b"y" * 512)
            size = _folder_size(tmpdir)
            self.assertEqual(size, 512)

    def test_nonexistent_directory_returns_zero(self):
        size = _folder_size("/nonexistent/directory/abc")
        self.assertEqual(size, 0)


class FolderNewestMtimeTests(unittest.TestCase):
    def test_returns_newest_file_mtime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.path.join(tmpdir, "old.txt")
            new = os.path.join(tmpdir, "new.txt")
            with open(old, "w") as f:
                f.write("old")
            with open(new, "w") as f:
                f.write("new")
            now = time.time()
            os.utime(old, (now - 100, now - 100))
            os.utime(new, (now - 10, now - 10))
            mtime = _folder_newest_mtime(tmpdir)
            self.assertAlmostEqual(mtime, now - 10, delta=2)

    def test_empty_directory_falls_back_to_dir_mtime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mtime = _folder_newest_mtime(tmpdir)
            self.assertGreater(mtime, 0)


class CleanupOrphanSessionsMissingRootTests(unittest.TestCase):
    def test_absent_session_root_returns_zeros(self):
        with patch(
            "el_sbobinator.core.shared.SESSION_ROOT", "/nonexistent/path/abc123"
        ):
            result = shared.cleanup_orphan_sessions()
        self.assertEqual(result["removed"], 0)
        self.assertEqual(result["freed_bytes"], 0)
        self.assertEqual(result["errors"], 0)


class SessionStorageCacheHitTests(unittest.TestCase):
    def test_second_call_within_ttl_returns_cached_result(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("el_sbobinator.core.shared.SESSION_ROOT", tmpdir):
                shared.invalidate_session_storage_cache()
                first = shared.get_session_storage_info()
                os.makedirs(os.path.join(tmpdir, "new_session"))
                second = shared.get_session_storage_info()
                self.assertEqual(first["total_sessions"], second["total_sessions"])

    def test_invalidate_clears_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("el_sbobinator.core.shared.SESSION_ROOT", tmpdir):
                shared.invalidate_session_storage_cache()
                shared.get_session_storage_info()
                shared.invalidate_session_storage_cache()
                result = shared.get_session_storage_info()
                self.assertIn("total_sessions", result)

    def test_concurrent_callers_share_one_traversal(self):
        import concurrent.futures as cf
        import threading

        call_count = 0
        call_count_lock = threading.Lock()
        gate = threading.Event()

        def slow_compute() -> dict:
            nonlocal call_count
            gate.wait(timeout=5.0)
            with call_count_lock:
                call_count += 1
            return {"total_bytes": 0, "total_sessions": 0}

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("el_sbobinator.core.shared.SESSION_ROOT", tmpdir),
                patch(
                    "el_sbobinator.core.shared._compute_session_storage_info",
                    side_effect=slow_compute,
                ),
            ):
                shared.invalidate_session_storage_cache()
                with cf.ThreadPoolExecutor(max_workers=3) as pool:
                    futs = [
                        pool.submit(shared.get_session_storage_info) for _ in range(3)
                    ]
                    time.sleep(0.05)
                    gate.set()
                    results = [f.result() for f in futs]

        self.assertTrue(all("total_sessions" in r for r in results))
        self.assertEqual(call_count, 1)


if __name__ == "__main__":
    unittest.main()
