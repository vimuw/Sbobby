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


if __name__ == "__main__":
    unittest.main()
