import unittest

from el_sbobinator.generation_service import QuotaDailyLimitError, retry_with_quota


class _FakeRuntime:
    def phase(self, _): pass
    def set_effective_api_key(self, _): pass


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


if __name__ == "__main__":
    unittest.main()
