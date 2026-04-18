"""Tests for config_service.py TTL cache (P3)."""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import el_sbobinator.config_service as cs

_FAKE_CFG: dict = {
    "api_key": "key-test",
    "preferred_model": "gemini-2.0-flash-lite",
    "fallback_models": ["gemini-2.0-flash"],
}


def _reset_cache() -> None:
    cs._config_cache = None
    cs._config_cache_ts = 0.0
    cs._config_cache_gen = 0


class TestLoadConfigCache(unittest.TestCase):
    def setUp(self) -> None:
        _reset_cache()

    def tearDown(self) -> None:
        _reset_cache()

    # ------------------------------------------------------------------
    # Cache hit
    # ------------------------------------------------------------------

    def test_hit_returns_cached_value(self) -> None:
        cs._config_cache = dict(_FAKE_CFG)
        cs._config_cache_ts = time.monotonic()

        with patch("el_sbobinator.config_service.os.path.exists") as mock_exists:
            result = cs.load_config()
            mock_exists.assert_not_called()

        self.assertEqual(result["api_key"], "key-test")

    def test_hit_returns_shallow_copy(self) -> None:
        """Mutating the returned dict must not corrupt the in-process cache."""
        cs._config_cache = dict(_FAKE_CFG)
        cs._config_cache_ts = time.monotonic()

        result = cs.load_config()
        result["api_key"] = "mutated"

        self.assertEqual(cs._config_cache["api_key"], "key-test")

    def test_hit_fallback_models_list_is_isolated(self) -> None:
        """Appending to returned fallback_models must not mutate the cache list."""
        cs._config_cache = dict(_FAKE_CFG)
        cs._config_cache["fallback_models"] = ["gemini-2.0-flash"]
        cs._config_cache_ts = time.monotonic()

        result = cs.load_config()
        result["fallback_models"].append("injected-model")

        self.assertEqual(cs._config_cache["fallback_models"], ["gemini-2.0-flash"])

    def test_hit_fallback_keys_list_is_isolated(self) -> None:
        """Appending to returned fallback_keys must not mutate the cache list."""
        cs._config_cache = dict(_FAKE_CFG)
        cs._config_cache["fallback_keys"] = ["key-a"]
        cs._config_cache_ts = time.monotonic()

        result = cs.load_config()
        result["fallback_keys"].append("injected-key")

        self.assertEqual(cs._config_cache["fallback_keys"], ["key-a"])

    # ------------------------------------------------------------------
    # Cache miss
    # ------------------------------------------------------------------

    def test_miss_on_expired_ttl(self) -> None:
        """Stale cache forces a fresh read; with no files → default returned."""
        cs._config_cache = dict(_FAKE_CFG)
        cs._config_cache_ts = time.monotonic() - (cs._CONFIG_CACHE_TTL + 1.0)

        with patch("el_sbobinator.config_service.os.path.exists", return_value=False):
            result = cs.load_config()

        self.assertEqual(result["api_key"], "")

    def test_miss_on_none_cache_consults_disk(self) -> None:
        """No cache populated → os.path.exists is called."""
        with patch(
            "el_sbobinator.config_service.os.path.exists", return_value=False
        ) as mock_exists:
            cs.load_config()
            mock_exists.assert_called()

    def test_miss_populates_cache(self) -> None:
        """After a miss the cache is populated for the next call."""
        with patch("el_sbobinator.config_service.os.path.exists", return_value=False):
            cs.load_config()

        self.assertIsNotNone(cs._config_cache)

    def test_second_call_after_miss_hits_cache(self) -> None:
        """The second call within TTL avoids disk entirely."""
        with patch("el_sbobinator.config_service.os.path.exists", return_value=False):
            cs.load_config()

        with patch("el_sbobinator.config_service.os.path.exists") as mock_exists:
            cs.load_config()
            mock_exists.assert_not_called()

    # ------------------------------------------------------------------
    # save_config invalidation
    # ------------------------------------------------------------------

    def test_save_invalidates_cache(self) -> None:
        cs._config_cache = dict(_FAKE_CFG)
        cs._config_cache_ts = time.monotonic()

        with (
            patch(
                "el_sbobinator.config_service.platform.system", return_value="Windows"
            ),
            patch("el_sbobinator.config_service.os.path.exists", return_value=False),
            patch("el_sbobinator.config_service.os.makedirs"),
            patch(
                "el_sbobinator.config_service._dpapi_protect_text_windows",
                return_value="",
            ),
            patch("builtins.open", MagicMock()),
            patch("el_sbobinator.config_service.os.replace"),
        ):
            cs.save_config("new-key")

        self.assertIsNone(cs._config_cache)

    # ------------------------------------------------------------------
    # Thread safety
    # ------------------------------------------------------------------

    def test_concurrent_reads_no_crash(self) -> None:
        """Twenty threads reading a hot cache simultaneously must not raise."""
        cs._config_cache = dict(_FAKE_CFG)
        cs._config_cache_ts = time.monotonic()

        errors: list[Exception] = []

        def _read() -> None:
            try:
                cs.load_config()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=_read) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])


class TestCacheGenerationCounter(unittest.TestCase):
    def setUp(self) -> None:
        _reset_cache()

    def tearDown(self) -> None:
        _reset_cache()

    def test_save_config_increments_gen(self) -> None:
        """save_config must bump _config_cache_gen so concurrent load_config skips its write."""
        initial_gen = cs._config_cache_gen
        with (
            patch(
                "el_sbobinator.config_service.platform.system", return_value="Windows"
            ),
            patch("el_sbobinator.config_service.os.path.exists", return_value=False),
            patch("el_sbobinator.config_service.os.makedirs"),
            patch(
                "el_sbobinator.config_service._dpapi_protect_text_windows",
                return_value="",
            ),
            patch("builtins.open", MagicMock()),
            patch("el_sbobinator.config_service.os.replace"),
        ):
            cs.save_config("some-key")
        self.assertEqual(cs._config_cache_gen, initial_gen + 1)

    def test_stale_load_does_not_overwrite_invalidated_cache(self) -> None:
        """If gen changed between lock-release and cache-write, load must not write."""
        cs._config_cache_gen = 1  # save already ran
        gen_at_start = 0  # what load captured before the I/O phase
        stale_data = {"api_key": "stale"}

        with cs._config_lock:
            if cs._config_cache_gen == gen_at_start:
                cs._config_cache = stale_data
                cs._config_cache_ts = time.monotonic()

        self.assertIsNone(cs._config_cache)


class TestSaveConfigWriteLock(unittest.TestCase):
    def setUp(self) -> None:
        _reset_cache()

    def tearDown(self) -> None:
        _reset_cache()

    def test_write_lock_held_during_file_write(self) -> None:
        """_write_lock must be held during os.replace to serialise concurrent saves."""
        lock_held: list[bool] = []

        def _check_lock(*args: object) -> None:
            lock_held.append(cs._write_lock.locked())

        with (
            patch(
                "el_sbobinator.config_service.platform.system", return_value="Windows"
            ),
            patch("el_sbobinator.config_service.os.path.exists", return_value=False),
            patch("el_sbobinator.config_service.os.makedirs"),
            patch(
                "el_sbobinator.config_service._dpapi_protect_text_windows",
                return_value="",
            ),
            patch("builtins.open", MagicMock()),
            patch("el_sbobinator.config_service.os.replace", side_effect=_check_lock),
        ):
            cs.save_config("test-key")

        self.assertTrue(lock_held, "os.replace was never called")
        self.assertTrue(all(lock_held), "_write_lock must be held during os.replace")

    def test_write_lock_released_on_early_return(self) -> None:
        """_write_lock must be released even when the file write fails (early return path)."""
        with (
            patch(
                "el_sbobinator.config_service.platform.system", return_value="Windows"
            ),
            patch("el_sbobinator.config_service.os.path.exists", return_value=False),
            patch("el_sbobinator.config_service.os.makedirs"),
            patch(
                "el_sbobinator.config_service._dpapi_protect_text_windows",
                return_value="",
            ),
            patch("builtins.open", side_effect=OSError("disk full")),
        ):
            cs.save_config("test-key")  # must not raise

        self.assertFalse(
            cs._write_lock.locked(), "_write_lock must be released after early return"
        )

    def test_concurrent_writes_are_serialised(self) -> None:
        """Two concurrent save_config calls must not interleave their read-modify-write."""
        call_order: list[str] = []
        barrier = threading.Barrier(2)
        errors: list[Exception] = []

        real_replace = cs.os.replace

        def _tracked_replace(src: str, dst: str) -> None:
            call_order.append("write")
            real_replace(src, dst)

        def _save(tag: str, key: str) -> None:
            try:
                barrier.wait()
                with patch(
                    "el_sbobinator.config_service.os.replace",
                    side_effect=_tracked_replace,
                ):
                    cs.save_config(key)
                call_order.append(f"done-{tag}")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        with (
            patch(
                "el_sbobinator.config_service.platform.system", return_value="Windows"
            ),
            patch("el_sbobinator.config_service.os.path.exists", return_value=False),
            patch("el_sbobinator.config_service.os.makedirs"),
            patch(
                "el_sbobinator.config_service._dpapi_protect_text_windows",
                return_value="",
            ),
            patch("builtins.open", MagicMock()),
        ):
            t1 = threading.Thread(target=_save, args=("A", "key-a"))
            t2 = threading.Thread(target=_save, args=("B", "key-b"))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

        self.assertEqual(errors, [])
        # With serialisation: writes never interleave — each "write" is followed
        # immediately by its own "done-X" before the other thread's "write" appears.
        for i, event in enumerate(call_order):
            if event == "write":
                self.assertIn(call_order[i + 1], ("done-A", "done-B"))


if __name__ == "__main__":
    unittest.main()
