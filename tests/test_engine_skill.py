#!/usr/bin/env python3
"""
Ported from Photos' tests/test_file_issue_skill.py. That file is a conformance
and drift scan for `.claude/skills/file-issue/SKILL.md` -- Photos' own skill
wrapper around `scripts/file_issue.sh`. This repo has no SKILL.md and no
skill-wrapper concept, so every class and helper that reads or checks the
skill document, its frontmatter, or Photos' own CLAUDE.md/docs/WORKFLOW.md was
left behind (`SkillDrivesTheScript`, `NoReimplementation`,
`FrontmatterKeepsTheSkillReachable`, `DocumentationNamesTheFrontDoor`, and the
skill-file-specific test in `FailClosed`). What's ported is only the coverage
of the script's own flag parsing and its fail-closed behavior when that
parsing can't find what it expects: `FlagsMatchTheScript` (trimmed to the
sub-tests that check the script alone, not a skill document naming its
flags) and the parser-block-gutting tests from `FailClosed`.

WHY THIS EXISTS (from the original file, as it applies to what remains)
------------------------------------------------------------------------
Does any flag this scan expects still exist in the script? The `--flag)` arms
are parsed out of the script itself via `parser_flags()`. Can the parser scan
actually fail rather than silently reporting no flags? `FailClosed`'s
meta-tests plant a gutted or missing parser block and assert the scan raises
rather than passing vacuously.

Run:  python3 tests/test_engine_skill.py
"""

import re
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
FILE_ISSUE = REPO / "file_issue.sh"

# --------------------------------------------------------------------------
# Reading. Raises rather than returning an empty result: an unreadable file is
# not evidence that the script is clean.
# --------------------------------------------------------------------------

def read_or_raise(path, scan_name):
    """Return the file's text, or raise naming the scan that wanted it.

    A scan that cannot open its subject proves nothing, so an OSError becomes a
    failure rather than a silent pass -- the same rule
    `scan_for_duplicated_comparisons` follows in tests/test_engine_gating.py
    ("Unable to look is not permission").
    """
    try:
        return Path(path).read_text()
    except OSError as exc:
        raise AssertionError(
            "the %s could not read %s (%s). "
            "Unable to look is not permission." % (scan_name, path, exc)) from exc


# --------------------------------------------------------------------------
# Flag drift.
# --------------------------------------------------------------------------

CASE_ARM = re.compile(r"^\s*(-[A-Za-z0-9|_-]+)\)")

# `file_issue.sh` prints these `gh issue edit` flags back to the caller
# as the remedy for a link it refuses to reconcile. They are gh's flags, not
# the script's, so they cannot be parser arms.
GH_REMEDY_FLAGS = ("--remove-parent", "--remove-blocked-by", "--remove-blocking")

# The remedy is CONSTRUCTED on a line naming the issue being adopted. Matching
# that construction is what keeps this allowlist honest.
#
# The earlier version tested `flag in script_text` -- membership in the whole
# file, comments included -- and claimed in its own comment that this meant
# the list "cannot be used to smuggle in a flag nothing accepts". It could:
# `--repo`, `--label`, `--json`, `--limit`, `--owner` and `--url` all appear
# somewhere in the script without being parser arms.
REMEDY_CONSTRUCTION = "gh issue edit $ADOPT"


def printed_as_a_remedy(flag, script_text):
    """True when the script really prints `flag` as a remedy the caller can run."""
    return any(REMEDY_CONSTRUCTION in line and flag in line
               for line in script_text.splitlines())


def parser_flags(path=FILE_ISSUE, text=None):
    """Return every flag `file_issue.sh` accepts, parsed from its own text.

    The flags live in the `while [ $# -gt 0 ]` loop's `case "$1" in`, whose arms
    look like `--title)` and, for the alternation form, `-h|--help)`. Raises when
    that loop cannot be found or looks implausibly small: a parser this scan
    cannot locate would turn the drift check into a vacuous pass.

    `text` lets a caller that has already read the script pass it in rather than
    reading the same file twice.
    """
    if text is None:
        text = read_or_raise(path, "flag-drift scan")
    match = re.search(r'case\s+"\$1"\s+in(.*?)\n\s*esac', text, re.DOTALL)
    if not match:
        raise AssertionError(
            "the argument parser (`case \"$1\" in` inside the `while [ $# -gt 0 ]` "
            "loop) was not found in %s. Without it this scan proves nothing." % path)
    flags = set()
    for line in match.group(1).splitlines():
        arm = CASE_ARM.match(line)
        if not arm:
            continue
        for token in arm.group(1).split("|"):
            if token.startswith("-"):
                flags.add(token)
    if "--dry-run" not in flags or len(flags) < 8:
        raise AssertionError(
            "only %d flag arms were parsed out of %s (%s). The parser's shape has "
            "changed and this scan can no longer read it."
            % (len(flags), path, sorted(flags)))
    return flags


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

class FlagsMatchTheScript(unittest.TestCase):
    """Can the script's own flag set still be parsed out of its text?

    Trimmed from Photos' version, which also compared the parsed set against
    every flag `.claude/skills/file-issue/SKILL.md` names -- this repo has no
    such document, so only the sub-tests that check the script alone survive.
    """

    def test_the_parser_arms_are_findable_and_include_the_known_flags(self):
        flags = parser_flags()
        for expected in ("--title", "--body-file", "--shape", "--adopt",
                         "--parent", "--no-parent", "--after", "--top",
                         "--blocked-by", "--blocks", "--dry-run", "--help", "-h"):
            self.assertIn(expected, flags)

    def test_the_gh_remedy_flags_are_only_allowed_because_the_script_prints_them(self):
        """Printed as a remedy, not merely spelled somewhere in the file.

        All three flags also appear in the capability probe's required-flag
        string, so asserting mere presence stayed green even with every remedy
        print site deleted -- the test was named for a thing it did not check.
        """
        script_text = read_or_raise(FILE_ISSUE, "remedy-flag check")
        for flag in GH_REMEDY_FLAGS:
            self.assertTrue(
                printed_as_a_remedy(flag, script_text),
                "%s is allowed only because the script prints it as a runnable "
                "remedy on a `%s` line; it no longer does"
                % (flag, REMEDY_CONSTRUCTION))

    def test_mere_presence_in_the_script_does_not_make_a_flag_a_remedy(self):
        """The claim the old comment made and the code did not keep.

        The old test was `flag in script_text` -- membership in the whole file,
        comments included. `--label`, `--json`, `--limit` and `--url` all appear
        somewhere in the script without being parser arms or remedies, which is
        exactly the set a hand-rolled reimplementation needs. Being printed on a
        runnable remedy line is the property that matters.
        """
        script_text = read_or_raise(FILE_ISSUE, "remedy-flag check")
        for flag in ("--label", "--json", "--limit"):
            self.assertIn(flag, script_text,
                          "precondition: %s appears somewhere in the script" % flag)
            self.assertFalse(
                printed_as_a_remedy(flag, script_text),
                "%s is not printed as a remedy and must not be treated as one"
                % flag)


class FailClosed(unittest.TestCase):
    """A scan that cannot look must raise, never pass.

    Trimmed from Photos' version to the parser-block-gutting tests -- an
    unrecognisable parser used to be indistinguishable from a clean result.
    That is a failure here. (Photos' sibling test for an unreadable SKILL.md
    is left behind along with the rest of the skill-document coverage.)
    """

    def test_an_unreadable_script_raises_in_the_flag_scan(self):
        with self.assertRaises(AssertionError):
            parser_flags(Path("/nonexistent/file_issue.sh"))

    def _script_copy(self, text):
        """Write a mutated copy of the script and return its path.

        `parser_flags` takes a PATH and opens it itself, so these two tests need
        a real file -- unlike a scanner that could be handed a mutated string
        directly. The directory is torn down afterwards: `mkdtemp` left one
        behind per test, every run, forever.
        """
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / "file_issue.sh"
        path.write_text(text)
        return path

    def test_a_missing_parser_block_raises(self):
        text = FILE_ISSUE.read_text().replace('case "$1" in', 'case "$X" in', 1)
        with self.assertRaises(AssertionError):
            parser_flags(self._script_copy(text))

    def test_a_gutted_parser_block_raises_rather_than_reporting_no_flags(self):
        """Arms removed one by one would otherwise shrink the scan to nothing."""
        text = FILE_ISSUE.read_text()
        match = re.search(r'case\s+"\$1"\s+in(.*?)\n\s*esac', text, re.DOTALL)
        self.assertIsNotNone(match, "the arm block to gut was not found")
        gutted = text[:match.start(1)] + '\n    *) die "no." ;;\n' + text[match.end(1):]
        with self.assertRaises(AssertionError):
            parser_flags(self._script_copy(gutted))


if __name__ == "__main__":
    unittest.main()
