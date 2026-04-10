import os
import tempfile
import unittest
from unittest.mock import patch

from el_sbobinator.validation_service import _check_writable_dir, validate_environment


class _AlwaysOkModels:
    def get(self, model=None, **kwargs):
        return {"model": model}


class _AlwaysOkClient:
    def __init__(self, api_key=None, **kwargs):
        self.api_key = api_key
        self.models = _AlwaysOkModels()


class _FallbackFailModels:
    def get(self, model=None, **kwargs):
        if model == "gemini-2.5-flash-lite":
            raise RuntimeError("model disabled for this key")
        return {"model": model}


class _FallbackFailClient:
    def __init__(self, api_key=None, **kwargs):
        self.api_key = api_key
        self.models = _FallbackFailModels()


class _PrimaryFailModels:
    def get(self, model=None, **kwargs):
        raise RuntimeError("primary access denied")


class _PrimaryFailClient:
    def __init__(self, api_key=None, **kwargs):
        self.api_key = api_key
        self.models = _PrimaryFailModels()


class _ClientCtorFail:
    def __init__(self, api_key=None, **kwargs):
        raise RuntimeError("invalid API key")


class _MiddleFailModels:
    def get(self, model=None, **kwargs):
        if model == "gemini-2.5-flash-lite":
            raise RuntimeError("middle model disabled")
        return {"model": model}


class _MiddleFailClient:
    def __init__(self, api_key=None, **kwargs):
        self.api_key = api_key
        self.models = _MiddleFailModels()


class _NoGenerateContentModel:
    supported_actions = ["countTokens"]


class _NoGenerateContentModels:
    def get(self, model=None, **kwargs):
        return _NoGenerateContentModel()


class _NoGenerateContentClient:
    def __init__(self, api_key=None, **kwargs):
        self.api_key = api_key
        self.models = _NoGenerateContentModels()


class ValidationServiceTests(unittest.TestCase):
    @patch("el_sbobinator.validation_service.get_desktop_dir", return_value=".")
    @patch("el_sbobinator.validation_service.resolve_ffmpeg", return_value="ffmpeg.exe")
    @patch("google.genai.Client", _AlwaysOkClient)
    def test_validate_environment_with_api_key(self, *_mocks):
        result = validate_environment(
            api_key="fake",
            validate_api_key=True,
            preferred_model="gemini-2.5-flash",
            fallback_models=["gemini-2.5-flash-lite"],
        )
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(len(result["checks"]), 5)
        api_check = next(
            check for check in result["checks"] if check["id"] == "api_key"
        )
        self.assertEqual(api_check["status"], "ok")
        details = [
            check.get("details")
            for check in result["checks"]
            if str(check.get("id", "")).startswith("api")
        ]
        self.assertIn("gemini-2.5-flash-lite", details)

    @patch("el_sbobinator.validation_service.get_desktop_dir", return_value=".")
    @patch("el_sbobinator.validation_service.resolve_ffmpeg", return_value="ffmpeg.exe")
    @patch("google.genai.Client", _FallbackFailClient)
    def test_validate_environment_keeps_primary_ok_when_fallback_fails(self, *_mocks):
        result = validate_environment(
            api_key="fake",
            validate_api_key=True,
            preferred_model="gemini-2.5-flash",
            fallback_models=["gemini-2.5-flash-lite"],
        )

        self.assertFalse(result["ok"])
        api_check = next(
            check for check in result["checks"] if check["id"] == "api_key"
        )
        fallback_check = next(
            check for check in result["checks"] if check["id"] == "api_model_1"
        )
        self.assertEqual(api_check["status"], "ok")
        self.assertEqual(fallback_check["status"], "error")
        self.assertIn("gemini-2.5-flash-lite", fallback_check["details"])
        self.assertEqual(
            fallback_check["message"],
            "Modello fallback 1 non accessibile con questa chiave.",
        )

    @patch("el_sbobinator.validation_service.get_desktop_dir", return_value=".")
    @patch("el_sbobinator.validation_service.resolve_ffmpeg", return_value="ffmpeg.exe")
    @patch("google.genai.Client", _PrimaryFailClient)
    def test_validate_environment_reports_primary_failure_as_api_key_error(
        self, *_mocks
    ):
        result = validate_environment(
            api_key="fake",
            validate_api_key=True,
            preferred_model="gemini-2.5-flash",
            fallback_models=["gemini-2.5-flash-lite"],
        )

        self.assertFalse(result["ok"])
        api_check = next(
            check for check in result["checks"] if check["id"] == "api_key"
        )
        self.assertEqual(api_check["status"], "error")
        self.assertEqual(api_check["label"], "API Key Gemini")
        self.assertEqual(
            api_check["message"],
            "API key non valida o modello primario non accessibile.",
        )
        self.assertNotIn("fallback", api_check["message"].lower())

    @patch("el_sbobinator.validation_service.get_desktop_dir", return_value=".")
    @patch("el_sbobinator.validation_service.resolve_ffmpeg", return_value="ffmpeg.exe")
    @patch("google.genai.Client", _ClientCtorFail)
    def test_validate_environment_reports_client_creation_failure_without_unbound_state(
        self, *_mocks
    ):
        result = validate_environment(
            api_key="fake",
            validate_api_key=True,
            preferred_model="gemini-2.5-flash",
            fallback_models=["gemini-2.5-flash-lite"],
        )

        self.assertFalse(result["ok"])
        api_check = next(
            check for check in result["checks"] if check["id"] == "api_key"
        )
        self.assertEqual(api_check["status"], "error")
        self.assertEqual(api_check["label"], "API Key Gemini")
        self.assertIn("invalid API key", api_check["details"])

    @patch("el_sbobinator.validation_service.get_desktop_dir", return_value=".")
    @patch("el_sbobinator.validation_service.resolve_ffmpeg", return_value="ffmpeg.exe")
    @patch("google.genai.Client", _NoGenerateContentClient)
    def test_validate_environment_rejects_models_without_generate_content(
        self, *_mocks
    ):
        result = validate_environment(
            api_key="fake",
            validate_api_key=True,
            preferred_model="gemini-2.5-flash",
            fallback_models=[],
        )

        self.assertFalse(result["ok"])
        api_check = next(
            check for check in result["checks"] if check["id"] == "api_key"
        )
        self.assertEqual(api_check["status"], "error")
        self.assertIn("generateContent", api_check["details"])

    @patch("el_sbobinator.validation_service.get_desktop_dir", return_value=".")
    @patch("el_sbobinator.validation_service.resolve_ffmpeg", return_value="ffmpeg.exe")
    @patch("google.genai.Client", _MiddleFailClient)
    def test_validate_environment_continues_after_middle_fallback_failure(
        self, *_mocks
    ):
        result = validate_environment(
            api_key="fake",
            validate_api_key=True,
            preferred_model="gemini-2.5-flash",
            fallback_models=["gemini-2.5-flash-lite", "gemini-3-flash-preview"],
        )

        self.assertFalse(result["ok"])
        check_ids = [check["id"] for check in result["checks"]]
        self.assertIn("api_key", check_ids)
        self.assertIn("api_model_1", check_ids)
        self.assertIn("api_model_2", check_ids)

        api_check = next(c for c in result["checks"] if c["id"] == "api_key")
        middle_check = next(c for c in result["checks"] if c["id"] == "api_model_1")
        last_check = next(c for c in result["checks"] if c["id"] == "api_model_2")

        self.assertEqual(api_check["status"], "ok")
        self.assertEqual(middle_check["status"], "error")
        self.assertIn("gemini-2.5-flash-lite", middle_check["details"])
        self.assertEqual(last_check["status"], "ok")
        self.assertEqual(last_check["details"], "gemini-3-flash-preview")


class CheckWritableDirTests(unittest.TestCase):
    def test_returns_true_when_directory_is_writable(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, msg = _check_writable_dir(tmp)
        self.assertTrue(ok)
        self.assertIn("consentita", msg)

    def test_returns_true_even_when_remove_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("os.remove", side_effect=OSError("locked")):
                ok, msg = _check_writable_dir(tmp)
            probe = os.path.join(tmp, ".el_sbobinator_write_test")
            if os.path.exists(probe):
                os.remove(probe)
        self.assertTrue(ok)
        self.assertIn("consentita", msg)

    def test_returns_false_when_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("builtins.open", side_effect=PermissionError("no write")):
                ok, msg = _check_writable_dir(tmp)
        self.assertFalse(ok)
        self.assertIn("no write", msg)


if __name__ == "__main__":
    unittest.main()
