#!/usr/bin/env python3
"""
Ported from Photos' tests/test_file_issue_gating.py, unchanged except for the
FILE_ISSUE path constant (no scripts/ subdirectory here) and one excluded test
method (see AbsentRefusalWording below) that checked Photos' own
docs/WORKFLOW.md, which does not exist in this repo.

Tests for file_issue.sh -- the gate that refuses to create an issue with
an unanswered placement question.

WHY THIS EXISTS
---------------
`docs/WORKFLOW.md` says an ordering constraint must be recorded as a blocker in
the same change that writes the issue. On 2026-08-19 that rule was broken three
times in one day, by sessions that had read it in the same sitting. A prompt does
not work. So the four placement questions -- parent, board position, what blocks
this, what this blocks -- are now flags, each of them REQUIRED, each with an
explicit way to say "none". A missing answer is an error that names the flag. It
is never a silent default, because a silent default is exactly what produced the
16 unrecorded constraints the 2026-08-19 ordering audit found.

Separately, a truncated board listing hid #164 well enough that a session filed
#176 as a duplicate. So the tool prints the board neighbourhood and any
near-duplicate titles and makes a human say yes before it creates anything, and
it treats a truncated board as fatal rather than as a short board.

HOW THESE TESTS AVOID THE REAL BOARD
------------------------------------
Every test runs `file_issue.sh` as a subprocess with a fake `gh` first on PATH.
The fake logs every argv it is given and replies from a canned response table.
No test reaches github.com. The refusal tests do not even get that far -- the
argument gate runs before the first network call, which is the point of it.

Run:  python3 tests/test_file_issue_gating.py
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
BOARD_SH = REPO / "board.sh"

# The Photos-shaped config -- read from the actual shipped example, not a
# hand-copied literal, so these tests prove the example.json itself drives
# the same behavior the old hardcoded script did (U3's first scenario: "a
# Photos-shaped config drives identical behavior to before").
with open(REPO / "config.example.json", encoding="utf-8") as _fh:
    PHOTOS_CONFIG = json.load(_fh)

# The Pluckd-shaped config -- a distinct vocabulary (work/bug/decision/
# plan-parent, no your-run, project board #1, no Design-line requirement),
# proving the schema is not over-fit to Photos' three shapes.
with open(TESTS / "fixtures" / "pluckd.config.json", encoding="utf-8") as _fh:
    PLUCKD_CONFIG = json.load(_fh)
FILE_ISSUE = REPO / "file_issue.sh"

PLAN_DESIGN = (
    "**Design:** [U2 of the finish-library-consolidation plan]"
    "(https://github.com/jffriend/photo-consolidation/blob/main/docs/plans/"
    "2026-08-05-001-feat-finish-library-consolidation-plan.md#u2-build-the-reconciler)"
)

FAKE_GH = '''#!/usr/bin/env python3
"""A stand-in for `gh`. Logs every argv and answers from a canned table.

A rule may carry `stdout` (the same reply every time) or `stdouts` (a list --
the Nth match of that rule gets the Nth entry, the last entry repeating). The
list form is what lets a test hand back one board before the position write and
a different board after it. `exit` and `exits` work the same way, which is how a
test makes the board read succeed once and then fail.
"""
import json, os, sys
d = os.environ["FAKE_GH_DIR"]
argv = sys.argv[1:]
with open(os.path.join(d, "calls.log"), "a") as fh:
    # One JSON list per line, NOT a delimiter-joined string. An argument may
    # legitimately contain a newline -- the move-record comment body is
    # several lines -- and a joined line would end at the first of them,
    # silently truncating that argument and turning the rest of the body into
    # phantom argv rows that `wrote_nothing()` and friends would then read as
    # real calls. JSON escapes the newline, so the argv round-trips exactly.
    fh.write(json.dumps(argv) + "\\n")
joined = " ".join(argv)
with open(os.path.join(d, "responses.json")) as fh:
    table = json.load(fh)
state_path = os.path.join(d, "state.json")
try:
    with open(state_path) as fh:
        state = json.load(fh)
except OSError:
    state = {}
for i, rule in enumerate(table):
    if rule["match"] in joined:
        n = state.get(str(i), 0)
        state[str(i)] = n + 1
        with open(state_path, "w") as fh:
            json.dump(state, fh)
        if "stdouts" in rule:
            outs = rule["stdouts"]
            sys.stdout.write(outs[min(n, len(outs) - 1)])
        else:
            sys.stdout.write(rule.get("stdout", ""))
        sys.stderr.write(rule.get("stderr", ""))
        if "exits" in rule:
            exs = rule["exits"]
            sys.exit(exs[min(n, len(exs) - 1)])
        sys.exit(rule.get("exit", 0))
sys.stdout.write("{}")
'''


def board_page(rows, has_next=False, cursor="C1"):
    """One page of the shape scripts/board.sh reads."""
    nodes = []
    for num, title in rows:
        nodes.append(
            {
                "fieldValueByName": {"name": "Backlog"},
                "content": {
                    "number": num,
                    "title": title,
                    "state": "OPEN",
                    "blockedBy": {"nodes": []},
                },
            }
        )
    return {
        "data": {
            "user": {
                "projectV2": {
                    "items": {
                        "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                        "nodes": nodes,
                    }
                }
            }
        }
    }


DEFAULT_BOARD = [
    (101, "First thing on the board"),
    (102, "Second thing"),
    (103, "Third thing"),
    (104, "Fourth thing"),
    (105, "Fifth thing"),
    (106, "Sixth thing"),
    (164, "Run: re-sort the library into YYYY/MM once the dates are final"),
    (107, "Eighth thing"),
]


GH_VERSION_LINE = "gh version 2.98.0 (2026-08-20)\n"

# The three flags U1's write path uses, as `gh issue create --help` prints them.
CREATE_FLAG_LINES = (
    "      --parent number        Add this issue to a parent issue\n"
    "      --blocked-by numbers   Mark this issue as blocked by other issues\n"
    "      --blocking numbers     Mark this issue as blocking other issues\n"
)


def create_help(flag_lines=CREATE_FLAG_LINES):
    """`gh issue create --help`, shaped like the real one.

    The EXAMPLES section names all three flags on purpose. The real help does
    too -- `--parent` appears three times in it -- which is why the probe has
    to anchor to the FLAGS block. A probe that grepped the whole text would
    pass on a `gh` that has none of the flags.
    """
    return (
        "Create an issue on GitHub.\n"
        "\n"
        "USAGE\n"
        "  gh issue create [flags]\n"
        "\n"
        "FLAGS\n"
        "  -a, --assignee login   Assign people by their login\n"
        "  -b, --body string      Supply a body\n"
        + flag_lines
        + "  -w, --web              Open the browser to create an issue\n"
        "\n"
        "INHERITED FLAGS\n"
        "      --repo [HOST/]OWNER/REPO   Select another repository\n"
        "\n"
        "EXAMPLES\n"
        "  $ gh issue create --parent 123 --blocked-by 4 --blocking 5\n"
    )


# The six flags U2's adopt write path uses, as `gh issue edit --help` prints them.
EDIT_FLAG_LINES = (
    "      --parent number              Add this issue to a parent issue\n"
    "      --remove-parent              Remove the parent of this issue\n"
    "      --add-blocked-by numbers     Mark this issue as blocked by other issues\n"
    "      --remove-blocked-by numbers  Remove blocked-by relationships\n"
    "      --add-blocking numbers       Mark this issue as blocking other issues\n"
    "      --remove-blocking numbers    Remove blocking relationships\n"
)


def edit_help(flag_lines=EDIT_FLAG_LINES):
    """`gh issue edit --help`, shaped like the real one.

    Adopt mode swaps this sub-command into the probe's needed-flags table, so
    a `gh` whose `issue edit` lacks the relationship flags must refuse an adopt
    exactly as a `gh` whose `issue create` lacks them refuses a create.
    """
    return (
        "Edit an issue on GitHub.\n"
        "\n"
        "USAGE\n"
        "  gh issue edit {<numbers> | <urls>} [flags]\n"
        "\n"
        "FLAGS\n"
        "      --add-label names      Add labels by name\n"
        "  -b, --body string          Set the new body\n"
        + flag_lines
        + "  -t, --title string     Set the new title\n"
        "\n"
        "INHERITED FLAGS\n"
        "      --repo [HOST/]OWNER/REPO   Select another repository\n"
        "\n"
        "EXAMPLES\n"
        "  $ gh issue edit 23 --parent 1 --add-blocked-by 4 --add-blocking 5\n"
    )


# The field list bare `gh issue view --json` prints -- to STDERR, exiting 1.
JSON_FIELDS = (
    "assignees", "author", "blockedBy", "blocking", "body", "closed",
    "number", "parent", "state", "title", "url",
)


def json_field_list(fields=JSON_FIELDS):
    return (
        "Specify one or more comma-separated fields for `--json`:\n"
        + "".join("  %s\n" % f for f in fields)
    )


def probe_rules(version_line=GH_VERSION_LINE, help_text=None, help_exit=0,
                fields=JSON_FIELDS, fields_text=None, fields_exit=1,
                flag_lines=None, edit_flag_lines=None, edit_help_text=None,
                edit_help_exit=0):
    """The fake's answers to the capability probe.

    These belong in the BASE table, not in `create_responses()`: most gate
    tests build a `Harness` with no response table at all, and a probe rule
    that only existed in the create table would leave them falling through to
    the fake's `{}` default -- so every one of them would get the probe refusal
    instead of the refusal it asserts.
    """
    if help_text is None:
        help_text = create_help(
            CREATE_FLAG_LINES if flag_lines is None else flag_lines)
    if edit_help_text is None:
        edit_help_text = edit_help(
            EDIT_FLAG_LINES if edit_flag_lines is None else edit_flag_lines)
    if fields_text is None:
        fields_text = json_field_list(fields) if fields else ""
    return [
        {"match": "--version", "stdout": version_line},
        {"match": "issue create --help", "stdout": help_text, "exit": help_exit},
        # Adopt mode probes `gh issue edit` instead of `gh issue create`.
        {"match": "issue edit --help", "stdout": edit_help_text,
         "exit": edit_help_exit},
        # Bare `gh issue view --json` writes to stderr and exits 1. That
        # non-zero exit is normal and must not read as "undeterminable".
        {"match": "issue view --json", "stderr": fields_text, "exit": fields_exit},
    ]


class Harness:
    """A temp dir holding a body file, a fake `gh`, and its response table."""

    def __init__(self, body, boards=None, responses=None, probe=None,
                 board_exits=None, config=None):
        self.dir = Path(tempfile.mkdtemp(prefix="file_issue_test_"))
        self.body_file = self.dir / "body.md"
        self.body_file.write_text(body)
        self.config = PHOTOS_CONFIG if config is None else config
        self.config_path = self.dir / "config.json"
        self.config_path.write_text(json.dumps(self.config))
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        self.calls_log = self.dir / "calls.log"
        self.calls_log.write_text("")
        boards = [DEFAULT_BOARD] if boards is None else boards
        pages = [json.dumps(board_page(b)) for b in boards]
        titles = json.dumps([{"number": n, "title": t} for n, t in boards[0]])
        board_rule = {"match": "items(first: 100", "stdouts": pages}
        if board_exits is not None:
            board_rule["exits"] = list(board_exits)
        table = [
            board_rule,
            {"match": "issue list", "stdout": titles},
        ]
        table.extend(probe_rules() if probe is None else probe)
        table.extend(responses or [])
        (self.dir / "responses.json").write_text(json.dumps(table))

    def run(self, *args, stdin="", path=None, env=None):
        """Run the script. `env` overrides the environment; a value of None
        DELETES that variable, which is how a test asks for the script's own
        production default instead of the test default set here.

        The read-back backoff is defaulted to ZERO seconds so the suite
        exercises the retry path without really sleeping. Exactly one test
        deletes it, to prove the production default is non-zero.

        --config is injected automatically, pointing at this harness's own
        config file, unless the caller already put --config in `args` --
        which is how a test exercises a bad or missing config on purpose.
        """
        args = list(args)
        if "--config" not in args:
            args = ["--config", str(self.config_path)] + args
        e = dict(os.environ)
        e["PATH"] = path if path is not None else f"{self.bin}:{e['PATH']}"
        e["FAKE_GH_DIR"] = str(self.dir)
        e["FILE_ISSUE_READBACK_DELAY"] = "0"
        for k, v in (env or {}).items():
            if v is None:
                e.pop(k, None)
            else:
                e[k] = str(v)
        env = e
        return subprocess.run(
            ["bash", str(FILE_ISSUE), *args],
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def calls(self):
        """Every argv the fake `gh` was invoked with, one list per call.

        Each logged line is a JSON list, so an argument carrying an embedded
        newline comes back whole instead of being cut at that newline and its
        tail read as further calls. The shape returned is unchanged -- a list
        of argv lists -- so `called()`, `network_calls()`, `wrote_nothing()`
        and `comment_body()` all read it exactly as before.
        """
        return [
            json.loads(line)
            for line in self.calls_log.read_text().splitlines()
            if line
        ]

    def called(self, *needles):
        """True when one NON-PROBE call carries every needle.

        `--help` calls are skipped. The capability probe runs
        `gh issue create --help`, which otherwise satisfies
        `called("issue", "create")` and would make five "no create happened"
        assertions pass on a probe call instead of a create.
        """
        for call in self.calls():
            joined = " ".join(call)
            if "--help" in call:
                continue
            if all(n in joined for n in needles):
                return True
        return False

    def network_calls(self):
        """Every call that is not part of the offline capability probe."""
        out = []
        for call in self.calls():
            if "--help" in call or call == ["--version"]:
                continue
            if call[:3] == ["issue", "view", "--json"]:
                continue
            out.append(call)
        return out


def full_args(body_file, **over):
    args = {
        "--title": "A brand new distinct piece of work",
        "--body-file": str(body_file),
        "--shape": "work",
        "--blocked-by": "none",
        "--blocks": "none",
    }
    args.update(over)
    out = []
    for k, v in args.items():
        out.append(k)
        if v is not None:
            out.append(v)
    return out


class RequiredFlags(unittest.TestCase):
    """Each of the seven required answers, refused by name when absent."""

    def setUp(self):
        self.h = Harness("**Design:** none\n")

    def _run(self, args):
        r = self.h.run(*args)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(
            self.h.called("issue", "create", "--title"),
            "refusal must happen before any create",
        )
        return r.stdout + r.stderr

    def test_missing_title(self):
        args = full_args(self.h.body_file)
        args = [a for a in args if a not in ("--title", "A brand new distinct piece of work")]
        out = self._run([*args, "--no-parent", "--top"])
        self.assertIn("--title", out)

    def test_missing_body_file(self):
        out = self._run(
            ["--title", "T", "--shape", "work", "--no-parent", "--top",
             "--blocked-by", "none", "--blocks", "none"]
        )
        self.assertIn("--body-file", out)

    def test_missing_shape(self):
        out = self._run(
            ["--title", "T", "--body-file", str(self.h.body_file), "--no-parent",
             "--top", "--blocked-by", "none", "--blocks", "none"]
        )
        self.assertIn("--shape", out)

    def test_unknown_shape(self):
        out = self._run(
            ["--title", "T", "--body-file", str(self.h.body_file), "--shape", "task",
             "--no-parent", "--top", "--blocked-by", "none", "--blocks", "none"]
        )
        self.assertIn("--shape", out)
        self.assertIn("investigation", out)

    def test_missing_parent_answer(self):
        out = self._run([*full_args(self.h.body_file), "--top"])
        self.assertIn("--parent", out)
        self.assertIn("--no-parent", out)

    def test_missing_position_answer(self):
        out = self._run([*full_args(self.h.body_file), "--no-parent"])
        self.assertIn("--after", out)
        self.assertIn("--top", out)

    def test_missing_blocked_by_answer(self):
        args = ["--title", "T", "--body-file", str(self.h.body_file), "--shape",
                "work", "--no-parent", "--top", "--blocks", "none"]
        out = self._run(args)
        self.assertIn("--blocked-by", out)

    def test_missing_blocks_answer(self):
        args = ["--title", "T", "--body-file", str(self.h.body_file), "--shape",
                "work", "--no-parent", "--top", "--blocked-by", "none"]
        out = self._run(args)
        self.assertIn("--blocks", out)

    def test_parent_and_no_parent_together_is_refused(self):
        out = self._run([*full_args(self.h.body_file), "--parent", "55", "--no-parent",
                         "--top"])
        self.assertIn("--parent", out)

    def test_after_and_top_together_is_refused(self):
        out = self._run([*full_args(self.h.body_file), "--no-parent", "--after", "101",
                         "--top"])
        self.assertIn("--top", out)


class PhotosConfigShapes(unittest.TestCase):
    """U1: bug and investigation are wired to their own labels under this
    repo's own shipped config (PHOTOS_CONFIG), and work is unchanged."""

    def _create_call_for(self, shape, title):
        board_after = [
            (200, title),
            (101, "First thing on the board"),
            (102, "Second thing"),
        ]
        h = Harness("**Design:** none\n", boards=[PRE_BOARD, board_after],
                    responses=create_responses([], []))
        r = h.run(
            "--title", title, "--body-file", str(h.body_file),
            "--shape", shape, "--no-parent", "--top",
            "--blocked-by", "none", "--blocks", "none",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        create_call = create_argv(h)
        self.assertIsNotNone(create_call)
        return create_call

    def test_bug_shape_carries_the_bug_label(self):
        call = self._create_call_for("bug", "A brand new bug")
        self.assertIn("bug", call)

    def test_investigation_shape_carries_the_investigation_label(self):
        call = self._create_call_for("investigation", "A brand new investigation")
        self.assertIn("investigation", call)

    def test_work_shape_still_carries_the_work_label(self):
        call = self._create_call_for("work", "A brand new distinct piece of work")
        self.assertIn("work", call)


class ParentingRule(unittest.TestCase):
    """
    A parent is REQUIRED when the issue is plan-derived and a judgement call
    otherwise. Plan-derived is detected mechanically: the `Design:` field links
    into `docs/plans/`.
    """

    def test_plan_derived_body_refuses_no_parent_and_quotes_the_design_line(self):
        h = Harness("Some body.\n\n" + PLAN_DESIGN + "\n")
        r = h.run(*full_args(h.body_file), "--no-parent", "--top")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("--parent", out)
        self.assertIn("docs/plans/", out)
        self.assertFalse(h.called("issue", "create", "--title"))

    def test_plan_derived_body_accepts_a_parent(self):
        h = Harness("Some body.\n\n" + PLAN_DESIGN + "\n")
        r = h.run(*full_args(h.body_file), "--parent", "55", "--top", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_design_none_accepts_no_parent(self):
        h = Harness("Some body.\n\n**Design:** none\n")
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_design_none_also_accepts_a_parent(self):
        h = Harness("Some body.\n\n**Design:** none\n")
        r = h.run(*full_args(h.body_file), "--parent", "55", "--top", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class NeighbourCheck(unittest.TestCase):
    """What the operator sees before saying yes."""

    def test_dry_run_shows_neighbours_and_creates_nothing(self):
        h = Harness("**Design:** none\n")
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "104", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("103", r.stdout)
        self.assertIn("104", r.stdout)
        self.assertIn("105", r.stdout)
        self.assertFalse(h.called("issue", "create", "--title"))

    def test_near_duplicate_title_is_reported_prominently(self):
        h = Harness("**Design:** none\n")
        r = h.run(
            "--title", "Re-sort the library into YYYY/MM folders",
            "--body-file", str(h.body_file), "--shape", "work",
            "--no-parent", "--top", "--blocked-by", "none", "--blocks", "none",
            "--dry-run",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("POSSIBLE DUPLICATES", r.stdout)
        self.assertIn("164", r.stdout)

    def test_a_truncated_board_is_fatal(self):
        # board.sh exits non-zero when rows != distinct. A truncated board is what
        # hid #164 and produced the duplicate, so it must stop the run.
        dupe = DEFAULT_BOARD + [DEFAULT_BOARD[0]]
        h = Harness("**Design:** none\n", boards=[dupe])
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("board", (r.stdout + r.stderr).lower())
        self.assertFalse(h.called("issue", "create", "--title"))



NEW_URL = "https://github.com/jffriend/photo-consolidation/issues/200\n"


PRE_BOARD = [
    (101, "First thing on the board"),
    (102, "Second thing"),
    (103, "Third thing"),
]


def create_responses(blocked_by, blocking, parent=None, corroborate=""):
    """Canned replies for the create-and-read-back half.

    The read-back rule keys on `--json parent,blockedBy,blocking`, never on a
    bare `parent`/`blocked-by`/`blocking` token: those words now appear in the
    `gh issue create` argv too.

    `corroborate` is the item id the single-issue project-items read returns
    when the board LISTING does not show the issue. Empty by default -- the
    corroborating read agrees the issue is not there -- so every existing
    assertion here is unchanged. Its rule must come BEFORE the generic
    `projectItems` rule, whose substring the corroborating call also carries.
    """
    return [
        {"match": "issue create", "stdout": NEW_URL},
        {"match": "item-add", "stdout": json.dumps({"id": "PVTI_new"})},
        {"match": "boardMembershipCorroboration",
         "stdout": (corroborate + "\n") if corroborate else ""},
        {"match": "projectItems", "stdout": "PVTI_after\n"},
        {"match": "updateProjectV2ItemPosition", "stdout": json.dumps({"data": {}})},
        {"match": "--json parent,blockedBy,blocking", "stdout": json.dumps({
            "parent": ({"number": int(parent)} if parent else None),
            "blockedBy": {
                "nodes": [{"number": n} for n in blocked_by],
                "totalCount": len(blocked_by),
            },
            "blocking": {
                "nodes": [{"number": n} for n in blocking],
                "totalCount": len(blocking),
            },
        })},
    ]


DUPE_TITLE = "Re-sort the library into YYYY/MM folders"
DUPE_PRE_BOARD = PRE_BOARD + [
    (164, "Run: re-sort the library into YYYY/MM once the dates are final"),
]
DUPE_POST_BOARD = [
    (101, "First thing on the board"),
    (200, DUPE_TITLE),
    (102, "Second thing"),
    (103, "Third thing"),
    (164, "Run: re-sort the library into YYYY/MM once the dates are final"),
]


class NoPromptOneRun(unittest.TestCase):
    """
    The engine never asks for confirmation. A create run with no possible
    duplicates writes in one run; one with possible duplicates stops before
    writing, with exit code 3, unless --file-anyway is given.
    """

    def _harness(self, pre=PRE_BOARD, post=None):
        post = post or [
            (101, "First thing on the board"),
            (200, "A brand new distinct piece of work"),
            (102, "Second thing"),
            (103, "Third thing"),
        ]
        return Harness("**Design:** none\n", boards=[pre, post],
                       responses=create_responses([], []))

    def test_no_matches_files_in_one_run_without_stdin(self):
        # Covers AE1.
        h = self._harness()
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("POSSIBLE DUPLICATES: none found", r.stdout)
        self.assertIn("READ-BACK", r.stdout)
        self.assertTrue(h.called("issue", "create", "--title"))

    def test_stdin_is_ignored(self):
        # An `n` that the old prompt would have read as "no" changes nothing.
        h = self._harness()
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101",
                  stdin="n\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(h.called("issue", "create", "--title"))

    def test_possible_duplicates_stop_before_any_write_with_exit_3(self):
        h = self._harness(DUPE_PRE_BOARD, DUPE_POST_BOARD)
        r = h.run(*full_args(h.body_file, **{"--title": DUPE_TITLE}),
                  "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("POSSIBLE DUPLICATES", r.stdout)
        self.assertIn("164", r.stdout)
        self.assertIn("ABOUT TO CREATE", r.stdout)
        self.assertIn("Nothing was created", r.stderr)
        self.assertIn("--file-anyway", r.stderr)
        self.assertFalse(h.called("issue", "create", "--title"))
        self.assertFalse(h.called("item-add"))

    def test_file_anyway_files_past_possible_duplicates(self):
        h = self._harness(DUPE_PRE_BOARD, DUPE_POST_BOARD)
        r = h.run(*full_args(h.body_file, **{"--title": DUPE_TITLE}),
                  "--no-parent", "--after", "101", "--file-anyway")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("164", r.stdout)
        self.assertIn("READ-BACK", r.stdout)
        self.assertTrue(h.called("issue", "create", "--title"))

    def test_dry_run_with_possible_duplicates_exits_0_and_writes_nothing(self):
        h = self._harness(DUPE_PRE_BOARD, DUPE_POST_BOARD)
        r = h.run(*full_args(h.body_file, **{"--title": DUPE_TITLE}),
                  "--no-parent", "--after", "101", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("164", r.stdout)
        self.assertFalse(h.called("issue", "create", "--title"))


class ReadBack(unittest.TestCase):
    """
    Never report success from an exit code. Every relationship is read back and
    compared, and a mismatch says which one and what state the issue was left in.
    """

    def _harness(self, board_after=None, blocked_by=(), blocking=(), parent=None):
        if board_after is None:
            board_after = [
                (101, "First thing on the board"),
                (200, "A brand new distinct piece of work"),
                (102, "Second thing"),
                (103, "Third thing"),
            ]
        return Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, board_after],
            responses=create_responses(list(blocked_by), list(blocking), parent),
        )

    def test_happy_path_all_relationships_match(self):
        h = self._harness()
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(h.called("issue", "create", "--title"))

    def test_happy_path_with_a_parent_and_both_directions(self):
        """All five comparisons on NON-EMPTY answers.

        Without this the suite only ever compares empty against empty, and an
        unmatched fake rule falling through to `{}` would pass it.
        """
        h = self._harness(blocked_by=[122], blocking=[63], parent="55")
        r = h.run(
            "--title", "A brand new distinct piece of work",
            "--body-file", str(h.body_file), "--shape", "work",
            "--parent", "55", "--after", "101",
            "--blocked-by", "122", "--blocks", "63",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertIn("board membership   ok", out)
        self.assertIn("board position     ok", out)
        self.assertIn("parent             ok (#55)", out)
        self.assertIn("blocked-by         ok (122)", out)
        self.assertIn("blocks             ok (63)", out)

    def test_blocked_by_mismatch_fails_loudly(self):
        # Requested --blocked-by 122, but the read-back comes back empty.
        h = self._harness(blocked_by=[])
        r = h.run(
            "--title", "A brand new distinct piece of work",
            "--body-file", str(h.body_file), "--shape", "work",
            "--no-parent", "--after", "101",
            "--blocked-by", "122", "--blocks", "none",
        )
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("blocked-by", out.lower())
        self.assertIn("200", out, "must name the issue that was left half-wired")

    def test_blocking_mismatch_fails_loudly(self):
        h = self._harness(blocking=[])
        r = h.run(
            "--title", "A brand new distinct piece of work",
            "--body-file", str(h.body_file), "--shape", "work",
            "--no-parent", "--after", "101",
            "--blocked-by", "none", "--blocks", "63",
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("blocks", (r.stdout + r.stderr).lower())

    def test_parent_mismatch_fails_loudly(self):
        h = self._harness(parent=None)  # asked for #55, server says none
        r = h.run(
            "--title", "A brand new distinct piece of work",
            "--body-file", str(h.body_file), "--shape", "work",
            "--parent", "55", "--after", "101",
            "--blocked-by", "none", "--blocks", "none",
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("parent", (r.stdout + r.stderr).lower())

    def test_board_position_mismatch_fails_loudly(self):
        # Asked for --after 101; the board reads back with 102 in front instead.
        wrong = [
            (101, "First thing on the board"),
            (102, "Second thing"),
            (200, "A brand new distinct piece of work"),
        ]
        h = self._harness(board_after=wrong)
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("position", (r.stdout + r.stderr).lower())

    def test_a_board_that_auto_adds_new_issues_does_not_half_wire_the_create(self):
        # A board with GitHub's auto-add workflow puts the new issue on it
        # before item-add runs, and item-add then refuses with "Content
        # already exists in this project". pluckd #504 and #508 both came back
        # HALF-WIRED this way. The id must come from the by-number lookup.
        responses = create_responses([], [])
        responses[1] = {"match": "item-add", "exit": 1, "stderr":
                        "GraphQL: Content already exists in this project "
                        "(addProjectV2ItemById)\n"}
        responses.insert(2, {"match": "boardItemByIssueNumber",
                             "stdout": "PVTI_auto_added\n"})
        h = Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, [
                (101, "First thing on the board"),
                (200, "A brand new distinct piece of work"),
                (102, "Second thing"),
                (103, "Third thing"),
            ]],
            responses=responses,
        )
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        positions = [c for c in h.calls()
                     if any("updateProjectV2ItemPosition" in a for a in c)]
        self.assertEqual(1, len(positions), positions)
        self.assertIn("PVTI_auto_added", " ".join(positions[0]))
        self.assertIn("board position     ok (after #101)", r.stdout)

    def test_missing_from_the_board_fails_loudly(self):
        h = self._harness(board_after=PRE_BOARD)
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("board", (r.stdout + r.stderr).lower())


def path_without_gh():
    """A PATH with every real command still resolvable except `gh`.

    PATH hides whole directories, not individual files, so a hardcoded
    directory list (e.g. "/usr/bin:/bin") only hides gh on a machine where
    gh happens to live outside those dirs. GitHub-hosted Ubuntu runners
    preinstall gh at /usr/bin/gh, alongside jq, python3, and the other
    coreutils this script also needs -- so excluding that directory to hide
    gh would break everything else it resolves there too. Forward every
    other command through one synthetic directory instead.
    """
    forward_dir = Path(tempfile.mkdtemp(prefix="file_issue_test_nogh_"))
    seen = set()
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        try:
            names = os.listdir(entry)
        except OSError:
            continue
        for name in names:
            if name == "gh" or name in seen:
                continue
            src = Path(entry) / name
            if not os.access(src, os.X_OK) or src.is_dir():
                continue
            try:
                (forward_dir / name).symlink_to(src)
            except OSError:
                continue
            seen.add(name)
    return str(forward_dir)


class CapabilityProbe(unittest.TestCase):
    """
    `gh` 2.94.0 replaced the node-id lookups this script used to hand-roll with
    native flags. The script now uses those flags, so it must establish they
    exist BEFORE it writes anything -- discovering an absent flag mid-write is
    what leaves a half-wired issue behind.

    The probe resolves to four states, never a boolean: not installed, absent,
    undeterminable, present. A probe that could not run is not a probe that
    passed.
    """

    ARGS_TAIL = ("--no-parent", "--top", "--dry-run")

    def _run(self, probe, path=None):
        h = Harness("**Design:** none\n", probe=probe)
        r = h.run(*full_args(h.body_file), *self.ARGS_TAIL, path=path)
        return h, r, r.stdout + r.stderr

    def test_help_missing_the_flags_refuses_before_any_network_call(self):
        h, r, out = self._run(probe_rules(flag_lines=""))
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("MISSING CAPABILITY", out)
        for flag in ("--parent", "--blocked-by", "--blocking"):
            self.assertIn(flag, out, "must name which flag is missing")
        self.assertIn("2.98.0", out, "must report the installed version")
        self.assertIn("brew upgrade gh", out, "must name the upgrade action")
        self.assertEqual([], h.network_calls(),
                         "the refusal must land before any network call")

    def test_help_with_all_the_flags_proceeds(self):
        h, r, out = self._run(probe_rules())
        self.assertEqual(r.returncode, 0, out)
        self.assertNotIn("MISSING CAPABILITY", out)
        self.assertNotIn("UNDETERMINABLE CAPABILITY", out)
        self.assertIn("2.98.0", r.stdout)

    def test_help_unreadable_refuses_as_undeterminable(self):
        h, r, out = self._run(probe_rules(help_text="", help_exit=1))
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("UNDETERMINABLE CAPABILITY", out)
        self.assertIn("gh issue create --help", out,
                      "must print the invocation whose output could not be read")
        self.assertIn("2.98.0", out, "must print the version or its sentinel")
        self.assertIn("gh issue create --help", out)
        self.assertEqual([], h.network_calls())

    def test_undeterminable_wording_is_distinct_from_absent_wording(self):
        _, _, absent = self._run(probe_rules(flag_lines=""))
        _, _, undet = self._run(probe_rules(help_text="", help_exit=1))
        self.assertIn("MISSING CAPABILITY", absent)
        self.assertNotIn("UNDETERMINABLE CAPABILITY", absent)
        self.assertIn("UNDETERMINABLE CAPABILITY", undet)
        self.assertNotIn("MISSING CAPABILITY", undet)

    def test_examples_naming_the_flags_do_not_satisfy_the_probe(self):
        # The real `gh issue create --help` names `--parent` three times, twice
        # outside the FLAGS block. Anchoring is what makes this refuse.
        h, r, out = self._run(probe_rules(flag_lines=""))
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("MISSING CAPABILITY", out)

    def test_unparseable_version_still_proceeds_and_prints_the_sentinel(self):
        h, r, out = self._run(probe_rules(version_line="gh, but which one?\n"))
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("unknown", r.stdout,
                      "the sentinel prints where the version would go")

    def test_missing_json_field_refuses_with_the_absent_wording(self):
        fields = tuple(f for f in JSON_FIELDS if f != "blockedBy")
        h, r, out = self._run(probe_rules(fields=fields))
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("MISSING CAPABILITY", out)
        self.assertIn("blockedBy", out)
        self.assertEqual([], h.network_calls())

    def test_unreadable_json_field_list_is_undeterminable(self):
        h, r, out = self._run(probe_rules(fields_text="", fields_exit=1))
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("UNDETERMINABLE CAPABILITY", out)
        self.assertIn("gh issue view --json", out)

    def test_a_nonzero_exit_from_the_field_list_is_not_undeterminable(self):
        # Bare `gh issue view --json` exits 1 on a healthy gh. Reading that as
        # a failure would refuse every run.
        h, r, out = self._run(probe_rules(fields_exit=1))
        self.assertEqual(r.returncode, 0, out)

    def test_gh_absent_from_path_refuses_saying_so(self):
        h, r, out = self._run(probe_rules(), path=path_without_gh())
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("REFUSED: gh is not on PATH", out)
        self.assertNotIn("MISSING CAPABILITY", out)
        self.assertNotIn("UNDETERMINABLE CAPABILITY", out)


class NativeWritePath(unittest.TestCase):
    """
    Parent and both blocking directions are set by the same call that creates
    the issue, through gh's own flags. No node id is resolved anywhere.
    """

    def _create_argv(self, h):
        for call in h.calls():
            if "--help" in call:
                continue
            if call[:2] == ["issue", "create"]:
                return call
        return None

    def test_create_call_carries_all_three_flags(self):
        board_after = [
            (101, "First thing on the board"),
            (200, "A brand new distinct piece of work"),
            (102, "Second thing"),
        ]
        h = Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, board_after],
            responses=create_responses([122], [63], "55"),
        )
        r = h.run(
            "--title", "A brand new distinct piece of work",
            "--body-file", str(h.body_file), "--shape", "work",
            "--parent", "55", "--after", "101",
            "--blocked-by", "122", "--blocks", "63",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = self._create_argv(h)
        self.assertIsNotNone(argv, "a real create must have been issued")
        self.assertIn("--parent", argv)
        self.assertEqual("55", argv[argv.index("--parent") + 1])
        self.assertIn("--blocked-by", argv)
        self.assertEqual("122", argv[argv.index("--blocked-by") + 1])
        self.assertIn("--blocking", argv)
        self.assertEqual("63", argv[argv.index("--blocking") + 1])
        self.assertFalse(h.called("sub_issues"))
        self.assertFalse(h.called("dependencies"))

    def test_none_answers_omit_the_flags_rather_than_passing_them_empty(self):
        board_after = [
            (101, "First thing on the board"),
            (200, "A brand new distinct piece of work"),
            (102, "Second thing"),
        ]
        h = Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, board_after],
            responses=create_responses([], [], None),
        )
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = self._create_argv(h)
        self.assertIsNotNone(argv)
        for flag in ("--parent", "--blocked-by", "--blocking"):
            self.assertNotIn(flag, argv,
                             "an unanswered relationship is an OMITTED flag, "
                             "never an empty one")

    def test_no_call_resolves_an_issue_node_id(self):
        board_after = [
            (101, "First thing on the board"),
            (200, "A brand new distinct piece of work"),
            (102, "Second thing"),
        ]
        h = Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, board_after],
            responses=create_responses([122], [63], "55"),
        )
        h.run(
            "--title", "A brand new distinct piece of work",
            "--body-file", str(h.body_file), "--shape", "work",
            "--parent", "55", "--after", "101",
            "--blocked-by", "122", "--blocks", "63",
        )
        for call in h.calls():
            joined = " ".join(call)
            self.assertNotIn("--jq .id", joined)
            self.assertNotIn("sub_issues", joined)
            self.assertNotIn("dependencies/", joined)

    def test_the_relationship_read_back_is_one_call(self):
        board_after = [
            (101, "First thing on the board"),
            (200, "A brand new distinct piece of work"),
            (102, "Second thing"),
        ]
        h = Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, board_after],
            responses=create_responses([122], [63], "55"),
        )
        r = h.run(
            "--title", "A brand new distinct piece of work",
            "--body-file", str(h.body_file), "--shape", "work",
            "--parent", "55", "--after", "101",
            "--blocked-by", "122", "--blocks", "63",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        views = [c for c in h.calls()
                 if c[:2] == ["issue", "view"] and "--help" not in c
                 and c[2:3] != ["--json"]]
        self.assertEqual(1, len(views), views)
        self.assertIn("--json", views[0])
        self.assertIn("parent,blockedBy,blocking", views[0])


# ---------------------------------------------------------------------------
# ADOPT MODE
#
# Wiring an issue that ALREADY EXISTS goes through the same tool, the same four
# required placement answers and the same read-back as creating one. What it
# must NOT do is reconcile: an existing link that contradicts an answer stops
# the run and prints the command that clears it.
# ---------------------------------------------------------------------------

ADOPT_NUM = "200"
ADOPT_URL = "https://github.com/jffriend/photo-consolidation/issues/200"

ADOPT_PRE_BOARD = [
    (101, "First thing on the board"),
    (102, "Second thing"),
    (200, "An existing issue being wired"),
]
ADOPT_POST_BOARD = [
    (101, "First thing on the board"),
    (200, "An existing issue being wired"),
    (102, "Second thing"),
]


def rel_json(parent=None, blocked_by=(), blocking=()):
    return {
        "parent": ({"number": int(parent)} if parent else None),
        "blockedBy": {"nodes": [{"number": int(n)} for n in blocked_by],
                      "totalCount": len(blocked_by)},
        "blocking": {"nodes": [{"number": int(n)} for n in blocking],
                     "totalCount": len(blocking)},
    }


def adopt_responses(pre_parent=None, pre_blocked=(), pre_blocking=(),
                    post_parent=None, post_blocked=(), post_blocking=(),
                    state="OPEN", body="**Design:** none\n",
                    view_exit=0, view_stdout=None,
                    edit_exit=0, item_by_number="PVTI_adopt",
                    corroborate=""):
    """Canned replies for an adopt run.

    The PRE-FETCH and the READ-BACK are two different `gh issue view` calls and
    they must be answerable differently -- the pre-fetch has to show no
    conflicting links or the KD2 refusal fires, while the read-back has to show
    the links just written. They are told apart by their `--json` field lists,
    and the pre-fetch rule comes FIRST because its field list contains the
    read-back's as a substring.
    """
    pre = dict(rel_json(pre_parent, pre_blocked, pre_blocking))
    pre["state"] = state
    pre["body"] = body
    if view_stdout is None:
        view_stdout = json.dumps(pre)
    return [
        {"match": "--json state,body,parent,blockedBy,blocking",
         "stdout": view_stdout, "exit": view_exit},
        # The by-issue-number item lookup carries a marker literal in its
        # GraphQL text. Without it the generic `projectItems` rule below would
        # hand adopt the `--after` item's id and the test would prove nothing.
        {"match": "boardItemByIssueNumber",
         "stdout": (item_by_number + "\n") if item_by_number else ""},
        # The read-back's corroborating single-issue read. Same store, its own
        # marker, so it is answerable separately from both lookups above.
        {"match": "boardMembershipCorroboration",
         "stdout": (corroborate + "\n") if corroborate else ""},
        {"match": "projectItems", "stdout": "PVTI_after\n"},
        {"match": "item-add", "stdout": json.dumps({"id": "PVTI_from_item_add"})},
        {"match": "issue edit", "stdout": "", "exit": edit_exit},
        {"match": "updateProjectV2ItemPosition", "stdout": json.dumps({"data": {}})},
        {"match": "--json parent,blockedBy,blocking",
         "stdout": json.dumps(rel_json(post_parent, post_blocked, post_blocking))},
    ]


def adopt_harness(boards=None, **kw):
    if boards is None:
        boards = [ADOPT_PRE_BOARD, ADOPT_POST_BOARD]
    return Harness("**Design:** none\n", boards=boards,
                   responses=adopt_responses(**kw))


def adopt_args(num=ADOPT_NUM, **over):
    args = {"--adopt": num, "--blocked-by": "none", "--blocks": "none"}
    args.update(over)
    out = []
    for k, v in args.items():
        out.append(k)
        if v is not None:
            out.append(v)
    return out


def edit_argv(h):
    """The one real `gh issue edit` argv, or None."""
    for call in h.calls():
        if "--help" in call:
            continue
        if call[:2] == ["issue", "edit"]:
            return call
    return None


def create_argv(h):
    for call in h.calls():
        if "--help" in call:
            continue
        if call[:2] == ["issue", "create"]:
            return call
    return None


def wrote_nothing(h):
    """True when no call in this run changed anything on the server."""
    for call in h.calls():
        if "--help" in call:
            continue
        joined = " ".join(call)
        if call[:2] in (["issue", "edit"], ["issue", "create"]):
            return False
        if "item-add" in joined or "updateProjectV2ItemPosition" in joined:
            return False
    return True


class AdoptGate(unittest.TestCase):
    """The same four required answers, and the offline stage of the gate."""

    def test_missing_parent_answer(self):
        h = adopt_harness()
        r = h.run(*adopt_args(), "--top")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("--parent", out)
        self.assertIn("--no-parent", out)
        self.assertTrue(wrote_nothing(h))

    def test_missing_position_answer(self):
        h = adopt_harness()
        r = h.run(*adopt_args(), "--no-parent")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("--after", out)
        self.assertIn("--top", out)
        self.assertTrue(wrote_nothing(h))

    def test_missing_blocked_by_answer(self):
        h = adopt_harness()
        r = h.run("--adopt", ADOPT_NUM, "--no-parent", "--top", "--blocks", "none")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--blocked-by", r.stdout + r.stderr)
        self.assertTrue(wrote_nothing(h))

    def test_missing_blocks_answer(self):
        h = adopt_harness()
        r = h.run("--adopt", ADOPT_NUM, "--no-parent", "--top",
                  "--blocked-by", "none")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--blocks", r.stdout + r.stderr)
        self.assertTrue(wrote_nothing(h))

    def test_adopt_with_create_inputs_is_refused_naming_the_conflict(self):
        for flag, value in (("--title", "T"),
                            ("--body-file", "/tmp/nope.md"),
                            ("--shape", "work")):
            with self.subTest(flag=flag):
                h = adopt_harness()
                r = h.run(*adopt_args(), "--no-parent", "--top", flag, value)
                self.assertNotEqual(r.returncode, 0)
                out = r.stdout + r.stderr
                self.assertIn("--adopt", out)
                self.assertIn(flag, out)
                self.assertIn("contradictory", out)
                self.assertTrue(wrote_nothing(h))

    def test_a_malformed_issue_number_is_refused_offline(self):
        h = adopt_harness()
        r = h.run(*adopt_args(num="two hundred"), "--no-parent", "--top")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--adopt", r.stdout + r.stderr)
        self.assertEqual([], h.network_calls())

    def test_a_nonexistent_issue_refuses_before_any_write(self):
        h = adopt_harness(view_stdout="", view_exit=1)
        r = h.run(*adopt_args(num="999"), "--no-parent", "--top")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("999", r.stdout + r.stderr)
        self.assertTrue(wrote_nothing(h))

    def test_a_closed_issue_refuses_before_any_write(self):
        h = adopt_harness(state="CLOSED")
        r = h.run(*adopt_args(), "--no-parent", "--top")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("CLOSED", out)
        self.assertTrue(wrote_nothing(h))

    def test_a_plan_derived_adopted_body_refuses_no_parent(self):
        h = adopt_harness(body="Some body.\n\n" + PLAN_DESIGN + "\n")
        r = h.run(*adopt_args(), "--no-parent", "--top")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("--parent", out)
        self.assertIn("docs/plans/", out)
        self.assertTrue(wrote_nothing(h))

    def test_dry_run_shows_the_neighbourhood_and_writes_nothing(self):
        h = adopt_harness()
        r = h.run(*adopt_args(), "--no-parent", "--after", "101", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("BOARD NEIGHBOURHOOD", r.stdout)
        self.assertIn("101", r.stdout)
        self.assertIn("Nothing was changed", r.stdout)
        self.assertTrue(wrote_nothing(h))

    def test_file_anyway_is_refused_in_adopt_mode(self):
        # Adopt has no duplicate check, so there is nothing to wave past.
        h = adopt_harness()
        r = h.run(*adopt_args(), "--no-parent", "--after", "101", "--file-anyway")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--file-anyway", r.stdout + r.stderr)
        self.assertTrue(wrote_nothing(h))

    def test_a_gh_whose_issue_edit_lacks_the_flags_refuses_the_adopt(self):
        h = Harness("**Design:** none\n",
                    boards=[ADOPT_PRE_BOARD, ADOPT_POST_BOARD],
                    responses=adopt_responses(),
                    probe=probe_rules(edit_flag_lines=""))
        r = h.run(*adopt_args(), "--no-parent", "--top", "--dry-run")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("MISSING CAPABILITY", out)
        for flag in ("--parent", "--add-blocked-by", "--add-blocking",
                     "--remove-parent", "--remove-blocked-by",
                     "--remove-blocking"):
            self.assertIn(flag, out)
        self.assertEqual([], h.network_calls())


class AdoptContradiction(unittest.TestCase):
    """
    KD2: refuse rather than reconcile, and make every refusal CLEARABLE by
    printing the exact `gh issue edit --remove-*` command.
    """

    def test_an_existing_different_parent_refuses_and_names_the_clearing_command(self):
        h = adopt_harness(pre_parent="77")
        r = h.run(*adopt_args(), "--parent", "55", "--after", "101")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("77", out, "must name what it found")
        self.assertIn("55", out, "must name what was asked for")
        self.assertIn("gh issue edit 200 --repo jffriend/photo-consolidation "
                      "--remove-parent", out)
        self.assertTrue(wrote_nothing(h))

    def test_an_existing_parent_under_no_parent_refuses_the_same_way(self):
        h = adopt_harness(pre_parent="77")
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("77", out)
        self.assertIn("--remove-parent", out)
        self.assertTrue(wrote_nothing(h))

    def test_unnamed_blocked_by_links_refuse_and_name_the_clearing_command(self):
        h = adopt_harness(pre_blocked=[122, 133])
        r = h.run(*adopt_args(**{"--blocked-by": "122"}), "--no-parent",
                  "--after", "101")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("133", out, "must name the link not asked for")
        self.assertIn("gh issue edit 200 --repo jffriend/photo-consolidation "
                      "--remove-blocked-by 133", out)
        self.assertTrue(wrote_nothing(h))

    def test_unnamed_blocks_links_refuse_and_name_the_clearing_command(self):
        h = adopt_harness(pre_blocking=[63])
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("63", out)
        self.assertIn("gh issue edit 200 --repo jffriend/photo-consolidation "
                      "--remove-blocking 63", out)
        self.assertTrue(wrote_nothing(h))


class AdoptDelta(unittest.TestCase):
    """
    `gh issue edit` is NOT idempotent -- measured against the live board on
    2026-08-24 with gh 2.98.0 and recorded on #233. Re-adding a link that is
    already there fails the WHOLE call:

        gh issue edit 234 --add-blocked-by 233
          Validation failed: Target issue has already been taken (addBlockedBy)
        gh issue edit 234 --parent 240
          Issue may not contain duplicate sub-issues (addSubIssue)

    So the apply step sends a DELTA, not a set. Anything already correct is
    skipped; anything contradicting has already been refused above.
    """

    def test_an_already_correct_parent_is_not_sent_again(self):
        h = adopt_harness(pre_parent="55", post_parent="55")
        r = h.run(*adopt_args(), "--parent", "55", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = edit_argv(h)
        if argv is not None:
            self.assertNotIn("--parent", argv,
                             "a parent already correct must not be re-added")

    def test_an_already_present_blocker_is_omitted_and_the_others_are_sent(self):
        h = adopt_harness(pre_blocked=[122], post_blocked=[122, 133])
        r = h.run(*adopt_args(**{"--blocked-by": "122,133"}), "--no-parent",
                  "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = edit_argv(h)
        self.assertIsNotNone(argv, "the missing blocker still has to be written")
        self.assertIn("--add-blocked-by", argv)
        self.assertEqual("133", argv[argv.index("--add-blocked-by") + 1],
                         "only the link that is not already there is sent")

    def test_an_already_present_blocking_link_is_omitted_and_the_others_are_sent(self):
        """The `blocks` mirror of the blocked-by test above.

        Photos' original suite only carried this shape for parent and
        blocked-by; blocking is the third relationship kind `EDIT_ARGS`
        computes a delta for and needs its own proof.
        """
        h = adopt_harness(pre_blocking=[63], post_blocking=[63, 70])
        r = h.run(*adopt_args(**{"--blocks": "63,70"}), "--no-parent",
                  "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = edit_argv(h)
        self.assertIsNotNone(argv, "the missing blocking link still has to be written")
        self.assertIn("--add-blocking", argv)
        self.assertEqual("70", argv[argv.index("--add-blocking") + 1],
                         "only the link that is not already there is sent")

    def test_the_position_write_is_issued_even_when_the_position_already_matches(self):
        """Position is the fourth placement answer, and the ONE relationship
        kind with no delta-skip, by design. KD2 refuses to reconcile parent,
        blocked-by and blocks when the server already disagrees, and skips
        writing them again when the server already agrees -- but adopt does
        not refuse a reposition (all four placement answers are mandatory,
        so a position is always named), and there is no `--position` flag on
        `gh issue edit` to omit in the first place: the write is a separate
        GraphQL mutation (`updateProjectV2ItemPosition`), issued
        unconditionally every time. This pins that as intentional, not a gap
        in the delta logic.
        """
        h = adopt_harness(boards=[ADOPT_PRE_BOARD, ADOPT_PRE_BOARD])
        r = h.run(*adopt_args(), "--no-parent", "--after", "102")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        positions = [c for c in h.calls()
                     if any("updateProjectV2ItemPosition" in a for a in c)]
        self.assertEqual(1, len(positions),
                         "the position write is unconditional, not delta-gated")

    def test_everything_already_present_issues_no_edit_at_all_and_still_reads_back(self):
        h = adopt_harness(pre_parent="55", pre_blocked=[122], pre_blocking=[63],
                          post_parent="55", post_blocked=[122], post_blocking=[63])
        r = h.run("--adopt", ADOPT_NUM, "--parent", "55", "--after", "101",
                  "--blocked-by", "122", "--blocks", "63")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIsNone(edit_argv(h),
                          "an empty delta must issue no gh issue edit at all")
        out = r.stdout
        self.assertIn("board membership   ok", out)
        self.assertIn("board position     ok", out)
        self.assertIn("parent             ok (#55)", out)
        self.assertIn("blocked-by         ok (122)", out)
        self.assertIn("blocks             ok (63)", out)

    def test_a_partially_applied_edit_is_caught_and_not_reported_as_nothing_written(self):
        # The edit exits non-zero after the parent landed and the blocker did
        # not. One rejected flag fails the whole call server-side, so "it
        # exited non-zero" is not evidence that nothing was written.
        h = adopt_harness(post_parent="55", post_blocked=[], edit_exit=1)
        r = h.run("--adopt", ADOPT_NUM, "--parent", "55", "--after", "101",
                  "--blocked-by", "122", "--blocks", "none")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("blocked-by", out, "must name the relationship that disagreed")
        self.assertIn("MAY still have been written", out)
        self.assertNotIn("Nothing was changed", out)
        self.assertNotIn("nothing was written", out.lower())


class AdoptReadBack(unittest.TestCase):
    """The SAME read-back the create path uses, applied to an existing issue."""

    def test_happy_path_all_five_relationships_match(self):
        h = adopt_harness(post_parent="55", post_blocked=[122], post_blocking=[63])
        r = h.run("--adopt", ADOPT_NUM, "--parent", "55", "--after", "101",
                  "--blocked-by", "122", "--blocks", "63")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertIn("board membership   ok", out)
        self.assertIn("board position     ok (after #101)", out)
        self.assertIn("parent             ok (#55)", out)
        self.assertIn("blocked-by         ok (122)", out)
        self.assertIn("blocks             ok (63)", out)
        self.assertIn("#200 is wired", out)

    def test_a_blocker_that_does_not_land_fails_without_advising_deletion(self):
        h = adopt_harness(post_blocked=[])
        r = h.run("--adopt", ADOPT_NUM, "--no-parent", "--after", "101",
                  "--blocked-by", "122", "--blocks", "none")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("blocked-by", out)
        self.assertIn("200", out, "must name the issue")
        self.assertIn("Do not delete #200", out)
        self.assertNotIn("or delete #200 and re-run", out)

    def test_a_parent_that_does_not_land_fails_naming_parent(self):
        h = adopt_harness(post_parent=None)
        r = h.run("--adopt", ADOPT_NUM, "--parent", "55", "--after", "101",
                  "--blocked-by", "none", "--blocks", "none")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("parent", (r.stdout + r.stderr).lower())

    def test_an_issue_already_on_the_board_resolves_its_item_id_by_number(self):
        # item-add cannot answer this: the create path takes the id from
        # item-add's output and refuses when it is empty, which for an issue
        # already on the board would abort a correctly wired filing.
        h = adopt_harness()
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(h.called("item-add"),
                         "the id came from the by-number lookup, not item-add")
        positions = [c for c in h.calls()
                     if any("updateProjectV2ItemPosition" in a for a in c)]
        self.assertEqual(1, len(positions), positions)
        self.assertIn("PVTI_adopt", " ".join(positions[0]))
        self.assertIn("board position     ok (after #101)", r.stdout)

    def test_the_by_number_lookup_falls_back_to_item_add_when_it_finds_nothing(self):
        # An adopted issue that is not on the board yet: the lookup returns
        # nothing and item-add puts it there.
        top_board = [
            (200, "An existing issue being wired"),
            (101, "First thing on the board"),
            (102, "Second thing"),
        ]
        h = adopt_harness(boards=[ADOPT_PRE_BOARD, top_board],
                          item_by_number="")
        r = h.run(*adopt_args(), "--no-parent", "--top")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(h.called("item-add"))
        self.assertIn("board position     ok (top)", r.stdout)

    def test_an_adopt_failure_never_says_a_create_happened(self):
        h = adopt_harness(post_blocked=[])
        r = h.run("--adopt", ADOPT_NUM, "--no-parent", "--after", "101",
                  "--blocked-by", "122", "--blocks", "none")
        out = r.stdout + r.stderr
        self.assertNotIn("the create succeeded", out)
        self.assertNotIn("created #", out)
        self.assertNotIn("Nothing was created", out)


# ---------------------------------------------------------------------------
# ONE IMPLEMENTATION (R8, R9, R24)
#
# Three different guards, because one is not enough: a text scan catches a
# verbatim copy, an equivalence test catches a paraphrase, a parity test
# catches a mode that writes a different relationship set.
# ---------------------------------------------------------------------------

READ_BACK_START = "# >>> SHARED READ-BACK START"
READ_BACK_END = "# <<< SHARED READ-BACK END"

# Tokens that exist only to compare a relationship against its answer. Every
# one of them must live inside the marked block and nowhere else.
COMPARISON_TOKENS = (
    "BOARD2_NUMS", "IDX2", "REL_JSON", "PARENT_READ",
    "BLOCKED_READ", "BLOCKED_WANT", "BLOCKING_READ", "BLOCKING_WANT",
)


def scan_for_duplicated_comparisons(path):
    """Return the tokens found OUTSIDE the marked shared read-back.

    Raises rather than returning a clean result when the file cannot be read or
    a marker is missing: an unreadable file is not evidence of no duplication,
    and a deleted marker would otherwise turn this scan into a vacuous pass.
    """
    try:
        text = Path(path).read_text()
    except OSError as exc:
        raise AssertionError(
            "the shared-read-back scan could not read %s (%s). "
            "Unable to look is not permission." % (path, exc))
    if text.count(READ_BACK_START) != 1 or text.count(READ_BACK_END) != 1:
        raise AssertionError(
            "the shared read-back markers are missing or duplicated in %s. "
            "Without them this scan proves nothing." % path)
    head, rest = text.split(READ_BACK_START, 1)
    block, tail = rest.split(READ_BACK_END, 1)
    outside = head + tail
    return {t for t in COMPARISON_TOKENS if t in outside}, \
           {t for t in COMPARISON_TOKENS if t in block}


# The two shared functions take NO arguments and read the globals $NUM/$URL,
# so their call sites are the bare function name and nothing else.
CURRENT_SHELL_CALL_SITES = ("read_back", "board_half")


def current_shell_call_problems(text):
    """Every way the two shared functions could end up in a subshell.

    Matches the WHOLE STRIPPED LINE, never a prefix. `half_wired()` exits
    directly and the script runs `set -uo pipefail` without `-e`, so a pipe, a
    background `&` or a trailing `||` all swallow that exit exactly as a
    command substitution does -- and the run then reports success on a real
    mismatch.
    """
    problems = []
    lines = [ln.strip() for ln in text.splitlines()]
    for fn in CURRENT_SHELL_CALL_SITES:
        for bad in ("$(%s" % fn, "`%s" % fn, "${%s" % fn):
            if bad in text:
                problems.append("%s is called in a subshell: %s" % (fn, bad))
        if fn not in lines:
            problems.append(
                "no top-level call site %r: the call must be the WHOLE line, "
                "with no pipe, no `&` and no `||`, so half_wired's exit reaches "
                "the shell running the script" % fn)
    return problems


class OneImplementation(unittest.TestCase):

    def test_no_relationship_comparison_lives_outside_the_shared_block(self):
        outside, inside = scan_for_duplicated_comparisons(FILE_ISSUE)
        self.assertEqual(set(), outside,
                         "a second copy of a relationship comparison drifts, "
                         "and no document stops it")
        self.assertEqual(set(COMPARISON_TOKENS), inside,
                         "every comparison must live INSIDE the marked block")

    def test_the_scan_fails_against_a_reintroduced_verbatim_copy(self):
        text = FILE_ISSUE.read_text()
        head, rest = text.split(READ_BACK_START, 1)
        block, tail = rest.split(READ_BACK_END, 1)
        # A verbatim copy-paste of one comparison, back outside the block.
        copied = '\nPARENT_READ="$(printf %s "$REL_JSON" | jq -r .parent.number)"\n'
        tmp = Path(tempfile.mkdtemp()) / "copy.sh"
        tmp.write_text(head + READ_BACK_START + block + READ_BACK_END
                       + copied + tail)
        outside, _ = scan_for_duplicated_comparisons(tmp)
        self.assertEqual({"PARENT_READ", "REL_JSON"}, outside)

    def test_the_scan_refuses_when_a_marker_is_missing(self):
        text = FILE_ISSUE.read_text().replace(READ_BACK_START, "# gone", 1)
        tmp = Path(tempfile.mkdtemp()) / "nomarker.sh"
        tmp.write_text(text)
        with self.assertRaises(AssertionError):
            scan_for_duplicated_comparisons(tmp)

    def test_the_scan_refuses_when_the_file_cannot_be_read(self):
        with self.assertRaises(AssertionError):
            scan_for_duplicated_comparisons(Path("/nonexistent/file_issue.sh"))

    def test_the_shared_functions_are_called_in_the_current_shell(self):
        """`X="$(read_back)"` would swallow half_wired's exit.

        The script runs `set -uo pipefail` WITHOUT `-e`, and `half_wired()`
        exits directly. Inside a command substitution that exit kills only the
        subshell, the assignment succeeds, and the run reports SUCCESS -- a
        vacuous pass in the very guard this script is.
        """
        self.assertEqual(
            [], current_shell_call_problems(FILE_ISSUE.read_text()))

    def test_the_current_shell_guard_catches_a_piped_call_site(self):
        """A pipeline is a subshell too, and the old check could not see one.

        The check used to forbid `$(`, a backtick and `${`, and otherwise only
        require the line to START with the call. `read_back | cat`,
        `read_back &` and `read_back || true` all satisfied that, and every one
        of them puts half_wired's `exit 1` in a subshell that `set -uo
        pipefail` without `-e` swallows. Appending `| cat` kept every guard
        assertion in this suite green while the mutated script exited 0 on a
        blocked-by mismatch that was really there. With no CI, this test is the
        only thing standing between that edit and the board.
        """
        text = FILE_ISSUE.read_text()
        for suffix in (" | cat", " &", " || true"):
            with self.subTest(suffix=suffix):
                mutated = text.replace("\nread_back\n",
                                       "\nread_back%s\n" % suffix)
                self.assertNotEqual(mutated, text,
                                    "the call site to mutate was not found")
                problems = current_shell_call_problems(mutated)
                self.assertTrue(problems,
                                "a call site in a subshell must be caught")
                self.assertTrue(any("read_back" in p for p in problems), problems)


PROVENANCE_PREFIXES = ("It is left", "Finish it by hand")


def failure_lines(stderr):
    """The failure output minus the two lines that legitimately differ.

    Only the provenance sentence and the next action depend on whether this run
    created the issue. Everything else -- the MISMATCH sentence and the
    requested-state summary -- must be byte-identical between the modes.
    """
    return [ln for ln in stderr.splitlines()
            if not ln.startswith(PROVENANCE_PREFIXES)]


class BehaviouralEquivalence(unittest.TestCase):
    """
    R9: a text scan catches a verbatim copy but not a paraphrase. This injects
    the SAME mismatch on both paths, for each of the five relationships, and
    requires byte-identical failure output.

    Both runs act on issue #200 so the issue number and URL in the message are
    the same in both modes and cannot mask a difference.
    """

    CREATE_BOARD_OK = [
        (101, "First thing on the board"),
        (200, "A brand new distinct piece of work"),
        (102, "Second thing"),
    ]
    CREATE_BOARD_MISSING = [(101, "First thing on the board"), (102, "Second thing")]
    CREATE_BOARD_WRONG_POS = [
        (101, "First thing on the board"),
        (102, "Second thing"),
        (200, "A brand new distinct piece of work"),
    ]
    ADOPT_BOARD_MISSING = [(101, "First thing on the board"), (102, "Second thing")]
    ADOPT_BOARD_WRONG_POS = [
        (101, "First thing on the board"),
        (102, "Second thing"),
        (200, "An existing issue being wired"),
    ]

    def _create(self, board_after, parent, blocked, blocking, args):
        h = Harness("**Design:** none\n",
                    boards=[PRE_BOARD, board_after],
                    responses=create_responses(blocked, blocking, parent))
        return h.run("--title", "A brand new distinct piece of work",
                     "--body-file", str(h.body_file), "--shape", "work",
                     *args)

    def _adopt(self, board_after, parent, blocked, blocking, args):
        h = Harness("**Design:** none\n",
                    boards=[ADOPT_PRE_BOARD, board_after],
                    responses=adopt_responses(post_parent=parent,
                                              post_blocked=blocked,
                                              post_blocking=blocking))
        return h.run("--adopt", ADOPT_NUM, *args)

    def _compare(self, create_r, adopt_r):
        self.assertNotEqual(create_r.returncode, 0, create_r.stdout)
        self.assertNotEqual(adopt_r.returncode, 0, adopt_r.stdout)
        c, a = failure_lines(create_r.stderr), failure_lines(adopt_r.stderr)
        self.assertIn("MISMATCH:", "\n".join(c))
        self.assertEqual(c, a,
                         "the two modes must share ONE read-back; a paraphrased "
                         "second copy drifts this output")

    def test_board_membership(self):
        args = ["--no-parent", "--after", "101", "--blocked-by", "none",
                "--blocks", "none"]
        self._compare(
            self._create(self.CREATE_BOARD_MISSING, None, [], [], args),
            self._adopt(self.ADOPT_BOARD_MISSING, None, [], [], args))

    def test_board_position(self):
        args = ["--no-parent", "--after", "101", "--blocked-by", "none",
                "--blocks", "none"]
        self._compare(
            self._create(self.CREATE_BOARD_WRONG_POS, None, [], [], args),
            self._adopt(self.ADOPT_BOARD_WRONG_POS, None, [], [], args))

    def test_parent(self):
        args = ["--parent", "55", "--after", "101", "--blocked-by", "none",
                "--blocks", "none"]
        self._compare(
            self._create(self.CREATE_BOARD_OK, None, [], [], args),
            self._adopt(ADOPT_POST_BOARD, None, [], [], args))

    def test_no_parent_but_one_reads_back(self):
        args = ["--no-parent", "--after", "101", "--blocked-by", "none",
                "--blocks", "none"]
        self._compare(
            self._create(self.CREATE_BOARD_OK, "77", [], [], args),
            self._adopt(ADOPT_POST_BOARD, "77", [], [], args))

    def test_blocked_by(self):
        args = ["--no-parent", "--after", "101", "--blocked-by", "122",
                "--blocks", "none"]
        self._compare(
            self._create(self.CREATE_BOARD_OK, None, [], [], args),
            self._adopt(ADOPT_POST_BOARD, None, [], [], args))

    def test_blocks(self):
        args = ["--no-parent", "--after", "101", "--blocked-by", "none",
                "--blocks", "63"]
        self._compare(
            self._create(self.CREATE_BOARD_OK, None, [], [], args),
            self._adopt(ADOPT_POST_BOARD, None, [], [], args))


# create's flag names, canonicalised to adopt's. An EXPLICIT map, so a fourth
# relationship added to one mode fails this test instead of slipping past an
# enumeration that silently stopped covering it.
RELATIONSHIP_FLAG_MAP = {
    "--parent": "--parent",
    "--blocked-by": "--add-blocked-by",
    "--blocking": "--add-blocking",
    "--add-blocked-by": "--add-blocked-by",
    "--add-blocking": "--add-blocking",
}
NOT_RELATIONSHIPS = {"--no-parent"}


def relationship_set(argv):
    """Every relationship-bearing flag in an argv, as {(canonical, value)}."""
    out = set()
    for i, arg in enumerate(argv):
        if not arg.startswith("--") or arg in NOT_RELATIONSHIPS:
            continue
        if arg in RELATIONSHIP_FLAG_MAP:
            out.add((RELATIONSHIP_FLAG_MAP[arg], argv[i + 1]))
        elif "parent" in arg or "block" in arg:
            raise AssertionError(
                "unmapped relationship-bearing flag %r -- add it to "
                "RELATIONSHIP_FLAG_MAP so parity keeps binding" % arg)
    return out


class WriteShapeParity(unittest.TestCase):
    """
    R24: for the same four answers, both modes write the same relationship set.

    The comparison is made against the SAME STARTING STATE -- an adopted issue
    with NONE of the relationships already present. Create always sends the
    full set; adopt sends the DELTA against what is already there, so against
    any other starting state the two modes legitimately differ and this test
    would be asserting the wrong thing.
    """

    BOARD_AFTER_CREATE = [
        (101, "First thing on the board"),
        (200, "A brand new distinct piece of work"),
        (102, "Second thing"),
    ]

    def _create_set(self, args, blocked, blocking, parent):
        h = Harness("**Design:** none\n",
                    boards=[PRE_BOARD, self.BOARD_AFTER_CREATE],
                    responses=create_responses(blocked, blocking, parent))
        r = h.run("--title", "A brand new distinct piece of work",
                  "--body-file", str(h.body_file), "--shape", "work",
                  *args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = create_argv(h)
        self.assertIsNotNone(argv)
        return relationship_set(argv)

    def _adopt_set(self, args, blocked, blocking, parent):
        h = adopt_harness(post_parent=parent, post_blocked=blocked,
                          post_blocking=blocking)
        r = h.run("--adopt", ADOPT_NUM, *args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = edit_argv(h)
        return relationship_set(argv) if argv else set()

    def test_all_three_relationships_are_written_the_same_by_both_modes(self):
        args = ["--parent", "55", "--after", "101", "--blocked-by", "122",
                "--blocks", "63"]
        created = self._create_set(args, [122], [63], "55")
        adopted = self._adopt_set(args, [122], [63], "55")
        self.assertEqual(set(), created ^ adopted,
                         "create wrote %s; adopt wrote %s" % (created, adopted))
        self.assertEqual(3, len(created))

    def test_none_answers_omit_every_flag_in_both_modes(self):
        args = ["--no-parent", "--after", "101", "--blocked-by", "none",
                "--blocks", "none"]
        created = self._create_set(args, [], [], None)
        adopted = self._adopt_set(args, [], [], None)
        self.assertEqual(set(), created)
        self.assertEqual(set(), adopted)


class Usage(unittest.TestCase):
    """
    R15: `usage()` used to copy a FIXED LINE RANGE that already ran past the
    header, so `--help` printed shell code verbatim. It is delimited now.
    """

    def test_help_prints_both_modes_and_no_shell_code(self):
        r = subprocess.run(["bash", str(FILE_ISSUE), "--help"],
                           capture_output=True, text=True, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("--adopt", out, "adopt mode must appear in usage")
        self.assertIn("--title", out)
        self.assertIn("--body-file", out)
        self.assertIn("--dry-run", out)
        self.assertIn("--blocked-by", out)
        for shell in ("set -uo pipefail", "die()", 'case "$1"', "${BASH_SOURCE",
                      "HELP BLOCK"):
            self.assertNotIn(shell, out,
                             "usage must print help, never shell code")
        self.assertGreater(len(out.splitlines()), 20,
                           "the help must not be truncated")


# ---------------------------------------------------------------------------
# U3. The board write is not read-your-writes consistent. Four correctly wired
# filings were declared HALF-WIRED because the listing was read before it had
# caught up, and the refusal told the operator to delete the issue. These
# tests pin the three-state resolution: not yet visible, did not land, could
# not look.
# ---------------------------------------------------------------------------

BOARD_WITHOUT_200 = [
    (101, "First thing on the board"),
    (102, "Second thing"),
    (103, "Third thing"),
]
BOARD_WITH_200 = [
    (101, "First thing on the board"),
    (200, "A brand new distinct piece of work"),
    (102, "Second thing"),
    (103, "Third thing"),
]
BOARD_200_WRONG_POS = [
    (101, "First thing on the board"),
    (102, "Second thing"),
    (200, "A brand new distinct piece of work"),
]


class ReadBackRetry(unittest.TestCase):
    """R1-R7: the read-back retries the READ, never the write."""

    def _run(self, boards, corroborate="", env=None, args=None,
             blocked_by=(), blocking=(), parent=None):
        h = Harness(
            "**Design:** none\n",
            boards=boards,
            responses=create_responses(list(blocked_by), list(blocking),
                                       parent, corroborate=corroborate),
        )
        args = args or ["--no-parent", "--after", "101"]
        return h, h.run(*full_args(h.body_file), *args, env=env)

    @staticmethod
    def _board_reads(h):
        return [c for c in h.calls() if any("items(first: 100" in a for a in c)]

    def test_listing_catches_up_on_the_second_read(self):
        """The defect itself: absent on the first read, there on the second."""
        h, r = self._run([PRE_BOARD, BOARD_WITHOUT_200, BOARD_WITH_200])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertIn("board membership   ok", out)
        self.assertIn("attempt 2", out, "a retried success must name the attempt")

    def test_a_write_that_never_lands_still_fails_and_never_says_delete(self):
        """R7: the bound is finite and this still fails.

        R6: the corroborating read agreed it is absent, but agreement on
        ABSENCE is weak -- the refusal rests on the exhausted bound -- so the
        wiring was not proven wrong and nothing may tell the operator to
        delete the issue.
        """
        h, r = self._run([PRE_BOARD, BOARD_WITHOUT_200], corroborate="")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("not on the board", out)
        self.assertNotIn("delete #200 and re-run", out)
        self.assertNotIn("delete", out.replace("Do not delete", ""),
                         "a false alarm followed literally destroys correct wiring")
        self.assertIn("--adopt 200", out, "must name a safe next action")
        self.assertEqual(5, len(self._board_reads(h)) - 1,
                         "the bound must actually be spent before refusing")

    def test_a_corroborated_member_still_waits_for_the_listing(self):
        """Membership proven by the direct read does NOT finish the check."""
        h, r = self._run([PRE_BOARD, BOARD_WITHOUT_200, BOARD_WITH_200],
                         corroborate="PVTI_new")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("board position     ok (after #101)", r.stdout)
        self.assertIn("attempt 2", r.stdout)

    def test_a_listing_that_never_catches_up_is_position_unverified(self):
        """Distinct from both 'not on the board' and 'position is wrong'."""
        h, r = self._run([PRE_BOARD, BOARD_WITHOUT_200], corroborate="PVTI_new")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("unverified", out.lower())
        self.assertIn("Membership is PROVEN", out)
        self.assertNotIn("not on the board", out,
                         "membership was proven; this is not an absent write")
        self.assertNotIn("it follows #", out,
                         "nothing here proved the position WRONG")
        self.assertNotIn("delete", out.replace("Do not delete", ""))
        self.assertIn("--adopt 200", out)

    def test_a_board_read_that_errors_says_the_READ_failed(self):
        """R4: unreadable never becomes absent by waiting."""
        h = Harness("**Design:** none\n",
                    boards=[PRE_BOARD, BOARD_WITHOUT_200],
                    board_exits=[0, 1],
                    responses=create_responses([], []))
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("The READ failed, not the write.", out)
        self.assertNotIn("not on the board", out)
        self.assertIn("--adopt 200", out, "R6: name the re-verification command")
        self.assertNotIn("delete", out.replace("Do not delete", ""))
        self.assertEqual(1, len(self._board_reads(h)) - 1,
                         "an unreadable board is fatal at once, never retried")

    def test_a_truncated_board_on_the_read_back_is_fatal_at_once(self):
        """rows != distinct is board.sh's own self-check. Not a short board,
        and not something waiting can fix."""
        dupe = BOARD_WITH_200 + [BOARD_WITH_200[0]]
        h, r = self._run([PRE_BOARD, dupe])
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("The READ failed, not the write.", out)
        self.assertEqual(1, len(self._board_reads(h)) - 1,
                         "a truncated board must not be retried")

    def test_a_stably_wrong_position_still_fails_naming_position(self):
        h, r = self._run([PRE_BOARD, BOARD_200_WRONG_POS])
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("board position", out)
        self.assertIn("it follows #102 instead", out)

    def test_a_position_wrong_on_the_first_read_and_right_on_the_second(self):
        h, r = self._run([PRE_BOARD, BOARD_200_WRONG_POS, BOARD_WITH_200])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("board position     ok (after #101)", r.stdout)
        self.assertIn("attempt 2", r.stdout)

    def test_success_on_the_final_attempt_warns_the_bound_is_nearly_spent(self):
        h, r = self._run([PRE_BOARD, BOARD_WITHOUT_200, BOARD_WITH_200],
                         env={"FILE_ISSUE_READBACK_ATTEMPTS": 2})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("attempt 2 of 2", r.stdout)
        self.assertIn("FINAL attempt", r.stderr)
        self.assertIn("bound is nearly exhausted", r.stderr)

    def test_the_warning_names_a_delay_the_ceiling_will_actually_accept(self):
        """#265: the old text said "raise ATTEMPTS / DELAY", but ATTEMPTS=6 at
        DELAY=1 is refused (31s over the 30s ceiling) -- a knob the very next
        run of this script would reject. The warning must name a DELAY value
        instead, and that value must itself pass the ceiling check at the
        same ATTEMPTS.

        The round-trip run below only needs to clear the STARTUP ceiling
        validation, which happens before any board read -- it does not need
        to actually retry. A board that converges on the first attempt
        proves the same thing without sleeping for the suggested value in
        real time (a prior version of this test fed ATTEMPTS=2's suggestion,
        the entire 30s ceiling, into a run that also converged on the FINAL
        attempt, so it really slept 30 seconds).
        """
        h, r = self._run([PRE_BOARD, BOARD_WITHOUT_200, BOARD_WITH_200],
                         env={"FILE_ISSUE_READBACK_ATTEMPTS": 2})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FILE_ISSUE_READBACK_ATTEMPTS /", r.stderr,
                         "must not repeat the knob the ceiling check refuses")
        self.assertIn("FILE_ISSUE_READBACK_DELAY=", r.stderr)
        suggested = int(r.stderr.rsplit("FILE_ISSUE_READBACK_DELAY=", 1)[1]
                         .split()[0].rstrip("."))

        h2, r2 = self._run(
            [PRE_BOARD, BOARD_WITH_200],
            env={"FILE_ISSUE_READBACK_ATTEMPTS": 2,
                 "FILE_ISSUE_READBACK_DELAY": suggested})
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertNotIn("over the", r2.stderr,
                         "the suggested DELAY must itself clear the ceiling check")

    def test_the_suggested_delay_matches_an_independently_computed_value(self):
        """The test above only checks that feeding the suggestion back
        clears the ceiling check -- a wrong formula that happened to land on
        any ceiling-safe value would still pass that. Compute the expected
        value independently in Python, at an ATTEMPTS where the division
        truncates (30 // 7 == 4, not 4.28...), so a formula bug that rounds
        differently is actually caught."""
        boards = [PRE_BOARD] + [BOARD_WITHOUT_200] * 3 + [BOARD_WITH_200]
        h, r = self._run(boards, env={"FILE_ISSUE_READBACK_ATTEMPTS": 4})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        expected = 30 // (2 ** (4 - 1) - 1)
        self.assertIn(f"FILE_ISSUE_READBACK_DELAY={expected}.", r.stderr)

    def test_delay_zero_stays_accepted_at_any_attempt_count(self):
        """Decided, not left open: DELAY=0 keeps passing the ceiling check
        regardless of ATTEMPTS, because the doubling sum of zero is always
        zero -- it cannot create the wall-clock hang risk the ceiling
        guards against. tests in this file rely on DELAY=0 for speed.

        The read-back must actually reach the final attempt here, not just
        pass the startup ceiling check -- a prior version of this test
        converged on the FIRST attempt, so the warning block this exact
        configuration triggers (ATTEMPTS=20 has no ceiling headroom left for
        any DELAY) never ran, and a broken suggestion there went undetected.
        DELAY stays 0 throughout, so the extra attempts cost no real time.
        """
        boards = [PRE_BOARD] + [BOARD_WITHOUT_200] * 19 + [BOARD_WITH_200]
        h, r = self._run(boards,
                         env={"FILE_ISSUE_READBACK_ATTEMPTS": 20,
                              "FILE_ISSUE_READBACK_DELAY": 0})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("attempt 20 of 20", r.stdout)
        self.assertNotIn("over the", r.stderr)
        self.assertNotIn("FILE_ISSUE_READBACK_DELAY=", r.stderr,
                         "ATTEMPTS=20 has no headroom; must not suggest a DELAY")
        self.assertIn("room left for a larger DELAY", r.stderr)

    def test_a_bound_of_zero_attempts_is_refused(self):
        """A read-back that never reads is a vacuous pass in the one guard
        this script is."""
        h, r = self._run([PRE_BOARD, BOARD_WITH_200],
                         env={"FILE_ISSUE_READBACK_ATTEMPTS": 0})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("FILE_ISSUE_READBACK_ATTEMPTS", r.stdout + r.stderr)

    def test_the_defaults_with_the_environment_unset_are_finite_and_non_zero(self):
        """Two halves, because either alone can hide the other's absence.

        Behaviourally: with BOTH variables deleted, a board that converges on
        the second read must still succeed (so the default attempt count is
        at least 2) and must have really waited (so the default delay is not
        zero). Textually: the defaults are whole numbers, and the doubling
        waits they imply sum to under the 30-second ceiling the script names.
        """
        import re
        import time
        text = FILE_ISSUE.read_text()
        attempts = re.search(
            r'READBACK_ATTEMPTS="\$\{FILE_ISSUE_READBACK_ATTEMPTS:-(\d+)\}"', text)
        delay = re.search(
            r'READBACK_DELAY="\$\{FILE_ISSUE_READBACK_DELAY:-(\d+)\}"', text)
        self.assertIsNotNone(attempts, "no production default for the attempt count")
        self.assertIsNotNone(delay, "no production default for the backoff")
        a, d = int(attempts.group(1)), int(delay.group(1))
        self.assertGreaterEqual(a, 2, "the bound must allow at least one retry")
        self.assertGreater(d, 0, "a zero production backoff re-reads instantly")
        total = sum(d * (2 ** i) for i in range(a - 1))
        self.assertLess(total, 30,
                        "the total wall-clock wait must stay under the 30s ceiling")
        self.assertIn("30 SECONDS", text, "the ceiling must be visible in the code")

        started = time.monotonic()
        h, r = self._run([PRE_BOARD, BOARD_WITHOUT_200, BOARD_WITH_200],
                         env={"FILE_ISSUE_READBACK_DELAY": None,
                              "FILE_ISSUE_READBACK_ATTEMPTS": None})
        elapsed = time.monotonic() - started
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("attempt 2", r.stdout)
        self.assertGreaterEqual(elapsed, 1.0,
                                "the default backoff really waited nothing")

    def test_the_retry_covers_adopt_mode_too(self):
        """The read-back is shared, so the retry must reach both modes."""
        board_without = [(101, "First thing on the board"), (102, "Second thing")]
        h = adopt_harness(boards=[ADOPT_PRE_BOARD, board_without,
                                  ADOPT_POST_BOARD])
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("attempt 2", r.stdout)
        self.assertIn("board position     ok (after #101)", r.stdout)

    def test_an_adopt_that_never_appears_never_says_delete_either(self):
        board_without = [(101, "First thing on the board"), (102, "Second thing")]
        h = adopt_harness(boards=[ADOPT_PRE_BOARD, board_without])
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("not on the board", out)
        self.assertNotIn("delete", out.replace("Do not delete", ""))


# ---------------------------------------------------------------------------
# THE 2026-08-24 REVIEW OF THE READ-BACK CHANGE.
#
# Every test below reproduces a defect a reviewer found in the change that was
# meant to stop the read-back raising FALSE alarms. Two shapes recur, and they
# are the two this whole script is bounded against: an UNCLEARABLE REFUSAL (a
# correctly wired issue told to delete itself) and a VACUOUS PASS (a guard that
# cannot fail). Several of these were the second shape arriving by a new route.
# ---------------------------------------------------------------------------


def override(responses, match, **fields):
    """Return `responses` with the rule whose `match` is `match` replaced.

    Keeps the ORDER of the table, which several rules depend on -- the marked
    GraphQL lookups have to stay ahead of the generic `projectItems` rule.
    """
    out = []
    seen = 0
    for rule in responses:
        if rule["match"] == match:
            seen += 1
            new = {"match": match}
            new.update(fields)
            out.append(new)
        else:
            out.append(rule)
    assert seen == 1, "no single rule matching %r" % match
    return out


def position_line(stdout):
    for ln in stdout.splitlines():
        if ln.startswith("  position"):
            return ln
    return ""


class ReadBackProvesSomething(unittest.TestCase):
    """F1: the relationship read-back passed on ANY non-empty JSON."""

    BOARD_AFTER = [
        (101, "First thing on the board"),
        (200, "A brand new distinct piece of work"),
        (102, "Second thing"),
    ]

    def test_a_reply_without_the_three_fields_is_not_a_pass(self):
        """`{"message":"Not Found"}` used to read back as three clean `ok`s.

        Every jq extraction on it yields empty, and empty compares EQUAL to the
        empty answer set -- so on the commonest filing shape the run printed
        `parent ok (none)`, `blocked-by ok (none)`, `blocks ok (none)` and
        exited 0 having proven nothing at all.
        """
        h = Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, self.BOARD_AFTER],
            responses=override(create_responses([], []),
                               "--json parent,blockedBy,blocking",
                               stdout=json.dumps({"message": "Not Found"})),
        )
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("unrecognised shape", out)
        self.assertNotIn("every relationship read back matching", out)
        self.assertIn("The READ failed, not the write.", out,
                      "a reply that could not be read is not a failed write")
        self.assertNotIn("delete", out.replace("Do not delete", ""))

    def test_a_relationship_read_that_exits_non_zero_is_not_a_pass(self):
        h = Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, self.BOARD_AFTER],
            responses=override(create_responses([], []),
                               "--json parent,blockedBy,blocking",
                               stdout="", exit=1),
        )
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("The READ failed, not the write.", out)


class NumbersAreValidatedOffline(unittest.TestCase):
    """F2, F3: a typo in --parent or --after used to create a REAL issue and
    then declare it half-wired, with "delete #N and re-run" as the remedy."""

    def test_a_malformed_parent_is_refused_offline(self):
        h = Harness("**Design:** none\n")
        r = h.run(*full_args(h.body_file), "--parent", "55x", "--top")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("--parent", out)
        self.assertIn("55x", out)
        self.assertEqual([], h.network_calls(),
                         "the refusal must land before anything is created")

    def test_a_regex_after_is_refused_offline(self):
        """`--after 1.4` used to MATCH #144 on the board.

        `grep -qx` reads its argument as a basic regular expression, so the
        "is it on the board" gate passed, the issue was created, and the
        GraphQL lookup -- which takes an Int! -- then failed and ended the run
        HALF-WIRED with the delete remedy.
        """
        board = [(101, "First"), (144, "Second"), (107, "Third")]
        h = Harness("**Design:** none\n", boards=[board])
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "1.4")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("--after", out)
        self.assertIn("1.4", out)
        self.assertEqual([], h.network_calls())

    def test_the_board_lookups_match_a_fixed_string_not_a_pattern(self):
        """Belt and braces: the digit gate above is the first line, and -F is
        the second. A future flag reaching these lookups gets both."""
        text = FILE_ISSUE.read_text()
        self.assertNotIn('grep -qx "$AFTER"', text)
        self.assertNotIn('grep -nx "$AFTER"', text)
        self.assertIn('grep -qxF -- "$AFTER"', text)
        self.assertIn('grep -nxF -- "$AFTER"', text)
        self.assertIn('grep -qxF -- "$NUM"', text)
        self.assertIn('grep -nxF -- "$NUM"', text)


class PositionProofIsLatched(unittest.TestCase):
    """F4: a position PROVEN WRONG was re-reported as position UNVERIFIED."""

    def test_proven_wrong_then_a_silent_listing_still_says_wrong(self):
        """Boards: pre, WRONG POSITION, then absent -- with the corroborating
        read positive throughout.

        The refusal used to be chosen from the LAST attempt's `in_listing`
        alone. The early attempt that saw the wrong position was thrown away,
        and the operator was told "the board listing never showed it" and
        "Nothing here proved the position wrong" -- both false. A did-not-land
        was routed into the probably-fine bucket.
        """
        h = Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, BOARD_200_WRONG_POS, BOARD_WITHOUT_200],
            responses=create_responses([], [], corroborate="PVTI_new"),
        )
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("it follows #102 instead", out,
                      "the proof must survive a later silent listing")
        self.assertNotIn("unverified", out.lower())
        self.assertNotIn("Membership is PROVEN", out)
        self.assertNotIn("never showed it", out)

    def test_a_wrong_position_that_later_reads_right_still_succeeds(self):
        """The latch must not defeat KD1's convergence: wrong then right is a
        listing that caught up, and that is the whole point of the retry."""
        h = Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, BOARD_200_WRONG_POS, BOARD_WITH_200],
            responses=create_responses([], []),
        )
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("board position     ok (after #101)", r.stdout)


class DuplicateNumbersInAnAnswer(unittest.TestCase):
    """F5: `--blocked-by 122,122` failed a CORRECTLY WIRED issue."""

    BOARD_AFTER = [
        (101, "First thing on the board"),
        (200, "A brand new distinct piece of work"),
        (102, "Second thing"),
    ]

    def test_a_repeated_blocker_reads_back_as_correctly_wired_on_create(self):
        """The server cannot hold the same link twice, so it reads back once.
        The WANTED set used to keep the repeat, so the comparison failed and
        the create-mode refusal told the operator to delete the issue."""
        h = Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, self.BOARD_AFTER],
            responses=create_responses([122], []),
        )
        r = h.run("--title", "A brand new distinct piece of work",
                  "--body-file", str(h.body_file), "--shape", "work",
                  "--no-parent", "--after", "101",
                  "--blocked-by", "122,122", "--blocks", "none")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("blocked-by         ok (122)", r.stdout)
        argv = create_argv(h)
        self.assertEqual("122", argv[argv.index("--blocked-by") + 1],
                         "the WRITE must not carry the repeat either -- "
                         "gh rejects an already-present link and fails the "
                         "whole call")

    def test_a_repeated_blocker_reads_back_as_correctly_wired_on_adopt(self):
        h = adopt_harness(post_blocked=[122])
        r = h.run("--adopt", ADOPT_NUM, "--no-parent", "--after", "101",
                  "--blocked-by", "122,122", "--blocks", "none")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("blocked-by         ok (122)", r.stdout)
        argv = edit_argv(h)
        self.assertIsNotNone(argv)
        self.assertEqual("122", argv[argv.index("--add-blocked-by") + 1],
                         "the adopt delta must not emit a repeat")

    def test_a_repeated_blocks_number_behaves_the_same_way(self):
        h = Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, self.BOARD_AFTER],
            responses=create_responses([], [63]),
        )
        r = h.run("--title", "A brand new distinct piece of work",
                  "--body-file", str(h.body_file), "--shape", "work",
                  "--no-parent", "--after", "101",
                  "--blocked-by", "none", "--blocks", "63,63,63")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("blocks             ok (63)", r.stdout)


class ProbeTerminator(unittest.TestCase):
    """F6: the probe passed a FLAGLESS gh when the FLAGS terminator moved."""

    def test_a_renamed_terminator_does_not_let_examples_satisfy_the_probe(self):
        """Closing the block on one hardcoded literal failed UNSAFE.

        With `INHERITED FLAGS` renamed to `GLOBAL FLAGS` the block ran to end
        of file and swallowed EXAMPLES -- which on real gh 2.98.0 names
        `--parent`, `--blocked-by` and `--blocking`. A gh with none of the
        flags in its FLAGS block then probed "ok" and was rejected mid-write,
        leaving behind the exact half-wired issue the probe exists to prevent.

        `test_examples_naming_the_flags_do_not_satisfy_the_probe` keeps the
        terminator, so it cannot see this.
        """
        flagless = create_help("").replace("INHERITED FLAGS", "GLOBAL FLAGS")
        self.assertIn("EXAMPLES", flagless)
        self.assertIn("--parent", flagless.split("EXAMPLES", 1)[1],
                      "the EXAMPLES must still name the flags, or this test "
                      "would pass for the wrong reason")
        h = Harness("**Design:** none\n", probe=probe_rules(help_text=flagless))
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("MISSING CAPABILITY", out)
        self.assertEqual([], h.network_calls())

    def test_a_lost_opener_still_fails_safe_as_undeterminable(self):
        """The other direction, pinned so a future edit cannot swap them."""
        no_flags_header = create_help().replace("\nFLAGS\n", "\nOPTIONS\n")
        h = Harness("**Design:** none\n",
                    probe=probe_rules(help_text=no_flags_header))
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("UNDETERMINABLE CAPABILITY", out)


class ErroredLookupIsNotAnAbsentItem(unittest.TestCase):
    """F8: a FAILED `--after` lookup was reported as proven-wrong."""

    def test_an_errored_after_lookup_says_the_READ_failed(self):
        """`2>/dev/null` made an errored query look exactly like an absent
        item, and the call site routed that to half_wired() -- the did-not-land
        refusal, the one that prints "delete #N and re-run" -- over a READ that
        failed."""
        board_after = [
            (101, "First thing on the board"),
            (200, "A brand new distinct piece of work"),
            (102, "Second thing"),
        ]
        h = Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, board_after],
            responses=override(create_responses([], []), "projectItems",
                               stdout="", stderr="GraphQL: something broke\n",
                               exit=1),
        )
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("The READ failed, not the write.", out)
        self.assertNotIn("could not find the board item", out)
        self.assertNotIn("delete", out.replace("Do not delete", ""))
        self.assertIn("--adopt 200", out, "must name a safe next action")

    def test_a_genuinely_absent_after_item_still_takes_the_proven_wrong_path(self):
        board_after = [
            (101, "First thing on the board"),
            (200, "A brand new distinct piece of work"),
            (102, "Second thing"),
        ]
        h = Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, board_after],
            responses=override(create_responses([], []), "projectItems",
                               stdout="", exit=0),
        )
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("could not find the board item for #101", out)


class RetryCeilingIsEnforced(unittest.TestCase):
    """F9: only the FORMAT of the two variables was validated, not the wait
    they imply."""

    def test_a_bound_over_the_thirty_second_ceiling_is_refused(self):
        h = Harness("**Design:** none\n")
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run",
                  env={"FILE_ISSUE_READBACK_ATTEMPTS": 50,
                       "FILE_ISSUE_READBACK_DELAY": 10})
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("FILE_ISSUE_READBACK_ATTEMPTS=50", out)
        self.assertIn("FILE_ISSUE_READBACK_DELAY=10", out)
        self.assertIn("30-second ceiling", out)
        self.assertEqual([], h.network_calls())

    def test_the_production_defaults_are_inside_the_ceiling(self):
        h = Harness("**Design:** none\n")
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run",
                  env={"FILE_ISSUE_READBACK_ATTEMPTS": None,
                       "FILE_ISSUE_READBACK_DELAY": None})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_bound_exactly_at_the_ceiling_is_accepted(self):
        # 30 + nothing more: two attempts, one 30-second wait.
        h = Harness("**Design:** none\n")
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run",
                  env={"FILE_ISSUE_READBACK_ATTEMPTS": 2,
                       "FILE_ISSUE_READBACK_DELAY": 30})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class VersionGapArithmetic(unittest.TestCase):
    """F10: the gap subtracted MINOR versions only."""

    def test_a_future_major_version_is_not_reported_as_behind(self):
        """gh 3.1 was reported as 97 releases BEHIND 2.98 -- a wrong number
        stated as confidently as a right one, in the sentence whose whole job
        is making the refusal clearable."""
        h = Harness("**Design:** none\n",
                    probe=probe_rules(version_line="gh version 3.1.0 (2027-01-01)\n",
                                      flag_lines=""))
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("installed gh 3.1.0", out)
        self.assertNotIn("97 release", out)
        self.assertNotIn("93 release", out)
        self.assertIn("major version ahead", out)

    def test_an_older_version_on_the_same_major_still_counts_releases(self):
        h = Harness("**Design:** none\n",
                    probe=probe_rules(version_line="gh version 2.90.0 (2026-06-01)\n",
                                      flag_lines=""))
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("8 release(s) behind 2.98.0", out)
        self.assertIn("4 release(s) behind 2.94.0", out)


class AbsentRefusalWording(unittest.TestCase):
    """F11a: "Add it by hand" asserted a write that had in fact succeeded."""

    def test_the_absent_refusal_does_not_claim_nothing_was_written(self):
        h = Harness("**Design:** none\n",
                    boards=[PRE_BOARD, BOARD_WITHOUT_200],
                    responses=create_responses([], []))
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertNotIn("Add it by hand", out,
                         "item-add and the position write both returned "
                         "without error before this read")
        self.assertIn("WITHOUT error", out)
        self.assertIn("--adopt 200", out)
        self.assertNotIn("delete", out.replace("Do not delete", ""))

    # F11b (test_the_workflow_doc_qualifies_the_dry_run_duplicate_check) is
    # intentionally left behind here: it asserted that Photos' own
    # docs/WORKFLOW.md documents the --dry-run/create-mode gating, which is a
    # Photos documentation-conformance check, not coverage of this script.


class AdoptDisclosesTheMove(unittest.TestCase):
    """F12: adopt silently MOVED a boarded issue, showing only the
    destination.

    Adopt refuses rather than reconciles for parent, blocked-by and blocks. It
    cannot for position -- all four placement answers are mandatory, so a
    position is always named and refusing would make adopt unusable for
    re-prioritising. So the fix is disclosure, not refusal.
    """

    def test_the_summary_names_the_current_slot_and_says_it_moves(self):
        # #200 sits third on ADOPT_PRE_BOARD, following #102.
        h = adopt_harness()
        r = h.run(*adopt_args(), "--no-parent", "--after", "101", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        line = position_line(r.stdout)
        self.assertIn("after #101", line)
        self.assertIn("currently at position 3", line)
        self.assertIn("following #102", line)
        self.assertIn("MOVES it", line)

    def test_a_position_that_is_already_correct_says_it_does_not_move(self):
        h = adopt_harness()
        r = h.run(*adopt_args(), "--no-parent", "--after", "102", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        line = position_line(r.stdout)
        self.assertIn("currently at position 3", line)
        self.assertIn("does NOT move it", line)

    def test_an_issue_not_yet_on_the_board_says_so_in_the_position_line(self):
        off_board = [(101, "First thing on the board"), (102, "Second thing")]
        h = adopt_harness(boards=[off_board, ADOPT_POST_BOARD])
        r = h.run(*adopt_args(), "--no-parent", "--after", "101", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        line = position_line(r.stdout)
        self.assertIn("not currently on the board", line)
        self.assertNotIn("MOVES it", line)

    def test_the_top_of_board_answer_discloses_the_move_too(self):
        h = adopt_harness()
        r = h.run(*adopt_args(), "--no-parent", "--top", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        line = position_line(r.stdout)
        self.assertIn("top of board", line)
        self.assertIn("currently at position 3", line)
        self.assertIn("MOVES it", line)


def comment_calls(h):
    """Every real `gh issue comment` argv this run made."""
    return [c for c in h.calls() if c[:2] == ["issue", "comment"]]


def comment_body(call):
    """The --body argument of a `gh issue comment` argv."""
    return call[call.index("--body") + 1]


class AdoptRecordsTheMove(unittest.TestCase):
    """F13: disclosure BEFORE the move was only half of it.

    The screen said "this MOVES it", the operator said yes, and the slot the
    issue came from was then recorded nowhere -- a real prior priority
    decision, unrecoverable the moment it was overwritten. So an adopt that
    moves an issue now comments on it naming both slots, and one that does not
    move it writes nothing.

    The judgement is NOT recomputed here: the script latches it in the same
    branch that prints the position line, so the screen and the comment cannot
    disagree, and the landing ordinal is the one the read-back itself proved.
    """

    def test_a_move_posts_one_comment_naming_both_slots(self):
        # #200 sits third on ADOPT_PRE_BOARD following #102, and lands second
        # on ADOPT_POST_BOARD following #101.
        h = adopt_harness()
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = comment_calls(h)
        self.assertEqual(1, len(calls), calls)
        self.assertIn("200", calls[0])
        body = comment_body(calls[0])
        self.assertIn("position 3", body)
        self.assertIn("following #102", body)
        self.assertIn("position 2", body)
        self.assertIn("following #101", body)
        self.assertIn("move recorded      ok", r.stdout)

    def test_the_comment_says_who_wrote_it_and_why(self):
        # The first line of the body carries the two slots. Everything AFTER
        # that first line is what makes the comment interpretable by someone
        # reading #200 months later with no memory of this run: it names the
        # tool that wrote it, the board it was wiring onto, and the reason the
        # record exists at all. Until the call log stopped truncating multi-
        # line arguments, no assertion could see past that first line, so this
        # whole trailer could have been deleted from the script with every
        # test still passing.
        h = adopt_harness()
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        body = comment_body(comment_calls(h)[0])
        self.assertIn("Recorded automatically by", body)
        self.assertIn("scripts/file_issue.sh", body)
        # PROJECT_NUMBER in the script -- the board this issue was wired onto.
        self.assertIn("project 2", body)
        self.assertIn("recoverable", body)
        # And the trailer is genuinely on its own line, below the summary --
        # proof the logged argument survived the newline rather than being
        # reassembled from fragments.
        self.assertGreater(len(body.splitlines()), 1, body)

    def test_a_position_that_does_not_change_posts_nothing(self):
        # Asking for the slot it already holds: still third, still after #102.
        h = adopt_harness(boards=[ADOPT_PRE_BOARD, ADOPT_PRE_BOARD])
        r = h.run(*adopt_args(), "--no-parent", "--after", "102")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([], comment_calls(h))
        self.assertIn("does NOT move it", position_line(r.stdout))

    def test_an_issue_not_yet_on_the_board_posts_nothing_and_succeeds(self):
        # No origin slot exists, so there is nothing to record -- and the run
        # must not trip over the absent one.
        off_board = [(101, "First thing on the board"), (102, "Second thing")]
        h = adopt_harness(boards=[off_board, ADOPT_POST_BOARD],
                          item_by_number="")
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([], comment_calls(h))
        self.assertIn("#200 is wired", r.stdout)

    def test_a_move_to_the_top_reads_as_the_top_not_an_empty_number(self):
        top_board = [
            (200, "An existing issue being wired"),
            (101, "First thing on the board"),
            (102, "Second thing"),
        ]
        h = adopt_harness(boards=[ADOPT_PRE_BOARD, top_board])
        r = h.run(*adopt_args(), "--no-parent", "--top")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = comment_calls(h)
        self.assertEqual(1, len(calls), calls)
        body = comment_body(calls[0])
        self.assertIn("to position 1 (the top of the board)", body)
        self.assertIn("following #102", body)
        self.assertNotIn("following #)", body)
        self.assertNotIn("following # ", body)

    def test_a_move_away_from_the_top_reads_the_origin_as_the_top(self):
        from_top = [
            (200, "An existing issue being wired"),
            (101, "First thing on the board"),
            (102, "Second thing"),
        ]
        h = adopt_harness(boards=[from_top, ADOPT_POST_BOARD])
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        body = comment_body(comment_calls(h)[0])
        self.assertIn("from position 1 (the top of the board)", body)
        self.assertIn("to position 2 (following #101)", body)
        self.assertNotIn("following #)", body)
        self.assertNotIn("following # ", body)

    def test_a_position_that_never_verifies_posts_no_comment(self):
        # The board comes back with #200 still following #102 after a run that
        # asked for #101, which is the half-wired path. A comment claiming a
        # move that did not land is worse than no comment.
        h = adopt_harness(boards=[ADOPT_PRE_BOARD, ADOPT_PRE_BOARD])
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual([], comment_calls(h))
        self.assertIn("board position", r.stdout + r.stderr)

    def test_a_failed_comment_warns_with_both_slots_and_still_exits_zero(self):
        # The wiring landed and read back correct. A failed comment must not
        # tell the operator to delete a correctly wired issue, and must not
        # fail the run -- but it must be impossible to miss.
        h = Harness(
            "**Design:** none\n",
            boards=[ADOPT_PRE_BOARD, ADOPT_POST_BOARD],
            responses=[{"match": "issue comment", "stdout": "",
                        "stderr": "HTTP 502", "exit": 1}] + adopt_responses(),
        )
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        err = r.stderr
        self.assertIn("WARNING", err)
        self.assertIn("position 3 (following #102)", err)
        self.assertIn("position 2 (following #101)", err)
        # WHY it failed is the only thing that tells the operator whether to
        # retry now or wait: gh's own stderr, and the exit code it came with.
        # Both reach the operator through one line in the script, and without
        # these two assertions dropping the `2>&1` capture would break nothing.
        self.assertIn("HTTP 502", err)
        self.assertIn("exited 1", err)
        # The half-wired remedies, absent -- asserted by the sentences the
        # `half_wired*` functions actually print, not by the bare word
        # "delete". `MOVE_ERR` interpolates real gh stderr into this same
        # stream, so a future gh message containing "delete" would otherwise
        # fail this test for a reason that has nothing to do with the remedy.
        self.assertNotIn("MISMATCH:", err)
        self.assertNotIn("and re-run. Do not assume it is fine.", err)
        self.assertNotIn("Do not delete #200", err)
        self.assertNotIn("Finish it by hand", err)
        self.assertNotIn("HALF-WIRED", r.stdout + err)
        self.assertIn("#200 is wired", r.stdout)

    def test_create_mode_posts_nothing_and_trips_no_unset_variable(self):
        # Create mode never runs the latching branch, so every variable the
        # move record reads must carry a default or `set -u` kills the run on
        # the commonest filing shape.
        board_after = [
            (101, "First thing on the board"),
            (200, "A brand new distinct piece of work"),
            (102, "Second thing"),
            (103, "Third thing"),
        ]
        h = Harness("**Design:** none\n", boards=[PRE_BOARD, board_after],
                    responses=create_responses([], []))
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([], comment_calls(h))
        self.assertNotIn("unbound variable", r.stdout + r.stderr)
        self.assertIn("#200 is created", r.stdout)

    def test_dry_run_with_a_move_posts_nothing(self):
        h = adopt_harness()
        r = h.run(*adopt_args(), "--no-parent", "--after", "101", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("MOVES it", position_line(r.stdout))
        self.assertEqual([], comment_calls(h))
        self.assertTrue(wrote_nothing(h))


class FakeGhRuleOrder(unittest.TestCase):
    """F14: the two GraphQL markers are distinct and neither shadows the
    other -- but only because their rules come BEFORE the generic
    `projectItems` rule. Nothing asserted that, and a reorder would make
    `test_missing_from_the_board_fails_loudly` unable to fail."""

    @staticmethod
    def _index(rules, match):
        for i, rule in enumerate(rules):
            if rule["match"] == match:
                return i
        raise AssertionError("no rule matching %r" % match)

    def test_the_marked_lookups_come_before_the_generic_one(self):
        create = create_responses([], [])
        self.assertLess(self._index(create, "boardMembershipCorroboration"),
                        self._index(create, "projectItems"))
        adopt = adopt_responses()
        for marker in ("boardItemByIssueNumber", "boardMembershipCorroboration"):
            self.assertLess(self._index(adopt, marker),
                            self._index(adopt, "projectItems"),
                            "%s must be answerable separately" % marker)

    def test_the_adopt_prefetch_comes_before_the_read_back(self):
        """The pre-fetch's field list CONTAINS the read-back's as a substring,
        so the order is what tells them apart."""
        adopt = adopt_responses()
        self.assertLess(
            self._index(adopt, "--json state,body,parent,blockedBy,blocking"),
            self._index(adopt, "--json parent,blockedBy,blocking"))

    def test_the_markers_the_script_emits_are_the_ones_the_fake_matches(self):
        text = FILE_ISSUE.read_text()
        for marker in ("boardItemByIssueNumber", "boardMembershipCorroboration"):
            self.assertIn(marker, text,
                          "the fake keys on a marker the script no longer emits")


# ---------------------------------------------------------------------------
# U3. The generalized, config-driven engine.
#
# ConfigValidation: a config with zero shapes, or a shape referencing an
# undefined label, must refuse with a clear offline error rather than a
# silent default (U3 edge case). PluckdConfig: a Pluckd-shaped config drives
# correct behavior against a genuinely distinct vocabulary (AE2), proving the
# schema is not over-fit to Photos' three shapes. BoardShIntegration:
# board.sh's config-driven query still emits the unchanged self-check line
# to stderr (U3's integration scenario).
# ---------------------------------------------------------------------------

class ConfigValidation(unittest.TestCase):
    """R2/KTD5: the config schema is validated offline, before any network
    call, naming the field or shape that is wrong -- never a silent default
    that lets an empty or underspecified vocabulary through."""

    def test_zero_shapes_refuses_with_a_clear_error(self):
        h = Harness("**Design:** none\n")
        bad = dict(PHOTOS_CONFIG)
        bad["shapes"] = []
        h.config_path.write_text(json.dumps(bad))
        r = h.run(*full_args(h.body_file), "--no-parent", "--top")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("zero shapes", out)
        self.assertFalse(h.called("issue", "create", "--title"))

    def test_a_shape_with_an_empty_labels_list_refuses_naming_the_shape(self):
        h = Harness("**Design:** none\n")
        bad = dict(PHOTOS_CONFIG)
        bad["shapes"] = [{"name": "work", "labels": []}]
        h.config_path.write_text(json.dumps(bad))
        r = h.run(*full_args(h.body_file), "--no-parent", "--top")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("no labels", out)
        self.assertIn("work", out)
        self.assertFalse(h.called("issue", "create", "--title"))

    def test_a_shape_missing_the_labels_key_entirely_also_refuses(self):
        h = Harness("**Design:** none\n")
        bad = dict(PHOTOS_CONFIG)
        bad["shapes"] = [{"name": "work"}]
        h.config_path.write_text(json.dumps(bad))
        r = h.run(*full_args(h.body_file), "--no-parent", "--top")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no labels", r.stdout + r.stderr)

    def test_a_missing_config_file_refuses_before_any_network_call(self):
        h = Harness("**Design:** none\n")
        r = h.run("--config", str(h.dir / "does-not-exist.json"),
                  *full_args(h.body_file), "--no-parent", "--top")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--config", r.stdout + r.stderr)
        self.assertFalse(h.called("issue", "create", "--title"))

    def test_malformed_json_refuses_with_a_clear_error(self):
        h = Harness("**Design:** none\n")
        h.config_path.write_text("{not valid json")
        r = h.run(*full_args(h.body_file), "--no-parent", "--top")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not valid JSON", r.stdout + r.stderr)

    def _review_config(self, value):
        h = Harness("**Design:** none\n")
        cfg = dict(PHOTOS_CONFIG)
        cfg["human_review_required"] = value
        h.config_path.write_text(json.dumps(cfg))
        return h

    def test_human_review_required_absent_is_accepted(self):
        # Covers AE4: a missing key means true. The skill, not the engine,
        # acts on it; the engine only has to accept it.
        h = Harness("**Design:** none\n")
        assert "human_review_required" not in PHOTOS_CONFIG
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_human_review_required_booleans_are_accepted(self):
        for value in (True, False):
            with self.subTest(value=value):
                h = self._review_config(value)
                r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_human_review_required_old_tier_refuses_naming_legal_values(self):
        # Covers AE5. No migration message for the old string tiers.
        h = self._review_config("agent")
        r = h.run(*full_args(h.body_file), "--no-parent", "--top")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("human_review_required", out)
        self.assertIn("agent", out)
        self.assertIn("true or false", out)
        self.assertFalse(h.called("issue", "create", "--title"))

    def test_human_review_required_non_boolean_values_refuse(self):
        # The string "true" is the one a value check (rather than a type
        # check) would let through; null is the one jq's `//` would read as
        # absent.
        for value in ("true", "false", "required", "optional", None, 1, 0, [], {}):
            with self.subTest(value=value):
                h = self._review_config(value)
                r = h.run(*full_args(h.body_file), "--no-parent", "--top")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("human_review_required", r.stdout + r.stderr)
                self.assertFalse(h.called("issue", "create", "--title"))


class PluckdConfig(unittest.TestCase):
    """AE2: a Pluckd-shaped config (shapes work/bug/decision/plan-parent, no
    your-run, project board #1, no Design-line requirement) drives the same
    four placement questions, applies the vocabulary IT names, and writes to
    ITS repo -- not Photos'."""

    def test_filing_a_bug_shaped_issue_uses_pluckds_repo_and_label(self):
        # The read-back re-reads the board, so the SECOND page must already
        # carry the new issue (#200) -- the same shape ReadBack._harness uses
        # -- or a correctly wired filing would fail its own read-back.
        board_after = [
            (101, "First thing on the board"),
            (200, "A Pluckd bug"),
            (102, "Second thing"),
            (103, "Third thing"),
        ]
        h = Harness("Some body, no Design field.\n", config=PLUCKD_CONFIG,
                    boards=[PRE_BOARD, board_after],
                    responses=create_responses([], []))
        r = h.run(
            "--title", "A Pluckd bug", "--body-file", str(h.body_file),
            "--shape", "bug", "--no-parent", "--after", "101",
            "--blocked-by", "none", "--blocks", "none",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        create_call = create_argv(h)
        self.assertIsNotNone(create_call)
        self.assertIn("--repo", create_call)
        self.assertEqual("jffriend/pluckd",
                         create_call[create_call.index("--repo") + 1])
        self.assertIn("bug", create_call)
        # "needs-joe" is Photos-only vocabulary; it must not leak into a
        # config that never defined it.
        self.assertNotIn("needs-joe", create_call)

    def test_your_run_is_not_a_recognized_shape_under_pluckds_config(self):
        h = Harness("Some body.\n", config=PLUCKD_CONFIG)
        r = h.run(
            "--title", "T", "--body-file", str(h.body_file),
            "--shape", "your-run", "--no-parent", "--top",
            "--blocked-by", "none", "--blocks", "none",
        )
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("--shape", out)
        self.assertIn("work, bug, decision, plan-parent", out)

    def test_a_plan_derived_body_does_not_require_a_parent_when_the_config_does_not_require_it(self):
        # Pluckd's config sets design_line_required=false, so a body whose
        # Design: field links into plan_dir must NOT trigger the parenting
        # refusal the way it would under Photos' config.
        body = (
            "Some body.\n\n**Design:** [U1](https://github.com/jffriend/pluckd/"
            "blob/main/docs/plans/2026-01-01-001-feat-x.md#u1)\n"
        )
        h = Harness(body, config=PLUCKD_CONFIG)
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class BoardShIntegration(unittest.TestCase):
    """R2/KTD3: board.sh reads the same --config file file_issue.sh reads,
    and its self-check line ('pages=N rows=N distinct=N') is unchanged --
    still written to stderr, still in that shape -- once the underlying
    GraphQL query is config-driven instead of hardcoding the login and
    project number."""

    def _env(self, h):
        env = dict(os.environ)
        env["PATH"] = f"{h.bin}:{env['PATH']}"
        env["FAKE_GH_DIR"] = str(h.dir)
        return env

    def test_the_self_check_line_is_emitted_to_stderr(self):
        h = Harness("**Design:** none\n")  # sets up the fake gh + a config
        out_path = h.dir / "board_out.json"
        r = subprocess.run(
            ["bash", str(BOARD_SH), "--config", str(h.config_path), str(out_path)],
            capture_output=True, text=True, env=self._env(h), check=False,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual("", r.stdout,
                         "the self-check line must go to stderr, not stdout")
        self.assertRegex(r.stderr, r"pages=\d+ rows=\d+ distinct=\d+")
        self.assertIn(f"rows={len(DEFAULT_BOARD)} distinct={len(DEFAULT_BOARD)}",
                      r.stderr)

    def test_config_and_output_path_are_accepted_in_either_order(self):
        h = Harness("**Design:** none\n")
        out_path = h.dir / "board_out2.json"
        r = subprocess.run(
            ["bash", str(BOARD_SH), str(out_path), "--config", str(h.config_path)],
            capture_output=True, text=True, env=self._env(h), check=False,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stderr, r"pages=\d+ rows=\d+ distinct=\d+")

    def test_a_config_missing_owner_refuses_before_any_query(self):
        h = Harness("**Design:** none\n")
        bad = dict(PHOTOS_CONFIG)
        del bad["owner"]
        h.config_path.write_text(json.dumps(bad))
        out_path = h.dir / "board_out3.json"
        r = subprocess.run(
            ["bash", str(BOARD_SH), "--config", str(h.config_path), str(out_path)],
            capture_output=True, text=True, env=self._env(h), check=False,
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("owner", r.stderr)


if __name__ == "__main__":
    unittest.main()
