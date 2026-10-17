#!/usr/bin/env python3
"""
Tests for issue_text.py -- the pure text logic behind the issue-filing
gate and the board audit.

WHY THIS EXISTS
---------------
`docs/WORKFLOW.md` already tells a session to record an ordering constraint as a
blocker when the issue is written. That instruction was violated three times in
one day by sessions that had read it in the same sitting, so the rule now lives
in a tool that refuses rather than in prose that asks. And a truncated board
listing hid #164 well enough that a later session filed #176 as a duplicate of
it, so the filing tool also looks for near-duplicate titles before it creates
anything.

Three pieces of logic carry that, and all three are pure text:

  1. `is_plan_derived` -- does the body's `Design:` field link into
     `docs/plans/`? If it does, a parent is REQUIRED and `--no-parent` must be
     refused. This is the repo owner's rule, not the tool's judgement.
  2. `possible_duplicates` -- which OPEN issues share enough of the new title to
     be worth a human look before creating?
  3. `states_prose_ordering` -- which issue bodies state an inter-issue order in
     prose? These are the ones that need a dependency link in one direction or
     the other.

Nothing here touches GitHub, and nothing here touches the photo library.

Run:  python3 tests/test_engine_issue_text.py
"""

import sys
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent))

import issue_text as T


class DesignField(unittest.TestCase):
    """Finding and reading the `Design:` field."""

    def test_bold_markdown_design_line_is_found(self):
        body = (
            "**Measured 2026-08-19:** 449 files.\n\n"
            "**Design:** [U2 of the plan](https://github.com/jffriend/"
            "photo-consolidation/blob/main/docs/plans/2026-08-05-001-feat-x.md#u2-build)\n"
        )
        line = T.design_field(body)
        self.assertIsNotNone(line)
        self.assertIn("docs/plans/", line)

    def test_plain_design_line_is_found(self):
        body = "Design: none\n"
        self.assertEqual(T.design_field(body).strip(), "Design: none")

    def test_heading_style_design_field_is_found(self):
        body = "## Design\n\nnone\n"
        self.assertIsNotNone(T.design_field(body))

    def test_absent_design_field_is_none(self):
        self.assertIsNone(T.design_field("**Measured:** nothing to see.\n"))


class PlanDerived(unittest.TestCase):
    """The parenting rule's mechanical test.

    `plan_dir` is passed explicitly on every call (KTD3) -- `is_plan_derived`
    no longer reads a hardcoded `PLAN_DIR` module constant. `"docs/plans/"`
    here is Photos' own value; `PluckdPlanDerived` below proves the same
    function works correctly against a distinct `plan_dir`.
    """

    PLAN_DIR = "docs/plans/"

    PLAN_LINK = (
        "**Design:** [U2 of the finish-library-consolidation plan]"
        "(https://github.com/jffriend/photo-consolidation/blob/main/docs/plans/"
        "2026-08-05-001-feat-finish-library-consolidation-plan.md#u2-build-the-reconciler)"
    )

    def test_link_into_docs_plans_is_plan_derived(self):
        self.assertTrue(
            T.is_plan_derived("body\n\n" + self.PLAN_LINK + "\n", self.PLAN_DIR))

    def test_design_none_is_not_plan_derived(self):
        self.assertFalse(
            T.is_plan_derived("body\n\n**Design:** none\n", self.PLAN_DIR))

    def test_absent_design_is_not_plan_derived(self):
        self.assertFalse(
            T.is_plan_derived("body with no design field\n", self.PLAN_DIR))

    def test_link_to_the_consolidation_plan_is_not_plan_derived(self):
        # photo-consolidation-plan.md is the narrative, not docs/plans/.
        body = (
            "**Design:** [Phase 5.1](https://github.com/jffriend/photo-consolidation/"
            "blob/main/photo-consolidation-plan.md#phase-51--unify)\n"
        )
        self.assertFalse(T.is_plan_derived(body, self.PLAN_DIR))

    def test_docs_plans_elsewhere_in_the_body_does_not_count(self):
        body = "The units live in docs/plans/ somewhere.\n\n**Design:** none\n"
        self.assertFalse(T.is_plan_derived(body, self.PLAN_DIR))


class PluckdPlanDerived(unittest.TestCase):
    """The same mechanical test against a distinct `plan_dir`.

    Pluckd's config (tests/fixtures/pluckd.config.json) sets
    design_line_required=false, so file_issue.sh never calls this function
    for Pluckd today -- but the function itself must not be over-fit to
    Photos' path, since a future consumer could set design_line_required
    true with its own plan_dir.
    """

    def test_a_link_into_the_configured_plan_dir_is_plan_derived(self):
        body = "**Design:** [U1](https://github.com/jffriend/pluckd/blob/main/design/plans/u1.md)"
        self.assertTrue(T.is_plan_derived(body, "design/plans/"))

    def test_a_link_into_docs_plans_does_not_count_under_a_different_plan_dir(self):
        body = "**Design:** [U1](https://github.com/jffriend/pluckd/blob/main/docs/plans/u1.md)"
        self.assertFalse(T.is_plan_derived(body, "design/plans/"))


class SignificantWords(unittest.TestCase):
    def test_stopwords_are_stripped(self):
        words = T.significant_words("Run: re-sort the library into YYYY/MM")
        self.assertNotIn("the", words)
        self.assertNotIn("into", words)
        self.assertIn("library", words)

    def test_case_and_punctuation_are_normalised(self):
        self.assertEqual(
            T.significant_words("Decide: Wipe MyPassport!"),
            T.significant_words("decide wipe mypassport"),
        )

    def test_short_tokens_are_not_significant(self):
        self.assertNotIn("mm", T.significant_words("YYYY/MM re-sort"))


class CodeTokens(unittest.TestCase):
    def test_backtick_token_is_extracted(self):
        self.assertIn("`fix:`", T.code_tokens("Retire the `Fix:` tags"))

    def test_quoted_token_is_extracted(self):
        self.assertIn('"needsreview"', T.code_tokens('Clear the "NeedsReview" flag'))

    def test_plain_title_has_no_code_tokens(self):
        self.assertEqual(T.code_tokens("Set up the offsite backup"), set())


class Duplicates(unittest.TestCase):
    """The check that would have caught #176 duplicating #164."""

    CANDIDATES = [
        (164, "Run: re-sort the library into YYYY/MM once the dates are final"),
        (122, "Retire the Mylio sidecars safely"),
        (63, "Upload the finished library to Google Photos"),
    ]

    def test_two_shared_significant_words_flags(self):
        hits = T.possible_duplicates(
            "Re-sort the library into YYYY/MM folders", self.CANDIDATES
        )
        self.assertEqual([n for n, _t, _w in hits], [164])

    def test_one_shared_significant_word_does_not_flag(self):
        hits = T.possible_duplicates("Verify the library checksums", self.CANDIDATES)
        self.assertEqual(hits, [])

    def test_a_shared_code_token_flags_on_its_own(self):
        cands = [(200, "Embed the `Fix:` dates")]
        hits = T.possible_duplicates("Retire `Fix:`", cands)
        self.assertEqual([n for n, _t, _w in hits], [200])

    def test_the_reason_is_reported_so_a_human_can_judge(self):
        hits = T.possible_duplicates("Re-sort the library into YYYY/MM", self.CANDIDATES)
        _num, _title, why = hits[0]
        self.assertIn("library", why)


class ProseOrdering(unittest.TestCase):
    """
    The detector for "this issue states an order but records no dependency".

    An earlier naive regex reported 34 of 66 because it matched "years before
    1975" and because it only looked at `blocked_by` -- an issue that says "do
    this before the upload" is correctly recorded as BLOCKING the upload, not as
    blocked. The direction problem is handled by the audit; the false-positive
    problem is handled here.
    """

    def test_until_the_named_work_is_ordering(self):
        body = "this issue stays open until the offsite backup is running"
        self.assertTrue(T.states_prose_ordering(body))

    def test_revisit_once_the_upload_is_ordering(self):
        body = (
            "Revisit once the library has been uploaded to Google Photos and "
            "verified, and the offsite backup is running."
        )
        self.assertTrue(T.states_prose_ordering(body))

    def test_gate_on_wording_is_ordering(self):
        body = "U5 and U4b are the gate on deleting the sidecars."
        self.assertTrue(T.states_prose_ordering(body))

    def test_run_it_after_a_numbered_issue_is_ordering(self):
        body = "Run it after the sidecars and shadows are deleted (#122), not before."
        self.assertTrue(T.states_prose_ordering(body))

    def test_a_year_after_a_before_is_not_ordering(self):
        body = "Every photo dated to the years before 1975 needs a manual check."
        self.assertEqual(T.states_prose_ordering(body), [])

    def test_an_indefinite_within_task_step_is_not_ordering(self):
        # #171: "before any snapshot-taking run" is a checklist step, not an order between issues.
        body = (
            "A line is added to the pre-run checklist requiring free space on the "
            "SSD to be checked before any snapshot-taking run."
        )
        self.assertEqual(T.states_prose_ordering(body), [])

    def test_dry_run_first_boilerplate_is_not_ordering(self):
        body = "**Dry run first:** run the script with --dry-run before you start."
        self.assertEqual(T.states_prose_ordering(body), [])

    def test_a_definite_object_that_is_not_work_is_not_ordering(self):
        # #90: "the block" here is a byte range inside a HEIC file, not a task.
        body = (
            "On iPhone HEIC photos it stops before the block that holds "
            "`ContentIdentifier`, the tag that links a still to its motion clip."
        )
        self.assertEqual(T.states_prose_ordering(body), [])

    def test_a_month_and_year_after_before_is_not_ordering(self):
        body = "1,354 are dated before September 2015, which is before the feature existed."
        self.assertEqual(T.states_prose_ordering(body), [])

    def test_before_and_after_is_a_comparison_not_an_order(self):
        # #50: measuring the same paths on both sides of a run.
        body = "The same 68 paths appear before and after the VD-U8 repair run."
        self.assertEqual(T.states_prose_ordering(body), [])

    def test_a_negated_block_is_not_ordering(self):
        body = "That is the right default and nothing is blocked by it."
        self.assertEqual(T.states_prose_ordering(body), [])

    def test_the_matched_sentence_is_returned_not_just_a_boolean(self):
        body = "Filler sentence. This stays open until the offsite backup is running."
        hits = T.states_prose_ordering(body)
        self.assertEqual(len(hits), 1)
        self.assertIn("offsite backup", hits[0])


if __name__ == "__main__":
    unittest.main()
