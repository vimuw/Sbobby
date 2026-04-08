import os
import tempfile
import time
import unittest
from unittest.mock import patch

from el_sbobinator import shared


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


if __name__ == "__main__":
    unittest.main()
