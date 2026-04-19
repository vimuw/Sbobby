import os
import tempfile
import threading
import unittest
from unittest.mock import patch

from el_sbobinator.generation_service import (
    AllModelsUnavailableError,
    DegenerateOutputError,
    QuotaDailyLimitError,
)
from el_sbobinator.model_registry import build_model_state
from el_sbobinator.phase1_service import process_phase1_transcription


class _FakeRuntime:
    def phase(self, _):
        pass

    def set_work_totals(self, **_):
        pass

    def update_work_done(self, *_, **__):
        pass

    def track_temp_file(self, _):
        pass

    def progress(self, _):
        pass

    def register_step_time(self, *_, **__):
        pass


class Phase1SessionErrorKeyTests(unittest.TestCase):
    def test_daily_quota_records_quota_daily_limit_phase1(self):
        """QuotaDailyLimitError in phase 1 must set last_error='quota_daily_limit_phase1'."""
        session = {"stage": "phase1", "phase1": {}}

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_dir = os.path.join(tmpdir, "chunks")
            os.makedirs(chunks_dir)

            with (
                patch(
                    "el_sbobinator.phase1_service.cut_audio_chunk_to_mp3",
                    return_value=(True, None),
                ),
                patch(
                    "el_sbobinator.phase1_service.retry_with_quota",
                    side_effect=QuotaDailyLimitError("daily"),
                ),
            ):
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

    def test_degenerate_output_stops_without_saving_chunk(self):
        session = {"stage": "phase1", "phase1": {}}

        class _Response:
            text = (
                "E allora l'emoglobina cede piu facilmente l'ossigeno. " * 8
            ).strip()

        class _Models:
            def generate_content(self, **_kwargs):
                return _Response()

        class _Client:
            def __init__(self):
                self.models = _Models()

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_dir = os.path.join(tmpdir, "chunks")
            os.makedirs(chunks_dir)

            with (
                patch(
                    "el_sbobinator.phase1_service.cut_audio_chunk_to_mp3",
                    return_value=(True, None),
                ),
                patch(
                    "el_sbobinator.phase1_service.generation_service.make_inline_audio_part",
                    return_value=object(),
                ),
                patch(
                    "el_sbobinator.phase1_service.retry_with_quota",
                    side_effect=lambda fn, **kwargs: (
                        kwargs["client"],
                        fn(kwargs["client"]),
                    ),
                ),
            ):
                _client, transcript, _prev = process_phase1_transcription(
                    client=_Client(),
                    model_name="gemini-2.5-flash",
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

            self.assertIsNone(transcript)
            self.assertEqual(session.get("last_error"), "phase1_degenerate_output")
            self.assertEqual(os.listdir(chunks_dir), [])

    def test_degenerate_output_chain_exhaustion_sets_specific_last_error(self):
        session = {"stage": "phase1", "phase1": {}}

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_dir = os.path.join(tmpdir, "chunks")
            os.makedirs(chunks_dir)

            with (
                patch(
                    "el_sbobinator.phase1_service.cut_audio_chunk_to_mp3",
                    return_value=(True, None),
                ),
                patch(
                    "el_sbobinator.phase1_service.generation_service.make_inline_audio_part",
                    return_value=object(),
                ),
                patch(
                    "el_sbobinator.phase1_service.retry_with_quota",
                    side_effect=__import__(
                        "el_sbobinator.generation_service",
                        fromlist=["DegenerateOutputError"],
                    ).DegenerateOutputError(
                        "Tutti i modelli della chain hanno prodotto output degenerato o non valido."
                    ),
                ),
            ):
                _client, transcript, _prev = process_phase1_transcription(
                    client=object(),
                    model_name="gemini-2.5-flash",
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

            self.assertIsNone(transcript)
            self.assertEqual(session.get("last_error"), "phase1_degenerate_output")
            self.assertEqual(os.listdir(chunks_dir), [])


class ChainExhaustionRecoveryTests(unittest.TestCase):
    _COMMON_KWARGS = dict(
        input_path="fake.mp3",
        preconv_used_path=None,
        ffmpeg_exe="ffmpeg",
        cancel_event=None,
        cancelled=lambda: False,
        start_sec=0,
        total_duration_sec=60,
        step_seconds=60,
        chunk_seconds=60,
        bitrate="48k",
        inline_max_bytes=None,
        prefetch_enabled=False,
        system_prompt="test",
        fallback_keys=[],
        request_fallback_key=lambda: None,
    )

    def _run(
        self, session, chunks_dir, retry_side_effect, model_state=None, switched=None
    ):
        call_count = [0]
        effects = list(retry_side_effect) if not callable(retry_side_effect) else None

        def fake_retry(fn, **kwargs):
            call_count[0] += 1
            if effects is not None:
                effect = effects[min(call_count[0] - 1, len(effects) - 1)]
            else:
                effect = retry_side_effect(call_count[0])
            if isinstance(effect, BaseException):
                raise effect
            return kwargs["client"], effect

        on_switched = (
            (lambda old, new: switched.append((old, new)))
            if switched is not None
            else None
        )

        with (
            patch(
                "el_sbobinator.phase1_service.cut_audio_chunk_to_mp3",
                return_value=(True, None),
            ),
            patch(
                "el_sbobinator.phase1_service.generation_service.make_inline_audio_part",
                return_value=object(),
            ),
            patch(
                "el_sbobinator.phase1_service.retry_with_quota", side_effect=fake_retry
            ),
        ):
            return process_phase1_transcription(  # type: ignore[arg-type]
                client=object(),
                model_name="gemini-2.5-flash",
                model_state=model_state,
                phase1_chunks_dir=chunks_dir,
                session=session,
                save_session=lambda: True,
                runtime=_FakeRuntime(),
                on_model_switched=on_switched,
                **self._COMMON_KWARGS,  # type: ignore[arg-type]
            ), call_count[0]

    def test_recovery_succeeds_on_extra_pass(self):
        """retry_with_quota exhausts the full model chain (DegenerateOutputError). Outer
        recovery resets model_state to primary and retries the chunk one more time.
        Extra pass returns valid output: one chunk saved, last_error absent."""
        session = {"stage": "phase1", "phase1": {}}
        switched = []
        model_state = build_model_state(
            "gemini-2.5-flash", ["gemini-2.5-flash-lite"], "gemini-2.5-flash-lite"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_dir = os.path.join(tmpdir, "chunks")
            os.makedirs(chunks_dir)

            (_, transcript, _), calls = self._run(
                session,
                chunks_dir,
                retry_side_effect=[
                    DegenerateOutputError("chain esaurita"),
                    "testo valido trascritto",
                ],
                model_state=model_state,
                switched=switched,
            )

            self.assertIsNotNone(transcript)
            self.assertIsNone(session.get("last_error"))
            self.assertEqual(len(os.listdir(chunks_dir)), 1)
            self.assertEqual(calls, 2)
            self.assertEqual(model_state.current, "gemini-2.5-flash")
            self.assertIn(("gemini-2.5-flash-lite", "gemini-2.5-flash"), switched)

    def test_recovery_extra_pass_also_exhausted_stops_job(self):
        """retry_with_quota exhausts the chain twice: once in the initial call and once
        in the outer recovery pass. No chunk saved, last_error='phase1_degenerate_output'."""
        session = {"stage": "phase1", "phase1": {}}

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_dir = os.path.join(tmpdir, "chunks")
            os.makedirs(chunks_dir)

            (_, transcript, _), calls = self._run(
                session,
                chunks_dir,
                retry_side_effect=[
                    DegenerateOutputError("chain esaurita prima volta"),
                    DegenerateOutputError("chain esaurita seconda volta"),
                ],
            )

            self.assertIsNone(transcript)
            self.assertEqual(session.get("last_error"), "phase1_degenerate_output")
            self.assertEqual(os.listdir(chunks_dir), [])
            self.assertEqual(calls, 2)

    def test_recovery_no_model_switch_callback_when_already_primary(self):
        """If model_state.current is already the primary when the chain is exhausted,
        the outer recovery resets the model but does NOT fire on_model_switched."""
        session = {"stage": "phase1", "phase1": {}}
        switched = []
        model_state = build_model_state("gemini-2.5-flash", [], "gemini-2.5-flash")

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_dir = os.path.join(tmpdir, "chunks")
            os.makedirs(chunks_dir)

            self._run(
                session,
                chunks_dir,
                retry_side_effect=[
                    DegenerateOutputError("chain esaurita"),
                    "testo valido trascritto",
                ],
                model_state=model_state,
                switched=switched,
            )

            self.assertEqual(switched, [])

    def test_recovery_extra_pass_503_switches_to_fallback_then_success(self):
        """Chain exhausted (fallback was active) → outer recovery resets to primary.
        Extra pass: primary gets 503 and retry_with_quota internally switches to fallback,
        returning valid output. Chunk saved, last_error absent."""
        session = {"stage": "phase1", "phase1": {}}
        switched = []
        # Start with fallback already active (prior 503 moved the model during this session)
        model_state = build_model_state(
            "gemini-2.5-flash", ["gemini-2.5-flash-lite"], "gemini-2.5-flash-lite"
        )

        call_count = [0]

        def fake_retry(fn, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First attempt: degenerate output exhausted the whole chain
                raise DegenerateOutputError(
                    "tutti i modelli hanno prodotto output degenerato"
                )
            # Second attempt (after recovery reset to primary):
            # simulate primary 503 → retry_with_quota switches to fallback internally
            ms = kwargs.get("model_state")
            if ms is not None:
                old = ms.current
                ms.current = "gemini-2.5-flash-lite"
                on_sw = kwargs.get("on_model_switched")
                if on_sw is not None and old != "gemini-2.5-flash-lite":
                    on_sw(old, "gemini-2.5-flash-lite")
            return kwargs["client"], "testo valido trascritto via fallback"

        saved_chunks = []
        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_dir = os.path.join(tmpdir, "chunks")
            os.makedirs(chunks_dir)

            with (
                patch(
                    "el_sbobinator.phase1_service.cut_audio_chunk_to_mp3",
                    return_value=(True, None),
                ),
                patch(
                    "el_sbobinator.phase1_service.generation_service.make_inline_audio_part",
                    return_value=object(),
                ),
                patch(
                    "el_sbobinator.phase1_service.retry_with_quota",
                    side_effect=fake_retry,
                ),
            ):
                _client, transcript, _prev = process_phase1_transcription(  # type: ignore[arg-type]
                    client=object(),
                    model_name="gemini-2.5-flash",
                    model_state=model_state,
                    phase1_chunks_dir=chunks_dir,
                    session=session,
                    save_session=lambda: True,
                    runtime=_FakeRuntime(),
                    on_model_switched=lambda old, new: switched.append((old, new)),
                    **self._COMMON_KWARGS,  # type: ignore[arg-type]
                )

            saved_chunks = os.listdir(chunks_dir)

        self.assertIsNotNone(transcript)
        self.assertIsNone(session.get("last_error"))
        self.assertEqual(len(saved_chunks), 1)
        self.assertEqual(call_count[0], 2)
        self.assertEqual(model_state.current, "gemini-2.5-flash-lite")
        # recovery: lite→flash; then 503 fallback: flash→lite
        self.assertIn(("gemini-2.5-flash-lite", "gemini-2.5-flash"), switched)
        self.assertIn(("gemini-2.5-flash", "gemini-2.5-flash-lite"), switched)

    def test_recovery_rebuilds_chunk_audio_for_each_pass(self):
        """cut_audio_chunk_to_mp3 and make_inline_audio_part must each be called once
        per outer-loop pass — twice total when the chain-exhaustion recovery fires —
        proving the chunk audio context is fully reconstructed before the extra pass."""
        from unittest.mock import MagicMock

        session = {"stage": "phase1", "phase1": {}}
        cut_mock = MagicMock(return_value=(True, None))
        inline_mock = MagicMock(return_value=object())
        call_count = [0]

        def fake_retry(fn, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise DegenerateOutputError("chain esaurita")
            return kwargs["client"], "testo valido trascritto"

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_dir = os.path.join(tmpdir, "chunks")
            os.makedirs(chunks_dir)

            with (
                patch("el_sbobinator.phase1_service.cut_audio_chunk_to_mp3", cut_mock),
                patch(
                    "el_sbobinator.phase1_service.generation_service.make_inline_audio_part",
                    inline_mock,
                ),
                patch(
                    "el_sbobinator.phase1_service.retry_with_quota",
                    side_effect=fake_retry,
                ),
            ):
                process_phase1_transcription(  # type: ignore[arg-type]
                    client=object(),
                    model_name="gemini-2.5-flash",
                    phase1_chunks_dir=chunks_dir,
                    session=session,
                    save_session=lambda: True,
                    runtime=_FakeRuntime(),
                    **self._COMMON_KWARGS,  # type: ignore[arg-type]
                )

        self.assertEqual(
            cut_mock.call_count, 2, "chunk audio must be re-cut on each attempt"
        )
        self.assertEqual(
            inline_mock.call_count,
            2,
            "inline audio part must be rebuilt on each attempt",
        )

    def test_all_models_unavailable_triggers_recovery_then_succeeds(self):
        """Compound failure: AllModelsUnavailableError (all 503) triggers the same
        chain-exhaustion recovery as DegenerateOutputError.  Second attempt succeeds:
        one chunk saved, last_error absent."""
        session = {"stage": "phase1", "phase1": {}}
        switched = []
        model_state = build_model_state(
            "gemini-2.5-flash", ["gemini-2.5-flash-lite"], "gemini-2.5-flash-lite"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_dir = os.path.join(tmpdir, "chunks")
            os.makedirs(chunks_dir)

            (_, transcript, _), calls = self._run(
                session,
                chunks_dir,
                retry_side_effect=[
                    AllModelsUnavailableError("tutti i modelli 503"),
                    "testo valido trascritto",
                ],
                model_state=model_state,
                switched=switched,
            )

            self.assertIsNotNone(transcript)
            self.assertIsNone(session.get("last_error"))
            self.assertEqual(len(os.listdir(chunks_dir)), 1)
            self.assertEqual(calls, 2)
            self.assertEqual(model_state.current, "gemini-2.5-flash")
            self.assertIn(("gemini-2.5-flash-lite", "gemini-2.5-flash"), switched)

    def test_all_models_unavailable_twice_sets_specific_error(self):
        """AllModelsUnavailableError on both the initial attempt and the recovery pass:
        transcript is None, last_error='phase1_all_models_unavailable'."""
        session = {"stage": "phase1", "phase1": {}}

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_dir = os.path.join(tmpdir, "chunks")
            os.makedirs(chunks_dir)

            (_, transcript, _), calls = self._run(
                session,
                chunks_dir,
                retry_side_effect=[
                    AllModelsUnavailableError("tutti i modelli 503 - prima volta"),
                    AllModelsUnavailableError("tutti i modelli 503 - seconda volta"),
                ],
            )

            self.assertIsNone(transcript)
            self.assertEqual(session.get("last_error"), "phase1_all_models_unavailable")
            self.assertEqual(os.listdir(chunks_dir), [])
            self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
