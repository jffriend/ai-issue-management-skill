#!/usr/bin/env python3
"""
Drift scans over `file_issue.sh`'s own flag parsing, plus a fill check for
SKILL.template.md.

WHY THIS EXISTS
---------------
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

# Raises rather than returning empty: an unreadable file is not evidence the script is clean.

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



CASE_ARM = re.compile(r"^\s*(-[A-Za-z0-9|_-]+)\)")

# REST endpoint tails file_issue.sh prints as the remedy for a refused link (#14 KTD9); GitHub's paths, not parser flags.
GH_REMEDY_FLAGS = ("/sub_issue -F sub_issue_id=", "/dependencies/blocked_by/")

# The remedy is built on a line running a REST delete against a script-named repo; matching that keeps the allowlist honest.
REMEDY_CONSTRUCTION = "gh api -X DELETE repos/$"


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



class FlagsMatchTheScript(unittest.TestCase):
    """Can the script's own flag set still be parsed out of its text?"""

    def test_the_parser_arms_are_findable_and_include_the_known_flags(self):
        flags = parser_flags()
        for expected in ("--title", "--body-file", "--shape", "--adopt",
                         "--parent", "--no-parent", "--after", "--top",
                         "--blocked-by", "--blocks", "--dry-run", "--file-anyway",
                         "--no-board", "--position-later", "--help", "-h"):
            self.assertIn(expected, flags)

    def test_the_gh_remedy_flags_are_only_allowed_because_the_script_prints_them(self):
        """Printed as a remedy, not merely spelled somewhere in the file.

        The REST paths also appear in comments and in the writes, so a
        presence check would stay green with every remedy print site deleted.
        """
        script_text = read_or_raise(FILE_ISSUE, "remedy-flag check")
        for flag in GH_REMEDY_FLAGS:
            self.assertTrue(
                printed_as_a_remedy(flag, script_text),
                "%s is allowed only because the script prints it as a runnable "
                "remedy on a `%s` line; it no longer does"
                % (flag, REMEDY_CONSTRUCTION))

    def test_mere_presence_in_the_script_does_not_make_a_flag_a_remedy(self):
        """Appearing somewhere in the file, comments included, is not enough.

        `-X POST`, `/sub_issues` and `-F issue_id=` all appear in the script
        without being parser arms or remedies, which is exactly the set a
        hand-rolled reimplementation needs. Being printed on a runnable remedy
        line is the property that matters.
        """
        script_text = read_or_raise(FILE_ISSUE, "remedy-flag check")
        for flag in ("-X POST", "/sub_issues", "-F issue_id="):
            self.assertIn(flag, script_text,
                          "precondition: %s appears somewhere in the script" % flag)
            self.assertFalse(
                printed_as_a_remedy(flag, script_text),
                "%s is not printed as a remedy and must not be treated as one"
                % flag)


class FailClosed(unittest.TestCase):
    """A scan that cannot look must raise, never pass.

    An unrecognisable parser would otherwise be indistinguishable from a
    clean result.
    """

    def test_an_unreadable_script_raises_in_the_flag_scan(self):
        with self.assertRaises(AssertionError):
            parser_flags(Path("/nonexistent/file_issue.sh"))

    def _script_copy(self, text):
        """Write a mutated copy of the script and return its path.

        `parser_flags` takes a PATH and opens it itself, so these two tests need
        a real file -- unlike a scanner that could be handed a mutated string
        directly. The directory is torn down afterwards so no run leaves one
        behind.
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


class TemplateFillsCleanly(unittest.TestCase):
    """A literal fill of SKILL.template.md, in the guide's own example form, reads correctly."""

    def test_no_article_doubles_before_the_board_name(self):
        text = read_or_raise(REPO / "SKILL.template.md", "template scan")
        self.assertIn('e.g. "the', text, "the guide's example value starts with 'the'")
        filled = text.replace("{{BOARD_NAME}}", "the Pluckd Roadmap board (project #1)")
        self.assertNotRegex(filled, r"(?i)\bthe the\b")


if __name__ == "__main__":
    unittest.main()
