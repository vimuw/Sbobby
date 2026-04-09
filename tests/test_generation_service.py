import threading
import unittest
from unittest.mock import patch

from el_sbobinator.generation_service import (
    DegenerateOutputError,
    QuotaDailyLimitError,
    detect_degenerate_output,
    retry_with_quota,
)
from el_sbobinator.model_registry import build_model_state


class _FakeRuntime:
    def __init__(self):
        self.rotated_keys = []
        self.phase_calls: list[str] = []

    def phase(self, text):
        self.phase_calls.append(text)

    def set_effective_api_key(self, key):
        self.rotated_keys.append(key)


class _Structured503QuotaError(RuntimeError):
    def __init__(self):
        super().__init__("503 Service Unavailable")
        self.code = 503
        self.status = "RESOURCE_EXHAUSTED"
        self.message = "Token balance exhausted for this API key"
        self.details = {
            "error": {
                "code": 503,
                "status": "RESOURCE_EXHAUSTED",
                "message": "Token balance exhausted for this API key",
            }
        }


class RetryWithQuotaTests(unittest.TestCase):
    def _run(self, fn, *, max_attempts=2):
        return retry_with_quota(
            fn,
            client=object(),
            fallback_keys=[],
            model_name="test-model",
            cancelled=lambda: False,
            runtime=_FakeRuntime(),
            request_fallback_key=lambda: None,
            max_attempts=max_attempts,
            retry_sleep_seconds=0.0,
            rate_limit_sleep_seconds=0.0,
        )

    def test_plain_503_switches_to_next_model_after_quick_retry(self):
        primary_client = object()
        model_state = build_model_state(
            "gemini-2.5-flash",
            ["gemini-2.5-flash-lite"],
            "gemini-2.5-flash",
        )
        switched = []

        def fn(current_client):
            if (
                current_client is primary_client
                and model_state.current == "gemini-2.5-flash-lite"
            ):
                return "ok"
            err = RuntimeError("503 Service Unavailable")
            err.code = 503
            raise err

        client, result = retry_with_quota(
            fn,
            client=primary_client,
            fallback_keys=[],
            model_name="gemini-2.5-flash",
            model_state=model_state,
            cancelled=lambda: False,
            runtime=_FakeRuntime(),
            request_fallback_key=lambda: None,
            max_attempts=2,
            retry_sleep_seconds=0.0,
            model_unavailable_retry_delays=(0.0, 0.0),
            rate_limit_sleep_seconds=0.0,
            on_model_switched=lambda old, new: switched.append((old, new)),
        )

        self.assertIs(client, primary_client)
        self.assertEqual(result, "ok")
        self.assertEqual(model_state.current, "gemini-2.5-flash-lite")
        self.assertEqual(switched, [("gemini-2.5-flash", "gemini-2.5-flash-lite")])

    def test_model_404_switches_immediately_without_sleep(self):
        model_state = build_model_state(
            "gemini-2.5-flash",
            ["gemini-2.5-flash-lite"],
            "gemini-2.5-flash",
        )
        switched = []
        call_models = []

        def fn(_client):
            call_models.append(model_state.current)
            if model_state.current == "gemini-2.5-flash-lite":
                return "ok"
            err = RuntimeError("404 NOT_FOUND model unsupported for generateContent")
            err.code = 404
            raise err

        with patch(
            "el_sbobinator.generation_service.sleep_with_cancel",
            side_effect=AssertionError("404 must not sleep before switching model"),
        ):
            client, result = retry_with_quota(
                fn,
                client=object(),
                fallback_keys=[],
                model_name="gemini-2.5-flash",
                model_state=model_state,
                cancelled=lambda: False,
                runtime=_FakeRuntime(),
                request_fallback_key=lambda: None,
                max_attempts=1,
                retry_sleep_seconds=0.0,
                model_unavailable_retry_delays=(0.0, 0.0),
                rate_limit_sleep_seconds=0.0,
                on_model_switched=lambda old, new: switched.append((old, new)),
            )

        self.assertEqual(result, "ok")
        self.assertEqual(call_models, ["gemini-2.5-flash", "gemini-2.5-flash-lite"])
        self.assertEqual(switched, [("gemini-2.5-flash", "gemini-2.5-flash-lite")])

    def test_degenerate_output_switches_model_without_consuming_attempts(self):
        model_state = build_model_state(
            "gemini-2.5-flash",
            ["gemini-2.5-flash-lite"],
            "gemini-2.5-flash",
        )
        switched = []
        call_models = []

        def fn(_client):
            call_models.append(model_state.current)
            if model_state.current == "gemini-2.5-flash-lite":
                return "ok"
            raise DegenerateOutputError("frase ripetuta 8 volte")

        client, result = retry_with_quota(
            fn,
            client=object(),
            fallback_keys=[],
            model_name="gemini-2.5-flash",
            model_state=model_state,
            cancelled=lambda: False,
            runtime=_FakeRuntime(),
            request_fallback_key=lambda: None,
            max_attempts=1,
            retry_sleep_seconds=0.0,
            model_unavailable_retry_delays=(0.0, 0.0),
            rate_limit_sleep_seconds=0.0,
            on_model_switched=lambda old, new: switched.append((old, new)),
        )

        self.assertEqual(result, "ok")
        self.assertEqual(call_models, ["gemini-2.5-flash", "gemini-2.5-flash-lite"])
        self.assertEqual(switched, [("gemini-2.5-flash", "gemini-2.5-flash-lite")])

    def test_degenerate_output_exhausted_chain_re_raises_degenerate_error(self):
        model_state = build_model_state(
            "gemini-2.5-flash",
            ["gemini-2.5-flash-lite"],
            "gemini-2.5-flash",
        )

        def fn(_client):
            raise DegenerateOutputError("frase ripetuta 8 volte")

        with self.assertRaises(DegenerateOutputError) as ctx:
            retry_with_quota(
                fn,
                client=object(),
                fallback_keys=[],
                model_name="gemini-2.5-flash",
                model_state=model_state,
                cancelled=lambda: False,
                runtime=_FakeRuntime(),
                request_fallback_key=lambda: None,
                max_attempts=1,
                retry_sleep_seconds=0.0,
                model_unavailable_retry_delays=(0.0, 0.0),
                rate_limit_sleep_seconds=0.0,
            )

        self.assertIn("output degenerato", str(ctx.exception).lower())

    def test_plain_503_exhausted_chain_raises_clear_error(self):
        model_state = build_model_state(
            "gemini-2.5-flash",
            ["gemini-2.5-flash-lite"],
            "gemini-2.5-flash",
        )

        def fn(_client):
            err = RuntimeError("503 Service Unavailable")
            err.code = 503
            raise err

        with self.assertRaises(RuntimeError) as ctx:
            retry_with_quota(
                fn,
                client=object(),
                fallback_keys=[],
                model_name="gemini-2.5-flash",
                model_state=model_state,
                cancelled=lambda: False,
                runtime=_FakeRuntime(),
                request_fallback_key=lambda: None,
                max_attempts=2,
                retry_sleep_seconds=0.0,
                model_unavailable_retry_delays=(0.0, 0.0),
                rate_limit_sleep_seconds=0.0,
            )
        self.assertIn("fallback configurati", str(ctx.exception))

    def test_plain_503_retry_that_becomes_429_does_not_switch_model(self):
        model_state = build_model_state(
            "gemini-2.5-flash",
            ["gemini-2.5-flash-lite"],
            "gemini-2.5-flash",
        )
        call_count = 0

        def fn(_client):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                err = RuntimeError("503 Service Unavailable")
                err.code = 503
                raise err
            raise RuntimeError("429 resource_exhausted per minute")

        with self.assertRaises(RuntimeError):
            retry_with_quota(
                fn,
                client=object(),
                fallback_keys=[],
                model_name="gemini-2.5-flash",
                model_state=model_state,
                cancelled=lambda: False,
                runtime=_FakeRuntime(),
                request_fallback_key=lambda: None,
                max_attempts=2,
                retry_sleep_seconds=0.0,
                model_unavailable_retry_delays=(0.0, 0.0),
                rate_limit_sleep_seconds=0.0,
            )

        self.assertEqual(model_state.current, "gemini-2.5-flash")

    def test_rate_limit_exhausted_raises_original_not_quota_daily(self):
        """Persistent per-minute 429s must NOT raise QuotaDailyLimitError
        and must not trigger fallback-key acquisition."""
        fallback_key_calls = []

        def fn(_client):
            raise RuntimeError("429 resource_exhausted per minute threshold")

        with self.assertRaises(RuntimeError) as ctx:
            retry_with_quota(
                fn,
                client=object(),
                fallback_keys=[],
                model_name="test-model",
                cancelled=lambda: False,
                runtime=_FakeRuntime(),
                request_fallback_key=lambda: fallback_key_calls.append(1) or None,
                max_attempts=2,
                retry_sleep_seconds=0.0,
                rate_limit_sleep_seconds=0.0,
            )
        self.assertNotIsInstance(ctx.exception, QuotaDailyLimitError)
        self.assertEqual(
            fallback_key_calls,
            [],
            "request_fallback_key must not be called for minute-scoped rate limits",
        )

    def test_daily_quota_still_raises_quota_daily_limit_error(self):
        """True daily-quota errors must still raise QuotaDailyLimitError."""

        def fn(_client):
            raise RuntimeError("429 quota exceeded daily limit per day")

        with self.assertRaises(QuotaDailyLimitError):
            self._run(fn)

    def test_rate_limit_retries_before_giving_up(self):
        """Rate-limit path must exhaust all attempts before raising."""
        call_count = 0

        def fn(_client):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("429 resource_exhausted per minute")

        with self.assertRaises(RuntimeError):
            self._run(fn, max_attempts=3)
        self.assertEqual(call_count, 3)

    def test_structured_503_exhausted_key_rotates_to_fallback_without_sleep_retry(self):
        runtime = _FakeRuntime()
        rotated_client = object()
        call_clients = []

        def fn(current_client):
            call_clients.append(current_client)
            if current_client is rotated_client:
                return "ok"
            raise _Structured503QuotaError()

        with (
            patch(
                "el_sbobinator.generation_service.try_rotate_key",
                return_value=(rotated_client, True, "fallback-key"),
            ) as mock_rotate,
            patch(
                "el_sbobinator.generation_service.sleep_with_cancel",
                side_effect=AssertionError(
                    "503 exhausted-key path must rotate immediately, not sleep-retry"
                ),
            ),
        ):
            client, result = retry_with_quota(
                fn,
                client=object(),
                fallback_keys=["fallback-key"],
                model_name="test-model",
                cancelled=lambda: False,
                runtime=runtime,
                request_fallback_key=lambda: None,
                max_attempts=2,
                retry_sleep_seconds=0.0,
                rate_limit_sleep_seconds=0.0,
            )

        self.assertIs(client, rotated_client)
        self.assertEqual(result, "ok")
        self.assertEqual(runtime.rotated_keys, ["fallback-key"])
        self.assertEqual(len(call_clients), 2)
        mock_rotate.assert_called_once()

    def test_structured_503_exhausted_key_without_fallback_raises_quota_error(self):
        with self.assertRaises(QuotaDailyLimitError):
            retry_with_quota(
                lambda _client: (_ for _ in ()).throw(_Structured503QuotaError()),
                client=object(),
                fallback_keys=[],
                model_name="test-model",
                cancelled=lambda: False,
                runtime=_FakeRuntime(),
                request_fallback_key=lambda: None,
                max_attempts=2,
                retry_sleep_seconds=0.0,
                rate_limit_sleep_seconds=0.0,
            )

    def test_plain_503_without_quota_signal_uses_generic_retry(self):
        call_count = 0

        def fn(_client):
            nonlocal call_count
            call_count += 1
            err = RuntimeError("503 Service Unavailable")
            err.code = 503
            raise err

        with patch("el_sbobinator.generation_service.try_rotate_key") as mock_rotate:
            with self.assertRaises(RuntimeError):
                self._run(fn, max_attempts=2)

        self.assertEqual(call_count, 2)
        mock_rotate.assert_not_called()

    def test_cancelled_quota_error_does_not_rotate_or_request_new_key(self):
        runtime = _FakeRuntime()
        client = object()
        cancel_event = __import__("threading").Event()
        fallback_keys = ["fallback-key-1", "fallback-key-2"]
        fallback_key_calls = []

        def fn(_client):
            cancel_event.set()
            raise RuntimeError("429 quota exceeded daily limit per day")

        with patch(
            "el_sbobinator.generation_service.try_rotate_key",
            side_effect=AssertionError(
                "La rotazione non deve partire dopo l'annullamento"
            ),
        ):
            returned_client, result = retry_with_quota(
                fn,
                client=client,
                fallback_keys=fallback_keys,
                model_name="test-model",
                cancelled=cancel_event.is_set,
                runtime=runtime,
                request_fallback_key=lambda: fallback_key_calls.append(1) or None,
                max_attempts=2,
                retry_sleep_seconds=0.0,
                rate_limit_sleep_seconds=0.0,
            )

        self.assertIs(returned_client, client)
        self.assertIsNone(result)
        self.assertEqual(runtime.rotated_keys, [])
        self.assertEqual(fallback_key_calls, [])
        self.assertEqual(fallback_keys, ["fallback-key-1", "fallback-key-2"])

    def test_cancel_during_fallback_validation_keeps_key_available(self):
        runtime = _FakeRuntime()
        client = object()
        cancel_event = threading.Event()
        fallback_keys = ["fallback-key-1"]

        class _ValidModels:
            def get(self, model=None, **kwargs):
                cancel_event.set()
                return {"model": model}

        class _ValidClient:
            def __init__(self, api_key=None, **kwargs):
                self.api_key = api_key
                self.models = _ValidModels()

        def fn(_client):
            raise RuntimeError("429 quota exceeded daily limit per day")

        with patch("el_sbobinator.generation_service.genai.Client", _ValidClient):
            returned_client, result = retry_with_quota(
                fn,
                client=client,
                fallback_keys=fallback_keys,
                model_name="test-model",
                cancelled=cancel_event.is_set,
                runtime=runtime,
                request_fallback_key=lambda: None,
                max_attempts=2,
                retry_sleep_seconds=0.0,
                rate_limit_sleep_seconds=0.0,
            )

        self.assertIs(returned_client, client)
        self.assertIsNone(result)
        self.assertEqual(runtime.rotated_keys, [])
        self.assertEqual(fallback_keys, ["fallback-key-1"])

    def test_detect_degenerate_output_flags_repeated_paragraphs(self):
        paragraph = "La ventilazione alveolare regola gli scambi gassosi in modo continuo durante tutta la respirazione."
        text = "\n\n".join([paragraph] * 4)
        self.assertIn("paragrafo ripetuto", detect_degenerate_output(text) or "")

    def test_detect_degenerate_output_flags_repeated_sentences(self):
        sentence = "E allora l'emoglobina cede piu facilmente l'ossigeno."
        text = " ".join([sentence] * 8)
        self.assertIn("frase ripetuta", detect_degenerate_output(text) or "")

    def test_503_phase_restored_after_switch_to_fallback(self):
        """503 retry 1/2 then retry 2/2 → switch model: each wait is followed by phase restore."""
        model_state = build_model_state(
            "gemini-2.5-flash", ["gemini-2.5-flash-lite"], "gemini-2.5-flash"
        )
        rt = _FakeRuntime()

        def fn(current_client):
            err = RuntimeError("503 Service Unavailable")
            err.code = 503
            raise err

        with self.assertRaises(RuntimeError):
            retry_with_quota(
                fn,
                client=object(),
                fallback_keys=[],
                model_name="gemini-2.5-flash",
                model_state=model_state,
                cancelled=lambda: False,
                runtime=rt,
                request_fallback_key=lambda: None,
                max_attempts=2,
                retry_sleep_seconds=0.0,
                model_unavailable_retry_delays=(0.0, 0.0),
                resume_phase_text="Fase 1/3: trascrizione (chunk 1/5)",
            )

        resume_text = "Fase 1/3: trascrizione (chunk 1/5)"
        wait1 = "Modello non disponibile: attesa 0s... (retry 1/2)"
        wait2 = "Modello non disponibile: attesa 0s... (retry 2/2)"
        self.assertIn(wait1, rt.phase_calls)
        self.assertIn(wait2, rt.phase_calls)
        self.assertIn(resume_text, rt.phase_calls)
        first_wait1 = rt.phase_calls.index(wait1)
        first_resume = rt.phase_calls.index(resume_text)
        self.assertGreater(
            first_resume,
            first_wait1,
            "resume phase must appear after first wait message",
        )
        first_wait2 = rt.phase_calls.index(wait2)
        second_resume = rt.phase_calls.index(resume_text, first_wait2)
        self.assertGreater(
            second_resume,
            first_wait2,
            "resume phase must appear after second wait message",
        )

    def test_rate_limit_phase_restored_after_wait(self):
        """After rate-limit sleep, runtime.phase() receives the resume text
        before the next callable_fn() attempt."""
        rt = _FakeRuntime()
        call_count = [0]

        def fn(current_client):
            call_count[0] += 1
            if call_count[0] == 1:
                err = RuntimeError("429 Too Many Requests per minute")
                err.code = 429
                raise err
            return "ok"

        _, result = retry_with_quota(
            fn,
            client=object(),
            fallback_keys=[],
            model_name="test-model",
            cancelled=lambda: False,
            runtime=rt,
            request_fallback_key=lambda: None,
            max_attempts=3,
            retry_sleep_seconds=0.0,
            rate_limit_sleep_seconds=0.0,
            resume_phase_text="Fase 2/3: revisione (1/4)",
        )

        self.assertEqual(result, "ok")
        self.assertIn("⏳ Rate limit: attesa 65s...", rt.phase_calls)
        self.assertIn("Fase 2/3: revisione (1/4)", rt.phase_calls)
        wait_idx = rt.phase_calls.index("⏳ Rate limit: attesa 65s...")
        resume_idx = rt.phase_calls.index("Fase 2/3: revisione (1/4)")
        self.assertGreater(resume_idx, wait_idx)

    def test_503_third_attempt_succeeds_without_model_switch(self):
        """503×2 (original + retry 1) → success on retry 2: no model switch, 3 total calls."""
        model_state = build_model_state(
            "gemini-2.5-flash", ["gemini-2.5-flash-lite"], "gemini-2.5-flash"
        )
        switched = []
        call_count = [0]

        def fn(_client):
            call_count[0] += 1
            if call_count[0] <= 2:
                err = RuntimeError("503 Service Unavailable")
                err.code = 503
                raise err
            return "ok"

        client, result = retry_with_quota(
            fn,
            client=object(),
            fallback_keys=[],
            model_name="gemini-2.5-flash",
            model_state=model_state,
            cancelled=lambda: False,
            runtime=_FakeRuntime(),
            request_fallback_key=lambda: None,
            max_attempts=2,
            retry_sleep_seconds=0.0,
            model_unavailable_retry_delays=(0.0, 0.0),
            rate_limit_sleep_seconds=0.0,
            on_model_switched=lambda old, new: switched.append((old, new)),
        )

        self.assertEqual(result, "ok")
        self.assertEqual(call_count[0], 3)
        self.assertEqual(model_state.current, "gemini-2.5-flash")
        self.assertEqual(
            switched,
            [],
            "no model switch must occur when success before retry budget exhausted",
        )

    def test_503_all_retries_exhausted_then_switches_model(self):
        """503×3 (original + retry 1 + retry 2) → switch to fallback, which succeeds."""
        model_state = build_model_state(
            "gemini-2.5-flash", ["gemini-2.5-flash-lite"], "gemini-2.5-flash"
        )
        switched = []
        call_count = [0]

        def fn(_client):
            call_count[0] += 1
            if model_state.current == "gemini-2.5-flash":
                err = RuntimeError("503 Service Unavailable")
                err.code = 503
                raise err
            return "ok"

        client, result = retry_with_quota(
            fn,
            client=object(),
            fallback_keys=[],
            model_name="gemini-2.5-flash",
            model_state=model_state,
            cancelled=lambda: False,
            runtime=_FakeRuntime(),
            request_fallback_key=lambda: None,
            max_attempts=2,
            retry_sleep_seconds=0.0,
            model_unavailable_retry_delays=(0.0, 0.0),
            rate_limit_sleep_seconds=0.0,
            on_model_switched=lambda old, new: switched.append((old, new)),
        )

        self.assertEqual(result, "ok")
        self.assertEqual(call_count[0], 4, "3 calls with flash + 1 with flash-lite")
        self.assertEqual(model_state.current, "gemini-2.5-flash-lite")
        self.assertEqual(switched, [("gemini-2.5-flash", "gemini-2.5-flash-lite")])

    def test_503_two_waits_phase_restore_interleaved(self):
        """With two retry delays the phase sequence must be:
        wait1 → restore → wait2 → restore (→ switch or success)."""
        model_state = build_model_state(
            "gemini-2.5-flash", ["gemini-2.5-flash-lite"], "gemini-2.5-flash"
        )
        rt = _FakeRuntime()
        call_count = [0]

        def fn(_client):
            call_count[0] += 1
            if call_count[0] <= 2:
                err = RuntimeError("503 Service Unavailable")
                err.code = 503
                raise err
            return "ok"

        retry_with_quota(
            fn,
            client=object(),
            fallback_keys=[],
            model_name="gemini-2.5-flash",
            model_state=model_state,
            cancelled=lambda: False,
            runtime=rt,
            request_fallback_key=lambda: None,
            max_attempts=2,
            retry_sleep_seconds=0.0,
            model_unavailable_retry_delays=(0.0, 0.0),
            rate_limit_sleep_seconds=0.0,
            resume_phase_text="Fase 1/3: trascrizione (chunk 3/10)",
        )

        wait1 = "Modello non disponibile: attesa 0s... (retry 1/2)"
        wait2 = "Modello non disponibile: attesa 0s... (retry 2/2)"
        restore = "Fase 1/3: trascrizione (chunk 3/10)"
        self.assertIn(wait1, rt.phase_calls)
        self.assertIn(wait2, rt.phase_calls)
        self.assertIn(restore, rt.phase_calls)
        idx_w1 = rt.phase_calls.index(wait1)
        idx_r1 = rt.phase_calls.index(restore)
        idx_w2 = rt.phase_calls.index(wait2)
        idx_r2 = rt.phase_calls.index(restore, idx_w2)
        self.assertLess(idx_w1, idx_r1)
        self.assertLess(idx_r1, idx_w2)
        self.assertLess(idx_w2, idx_r2)

    def test_503_cancel_during_second_retry_sleep_returns_none_no_switch(self):
        """If cancel fires during the second 503 sleep, returns (client, None) without switching model."""
        model_state = build_model_state(
            "gemini-2.5-flash", ["gemini-2.5-flash-lite"], "gemini-2.5-flash"
        )
        switched = []
        sleep_call = [0]
        original_client = object()

        def fn(_client):
            err = RuntimeError("503 Service Unavailable")
            err.code = 503
            raise err

        def mock_sleep(cancelled_fn, seconds):
            sleep_call[0] += 1
            if sleep_call[0] >= 2:
                return False
            return True

        with patch(
            "el_sbobinator.generation_service.sleep_with_cancel", side_effect=mock_sleep
        ):
            returned_client, result = retry_with_quota(
                fn,
                client=original_client,
                fallback_keys=[],
                model_name="gemini-2.5-flash",
                model_state=model_state,
                cancelled=lambda: False,
                runtime=_FakeRuntime(),
                request_fallback_key=lambda: None,
                max_attempts=2,
                retry_sleep_seconds=0.0,
                model_unavailable_retry_delays=(0.0, 0.0),
                rate_limit_sleep_seconds=0.0,
                on_model_switched=lambda old, new: switched.append((old, new)),
            )

        self.assertIsNone(result)
        self.assertIs(returned_client, original_client)
        self.assertEqual(
            switched, [], "model must not switch when cancel fires during sleep"
        )
        self.assertEqual(model_state.current, "gemini-2.5-flash")

    def test_503_inner_retry_raises_429_reraises_429_not_503(self):
        """Regression: when the inner 503-model-unavailable retry loop encounters a
        minute-scoped 429 and breaks, the terminal `raise exc` must surface the 429,
        not the original outer 503 that `sys.exc_info()` still holds."""
        model_state = build_model_state(
            "gemini-2.5-flash",
            ["gemini-2.5-flash-lite"],
            "gemini-2.5-flash",
        )
        call_count = [0]

        def fn(_client):
            call_count[0] += 1
            if call_count[0] <= 3:
                err = RuntimeError("429 Too Many Requests per minute")
                err.code = 429
                raise err
            if call_count[0] == 4:
                err = RuntimeError("503 Service Unavailable")
                err.code = 503
                raise err
            err = RuntimeError("429 Too Many Requests per minute")
            err.code = 429
            raise err

        with self.assertRaises(RuntimeError) as ctx:
            retry_with_quota(
                fn,
                client=object(),
                fallback_keys=[],
                model_name="gemini-2.5-flash",
                model_state=model_state,
                cancelled=lambda: False,
                runtime=_FakeRuntime(),
                request_fallback_key=lambda: None,
                max_attempts=4,
                retry_sleep_seconds=0.0,
                model_unavailable_retry_delays=(0.0,),
                rate_limit_sleep_seconds=0.0,
            )

        self.assertNotIsInstance(ctx.exception, QuotaDailyLimitError)
        self.assertIn("429", str(ctx.exception))
        self.assertEqual(getattr(ctx.exception, "code", None), 429)
        self.assertNotIn("503", str(ctx.exception))
        self.assertEqual(model_state.current, "gemini-2.5-flash")


if __name__ == "__main__":
    unittest.main()
