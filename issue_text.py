#!/usr/bin/env python3
"""
issue_text.py  --  the pure text logic behind the issue-filing gate and the
board audit.

WHY THIS EXISTS
---------------
Three questions about an issue can be answered from its text alone, and all
three were previously answered by a human remembering to:

  1. Is this issue plan-derived?  `is_plan_derived` reads the `Design:` field.
     If it links into `docs/plans/`, a parent is REQUIRED and `--no-parent` is
     refused by `scripts/file_issue.sh`. That is the repo owner's rule, applied
     mechanically so it does not depend on anyone noticing.

  2. Does a title look like one already on the board?  `possible_duplicates`.
     A truncated board listing hid #164 on 2026-08-19 and a session filed #176
     as a duplicate of it. The filing tool now prints near-duplicates and makes
     a human say yes.

  3. Does this body state an order between two pieces of work?
     `states_prose_ordering`. `docs/WORKFLOW.md` requires such an order to be
     recorded as a `dependencies/blocked_by` link in the same change; the
     2026-08-19 ordering audit found 16 that were not.

This module reads text. It calls nothing, writes nothing, and knows nothing
about GitHub. `scripts/file_issue.sh` shells out to the CLI at the bottom.

CLI (for the bash caller)
    python3 issue_text.py plan-derived --config <config.json> <body-file>
        # exit 0 = plan-derived (reads plan_dir from the config)
    python3 issue_text.py design-line  [--config <config.json>] <body-file>
        # prints the Design: line
    python3 issue_text.py dupes [--config <config.json>] <title> <candidates.json>

--config is accepted by every subcommand for a single consistent CLI surface,
but only `plan-derived` actually reads it (for its `plan_dir` field) --
`design-line` and `dupes` are pure text operations that need no config.
"""

import json
import re
import sys

# Matches `**Design:** ...`, `Design: ...`, `## Design`, `- **Design:** ...`.
_DESIGN_LINE = re.compile(
    r"^\s*(?:[-*+]\s*)?(?:\#{1,6}\s*)?\*{0,2}\s*Design\s*\*{0,2}\s*:?\s*\*{0,2}\s*(.*)$",
    re.IGNORECASE,
)


def design_field(body):
    """
    Return the `Design:` line as written, or None.

    When the field is a heading with its value on a following line
    (`## Design` then `none`), the value line is appended so the caller sees
    the whole answer.
    """
    lines = body.splitlines()
    for i, line in enumerate(lines):
        m = _DESIGN_LINE.match(line)
        if not m:
            continue
        value = m.group(1).strip()
        if value:
            return line.rstrip()
        for follow in lines[i + 1:]:
            if follow.strip():
                return line.rstrip() + "\n" + follow.rstrip()
        return line.rstrip()
    return None


def is_plan_derived(body, plan_dir):
    """
    True when the `Design:` field links into `plan_dir` (e.g. `docs/plans/`).

    Only the field counts. A mention of `plan_dir` in the prose is not a
    design link, and a link to a narrative document elsewhere in the repo is
    not a plan unit. `plan_dir` is the consuming repo's own config value
    (KTD3) -- this function no longer reads a hardcoded constant, so a caller
    that forgets to supply it gets a TypeError, not a silently-wrong default.
    """
    line = design_field(body)
    return bool(line) and plan_dir in line



STOPWORDS = {
    "the", "and", "for", "into", "onto", "with", "from", "that", "this", "then",
    "than", "are", "was", "were", "has", "have", "had", "not", "but", "its",
    "it's", "all", "any", "our", "out", "off", "per", "via", "you", "your",
    "can", "will", "should", "must", "when", "what", "which", "who", "how",
    "why", "where", "them", "they", "their", "there", "been", "being", "does",
    "did", "done", "get", "got", "make", "made", "one", "two", "now", "new",
    "old", "yes", "some", "each", "every", "more", "most", "less", "only",
    "also", "just", "still", "before", "after", "once", "over", "under",
    "about", "against", "between", "both", "same", "such", "own", "too",
    "very", "these", "those", "here",
}

_WORD = re.compile(r"[a-z0-9]+")
_BACKTICK = re.compile(r"`([^`]+)`")
_QUOTED = re.compile(r"[\"“]([^\"”]+)[\"”]")

MIN_WORD_LEN = 3


def significant_words(title):
    """Lowercased words of >= MIN_WORD_LEN characters that are not stopwords."""
    return {
        w
        for w in _WORD.findall(title.lower())
        if len(w) >= MIN_WORD_LEN and w not in STOPWORDS
    }


def code_tokens(title):
    """
    Lowercased `backticked` and "quoted" tokens, delimiters kept.

    These carry more weight than an ordinary word: two issues that both name
    `Fix:` or "NeedsReview" are about the same thing far more often than two
    issues that happen to share a common noun.
    """
    out = set()
    for m in _BACKTICK.findall(title):
        out.add("`" + m.strip().lower() + "`")
    for m in _QUOTED.findall(title):
        out.add('"' + m.strip().lower() + '"')
    return out


def _cores(tokens):
    return {t.strip("`\"“”").lower() for t in tokens}


def possible_duplicates(new_title, candidates, min_shared=2):
    """
    Candidates worth a human look before creating `new_title`.

    `candidates` is an iterable of (number, title). Flags on two or more shared
    significant words, or on any one shared code token. Returns
    [(number, title, why)] with `why` naming what they share, because a list of
    numbers with no reason is a list a hurried session scrolls past.
    """
    new_words = significant_words(new_title)
    new_codes = _cores(code_tokens(new_title))
    hits = []
    for number, title in candidates:
        shared_codes = new_codes & _cores(code_tokens(title))
        shared_words = new_words & significant_words(title)
        if shared_codes:
            why = "shares code token: " + ", ".join(sorted(shared_codes))
        elif len(shared_words) >= min_shared:
            why = "shares: " + ", ".join(sorted(shared_words))
        else:
            continue
        hits.append((number, title, why))
    return hits



# Cues strong enough to stand alone: they only ever describe one thing gating another.
_STRONG_CUES = re.compile(
    r"\b(?:"
    r"gate[sd]?\s+on"
    r"|is\s+the\s+gate"
    r"|blocked\s+(?:on|by)"
    r"|prerequisite"
    r"|depends?\s+on\s+(?:the|that|this|#)"
    r"|must\s+(?:happen|run|come|be\s+done)\s+(?:before|after)"
    r"|waits?\s+(?:for|until)"
    r"|stays?\s+open\s+until"
    r"|revisit\s+(?:once|after|when)"
    r")\b",
    re.IGNORECASE,
)

# Cues that mean an inter-issue order only when a specific piece of work follows ("before 1975" is not one).
_WEAK_CUES = re.compile(r"\b(?:before|after|until|once|then)\b", re.IGNORECASE)

_CLAUSE_END = re.compile(r"[,;:.!?—]|\Z")

_DEFINITE = re.compile(
    r"^\s*(?:"
    r"the\b|that\b|this\b|those\b|these\b|its\b"
    r"|then\b"
    r"|#\d+"
    r"|[uU]\d"
    r"|[A-Z][A-Za-z0-9-]*\b"      # a proper name: Mylio, Google Photos, Phase 7
    r")",
)

_INDEFINITE = re.compile(
    r"^\s*(?:"
    r"a\b|an\b|any\b|each\b|every\b|another\b|some\b|no\b"
    r"|anything\b|nothing\b|everything\b|something\b"
    r"|you\b|your\b|we\b|i\b"
    r"|\d"
    r")",
    re.IGNORECASE,
)

# The object must name work, or "stops before the block that holds `ContentIdentifier`" reads as an order.
_WORK_REF = re.compile(
    r"\b(?:"
    r"upload(?:s|ed|ing)?|backup|back\s?ups?"
    r"|verif(?:y|ied|ies|ication)"
    r"|delet(?:e|ed|es|ion)|remov(?:e|ed|al)|wipe[ds]?|retir(?:e|ed|ement)"
    r"|re-?sort(?:ed|s)?|renam(?:e|ed)|mov(?:e|ed)"
    r"|export(?:ed|s)?|import(?:ed|s)?|migrat(?:e|ed|ion)"
    r"|decommission(?:ed)?|consolidat(?:e|ed|ion)"
    r"|repair(?:ed|s)?|scan(?:ned|s)?|sweep|swept|dedup\w*"
    r"|harvest(?:ed|s)?|reconcil\w*|rotation[s]?"
    r"|run[s]?|ran|pass(?:es)?|round[s]?|review(?:ed|s)?"
    r"|build|built|writ(?:e|ten|es)|wrote"
    r"|snapshot[s]?|sidecar[s]?|tagging"
    r"|phase\s*\d|issue\s*#?\d+|#\d+|\b[uU]\d+\b"
    r")\b",
    re.IGNORECASE,
)

# Template boilerplate ("Dry run first", "Before you start") and "before and after X" comparisons are not orderings.
_BOILERPLATE = re.compile(
    r"\b(?:dry\s+run\s+first|before\s+you\s+start|after\s+you\s+finish"
    r"|before\s+you\s+run|read\s+this\s+before"
    r"|before\s+and\s+after|after\s+and\s+before"
    r"|nothing\s+(?:is|was|are|were)\s+blocked)\b",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n")


def _sentences(body):
    for chunk in _SENTENCE_SPLIT.split(body):
        chunk = chunk.strip()
        if chunk:
            yield chunk


def states_prose_ordering(body):
    """
    Sentences that state an order between this work and other work.

    Returns the matched sentences, not a boolean, so the audit can print the
    evidence and a reader can disagree with it.

    The naive version of this reported 34 of 66 open issues. Two things it got
    wrong are handled here: a weak cue only counts when what follows it names a
    specific other piece of work (so "years before 1975" and "before any
    snapshot-taking run" do not count), and the issue templates' own
    boilerplate is excluded. The third thing it got wrong -- checking only
    `blocked_by`, when "do this before the upload" is correctly recorded as
    BLOCKING the upload -- belongs to the caller, and `board_audit.py` checks
    both directions.
    """
    hits = []
    for sentence in _sentences(body):
        if _BOILERPLATE.search(sentence):
            continue
        if _STRONG_CUES.search(sentence):
            hits.append(sentence)
            continue
        matched = False
        for m in _WEAK_CUES.finditer(sentence):
            if m.group(0).lower() == "then":
                # "then" counts only as the object of another cue ("until then"), which the object test below handles.
                continue
            rest = sentence[m.end():]
            end = _CLAUSE_END.search(rest).start()
            obj = rest[:end] if end else rest
            if _INDEFINITE.match(obj):
                continue
            if _DEFINITE.match(obj) and _WORK_REF.search(obj):
                matched = True
                break
        if matched:
            hits.append(sentence)
    return hits




def _extract_config_flag(args):
    """Pull a `--config <path>` pair out of `args`, wherever it appears.

    Returns (config_path_or_None, remaining_positional_args). Every
    subcommand accepts --config for one consistent CLI surface (KTD3); only
    `plan-derived` requires the value it names.
    """
    args = list(args)
    if "--config" not in args:
        return None, args
    i = args.index("--config")
    if i + 1 >= len(args):
        print("ERROR: --config needs a value.", file=sys.stderr)
        sys.exit(2)
    config_path = args[i + 1]
    del args[i:i + 2]
    return config_path, args


def load_plan_dir(config_path):
    """Read the `plan_dir` field out of a JSON config file, or raise."""
    with open(config_path, encoding="utf-8") as fh:
        config = json.load(fh)
    plan_dir = config.get("plan_dir")
    if not plan_dir:
        raise SystemExit(
            f"ERROR: config {config_path} is missing required field: plan_dir")
    return plan_dir


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    cmd = argv[1]
    config_path, rest = _extract_config_flag(argv[2:])
    if cmd == "plan-derived":
        if config_path is None:
            print("ERROR: plan-derived requires --config <path>.", file=sys.stderr)
            return 2
        plan_dir = load_plan_dir(config_path)
        with open(rest[0], encoding="utf-8") as fh:
            body = fh.read()
        return 0 if is_plan_derived(body, plan_dir) else 1
    if cmd == "design-line":
        with open(rest[0], encoding="utf-8") as fh:
            body = fh.read()
        line = design_field(body)
        if line is None:
            return 1
        print(line)
        return 0
    if cmd == "dupes":
        title = rest[0]
        with open(rest[1], encoding="utf-8") as fh:
            rows = json.load(fh)
        cands = [(r["number"], r["title"]) for r in rows]
        for number, cand_title, why in possible_duplicates(title, cands):
            print(f"#{number}\t{cand_title}\t({why})")
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
