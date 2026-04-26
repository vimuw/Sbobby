import subprocess
import unittest
from unittest.mock import MagicMock, patch

from el_sbobinator.utils.ffmpeg_utils import preconvert_to_mono16k_mp3


class PreconvertToMono16kMp3CommandTests(unittest.TestCase):
    def _captured_cmd(self, extra_kwargs=None):
        """Run preconvert_to_mono16k_mp3 with a fake runner and return the command it built."""
        captured = {}

        def fake_run(cmd, *, stop_event=None):
            captured["cmd"] = list(cmd)
            return 0, "", "", False

        with patch(
            "el_sbobinator.utils.ffmpeg_utils._run_cancellable", side_effect=fake_run
        ):
            with patch(
                "el_sbobinator.utils.ffmpeg_utils.get_ffmpeg_exe", return_value="ffmpeg"
            ):
                with patch("os.path.exists", return_value=True):
                    with patch("os.path.getsize", return_value=4096):
                        kwargs = dict(
                            input_path="lesson.mp3",
                            output_path="/tmp/out.partial.mp3",
                            bitrate="48k",
                        )
                        if extra_kwargs:
                            kwargs.update(extra_kwargs)
                        preconvert_to_mono16k_mp3(**kwargs)
        return captured.get("cmd", [])

    def test_explicit_mp3_format_flag_present_before_output_path(self):
        cmd = self._captured_cmd()
        self.assertIn("-f", cmd)
        self.assertIn("mp3", cmd)
        f_idx = cmd.index("-f")
        self.assertEqual(cmd[f_idx + 1], "mp3")
        output_idx = cmd.index("/tmp/out.partial.mp3")
        self.assertEqual(
            f_idx + 2,
            output_idx,
            "-f mp3 must be the two tokens immediately before the output path",
        )

    def test_format_flag_present_regardless_of_output_extension(self):
        cmd = self._captured_cmd({"output_path": "/tmp/out.somerandomeext"})
        f_idx = cmd.index("-f")
        self.assertEqual(cmd[f_idx + 1], "mp3")
        output_idx = cmd.index("/tmp/out.somerandomeext")
        self.assertEqual(f_idx + 2, output_idx)

    def test_chunk_cut_commands_are_not_affected(self):
        from el_sbobinator.utils.ffmpeg_utils import cut_chunk_to_mp3

        captured = {}

        def fake_run(cmd, *, stop_event=None):
            captured["cmd"] = list(cmd)
            return 0, "", "", False

        with patch(
            "el_sbobinator.utils.ffmpeg_utils._run_cancellable", side_effect=fake_run
        ):
            with patch(
                "el_sbobinator.utils.ffmpeg_utils.get_ffmpeg_exe", return_value="ffmpeg"
            ):
                with patch("os.path.exists", return_value=True):
                    with patch("os.path.getsize", return_value=4096):
                        cut_chunk_to_mp3(
                            input_path="lesson.mp3",
                            output_path="/tmp/chunk.mp3",
                            start_sec=0,
                            duration_sec=60,
                        )

        cmd = captured.get("cmd", [])
        f_indices = [i for i, tok in enumerate(cmd) if tok == "-f"]
        self.assertEqual(f_indices, [], "cut_chunk_to_mp3 must not contain -f flag")


class ProbeDurationSecondsTests(unittest.TestCase):
    def test_nonexistent_file_returns_file_not_found(self):
        from el_sbobinator.utils.ffmpeg_utils import probe_duration_seconds

        seconds, reason = probe_duration_seconds("/no/such/file.mp3")
        self.assertIsNone(seconds)
        self.assertEqual(reason, "file_non_trovato")

    def test_parses_hms_correctly(self):
        from el_sbobinator.utils.ffmpeg_utils import probe_duration_seconds

        fake_result = MagicMock()
        fake_result.stderr = b"  Duration: 01:02:03.5, start: 0"
        fake_result.stdout = b""
        fake_result.returncode = 1

        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.abspath", side_effect=lambda p: p),
            patch("subprocess.run", return_value=fake_result),
            patch(
                "el_sbobinator.utils.ffmpeg_utils.get_ffmpeg_exe", return_value="ffmpeg"
            ),
        ):
            seconds, reason = probe_duration_seconds("/fake/audio.mp3")

        assert seconds is not None
        self.assertAlmostEqual(seconds, 3723.5)
        self.assertIsNone(reason)

    def test_duration_na_returns_duration_na(self):
        from el_sbobinator.utils.ffmpeg_utils import probe_duration_seconds

        fake_result = MagicMock()
        fake_result.stderr = b"Duration: N/A, start: 0"
        fake_result.stdout = b""
        fake_result.returncode = 1

        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.abspath", side_effect=lambda p: p),
            patch("subprocess.run", return_value=fake_result),
            patch(
                "el_sbobinator.utils.ffmpeg_utils.get_ffmpeg_exe", return_value="ffmpeg"
            ),
        ):
            seconds, reason = probe_duration_seconds("/fake/audio.mp3")

        self.assertIsNone(seconds)
        self.assertEqual(reason, "duration_NA")

    def test_comma_decimal_separator(self):
        from el_sbobinator.utils.ffmpeg_utils import probe_duration_seconds

        fake_result = MagicMock()
        fake_result.stderr = b"  Duration: 00:00:10,5, start: 0"
        fake_result.stdout = b""
        fake_result.returncode = 1

        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.abspath", side_effect=lambda p: p),
            patch("subprocess.run", return_value=fake_result),
            patch(
                "el_sbobinator.utils.ffmpeg_utils.get_ffmpeg_exe", return_value="ffmpeg"
            ),
        ):
            seconds, reason = probe_duration_seconds("/fake/audio.mp3")

        assert seconds is not None
        self.assertAlmostEqual(seconds, 10.5)
        self.assertIsNone(reason)


class RunCancellableTests(unittest.TestCase):
    def test_cancel_via_stop_event_returns_was_cancelled_true(self):
        import threading

        from el_sbobinator.utils.ffmpeg_utils import _run_cancellable

        stop = threading.Event()
        stop.set()

        proc = MagicMock()
        proc.communicate.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=0.15)
        proc.poll.return_value = 0
        proc.returncode = 0

        with patch("subprocess.Popen", return_value=proc):
            rc, _out, _err, was_cancelled = _run_cancellable(
                ["echo", "hi"], stop_event=stop
            )

        self.assertTrue(was_cancelled)


class PreconvertCancelTests(unittest.TestCase):
    def test_cancel_removes_partial_output(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "out.mp3")
            with open(output_path, "wb") as fh:
                fh.write(b"partial")

            def fake_run(cmd, *, stop_event=None):
                return 0, "", "", True  # was_cancelled=True

            with (
                patch(
                    "el_sbobinator.utils.ffmpeg_utils._run_cancellable",
                    side_effect=fake_run,
                ),
                patch(
                    "el_sbobinator.utils.ffmpeg_utils.get_ffmpeg_exe",
                    return_value="ffmpeg",
                ),
            ):
                ok, reason = preconvert_to_mono16k_mp3(
                    input_path="input.mp3",
                    output_path=output_path,
                )

            self.assertFalse(ok)
            self.assertEqual(reason, "cancelled")
            self.assertFalse(os.path.exists(output_path))

    def test_ffmpeg_failure_returns_stderr_tail(self):
        def fake_run(cmd, *, stop_event=None):
            return 1, "", "some ffmpeg error\nfinal line", False

        with (
            patch(
                "el_sbobinator.utils.ffmpeg_utils._run_cancellable",
                side_effect=fake_run,
            ),
            patch(
                "el_sbobinator.utils.ffmpeg_utils.get_ffmpeg_exe", return_value="ffmpeg"
            ),
        ):
            ok, reason = preconvert_to_mono16k_mp3(
                input_path="input.mp3",
                output_path="/tmp/out.mp3",
            )

        self.assertFalse(ok)
        assert reason is not None
        self.assertIn("final line", reason)


class CutChunkStreamCopyTests(unittest.TestCase):
    def test_stream_copy_true_uses_copy_codec(self):
        from el_sbobinator.utils.ffmpeg_utils import cut_chunk_to_mp3

        captured: dict = {}

        def fake_run(cmd, *, stop_event=None):
            captured["cmd"] = list(cmd)
            return 0, "", "", False

        with (
            patch(
                "el_sbobinator.utils.ffmpeg_utils._run_cancellable",
                side_effect=fake_run,
            ),
            patch(
                "el_sbobinator.utils.ffmpeg_utils.get_ffmpeg_exe", return_value="ffmpeg"
            ),
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=4096),
        ):
            cut_chunk_to_mp3(
                input_path="lesson.mp3",
                output_path="/tmp/chunk.mp3",
                start_sec=0,
                duration_sec=60,
                stream_copy=True,
            )

        cmd = captured.get("cmd", [])
        self.assertIn("-c:a", cmd)
        self.assertIn("copy", cmd)
        self.assertNotIn("-ac", cmd)
        self.assertNotIn("-ar", cmd)


if __name__ == "__main__":
    unittest.main()
