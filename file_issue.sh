#!/bin/bash
# scripts/file_issue.sh — the only supported way to put an issue on the board,
# whether it is created here or already exists and is being wired.
#
# WHY THIS REFUSES INSTEAD OF REMINDING
# ------------------------------------
# docs/WORKFLOW.md § "Recording an ordering constraint" already says an order
# between two pieces of work must be recorded as a blocker in the same change
# that writes the issue. On 2026-08-19 that rule was broken three times in one
# day, by sessions that had read it in the same sitting. The 2026-08-19 ordering
# audit found 16 stated constraints with no blocker link — including the iCloud
# wipe (#138) sitting 40 positions ahead of the work establishing that 329
# photos exist only in iCloud, which the § 7 query would have offered as ready
# to start.
#
# So the four placement questions are flags, all four REQUIRED, each with an
# explicit way to say "none". A missing one is an error naming the flag. There
# is no default, because a default is what gets taken silently. Adopt mode asks
# exactly the same four.
#
# Separately: a truncated board listing hid #164 well enough that a session
# filed #176 as a duplicate of it. So this prints the board neighbourhood and
# any near-duplicate titles, stops before writing when there are any, and treats a truncated
# board as fatal rather than as a short board.
#
# And nothing here reports success from an exit code. Every relationship is
# applied and then READ BACK, by ONE shared read-back that both modes call. A
# mismatch names the relationship and says what state the issue was left in, so
# it can be finished by hand.
#
# The board half of that read-back resolves THREE states, not two. A write to
# project 2 is not read-your-writes consistent, so a listing that does not show
# the issue may mean the write has not propagated, that it did not land, or
# that the read did not answer. Reading it as one state declared four correctly
# wired filings HALF-WIRED and told the operator to delete them. So the READ is
# retried on a finite bound (never the write), and each of the three states
# refuses in its own words with a next action that is safe on a correctly wired
# issue.
#
# >>> HELP BLOCK START
# USAGE — two modes. Both answer the same four placement questions. Both
# require --config, naming the JSON file that supplies this board's repo,
# owner, project number, shape/label vocabulary and plan-derived rules (see
# config.example.json).
#
#   CREATE a new issue and wire it:
#     bash file_issue.sh --config config.json \
#         --title "..." --body-file body.md --shape work \
#         (--parent N | --no-parent) \
#         (--after N | --top) \
#         (--blocked-by N,N | --blocked-by none) \
#         (--blocks N,N | --blocks none) \
#         [--dry-run] [--file-anyway]
#
#   ADOPT an issue that already exists and wire it:
#     bash file_issue.sh --config config.json --adopt N \
#         (--parent N | --no-parent) \
#         (--after N | --top) \
#         (--blocked-by N,N | --blocked-by none) \
#         (--blocks N,N | --blocks none) \
#         [--dry-run]
#
#   --shape is one of the names in --config's `shapes` list. It sets the
#   labels that config names for it. It belongs to create only.
#
#   --adopt is mutually exclusive with --title, --body-file and --shape: an
#   issue that already exists has all three already.
#
#   Adopt mode refuses rather than reconciles. If the issue is closed, sits
#   under a different parent, or carries a blocked-by or blocks link this
#   invocation did not name, it stops and prints the
#   `gh api -X DELETE` command that clears each contradiction. It
#   writes only the relationships that are not already there, and reads every
#   one of them back regardless.
#
#   The one thing adopt does NOT refuse is the board POSITION. All four
#   placement answers are mandatory, so a position is always named, and adopt
#   MOVES the issue to it. The summary names where the issue sits today beside
#   where you are sending it, and the move is recorded as a comment on the
#   issue once the read-back proves it landed.
#
#   WHERE GRAPHQL IS REFUSED (a Claude Code cloud session, for one). Every
#   call goes over GitHub's REST API except the board-position write, which
#   has no REST route. When GitHub refuses that write with HTTP 403, the run
#   still files and wires the issue, reads every relationship back, and exits
#   0. The read-back says the board position is NOT SET, the issue sits wherever
#   the board put it (usually the bottom), and a notice prints the adopt
#   command that places it from a session where GraphQL works. No move
#   comment is written in that case, because nothing moved; the adopt run
#   that places it later records its own move.
#
#   There is no confirmation prompt; a run without --dry-run writes. The one
#   exception is a create run that finds possible duplicates: it prints them
#   and stops with exit code 3, having created nothing. Re-run with
#   --file-anyway once you have ruled them out. Every other refusal exits 1.
#
#   --dry-run stops after the board neighbourhood, the duplicate check and the
#   summary. Nothing is created and nothing is changed.
#
#   BODIES AND COMMENTS. This script never edits the body of an issue that
#   already exists — adopt refuses --body-file for that reason. But the rule
#   about bodies binds anything that comments on an issue, so it is stated
#   where the tool is read: a comment may ADD a measurement, a decision or
#   progress; it may NOT leave the body saying something the comment
#   contradicts. If your comment corrects the body, rewrite the body in the
#   same action, date the rewrite at the top of it, and leave the comments as
#   the record with "where they disagree with the body, the body wins."
#   GitHub renders the body first and above the fold, so the superseded
#   instruction is the one in the reading position. See docs/WORKFLOW.md
#   section "A comment that corrects the body corrects the body".
# <<< HELP BLOCK END

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEIGHBOURS=3
# REPO, OWNER, PROJECT_NUMBER, PROJECT_ID, the shape/label vocabulary, the
# plan-derived path (PLAN_DIR) and whether a Design: line is required at all
# (DESIGN_LINE_REQUIRED) are no longer hardcoded here. They are read from the
# JSON file named by --config, once the argument parser below has run --
# see "Load and validate --config" further down, and config.example.json.

# READ-BACK RETRY BOUND (KD1: retry the READ, never the write).
#
# A write to project 2 is not read-your-writes consistent. Four correctly
# wired filings were declared HALF-WIRED because the board listing was read
# before it had caught up, and the refusal told the operator to delete the
# issue. So the read-back re-reads on a finite, growing wait.
#
# HARD CEILING: the total wall-clock wait for ONE read-back must never exceed
# 30 SECONDS. With the defaults below the waits are 1 + 2 + 4 + 8 = 15s across
# 5 attempts, provably under the ceiling. Anything raising either default must
# re-check that sum against it.
#
# MEASURED 2026-08-24, against the live board (154 items, 2 pages), gh 2.98.0.
# Seven real filings and adoptions were made that day. SIX of the seven had a
# read-back that was clean on the FIRST attempt — the race did not fire once
# naturally, in a session that also filed several within seconds of each
# other. So there is no observed natural convergence time to calibrate to,
# and these numbers are NOT calibrated to one. State that plainly rather than
# implying a measurement that was not taken.
#
# What WAS measured: the retry path itself, exercised against genuine GitHub
# responses by dropping the new issue's row from the first board read only
# (the injection R16 permits). It converged on attempt 2 after a 1-second
# wait, and reported `board read ok on attempt 2 of 5`. Against the pre-U3
# script that same condition produced the false HALF-WIRED alarm, complete
# with the delete-and-re-run remedy.
#
# The bound below is therefore set from the CEILING, not from a convergence
# curve: as many attempts as fit comfortably under 30 seconds. If a refusal
# ever reports success on the final attempt, the warning it prints is the
# signal to come back and re-measure — by then there will be a real curve.
#
# UNRESOLVED, and recorded rather than guessed: whether the underlying cause
# is Projects replication lag or a listing read torn across the two pages
# while a write lands. The race never fired naturally here, so nothing
# distinguished them. A bounded retry mitigates both.
#
# THIS IS THE COMING BACK (#265, 2026-08-25). Filing #264 succeeded on
# attempt 5 of 5 at 15s cumulative wait — the FIRST time the signal above
# fired for real. That places real convergence somewhere in (7s, 15s], the
# first actual data point since this file was written. It is one filing, not
# a curve, so this is a minimal fix to the warning the signal exposed, not
# the full measurement campaign that would build one — that campaign is
# deliberately deferred rather than run here.
#
# THE WARNING BUG THAT FIRED: the old text told the operator to "raise
# FILE_ISSUE_READBACK_ATTEMPTS / _DELAY", but raising ATTEMPTS alone almost
# always overshoots the ceiling below — the wait DOUBLES each attempt, so
# ATTEMPTS=6 at the current DELAY needs 31s, one second over. DELAY is the
# lever with headroom: it scales the SAME doubling series linearly, at the
# SAME attempt count. The warning below now computes, from the live
# ATTEMPTS, the highest DELAY the ceiling still accepts, and names that —
# never a knob the check two screens down will refuse.
#
# THE DELAY=0 QUESTION, decided rather than left open: DELAY=0 keeps passing
# the ceiling check at any ATTEMPTS, because the doubling sum of zero is
# always zero — it was flagged as a loophole that "adds attempts but no
# wall-clock tolerance". It stays allowed, deliberately: the ceiling exists
# to bound real wall-clock hang risk, and a wait that is always zero cannot
# create that risk regardless of ATTEMPTS. It is also load-bearing —
# tests/test_engine_gating.py runs the retry path at DELAY=0 to stay
# fast and deterministic. What DELAY=0 does NOT do is buy extra retries with
# real tolerance; an operator chasing more real wall-clock budget still
# needs a non-zero DELAY, per the warning above.
READBACK_ATTEMPTS="${FILE_ISSUE_READBACK_ATTEMPTS:-5}"
READBACK_DELAY="${FILE_ISSUE_READBACK_DELAY:-1}"
READBACK_WAITED=0   # seconds actually spent waiting, reported in every refusal

CONFIG=""
TITLE=""
BODY_FILE=""
SHAPE=""
ADOPT=""
# THE MOVE RECORD (adopt mode only), latched where the pre-write summary
# decides it. Adopt does not refuse a reposition — it MOVES the issue — and
# until this existed the slot it moved FROM was recorded nowhere, so a real
# prior priority decision vanished the moment it was overwritten. These three
# carry that slot from the POSITION_LINE block, which already computes it for
# the screen, down to the comment written after the read-back proves the move
# landed. They are NEVER recomputed: one branch decides, so the screen and the
# comment cannot disagree.
#
# They are defaulted HERE, beside the other argument defaults, because create
# mode never runs the block that latches them and this script runs under
# `set -u`. An adopt of an issue that is not yet on the board leaves them at
# these defaults too — there is no origin slot to name, so there is nothing to
# record.
ADOPT_MOVED=0
ADOPT_FROM_IDX=""
ADOPT_FROM_PREV=""
ADOPT_LANDED_IDX=""
PARENT=""
NO_PARENT=0
AFTER=""
TOP=0
BLOCKED_BY=""
BLOCKED_BY_SET=0
BLOCKS=""
BLOCKS_SET=0
DRY_RUN=0
FILE_ANYWAY=0

die() { printf '%s\n' "$*" >&2; exit 1; }

# A bound of zero attempts is a read-back that never reads, which would be a
# vacuous pass in the one guard this script is. Refuse it rather than accept
# it. A delay of zero is legitimate — the test suite uses it — but an attempt
# count of zero, or either value non-numeric, is not.
case "$READBACK_ATTEMPTS" in
  ''|*[!0-9]*) die "ERROR: FILE_ISSUE_READBACK_ATTEMPTS must be a whole number of attempts (got: $READBACK_ATTEMPTS)." ;;
esac
[ "$READBACK_ATTEMPTS" -ge 1 ] || die "ERROR: FILE_ISSUE_READBACK_ATTEMPTS must be at least 1; a read-back that never reads verifies nothing."
case "$READBACK_DELAY" in
  ''|*[!0-9]*) die "ERROR: FILE_ISSUE_READBACK_DELAY must be a whole number of seconds (got: $READBACK_DELAY)." ;;
esac

# THE CEILING IS ENFORCED, not merely stated. Validating only the FORMAT of the
# two variables let `FILE_ISSUE_READBACK_ATTEMPTS=50 FILE_ISSUE_READBACK_DELAY=10`
# through — a worst case of well over an hour, contradicting the 30-second
# ceiling this file states a few lines above. It cannot make the guard pass, but
# it can hang a session for as long as it likes, and a ceiling that nothing
# checks is a comment, not a bound. The sum below is the same doubling series
# the retry loop walks: delay + 2*delay + ... across ATTEMPTS-1 waits. It stops
# adding as soon as it is over, so an absurd attempt count cannot overflow.
READBACK_CEILING=30
READBACK_WORST_CASE=0
readback_d="$READBACK_DELAY"
readback_i=1
while [ "$readback_i" -lt "$READBACK_ATTEMPTS" ]; do
  READBACK_WORST_CASE=$(( READBACK_WORST_CASE + readback_d ))
  [ "$READBACK_WORST_CASE" -gt "$READBACK_CEILING" ] && break
  readback_d=$(( readback_d * 2 ))
  readback_i=$(( readback_i + 1 ))
done
unset readback_d readback_i
if [ "$READBACK_WORST_CASE" -gt "$READBACK_CEILING" ]; then
  die "ERROR: FILE_ISSUE_READBACK_ATTEMPTS=$READBACK_ATTEMPTS with FILE_ISSUE_READBACK_DELAY=$READBACK_DELAY
       would wait at least ${READBACK_WORST_CASE}s on one read-back, over the
       ${READBACK_CEILING}-second ceiling this script sets for itself. The waits double:
       ${READBACK_DELAY}s, then twice that, and so on across $READBACK_ATTEMPTS attempts.
       Lower one of the two, or raise the ceiling deliberately and re-measure."
fi

usage() {
  # Delimited, never a line range. A fixed range silently ran past the header
  # once the header grew, and printed shell code as help.
  awk '/^# >>> HELP BLOCK START$/ {inblock=1; next}
       /^# <<< HELP BLOCK END$/   {inblock=0}
       inblock' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --config)     CONFIG="${2-}"; shift 2 || die "ERROR: --config needs a value." ;;
    --title)      TITLE="${2-}"; shift 2 || die "ERROR: --title needs a value." ;;
    --body-file)  BODY_FILE="${2-}"; shift 2 || die "ERROR: --body-file needs a value." ;;
    --shape)      SHAPE="${2-}"; shift 2 || die "ERROR: --shape needs a value." ;;
    --adopt)      ADOPT="${2-}"; shift 2 || die "ERROR: --adopt needs a value." ;;
    --parent)     PARENT="${2-}"; shift 2 || die "ERROR: --parent needs a value." ;;
    --no-parent)  NO_PARENT=1; shift ;;
    --after)      AFTER="${2-}"; shift 2 || die "ERROR: --after needs a value." ;;
    --top)        TOP=1; shift ;;
    --blocked-by) BLOCKED_BY="${2-}"; BLOCKED_BY_SET=1; shift 2 || die "ERROR: --blocked-by needs a value." ;;
    --blocks)     BLOCKS="${2-}"; BLOCKS_SET=1; shift 2 || die "ERROR: --blocks needs a value." ;;
    --dry-run)    DRY_RUN=1; shift ;;
    --file-anyway) FILE_ANYWAY=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    *)            die "ERROR: unknown flag: $1" ;;
  esac
done

if [ -n "$ADOPT" ]; then MODE=adopt; else MODE=create; fi
if [ "$MODE" = adopt ]; then NOTHING="Nothing was changed."; else NOTHING="Nothing was created."; fi

# ---------------------------------------------------------------------------
# Load and validate --config. Everything the header used to hardcode --
# REPO, OWNER, PROJECT_NUMBER, PROJECT_ID, the shape/label vocabulary, the
# plan-derived path, and whether a Design: line is required at all -- comes
# from this one JSON file, read once, here, before any network call. A
# missing or malformed field fails now, offline, naming the field, rather
# than surfacing as a confusing GraphQL error deep inside a write.
# ---------------------------------------------------------------------------

[ -n "$CONFIG" ] || die "ERROR: --config is required, naming the JSON config file for
       this board (repo, owner, project number, shapes/labels, plan-derived
       rules -- see config.example.json). $NOTHING"
[ -f "$CONFIG" ] || die "ERROR: --config names a file that does not exist: $CONFIG"
command -v jq >/dev/null 2>&1 || die "ERROR: jq is required to read --config and was not found on PATH."
jq -e . "$CONFIG" >/dev/null 2>&1 || die "ERROR: --config $CONFIG is not valid JSON."

REPO="$(jq -r '.repo // empty' "$CONFIG")"
OWNER="$(jq -r '.owner // empty' "$CONFIG")"
PROJECT_NUMBER="$(jq -r '.project_number // empty' "$CONFIG")"
PROJECT_ID="$(jq -r '.project_id // empty' "$CONFIG")"
PLAN_DIR="$(jq -r '.plan_dir // empty' "$CONFIG")"
DESIGN_LINE_REQUIRED="$(jq -r 'if (.design_line_required // false) then "true" else "false" end' "$CONFIG")"
# human_review_required is a JSON boolean, missing meaning true. The engine
# only validates it; the skill reads it to decide whether a human previews
# first. Check the TYPE: jq's `//` treats false as absent, and a string "true"
# would pass a value check.
HUMAN_REVIEW_TYPE="$(jq -r 'if has("human_review_required") then (.human_review_required | type) else "boolean" end' "$CONFIG")"

[ -n "$REPO" ] || die "ERROR: config $CONFIG is missing required field: repo"
case "$REPO" in
  */*) ;;
  *) die "ERROR: config $CONFIG's repo must be OWNER/NAME (got: $REPO)." ;;
esac
[ -n "$OWNER" ] || die "ERROR: config $CONFIG is missing required field: owner"
case "$PROJECT_NUMBER" in
  ''|*[!0-9]*) die "ERROR: config $CONFIG is missing or has a non-numeric project_number (got: ${PROJECT_NUMBER:-<empty>})." ;;
esac
[ -n "$PROJECT_ID" ] || die "ERROR: config $CONFIG is missing required field: project_id
       (the project board's node id -- needed to set a board position). $NOTHING"
PROJECT_PATH="users/$OWNER/projectsV2/$PROJECT_NUMBER"
if [ "$DESIGN_LINE_REQUIRED" = "true" ] && [ -z "$PLAN_DIR" ]; then
  die "ERROR: config $CONFIG sets design_line_required=true but has no plan_dir set."
fi
[ "$HUMAN_REVIEW_TYPE" = "boolean" ] || die "ERROR: config $CONFIG's human_review_required must be true or false
       (got: $(jq -c '.human_review_required' "$CONFIG"))."

SHAPE_COUNT="$(jq -r '(.shapes // []) | length' "$CONFIG")"
[ "$SHAPE_COUNT" -gt 0 ] || die "ERROR: config $CONFIG defines zero shapes. At least one
       shape (a name and its labels) is required."
BAD_SHAPE="$(jq -r '(.shapes // [])[] | select((.labels // []) | length == 0) | .name' "$CONFIG" | head -1)"
[ -z "$BAD_SHAPE" ] || die "ERROR: config $CONFIG's shape '$BAD_SHAPE' has no labels
       defined. Every shape needs at least one label."
SHAPE_NAMES="$(jq -r '[(.shapes // [])[].name] | join(", ")' "$CONFIG")"

# ---------------------------------------------------------------------------
# The OFFLINE stage of the gate. Nothing in this block touches the network.
#
# Adopt mode's gate runs in TWO stages: this one, and a post-fetch stage after
# the issue is read but still before any write. The parenting rule needs the
# issue body, and for an existing issue the body only arrives over the network.
# ---------------------------------------------------------------------------

if [ "$MODE" = adopt ]; then
  for pair in "--title:$TITLE" "--body-file:$BODY_FILE" "--shape:$SHAPE"; do
    if [ -n "${pair#*:}" ]; then
      die "ERROR: --adopt and ${pair%%:*} are contradictory. $NOTHING
       --adopt names an issue that already exists, so its title, body and
       shape are already on the server. Pass the four placement answers only."
    fi
  done
  [ "$FILE_ANYWAY" -eq 0 ] || die "ERROR: --adopt and --file-anyway are contradictory. $NOTHING
       --file-anyway waves a create run past its possible duplicates. Adopt
       has no duplicate check, because the issue already exists."
  case "$ADOPT" in
    *[!0-9]*|"") die "ERROR: --adopt takes an issue number (got: $ADOPT). $NOTHING" ;;
  esac
else
  [ -n "$TITLE" ] || die "ERROR: --title is required. Nothing was created."
  [ -n "$BODY_FILE" ] || die "ERROR: --body-file is required. Nothing was created."
  [ -f "$BODY_FILE" ] || die "ERROR: --body-file names a file that does not exist: $BODY_FILE"
  [ -n "$SHAPE" ] || die "ERROR: --shape is required, one of: $SHAPE_NAMES. Nothing was created."

  SHAPE_LABELS="$(jq -r --arg s "$SHAPE" '(.shapes // [])[] | select(.name == $s) | .labels[]' "$CONFIG")"
  [ -n "$SHAPE_LABELS" ] || die "ERROR: --shape must be one of: $SHAPE_NAMES (got: $SHAPE). Nothing was created."
  # The create is `gh api -X POST repos/{repo}/issues`, which takes labels as
  # an array field: one `labels[]=` per label.
  LABEL_FIELDS=()
  while IFS= read -r lbl; do
    [ -n "$lbl" ] && LABEL_FIELDS+=(-f "labels[]=$lbl")
  done <<<"$SHAPE_LABELS"
fi

if [ -n "$PARENT" ] && [ "$NO_PARENT" -eq 1 ]; then
  die "ERROR: --parent and --no-parent are contradictory. Pass exactly one. $NOTHING"
fi
if [ -z "$PARENT" ] && [ "$NO_PARENT" -eq 0 ]; then
  die "ERROR: no parent answer. Pass --parent <N> or --no-parent.
       Every issue answers this. There is no default."
fi
# --parent is an ISSUE NUMBER, and it is digit-validated here for the same
# reason --adopt is. A typo that survives the offline gate is not caught until
# the read-back, and by then a REAL issue exists whose parent never landed —
# so the operator is handed the create-mode remedy, "delete #N and re-run", for
# a mistake that cost nothing to catch before anything was written.
if [ -n "$PARENT" ]; then
  case "$PARENT" in
    *[!0-9]*) die "ERROR: --parent takes an issue number (got: $PARENT). $NOTHING" ;;
  esac
fi

if [ -n "$AFTER" ] && [ "$TOP" -eq 1 ]; then
  die "ERROR: --after and --top are contradictory. Pass exactly one. $NOTHING"
fi
if [ -z "$AFTER" ] && [ "$TOP" -eq 0 ]; then
  die "ERROR: no board-position answer. Pass --after <N> or --top.
       Every issue answers this. There is no default — an unpositioned issue
       lands wherever the board put it, which is not a priority decision."
fi
# --after is an ISSUE NUMBER too, and it is validated for a second reason on
# top of the typo one: the board lookups that use it are grep matches, and an
# unvalidated value is a REGEX. `printf '101\n144\n107\n' | grep -qx '1.4'`
# succeeds, so `--after 1.4` used to pass the "is it on the board" gate, the
# issue was created, and the lookup of a non-number then failed
# and left the run reporting HALF-WIRED with the delete remedy. Both halves are
# fixed: digits only here, and -F (fixed string) on every board lookup below.
if [ -n "$AFTER" ]; then
  case "$AFTER" in
    *[!0-9]*) die "ERROR: --after takes an issue number (got: $AFTER). $NOTHING" ;;
  esac
fi

if [ "$BLOCKED_BY_SET" -eq 0 ]; then
  die "ERROR: no blocked-by answer. Pass --blocked-by <N,N,...> or --blocked-by none.
       Every issue answers this. There is no default — an ordering constraint
       that lives only in the issue's prose is invisible to the board."
fi
if [ "$BLOCKS_SET" -eq 0 ]; then
  die "ERROR: no blocks answer. Pass --blocks <N,N,...> or --blocks none.
       Every issue answers this. There is no default — \"do this before the
       upload\" is recorded as BLOCKING the upload, and that direction is the
       one sessions forget."
fi

parse_list() {
  # "none" (any case) or empty means the empty set.
  local raw="$1" n
  case "$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')" in
    none|"") return 0 ;;
  esac
  # Note the trailing newline: `read` drops a final line that has none, and a
  # silently dropped blocker is the exact failure this whole script exists to
  # stop.
  # `sort -n -u` is not cosmetic. `--blocked-by 122,122` used to make the
  # WANTED set "122,122" while the server — which cannot hold the same link
  # twice — correctly read back "122". A CORRECTLY WIRED issue then failed its
  # own read-back and, in create mode, was told to delete itself. The same
  # repeat would also have written the link twice, and a second write of an
  # already-present link is refused (it failed the whole `gh issue edit
  # --add-blocked-by 122,122` call this script used to make). De-duplicating HERE
  # fixes the write side and the compare side together, which is the only way
  # the two stay in agreement.
  printf '%s\n' "$raw" | tr ',' '\n' | while read -r n; do
    n="$(printf '%s' "$n" | tr -d '[:space:]#')"
    [ -n "$n" ] || continue
    case "$n" in
      *[!0-9]*) printf 'BAD\n' ;;
      *) printf '%s\n' "$n" ;;
    esac
  done | sort -n -u
}

BLOCKED_LIST="$(parse_list "$BLOCKED_BY")"
BLOCKS_LIST="$(parse_list "$BLOCKS")"
case "$BLOCKED_LIST" in *BAD*) die "ERROR: --blocked-by takes issue numbers or the word none (got: $BLOCKED_BY)." ;; esac
case "$BLOCKS_LIST" in *BAD*) die "ERROR: --blocks takes issue numbers or the word none (got: $BLOCKS)." ;; esac

# The parenting rule. Decided by the repo owner: a parent is REQUIRED when the
# issue is plan-derived, and a judgement call otherwise. Plan-derived is read
# mechanically off the body's `Design:` field. On the create path the body is
# already on disk; on the adopt path it arrives with the post-fetch stage, and
# this same function is applied to it there.
parenting_rule() {
  local body_file="$1" design_line
  # Whether this rule applies AT ALL is itself config-driven -- Pluckd's
  # config has no Design-line requirement unless it adds one.
  [ "$DESIGN_LINE_REQUIRED" = "true" ] || return 0
  if python3 "$SCRIPT_DIR/issue_text.py" plan-derived --config "$CONFIG" "$body_file"; then
    if [ "$NO_PARENT" -eq 1 ]; then
      design_line="$(python3 "$SCRIPT_DIR/issue_text.py" design-line --config "$CONFIG" "$body_file")"
      die "ERROR: this issue is plan-derived, so --parent is required and --no-parent is refused.
       Its Design: field links into $PLAN_DIR —

         $design_line

       Pass --parent <N> naming the plan-parent issue for that plan.
       $NOTHING"
    fi
  fi
}

[ "$MODE" = create ] && parenting_rule "$BODY_FILE"

# ---------------------------------------------------------------------------
# The capability probe. Issue #14 moves every GitHub call this script makes to
# `gh api` REST paths, leaving the board-position write as its one GraphQL
# call, and the `gh api` features it uses are old enough to need no version
# check. So the probe asks one thing: is gh on PATH. It used to read `gh issue create/edit --help` and
# `gh issue view --json` for native relationship flags and fields, which the
# REST paths do not use.
#
# The version is READ and PRINTED for the record, and never decides. An
# unreadable version string prints the sentinel `unknown` and the run
# proceeds.
# ---------------------------------------------------------------------------

gh_version_fact() {
  # The installed version, or the sentinel `unknown`. Never a refusal.
  local line v
  line="$(gh --version 2>/dev/null | head -1)"
  case "$line" in
    *"gh version "*) ;;
    *) printf 'unknown\n'; return 0 ;;
  esac
  v="${line#*gh version }"
  v="${v%% *}"
  case "$v" in
    ''|*[!0-9.]*) printf 'unknown\n' ;;
    *) printf '%s\n' "$v" ;;
  esac
}

probe_gh_capability() {
  command -v gh >/dev/null 2>&1 || die "REFUSED: gh is not on PATH.
       This script writes every issue relationship through gh, and reads
       every one of them back through gh. $NOTHING
       Install it (brew install gh), then re-run this command."

  GH_VERSION="$(gh_version_fact)"
  echo "gh capability     ok (gh $GH_VERSION)"
}

probe_gh_capability

# ---------------------------------------------------------------------------
# From here on calls go to the network. Everything down to the --dry-run exit
# and the possible-duplicates stop is still READ-ONLY: nothing creates or
# changes anything before them.
# ---------------------------------------------------------------------------

BOARD_JSON="$(mktemp -t file_issue_board.XXXXXX)"
BOARD_ERR="$(mktemp -t file_issue_boarderr.XXXXXX)"
GH_API_ERR="$(mktemp -t file_issue_ghapierr.XXXXXX)"
cleanup() { rm -f "$BOARD_JSON" "$BOARD_ERR" "$GH_API_ERR" "${BOARD_JSON}.2" "${TITLES_JSON:-}" "${ADOPT_BODY:-}" ; }
trap cleanup EXIT

# REST helpers. gh_api runs `gh api` with its arguments, passes stdout through
# and keeps stderr in $GH_API_ERR, so a caller can tell WHY a call failed:
# gh_api_failed_with reads gh's own "(HTTP NNN)" suffix from it, and a failure
# that does not carry that status is never read as it. gh's message never
# reaches the terminal, so a caller that reports a failure prints gh_api_err.
gh_api() { gh api "$@" 2>"$GH_API_ERR"; }
gh_api_failed_with() { grep -qF "(HTTP $1)" "$GH_API_ERR"; }
gh_api_err() { tr '\n' ' ' <"$GH_API_ERR"; }

issue_numeric_id() {
  # $1 an issue number. Prints the issue's numeric REST `id` -- what the
  # sub-issue, dependency and project-item endpoints take, never the number.
  # Returns 0 found, 2 the issue does not exist (HTTP 404), 1 could not read:
  # any other failure, or a reply with no numeric id. Unable to look is not
  # "does not exist"; only a 404 says that.
  local reply id
  reply="$(gh_api "repos/$REPO/issues/$1")" || { gh_api_failed_with 404 && return 2; return 1; }
  id="$(printf '%s\n' "$reply" \
    | jq -r 'if (.id | type) == "number" and .number != null then .id else empty end' 2>/dev/null)"
  [ -n "$id" ] || return 1
  printf '%s\n' "$id"
}

# The comparison form of an answer set: sorted, DE-DUPLICATED, comma-joined.
# The -u matches parse_list's, because the read-back compares this against what
# the server holds and the server never holds a link twice.
norm() { printf '%s' "$1" | tr ' ' '\n' | sed '/^$/d' | sort -nu | paste -sd, - ; }
csv_of() { printf '%s' "$1" | tr '\n' ',' | sed 's/,$//'; }
in_set() {
  # in_set <needle> <space-separated haystack>
  local n="$1" h
  for h in $2; do [ "$h" = "$n" ] && return 0; done
  return 1
}

# REPLY PARSING. Adopt's pre-fetch and the shared read-back read the same
# three REST replies -- the issue and its two dependency lists -- and both
# parse them HERE, so one reply can never be read two ways. These only parse;
# the read-back is still the one place a relationship is compared.
issue_reply_parent() {
  # $1 a `GET repos/{repo}/issues/{n}` reply its caller has already checked
  # is an issue. Prints the parent's number, nothing for no parent, or BAD.
  # The parent is the number at the end of `parent_issue_url`. GitHub OMITS
  # the key on a parentless issue (measured 2026-10-15), so absent or null is
  # "no parent". Anything else that is not a URL ending in a number is a
  # reply this cannot read, never "no parent".
  local out
  out="$(printf '%s' "$1" | jq -r '
    .parent_issue_url as $u
    | if $u == null then ""
      elif ($u | type) == "string" and ($u | test("/[0-9]+$")) then ($u | capture("/(?<n>[0-9]+)$").n)
      else "BAD" end' 2>/dev/null)" || out="BAD"
  printf '%s\n' "$out"
}

dependency_entries() {
  # $1 a `.../dependencies/blocked_by` or `/blocking` reply. Prints one
  # "number:id:owner/name" per linked issue, sorted by number, nothing for no
  # links, or BAD. Empty is a legal answer, so the reply must be an ARRAY of
  # issues carrying a number and an id: an object here -- an error reply --
  # would otherwise read as "no links". The lists carry issues from OTHER
  # repos too (measured 2026-10-15: this repo's #14 blocks
  # jffriend/pluckd#577), so each entry keeps the repo its `repository_url`
  # names.
  local out
  [ -n "$1" ] || { printf 'BAD\n'; return 0; }
  out="$(printf '%s' "$1" | jq -r --arg repo "$REPO" '
    if type == "array" and all(.[]; (.number | type) == "number" and (.id | type) == "number")
    then (sort_by(.number) | .[]
          | "\(.number):\(.id):\((.repository_url // "") | sub("^.*/repos/"; "") | if . == "" then $repo else . end)")
    else "BAD" end' 2>/dev/null)" || out="BAD"
  [ -z "$out" ] || printf '%s\n' "$out"
}

entry_numbers() {
  # $1 dependency_entries output. Prints the issue numbers, space-separated.
  printf '%s\n' "$1" | sed '/^$/d' | cut -d: -f1 | tr '\n' ' ' | sed 's/ *$//'
}

# ---------------------------------------------------------------------------
# Adopt: the POST-FETCH stage of the gate. Reads the issue, then refuses on a
# closed issue, on the parenting rule, and on any relationship that contradicts
# the answers given. Still before any write.
# ---------------------------------------------------------------------------

FOUND_PARENT=""
FOUND_BLOCKED=""
FOUND_BLOCKING=""
FOUND_BLOCKED_PAIRS=""   # "number:id" per blocker, for the remedies
FOUND_BLOCKING_PAIRS=""
SELF_ID=""               # the numeric REST id of the issue being wired

if [ "$MODE" = adopt ]; then
  # Three REST reads: the issue, and the two dependency lists. Each reply is
  # checked for its SHAPE, not its emptiness, because empty is a legal answer
  # for all three -- no parent, no blockers, blocks nothing -- and a reply of
  # the wrong shape extracts as exactly that.
  ADOPT_JSON="$(gh_api "repos/$REPO/issues/$ADOPT")"
  if [ -z "$(printf '%s' "$ADOPT_JSON" | tr -d '[:space:]')" ] \
     || [ "$(printf '%s' "$ADOPT_JSON" | jq -r 'has("state") and has("number") and ((.id | type) == "number")' 2>/dev/null)" != "true" ]; then
    die "ERROR: --adopt $ADOPT — issue #$ADOPT could not be read from $REPO.
       Check that the number exists and that 'gh auth status' is healthy.
       $NOTHING"
  fi
  # The numeric id the sub-issue and dependency endpoints take for #$ADOPT.
  SELF_ID="$(printf '%s' "$ADOPT_JSON" | jq -r '.id')"

  ADOPT_STATE="$(printf '%s' "$ADOPT_JSON" | jq -r '.state // ""')"
  case "$ADOPT_STATE" in
    OPEN|open) ;;
    *) die "ERROR: --adopt $ADOPT — issue #$ADOPT is ${ADOPT_STATE:-not open}, not open.
       A closed issue is not outstanding work, so it does not go on the board.
       Reopen it first if it should be, then re-run this command. $NOTHING" ;;
  esac

  ADOPT_BODY="$(mktemp -t file_issue_adoptbody.XXXXXX)"
  printf '%s' "$ADOPT_JSON" | jq -r '.body // ""' >"$ADOPT_BODY"
  parenting_rule "$ADOPT_BODY"

  FOUND_PARENT="$(issue_reply_parent "$ADOPT_JSON")"
  [ "$FOUND_PARENT" != "BAD" ] || die "ERROR: --adopt $ADOPT — the parent of #$ADOPT could not be read from $REPO.
       The reply's parent_issue_url is not an issue URL. $NOTHING"

  # The ids are kept beside the numbers, as "number:id:owner/name": the
  # remedies below name them.
  for dep in blocked_by blocking; do
    dep_json="$(gh_api "repos/$REPO/issues/$ADOPT/dependencies/$dep?per_page=100")"
    dep_rc=$?
    dep_pairs="$(dependency_entries "$dep_json")"
    if [ "$dep_rc" -ne 0 ] || [ "$dep_pairs" = "BAD" ]; then
      die "ERROR: --adopt $ADOPT — the $( [ "$dep" = blocked_by ] && echo blocked-by || echo blocks ) links of #$ADOPT could not be read from $REPO.
       $(gh_api_err)
       $NOTHING"
    fi
    if [ "$dep" = blocked_by ]; then FOUND_BLOCKED_PAIRS="$dep_pairs"; else FOUND_BLOCKING_PAIRS="$dep_pairs"; fi
  done
  FOUND_BLOCKED="$(entry_numbers "$FOUND_BLOCKED_PAIRS")"
  FOUND_BLOCKING="$(entry_numbers "$FOUND_BLOCKING_PAIRS")"

  ASKED_BLOCKED="$(printf '%s' "$BLOCKED_LIST" | tr '\n' ' ' | sed 's/ *$//')"
  ASKED_BLOCKING="$(printf '%s' "$BLOCKS_LIST" | tr '\n' ' ' | sed 's/ *$//')"

  # KD2: refuse to reconcile. Silently overwriting a parent or a blocker is the
  # failure this script exists to prevent, and it would be invisible
  # afterwards. Every refusal names the command that clears it — a refusal the
  # operator cannot clear sends them back to the ad hoc commands this tool
  # replaces.
  if [ -n "$FOUND_PARENT" ] && [ "$FOUND_PARENT" != "$PARENT" ]; then
    die "ERROR: --adopt $ADOPT — the parent already there contradicts the answer given.
       $NOTHING
       found:     #$ADOPT sits under #$FOUND_PARENT
       asked for: $( [ -n "$PARENT" ] && printf '#%s' "$PARENT" || printf 'no parent' )

       This refuses rather than reconciling: overwriting a parent would be
       invisible afterwards. Clear it, then re-run this command:

         gh api -X DELETE repos/$REPO/issues/$FOUND_PARENT/sub_issue -F sub_issue_id=$SELF_ID"
  fi

  # Each remedy below is one REST delete per link, naming the numeric id the
  # endpoint takes. A blocks link is the blocked issue's blocked-by link, so
  # it is cleared against that issue, by #$ADOPT's own id.
  UNASKED_BLOCKED=""
  CLEAR_BLOCKED=""
  for pair in $FOUND_BLOCKED_PAIRS; do
    n="${pair%%:*}"
    in_set "$n" "$ASKED_BLOCKED" && continue
    UNASKED_BLOCKED="$UNASKED_BLOCKED $n"
    dep_id="${pair#*:}"
    dep_id="${dep_id%%:*}"
    CLEAR_BLOCKED="$CLEAR_BLOCKED
         gh api -X DELETE repos/$REPO/issues/$ADOPT/dependencies/blocked_by/$dep_id"
  done
  UNASKED_BLOCKED="${UNASKED_BLOCKED# }"
  if [ -n "$UNASKED_BLOCKED" ]; then
    die "ERROR: --adopt $ADOPT — blocked-by links already there were not named by
       this invocation. $NOTHING
       found:     #$ADOPT is already blocked by [$FOUND_BLOCKED]
       asked for: [${ASKED_BLOCKED:-none}]
       not named: [$UNASKED_BLOCKED]

       This refuses rather than reconciling. Clear them, then re-run:
$CLEAR_BLOCKED"
  fi

  UNASKED_BLOCKING=""
  CLEAR_BLOCKING=""
  for pair in $FOUND_BLOCKING_PAIRS; do
    n="${pair%%:*}"
    in_set "$n" "$ASKED_BLOCKING" && continue
    UNASKED_BLOCKING="$UNASKED_BLOCKING $n"
    CLEAR_BLOCKING="$CLEAR_BLOCKING
         gh api -X DELETE repos/${pair##*:}/issues/$n/dependencies/blocked_by/$SELF_ID"
  done
  UNASKED_BLOCKING="${UNASKED_BLOCKING# }"
  if [ -n "$UNASKED_BLOCKING" ]; then
    die "ERROR: --adopt $ADOPT — blocks links already there were not named by this
       invocation. $NOTHING
       found:     #$ADOPT already blocks [$FOUND_BLOCKING]
       asked for: [${ASKED_BLOCKING:-none}]
       not named: [$UNASKED_BLOCKING]

       This refuses rather than reconciling. Clear them, then re-run:
$CLEAR_BLOCKING"
  fi
fi

# ---------------------------------------------------------------------------
# The neighbour check. Read-only; still creates and changes nothing.
# ---------------------------------------------------------------------------

read_board() {
  # Ordered "<number>\t<title>\t<item node id>\t<item numeric id>" lines. The
  # position write takes the node id; the single-item read the read-back
  # corroborates with takes the numeric one. A truncated board is fatal,
  # because a truncated board is exactly what hid #164. Only issues are rows:
  # the GraphQL listing this replaced read pull requests and drafts as
  # numberless, and the REST one gives a pull request a number.
  local out="$1"
  if ! bash "$SCRIPT_DIR/board.sh" --config "$CONFIG" "$out" 2>"$BOARD_ERR"; then
    printf 'ERROR: the board listing is not trustworthy — %s\n' "$(tr '\n' ' ' <"$BOARD_ERR")" >&2
    printf 'A truncated board reads exactly like a short one. Refusing to go on.\n' >&2
    return 1
  fi
  jq -s -r '[.[][]]
            | .[] | select(.content_type == "Issue" and .content.number != null)
            | "\(.content.number)\t\(.content.title)\t\(.node_id)\t\(.id)"' "$out"
}

BOARD_ROWS="$(read_board "$BOARD_JSON")" || exit 1
BOARD_NUMS="$(printf '%s\n' "$BOARD_ROWS" | cut -f1)"

if [ "$TOP" -eq 0 ]; then
  if ! printf '%s\n' "$BOARD_NUMS" | grep -qxF -- "$AFTER"; then
    die "ERROR: --after $AFTER — issue #$AFTER is not on the board, so there is no
       position after it. $NOTHING"
  fi
fi

echo "BOARD NEIGHBOURHOOD — where this issue would land"
echo "------------------------------------------------------------------------"
if [ "$TOP" -eq 1 ]; then
  echo "  >>> NEW ISSUE HERE (top of board) <<<"
  printf '%s\n' "$BOARD_ROWS" | head -n "$NEIGHBOURS" | awk -F'\t' '{printf "      #%-6s %s\n", $1, substr($2,1,70)}'
else
  IDX="$(printf '%s\n' "$BOARD_NUMS" | grep -nxF -- "$AFTER" | head -1 | cut -d: -f1)"
  START=$(( IDX - NEIGHBOURS )); [ "$START" -lt 1 ] && START=1
  printf '%s\n' "$BOARD_ROWS" | sed -n "${START},${IDX}p" | awk -F'\t' '{printf "      #%-6s %s\n", $1, substr($2,1,70)}'
  echo "  >>> NEW ISSUE HERE <<<"
  printf '%s\n' "$BOARD_ROWS" | sed -n "$(( IDX + 1 )),$(( IDX + NEIGHBOURS ))p" | awk -F'\t' '{printf "      #%-6s %s\n", $1, substr($2,1,70)}'
fi
echo

if [ "$MODE" = create ]; then
  # The duplicate-title check answers a question that only arises for an issue
  # that does not exist yet, so adopt mode skips it.
  TITLES_JSON="$(mktemp -t file_issue_titles.XXXXXX)"
  TITLES_LIMIT=500
  # REST's open-issue listing, a page of 100 at a time, up to TITLES_LIMIT raw
  # entries. The listing carries pull requests too, and a pull request is not
  # an issue a new one could duplicate, so they are dropped below -- but only
  # after counting, because they fill the same pages and a listing that hit
  # the limit on them still left issues unread.
  titles_raw=0
  titles_page=1
  titles_pages=""
  while [ "$titles_raw" -lt "$TITLES_LIMIT" ]; do
    page_json="$(gh_api "repos/$REPO/issues?state=open&per_page=100&page=$titles_page")" \
      || die "ERROR: could not list open issues to check for duplicates ($(gh_api_err)). Nothing was created."
    # Fail closed on the shape: a reply that is not an array of issues would
    # otherwise count as an empty page and end the listing as "no duplicates".
    page_len="$(printf '%s' "$page_json" | jq -r 'if type == "array" then length else empty end' 2>/dev/null)"
    [ -n "$page_len" ] || die "ERROR: the duplicate check failed, so this cannot say there are no duplicates.
       The open-issue listing came back in an unrecognised shape. $NOTHING"
    titles_pages="$titles_pages$page_json"
    titles_raw=$(( titles_raw + page_len ))
    [ "$page_len" -lt 100 ] && break
    titles_page=$(( titles_page + 1 ))
  done
  printf '%s' "$titles_pages" \
    | jq -s '[.[][] | select(has("pull_request") | not) | {number, title}]' >"$TITLES_JSON"
  # A full listing means there may be more open issues than were read, and a
  # match among those is missed. Say so; checking past the limit is #19.
  if [ "$titles_raw" -ge "$TITLES_LIMIT" ]; then
    echo "WARNING: the duplicate check read only the first $TITLES_LIMIT open issues."
    echo "         The repo may have more, and a duplicate among them would be missed."
    echo
  fi
  # Fail closed. DUPES is the only thing standing between a create run and
  # its write, so a checker that crashed must not read as "none found".
  DUPES="$(python3 "$SCRIPT_DIR/issue_text.py" dupes "$TITLE" "$TITLES_JSON")" \
    || die "ERROR: the duplicate check failed, so this cannot say there are no duplicates. $NOTHING"
  if [ -n "$DUPES" ]; then
    echo "########################################################################"
    echo "## POSSIBLE DUPLICATES — read these before anything is filed          #"
    echo "########################################################################"
    printf '%s\n' "$DUPES" | awk -F'\t' '{printf "   %-7s %s\n        %s\n", $1, $2, $3}'
    echo "########################################################################"
    echo
  else
    echo "POSSIBLE DUPLICATES: none found."
    echo
  fi
fi

if [ "$MODE" = adopt ]; then
  ADOPT_TITLE="$(printf '%s\n' "$BOARD_ROWS" | awk -F'\t' -v n="$ADOPT" '$1 == n {print $2; exit}')"
  echo "ABOUT TO WIRE AN EXISTING ISSUE"
  echo "  issue      #$ADOPT ${ADOPT_TITLE:-(not currently on the board)}"
else
  echo "ABOUT TO CREATE"
  echo "  title      $TITLE"
  echo "  shape      $SHAPE"
fi
echo "  parent     ${PARENT:-none}"

# WHERE IT IS GOING, AND — IN ADOPT MODE — WHERE IT IS TODAY.
#
# Adopt refuses rather than reconciles for parent, blocked-by and blocks. It
# does NOT for board position: all four placement answers are mandatory, so a
# position is always named, and refusing every adopt of a boarded issue would
# make the tool unusable for re-prioritising. So it MOVES the issue — and it
# used to do so with the confirmation screen showing only the destination. The
# operator confirmed a move whose cost, a priority slot that was a real prior
# decision, was invisible before and left no trace afterwards to reconstruct.
# The fix is disclosure: name the current slot beside the requested one, and
# say plainly when confirming will move it.
POSITION_LINE="$( [ "$TOP" -eq 1 ] && echo "top of board" || echo "after #$AFTER" )"
if [ "$MODE" = adopt ]; then
  ADOPT_IDX="$(printf '%s\n' "$BOARD_NUMS" | grep -nxF -- "$ADOPT" | head -1 | cut -d: -f1)"
  if [ -z "$ADOPT_IDX" ]; then
    POSITION_LINE="$POSITION_LINE  (not currently on the board)"
  else
    ADOPT_PREV="$(printf '%s\n' "$BOARD_NUMS" | sed -n "$(( ADOPT_IDX - 1 ))p")"
    ADOPT_WHERE="currently at position $ADOPT_IDX$( [ -n "$ADOPT_PREV" ] && printf ', following #%s' "$ADOPT_PREV" || printf ', at the top' )"
    if { [ "$TOP" -eq 1 ] && [ "$ADOPT_IDX" = "1" ]; } \
       || { [ "$TOP" -eq 0 ] && [ "$ADOPT_PREV" = "$AFTER" ]; }; then
      POSITION_LINE="$POSITION_LINE  ($ADOPT_WHERE — already there, this does NOT move it)"
      ADOPT_MOVED=0
    else
      POSITION_LINE="$POSITION_LINE  ($ADOPT_WHERE — this MOVES it)"
      # Disclosure before was only half the fix: once confirmed, the previous
      # position was still unrecoverable. Latch it here, in the SAME branch
      # that prints "this MOVES it", so the record written after the read-back
      # is the very judgement the operator saw — not a second opinion formed
      # from a second board read.
      ADOPT_MOVED=1
      ADOPT_FROM_IDX="$ADOPT_IDX"
      ADOPT_FROM_PREV="$ADOPT_PREV"
    fi
  fi
fi
echo "  position   $POSITION_LINE"
echo "  blocked by $( [ -n "$BLOCKED_LIST" ] && printf '%s' "$(printf '%s' "$BLOCKED_LIST" | tr '\n' ' ')" || echo none )"
echo "  blocks     $( [ -n "$BLOCKS_LIST" ] && printf '%s' "$(printf '%s' "$BLOCKS_LIST" | tr '\n' ' ')" || echo none )"
echo

if [ "$DRY_RUN" -eq 1 ]; then
  echo "--dry-run: stopping here. $NOTHING"
  exit 0
fi

# There is no confirmation prompt. Under an agent, stdin is never a terminal,
# so the prompt only ever read a `y` piped in ahead of time. What it guarded
# that the engine cannot judge is whether this is a duplicate, so that is
# where a run stops: possible duplicates and no --file-anyway means nothing is
# written, with an exit code of its own so the caller can tell "go judge
# these" from a refusal. Everything else -- the placement refusals, the
# truncated board, adopt's refusals, the read-back, the move record -- never
# depended on the prompt and still runs.
if [ "$MODE" = create ] && [ -n "$DUPES" ] && [ "$FILE_ANYWAY" -eq 0 ]; then
  printf '%s\n' "STOPPED: possible duplicates listed above. $NOTHING
       If none of them is the same work, re-run the same command with
       --file-anyway." >&2
  exit 3
fi

# ---------------------------------------------------------------------------
# Apply. This is the ONE place the two modes legitimately differ: create
# writes the issue and then every relationship asked for; adopt writes only
# the ones that are not already there. Both write through write_links, one
# REST call per link, and both leave the verdict to the shared read-back.
# ---------------------------------------------------------------------------

half_wired_head() {
  # The part every failure shares. Never leave the operator guessing what
  # exists on the server. The mismatch sentence and the requested-state
  # summary are IDENTICAL in both modes; only the provenance and the next
  # action differ, because only they depend on whether this run created the
  # issue.
  printf '\n' >&2
  printf 'MISMATCH: %s\n' "$1" >&2
  printf '\n' >&2
  printf 'Issue #%s EXISTS at %s.\n' "$NUM" "$URL" >&2
  printf '%s\n' "$HALF_WIRED_PROVENANCE" >&2
  printf 'Requested: parent=%s, position=%s, blocked-by=[%s], blocks=[%s].\n' \
    "${PARENT:-none}" \
    "$( [ "$TOP" -eq 1 ] && echo top || echo "after #$AFTER" )" \
    "$(printf '%s' "$BLOCKED_LIST" | tr '\n' ' ')" \
    "$(printf '%s' "$BLOCKS_LIST" | tr '\n' ' ')" >&2
}

reverify_command() {
  # The one command that re-runs every check on an issue that already exists,
  # and is SAFE on a correctly wired one: adopt mode writes only relationships
  # that are not already there, and reads all of them back. This is what makes
  # a "could not look" refusal clearable instead of a dead end. It runs over
  # REST, so it works where GraphQL is refused.
  #
  # The script and --config paths are the ones THIS run was given, so the
  # command runs from wherever this one was run. It used to print
  # `scripts/file_issue.sh` with no --config, which is neither this repo's
  # layout nor a runnable command since --config became required.
  printf '  bash %q --config %q --adopt %s %s %s --blocked-by %s --blocks %s\n' \
    "${BASH_SOURCE[0]}" "$CONFIG" \
    "$NUM" \
    "$( [ -n "$PARENT" ] && printf -- '--parent %s' "$PARENT" || printf -- '--no-parent' )" \
    "$( [ "$TOP" -eq 1 ] && printf -- '--top' || printf -- '--after %s' "$AFTER" )" \
    "$( [ -n "$BLOCKED_LIST" ] && csv_of "$BLOCKED_LIST" || printf 'none' )" \
    "$( [ -n "$BLOCKS_LIST" ] && csv_of "$BLOCKS_LIST" || printf 'none' )"
}

half_wired() {
  # DID NOT LAND — the server itself reported a state contradicting the answer
  # given. The wiring is proven wrong, so this is the only cause whose next
  # action may include re-filing.
  half_wired_head "$1"
  printf '%s\n' "$HALF_WIRED_NEXT" >&2
  exit 1
}

half_wired_absent() {
  # DID NOT LAND, as far as a bounded wait could establish: the board listing
  # never showed the issue and the corroborating single-item read never showed
  # it either. Both queries hit the same Projects store and share its
  # replication lag, so their agreement is a weak signal — the refusal rests on
  # the EXHAUSTED BOUND, not on that agreement. Nothing here proved the wiring
  # wrong, so nothing here may tell the operator to re-file.
  half_wired_head "$1"
  printf 'Read %s times over %ss; the board never showed it and a direct read of the\n' \
    "$READBACK_ATTEMPTS" "$READBACK_WAITED" >&2
  printf "issue's board item did not show it either.\n" >&2
  if [ "$POSITION_DEGRADED" -eq 1 ]; then
    printf 'The item-add returned WITHOUT error before this read (GitHub refused the\n' >&2
    printf 'position write, which moves nothing), so this is as likely a listing that\n' >&2
    printf 'has not caught up as a write that never landed. Check the board yourself,\n' >&2
    printf 'and re-run the check once it settles:\n' >&2
  else
    printf 'The item-add and the position write both returned WITHOUT error before this\n' >&2
    printf 'read, so this is as likely a listing that has not caught up as a write that\n' >&2
    printf 'never landed. Check the board yourself, and re-run the check once it settles:\n' >&2
  fi
  reverify_command >&2
  exit 1
}

half_wired_unverified() {
  # POSITION UNVERIFIED. Membership IS proven — a direct read of the issue's
  # board item returned it. Position is an index into the
  # board listing, and the listing never caught up, so there was nothing to
  # compare it against. This is not a failed write and must never read as one.
  half_wired_head "$1"
  printf 'Membership is PROVEN: a direct read of the board item of #%s returned it on\n' "$NUM" >&2
  printf 'project %s. Only the POSITION is unverified — the board listing was\n' "$PROJECT_NUMBER" >&2
  printf 'still behind after %s reads over %ss. Nothing here proved the position wrong,\n' \
    "$READBACK_ATTEMPTS" "$READBACK_WAITED" >&2
  printf 'and nothing here proved the write failed. Re-run the check once the listing\n' >&2
  printf 'catches up:\n' >&2
  reverify_command >&2
  exit 1
}

half_wired_unreadable() {
  # COULD NOT LOOK. The READ failed, not the write. Unable to look is not
  # evidence of absence, so this says so and hands over the command that
  # settles it once the read works again.
  half_wired_head "$1"
  printf 'The READ failed, not the write. Nothing here says the write did not land, and\n' >&2
  printf 'no relationship was proven wrong. Re-run the check once the board reads again:\n' >&2
  reverify_command >&2
  exit 1
}

resolve_or_refuse() {
  # $1 the flag that named the issue, $2 its number. Sets RESOLVED_ID to the
  # issue's numeric id, or refuses: every link write needs an id, and a number
  # that does not resolve is refused BEFORE anything is written. The single
  # `gh issue create` this replaced failed atomically on a missing number;
  # REST create is several calls, and a typo found after the first would
  # leave a real issue half-wired. Called in the CURRENT SHELL, so its die
  # reaches the shell running the script.
  local id rc
  id="$(issue_numeric_id "$2")"
  rc=$?
  case "$rc" in
    0) RESOLVED_ID="$id" ;;
    2) die "ERROR: $1 $2 — issue #$2 does not exist in $REPO. $NOTHING" ;;
    *) die "ERROR: $1 $2 — issue #$2 could not be read from $REPO, so its id is unknown.
       $(gh_api_err)
       $NOTHING" ;;
  esac
}

LINK_WRITE_FAILED=0
post_link() {
  # $1 what the link is, for the warning; the rest are `gh api` arguments.
  # A failed write is a WARNING, not fatal, and NOT evidence that nothing
  # landed: a call can fail after the server applied it, so the read-back is
  # what establishes the true state.
  local what="$1"
  shift
  if ! gh_api -X POST "$@" >/dev/null; then
    LINK_WRITE_FAILED=1
    echo "WARNING: writing $what for #$NUM exited non-zero: $(gh_api_err)" >&2
  fi
}

write_links() {
  # $1 the parent to put #$NUM under, or empty. $2 its blockers, as
  # "number:id" pairs. $3 the issues it blocks, as numbers. Each link is its
  # own REST call. A blocks link is the OTHER issue's blocked-by link, so it
  # is written against that issue, carrying #$NUM's own id. An empty answer
  # writes nothing -- never an empty link.
  local pair n
  [ -n "$1" ] && post_link "parent #$1" "repos/$REPO/issues/$1/sub_issues" -F sub_issue_id="$SELF_ID"
  for pair in $2; do
    post_link "blocked-by #${pair%%:*}" "repos/$REPO/issues/$NUM/dependencies/blocked_by" -F issue_id="${pair#*:}"
  done
  for n in $3; do
    post_link "blocks #$n" "repos/$REPO/issues/$n/dependencies/blocked_by" -F issue_id="$SELF_ID"
  done
  if [ "$LINK_WRITE_FAILED" -eq 1 ]; then
    echo "         Links whose write failed MAY still have been written." >&2
    echo "         The read-back below reports each one separately." >&2
  fi
}

RESOLVED_ID=""
if [ "$MODE" = create ]; then
  # Resolve every referenced issue first (#14 KTD3). The parent and each
  # blocked issue are read only to prove they exist; each blocker's id is
  # what its link write takes.
  [ -n "$PARENT" ] && resolve_or_refuse --parent "$PARENT"
  CREATE_BLOCKER_PAIRS=""
  for n in $BLOCKED_LIST; do
    resolve_or_refuse --blocked-by "$n"
    CREATE_BLOCKER_PAIRS="$CREATE_BLOCKER_PAIRS $n:$RESOLVED_ID"
  done
  for n in $BLOCKS_LIST; do
    resolve_or_refuse --blocks "$n"
  done

  # The issue first, then each link, then the read-back judges (#14 KTD4).
  # The window in which the issue exists partly linked is accepted: a failed
  # link write warns and carries on, and the refusal the read-back picks names
  # the adopt command that writes only what is missing.
  CREATE_REPLY="$(gh_api -X POST "repos/$REPO/issues" -f title="$TITLE" -F body=@"$BODY_FILE" "${LABEL_FIELDS[@]}")" \
    || die "ERROR: the issue create failed: $(gh_api_err)
       Nothing to read back."
  NUM="$(printf '%s' "$CREATE_REPLY" | jq -r '.number // ""' 2>/dev/null)"
  URL="$(printf '%s' "$CREATE_REPLY" | jq -r '.html_url // ""' 2>/dev/null)"
  SELF_ID="$(printf '%s' "$CREATE_REPLY" | jq -r '.id // ""' 2>/dev/null)"
  case "$NUM" in ''|*[!0-9]*) die "ERROR: could not read an issue number out of the create reply: $CREATE_REPLY" ;; esac
  case "$SELF_ID" in ''|*[!0-9]*) die "ERROR: could not read the id of #$NUM out of the create reply: $CREATE_REPLY" ;; esac
  [ -n "$URL" ] || die "ERROR: could not read the URL of #$NUM out of the create reply: $CREATE_REPLY"
  HALF_WIRED_PROVENANCE="It is left HALF-WIRED — the create succeeded and this relationship did not."
  # Leads with the adopt command: it writes only the links that are missing,
  # reads every one back, and runs over REST. Deleting an issue needs GraphQL,
  # so delete-and-re-run is offered only as a local-session alternative.
  HALF_WIRED_NEXT="Finish it with this command. It writes only the links that are missing, reads every one back, and needs no GraphQL:
$(reverify_command)
In a local session you may instead delete #$NUM and re-run. Do not assume it is fine."
  echo "created #$NUM  $URL"
  write_links "$PARENT" "$CREATE_BLOCKER_PAIRS" "$BLOCKS_LIST"
else
  NUM="$ADOPT"
  URL="https://github.com/$REPO/issues/$NUM"
  HALF_WIRED_PROVENANCE="It is left PARTLY WIRED — relationships this run wrote may have landed, and this one did not agree."
  HALF_WIRED_NEXT="Finish it by hand, then re-run this command. Do not delete #$NUM — nothing here proved its wiring wrong."

  # A DELTA, not a set. `gh issue edit` is NOT idempotent on either kind of
  # relationship — measured against the live board on 2026-08-24 with gh
  # 2.98.0, recorded on #233. Re-adding a link that is already there fails the
  # WHOLE call:
  #   gh issue edit 234 --add-blocked-by 233 -> Validation failed: Target issue
  #        has already been taken (addBlockedBy), exit 1
  #   gh issue edit 234 --parent 240         -> Issue may not contain duplicate
  #        sub-issues (addSubIssue), exit 1
  # The pre-existing link survived both, so it is a refusal, not corruption.
  # The REST writes that replaced it (#14) carry one link each, so a repeat
  # can cost only its own call -- but REST is assumed to refuse a repeat the
  # same way, not measured, so the delta stands. A link is written ONLY when
  # it is NOT already there. A contradicting one has already been refused
  # above; an already matching one is skipped. If the delta is empty nothing
  # is written at all — and the read-back still runs, because it is the only
  # proof anything holds.
  ADD_PARENT=""
  [ -n "$PARENT" ] && [ "$PARENT" != "$FOUND_PARENT" ] && ADD_PARENT="$PARENT"

  # Each missing blocker's id is resolved before any write, as create does.
  ADD_BLOCKED_PAIRS=""
  for n in $ASKED_BLOCKED; do
    in_set "$n" "$FOUND_BLOCKED" && continue
    resolve_or_refuse --blocked-by "$n"
    ADD_BLOCKED_PAIRS="$ADD_BLOCKED_PAIRS $n:$RESOLVED_ID"
  done

  ADD_BLOCKING=""
  for n in $ASKED_BLOCKING; do
    in_set "$n" "$FOUND_BLOCKING" || ADD_BLOCKING="$ADD_BLOCKING $n"
  done

  if [ -z "$ADD_PARENT$ADD_BLOCKED_PAIRS$ADD_BLOCKING" ]; then
    echo "relationships     every one asked for is already there; no write issued"
    echo "                  (the read-back below is the only proof of that)"
  else
    write_links "$ADD_PARENT" "$ADD_BLOCKED_PAIRS" "$ADD_BLOCKING"
  fi
  echo "wiring #$NUM  $URL"
fi

# ---------------------------------------------------------------------------
# SHARED BOARD HALF. Both modes call these, in the current shell.
# ---------------------------------------------------------------------------

ITEM_ID=""             # the item's node id, which the position write takes
ITEM_REST_ID=""        # its numeric REST id, which the single-item read takes
POSITION_DEGRADED=0    # 1 once GitHub has refused the position write (#14 KTD2)

board_row_item() {
  # $1 board rows as read_board prints them, $2 an issue number. Prints that
  # issue's "<node id>\t<numeric id>", or nothing when it is not a row.
  printf '%s\n' "$1" | awk -F'\t' -v n="$2" '$1 == n {print $3 "\t" $4; exit}'
}

take_item() {
  # $1 "<node id>\t<numeric id>". Sets ITEM_ID and ITEM_REST_ID when both are
  # really there; leaves them empty otherwise, so the caller's fallback runs.
  local node="${1%%	*}" id="${1#*	}"
  case "$node" in ''|null) return 1 ;; esac
  case "$id" in ''|*[!0-9]*) return 1 ;; esac
  ITEM_ID="$node"
  ITEM_REST_ID="$id"
}

board_membership_corroboration() {
  # The SECOND query path over the same Projects store, issued on EVERY
  # read-back attempt on which the board listing does not show the issue:
  # the single item, read by the numeric id item-add or the listing gave it
  # (#14 KTD5).
  #
  # A POSITIVE result is conclusive: the listing was stale and membership is
  # proven. Agreement on ABSENCE is a weaker signal — both queries hit the
  # same store and share its replication lag — and is never what a refusal
  # rests on; the refusal rests on the exhausted bound. So anything short of
  # a reply naming #$1 as the item's content -- an error, a 404, a reply of
  # another shape -- is "not shown", never a pass.
  local reply
  [ -n "$ITEM_REST_ID" ] || return 1
  reply="$(gh_api "$PROJECT_PATH/items/$ITEM_REST_ID")" || return 1
  [ "$(printf '%s' "$reply" | jq -r --argjson n "$1" '.content.number == $n' 2>/dev/null)" = "true" ]
}

write_position() {
  # The ONE GraphQL call left (#14 KTD2): no REST route sets a board position.
  # $1 the node id of the item to follow, or empty for the top.
  #
  # Classified by its error. Exit non-zero with gh's `(HTTP 403)` means GitHub
  # REFUSED it -- a session without GraphQL access -- so the position is
  # recorded as degraded and the run carries on: the item is on the board,
  # wherever it landed, and the read-back still proves that. Any other failure
  # is the half-wired refusal it has always been.
  if [ -z "$1" ]; then
    gh_api graphql -f query='mutation($p:ID!,$i:ID!){updateProjectV2ItemPosition(input:{projectId:$p,itemId:$i}){clientMutationId}}' \
      -f p="$PROJECT_ID" -f i="$ITEM_ID" >/dev/null && return 0
  else
    gh_api graphql -f query='mutation($p:ID!,$i:ID!,$a:ID!){updateProjectV2ItemPosition(input:{projectId:$p,itemId:$i,afterId:$a}){clientMutationId}}' \
      -f p="$PROJECT_ID" -f i="$ITEM_ID" -f a="$1" >/dev/null && return 0
  fi
  if gh_api_failed_with 403; then
    POSITION_DEGRADED=1
    return 0
  fi
  half_wired "the board position write failed for #$NUM: $(gh_api_err)"
}

board_half() {
  # Puts the issue on project 2 if it is not there and writes its position.
  #
  # Takes NO arguments, and reads the globals $NUM and $URL. It used to take
  # them as $1 and $2 while its failure path fell through to half_wired_head,
  # which prints the GLOBALS — so it looked parameterised and was not. With one
  # call site the two could never disagree, which is exactly what makes that
  # shape a trap: the day a second call site passes a different number, every
  # refusal names the wrong issue and nothing complains. Reading the globals in
  # one place is the honest version.
  #
  # Calls half_wired directly, so it MUST be invoked in the current shell.
  local add_err="" after_item rows
  # An adopted issue already on the board takes its item from the pre-write
  # listing, so it does not depend on item-add's output: item-add refuses an
  # issue already there, and that would abort a correctly wired filing.
  if [ "$MODE" = adopt ]; then
    take_item "$(board_row_item "$BOARD_ROWS" "$NUM")"
  fi
  if [ -z "$ITEM_ID" ]; then
    take_item "$(gh_api -X POST "$PROJECT_PATH/items" -f type=Issue -F id="$SELF_ID" \
      | jq -r '"\(.node_id)\t\(.id)"' 2>/dev/null)" \
      || add_err="$(gh_api_err)"
  fi
  # A board with GitHub's auto-add workflow puts a NEW issue on it before
  # item-add runs, and item-add then refuses it as already there and returns
  # no item. The issue IS on the board, so look for it in a fresh listing
  # before calling this a failure (pluckd #504, #508) -- fresh, because the
  # pre-write listing predates a just-created issue. A listing that cannot
  # be read is a could-not-look, never a did-not-land.
  if [ -z "$ITEM_ID" ]; then
    rows="$(read_board "${BOARD_JSON}.2")" \
      || half_wired_unreadable "the board (project $PROJECT_NUMBER) could not be re-read to find the item for #$NUM"
    take_item "$(board_row_item "$rows" "$NUM")"
  fi
  [ -n "$ITEM_ID" ] || half_wired "the board (project $PROJECT_NUMBER) did not return an item id for #$NUM${add_err:+ ($add_err)}"

  if [ "$TOP" -eq 1 ]; then
    write_position ""
  else
    # From the PRE-WRITE listing, which the gate above already proved holds
    # #$AFTER -- so the item cannot be ABSENT here. A row with no node id is a
    # listing this cannot read, and a read that failed proves nothing about
    # #$AFTER, so it must never reach half_wired(), whose next action
    # includes deleting the issue.
    after_item="$(board_row_item "$BOARD_ROWS" "$AFTER" | cut -f1)"
    case "$after_item" in
      ''|null) half_wired_unreadable "the board item for #$AFTER could not be read, so #$NUM could not be positioned" ;;
    esac
    write_position "$after_item"
  fi
}

# In the CURRENT SHELL. Assigned from a command substitution instead, the exit
# inside half_wired would kill only the subshell, the assignment would succeed,
# and the run would report success — a vacuous pass in the very guard this
# script is.
board_half

# >>> SHARED READ-BACK START
# Read back. An exit code is not evidence. Both modes call this ONE
# implementation; no relationship comparison exists anywhere else in this file,
# and tests/test_engine_gating.py scans for a second copy.
DEPENDENCY_NUMBERS=""
read_dependency_numbers() {
  # $1 the dependency list (blocked_by or blocking), $2 its name in a refusal.
  # Sets DEPENDENCY_NUMBERS to the linked issue numbers in comparison form,
  # or refuses as COULD NOT LOOK. Sets a global rather than printing so its
  # refusal exits the shell running the script: call it in the CURRENT SHELL.
  local reply rc entries
  reply="$(gh_api "repos/$REPO/issues/$NUM/dependencies/$1?per_page=100")"
  rc=$?
  entries="$(dependency_entries "$reply")"
  [ "$rc" -eq 0 ] \
    || half_wired_unreadable "the $2 links of #$NUM could not be read back — gh exited $rc: $(gh_api_err)"
  [ "$entries" != "BAD" ] \
    || half_wired_unreadable "the $2 links of #$NUM came back in an unrecognised shape — the reply is not a list of issues"
  DEPENDENCY_NUMBERS="$(norm "$(entry_numbers "$entries")")"
}

read_back() {
  # Compares every relationship against the four answers.
  #
  # Takes NO arguments, and reads the globals $NUM and $URL, for the same
  # reason board_half does: its failure path falls through to half_wired_head,
  # which prints the globals. A parameter that the failure path ignores is a
  # parameter that lies.
  #
  # Calls half_wired directly, so it MUST be invoked in the current shell.
  echo
  echo "READ-BACK"

  # THREE STATES, not two. A board write is not read-your-writes consistent,
  # so "the listing does not show it" means one of: not yet visible, did not
  # land, or the read did not answer. They call for different operator
  # actions, so they are resolved separately and refused separately.
  #
  # The retry is on the READ only (KD1). No mutation is re-issued, and the
  # bound is finite: this still fails when the write genuinely did not land.
  local attempt=1 delay="$READBACK_DELAY"
  local in_listing=0 member_proven=0 position_ok=0 position_msg=""
  # PROOF IS LATCHED, because it does not expire. The refusal used to be chosen
  # from the LAST attempt's in_listing alone: an early attempt that SAW the
  # issue and found its position wrong, followed by a listing that went silent,
  # left in_listing at 0 and member_proven at 1, threw position_msg away, and
  # told the operator "the board listing never showed it" and "Nothing here
  # proved the position wrong" — both false, and a did-not-land routed into the
  # probably-fine bucket. Once the server has shown a wrong position, that is
  # settled; no later silence unsettles it.
  local position_proven_wrong=0
  READBACK_WAITED=0

  while : ; do
    # A failed page, a page cap or a rows-vs-distinct truncation is FATAL in
    # board.sh and stays fatal here. Unable to look is not permission, and it
    # is never a reason to keep waiting.
    BOARD2_ROWS="$(read_board "${BOARD_JSON}.2")" \
      || half_wired_unreadable "the board (project $PROJECT_NUMBER) could not be re-read to verify #$NUM"
    BOARD2_NUMS="$(printf '%s\n' "$BOARD2_ROWS" | cut -f1)"

    if printf '%s\n' "$BOARD2_NUMS" | grep -qxF -- "$NUM"; then
      in_listing=1
      member_proven=1
      # A DEGRADED position was never written, so there is no position to
      # compare (#14 KTD8): membership is the whole board check, and it is
      # proven.
      [ "$POSITION_DEGRADED" -eq 1 ] && break
      IDX2="$(printf '%s\n' "$BOARD2_NUMS" | grep -nxF -- "$NUM" | head -1 | cut -d: -f1)"
      if [ "$TOP" -eq 1 ]; then
        if [ "$IDX2" = "1" ]; then
          position_ok=1
        else
          position_ok=0
          position_proven_wrong=1
          position_msg="board position — asked for the top of the board; #$NUM sits at position $IDX2, behind #$(printf '%s\n' "$BOARD2_NUMS" | sed -n "$(( IDX2 - 1 ))p")"
        fi
      else
        PREV="$(printf '%s\n' "$BOARD2_NUMS" | sed -n "$(( IDX2 - 1 ))p")"
        if [ "$PREV" = "$AFTER" ]; then
          position_ok=1
        else
          position_ok=0
          position_proven_wrong=1
          position_msg="board position — asked for #$NUM to follow #$AFTER; it follows #${PREV:-nothing} instead"
        fi
      fi
      [ "$position_ok" -eq 1 ] && break
    else
      in_listing=0
      # Every attempt on which the listing is silent, ask the store directly.
      # A positive answer proves MEMBERSHIP; it does not finish the check,
      # because position is an index into the listing and until the listing
      # shows the issue there is nothing to compare. A degraded position has
      # nothing to compare either way, so there it does finish the check.
      if board_membership_corroboration "$NUM"; then
        member_proven=1
        [ "$POSITION_DEGRADED" -eq 1 ] && break
      fi
    fi

    [ "$attempt" -ge "$READBACK_ATTEMPTS" ] && break
    if [ "$delay" -gt 0 ]; then
      sleep "$delay"
      READBACK_WAITED=$(( READBACK_WAITED + delay ))
    fi
    attempt=$(( attempt + 1 ))
    delay=$(( delay * 2 ))
  done

  if [ "$POSITION_DEGRADED" -eq 1 ]; then
    # No position was written, so none was compared and the latch below can
    # never have been set. Membership is the whole board verdict, proven by
    # the listing or the corroborating read within the same bound -- and an
    # issue neither ever showed is refused exactly as it is when the position
    # write succeeded.
    [ "$member_proven" -eq 1 ] \
      || half_wired_absent "#$NUM is not on the board (project $PROJECT_NUMBER) after being added to it"
  else
    # The latch is read FIRST, ahead of the in_listing dispatch, and it is read
    # only when NO attempt ever saw the position right. Convergence still wins:
    # a listing that showed a wrong position and then showed the right one has
    # caught up, which is the whole point of KD1's retry, and that path breaks
    # out of the loop with position_ok=1 before ever reaching here. What must not
    # survive is the other order — proven wrong, then silence — which used to
    # discard the proof and report POSITION UNVERIFIED over a position the server
    # itself had already contradicted.
    if [ "$position_ok" -eq 0 ] && [ "$position_proven_wrong" -eq 1 ]; then
      half_wired "$position_msg"
    fi
    if [ "$in_listing" -eq 0 ]; then
      if [ "$member_proven" -eq 1 ]; then
        half_wired_unverified "board position for #$NUM could not be verified — #$NUM is on the board, but the board listing never showed it"
      fi
      half_wired_absent "#$NUM is not on the board (project $PROJECT_NUMBER) after being added to it"
    fi
    [ "$position_ok" -eq 1 ] || half_wired "$position_msg"

    # THE LANDING INDEX, retained at the one point it has been PROVEN — every
    # path above this line either exits through a half_wired_* refusal or has
    # compared the index the server reported against what was asked for. The
    # move record written after this function returns reads this, so it can
    # never name a position that was not verified, and it costs no extra read.
    ADOPT_LANDED_IDX="$IDX2"
  fi

  if [ "$attempt" -gt 1 ]; then
    echo "  board read         ok on attempt $attempt of $READBACK_ATTEMPTS (the board took ${READBACK_WAITED}s to catch up)"
    if [ "$attempt" -ge "$READBACK_ATTEMPTS" ]; then
      echo "WARNING: that was the FINAL attempt — the retry bound is nearly exhausted." >&2
      echo "         The measured numbers have gone stale. Re-measure the board's" >&2
      echo "         convergence when you can. If you need more budget now, raise" >&2
      echo "         FILE_ISSUE_READBACK_DELAY, not _ATTEMPTS — attempts cost the" >&2
      echo "         30-second ceiling faster since the wait doubles each time." >&2
      # The highest DELAY the ceiling still accepts at this ATTEMPTS, computed
      # the same way READBACK_WORST_CASE is above: never name a knob the
      # ceiling check two screens up would refuse. The loop stops doubling
      # once warn_pow2 already clears the ceiling — past that point the
      # quotient below can only be 0, so further doubling changes nothing
      # except risking bash's 64-bit wraparound at absurd ATTEMPTS values.
      warn_pow2=1; warn_i=1
      while [ "$warn_i" -lt "$READBACK_ATTEMPTS" ] && [ "$warn_pow2" -le "$READBACK_CEILING" ]; do
        warn_pow2=$(( warn_pow2 * 2 ))
        warn_i=$(( warn_i + 1 ))
      done
      warn_denom=$(( warn_pow2 - 1 ))
      [ "$warn_denom" -lt 1 ] && warn_denom=1
      warn_suggested=$(( READBACK_CEILING / warn_denom ))
      # Only ever NAME a DELAY that is a real, positive improvement over the
      # one already in effect. Below ATTEMPTS=6 the ceiling has genuine room;
      # at and above it the quotient floors to 0 — printing that as "the
      # ceiling allows up to" would repeat the exact bug this warning was
      # rewritten to stop: naming a knob that helps nothing.
      if [ "$warn_suggested" -gt 0 ] && [ "$warn_suggested" -gt "$READBACK_DELAY" ]; then
        echo "         At ATTEMPTS=$READBACK_ATTEMPTS the ceiling allows up to" >&2
        echo "         FILE_ISSUE_READBACK_DELAY=$warn_suggested." >&2
      else
        echo "         At ATTEMPTS=$READBACK_ATTEMPTS the 30-second ceiling has no" >&2
        echo "         room left for a larger DELAY — raising it further would be" >&2
        echo "         refused or buy nothing. Lower FILE_ISSUE_READBACK_ATTEMPTS" >&2
        echo "         instead; a smaller ATTEMPTS count leaves the ceiling room" >&2
        echo "         for a real DELAY." >&2
      fi
      unset warn_pow2 warn_i warn_denom warn_suggested
    fi
  fi
  echo "  board membership   ok"
  if [ "$POSITION_DEGRADED" -eq 1 ]; then
    echo "  board position     NOT SET (GitHub refused the position write; see the notice below)"
  elif [ "$TOP" -eq 1 ]; then
    echo "  board position     ok (top)"
  else
    echo "  board position     ok (after #$AFTER)"
  fi

  # Three REST reads (#14 KTD6): the issue, for its parent, and its two
  # dependency lists. EACH REPLY'S SHAPE IS CHECKED, because emptiness alone
  # was a vacuous pass. A reply that simply lacks the fields compared —
  # `{"message":"Not Found"}` is the one that reproduced it — extracts as
  # empty, and empty compares EQUAL to the empty answer set. On the commonest
  # filing shape, `--no-parent --blocked-by none --blocks none`, the run
  # printed three `ok (none)` lines and exited 0 having proven NOTHING at all.
  # So the issue reply must carry a number and a state, its parent must parse,
  # and each dependency reply must be an array -- the same checks adopt's
  # pre-fetch makes, through the same parsers.
  #
  # All of them are COULD NOT LOOK, never did not land: a read that failed
  # says nothing about the write, and its refusal must not offer to delete
  # anything.
  REL_JSON="$(gh_api "repos/$REPO/issues/$NUM")"
  REL_RC=$?
  [ "$REL_RC" -eq 0 ] || half_wired_unreadable "the relationships of #$NUM could not be read back — gh exited $REL_RC: $(gh_api_err)"
  [ -n "$REL_JSON" ] || half_wired_unreadable "the relationships of #$NUM could not be read back at all"
  [ "$(printf '%s' "$REL_JSON" | jq -r 'type == "object" and has("number") and has("state")' 2>/dev/null)" = "true" ] \
    || half_wired_unreadable "the relationships of #$NUM came back in an unrecognised shape — the issue reply carries no number/state to read a parent from"

  PARENT_READ="$(issue_reply_parent "$REL_JSON")"
  [ "$PARENT_READ" != "BAD" ] \
    || half_wired_unreadable "the parent of #$NUM could not be read back — the reply's parent_issue_url is not an issue URL"
  if [ -n "$PARENT" ]; then
    [ "$PARENT_READ" = "$PARENT" ] || half_wired "parent — asked for #$NUM to sit under #$PARENT; it reads back as ${PARENT_READ:-no parent}"
    echo "  parent             ok (#$PARENT)"
  else
    [ -z "$PARENT_READ" ] || half_wired "parent — asked for no parent; #$NUM reads back under #$PARENT_READ"
    echo "  parent             ok (none)"
  fi

  read_dependency_numbers blocked_by blocked-by
  BLOCKED_READ="$DEPENDENCY_NUMBERS"
  BLOCKED_WANT="$(norm "$(printf '%s' "$BLOCKED_LIST" | tr '\n' ' ')")"
  [ "$BLOCKED_READ" = "$BLOCKED_WANT" ] \
    || half_wired "blocked-by — asked for [${BLOCKED_WANT:-none}]; #$NUM reads back as [${BLOCKED_READ:-none}]"
  echo "  blocked-by         ok (${BLOCKED_WANT:-none})"

  read_dependency_numbers blocking blocks
  BLOCKING_READ="$DEPENDENCY_NUMBERS"
  BLOCKING_WANT="$(norm "$(printf '%s' "$BLOCKS_LIST" | tr '\n' ' ')")"
  [ "$BLOCKING_READ" = "$BLOCKING_WANT" ] \
    || half_wired "blocks — asked for #$NUM to block [${BLOCKING_WANT:-none}]; it reads back blocking [${BLOCKING_READ:-none}]"
  echo "  blocks             ok (${BLOCKING_WANT:-none})"
}
# <<< SHARED READ-BACK END

# In the CURRENT SHELL, for the same reason board_half is.
read_back

# ---------------------------------------------------------------------------
# RECORD THE MOVE. Only reachable when read_back RETURNED, and read_back never
# returns on a mismatch — every failure path in it ends in a half_wired_* that
# exits. So the position this comment claims has been read back off the server
# and proven. That ordering is the whole guarantee, and it is why this block
# sits after the call rather than inside the read-back loop: a comment naming a
# move that did not land is worse than no comment at all.
#
# The landing ordinal comes from $ADOPT_LANDED_IDX, which read_back sets from
# the very index its own position check compared against, at the point that
# check passed. Nothing here reads the board again.
#
# A DEGRADED position records nothing: the position write was refused, so the
# issue did not move and there is no move to record (#14 KTD8). The adopt run
# that places it later, from a local session, records its own move.
if [ "$ADOPT_MOVED" -eq 1 ] && [ "$POSITION_DEGRADED" -eq 0 ]; then
  # Each side names its ordinal AND what it follows. An ordinal on its own is
  # meaningless once the board shifts under it, and a slot at the head of the
  # board follows nothing — so it reads as the top rather than as "following #"
  # with an empty number after it.
  MOVE_FROM="position $ADOPT_FROM_IDX ($( [ -n "$ADOPT_FROM_PREV" ] \
    && printf 'following #%s' "$ADOPT_FROM_PREV" \
    || printf 'the top of the board' ))"
  MOVE_TO="position $ADOPT_LANDED_IDX ($( [ "$TOP" -eq 1 ] \
    && printf 'the top of the board' \
    || printf 'following #%s' "$AFTER" ))"
  MOVE_SUMMARY="Moved from $MOVE_FROM to $MOVE_TO."
  MOVE_COMMENT="$MOVE_SUMMARY

Recorded automatically by \`scripts/file_issue.sh\` when this issue was wired
onto project $PROJECT_NUMBER, so the slot it came from stays recoverable.
The destination was read back from the board and verified; the origin is the
slot shown in the pre-write summary immediately before the move."

  # BEST EFFORT, AND LOUD WHEN IT FAILS. The wiring has already landed and
  # already been verified by the time this runs. So a failed comment must not
  # call die or any half_wired_* function: those print the delete-and-re-run
  # remedy, which on a correctly wired issue is destructive advice. It must
  # also not be silent, or the promise that a move is always recorded becomes
  # one the tool quietly breaks. So: warn on stderr, carry both positions in
  # text the operator can paste, and still exit 0 — because the wiring did
  # succeed.
  #
  # A comment is the one write in this project that legitimately bypasses
  # this script (docs/WORKFLOW.md § 7 names it, as `gh issue comment`),
  # because a comment creates no issue and touches no board field. This posts
  # the same comment over REST (#14); it relies on that existing carve-out and
  # does not widen it.
  MOVE_RC=0
  gh_api -X POST "repos/$REPO/issues/$NUM/comments" -f body="$MOVE_COMMENT" >/dev/null \
    || MOVE_RC=$?
  MOVE_ERR="$(gh_api_err)"
  if [ "$MOVE_RC" -eq 0 ]; then
    echo "  move recorded      ok ($MOVE_SUMMARY)"
  else
    echo "########################################################################" >&2
    echo "## WARNING: the move LANDED but recording it FAILED                    #" >&2
    echo "########################################################################" >&2
    echo "#$NUM is correctly wired and every relationship read back matching."   >&2
    echo "Nothing is half-wired and there is nothing here to undo."              >&2
    echo "What failed is the comment recording where this issue came from, so"   >&2
    echo "that slot is not written down anywhere yet."                           >&2
    echo "  the comment POST exited $MOVE_RC: ${MOVE_ERR:-(no output)}"          >&2
    echo "POST THIS ON #$NUM BY HAND:"                                           >&2
    printf '%s\n' "$MOVE_COMMENT"                                               >&2
    echo "########################################################################" >&2
  fi
fi

echo
DONE_VERB="$( [ "$MODE" = adopt ] && echo wired || echo created )"
if [ "$POSITION_DEGRADED" -eq 0 ]; then
  echo "#$NUM is $DONE_VERB and every relationship read back matching. $URL"
else
  echo "#$NUM is $DONE_VERB and every relationship read back matching, but its board position is NOT SET. $URL"
  # Loud, and still exit 0: everything this run could write landed and read
  # back. What is left needs GraphQL, so the command below is for a session
  # that has it. It is the adopt re-run, which writes only what is missing --
  # here, the position -- and reads everything back.
  echo "########################################################################" >&2
  echo "## BOARD POSITION NOT SET                                              #" >&2
  echo "########################################################################" >&2
  echo "GitHub refused the GraphQL position write (HTTP 403), so #$NUM is on the" >&2
  echo "board wherever it landed, not $( [ "$TOP" -eq 1 ] && echo "at the top" || echo "after #$AFTER" ). Every other relationship read back" >&2
  echo "matching; nothing is half-wired. Place it from a local session, where" >&2
  echo "GraphQL is reachable, with:" >&2
  reverify_command >&2
  echo "########################################################################" >&2
fi
