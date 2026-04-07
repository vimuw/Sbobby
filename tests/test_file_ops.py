import os
import tempfile
import threading
import time
import unittest

from el_sbobinator.file_ops import save_html_body_content, _html_last_gen


_SHELL_HTML = (
    "<!DOCTYPE html><html><head></head><body>",
    "</body></html>",
)


def _write(path, content, generation=None):
    return save_html_body_content(path, content, shell=_SHELL_HTML, generation=generation)


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class GenerationOrderingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "doc.html")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("<html><body><p>initial</p></body></html>")
        _write(self.path, "<p>initial</p>")

    def tearDown(self):
        self._tmp.cleanup()

    # ------------------------------------------------------------------
    # Basic generation semantics
    # ------------------------------------------------------------------

    def test_no_generation_always_writes(self):
        _write(self.path, "<p>v1</p>")
        _write(self.path, "<p>v2</p>")
        self.assertIn("v2", _read(self.path))

    def test_generation_newer_wins(self):
        _write(self.path, "<p>old</p>", generation=1)
        result = _write(self.path, "<p>new</p>", generation=2)
        self.assertTrue(result)
        self.assertIn("new", _read(self.path))

    def test_generation_stale_discarded(self):
        _write(self.path, "<p>new</p>", generation=5)
        result = _write(self.path, "<p>old</p>", generation=3)
        self.assertFalse(result)
        self.assertIn("new", _read(self.path))

    def test_same_generation_discarded(self):
        _write(self.path, "<p>first</p>", generation=2)
        result = _write(self.path, "<p>second</p>", generation=2)
        self.assertFalse(result)
        self.assertIn("first", _read(self.path))

    def test_generation_none_overwrites_tracked_file(self):
        _write(self.path, "<p>gen1</p>", generation=10)
        result = _write(self.path, "<p>forced</p>", generation=None)
        self.assertTrue(result)
        self.assertIn("forced", _read(self.path))

    def test_last_gen_updated_after_write(self):
        _write(self.path, "<p>x</p>", generation=7)
        self.assertEqual(_html_last_gen.get(self.path), 7)

    # ------------------------------------------------------------------
    # Concurrent write ordering
    # ------------------------------------------------------------------

    def test_concurrent_saves_newer_generation_wins_on_disk(self):
        """Simulate two threads racing: older gen must not overwrite newer content."""
        barrier = threading.Barrier(2)
        results = {}

        def save_old():
            barrier.wait()
            time.sleep(0.02)  # arrives second under lock
            results["old"] = _write(self.path, "<p>OLD</p>", generation=1)

        def save_new():
            barrier.wait()
            results["new"] = _write(self.path, "<p>NEW</p>", generation=2)

        t1 = threading.Thread(target=save_old)
        t2 = threading.Thread(target=save_new)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        disk = _read(self.path)
        self.assertIn("NEW", disk)
        self.assertNotIn("OLD", disk)
        self.assertTrue(results["new"])
        self.assertFalse(results["old"])

    def test_concurrent_saves_no_generation_both_complete(self):
        """Without generation, both writes go through (no ordering guarantee, but no crash)."""
        barrier = threading.Barrier(2)

        def save(content):
            barrier.wait()
            _write(self.path, content)

        threads = [threading.Thread(target=save, args=(f"<p>v{i}</p>",)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        disk = _read(self.path)
        self.assertTrue(disk)  # file exists and is non-empty


if __name__ == "__main__":
    unittest.main()
