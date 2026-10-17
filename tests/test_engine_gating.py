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

Run:  python3 tests/test_engine_gating.py
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


# The Status field's numeric id in the fake's fields listing. board.sh asks
# for the field by this id, because the REST items endpoint's `fields`
# parameter takes ids, not names (`fields=Status` is an HTTP 400).
STATUS_FIELD_ID = 77001
FIELDS_WITH_STATUS = [
    {"id": 77000, "name": "Title", "data_type": "title"},
    {"id": STATUS_FIELD_ID, "name": "Status", "data_type": "single_select"},
]


def board_page(rows, next_cursor=None, status="Backlog"):
    """One page as `gh api -i users/{owner}/projectsV2/{n}/items` prints it.

    The status line, the response headers, a blank line, then the REST item
    array. A page with more after it carries a `Link` header whose
    `rel="next"` URL holds the `after` cursor -- listed AFTER a `rel="prev"`
    entry, so a parser that takes the first URL in the header reads the
    wrong one. Header lines end in CRLF, as real gh prints them.
    """
    items = []
    for num, title in rows:
        items.append(
            {
                "id": 900000 + num,
                "node_id": "PVTI_%d" % num,
                "content_type": "Issue",
                "content": {"number": num, "title": title, "state": "open"},
                "fields": [
                    {
                        "id": STATUS_FIELD_ID,
                        "name": "Status",
                        "data_type": "single_select",
                        "value": {"name": {"raw": status, "html": status}},
                    }
                ],
            }
        )
    head = "HTTP/2.0 200 OK\nContent-Type: application/json; charset=utf-8\r\n"
    if next_cursor is not None:
        base = "https://api.github.com/user/1/projectsV2/2/items?per_page=100"
        head += ('Link: <%s&before=PREV>; rel="prev", <%s&after=%s>; rel="next"\r\n'
                 % (base, base, next_cursor))
    return head + "\r\n" + json.dumps(items)


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

# The duplicate check's open-issue listing, `GET repos/{repo}/issues?state=
# open&per_page=100&page=N`. The listing includes pull requests.
TITLES_MATCH = "/issues?state=open"


def titles_pages(entries):
    """The open-issue listing as the pages the script asks for, in order.

    100 to a page, the size the script asks for. A full last page is followed
    by an empty one, because the fake repeats its last reply: without the
    empty page a run asking for page N+1 would get page N again.
    """
    pages = [entries[i:i + 100] for i in range(0, len(entries), 100)] or [[]]
    if len(pages[-1]) == 100:
        pages.append([])
    return [json.dumps(p) for p in pages]


# Every issue's numeric REST `id` in the fake: what the sub-issue and
# dependency endpoints take, never the number. Offset so an id can never be
# mistaken for a number, and so a test can turn one back into the other.
ISSUE_ID_BASE = 7000000


def issue_id(n):
    return ISSUE_ID_BASE + int(n)


def issue_reply(n, state="open", body="", parent=None, labels=()):
    """`GET repos/{repo}/issues/{n}` as GitHub returns it.

    `parent_issue_url` is ABSENT on a parentless issue, not null -- measured
    2026-10-15 -- so it is added only when there is a parent. `labels` is
    always present, as an array of label objects, empty when there are none.
    """
    d = {"id": issue_id(n), "number": int(n), "state": state, "body": body,
         "labels": [{"name": name} for name in labels],
         "html_url": "https://github.com/jffriend/photo-consolidation/issues/%d" % int(n)}
    if parent:
        d["parent_issue_url"] = (
            "https://api.github.com/repos/jffriend/photo-consolidation/issues/%d"
            % int(parent))
    return d


# The issues the tests name as a parent, a blocker or a blocked issue. Create
# reads each once for its id before writing anything (#14 KTD3). No number
# here is a prefix of another, because the fake matches on substrings.
REFERENCED = (55, 63, 70, 77, 122, 133, 240)


def referenced_issue_rules():
    """One `GET repos/{repo}/issues/{n}` rule per referenced issue.

    These go LAST in a table: `issues/55` is also a substring of the
    `issues/55/sub_issues` write, which the `-X POST` rule must answer first.
    """
    return [{"match": "issues/%d" % n, "stdout": json.dumps(issue_reply(n))}
            for n in REFERENCED]

def probe_rules(version_line=GH_VERSION_LINE):
    """The fake's answer to `gh --version`, the only thing the probe asks.

    This belongs in the BASE table, not in `create_responses()`: most gate
    tests build a `Harness` with no response table at all.
    """
    return [{"match": "--version", "stdout": version_line}]


GRAPHQL_BLOCKED_RULE = {
    "match": "graphql", "exit": 1, "stdout": "",
    "stderr": "gh: Resource not accessible by integration (HTTP 403)\n",
}

# How a Claude Code cloud session's GitHub proxy refuses the user-owned board
# (measured 2026-10-16, #14): every `users/{owner}/projectsV2/...` path.
BOARD_REFUSED_RULE = {
    "match": "projectsV2", "exit": 1, "stdout": "",
    "stderr": ("gh: This GitHub API path is not available: sessions are bound "
               "to their configured repositories. Use repository-scoped "
               "endpoints (repos/{owner}/{repo}/...). (HTTP 403)\n"),
}

# The environment variable that turns cloud mode on (#14 KTD2). The harness
# unsets it unless a test sets it, so a suite run inside a cloud session does
# not turn every test into a cloud run (#14 KTD11).
CLOUD_ENV_VAR = "CLAUDE_CODE_REMOTE"
CLOUD_ENV = {CLOUD_ENV_VAR: "true"}


class Harness:
    """A temp dir holding a body file, a fake `gh`, and its response table."""

    def __init__(self, body, boards=None, responses=None, probe=None,
                 board_exits=None, config=None, board_stdouts=None,
                 fields=None, graphql_blocked=False, board_refused=False):
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
        # One single-page board per board READ, in order. `board_stdouts`
        # replaces that with raw page replies, one per board-page CALL, which
        # is how a test hands back a board that spans several pages.
        pages = ([board_page(b) for b in boards] if board_stdouts is None
                 else list(board_stdouts))
        titles = titles_pages([{"number": n, "title": t} for n, t in boards[0]])
        project = self.config["project_number"]
        board_rule = {"match": "projectsV2/%s/items?per_page=" % project,
                      "stdouts": pages}
        if board_exits is not None:
            board_rule["exits"] = list(board_exits)
        # `graphql_blocked` refuses every GraphQL call the way a session
        # without GraphQL access does (#14 KTD10): exit 1, gh's `(HTTP 403)`
        # suffix on stderr. It goes FIRST, so no other rule can answer one.
        table = [GRAPHQL_BLOCKED_RULE] if graphql_blocked else []
        # `board_refused` answers every board path the way a cloud session's
        # proxy does, ahead of the board rules below.
        if board_refused:
            table.append(BOARD_REFUSED_RULE)
        table += [
            board_rule,
            {"match": "projectsV2/%s/fields" % project,
             "stdout": json.dumps(FIELDS_WITH_STATUS if fields is None
                                  else fields)},
            {"match": TITLES_MATCH, "stdouts": titles},
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
        e.pop(CLOUD_ENV_VAR, None)
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
        """True when one call carries every needle."""
        for call in self.calls():
            joined = " ".join(call)
            if all(n in joined for n in needles):
                return True
        return False

    def network_calls(self):
        """Every call except the probe's offline `gh --version`."""
        return [call for call in self.calls() if call != ["--version"]]

    def create_posts(self):
        """Every issue-create call: `gh api -X POST repos/{repo}/issues`."""
        return [c for c in self.calls()
                if c[:3] == ["api", "-X", "POST"] and len(c) > 3
                and c[3].startswith("repos/") and c[3].endswith("/issues")
                and c[3].count("/") == 3]

    def created(self):
        """True when this run sent an issue create."""
        return bool(self.create_posts())


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
            self.h.created(),
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
        self.assertIn("labels[]=bug", call)

    def test_investigation_shape_carries_the_investigation_label(self):
        call = self._create_call_for("investigation", "A brand new investigation")
        self.assertIn("labels[]=investigation", call)

    def test_work_shape_still_carries_the_work_label(self):
        call = self._create_call_for("work", "A brand new distinct piece of work")
        self.assertIn("labels[]=work", call)


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
        self.assertFalse(h.created())

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
        self.assertFalse(h.created())

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
        self.assertFalse(h.created())



PRE_BOARD = [
    (101, "First thing on the board"),
    (102, "Second thing"),
    (103, "Third thing"),
]


# The REST board-half calls, as the fake matches them. Item-add is `POST
# users/{owner}/projectsV2/{n}/items -f type=Issue -F id=<issue id>`; its rule
# must come BEFORE the generic `-X POST` rule, which it also matches. The
# single-item read the read-back corroborates with is `GET .../items/<id>`,
# and nothing else carries `/items/`: the listing is `items?per_page=`.
ITEM_ADD_MATCH = "items -f type=Issue"
ITEM_READ_MATCH = "/items/"
# The position write is the one GraphQL call left (#14 KTD2).
POSITION_MATCH = "updateProjectV2ItemPosition"


def item_reply(n, node_id=None):
    """A REST project item. Every item the fake's board listing carries has
    numeric id 900000 + its issue number and node id PVTI_<number> (see
    board_page); item-add answers in the same shape."""
    return {"id": 900000 + int(n), "node_id": node_id or "PVTI_%d" % int(n),
            "content_type": "Issue", "content": {"number": int(n)}}


def item_read_rule(corroborate):
    """The read-back's single-item read: the item when `corroborate` is
    truthy, a 404 otherwise -- the corroborating read agrees it is absent."""
    if corroborate:
        return {"match": ITEM_READ_MATCH, "stdout": json.dumps(item_reply(200))}
    return {"match": ITEM_READ_MATCH, "exit": 1,
            "stderr": "gh: Not Found (HTTP 404)\n"}


# The relationship read-back's three REST reads of #200 (#14 KTD6). The two
# dependency lists come before the bare issue read, which is a substring of
# both.
READ_BLOCKED_MATCH = "issues/200/dependencies/blocked_by?"
READ_BLOCKING_MATCH = "issues/200/dependencies/blocking?"
READ_ISSUE_MATCH = "issues/200"


def dependency_list(numbers):
    """`GET .../dependencies/blocked_by` or `/blocking`: an array of issues."""
    return json.dumps([{"number": int(n), "id": issue_id(n)} for n in numbers])


def create_responses(blocked_by, blocking, parent=None, corroborate=""):
    """Canned replies for the create-and-read-back half.

    The issue create is `POST repos/{repo}/issues` with its title as the first
    field, so `issues -f title=` matches it and nothing else. Item-add is
    answered next, then every other write -- the sub-issue and dependency
    POSTs -- by the generic `-X POST` rule, which must come before the issue
    reads at the end: `issues/55` is a substring of `issues/55/sub_issues`.

    The read-back is three REST reads of #200: the issue (its parent) and its
    two dependency lists.

    `corroborate` makes the single-item read return the item when the board
    LISTING does not show the issue. Empty by default -- the corroborating
    read agrees the issue is not there.
    """
    return [
        {"match": "issues -f title=", "stdout": json.dumps(issue_reply(200))},
        {"match": ITEM_ADD_MATCH, "stdout": json.dumps(item_reply(200))},
        {"match": "-X POST", "stdout": "{}"},
        {"match": POSITION_MATCH, "stdout": json.dumps({"data": {}})},
        item_read_rule(corroborate),
        {"match": READ_BLOCKED_MATCH, "stdout": dependency_list(blocked_by)},
        {"match": READ_BLOCKING_MATCH, "stdout": dependency_list(blocking)},
        {"match": READ_ISSUE_MATCH,
         "stdout": json.dumps(issue_reply(200, parent=parent))},
        *referenced_issue_rules(),
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
        self.assertTrue(h.created())

    def test_stdin_is_ignored(self):
        # An `n` that the old prompt would have read as "no" changes nothing.
        h = self._harness()
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101",
                  stdin="n\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(h.created())

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
        self.assertFalse(h.created())
        self.assertFalse(h.called(ITEM_ADD_MATCH))

    def test_file_anyway_files_past_possible_duplicates(self):
        h = self._harness(DUPE_PRE_BOARD, DUPE_POST_BOARD)
        r = h.run(*full_args(h.body_file, **{"--title": DUPE_TITLE}),
                  "--no-parent", "--after", "101", "--file-anyway")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("164", r.stdout)
        self.assertIn("READ-BACK", r.stdout)
        self.assertTrue(h.created())

    def test_a_failed_duplicate_check_stops_rather_than_reading_as_none(self):
        # With no prompt, DUPES is the stop's only input. A listing the
        # checker cannot parse must not come out as "none found" and file.
        h = self._harness()
        table = json.loads((h.dir / "responses.json").read_text())
        for rule in table:
            if rule.get("match") == TITLES_MATCH:
                rule["stdouts"] = ["not json"]
        (h.dir / "responses.json").write_text(json.dumps(table))
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("duplicate check failed", r.stderr)
        self.assertNotIn("POSSIBLE DUPLICATES: none found", r.stdout)
        self.assertFalse(h.created())

    def _harness_with_listing(self, entries):
        h = self._harness()
        table = json.loads((h.dir / "responses.json").read_text())
        for rule in table:
            if rule.get("match") == TITLES_MATCH:
                rule["stdouts"] = titles_pages(entries)
        (h.dir / "responses.json").write_text(json.dumps(table))
        return h

    def _harness_with_open_issue_count(self, count):
        return self._harness_with_listing(
            [{"number": 1000 + i, "title": f"Unrelated open issue {i}"}
             for i in range(count)])

    @staticmethod
    def _listing_calls(h):
        return [c for c in h.calls() if any(TITLES_MATCH in a for a in c)]

    def test_a_pull_request_with_a_matching_title_is_not_a_duplicate(self):
        # The REST listing of open issues includes pull requests. A PR is not
        # an issue a new one could duplicate, so it never reaches the check.
        h = self._harness_with_listing([
            {"number": 300, "title": DUPE_TITLE,
             "pull_request": {"url": "https://api.github.com/repos/x/y/pulls/300"}},
            {"number": 101, "title": "First thing on the board"},
        ])
        r = h.run(*full_args(h.body_file, **{"--title": DUPE_TITLE}),
                  "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("POSSIBLE DUPLICATES: none found", r.stdout)
        self.assertNotIn("#300", r.stdout)
        self.assertTrue(h.created())

    def test_an_issue_with_a_matching_title_on_page_two_is_found(self):
        entries = [{"number": 1000 + i, "title": f"Unrelated open issue {i}"}
                   for i in range(100)]
        entries.append({"number": 164, "title":
                        "Run: re-sort the library into YYYY/MM once the dates are final"})
        h = self._harness_with_listing(entries)
        r = h.run(*full_args(h.body_file, **{"--title": DUPE_TITLE}),
                  "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("164", r.stdout)
        calls = self._listing_calls(h)
        self.assertEqual(2, len(calls), calls)
        self.assertIn("page=2", " ".join(calls[1]))

    def test_a_listing_at_the_limit_warns_that_matches_may_be_missed(self):
        # Issue #17: the check reads at most 500 open issues. A full listing
        # means there may be more, so the run says so, then files as before.
        h = self._harness_with_open_issue_count(500)
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("WARNING: the duplicate check read only the first 500",
                      r.stdout)
        self.assertTrue(h.created())

    def test_the_limit_counts_pull_requests_because_they_fill_the_same_pages(self):
        # 500 raw entries, 100 of them pull requests: only 400 issues were
        # checked, and the listing still stopped at the limit with more
        # possibly unread.
        entries = [{"number": 1000 + i, "title": f"Unrelated open issue {i}"}
                   for i in range(400)]
        entries += [{"number": 2000 + i, "title": f"A pull request {i}",
                     "pull_request": {"url": "x"}} for i in range(100)]
        h = self._harness_with_listing(entries)
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("WARNING: the duplicate check read only the first 500",
                      r.stdout)
        self.assertEqual(5, len(self._listing_calls(h)),
                         "the listing stops at the limit")

    def test_a_listing_under_the_limit_does_not_warn(self):
        h = self._harness_with_open_issue_count(499)
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("WARNING: the duplicate check", r.stdout)
        self.assertIn("POSSIBLE DUPLICATES: none found", r.stdout)

    def test_dry_run_with_possible_duplicates_exits_0_and_writes_nothing(self):
        h = self._harness(DUPE_PRE_BOARD, DUPE_POST_BOARD)
        r = h.run(*full_args(h.body_file, **{"--title": DUPE_TITLE}),
                  "--no-parent", "--after", "101", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("164", r.stdout)
        self.assertFalse(h.created())


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
        self.assertTrue(h.created())

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
        # HALF-WIRED this way. The id must come from the board listing, re-read
        # after item-add fails, since the pre-write listing predates the issue
        # (#14 KTD5).
        responses = override(create_responses([], []), ITEM_ADD_MATCH, exit=1,
                             stderr="gh: Content already exists in this "
                                    "project (HTTP 422)\n")
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
        self.assertIn("i=PVTI_200", positions[0],
                      "the node id the re-read listing carries for #200")
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
    #14 KTD7: every GitHub call now goes through `gh api`, so the probe no
    longer reads `gh issue create/edit --help` or `gh issue view --json` for
    flags and fields the engine does not use. It refuses only when `gh` is not
    on PATH, and prints the installed version for the record.
    """

    ARGS_TAIL = ("--no-parent", "--top", "--dry-run")

    def _run(self, probe, path=None):
        h = Harness("**Design:** none\n", probe=probe)
        r = h.run(*full_args(h.body_file), *self.ARGS_TAIL, path=path)
        return h, r, r.stdout + r.stderr

    def test_a_fake_with_no_flag_probe_answers_proceeds(self):
        # The fake answers only `--version`; a `--help` or bare
        # `issue view --json` call would get `{}` back and refuse.
        h, r, out = self._run(probe_rules())
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("2.98.0", r.stdout, "the version is still printed")
        for call in h.calls():
            self.assertNotIn("--help", call, call)
            self.assertNotEqual(["issue", "view", "--json"], call[:3], call)

    def test_unparseable_version_still_proceeds_and_prints_the_sentinel(self):
        h, r, out = self._run(probe_rules(version_line="gh, but which one?\n"))
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("unknown", r.stdout,
                      "the sentinel prints where the version would go")

    def test_gh_absent_from_path_refuses_saying_so(self):
        h, r, out = self._run(probe_rules(), path=path_without_gh())
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("REFUSED: gh is not on PATH", out)
        self.assertEqual([], h.calls())


class RestWritePath(unittest.TestCase):
    """
    #14 U3: create writes over REST. The issue is one POST; then the parent is
    one sub_issues POST and each blocking link one dependencies POST, each
    carrying a numeric issue `id` -- the parent link and every blocks link the
    NEW issue's, every blocked-by link the blocker's. Every referenced issue
    is read for its id before anything is written (KTD3).
    """

    BOARD_AFTER = [
        (101, "First thing on the board"),
        (200, "A brand new distinct piece of work"),
        (102, "Second thing"),
    ]

    def _run(self, *args, responses=None, blocked=(), blocking=(), parent=None):
        h = Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, self.BOARD_AFTER],
            responses=(responses if responses is not None else
                       create_responses(list(blocked), list(blocking), parent)),
        )
        return h, h.run("--title", "A brand new distinct piece of work",
                        "--body-file", str(h.body_file), "--shape", "work",
                        *args)

    def test_parent_two_blockers_and_one_blocked_issue_are_five_writes(self):
        h, r = self._run("--parent", "55", "--after", "101",
                         "--blocked-by", "122,133", "--blocks", "63",
                         blocked=[122, 133], blocking=[63], parent="55")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(1, len(h.create_posts()), h.calls())
        self.assertEqual(sorted([
            ("55/sub_issues", "sub_issue_id=%d" % issue_id(200)),
            ("200/dependencies/blocked_by", "issue_id=%d" % issue_id(122)),
            ("200/dependencies/blocked_by", "issue_id=%d" % issue_id(133)),
            ("63/dependencies/blocked_by", "issue_id=%d" % issue_id(200)),
        ]), sorted(link_writes(h)))
        self.assertIn("parent             ok (#55)", r.stdout)
        self.assertIn("blocked-by         ok (122,133)", r.stdout)
        self.assertIn("blocks             ok (63)", r.stdout)

    def test_every_link_is_written_after_the_issue_and_every_read_before_it(self):
        h, r = self._run("--parent", "55", "--after", "101",
                         "--blocked-by", "122", "--blocks", "63",
                         blocked=[122], blocking=[63], parent="55")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = h.calls()
        create_at = calls.index(h.create_posts()[0])
        for n in (55, 122, 63):
            reads = [i for i, c in enumerate(calls)
                     if c == ["api", "repos/jffriend/photo-consolidation/issues/%d" % n]]
            self.assertEqual(1, len(reads), "#%d is read once for its id" % n)
            self.assertLess(reads[0], create_at)
        for i, c in enumerate(calls):
            if c[:3] == ["api", "-X", "POST"] and i != create_at:
                self.assertGreater(i, create_at, c)

    def test_the_create_carries_title_body_and_labels(self):
        h, r = self._run("--no-parent", "--after", "101",
                         "--blocked-by", "none", "--blocks", "none")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = h.create_posts()[0]
        self.assertEqual("repos/jffriend/photo-consolidation/issues", argv[3])
        self.assertIn("title=A brand new distinct piece of work", argv)
        self.assertIn("body=@%s" % h.body_file, argv)
        self.assertIn("labels[]=work", argv)

    def test_none_answers_write_no_link_at_all(self):
        h, r = self._run("--no-parent", "--after", "101",
                         "--blocked-by", "none", "--blocks", "none")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([], link_writes(h),
                         "an unanswered relationship is no write, never an empty one")

    def test_a_blocker_that_does_not_exist_refuses_before_the_create(self):
        responses = [{"match": "issues/999", "exit": 1,
                      "stderr": "gh: Not Found (HTTP 404)\n"}] \
            + create_responses([], [])
        h, r = self._run("--no-parent", "--after", "101",
                         "--blocked-by", "999", "--blocks", "none",
                         responses=responses)
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("#999 does not exist", r.stderr)
        self.assertIn("Nothing was created.", r.stderr)
        self.assertFalse(h.created())
        self.assertTrue(wrote_nothing(h))

    def test_a_blocker_that_cannot_be_read_refuses_without_saying_it_is_missing(self):
        responses = [{"match": "issues/122", "exit": 1,
                      "stderr": "gh: Server Error (HTTP 502)\n"}] \
            + create_responses([], [])
        h, r = self._run("--no-parent", "--after", "101",
                         "--blocked-by", "122", "--blocks", "none",
                         responses=responses)
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("#122 could not be read", r.stderr)
        self.assertNotIn("does not exist", r.stderr)
        self.assertIn("Nothing was created.", r.stderr)
        self.assertTrue(wrote_nothing(h))

    def test_a_failed_link_write_warns_and_the_read_back_refuses(self):
        responses = [{"match": "-X POST repos/jffriend/photo-consolidation/"
                               "issues/200/dependencies/blocked_by",
                      "exit": 1, "stderr": "gh: Validation Failed (HTTP 422)\n"}] \
            + create_responses([], [])
        h, r = self._run("--no-parent", "--after", "101",
                         "--blocked-by", "122", "--blocks", "none",
                         responses=responses)
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        err = r.stderr
        self.assertIn("WARNING", err)
        self.assertIn("HTTP 422", err, "gh's own reason reaches the operator")
        self.assertIn("MISMATCH: blocked-by", err)
        self.assertTrue(h.called("updateProjectV2ItemPosition"),
                        "a failed link does not stop the run before the read-back")
        lines = err.splitlines()
        finish = [i for i, ln in enumerate(lines) if ln.startswith("Finish it")]
        self.assertEqual(1, len(finish), err)
        command = lines[finish[0] + 1]
        self.assertEqual(
            "  bash %s --config %s --adopt 200 --no-parent --after 101 "
            "--blocked-by 122 --blocks none" % (FILE_ISSUE, h.config_path),
            command, "the remedy leads with the runnable adopt command")
        tail = "\n".join(lines[finish[0] + 2:])
        self.assertIn("delete #200 and re-run", tail)
        self.assertIn("local session", tail)
        self.assertNotIn("delete", "\n".join(lines[:finish[0] + 2])
                         .replace("Do not delete", ""))

    def test_no_create_goes_through_gh_issue_or_graphql(self):
        h, r = self._run("--parent", "55", "--after", "101",
                         "--blocked-by", "122", "--blocks", "63",
                         blocked=[122], blocking=[63], parent="55")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for call in h.calls():
            joined = " ".join(call)
            self.assertNotEqual(["issue", "create"], call[:2], call)
            self.assertNotEqual(["issue", "list"], call[:2], call)
            if "graphql" in joined:
                # The position write is the only call left on GraphQL.
                self.assertIn(POSITION_MATCH, joined, call)

    def test_the_relationship_read_back_is_three_rest_reads(self):
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
        base = "repos/jffriend/photo-consolidation/issues/200"
        for path in (base, base + "/dependencies/blocked_by?per_page=100",
                     base + "/dependencies/blocking?per_page=100"):
            reads = [c for c in h.calls() if c == ["api", path]]
            self.assertEqual(1, len(reads), (path, h.calls()))
        self.assertFalse([c for c in h.calls() if c[:2] == ["issue", "view"]])


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


def adopt_responses(pre_parent=None, pre_blocked=(), pre_blocking=(),
                    post_parent=None, post_blocked=(), post_blocking=(),
                    state="open", body="**Design:** none\n",
                    issue_stdout=None, write_exit=0,
                    corroborate="", blocked_stdout=None,
                    pre_labels=(), post_labels=(), delete_exit=0,
                    after_delete_stdout=None):
    """Canned replies for an adopt run.

    The PRE-FETCH and the READ-BACK read the same three REST paths -- the
    issue and its two dependency lists -- so each rule answers its FIRST call
    with the pre-write state and every later one with the post-write state.
    They must differ: the pre-fetch has to show no conflicting links or the
    KD2 refusal fires, while the read-back has to show the links just written.

    ORDER MATTERS, because the fake matches substrings. Item-add comes first,
    since it also carries `-X POST`; then the `-X POST` rule, since every
    write's path also names an issue a read rule matches. The two
    dependency-list reads come before the bare issue read `issues/200`, which
    is a substring of both.
    """
    if issue_stdout is None:
        issue_stdout = json.dumps(issue_reply(ADOPT_NUM, state=state, body=body,
                                              parent=pre_parent,
                                              labels=pre_labels))
    if blocked_stdout is None:
        blocked_stdout = dependency_list(pre_blocked)
    return [
        {"match": ITEM_ADD_MATCH,
         "stdout": json.dumps(item_reply(200, node_id="PVTI_from_item_add"))},
        {"match": "-X POST", "stdout": "{}", "exit": write_exit},
        # The label removal (#14 U4) names `issues/200`, so it must be
        # answered before the issue read below.
        {"match": "-X DELETE", "stdout": "", "exit": delete_exit,
         "stderr": "" if delete_exit == 0 else "gh: Server Error (HTTP 500)\n"},
        {"match": POSITION_MATCH, "stdout": json.dumps({"data": {}})},
        item_read_rule(corroborate),
        {"match": READ_BLOCKED_MATCH,
         "stdouts": [blocked_stdout, dependency_list(post_blocked)]},
        {"match": READ_BLOCKING_MATCH,
         "stdouts": [dependency_list(pre_blocking), dependency_list(post_blocking)]},
        {"match": READ_ISSUE_MATCH,
         # A third reply, when given, answers the fresh read after a label
         # removal, so a test can tell it from the stale read-back reply.
         "stdouts": [issue_stdout,
                     json.dumps(issue_reply(ADOPT_NUM, state=state, body=body,
                                            parent=post_parent,
                                            labels=post_labels))]
                    + ([] if after_delete_stdout is None
                       else [after_delete_stdout])},
        *referenced_issue_rules(),
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


def link_writes(h):
    """Every relationship write, as (path after `/issues/`, its id field).

    `("55/sub_issues", "sub_issue_id=7000200")` puts #200 under #55;
    `("200/dependencies/blocked_by", "issue_id=7000122")` makes #200 blocked
    by #122.
    """
    out = []
    for call in h.calls():
        if call[:3] != ["api", "-X", "POST"] or len(call) < 4:
            continue
        path = call[3]
        if "/sub_issues" in path or "/dependencies/" in path:
            fields = [a for a in call[4:] if "_id=" in a]
            out.append((path.split("/issues/", 1)[1],
                        fields[0] if fields else ""))
    return out


def create_argv(h):
    posts = h.create_posts()
    return posts[0] if posts else None


WRITE_METHODS = ("POST", "PATCH", "PUT", "DELETE")


def wrote_nothing(h):
    """True when no call in this run changed anything on the server."""
    for call in h.calls():
        joined = " ".join(call)
        if call[:2] in (["issue", "edit"], ["issue", "create"]):
            return False
        if call[:1] == ["api"] and "-X" in call \
                and call[call.index("-X") + 1] in WRITE_METHODS:
            return False
        if POSITION_MATCH in joined:
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
        h = Harness("**Design:** none\n",
                    responses=[{"match": "issues/999", "exit": 1,
                                "stderr": "gh: Not Found (HTTP 404)\n"}]
                    + adopt_responses())
        r = h.run(*adopt_args(num="999"), "--no-parent", "--top")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("999", r.stdout + r.stderr)
        self.assertTrue(wrote_nothing(h))

    def test_a_closed_issue_refuses_before_any_write(self):
        # REST spells the state in lower case.
        h = adopt_harness(state="closed")
        r = h.run(*adopt_args(), "--no-parent", "--top")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("is closed, not open", out)
        self.assertTrue(wrote_nothing(h))

    def test_a_parentless_issue_has_no_parent_key_and_reads_as_no_parent(self):
        # GitHub OMITS parent_issue_url on a parentless issue (measured
        # 2026-10-15). Absent is a legal answer, so adopt must read it as "no
        # parent" and write the one asked for.
        h = adopt_harness(post_parent="55")
        self.assertNotIn("parent_issue_url",
                         issue_reply(ADOPT_NUM), "precondition: key absent")
        r = h.run(*adopt_args(), "--parent", "55", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([("55/sub_issues", "sub_issue_id=%d" % issue_id(200))],
                         link_writes(h))

    def test_an_issue_reply_without_number_and_state_refuses(self):
        # {"message": ...} is a reply whose every field extracts as absent,
        # and absent is a legal parent answer. Only its shape tells it apart.
        h = adopt_harness(issue_stdout=json.dumps({"message": "Not Found"}))
        r = h.run(*adopt_args(), "--no-parent", "--top")
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("could not be read", r.stderr)
        self.assertTrue(wrote_nothing(h))

    def test_a_malformed_parent_url_refuses_rather_than_reading_as_no_parent(self):
        reply = issue_reply(ADOPT_NUM)
        reply["parent_issue_url"] = "https://api.github.com/repos/x/y/issues/"
        h = adopt_harness(issue_stdout=json.dumps(reply))
        r = h.run(*adopt_args(), "--no-parent", "--top")
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("parent", r.stderr)
        self.assertIn("could not be read", r.stderr)
        self.assertTrue(wrote_nothing(h))

    def test_a_dependency_list_that_is_not_an_array_refuses(self):
        # An object here would extract as no blockers, which is legal too.
        h = adopt_harness(blocked_stdout=json.dumps({"message": "Not Found"}))
        r = h.run(*adopt_args(), "--no-parent", "--top")
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("blocked-by", r.stderr)
        self.assertIn("could not be read", r.stderr)
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


class AdoptContradiction(unittest.TestCase):
    """
    KD2: refuse rather than reconcile, and make every refusal CLEARABLE by
    printing the exact REST command that removes the link (#14 KTD9). Each
    names a numeric issue `id`, taken from the replies adopt already read.
    """

    def test_an_existing_different_parent_refuses_and_names_the_clearing_command(self):
        h = adopt_harness(pre_parent="77")
        r = h.run(*adopt_args(), "--parent", "55", "--after", "101")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("77", out, "must name what it found")
        self.assertIn("55", out, "must name what was asked for")
        self.assertIn("gh api -X DELETE repos/jffriend/photo-consolidation/"
                      "issues/77/sub_issue -F sub_issue_id=%d" % issue_id(200),
                      out)
        self.assertTrue(wrote_nothing(h))

    def test_an_existing_parent_under_no_parent_refuses_the_same_way(self):
        h = adopt_harness(pre_parent="77")
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("77", out)
        self.assertIn("issues/77/sub_issue -F sub_issue_id=", out)
        self.assertTrue(wrote_nothing(h))

    def test_unnamed_blocked_by_links_refuse_and_name_the_clearing_command(self):
        h = adopt_harness(pre_blocked=[122, 133])
        r = h.run(*adopt_args(**{"--blocked-by": "122"}), "--no-parent",
                  "--after", "101")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("133", out, "must name the link not asked for")
        self.assertIn("gh api -X DELETE repos/jffriend/photo-consolidation/"
                      "issues/200/dependencies/blocked_by/%d" % issue_id(133), out)
        self.assertNotIn("blocked_by/%d" % issue_id(122), out,
                         "a link that was asked for is not cleared")
        self.assertTrue(wrote_nothing(h))

    def test_unnamed_blocks_links_refuse_and_name_the_clearing_command(self):
        # A blocks link is the blocked issue's blocked-by link, so it is
        # cleared against #63, by #200's id.
        h = adopt_harness(pre_blocking=[63])
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("63", out)
        self.assertIn("gh api -X DELETE repos/jffriend/photo-consolidation/"
                      "issues/63/dependencies/blocked_by/%d" % issue_id(200), out)
        self.assertTrue(wrote_nothing(h))

    def test_an_unnamed_blocks_link_into_another_repo_is_cleared_in_that_repo(self):
        # Dependency lists carry issues from other repos too (measured
        # 2026-10-15: this repo's #14 blocks jffriend/pluckd#577). The link
        # lives on the blocked issue, so the remedy must name ITS repo.
        blocking = json.dumps([{
            "number": 577, "id": 5872918136,
            "repository_url": "https://api.github.com/repos/jffriend/pluckd"}])
        responses = override(adopt_responses(), "issues/200/dependencies/blocking?",
                             stdout=blocking)
        h = Harness("**Design:** none\n", boards=[ADOPT_PRE_BOARD, ADOPT_POST_BOARD],
                    responses=responses)
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("gh api -X DELETE repos/jffriend/pluckd/"
                      "issues/577/dependencies/blocked_by/%d" % issue_id(200),
                      r.stderr)
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
    skipped; anything contradicting has already been refused above. Over REST
    each link is its own POST (#14 U4), and the delta decides which are sent.
    """

    def test_an_already_correct_parent_is_not_sent_again(self):
        h = adopt_harness(pre_parent="55", post_parent="55")
        r = h.run(*adopt_args(), "--parent", "55", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([], link_writes(h),
                         "a parent already correct must not be re-added")

    def test_an_already_present_blocker_is_omitted_and_the_others_are_sent(self):
        h = adopt_harness(pre_blocked=[122], post_blocked=[122, 133])
        r = h.run(*adopt_args(**{"--blocked-by": "122,133"}), "--no-parent",
                  "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(
            [("200/dependencies/blocked_by", "issue_id=%d" % issue_id(133))],
            link_writes(h), "only the link that is not already there is sent")

    def test_an_already_present_blocking_link_is_omitted_and_the_others_are_sent(self):
        """The `blocks` mirror of the blocked-by test above.

        Photos' original suite only carried this shape for parent and
        blocked-by; blocking is the third relationship kind the delta is
        computed for and needs its own proof.
        """
        h = adopt_harness(pre_blocking=[63], post_blocking=[63, 70])
        r = h.run(*adopt_args(**{"--blocks": "63,70"}), "--no-parent",
                  "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(
            [("70/dependencies/blocked_by", "issue_id=%d" % issue_id(200))],
            link_writes(h), "only the link that is not already there is sent")

    def test_the_position_write_is_issued_even_when_the_position_already_matches(self):
        """Position is the fourth placement answer, and the ONE relationship
        kind with no delta-skip, by design. KD2 refuses to reconcile parent,
        blocked-by and blocks when the server already disagrees, and skips
        writing them again when the server already agrees -- but adopt does
        not refuse a reposition (all four placement answers are mandatory,
        so a position is always named), and there is no REST position write
        to omit in the first place: the write is a separate GraphQL mutation (`updateProjectV2ItemPosition`), issued
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

    def test_everything_already_present_issues_no_write_at_all_and_still_reads_back(self):
        h = adopt_harness(pre_parent="55", pre_blocked=[122], pre_blocking=[63],
                          post_parent="55", post_blocked=[122], post_blocking=[63])
        r = h.run("--adopt", ADOPT_NUM, "--parent", "55", "--after", "101",
                  "--blocked-by", "122", "--blocks", "63")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([], link_writes(h),
                         "an empty delta must issue no link write at all")
        self.assertIn("no write issued", r.stdout)
        out = r.stdout
        self.assertIn("board membership   ok", out)
        self.assertIn("board position     ok", out)
        self.assertIn("parent             ok (#55)", out)
        self.assertIn("blocked-by         ok (122)", out)
        self.assertIn("blocks             ok (63)", out)

    def test_a_partially_applied_edit_is_caught_and_not_reported_as_nothing_written(self):
        # Every write exits non-zero, yet the parent landed and the blocker
        # did not. "It exited non-zero" is not evidence that nothing was
        # written, so the read-back is what decides.
        h = adopt_harness(post_parent="55", post_blocked=[], write_exit=1)
        r = h.run("--adopt", ADOPT_NUM, "--parent", "55", "--after", "101",
                  "--blocked-by", "122", "--blocks", "none")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("blocked-by", out, "must name the relationship that disagreed")
        self.assertIn("MAY still have been written", out)
        self.assertNotIn("Nothing was changed", out)
        self.assertNotIn("nothing was written", out.lower())


class AdoptResolvesBeforeWriting(unittest.TestCase):
    """KTD3 holds in adopt too: every number adopt is about to link is
    resolved before the first write. A typo in --parent or --blocks used to
    surface only as a 404 on its own POST, after the other links had landed,
    leaving the issue partly wired."""

    MISSING = [{"match": "issues/999", "exit": 1,
                "stderr": "gh: Not Found (HTTP 404)\n"}]

    def _adopt(self, *args):
        h = Harness("**Design:** none\n",
                    boards=[ADOPT_PRE_BOARD, ADOPT_POST_BOARD],
                    responses=self.MISSING + adopt_responses())
        return h, h.run("--adopt", ADOPT_NUM, *args)

    def test_a_blocks_number_that_does_not_exist_refuses_before_any_write(self):
        h, r = self._adopt("--no-parent", "--after", "101",
                           "--blocked-by", "122", "--blocks", "999")
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("#999 does not exist", r.stderr)
        self.assertTrue(wrote_nothing(h), "the blocked-by link must not land first")

    def test_a_parent_number_that_does_not_exist_refuses_before_any_write(self):
        h, r = self._adopt("--parent", "999", "--after", "101",
                           "--blocked-by", "122", "--blocks", "none")
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("#999 does not exist", r.stderr)
        self.assertTrue(wrote_nothing(h), "the blocked-by link must not land first")


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

    def test_an_issue_already_on_the_board_takes_its_item_id_from_the_listing(self):
        # item-add cannot answer this: the create path takes the id from
        # item-add's output and refuses when it is empty, which for an issue
        # already on the board would abort a correctly wired filing. The
        # pre-write listing carries the item's node id (#14 KTD5).
        h = adopt_harness()
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(h.called(ITEM_ADD_MATCH),
                         "the id came from the board listing, not item-add")
        positions = [c for c in h.calls()
                     if any("updateProjectV2ItemPosition" in a for a in c)]
        self.assertEqual(1, len(positions), positions)
        self.assertIn("i=PVTI_200", positions[0])
        self.assertIn("a=PVTI_101", positions[0])
        self.assertIn("board position     ok (after #101)", r.stdout)

    def test_an_issue_not_on_the_board_is_item_added(self):
        # An adopted issue that is not on the board yet: the listing has no
        # row for it, so item-add puts it there.
        off_board = [(101, "First thing on the board"), (102, "Second thing")]
        top_board = [
            (200, "An existing issue being wired"),
            (101, "First thing on the board"),
            (102, "Second thing"),
        ]
        h = adopt_harness(boards=[off_board, top_board])
        r = h.run(*adopt_args(), "--no-parent", "--top")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(h.called(ITEM_ADD_MATCH))
        positions = [c for c in h.calls()
                     if any("updateProjectV2ItemPosition" in a for a in c)]
        self.assertIn("i=PVTI_from_item_add", positions[0])
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
    "LABEL_READ",
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


PROVENANCE_PREFIXES = ("It is left", "Finish it", "In a local session")


def failure_lines(stderr):
    """The failure output minus the lines that legitimately differ.

    Only the provenance sentence and the next action depend on whether this run
    created the issue. Everything else -- the MISMATCH sentence and the
    requested-state summary -- must be byte-identical between the modes.

    Create's next action is three lines (#14 KTD4): a "Finish it" line, the
    adopt command on the line after it, and the local-session alternative.
    The command line is dropped only where it follows a "Finish it" line, so
    the re-verification command the other refusals print is still compared.
    """
    out, after_finish = [], False
    for ln in stderr.splitlines():
        drop = ln.startswith(PROVENANCE_PREFIXES) \
            or (after_finish and ln.startswith("  bash "))
        after_finish = ln.startswith("Finish it")
        if not drop:
            out.append(ln)
    return out


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
        return self._same_config(h, h.run(
            "--title", "A brand new distinct piece of work",
            "--body-file", str(h.body_file), "--shape", "work", *args))

    @staticmethod
    def _same_config(h, r):
        # Each harness has its own temp --config path, and the re-verify
        # command prints it. That is the one difference that is not the
        # read-back's, so it is named out before comparing.
        r.stderr = r.stderr.replace(str(h.config_path), "<config>")
        return r

    def _adopt(self, board_after, parent, blocked, blocking, args):
        h = Harness("**Design:** none\n",
                    boards=[ADOPT_PRE_BOARD, board_after],
                    responses=adopt_responses(post_parent=parent,
                                              post_blocked=blocked,
                                              post_blocking=blocking))
        return self._same_config(h, h.run("--adopt", ADOPT_NUM, *args))

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


def relationship_set(h):
    """Every relationship this run wrote, as {(kind, other issue number)}.

    Read off the REST writes `link_writes` returns, with each numeric id
    turned back into its number. An EXPLICIT mapping, so a write of a fourth
    kind fails this test instead of slipping past an enumeration that silently
    stopped covering it.
    """
    out = set()
    for path, field in link_writes(h):
        target, _, endpoint = path.partition("/")
        if not field:
            raise AssertionError("relationship write with no id field: %r" % path)
        other = int(field.split("=", 1)[1]) - ISSUE_ID_BASE
        if endpoint == "sub_issues" and other == int(ADOPT_NUM):
            out.add(("parent", int(target)))
        elif endpoint == "dependencies/blocked_by" and target == ADOPT_NUM:
            out.add(("blocked-by", other))
        elif endpoint == "dependencies/blocked_by" and other == int(ADOPT_NUM):
            out.add(("blocks", int(target)))
        else:
            raise AssertionError(
                "unmapped relationship write %r %r -- map it in "
                "relationship_set so parity keeps binding" % (path, field))
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
        self.assertIsNotNone(create_argv(h))
        return relationship_set(h)

    def _adopt_set(self, args, blocked, blocking, parent):
        h = adopt_harness(post_parent=parent, post_blocked=blocked,
                          post_blocking=blocking)
        r = h.run("--adopt", ADOPT_NUM, *args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return relationship_set(h)

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
        self.assertIn("--no-board", out)
        self.assertIn("--position-later", out)
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
        return [c for c in h.calls() if any("/items?per_page=" in a for a in c)]

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

    Keeps the ORDER of the table, which several rules depend on -- item-add
    has to stay ahead of the generic `-X POST` rule, and the dependency-list
    reads ahead of the bare issue read.
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
    """F1: the relationship read-back passed on ANY non-empty JSON.

    Over REST (#14 KTD6) it reads three replies, and each one's SHAPE is
    checked, because empty is a legal answer for all three: an issue with no
    parent, no blockers, blocking nothing.
    """

    BOARD_AFTER = [
        (101, "First thing on the board"),
        (200, "A brand new distinct piece of work"),
        (102, "Second thing"),
    ]

    def _run(self, match=None, args=("--no-parent",), parent=None, **fields):
        responses = create_responses([], [], parent)
        if match is not None:
            responses = override(responses, match, **fields)
        h = Harness("**Design:** none\n", boards=[PRE_BOARD, self.BOARD_AFTER],
                    responses=responses)
        r = h.run(*full_args(h.body_file), *args, "--after", "101")
        return r, r.stdout + r.stderr

    # The read-back line each REST reply proves, keyed by the rule answering it.
    OK_LINE = {READ_ISSUE_MATCH: "  parent             ok",
               READ_BLOCKED_MATCH: "  blocked-by         ok",
               READ_BLOCKING_MATCH: "  blocks             ok"}

    def _assert_could_not_look(self, r, out, match):
        self.assertNotEqual(r.returncode, 0, out)
        self.assertNotIn("every relationship read back matching", out)
        self.assertNotIn(self.OK_LINE[match], out,
                         "a reply that could not be read proved nothing")
        self.assertIn("The READ failed, not the write.", out,
                      "a reply that could not be read is not a failed write")
        self.assertNotIn("delete", out.replace("Do not delete", ""))

    def test_an_issue_reply_without_number_and_state_is_not_a_pass(self):
        """`{"message":"Not Found"}` used to read back as three clean `ok`s.

        Every jq extraction on it yields empty, and empty compares EQUAL to the
        empty answer set -- so on the commonest filing shape the run printed
        `parent ok (none)`, `blocked-by ok (none)`, `blocks ok (none)` and
        exited 0 having proven nothing at all.
        """
        r, out = self._run(READ_ISSUE_MATCH,
                           stdout=json.dumps({"message": "Not Found"}))
        self._assert_could_not_look(r, out, READ_ISSUE_MATCH)
        self.assertIn("unrecognised shape", out)

    def test_an_issue_read_that_exits_non_zero_is_not_a_pass(self):
        r, out = self._run(READ_ISSUE_MATCH, stdout="", exit=1,
                           stderr="gh: Server Error (HTTP 502)\n")
        self._assert_could_not_look(r, out, READ_ISSUE_MATCH)

    def test_a_dependency_list_that_is_not_an_array_is_not_a_pass(self):
        # Covers R4. An object there would extract as "no links".
        for match in (READ_BLOCKED_MATCH, READ_BLOCKING_MATCH):
            with self.subTest(match=match):
                r, out = self._run(match,
                                   stdout=json.dumps({"message": "Not Found"}))
                self._assert_could_not_look(r, out, match)

    def test_a_dependency_read_that_exits_non_zero_is_not_a_pass(self):
        r, out = self._run(READ_BLOCKING_MATCH, stdout="", exit=1,
                           stderr="gh: Server Error (HTTP 502)\n")
        self._assert_could_not_look(r, out, READ_BLOCKING_MATCH)

    def test_a_malformed_parent_url_is_not_read_as_no_parent(self):
        reply = issue_reply(200)
        reply["parent_issue_url"] = "https://api.github.com/repos/x/y/issues/"
        r, out = self._run(READ_ISSUE_MATCH, stdout=json.dumps(reply))
        self._assert_could_not_look(r, out, READ_ISSUE_MATCH)
        self.assertIn("parent", out)

    def test_a_parentless_reply_with_no_parent_key_passes_a_no_parent_filing(self):
        # GitHub OMITS parent_issue_url on a parentless issue (measured
        # 2026-10-15), so an absent key is "no parent", not "could not look".
        self.assertNotIn("parent_issue_url", issue_reply(200), "precondition")
        r, out = self._run()
        self.assertEqual(0, r.returncode, out)
        self.assertIn("parent             ok (none)", r.stdout)

    def test_a_parent_url_naming_the_asked_for_parent_passes(self):
        r, out = self._run(args=("--parent", "240"), parent="240")
        self.assertEqual(0, r.returncode, out)
        self.assertIn("parent             ok (#240)", r.stdout)


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
        self.assertEqual(
            [("200/dependencies/blocked_by", "issue_id=%d" % issue_id(122))],
            link_writes(h),
            "the WRITE must not carry the repeat either -- a second write of "
            "an already-present link is refused")

    def test_a_repeated_blocker_reads_back_as_correctly_wired_on_adopt(self):
        h = adopt_harness(post_blocked=[122])
        r = h.run("--adopt", ADOPT_NUM, "--no-parent", "--after", "101",
                  "--blocked-by", "122,122", "--blocks", "none")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("blocked-by         ok (122)", r.stdout)
        self.assertEqual(
            [("200/dependencies/blocked_by", "issue_id=%d" % issue_id(122))],
            link_writes(h), "the adopt delta must not emit a repeat")

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


def board_page_without_node_id(rows, n):
    """`board_page(rows)` with issue #n's item carrying no node id."""
    head, body = board_page(rows).split("\r\n\r\n", 1)
    items = json.loads(body)
    for item in items:
        if item["content"]["number"] == n:
            del item["node_id"]
    return head + "\r\n\r\n" + json.dumps(items)


class ErroredLookupIsNotAnAbsentItem(unittest.TestCase):
    """F8: a FAILED `--after` lookup was reported as proven-wrong.

    The `--after` item's node id now comes from the pre-write board listing
    (#14 KTD5), which the gate already proved names #AFTER. So the item can no
    longer be ABSENT once a write has happened; it can still be UNREADABLE --
    a row with no node id -- and that must stay a could-not-look.
    """

    BOARD_AFTER = [
        (101, "First thing on the board"),
        (200, "A brand new distinct piece of work"),
        (102, "Second thing"),
    ]

    def test_an_after_item_with_no_node_id_says_the_READ_failed(self):
        """`2>/dev/null` once made an errored query look exactly like an
        absent item, and the call site routed that to half_wired() -- the
        did-not-land refusal, the one that prints "delete #N and re-run" --
        over a READ that failed."""
        h = Harness(
            "**Design:** none\n",
            boards=[PRE_BOARD, self.BOARD_AFTER],
            board_stdouts=[board_page_without_node_id(PRE_BOARD, 101),
                           board_page(self.BOARD_AFTER)],
            responses=create_responses([], []),
        )
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        out = r.stdout + r.stderr
        self.assertEqual(1, r.returncode, out)
        self.assertIn("the board item for #101 could not be read", out)
        self.assertIn("The READ failed, not the write.", out)
        self.assertNotIn("delete", out.replace("Do not delete", ""))
        self.assertIn("--adopt 200", out, "must name a safe next action")
        self.assertFalse(h.called(POSITION_MATCH))


POSITION_403 = {"exit": 1, "stdout": "",
                "stderr": "gh: Resource not accessible by integration (HTTP 403)\n"}


class BoardHalfOverRest(unittest.TestCase):
    """#14 U5: item-add is a REST POST carrying the issue's numeric id, and the
    position write -- the one GraphQL call left -- is classified by its error
    (KTD2): HTTP 403 degrades, anything else is half-wired as before."""

    BOARD_AFTER = [
        (101, "First thing on the board"),
        (200, "A brand new distinct piece of work"),
        (102, "Second thing"),
    ]

    def _run(self, responses=None, boards=None):
        h = Harness("**Design:** none\n",
                    boards=boards or [PRE_BOARD, self.BOARD_AFTER],
                    responses=responses or create_responses([], []))
        return h, h.run(*full_args(h.body_file), "--no-parent", "--after", "101")

    def test_item_add_posts_the_issue_id_and_the_position_takes_its_node_id(self):
        h, r = self._run()
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        adds = [c for c in h.calls() if ITEM_ADD_MATCH in " ".join(c)]
        self.assertEqual(1, len(adds), adds)
        self.assertEqual(["api", "-X", "POST", "users/jffriend/projectsV2/2/items",
                          "-f", "type=Issue", "-F", "id=%d" % issue_id(200)],
                         adds[0])
        positions = [c for c in h.calls() if POSITION_MATCH in " ".join(c)]
        self.assertEqual(1, len(positions), positions)
        self.assertIn("i=PVTI_200", positions[0])
        self.assertIn("a=PVTI_101", positions[0],
                      "the --after item's node id, from the pre-write listing")

    def test_a_refused_position_write_continues_to_the_read_back(self):
        h, r = self._run(override(create_responses([], []), POSITION_MATCH,
                                  **POSITION_403))
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("READ-BACK", r.stdout)
        self.assertIn("board membership   ok", r.stdout)
        self.assertNotIn("MISMATCH", r.stderr)

    def test_a_position_write_failing_any_other_way_is_half_wired(self):
        h, r = self._run(override(create_responses([], []), POSITION_MATCH,
                                  exit=1, stdout="",
                                  stderr="gh: Bad Gateway (HTTP 502)\n"))
        err = r.stderr
        self.assertEqual(1, r.returncode, r.stdout + err)
        self.assertIn("MISMATCH: the board position write failed for #200", err)
        self.assertIn("HTTP 502", err, "gh's own reason reaches the operator")
        self.assertIn("It is left HALF-WIRED", err)
        self.assertNotIn("READ-BACK", r.stdout)
        self.assertNotIn("NOT SET", r.stdout + err)

    def test_corroboration_reads_the_item_item_add_returned(self):
        # The listing never shows #200; the single-item read by item-add's
        # numeric id is what proves membership.
        h, r = self._run(create_responses([], [], corroborate=True),
                         boards=[PRE_BOARD, BOARD_WITHOUT_200])
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("Membership is PROVEN", r.stderr)
        self.assertTrue(h.called("api", "users/jffriend/projectsV2/2/items/900200"))

    def test_a_corroborating_item_that_names_another_issue_proves_nothing(self):
        # A reply that is the wrong item, or not an item at all, must not read
        # as membership.
        for reply in (item_reply(201), {"message": "Not Found"}):
            with self.subTest(reply=reply):
                responses = override(create_responses([], []), ITEM_READ_MATCH,
                                     stdout=json.dumps(reply))
                h, r = self._run(responses, boards=[PRE_BOARD, BOARD_WITHOUT_200])
                self.assertEqual(1, r.returncode, r.stdout + r.stderr)
                self.assertIn("not on the board", r.stderr)
                self.assertNotIn("Membership is PROVEN", r.stderr)


class DegradedPosition(unittest.TestCase):
    """#14 U6 / KTD8: a position write refused with HTTP 403 leaves the item
    where it landed. Membership is still proven, the position comparison is
    skipped and reported NOT SET, adopt's move comment is not written, and the
    run ends 0 with the command a local session runs to place it."""

    BOARD_AFTER = [
        (101, "First thing on the board"),
        (102, "Second thing"),
        (200, "A brand new distinct piece of work"),
    ]

    def _create(self, boards=None, corroborate=""):
        responses = override(create_responses([], [], corroborate=corroborate),
                             POSITION_MATCH, **POSITION_403)
        h = Harness("**Design:** none\n",
                    boards=boards or [PRE_BOARD, self.BOARD_AFTER],
                    responses=responses)
        return h, h.run(*full_args(h.body_file), "--no-parent", "--after", "101")

    def test_a_degraded_create_proves_membership_and_says_not_set(self):
        # #200 landed at the bottom, not after #101: no position mismatch.
        h, r = self._create()
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("board membership   ok", r.stdout)
        self.assertIn("board position     NOT SET", r.stdout)
        self.assertNotIn("board position     ok", r.stdout)
        self.assertNotIn("MISMATCH", r.stderr)
        self.assertIn("blocks             ok (none)", r.stdout,
                      "the relationships are still read back")
        err = r.stderr
        self.assertIn("HTTP 403", err)
        self.assertIn("wherever it landed", err)
        self.assertIn(
            "  bash %s --config %s --adopt 200 --no-parent --after 101 "
            "--blocked-by none --blocks none" % (FILE_ISSUE, h.config_path),
            err.splitlines(), "the exact command a local session runs")

    def test_a_degraded_create_proven_only_by_corroboration_succeeds(self):
        h, r = self._create(boards=[PRE_BOARD, BOARD_WITHOUT_200],
                            corroborate=True)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("board membership   ok", r.stdout)
        self.assertIn("board position     NOT SET", r.stdout)

    def test_a_degraded_create_that_never_appears_is_still_absent(self):
        h, r = self._create(boards=[PRE_BOARD, BOARD_WITHOUT_200])
        out = r.stdout + r.stderr
        self.assertEqual(1, r.returncode, out)
        self.assertIn("not on the board", out)
        self.assertNotIn("NOT SET", r.stdout)
        self.assertNotIn("delete", out.replace("Do not delete", ""))
        self.assertEqual(5, len([c for c in h.calls()
                                 if any("/items?per_page=" in a for a in c)]) - 1,
                         "the same retry bound is spent before refusing")

    def test_a_degraded_adopt_that_would_have_moved_writes_no_comment(self):
        # #200 sits third on ADOPT_PRE_BOARD; --after 101 would move it.
        responses = override(adopt_responses(), POSITION_MATCH, **POSITION_403)
        h = Harness("**Design:** none\n",
                    boards=[ADOPT_PRE_BOARD, ADOPT_PRE_BOARD],
                    responses=responses)
        r = h.run(*adopt_args(), "--no-parent", "--after", "101")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("MOVES it", position_line(r.stdout))
        self.assertIn("board position     NOT SET", r.stdout)
        self.assertEqual([], comment_calls(h), "nothing moved, so nothing to record")
        self.assertNotIn("move recorded", r.stdout)
        self.assertIn("--adopt 200 --no-parent --after 101", r.stderr)

    def test_a_degraded_adopt_already_in_place_proves_the_position(self):
        # #200 already follows #102 on ADOPT_PRE_BOARD, so nothing has to
        # move: a refused position write changes nothing, and the read-back
        # proves the position instead of reporting it NOT SET.
        responses = override(adopt_responses(), POSITION_MATCH, **POSITION_403)
        h = Harness("**Design:** none\n",
                    boards=[ADOPT_PRE_BOARD, ADOPT_PRE_BOARD],
                    responses=responses)
        r = h.run(*adopt_args(), "--no-parent", "--after", "102")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("does NOT move it", position_line(r.stdout))
        self.assertIn("board position     ok", r.stdout)
        self.assertNotIn("NOT SET", r.stdout + r.stderr)
        self.assertEqual([], comment_calls(h))


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


COMMENT_MATCH = "issues/200/comments"


def comment_calls(h):
    """Every comment this run posted: `gh api -X POST .../issues/N/comments`."""
    return [c for c in h.calls()
            if c[:3] == ["api", "-X", "POST"] and len(c) > 3
            and c[3].endswith("/comments")]


def comment_body(call):
    """The `body=` field of a comment POST."""
    bodies = [a for a in call if a.startswith("body=")]
    assert len(bodies) == 1, call
    return bodies[0][len("body="):]


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
        self.assertEqual("repos/jffriend/photo-consolidation/issues/200/comments",
                         calls[0][3])
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
        h = adopt_harness(boards=[off_board, ADOPT_POST_BOARD])
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
            responses=[{"match": COMMENT_MATCH, "stdout": "",
                        "stderr": "gh: Bad Gateway (HTTP 502)\n", "exit": 1}]
            + adopt_responses(),
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
    """F14: the fake matches argv SUBSTRINGS, so a specific rule only answers
    when it comes before every more general rule it overlaps. Nothing used to
    assert that, and a reorder made `test_missing_from_the_board_fails_loudly`
    unable to fail."""

    @staticmethod
    def _index(rules, match):
        for i, rule in enumerate(rules):
            if rule["match"] == match:
                return i
        raise AssertionError("no rule matching %r" % match)

    def test_item_add_comes_before_the_generic_post(self):
        # Item-add is a POST too; behind `-X POST` it would answer `{}`.
        for table in (create_responses([], []), adopt_responses()):
            self.assertLess(self._index(table, ITEM_ADD_MATCH),
                            self._index(table, "-X POST"))

    def test_the_dependency_reads_come_before_the_issue_read(self):
        """`issues/200` is a substring of both dependency-list paths, so the
        order is what tells them apart."""
        for table in (create_responses([], []), adopt_responses()):
            bare = self._index(table, READ_ISSUE_MATCH)
            for match in (READ_BLOCKED_MATCH, READ_BLOCKING_MATCH):
                self.assertLess(self._index(table, match), bare)

    def test_no_rule_is_shadowed_by_an_earlier_one(self):
        """A rule whose match CONTAINS an earlier rule's match can never be
        reached: every argv it matches, the earlier one matched first. A
        test leaning on it would pass on the wrong reply."""
        for name, table in (("create", create_responses([], [])),
                            ("adopt", adopt_responses())):
            matches = [r["match"] for r in table]
            for j, later in enumerate(matches):
                for earlier in matches[:j]:
                    self.assertNotIn(
                        earlier, later,
                        "%s table: %r is dead behind %r" % (name, later, earlier))

    def test_every_write_reaches_the_post_rule_before_any_read_rule(self):
        """`issues/55/sub_issues` also contains `issues/55`. The write rules
        come first, so a write is never answered with an issue read."""
        for table in (create_responses([], []), adopt_responses()):
            post = self._index(table, "-X POST")
            for i, rule in enumerate(table):
                if rule["match"].startswith("issues/"):
                    self.assertLess(post, i, rule["match"])


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
        self.assertFalse(h.created())

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
        self.assertFalse(h.created())

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
        self.assertFalse(h.created())

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
        cfg = {k: v for k, v in PHOTOS_CONFIG.items() if k != "human_review_required"}
        h.config_path.write_text(json.dumps(cfg))
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
        self.assertFalse(h.created())

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
                self.assertFalse(h.created())


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
        self.assertEqual("repos/jffriend/pluckd/issues", create_call[3])
        self.assertIn("labels[]=bug", create_call)
        # "needs-joe" is Photos-only vocabulary; it must not leak into a
        # config that never defined it.
        self.assertNotIn("labels[]=needs-joe", create_call)

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
    board read is config-driven instead of hardcoding the login and
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


class BoardOverRest(unittest.TestCase):
    """#14 U1: board.sh reads the board through the REST items endpoint,
    following the `Link` header's `after` cursor itself, so the page count,
    the 20-page cap and the rows-versus-distinct self-check all survive the
    move off GraphQL."""

    PAGE1 = [(101, "First thing on the board"), (102, "Second thing"),
             (103, "Third thing")]
    PAGE2 = [(104, "Fourth thing"), (105, "Fifth thing"),
             (106, "Sixth thing")]

    def _board_calls(self, h):
        return [c for c in h.calls() if any("/items?per_page=" in a for a in c)]

    def _board_sh(self, h):
        out_path = h.dir / "board_out.json"
        env = dict(os.environ)
        env["PATH"] = f"{h.bin}:{env['PATH']}"
        env["FAKE_GH_DIR"] = str(h.dir)
        r = subprocess.run(
            ["bash", str(BOARD_SH), "--config", str(h.config_path), str(out_path)],
            capture_output=True, text=True, env=env, check=False,
        )
        return r, out_path

    def test_a_two_page_board_is_read_in_order(self):
        h = Harness("**Design:** none\n",
                    boards=[self.PAGE1 + self.PAGE2],
                    board_stdouts=[board_page(self.PAGE1, next_cursor="CUR2"),
                                   board_page(self.PAGE2)])
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "103",
                  "--dry-run")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        # --after 103 sits on the seam: its neighbours above come from page 1
        # and its neighbours below from page 2, in board order.
        seen = [out.index("#%d " % n) for n, _ in self.PAGE1 + self.PAGE2]
        self.assertEqual(sorted(seen), seen, out)
        self.assertLess(out.index("#103 "), out.index("NEW ISSUE HERE"))
        self.assertLess(out.index("NEW ISSUE HERE"), out.index("#104 "))
        calls = self._board_calls(h)
        self.assertEqual(2, len(calls), calls)
        self.assertNotIn("after=", " ".join(calls[0]))
        self.assertIn("after=CUR2", " ".join(calls[1]),
                      "the second page must be asked for by the next cursor")
        self.assertIn("-i", calls[0], "the Link header is only seen with -i")

    def test_board_sh_counts_both_pages(self):
        h = Harness("**Design:** none\n",
                    board_stdouts=[board_page(self.PAGE1, next_cursor="CUR2"),
                                   board_page(self.PAGE2)])
        r, _ = self._board_sh(h)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("pages=2 rows=6 distinct=6", r.stderr)

    def test_repeated_pages_are_a_truncated_board(self):
        # The cursor did not advance: the same page came back twice.
        h = Harness("**Design:** none\n",
                    board_stdouts=[board_page(self.PAGE1, next_cursor="CUR2"),
                                   board_page(self.PAGE1)])
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("TRUNCATED BOARD", out)
        self.assertIn("not trustworthy", out)

    def test_a_failed_page_read_fails_the_run(self):
        h = Harness("**Design:** none\n",
                    board_stdouts=[board_page(self.PAGE1, next_cursor="CUR2"),
                                   board_page(self.PAGE2)],
                    board_exits=[0, 1])
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("QUERY FAILED on page 2", out)
        self.assertIn("not trustworthy", out)

    def test_a_page_that_is_not_an_item_array_fails_the_run(self):
        # An empty or object-shaped body would otherwise count as zero rows,
        # and a truncated board reads exactly like a short one.
        h = Harness("**Design:** none\n",
                    board_stdouts=["HTTP/2.0 200 OK\n\r\n"
                                   + json.dumps({"message": "Not an array"})])
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("QUERY FAILED on page 1", out)
        self.assertIn("not trustworthy", out)

    def test_a_next_link_without_a_cursor_fails_the_run(self):
        # Ending the loop there would read a long board as a short one.
        page = board_page(self.PAGE1, next_cursor="X").replace(
            "&after=X", "&cursor=X")
        h = Harness("**Design:** none\n", board_stdouts=[page])
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("carries no cursor", out)

    def test_a_pull_request_on_the_board_is_not_a_row(self):
        # The GraphQL listing read a pull request as numberless and dropped
        # it; the REST listing numbers it, so the row filter is by type.
        page = json.loads(board_page(self.PAGE1).split("\r\n\r\n", 1)[1])
        page.append({"id": 1, "node_id": "PVTI_pr", "content_type": "PullRequest",
                     "content": {"number": 150, "title": "A pull request"},
                     "fields": []})
        h = Harness("**Design:** none\n", boards=[self.PAGE1],
                    board_stdouts=["HTTP/2.0 200 OK\n\r\n" + json.dumps(page)])
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "103",
                  "--dry-run")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("#103 ", out)
        self.assertNotIn("#150", out)

    def test_the_page_cap_still_fires(self):
        # Every page claims a next page; the cap is what stops the loop.
        h = Harness("**Design:** none\n",
                    board_stdouts=[board_page(self.PAGE1, next_cursor="SAME")])
        r = h.run(*full_args(h.body_file), "--no-parent", "--top", "--dry-run")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("PAGE CAP HIT", out)
        self.assertEqual(20, len(self._board_calls(h)))

    def test_status_is_requested_by_its_numeric_field_id(self):
        h = Harness("**Design:** none\n")
        r, out_path = self._board_sh(h)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = self._board_calls(h)
        self.assertTrue(calls)
        for call in calls:
            self.assertIn("fields=%d" % STATUS_FIELD_ID, " ".join(call))
        items = [i for page in out_path.read_text().split("\n") if page.strip()
                 for i in json.loads(page)]
        self.assertEqual(len(DEFAULT_BOARD), len(items))
        for item in items:
            status = [f for f in item["fields"] if f["name"] == "Status"]
            self.assertEqual("Backlog", status[0]["value"]["name"]["raw"])

    def test_a_project_without_a_status_field_omits_the_fields_parameter(self):
        h = Harness("**Design:** none\n",
                    fields=[{"id": 77000, "name": "Title", "data_type": "title"}])
        r, _ = self._board_sh(h)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = self._board_calls(h)
        self.assertTrue(calls)
        for call in calls:
            self.assertNotIn("fields=", " ".join(call))


class GraphQLBlocked(unittest.TestCase):
    """#14 U7: the main flows with EVERY GraphQL call refused (HTTP 403), as in
    a session whose proxy blocks GraphQL. Filing, adopting, the dry-run and
    the duplicate stop all still work; only the board position degrades.

    Every test also asserts the only GraphQL call it made was the position
    write, so a path that reintroduces any other GraphQL call fails here even
    where its refusal would otherwise be absorbed.
    """

    def tearDown(self):
        for call in self.h.calls():
            joined = " ".join(call)
            if "graphql" in joined:
                self.assertIn(POSITION_MATCH, joined,
                              "a GraphQL call other than the position write: %r"
                              % call)

    def _create(self, responses, *args, pre=PRE_BOARD, post=None):
        post = post or [
            (101, "First thing on the board"),
            (102, "Second thing"),
            (103, "Third thing"),
            (200, "A brand new distinct piece of work"),
        ]
        self.h = Harness("**Design:** none\n", boards=[pre, post],
                         responses=responses, graphql_blocked=True)
        return self.h.run("--body-file", str(self.h.body_file),
                          "--shape", "work", *args)

    def test_create_with_a_parent_and_links_files_and_reads_back(self):
        # Covers R1.
        r = self._create(create_responses([122], [63], "55"),
                         "--title", "A brand new distinct piece of work",
                         "--parent", "55", "--after", "101",
                         "--blocked-by", "122", "--blocks", "63")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        out = r.stdout
        self.assertTrue(self.h.created())
        self.assertIn("board membership   ok", out)
        self.assertIn("board position     NOT SET", out)
        self.assertIn("parent             ok (#55)", out)
        self.assertIn("blocked-by         ok (122)", out)
        self.assertIn("blocks             ok (63)", out)
        self.assertEqual(1, len([c for c in self.h.calls()
                                 if POSITION_MATCH in " ".join(c)]),
                         "the position write is tried once, never retried")
        self.assertIn("--adopt 200 --parent 55 --after 101 --blocked-by 122 "
                      "--blocks 63", r.stderr)

    def test_adopt_that_writes_one_missing_link_succeeds(self):
        # Covers R2.
        self.h = Harness("**Design:** none\n",
                         boards=[ADOPT_PRE_BOARD, ADOPT_POST_BOARD],
                         responses=adopt_responses(post_blocked=[122]),
                         graphql_blocked=True)
        r = self.h.run(*adopt_args(**{"--blocked-by": "122"}), "--no-parent",
                       "--after", "101")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertEqual(
            [("200/dependencies/blocked_by", "issue_id=%d" % issue_id(122))],
            link_writes(self.h))
        self.assertIn("blocked-by         ok (122)", r.stdout)
        self.assertIn("board position     NOT SET", r.stdout)
        self.assertIn("#200 is wired", r.stdout)

    def test_dry_run_shows_the_neighbourhood_and_duplicate_check(self):
        # Covers R3.
        r = self._create(create_responses([], []),
                         "--title", "A brand new distinct piece of work",
                         "--no-parent", "--after", "102",
                         "--blocked-by", "none", "--blocks", "none", "--dry-run")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("BOARD NEIGHBOURHOOD", r.stdout)
        self.assertIn("#101", r.stdout)
        self.assertIn("#103", r.stdout)
        self.assertIn("POSSIBLE DUPLICATES: none found", r.stdout)
        self.assertTrue(wrote_nothing(self.h))
        self.assertFalse([c for c in self.h.calls() if "graphql" in " ".join(c)])

    def test_possible_duplicates_still_stop_with_exit_3(self):
        r = self._create(create_responses([], []),
                         "--title", DUPE_TITLE, "--no-parent", "--after", "101",
                         "--blocked-by", "none", "--blocks", "none",
                         pre=DUPE_PRE_BOARD, post=DUPE_POST_BOARD)
        self.assertEqual(3, r.returncode, r.stdout + r.stderr)
        self.assertIn("164", r.stdout)
        self.assertTrue(wrote_nothing(self.h))
        self.assertFalse([c for c in self.h.calls() if "graphql" in " ".join(c)])


# ---------------------------------------------------------------------------
# #14 cloud mode. A Claude Code cloud session's proxy refuses the user-owned
# board, so cloud mode (CLAUDE_CODE_REMOTE=true, or --no-board) never reads or
# writes it: the position is decided later, the issue carries the needs-board
# label, and everything the run wrote is read back.
# ---------------------------------------------------------------------------

PENDING_LABEL = "needs-board"


def cloud_create_responses(post_labels=("work", PENDING_LABEL), blocked_by=(),
                           blocking=(), parent=None):
    """A cloud create's replies: the create, the link writes, and the three
    relationship reads of #200. There is no board rule -- the harness refuses
    every board path -- and the issue read carries the labels the read-back
    checks."""
    return [
        {"match": "issues -f title=", "stdout": json.dumps(issue_reply(200))},
        {"match": "-X POST", "stdout": "{}"},
        {"match": READ_BLOCKED_MATCH, "stdout": dependency_list(blocked_by)},
        {"match": READ_BLOCKING_MATCH, "stdout": dependency_list(blocking)},
        {"match": READ_ISSUE_MATCH,
         "stdout": json.dumps(issue_reply(200, parent=parent,
                                          labels=post_labels))},
        *referenced_issue_rules(),
    ]


def touched_the_board(h):
    """Every call that reached the board or GraphQL."""
    return [c for c in h.calls()
            if "projectsV2" in " ".join(c) or "graphql" in " ".join(c)]


def label_writes(h):
    """Every label add: `gh api -X POST repos/{repo}/issues/{n}/labels`."""
    return [c for c in h.calls()
            if c[:3] == ["api", "-X", "POST"] and len(c) > 3
            and c[3].endswith("/labels")]


def label_deletes(h):
    """Every label removal: `gh api -X DELETE .../issues/{n}/labels/{name}`."""
    return [c for c in h.calls()
            if c[:3] == ["api", "-X", "DELETE"] and len(c) > 3
            and "/labels/" in c[3]]


class CloudModeSwitch(unittest.TestCase):
    """#14 U1: cloud mode is decided before any network call, and it changes
    which position answers a run accepts (R1-R7)."""

    def setUp(self):
        self.h = Harness("**Design:** none\n", board_refused=True,
                         responses=cloud_create_responses())

    def _refused(self, *args, env=None):
        r = self.h.run(*full_args(self.h.body_file), "--no-parent", *args,
                       env=env)
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertFalse(self.h.network_calls(),
                         "the refusal must come before any network call")
        return r.stdout + r.stderr

    def test_after_in_cloud_mode_is_refused_naming_position_later(self):
        # Covers AE2.
        out = self._refused("--after", "12", env=CLOUD_ENV)
        self.assertIn("--position-later", out)

    def test_top_with_no_board_is_refused_naming_position_later(self):
        out = self._refused("--no-board", "--top")
        self.assertIn("--position-later", out)

    def test_cloud_mode_with_no_position_answer_is_refused(self):
        out = self._refused(env=CLOUD_ENV)
        self.assertIn("--position-later", out)

    def test_position_later_outside_cloud_mode_is_refused(self):
        out = self._refused("--position-later")
        self.assertIn("cloud mode", out)
        self.assertIn("--after", out)

    def test_only_the_exact_value_true_turns_cloud_mode_on(self):
        for value in ("false", "1", "TRUE", ""):
            h = Harness("**Design:** none\n", responses=create_responses([], []))
            r = h.run(*full_args(h.body_file), "--no-parent", "--top",
                      "--dry-run", env={CLOUD_ENV_VAR: value})
            self.assertEqual(0, r.returncode, (value, r.stdout + r.stderr))
            self.assertNotIn("cloud mode", r.stdout, value)
            self.assertIn("BOARD NEIGHBOURHOOD", r.stdout, value)

    def test_the_cloud_line_names_both_triggers_before_the_gh_probe(self):
        r = self.h.run(*full_args(self.h.body_file), "--no-parent",
                       "--position-later", "--no-board", "--dry-run",
                       env=CLOUD_ENV)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        lines = r.stdout.splitlines()
        cloud = [i for i, line in enumerate(lines) if line.startswith("cloud mode")]
        probe = [i for i, line in enumerate(lines) if line.startswith("gh capability")]
        self.assertTrue(cloud and probe, r.stdout)
        self.assertLess(cloud[0], probe[0])
        self.assertIn(CLOUD_ENV_VAR, lines[cloud[0]])
        self.assertIn("--no-board", lines[cloud[0]])


class CloudModeSkipsTheBoard(unittest.TestCase):
    """#14 U2: a cloud run never touches the board or GraphQL (R10), says so
    in its read-back (R13) and its dry run (R11), and a local run whose board
    is refused still stops (R3)."""

    def _create(self, *extra, responses=None, parent=("--no-parent",)):
        self.h = Harness("**Design:** none\n", board_refused=True,
                         graphql_blocked=True,
                         responses=responses or cloud_create_responses())
        return self.h.run(*full_args(self.h.body_file), *parent,
                          "--position-later", *extra, env=CLOUD_ENV)

    def test_a_cloud_create_never_calls_the_board_or_graphql(self):
        r = self._create()
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertEqual([], touched_the_board(self.h))

    def test_the_cloud_read_back_says_the_board_was_not_checked(self):
        r = self._create()
        self.assertIn("board membership   not checked (cloud mode)", r.stdout)
        self.assertIn("board position     not checked (cloud mode)", r.stdout)
        self.assertNotIn("board membership   ok", r.stdout)
        self.assertNotIn("board position     ok", r.stdout)

    def test_a_cloud_dry_run_shows_duplicates_and_no_neighbourhood(self):
        # Covers AE6.
        r = self._create("--dry-run")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("not available in cloud mode", r.stdout)
        self.assertIn("POSSIBLE DUPLICATES: none found", r.stdout)
        self.assertTrue(wrote_nothing(self.h))
        self.assertEqual([], touched_the_board(self.h))

    def test_a_refused_board_still_stops_a_local_run(self):
        # Covers AE3.
        h = Harness("**Design:** none\n", board_refused=True,
                    responses=create_responses([], []))
        r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101")
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("the board listing is not trustworthy", r.stderr)
        self.assertTrue(wrote_nothing(h))

    def test_a_cloud_adopt_shows_the_issues_own_title(self):
        reply = issue_reply(ADOPT_NUM, body="**Design:** none\n",
                            labels=(PENDING_LABEL,))
        reply["title"] = "An existing issue being wired"
        h = Harness("**Design:** none\n", board_refused=True,
                    responses=adopt_responses(issue_stdout=json.dumps(reply),
                                              post_labels=(PENDING_LABEL,)))
        r = h.run(*adopt_args(), "--no-parent", "--position-later", env=CLOUD_ENV)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("#200 An existing issue being wired", r.stdout)
        self.assertEqual([], touched_the_board(h))

    def test_a_cloud_refusal_hands_back_a_command_the_cloud_accepts(self):
        # Asked for a parent that does not read back: half-wired, with the
        # adopt re-run as its remedy.
        r = self._create(parent=("--parent", "55"))
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("--position-later", r.stderr)
        self.assertNotIn("--after", r.stderr)
        self.assertNotIn("--top", r.stderr)


class CloudModeLabel(unittest.TestCase):
    """#14 U3: every cloud-filed or cloud-adopted issue carries needs-board,
    proven by the read-back, and the run says it is not on the board (R8, R9,
    R12, R14)."""

    def _cloud(self, responses, *args, create=None):
        """Runs in cloud mode. `create`, a dict of full_args overrides, puts a
        create run's arguments first, built against this harness's body file."""
        self.h = Harness("**Design:** none\n", board_refused=True,
                         responses=responses)
        if create is not None:
            args = (*full_args(self.h.body_file, **create), *args)
        return self.h.run(*args, env=CLOUD_ENV)

    def test_a_cloud_create_sends_the_label_in_the_create_and_reads_it_back(self):
        # Covers AE1.
        r = self._cloud(cloud_create_responses(parent=55, blocking=(122,)),
                        "--parent", "55", "--position-later",
                        create={"--blocks": "122"})
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        create = create_argv(self.h)
        self.assertIn("labels[]=work", create)
        self.assertIn("labels[]=%s" % PENDING_LABEL, create)
        self.assertEqual([], label_writes(self.h),
                         "a create carries the label in the create itself")
        self.assertIn("parent             ok (#55)", r.stdout)
        self.assertIn("blocks             ok (122)", r.stdout)
        self.assertIn("needs-board        ok (present)", r.stdout)
        self.assertIn("#200 is created", r.stdout)
        self.assertIn("NOT on the board", r.stdout)
        self.assertIn("NOT ON THE BOARD", r.stderr)

    def test_a_cloud_adopt_of_a_labeled_issue_writes_no_label(self):
        # Covers AE4.
        r = self._cloud(adopt_responses(pre_parent=55, post_parent=55,
                                        post_blocking=(122,),
                                        pre_labels=(PENDING_LABEL,),
                                        post_labels=(PENDING_LABEL,)),
                        *adopt_args(**{"--blocks": "122"}), "--parent", "55",
                        "--position-later")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertEqual([], label_writes(self.h))
        self.assertEqual(
            [("122/dependencies/blocked_by", "issue_id=%d" % issue_id(200))],
            link_writes(self.h))
        self.assertIn("needs-board        ok (present)", r.stdout)

    def test_a_cloud_adopt_of_an_unlabeled_issue_adds_the_label_once(self):
        r = self._cloud(adopt_responses(post_labels=(PENDING_LABEL,)),
                        *adopt_args(), "--no-parent", "--position-later")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        writes = label_writes(self.h)
        self.assertEqual(1, len(writes), writes)
        self.assertIn("labels[]=%s" % PENDING_LABEL, writes[0])
        self.assertIn("needs-board        ok (present)", r.stdout)

    def test_a_label_missing_after_a_cloud_create_is_refused(self):
        r = self._cloud(cloud_create_responses(post_labels=("work",)),
                        "--no-parent", "--position-later", create={})
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn(PENDING_LABEL, r.stderr)
        self.assertIn("absent", r.stderr)
        self.assertNotIn("needs-board        ok", r.stdout)

    def test_a_read_back_reply_with_no_labels_list_is_unreadable(self):
        reply = issue_reply(200)
        del reply["labels"]
        r = self._cloud(override(cloud_create_responses(), READ_ISSUE_MATCH,
                                 stdout=json.dumps(reply)),
                        "--no-parent", "--position-later", create={})
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("unrecognised shape", r.stderr)
        self.assertNotIn("needs-board        ok", r.stdout)

    def test_a_local_create_carries_no_pending_label(self):
        h = Harness("**Design:** none\n",
                    boards=[PRE_BOARD, [(200, "x")] + PRE_BOARD],
                    responses=create_responses([], []))
        r = h.run(*full_args(h.body_file), "--no-parent", "--top")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertNotIn("labels[]=%s" % PENDING_LABEL, create_argv(h))
        self.assertNotIn(PENDING_LABEL, r.stdout)


class LocalPlacementClearsTheLabel(unittest.TestCase):
    """#14 U4: a local adopt that places a needs-board issue removes the label
    once the placement reads back, and proves it is gone (R15, R16)."""

    def _adopt(self, *extra, responses=None, **kw):
        self.h = Harness("**Design:** none\n",
                         boards=[ADOPT_PRE_BOARD, ADOPT_POST_BOARD],
                         responses=responses or adopt_responses(**kw))
        return self.h.run(*adopt_args(), "--no-parent", "--after", "101", *extra)

    def test_placing_a_labeled_issue_removes_the_label_and_proves_it(self):
        # Covers AE5. The read-back reply still shows the label, as it would
        # just before the DELETE; only the fresh read after it shows it gone,
        # so this fails if the removal is judged from the stale reply.
        r = self._adopt(pre_labels=(PENDING_LABEL,), post_labels=(PENDING_LABEL,),
                        after_delete_stdout=json.dumps(issue_reply(ADOPT_NUM)))
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        deletes = label_deletes(self.h)
        self.assertEqual(1, len(deletes), deletes)
        self.assertTrue(deletes[0][3].endswith("issues/200/labels/%s" % PENDING_LABEL),
                        deletes[0])
        self.assertIn("needs-board        removed", r.stdout)

    def test_a_failed_removal_warns_and_still_exits_0(self):
        r = self._adopt(pre_labels=(PENDING_LABEL,), post_labels=(PENDING_LABEL,),
                        delete_exit=1)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("gh api -X DELETE repos/jffriend/photo-consolidation/"
                      "issues/200/labels/%s" % PENDING_LABEL, r.stderr)
        self.assertNotIn("MISMATCH", r.stderr)
        self.assertNotIn("needs-board        removed", r.stdout)

    def test_a_removal_that_does_not_read_back_warns(self):
        r = self._adopt(pre_labels=(PENDING_LABEL,), post_labels=(PENDING_LABEL,))
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertEqual(1, len(label_deletes(self.h)))
        self.assertIn("gh api -X DELETE repos/jffriend/photo-consolidation/"
                      "issues/200/labels/%s" % PENDING_LABEL, r.stderr)
        self.assertNotIn("needs-board        removed", r.stdout)

    def test_a_delete_that_fails_but_landed_reads_back_removed(self):
        # The DELETE exits non-zero but GitHub applied it: the fresh read is
        # what decides, so no second DELETE is offered.
        r = self._adopt(pre_labels=(PENDING_LABEL,), post_labels=(PENDING_LABEL,),
                        delete_exit=1,
                        after_delete_stdout=json.dumps(issue_reply(ADOPT_NUM)))
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("needs-board        removed", r.stdout)
        self.assertNotIn("gh api -X DELETE", r.stderr)

    def test_an_unreadable_fresh_read_says_unknown_and_offers_no_delete(self):
        unreadable = json.dumps({"message": "Server Error"})
        r = self._adopt(pre_labels=(PENDING_LABEL,), post_labels=(PENDING_LABEL,),
                        after_delete_stdout=unreadable)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("UNKNOWN", r.stderr)
        self.assertNotIn("gh api -X DELETE", r.stderr)
        self.assertIn("gh api repos/jffriend/photo-consolidation/issues/200",
                      r.stderr)
        self.assertNotIn("needs-board        removed", r.stdout)

    def test_an_unlabeled_issue_gets_no_label_removal(self):
        r = self._adopt()
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertEqual([], label_deletes(self.h))

    def test_a_labeled_issue_whose_position_is_not_set_keeps_its_label(self):
        responses = override(adopt_responses(pre_labels=(PENDING_LABEL,),
                                             post_labels=(PENDING_LABEL,)),
                             POSITION_MATCH, **POSITION_403)
        r = self._adopt(responses=responses)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("board position     NOT SET", r.stdout)
        self.assertEqual([], label_deletes(self.h))

    def test_a_dry_run_of_a_labeled_issue_removes_nothing(self):
        r = self._adopt("--dry-run", pre_labels=(PENDING_LABEL,))
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertEqual([], label_deletes(self.h))
        self.assertTrue(wrote_nothing(self.h))


if __name__ == "__main__":
    unittest.main()
