"""Regression tests for LocalMediaServer."""

import threading
import unittest
from unittest.mock import MagicMock

from el_sbobinator.media_server import LocalMediaServer


def _fake_server():
    srv = MagicMock()
    srv.server_address = ("127.0.0.1", 0)
    return srv


class EvictOldestTests(unittest.TestCase):
    def setUp(self):
        LocalMediaServer._servers.clear()

    def tearDown(self):
        LocalMediaServer._servers.clear()

    def test_no_error_at_capacity(self):
        """_evict_oldest_if_needed must not raise TypeError when _servers is a plain dict."""
        for i in range(LocalMediaServer.MAX_ENTRIES):
            LocalMediaServer._servers[f"/fake/path_{i}.mp3"] = (_fake_server(), 9000 + i)

        try:
            LocalMediaServer._evict_oldest_if_needed()
        except TypeError as exc:
            self.fail(f"_evict_oldest_if_needed raised TypeError: {exc}")

    def test_removes_first_inserted(self):
        """The oldest (first-inserted) entry is the one evicted."""
        paths = [f"/fake/path_{i}.mp3" for i in range(LocalMediaServer.MAX_ENTRIES)]
        for i, p in enumerate(paths):
            LocalMediaServer._servers[p] = (_fake_server(), 9000 + i)

        LocalMediaServer._evict_oldest_if_needed()

        self.assertNotIn(paths[0], LocalMediaServer._servers)
        for p in paths[1:]:
            self.assertIn(p, LocalMediaServer._servers)

    def test_noop_below_capacity(self):
        """No eviction occurs when below MAX_ENTRIES."""
        for i in range(LocalMediaServer.MAX_ENTRIES - 1):
            LocalMediaServer._servers[f"/fake/path_{i}.mp3"] = (_fake_server(), 9000 + i)

        LocalMediaServer._evict_oldest_if_needed()

        self.assertEqual(len(LocalMediaServer._servers), LocalMediaServer.MAX_ENTRIES - 1)

    def test_evict_calls_shutdown(self):
        """Evicted server's shutdown and server_close are called."""
        oldest = _fake_server()
        LocalMediaServer._servers["/fake/oldest.mp3"] = (oldest, 9000)
        for i in range(1, LocalMediaServer.MAX_ENTRIES):
            LocalMediaServer._servers[f"/fake/path_{i}.mp3"] = (_fake_server(), 9000 + i)

        LocalMediaServer._evict_oldest_if_needed()

        threading.Event().wait(0.1)
        oldest.shutdown.assert_called_once()
        oldest.server_close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
