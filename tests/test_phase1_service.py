import os
import tempfile
import threading
import unittest
from unittest.mock import patch

from el_sbobinator.generation_service import QuotaDailyLimitError
from el_sbobinator.phase1_service import process_phase1_transcription


class _FakeRuntime:
    def phase(self, _): pass
    def set_work_totals(self, **_): pass
    def update_work_done(self, *_, **__): pass
    def track_temp_file(self, _): pass
    def progress(self, _): pass
    def register_step_time(self, *_, **__): pass


class Phase1SessionErrorKeyTests(unittest.TestCase):
    def test_daily_quota_records_quota_daily_limit_phase1(self):
        """QuotaDailyLimitError in phase 1 must set last_error='quota_daily_limit_phase1'."""
        session = {"stage": "phase1", "phase1": {}}

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_dir = os.path.join(tmpdir, "chunks")
            os.makedirs(chunks_dir)

            with patch("el_sbobinator.phase1_service.cut_audio_chunk_to_mp3", return_value=(True, None)), \
                 patch("el_sbobinator.phase1_service.retry_with_quota", side_effect=QuotaDailyLimitError("daily")):

                process_phase1_transcription(
                    client=object(),
                    model_name="test",
                    input_path="fake.mp3",
                    preconv_used_path=None,
                    ffmpeg_exe="ffmpeg",
                    cancel_event=threading.Event(),
                    cancelled=lambda: False,
                    start_sec=0,
                    total_duration_sec=60,
                    step_seconds=60,
                    chunk_seconds=60,
                    bitrate="48k",
                    inline_max_bytes=None,
                    prefetch_enabled=False,
                    phase1_chunks_dir=chunks_dir,
                    session=session,
                    save_session=lambda: True,
                    fallback_keys=[],
                    request_fallback_key=lambda: None,
                    system_prompt="test",
                    runtime=_FakeRuntime(),
                )

        self.assertEqual(
            session.get("last_error"),
            "quota_daily_limit_phase1",
            "session must record quota_daily_limit_phase1 when QuotaDailyLimitError is raised in phase 1",
        )


if __name__ == "__main__":
    unittest.main()
