import os
import tempfile
import unittest
from unittest.mock import patch

from el_sbobinator.revision_service import (
    _paragraphs_within_budget,
    build_macro_blocks,
    process_boundary_revision_phase,
)


# ---------------------------------------------------------------------------
# Helpers shared across test classes
# ---------------------------------------------------------------------------

class _FakeRuntime:
    def phase(self, *a): pass
    def set_work_totals(self, **kw): pass
    def update_work_done(self, *a, **kw): pass
    def progress(self, v): pass
    def register_step_time(self, *a, **kw): pass


def _session(pairs_total=1):
    return {"boundary": {"pairs_total": pairs_total, "next_pair": 1}, "last_error": None}


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
            len(blocks), 1,
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
        head_para = tail_para + " e i processi vitali"   # +20 chars ≈ 3.6 % → ratio ≈ 0.965

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
            self.assertTrue(os.path.exists(done_path), "boundary must be marked done after local dedup")

            with open(os.path.join(rdir, "rev_002.md"), encoding="utf-8") as fh:
                updated = fh.read()
            self.assertNotIn(tail_para, updated, "duplicate paragraph must be stripped from block N+1")
            self.assertIn("Testo conclusivo", updated, "non-duplicate content must be preserved")

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
                fh.write(f"{long_para} con una piccola variante finale aggiuntiva.\n\nContinuazione.\n")

            session = _session()

            # Force SequenceMatcher to return 0.99 so the similarity gate triggers AI,
            # then make the AI call fail.
            with patch("el_sbobinator.revision_service.difflib.SequenceMatcher") as mock_sm:
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
                session.get("last_error"), "boundary_ai_failed",
                "session must record boundary_ai_failed so pipeline gate blocks done transition",
            )
            self.assertEqual(
                session["boundary"]["next_pair"], 1,
                "next_pair must point to the failed pair so resume retries it correctly",
            )
            self.assertFalse(
                os.path.exists(os.path.join(bdir, "boundary_001.done")),
                ".done must NOT be written on failure — writing it would silently mask the unresolved boundary",
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


if __name__ == "__main__":
    unittest.main()
