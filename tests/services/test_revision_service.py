import os
import tempfile
import unittest
from unittest.mock import patch

from el_sbobinator.services.generation_service import QuotaDailyLimitError
from el_sbobinator.services.revision_service import (
    build_macro_blocks,
    process_macro_revision_phase,
)

# ---------------------------------------------------------------------------
# Helpers shared across test classes
# ---------------------------------------------------------------------------


class _FakeRuntime:
    def phase(self, *a):
        pass

    def set_work_totals(self, **kw):
        pass

    def update_work_done(self, *a, **kw):
        pass

    def progress(self, v):
        pass

    def register_step_time(self, *a, **kw):
        pass


# ---------------------------------------------------------------------------
# build_macro_blocks
# ---------------------------------------------------------------------------


class TestBuildMacroBlocks(unittest.TestCase):
    def test_heading_aware_split_past_soft_threshold(self):
        char_limit = 1000
        # body must be > 500 chars (has_content guard) AND > 70 % of limit (700 chars)
        body = "A" * 750
        text = body + "\n\n## Nuova Sezione\n\nContenuto della nuova sezione."
        blocks = build_macro_blocks(text, char_limit)
        self.assertEqual(len(blocks), 2, "H2 heading past 70 % should open a new block")
        self.assertTrue(
            blocks[1].strip().startswith("## Nuova Sezione"),
            "new block must start with the heading, not trail behind it",
        )

    def test_no_premature_split_before_soft_threshold(self):
        char_limit = 1000
        # Heading appears at only 200 chars — well below the 70 % (700 char) threshold
        text = "A" * 200 + "\n\n## Titolo Anticipato\n\nAltra roba qui."
        blocks = build_macro_blocks(text, char_limit)
        self.assertEqual(
            len(blocks),
            1,
            "heading appearing before 70 % of the limit must NOT trigger a split",
        )


class TestProcessMacroRevisionPhase(unittest.TestCase):
    def _make_session(self):
        return {"phase2": {"revised_done": 0}, "stage": "phase2", "last_error": None}

    def _run(self, macro_blocks, phase2_dir, session, rq_side_effect):
        """Run process_macro_revision_phase with mocked retry_with_quota and sleep."""
        with (
            patch(
                "el_sbobinator.services.revision_service.retry_with_quota",
                side_effect=rq_side_effect,
            ),
            patch(
                "el_sbobinator.services.revision_service.sleep_with_cancel",
                return_value=True,
            ),
        ):
            _, revised_text = process_macro_revision_phase(
                client=object(),
                model_name="test-model",
                macro_blocks=macro_blocks,
                phase2_revised_dir=phase2_dir,
                session=session,
                save_session=lambda: True,
                runtime=_FakeRuntime(),
                cancelled=lambda: False,
                fallback_keys=[],
                request_fallback_key=lambda: None,
                prompt_revisione="Revisiona.",
            )
        return revised_text

    def test_main_pass_success_writes_md_and_increments_revised_done(self):
        """Happy path: retry_with_quota succeeds → .md created, revised_done=1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session()

            def success(fn, *, client, **kw):
                return client, "Testo revisionato"

            self._run(["Blocco."], tmpdir, session, success)

            self.assertTrue(os.path.exists(os.path.join(tmpdir, "rev_001.md")))
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "rev_001.raw.md")))
            self.assertEqual(session["phase2"]["revised_done"], 1)
            self.assertEqual(session.get("revision_failed_blocks", []), [])

    def test_main_pass_failure_writes_raw_md_not_md(self):
        """Main pass fail → .raw.md written (not .md), retry pass also fails →
        finalized to .md with raw content, block in revision_failed_blocks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session()

            def always_fail(fn, *, client, **kw):
                raise RuntimeError("network error")

            self._run(["Blocco grezzo."], tmpdir, session, always_fail)

            self.assertFalse(os.path.exists(os.path.join(tmpdir, "rev_001.raw.md")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "rev_001.md")))
            self.assertIn(1, session.get("revision_failed_blocks", []))

    def test_resume_with_raw_md_goes_to_retry_pass_not_skipped_as_done(self):
        """On resume, a pre-existing .raw.md must trigger the retry pass,
        not be silently skipped like a completed block."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_path = os.path.join(tmpdir, "rev_001.raw.md")
            with open(raw_path, "w", encoding="utf-8") as fh:
                fh.write("Contenuto raw originale.\n")

            session = self._make_session()
            call_count = [0]

            def track_calls(fn, *, client, **kw):
                call_count[0] += 1
                return client, "Testo revisionato dal retry"

            self._run(["Contenuto raw originale."], tmpdir, session, track_calls)

            self.assertEqual(
                call_count[0],
                1,
                "retry_with_quota must be called exactly once (retry pass)",
            )
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "rev_001.md")))
            self.assertFalse(os.path.exists(raw_path))
            self.assertEqual(session.get("revision_failed_blocks", []), [])

    def test_retry_pass_success_removes_raw_md_and_creates_md(self):
        """Main pass fails → .raw.md; retry pass succeeds → .md created,
        .raw.md deleted, NOT in revision_failed_blocks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session()
            calls = [0]

            def first_fail_then_success(fn, *, client, **kw):
                calls[0] += 1
                if calls[0] == 1:
                    raise RuntimeError("main pass fail")
                return client, "Testo dal retry"

            revised_text = self._run(
                ["Blocco."], tmpdir, session, first_fail_then_success
            )

            self.assertFalse(os.path.exists(os.path.join(tmpdir, "rev_001.raw.md")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "rev_001.md")))
            self.assertEqual(session.get("revision_failed_blocks", []), [])
            self.assertIn("Testo dal retry", revised_text)

    def test_retry_pass_definitive_failure_finalizes_to_md_and_records_failed_blocks(
        self,
    ):
        """Both main pass and retry pass fail → .raw.md renamed to .md (raw content preserved),
        block index recorded in session revision_failed_blocks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session()

            def always_fail(fn, *, client, **kw):
                raise RuntimeError("always fails")

            self._run(["Contenuto grezzo."], tmpdir, session, always_fail)

            rev_path = os.path.join(tmpdir, "rev_001.md")
            self.assertTrue(os.path.exists(rev_path))
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "rev_001.raw.md")))
            self.assertIn(1, session.get("revision_failed_blocks", []))

    def test_quota_in_retry_pass_leaves_raw_md_and_does_not_finalize(self):
        """Main pass fails (RuntimeError) → .raw.md written.
        Retry pass raises QuotaDailyLimitError → early return,
        .raw.md must remain on disk, last_error set, .md must NOT exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session()
            calls = [0]

            def main_fail_retry_quota(fn, *, client, **kw):
                calls[0] += 1
                if calls[0] == 1:
                    raise RuntimeError("main pass fail")
                raise QuotaDailyLimitError("quota in retry")

            with (
                patch(
                    "el_sbobinator.services.revision_service.retry_with_quota",
                    side_effect=main_fail_retry_quota,
                ),
                patch(
                    "el_sbobinator.services.revision_service.sleep_with_cancel",
                    return_value=True,
                ),
            ):
                process_macro_revision_phase(
                    client=object(),
                    model_name="test-model",
                    macro_blocks=["Blocco."],
                    phase2_revised_dir=tmpdir,
                    session=session,
                    save_session=lambda: True,
                    runtime=_FakeRuntime(),
                    cancelled=lambda: False,
                    fallback_keys=[],
                    request_fallback_key=lambda: None,
                    prompt_revisione="Revisiona.",
                )

            self.assertTrue(
                os.path.exists(os.path.join(tmpdir, "rev_001.raw.md")),
                ".raw.md must remain when quota interrupts retry pass",
            )
            self.assertFalse(
                os.path.exists(os.path.join(tmpdir, "rev_001.md")),
                ".md must NOT be created if retry was interrupted",
            )
            self.assertEqual(session.get("last_error"), "quota_daily_limit_phase2")


if __name__ == "__main__":
    unittest.main()
