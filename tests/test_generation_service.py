import unittest
import threading
from unittest.mock import patch

from el_sbobinator.generation_service import QuotaDailyLimitError, retry_with_quota


class _FakeRuntime:
    def __init__(self):
        self.rotated_keys = []

    def phase(self, _): pass

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
            fallback_key_calls, [],
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

        with patch(
            "el_sbobinator.generation_service.try_rotate_key",
            return_value=(rotated_client, True, "fallback-key"),
        ) as mock_rotate, patch(
            "el_sbobinator.generation_service.sleep_with_cancel",
            side_effect=AssertionError("503 exhausted-key path must rotate immediately, not sleep-retry"),
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
            side_effect=AssertionError("La rotazione non deve partire dopo l'annullamento"),
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


if __name__ == "__main__":
    unittest.main()
