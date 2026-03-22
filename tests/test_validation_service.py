import unittest
from unittest.mock import patch

from el_sbobinator.validation_service import validate_environment


class _FakeModels:
    def get(self, model=None, **kwargs):
        return {"model": model}


class _FakeClient:
    def __init__(self, api_key=None, **kwargs):
        self.api_key = api_key
        self.models = _FakeModels()


class ValidationServiceTests(unittest.TestCase):
    @patch("el_sbobinator.validation_service.get_desktop_dir", return_value=".")
    @patch("el_sbobinator.validation_service.resolve_ffmpeg", return_value="ffmpeg.exe")
    @patch("google.genai.Client", _FakeClient)
    def test_validate_environment_with_api_key(self, *_mocks):
        result = validate_environment(api_key="fake", validate_api_key=True)
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(len(result["checks"]), 4)
        api_check = next(check for check in result["checks"] if check["id"] == "api_key")
        self.assertEqual(api_check["status"], "ok")


if __name__ == "__main__":
    unittest.main()
