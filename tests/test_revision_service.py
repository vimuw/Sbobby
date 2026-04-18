import os
import tempfile
import unittest
from unittest.mock import patch

from el_sbobinator.generation_service import QuotaDailyLimitError
from el_sbobinator.revision_service import (
    _paragraphs_within_budget,
    build_macro_blocks,
    process_boundary_revision_phase,
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


def _session(pairs_total=1):
    return {
        "boundary": {"pairs_total": pairs_total, "next_pair": 1},
        "last_error": None,
    }


def _run_boundary(bdir, rdir, session):
    process_boundary_revision_phase(
        client=None,
        model_name="unused",
        boundary_dir=bdir,
        phase2_revised_dir=rdir,
        session=session,
        save_session=lambda: True,
        runtime=_FakeRuntime(),
        cancelled=lambda: False,
        fallback_keys=[],
        request_fallback_key=lambda: None,
    )


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


# ---------------------------------------------------------------------------
# _paragraphs_within_budget
# ---------------------------------------------------------------------------


class TestParagraphsWithinBudget(unittest.TestCase):
    def test_tail_window_respects_budget_and_preserves_order(self):
        parts = ["A" * 100, "B" * 100, "C" * 100, "D" * 100]
        # budget=250: collecting from end → D(100) ok, C(200) ok, B(300) exceeds and list non-empty → stop
        result = _paragraphs_within_budget(parts, 250, from_end=True)
        self.assertEqual(result, ["C" * 100, "D" * 100])

    def test_head_window_respects_budget_and_preserves_order(self):
        parts = ["A" * 100, "B" * 100, "C" * 100, "D" * 100]
        # budget=250: A(100) ok, B(200) ok, C(300) exceeds → [A, B]
        result = _paragraphs_within_budget(parts, 250, from_end=False)
        self.assertEqual(result, ["A" * 100, "B" * 100])


# ---------------------------------------------------------------------------
# process_boundary_revision_phase
# ---------------------------------------------------------------------------


class TestBoundaryRevisionPhase(unittest.TestCase):
    def test_local_overlap_symmetric_tail_contained_in_head(self):
        """strict_duplicate must detect duplicates where the TAIL paragraph is the shorter
        substring contained inside the HEAD paragraph (symmetric fix: tail in head)."""
        # Construct a pre-normalised plain-text paragraph (no special chars so that
        # normalize_paragraph() does not shrink it significantly).
        tail_para = (
            "la cellula e l unita fondamentale della vita biologica ogni cellula contiene dna "
            "che codifica per le proteine necessarie alla vita la membrana cellulare regola "
            "gli scambi con l esterno e garantisce l omeostasi il nucleo controlla le attivita "
            "cellulari"
        ).strip()
        # head = tail + small suffix so that: tail_norm IN head_norm  AND
        # len(tail_norm) / len(head_norm) >= 0.92
        head_para = (
            tail_para + " e i processi vitali"
        )  # +20 chars ≈ 3.6 % → ratio ≈ 0.965

        with tempfile.TemporaryDirectory() as tmpdir:
            bdir = os.path.join(tmpdir, "boundary")
            rdir = os.path.join(tmpdir, "revised")
            os.makedirs(bdir)
            os.makedirs(rdir)

            with open(os.path.join(rdir, "rev_001.md"), "w", encoding="utf-8") as fh:
                fh.write(f"Testo introduttivo.\n\n{tail_para}\n")
            with open(os.path.join(rdir, "rev_002.md"), "w", encoding="utf-8") as fh:
                fh.write(f"{head_para}\n\nTesto conclusivo.\n")

            session = _session()
            _run_boundary(bdir, rdir, session)

            done_path = os.path.join(bdir, "boundary_001.done")
            self.assertTrue(
                os.path.exists(done_path),
                "boundary must be marked done after local dedup",
            )

            with open(os.path.join(rdir, "rev_002.md"), encoding="utf-8") as fh:
                updated = fh.read()
            self.assertNotIn(
                tail_para,
                updated,
                "duplicate paragraph must be stripped from block N+1",
            )
            self.assertIn(
                "Testo conclusivo", updated, "non-duplicate content must be preserved"
            )

    def test_ai_failure_stops_phase_and_persists_resume_state(self):
        """When retry_with_quota raises RuntimeError the phase must stop immediately,
        set last_error='boundary_ai_failed', preserve next_pair for correct resume,
        and must NOT write the .done sentinel."""
        long_para = (
            "la fotosintesi e il processo mediante il quale le piante convertono l energia luminosa "
            "in energia chimica accumulata sotto forma di glucosio questo processo avviene nei "
            "cloroplasti attraverso due fasi principali la fase luminosa e il ciclo di Calvin"
        ).strip()  # ~265 chars, safely above the 120-char min-length guard in max_similarity

        with tempfile.TemporaryDirectory() as tmpdir:
            bdir = os.path.join(tmpdir, "boundary")
            rdir = os.path.join(tmpdir, "revised")
            os.makedirs(bdir)
            os.makedirs(rdir)

            with open(os.path.join(rdir, "rev_001.md"), "w", encoding="utf-8") as fh:
                fh.write(f"Premessa.\n\n{long_para}\n")
            # Right block: same paragraph + short suffix → strict_duplicate returns False
            # (ratio ≈ 0.91 < 0.92) but similarity is high enough to trigger AI once mocked
            with open(os.path.join(rdir, "rev_002.md"), "w", encoding="utf-8") as fh:
                fh.write(
                    f"{long_para} con una piccola variante finale aggiuntiva.\n\nContinuazione.\n"
                )

            session = _session()

            # Force SequenceMatcher to return 0.99 so the similarity gate triggers AI,
            # then make the AI call fail.
            with patch(
                "el_sbobinator.revision_service.difflib.SequenceMatcher"
            ) as mock_sm:
                mock_sm.return_value.ratio.return_value = 0.99
                with patch(
                    "el_sbobinator.revision_service.retry_with_quota",
                    side_effect=RuntimeError("network error"),
                ):
                    process_boundary_revision_phase(
                        client=object(),
                        model_name="gemini",
                        boundary_dir=bdir,
                        phase2_revised_dir=rdir,
                        session=session,
                        save_session=lambda: True,
                        runtime=_FakeRuntime(),
                        cancelled=lambda: False,
                        fallback_keys=[],
                        request_fallback_key=lambda: None,
                    )

            # Assertions inside the tempdir block so the .done check is meaningful
            # (os.path.exists would always return False after cleanup).
            self.assertEqual(
                session.get("last_error"),
                "boundary_ai_failed",
                "session must record boundary_ai_failed so pipeline gate blocks done transition",
            )
            self.assertEqual(
                session["boundary"]["next_pair"],
                1,
                "next_pair must point to the failed pair so resume retries it correctly",
            )
            self.assertFalse(
                os.path.exists(os.path.join(bdir, "boundary_001.done")),
                ".done must NOT be written on failure — writing it would silently mask the unresolved boundary",
            )

    def test_orphan_tmp_files_cleaned_on_startup(self):
        """Orphan *.tmp files left in boundary_dir by a previous crash between the two
        os.replace() calls must be removed at the start of the next run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bdir = os.path.join(tmpdir, "boundary")
            rdir = os.path.join(tmpdir, "revised")
            os.makedirs(bdir)
            os.makedirs(rdir)

            orphan_left = os.path.join(bdir, "rev_001.tmp")
            orphan_right = os.path.join(bdir, "rev_002.tmp")
            with open(orphan_left, "w", encoding="utf-8") as fh:
                fh.write("stale left content\n")
            with open(orphan_right, "w", encoding="utf-8") as fh:
                fh.write("stale right content\n")

            with open(os.path.join(rdir, "rev_001.md"), "w", encoding="utf-8") as fh:
                fh.write("blocco uno.\n")
            with open(os.path.join(rdir, "rev_002.md"), "w", encoding="utf-8") as fh:
                fh.write("blocco due.\n")

            session = _session()
            _run_boundary(bdir, rdir, session)

            self.assertFalse(
                os.path.exists(orphan_left),
                "rev_001.tmp orphan must be removed by the startup cleanup pass",
            )
            self.assertFalse(
                os.path.exists(orphan_right),
                "rev_002.tmp orphan must be removed by the startup cleanup pass",
            )

    def test_max_similarity_aligned_no_false_positive_from_cross_pairs(self):
        """The new boundary-aligned max_similarity must NOT trigger AI when the only
        high-similarity pair is at a non-aligned position (old Cartesian-product code
        would have fired; new windowed code must stay below the 0.975 threshold)."""
        # paragraph_common appears at tail[-1] and head[1] — non-aligned across the boundary
        common_para = (
            "la mitosi e un processo di divisione cellulare che produce due cellule figlie "
            "con lo stesso corredo cromosomico della cellula madre questo processo e fondamentale "
            "per la crescita e il rinnovamento dei tessuti negli organismi pluricellulari"
        ).strip()
        # Different topic at the aligned position (tail[-1] vs head[0])
        left_unique = (
            "le reazioni enzimatiche avvengono in specifici siti attivi dove il substrato "
            "si lega temporaneamente alla proteina catalitica formando un complesso che abbassa "
            "l energia di attivazione della reazione chimica nel metabolismo cellulare"
        ).strip()
        right_first = (
            "il sistema immunitario e composto da cellule specializzate come linfociti e macrofagi "
            "che riconoscono e eliminano gli agenti patogeni attraverso meccanismi di difesa "
            "altamente specifici e adattativi sviluppati durante l evoluzione degli organismi"
        ).strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            bdir = os.path.join(tmpdir, "boundary")
            rdir = os.path.join(tmpdir, "revised")
            os.makedirs(bdir)
            os.makedirs(rdir)

            with open(os.path.join(rdir, "rev_001.md"), "w", encoding="utf-8") as fh:
                fh.write(f"{left_unique}\n\n{common_para}\n")
            with open(os.path.join(rdir, "rev_002.md"), "w", encoding="utf-8") as fh:
                fh.write(f"{right_first}\n\n{common_para}\n\nContenuto finale.\n")

            session = _session()

            with patch("el_sbobinator.revision_service.retry_with_quota") as mock_rq:
                _run_boundary(bdir, rdir, session)

            mock_rq.assert_not_called()
            self.assertTrue(
                os.path.exists(os.path.join(bdir, "boundary_001.done")),
                "boundary must be resolved without AI when aligned pairs are dissimilar",
            )
            self.assertIsNone(session.get("last_error"))


# ---------------------------------------------------------------------------
# process_macro_revision_phase — two-pass retry architecture
# ---------------------------------------------------------------------------


class TestProcessMacroRevisionPhase(unittest.TestCase):
    def _make_session(self):
        return {"phase2": {"revised_done": 0}, "stage": "phase2", "last_error": None}

    def _run(self, macro_blocks, phase2_dir, session, rq_side_effect):
        """Run process_macro_revision_phase with mocked retry_with_quota and sleep."""
        with (
            patch(
                "el_sbobinator.revision_service.retry_with_quota",
                side_effect=rq_side_effect,
            ),
            patch(
                "el_sbobinator.revision_service.sleep_with_cancel", return_value=True
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
                    "el_sbobinator.revision_service.retry_with_quota",
                    side_effect=main_fail_retry_quota,
                ),
                patch(
                    "el_sbobinator.revision_service.sleep_with_cancel",
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
