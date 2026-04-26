import io
import logging
import os
import tempfile
import unittest

from el_sbobinator.utils.logging_utils import (
    LOGGER_NAME,
    StructuredFormatter,
    attach_file_handler,
    configure_logging,
    detach_file_handler,
    get_logger,
)


class StructuredFormatterTests(unittest.TestCase):
    def _make_record(self, msg="test message", **context):
        record = logging.LogRecord(
            name=LOGGER_NAME,
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for key, value in context.items():
            setattr(record, key, value)
        return record

    def test_no_context_returns_base_format(self):
        fmt = StructuredFormatter("%(message)s", "%H:%M:%S")
        record = self._make_record("hello")
        result = fmt.format(record)
        self.assertEqual(result, "hello")

    def test_with_context_appends_key_value_pairs(self):
        fmt = StructuredFormatter("%(message)s", "%H:%M:%S")
        record = self._make_record("hello", run_id="abc123", stage="phase1")
        result = fmt.format(record)
        self.assertIn("run_id=abc123", result)
        self.assertIn("stage=phase1", result)
        self.assertIn("[", result)

    def test_empty_context_values_not_appended(self):
        fmt = StructuredFormatter("%(message)s", "%H:%M:%S")
        record = self._make_record("hello", run_id="", session_dir=None)
        result = fmt.format(record)
        self.assertNotIn("[", result)


class ConfigureLoggingTests(unittest.TestCase):
    def setUp(self):
        logger = logging.getLogger(LOGGER_NAME)
        logger.__dict__.pop("_el_sbobinator_configured", None)
        logger.handlers = [
            h for h in logger.handlers if type(h) is not logging.StreamHandler
        ]

    def tearDown(self):
        logger = logging.getLogger(LOGGER_NAME)
        if not getattr(logger, "_el_sbobinator_configured", False):
            configure_logging()

    def test_returns_logger_with_correct_name(self):
        logger = configure_logging(stream=io.StringIO())
        self.assertEqual(logger.name, LOGGER_NAME)

    def test_second_call_returns_same_logger_without_adding_handler(self):
        stream = io.StringIO()
        logger1 = configure_logging(stream=stream)
        handler_count_before = len(logger1.handlers)
        logger2 = configure_logging(stream=stream)
        self.assertIs(logger1, logger2)
        self.assertEqual(len(logger2.handlers), handler_count_before)


class GetLoggerTests(unittest.TestCase):
    def test_returns_logger_adapter(self):
        adapter = get_logger()
        self.assertIsInstance(adapter, logging.LoggerAdapter)

    def test_context_included_in_adapter_extra(self):
        adapter = get_logger(run_id="run-42", stage="phase2")
        assert adapter.extra is not None
        self.assertEqual(adapter.extra.get("run_id"), "run-42")
        self.assertEqual(adapter.extra.get("stage"), "phase2")

    def test_empty_context_values_excluded(self):
        adapter = get_logger(run_id="", session_dir=None)  # type: ignore[arg-type]
        assert adapter.extra is not None
        self.assertNotIn("run_id", adapter.extra)
        self.assertNotIn("session_dir", adapter.extra)

    def test_named_sub_logger(self):
        adapter = get_logger(name="el_sbobinator.pipeline")
        self.assertEqual(adapter.logger.name, "el_sbobinator.pipeline")


class AttachDetachFileHandlerTests(unittest.TestCase):
    def test_attach_creates_file_and_returns_handler(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "sub", "app.log")
            handler = attach_file_handler(log_path)
            try:
                self.assertIsNotNone(handler)
                self.assertTrue(os.path.exists(log_path))
            finally:
                detach_file_handler(handler)

    def test_attach_invalid_path_returns_none(self):
        handler = attach_file_handler("\x00invalid\x00path.log")
        self.assertIsNone(handler)

    def test_detach_none_is_noop(self):
        detach_file_handler(None)

    def test_detach_removes_handler_from_logger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "app.log")
            handler = attach_file_handler(log_path)
            self.assertIsNotNone(handler)
            logger = configure_logging()
            self.assertIn(handler, logger.handlers)
            detach_file_handler(handler)
            self.assertNotIn(handler, logger.handlers)


if __name__ == "__main__":
    unittest.main()
