import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_release.py"
_SPEC = importlib.util.spec_from_file_location("build_release_module", _MODULE_PATH)
assert _SPEC is not None
build_release = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(build_release)


class BuildReleaseTests(unittest.TestCase):
    def test_postbuild_smoke_fails_when_artifact_is_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(build_release, "ROOT", Path(tmpdir)):
                with self.assertRaises(FileNotFoundError):
                    build_release.run_postbuild_smoke("windows")

    def test_postbuild_smoke_runs_smoke_script_when_artifact_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "dist" / build_release.APP_NAME
            artifact_dir.mkdir(parents=True, exist_ok=True)
            inner_exe = artifact_dir / f"{build_release.APP_NAME}.exe"
            inner_exe.write_bytes(b"ok")

            with (
                patch.object(build_release, "ROOT", root),
                patch.object(build_release, "run") as mock_run,
            ):
                build_release.run_postbuild_smoke("windows")

            mock_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
