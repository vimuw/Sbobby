import io
import sys
import unittest
from unittest.mock import MagicMock, call, mock_open, patch

from el_sbobinator.core.updater import download_and_install_update


class UpdaterTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

    def test_empty_string_version_returns_error(self):
        result = download_and_install_update("")
        self.assertFalse(result["ok"])
        self.assertIn("Versione", result["error"])

    def test_none_version_returns_error(self):
        result = download_and_install_update(None)  # type: ignore[arg-type]
        self.assertFalse(result["ok"])

    def test_version_v_prefix_stripped_in_filename(self):
        """'v1.2.3' must produce filename '1.2.3', not 'v1.2.3'."""
        captured: list[str] = []

        class _FakeResp:
            def read(self, n):
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        with (
            patch.object(sys, "platform", "win32"),
            patch("urllib.request.urlopen", return_value=_FakeResp()) as mock_urlopen,
            patch("builtins.open", mock_open()),
            patch("os.startfile", create=True),
            patch("threading.Thread"),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            mock_tmp.return_value.__enter__.return_value.name = "/tmp/setup.exe"
            mock_tmp.return_value.__exit__.return_value = False
            download_and_install_update("v1.2.3")
            url = mock_urlopen.call_args[0][0]
            captured.append(url)

        self.assertIn("1.2.3", captured[0])
        self.assertNotIn("vv", captured[0])
        self.assertIn("Setup-v1.2.3.exe", captured[0])

    # ------------------------------------------------------------------
    # Unsupported platform
    # ------------------------------------------------------------------

    def test_unsupported_platform_returns_error(self):
        with patch.object(sys, "platform", "linux"):
            result = download_and_install_update("1.0.0")
        self.assertFalse(result["ok"])
        self.assertIn("linux", result["error"])

    # ------------------------------------------------------------------
    # Download failure
    # ------------------------------------------------------------------

    def test_download_failure_returns_error(self):
        with (
            patch.object(sys, "platform", "win32"),
            patch("urllib.request.urlopen", side_effect=OSError("network error")),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            mock_tmp.return_value.__enter__.return_value.name = "/tmp/setup.exe"
            mock_tmp.return_value.__exit__.return_value = False
            result = download_and_install_update("1.0.0")

        self.assertFalse(result["ok"])
        self.assertIn("Download", result["error"])

    # ------------------------------------------------------------------
    # Windows happy path
    # ------------------------------------------------------------------

    def test_windows_calls_startfile_with_exe(self):
        class _FakeResp:
            def read(self, n):
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        with (
            patch.object(sys, "platform", "win32"),
            patch("urllib.request.urlopen", return_value=_FakeResp()),
            patch("builtins.open", mock_open()),
            patch("os.startfile", create=True) as mock_start,
            patch("threading.Thread") as mock_thread,
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            mock_tmp.return_value.__enter__.return_value.name = "/tmp/setup.exe"
            mock_tmp.return_value.__exit__.return_value = False
            mock_thread.return_value.start.return_value = None
            result = download_and_install_update("2.0.0")

        self.assertTrue(result["ok"])
        mock_start.assert_called_once()
        called_path = mock_start.call_args[0][0]
        self.assertTrue(called_path.endswith(".exe"))

    # ------------------------------------------------------------------
    # macOS happy path
    # ------------------------------------------------------------------

    def test_macos_happy_path_calls_subprocess_sequence(self):
        import plistlib

        fake_plist = plistlib.dumps(
            {"system-entities": [{"mount-point": "/Volumes/ElSbobinator"}]}
        )

        class _FakeResp:
            def read(self, n):
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        fake_proc = MagicMock()
        fake_proc.stdout = fake_plist
        fake_proc.returncode = 0

        call_names: list[str] = []

        def _fake_run(cmd, **kwargs):
            call_names.append(cmd[0])
            return fake_proc

        with (
            patch.object(sys, "platform", "darwin"),
            patch("urllib.request.urlopen", return_value=_FakeResp()),
            patch("builtins.open", mock_open()),
            patch("subprocess.run", side_effect=_fake_run),
            patch("subprocess.Popen"),
            patch("threading.Thread") as mock_thread,
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
            patch("os.unlink"),
        ):
            mock_tmp.return_value.__enter__.return_value.name = "/tmp/app.dmg"
            mock_tmp.return_value.__exit__.return_value = False
            mock_thread.return_value.start.return_value = None
            result = download_and_install_update("1.5.0")

        self.assertTrue(result["ok"])
        self.assertIn("hdiutil", call_names)
        self.assertIn("cp", call_names)
        self.assertIn("hdiutil", call_names)

    # ------------------------------------------------------------------
    # macOS — no mount point
    # ------------------------------------------------------------------

    def test_macos_no_mount_point_returns_error(self):
        import plistlib

        fake_plist = plistlib.dumps({"system-entities": []})

        class _FakeResp:
            def read(self, n):
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        fake_proc = MagicMock()
        fake_proc.stdout = fake_plist
        fake_proc.returncode = 0

        with (
            patch.object(sys, "platform", "darwin"),
            patch("urllib.request.urlopen", return_value=_FakeResp()),
            patch("builtins.open", mock_open()),
            patch("subprocess.run", return_value=fake_proc),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
            patch("os.unlink"),
        ):
            mock_tmp.return_value.__enter__.return_value.name = "/tmp/app.dmg"
            mock_tmp.return_value.__exit__.return_value = False
            result = download_and_install_update("1.5.0")

        self.assertFalse(result["ok"])
        self.assertIn("DMG", result["error"])


if __name__ == "__main__":
    unittest.main()
