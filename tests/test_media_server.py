"""Regression tests for LocalMediaServer."""

import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
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

    def test_cache_hit_survives_eviction(self):
        """A cache hit moves an entry to MRU so the next-oldest item is evicted."""
        paths = [f"/fake/path_{i}.mp3" for i in range(LocalMediaServer.MAX_ENTRIES - 1)]
        for i, path in enumerate(paths):
            LocalMediaServer._servers[path] = (_fake_server(), 9000 + i)

        entry = LocalMediaServer._servers.pop(paths[0])
        LocalMediaServer._servers[paths[0]] = entry

        LocalMediaServer._servers["/fake/new.mp3"] = (_fake_server(), 9099)
        LocalMediaServer._evict_oldest_if_needed()

        self.assertIn(paths[0], LocalMediaServer._servers)
        self.assertNotIn(paths[1], LocalMediaServer._servers)


class RangeRequestTests(unittest.TestCase):
    def setUp(self):
        LocalMediaServer.shutdown_all()
        LocalMediaServer._servers.clear()
        self._tmp_path = None

    def tearDown(self):
        LocalMediaServer.shutdown_all()
        LocalMediaServer._servers.clear()
        if self._tmp_path and os.path.exists(self._tmp_path):
            os.unlink(self._tmp_path)

    def _make_url(self, data: bytes) -> str:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        try:
            tmp.write(data)
        finally:
            tmp.close()
        self._tmp_path = tmp.name
        return LocalMediaServer.stream_url_for_file(self._tmp_path)

    def test_unsatisfiable_range_returns_416(self):
        """bytes=50-60 on a 10-byte file must return 416."""
        url = self._make_url(b"0123456789")
        req = urllib.request.Request(url, headers={"Range": "bytes=50-60"})

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)

        self.assertEqual(ctx.exception.code, 416)
        self.assertEqual(ctx.exception.headers.get("Content-Range"), "bytes */10")

    def test_suffix_range_returns_last_bytes(self):
        """bytes=-4 must return the final four bytes as partial content."""
        url = self._make_url(b"0123456789")
        req = urllib.request.Request(url, headers={"Range": "bytes=-4"})

        with urllib.request.urlopen(req, timeout=5) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers.get("Content-Range"), "bytes 6-9/10")
            self.assertEqual(response.read(), b"6789")


if __name__ == "__main__":
    unittest.main()
