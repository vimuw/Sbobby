import unittest
from unittest.mock import patch

from el_sbobinator.model_registry import (
    MODEL_OPTIONS,
    SUPPORTED_MODELS,
    build_model_state,
    default_chunk_minutes_for_model,
    default_macro_char_limit_for_model,
    sanitize_fallback_models,
)
from el_sbobinator.pipeline.pipeline_settings import load_and_sanitize_settings


class ResumeModelStateTests(unittest.TestCase):
    def test_resume_without_effective_starts_from_primary(self):
        """Resume with no effective_model → current = primary."""
        ms = build_model_state("gemini-2.5-flash", ["gemini-2.5-flash-lite"])
        self.assertEqual(ms.current, "gemini-2.5-flash")

    def test_resume_ignores_stale_effective_model(self):
        """Pipeline no longer passes effective_model at resume; chain and primary are correct."""
        ms = build_model_state("gemini-2.5-flash", ["gemini-2.5-flash-lite"])
        self.assertEqual(ms.current, "gemini-2.5-flash")
        self.assertEqual(ms.chain, ("gemini-2.5-flash", "gemini-2.5-flash-lite"))

    def test_chain_preserved_for_fallback_on_503(self):
        """Fallback chain is still intact so retry_with_quota can degrade if needed."""
        ms = build_model_state("gemini-2.5-flash", ["gemini-2.5-flash-lite"])
        self.assertIn("gemini-2.5-flash-lite", ms.chain)


class SupportedModelsTests(unittest.TestCase):
    def test_gemini_25_flash_in_supported_models(self):
        self.assertIn("gemini-2.5-flash", SUPPORTED_MODELS)

    def test_gemini_25_flash_lite_in_supported_models(self):
        self.assertIn("gemini-2.5-flash-lite", SUPPORTED_MODELS)

    def test_removed_models_not_in_supported_models(self):
        for removed in ("gemini-2.5-pro", "gemini-2.0-flash", "gemini-2.0-flash-lite"):
            self.assertNotIn(
                removed, SUPPORTED_MODELS, f"{removed} should have been removed"
            )

    def test_gemini_31_flash_lite_preview_in_supported_models(self):
        self.assertIn("gemini-3.1-flash-lite-preview", SUPPORTED_MODELS)

    def test_gemini_15_flash_not_in_supported_models(self):
        self.assertNotIn("gemini-1.5-flash", SUPPORTED_MODELS)

    def test_current_fallbacks_accepted_by_sanitize_fallback_models(self):
        result = sanitize_fallback_models(
            ["gemini-2.5-flash-lite", "gemini-3.1-flash-lite-preview"],
            primary_model="gemini-2.5-flash",
        )
        self.assertEqual(
            result,
            ["gemini-2.5-flash-lite", "gemini-3.1-flash-lite-preview"],
        )

    def test_removed_models_filtered_by_sanitize_fallback_models(self):
        result = sanitize_fallback_models(
            ["gemini-2.0-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"],
            primary_model="gemini-2.5-flash",
        )
        self.assertEqual(result, ["gemini-2.5-flash-lite"])

    def test_chain_with_current_default_fallbacks(self):
        ms = build_model_state(
            "gemini-2.5-flash",
            ["gemini-2.5-flash-lite", "gemini-3.1-flash-lite-preview"],
        )
        self.assertEqual(
            ms.chain,
            (
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
                "gemini-3.1-flash-lite-preview",
            ),
        )
        self.assertEqual(ms.current, "gemini-2.5-flash")

    def test_unsupported_primary_falls_back_to_default(self):
        ms = build_model_state("gemini-2.5-pro", ["gemini-2.5-flash"])
        self.assertEqual(ms.current, "gemini-2.5-flash")
        self.assertIn("gemini-2.5-flash", ms.chain)


class DefaultChunkMinutesTests(unittest.TestCase):
    def test_known_models_match_model_options(self):
        for opt in MODEL_OPTIONS:
            expected = int(opt["default_chunk_minutes"])
            got = default_chunk_minutes_for_model(opt["id"])
            self.assertEqual(
                got,
                expected,
                msg=f"model {opt['id']!r}: expected {expected}, got {got}",
            )

    def test_unknown_model_falls_back_to_15(self):
        result = default_chunk_minutes_for_model("gemini-unknown-model")
        self.assertEqual(result, 15)

    def test_derives_from_model_options_not_hardcoded(self):
        patched = tuple(
            {**opt, "default_chunk_minutes": 42}
            if opt["id"] == "gemini-2.5-flash-lite"
            else opt
            for opt in MODEL_OPTIONS
        )
        with patch("el_sbobinator.model_registry.MODEL_OPTIONS", patched):
            result = default_chunk_minutes_for_model("gemini-2.5-flash-lite")
        self.assertEqual(result, 42)


class DefaultMacroCharLimitTests(unittest.TestCase):
    def test_known_models_match_model_options(self):
        for opt in MODEL_OPTIONS:
            expected = int(opt["default_macro_char_limit"])
            got = default_macro_char_limit_for_model(opt["id"])
            self.assertEqual(
                got,
                expected,
                msg=f"model {opt['id']!r}: expected {expected}, got {got}",
            )

    def test_flash_lite_31_returns_7500(self):
        result = default_macro_char_limit_for_model("gemini-3.1-flash-lite-preview")
        self.assertEqual(result, 7500)

    def test_flash_lite_25_returns_15000(self):
        result = default_macro_char_limit_for_model("gemini-2.5-flash-lite")
        self.assertEqual(result, 15000)

    def test_unknown_model_falls_back_to_22000(self):
        result = default_macro_char_limit_for_model("gemini-unknown-model")
        self.assertEqual(result, 22000)

    def test_load_and_sanitize_defaults_macro_from_model_when_missing(self):
        session = {
            "settings": {
                "model": "gemini-3.1-flash-lite-preview",
                "fallback_models": [],
                "effective_model": "gemini-3.1-flash-lite-preview",
                "audio": {"bitrate": "48k"},
            }
        }
        settings, changed = load_and_sanitize_settings(session)
        self.assertEqual(settings.macro_char_limit, 7500)
        self.assertEqual(session["settings"]["macro_char_limit"], 7500)
        self.assertTrue(changed)

    def test_load_and_sanitize_migrates_old_global_default_for_flash_lite_31(self):
        session = {
            "settings": {
                "model": "gemini-3.1-flash-lite-preview",
                "fallback_models": [],
                "effective_model": "gemini-3.1-flash-lite-preview",
                "chunk_minutes": 5,
                "overlap_seconds": 30,
                "macro_char_limit": 22000,
                "preconvert_audio": True,
                "prefetch_next_chunk": True,
                "inline_audio_max_mb": 6.0,
                "audio": {"bitrate": "48k"},
            }
        }
        settings, changed = load_and_sanitize_settings(session)
        self.assertEqual(settings.macro_char_limit, 7500)
        self.assertEqual(session["settings"]["macro_char_limit"], 7500)
        self.assertTrue(changed)

    def test_load_and_sanitize_migrates_old_global_default_for_flash_lite_25(self):
        session = {
            "settings": {
                "model": "gemini-2.5-flash-lite",
                "fallback_models": [],
                "effective_model": "gemini-2.5-flash-lite",
                "chunk_minutes": 10,
                "overlap_seconds": 30,
                "macro_char_limit": 22000,
                "preconvert_audio": True,
                "prefetch_next_chunk": True,
                "inline_audio_max_mb": 6.0,
                "audio": {"bitrate": "48k"},
            }
        }
        settings, changed = load_and_sanitize_settings(session)
        self.assertEqual(settings.macro_char_limit, 15000)
        self.assertEqual(session["settings"]["macro_char_limit"], 15000)
        self.assertTrue(changed)

    def test_load_and_sanitize_preserves_explicit_non_default_macro_char_limit(self):
        session = {
            "settings": {
                "model": "gemini-3.1-flash-lite-preview",
                "fallback_models": [],
                "effective_model": "gemini-3.1-flash-lite-preview",
                "chunk_minutes": 5,
                "overlap_seconds": 30,
                "macro_char_limit": 10000,
                "preconvert_audio": True,
                "prefetch_next_chunk": True,
                "inline_audio_max_mb": 6.0,
                "audio": {"bitrate": "48k"},
            }
        }
        settings, changed = load_and_sanitize_settings(session)
        self.assertEqual(settings.macro_char_limit, 10000)


if __name__ == "__main__":
    unittest.main()
