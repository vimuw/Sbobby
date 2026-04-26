import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from el_sbobinator.utils.file_ops import (
    _html_last_gen,
    extract_html_shell,
    open_path_with_default_app,
    read_html_content,
    save_html_body_content,
)

_SHELL_HTML = (
    "<!DOCTYPE html><html><head></head><body>",
    "</body></html>",
)


def _write(path, content, generation=None):
    return save_html_body_content(
        path, content, shell=_SHELL_HTML, generation=generation
    )


def _read(path):
    with open(path, encoding="utf-8") as f:
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

        threads = [
            threading.Thread(target=save, args=(f"<p>v{i}</p>",)) for i in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        disk = _read(self.path)
        self.assertTrue(disk)  # file exists and is non-empty


class ExtractHtmlShellTests(unittest.TestCase):
    def test_valid_html_returns_tuple(self):
        html = "<!DOCTYPE html><html><head></head><body><p>Hello</p></body></html>"
        result = extract_html_shell(html)
        assert result is not None
        open_tag, close_tag = result
        self.assertIn("<body", open_tag)
        self.assertIn("</body>", close_tag)

    def test_no_body_tag_returns_none(self):
        html = "<html><p>no body tag</p></html>"
        self.assertIsNone(extract_html_shell(html))

    def test_body_with_attributes(self):
        html = '<html><body class="main"><p>content</p></body></html>'
        result = extract_html_shell(html)
        assert result is not None
        open_tag, _ = result
        self.assertIn('class="main"', open_tag)

    def test_empty_string_returns_none(self):
        self.assertIsNone(extract_html_shell(""))

    def test_only_open_body_no_close_returns_none(self):
        html = "<html><body><p>no close</p>"
        self.assertIsNone(extract_html_shell(html))


class ReadHtmlContentTests(unittest.TestCase):
    def test_reads_existing_file(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", encoding="utf-8", delete=False
        ) as f:
            f.write("<html><body>test</body></html>")
            path = f.name
        try:
            content = read_html_content(path)
            self.assertIn("test", content)
        finally:
            os.unlink(path)

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            read_html_content("/nonexistent/file.html")


class SaveHtmlBodyContentWithoutShellTests(unittest.TestCase):
    def test_reads_shell_from_file_when_not_provided(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "doc.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write("<html><body><p>original</p></body></html>")
            result = save_html_body_content(path, "<p>updated</p>", shell=None)
            self.assertTrue(result)
            with open(path, encoding="utf-8") as f:
                disk = f.read()
            self.assertIn("updated", disk)

    def test_no_body_in_file_writes_fallback_document(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "bare.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write("no body here at all")
            result = save_html_body_content(path, "<p>content</p>", shell=None)
            self.assertTrue(result)
            with open(path, encoding="utf-8") as f:
                disk = f.read()
            self.assertIn("<!DOCTYPE html>", disk)

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            save_html_body_content("/nonexistent/path.html", "<p>x</p>")

    def test_concurrent_shell_none_reads_stay_consistent(self):
        """Concurrent writers with shell=None must not see a stale shell.

        Before the fix, the file was read outside _html_write_lock, so a
        concurrent writer could replace the file between the read and the
        write, leaving the winning thread's output with a stale shell.  With
        the fix, the read happens inside the lock so both reads always observe
        the file as it stands at the moment of each writer's turn.
        """
        N = 20
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "concurrent.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    "<html><head><meta charset='utf-8'></head>"
                    "<body><p>init</p></body></html>"
                )

            barrier = threading.Barrier(N)
            errors: list[Exception] = []

            def writer(idx: int) -> None:
                try:
                    barrier.wait()
                    save_html_body_content(path, f"<p>thread-{idx}</p>", shell=None)
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=writer, args=(i,)) for i in range(N)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(errors, [], errors)
            with open(path, encoding="utf-8") as f:
                final = f.read()
            self.assertIn("<html", final)
            self.assertIn("</body>", final)
            self.assertIn("<p>thread-", final)


class OpenPathWithDefaultAppTests(unittest.TestCase):
    def test_empty_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            open_path_with_default_app("")

    def test_non_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            open_path_with_default_app(None)  # type: ignore[arg-type]

    def test_nonexistent_file_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            open_path_with_default_app("/nonexistent/really/does/not/exist.html")

    def test_disallowed_extension_raises_value_error(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            with self.assertRaises(ValueError):
                open_path_with_default_app(path)
        finally:
            os.unlink(path)

    def test_allowed_html_file_on_win32(self):
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            path = f.name
        try:
            with (
                patch.object(sys, "platform", "win32"),
                patch("os.startfile", create=True) as mock_sf,
            ):
                open_path_with_default_app(path)
                mock_sf.assert_called_once()
        finally:
            os.unlink(path)

    def test_allowed_html_file_on_darwin(self):
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            path = f.name
        try:
            with (
                patch.object(sys, "platform", "darwin"),
                patch("subprocess.Popen") as mock_popen,
            ):
                open_path_with_default_app(path)
                mock_popen.assert_called_once()
        finally:
            os.unlink(path)

    def test_url_http_on_win32(self):
        with (
            patch.object(sys, "platform", "win32"),
            patch("os.startfile", create=True) as mock_sf,
        ):
            open_path_with_default_app("http://example.com")
            mock_sf.assert_called_once_with("http://example.com")

    def test_url_https_on_darwin(self):
        with (
            patch.object(sys, "platform", "darwin"),
            patch("subprocess.Popen") as mock_popen,
        ):
            open_path_with_default_app("https://example.com")
            mock_popen.assert_called_once_with(["open", "https://example.com"])

    def test_directory_path_opens_without_extension_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.object(sys, "platform", "win32"),
                patch("os.startfile", create=True) as mock_sf,
            ):
                open_path_with_default_app(tmpdir)
                mock_sf.assert_called_once()


if __name__ == "__main__":
    unittest.main()
