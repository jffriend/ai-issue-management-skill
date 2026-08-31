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
# any near-duplicate titles, makes a human say yes, and treats a truncated
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
# USAGE — two modes. Both answer the same four placement questions.
#
#   CREATE a new issue and wire it:
#     bash scripts/file_issue.sh \
#         --title "..." --body-file body.md --shape work \
#         (--parent N | --no-parent) \
#         (--after N | --top) \
#         (--blocked-by N,N | --blocked-by none) \
#         (--blocks N,N | --blocks none) \
#         [--dry-run]
#
#   ADOPT an issue that already exists and wire it:
#     bash scripts/file_issue.sh --adopt N \
#         (--parent N | --no-parent) \
#         (--after N | --top) \
#         (--blocked-by N,N | --blocked-by none) \
#         (--blocks N,N | --blocks none) \
#         [--dry-run]
#
#   --shape is one of: work, decision, your-run, plan-parent. It sets the
#   labels. It belongs to create only.
#
#   --adopt is mutually exclusive with --title, --body-file and --shape: an
#   issue that already exists has all three already.
#
#   Adopt mode refuses rather than reconciles. If the issue is closed, sits
#   under a different parent, or carries a blocked-by or blocks link this
#   invocation did not name, it stops and prints the
#   `gh issue edit --remove-*` command that clears each contradiction. It
#   writes only the relationships that are not already there, and reads every
#   one of them back regardless.
#
#   The one thing adopt does NOT refuse is the board POSITION. All four
#   placement answers are mandatory, so a position is always named, and adopt
#   MOVES the issue to it. The confirmation summary names where the issue sits
#   today beside where you are sending it, so the slot you are giving up is
#   visible before you say yes.
#
#   --dry-run stops after the board neighbourhood and the confirmation summary.
#   Nothing is created and nothing is changed.
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
REPO="jffriend/photo-consolidation"
OWNER="jffriend"
PROJECT_NUMBER=2
PROJECT_ID="PVT_kwHOAVhgcc4BgorE"
NEIGHBOURS=3

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
# tests/test_file_issue_gating.py runs the retry path at DELAY=0 to stay
# fast and deterministic. What DELAY=0 does NOT do is buy extra retries with
# real tolerance; an operator chasing more real wall-clock budget still
# needs a non-zero DELAY, per the warning above.
READBACK_ATTEMPTS="${FILE_ISSUE_READBACK_ATTEMPTS:-5}"
READBACK_DELAY="${FILE_ISSUE_READBACK_DELAY:-1}"
READBACK_WAITED=0   # seconds actually spent waiting, reported in every refusal

TITLE=""
BODY_FILE=""
SHAPE=""
ADOPT=""
# THE MOVE RECORD (adopt mode only), latched where the confirmation screen
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
    -h|--help)    usage; exit 0 ;;
    *)            die "ERROR: unknown flag: $1" ;;
  esac
done

if [ -n "$ADOPT" ]; then MODE=adopt; else MODE=create; fi
if [ "$MODE" = adopt ]; then NOTHING="Nothing was changed."; else NOTHING="Nothing was created."; fi

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
  case "$ADOPT" in
    *[!0-9]*|"") die "ERROR: --adopt takes an issue number (got: $ADOPT). $NOTHING" ;;
  esac
else
  [ -n "$TITLE" ] || die "ERROR: --title is required. Nothing was created."
  [ -n "$BODY_FILE" ] || die "ERROR: --body-file is required. Nothing was created."
  [ -f "$BODY_FILE" ] || die "ERROR: --body-file names a file that does not exist: $BODY_FILE"
  [ -n "$SHAPE" ] || die "ERROR: --shape is required, one of: work, decision, your-run, plan-parent. Nothing was created."

  case "$SHAPE" in
    work)        LABELS=(--label work) ;;
    decision)    LABELS=(--label decision --label needs-joe) ;;
    your-run)    LABELS=(--label your-run --label needs-joe) ;;
    plan-parent) LABELS=(--label plan) ;;
    *) die "ERROR: --shape must be one of: work, decision, your-run, plan-parent (got: $SHAPE). Nothing was created." ;;
  esac
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
# issue was created, and the GraphQL lookup — which takes an Int! — then failed
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
  # repeat would also have failed the whole `gh issue edit --add-blocked-by
  # 122,122` call, the way any already-present link does. De-duplicating HERE
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
  if python3 "$SCRIPT_DIR/issue_text.py" plan-derived "$body_file"; then
    if [ "$NO_PARENT" -eq 1 ]; then
      design_line="$(python3 "$SCRIPT_DIR/issue_text.py" design-line "$body_file")"
      die "ERROR: this issue is plan-derived, so --parent is required and --no-parent is refused.
       Its Design: field links into docs/plans/ —

         $design_line

       Pass --parent <N> naming the plan-parent issue for that plan.
       $NOTHING"
    fi
  fi
}

[ "$MODE" = create ] && parenting_rule "$BODY_FILE"

# ---------------------------------------------------------------------------
# The capability probe. gh 2.94.0 replaced the node-id lookups this script used
# to hand-roll with native relationship flags, and this script now uses them.
# A flag discovered absent MID-WRITE leaves a half-wired issue behind, so the
# capability is established here, offline, before anything touches the network.
#
# It resolves to four states, never a boolean:
#   not installed  — gh is not on PATH
#   absent         — a flag or a --json field this write path needs is missing
#   undeterminable — the help output could not be read or parsed at all
#   present        — proceed
# A probe that could not run is not a probe that passed. Unable to look is not
# permission.
#
# The version is READ and REPORTED — it is what makes the refusal clearable —
# but it never decides. A gh whose flags probe cleanly and whose version string
# is unreadable proceeds, with a sentinel printed where the version would go.
# ---------------------------------------------------------------------------

GH_FLAGS_LANDED_IN="2.94.0"      # corroborated against the cli/cli releases API
GH_NEWEST_VERIFIED_HERE="2.98.0" # the newest release checked by hand in this repo

# The capabilities the write path of THIS RUN uses. One row per gh sub-command.
# Adopt mode swaps in its own row: the create path never runs `gh issue edit`
# and adopt never runs `gh issue create`, and refusing either over a flag it
# does not use would be a refusal with no cause.
GH_NEEDED_FLAGS=(
  "issue create|--parent,--blocked-by,--blocking"
)
if [ "$MODE" = adopt ]; then
  GH_NEEDED_FLAGS=(
    "issue edit|--parent,--add-blocked-by,--add-blocking,--remove-parent,--remove-blocked-by,--remove-blocking"
  )
fi
GH_NEEDED_JSON_FIELDS="parent blockedBy blocking"

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

gh_version_major() { local x="$1"; printf '%s' "${x%%.*}"; }
gh_version_minor() { local x="$1"; x="${x#*.}"; printf '%s' "${x%%.*}"; }

gh_gap_phrase() {
  # How far $1 sits from the reference version $2, in words. The comparison is
  # on (major, minor) TOGETHER. Subtracting minors alone reported a future
  # gh 3.1 as 97 releases BEHIND 2.98 — a wrong number stated with the same
  # confidence as a right one, in the sentence that exists to make the refusal
  # clearable. Across a major bump no release COUNT is meaningful, so none is
  # invented; the direction is stated and the reference named.
  local v="$1" ref="$2" what="$3"
  local vma vmi rma rmi
  vma="$(gh_version_major "$v")";   vmi="$(gh_version_minor "$v")"
  rma="$(gh_version_major "$ref")"; rmi="$(gh_version_minor "$ref")"
  if [ "$vma" -eq "$rma" ]; then
    if [ "$vmi" -lt "$rmi" ]; then
      printf '%s release(s) behind %s, %s' "$(( rmi - vmi ))" "$ref" "$what"
    else
      printf 'at or ahead of %s, %s' "$ref" "$what"
    fi
  elif [ "$vma" -lt "$rma" ]; then
    printf 'a whole major version behind %s, %s' "$ref" "$what"
  else
    printf 'a whole major version ahead of %s, %s' "$ref" "$what"
  fi
}

gh_version_with_gap() {
  # A version recorded without its gap is what let a session read
  # `gh version 2.90.0` and draw no conclusion from it.
  local v="$1" major minor
  if [ "$v" = "unknown" ]; then
    printf 'installed gh version: unknown (its version string could not be parsed)'
    return 0
  fi
  major="$(gh_version_major "$v")"
  minor="$(gh_version_minor "$v")"
  case "$major" in ''|*[!0-9]*) printf 'installed gh %s' "$v"; return 0 ;; esac
  case "$minor" in ''|*[!0-9]*) printf 'installed gh %s' "$v"; return 0 ;; esac
  printf 'installed gh %s' "$v"
  printf ' — %s' \
    "$(gh_gap_phrase "$v" "$GH_NEWEST_VERIFIED_HERE" 'the newest verified in this repo')"
  printf ', and %s' \
    "$(gh_gap_phrase "$v" "$GH_FLAGS_LANDED_IN" 'where these flags landed')"
}

gh_flags_block() {
  # The FLAGS block only. Every flag also appears in EXAMPLES — `--parent`
  # appears three times in `gh issue create --help` — so grepping the whole
  # text would pass on a gh that has none of them.
  #
  # The block closes on ANY section header, never on one hardcoded literal.
  # Losing the OPENER fails safe: no block is read, the probe calls it
  # undeterminable and refuses. Losing or RENAMING the CLOSER used to fail
  # UNSAFE — with `INHERITED FLAGS` renamed to `GLOBAL FLAGS` the block ran to
  # end of file and swallowed EXAMPLES, so a gh with NONE of the flags probed
  # "ok" and was rejected mid-write, leaving behind exactly the half-wired
  # issue this probe exists to prevent. gh section headers are upper-case
  # words at column zero, so that is what ends the block.
  awk '/^FLAGS$/ {inblock=1; next} /^[A-Z][A-Z ]*$/ {inblock=0} inblock'
}

probe_gh_capability() {
  command -v gh >/dev/null 2>&1 || die "REFUSED: gh is not on PATH.
       This script writes every issue relationship through gh's native flags,
       and reads every one of them back through gh. $NOTHING
       Install it (brew install gh), then re-run this command."

  GH_VERSION="$(gh_version_fact)"

  local missing="" undeterminable=""
  local row cmd flags flag help block

  for row in "${GH_NEEDED_FLAGS[@]}"; do
    cmd="${row%%|*}"
    flags="${row#*|}"
    # shellcheck disable=SC2086
    help="$(gh $cmd --help 2>/dev/null)"
    block="$(printf '%s\n' "$help" | gh_flags_block)"
    if [ -z "$(printf '%s' "$block" | tr -d '[:space:]')" ]; then
      undeterminable="${undeterminable}         gh $cmd --help   (no FLAGS block could be read from its output)
"
      continue
    fi
    for flag in $(printf '%s' "$flags" | tr ',' ' '); do
      printf '%s\n' "$block" | grep -qE -- "(^|[^-[:alnum:]])$flag([^-[:alnum:]]|\$)" \
        || missing="${missing}         $flag   (a flag of: gh $cmd)
"
    done
  done

  # Bare `gh issue view --json` prints its field list to STDERR and exits 1.
  # That non-zero exit is NORMAL. Reading it as undeterminable would refuse
  # every run; capture with 2>&1 and judge the output, not the exit code.
  local fieldout fieldlist field
  fieldout="$(gh issue view --json 2>&1)"
  fieldlist="$(printf '%s\n' "$fieldout" | awk '/^  [A-Za-z][A-Za-z0-9]*$/ {print $1}')"
  if [ -z "$fieldlist" ]; then
    undeterminable="${undeterminable}         gh issue view --json   (no --json field list could be read from its output)
"
  else
    for field in $GH_NEEDED_JSON_FIELDS; do
      printf '%s\n' "$fieldlist" | grep -qx -- "$field" \
        || missing="${missing}         $field   (a --json field of: gh issue view)
"
    done
  fi

  if [ -n "$undeterminable" ]; then
    die "REFUSED — UNDETERMINABLE CAPABILITY: this gh's support for native issue
       relationships could not be established. $NOTHING

       Unable to look is not permission, so this refuses rather than assuming.

       These invocations produced output that could not be read or parsed:

$undeterminable
       $(gh_version_with_gap "$GH_VERSION")

       To clear this, run that invocation yourself and see what it prints:

         gh issue create --help
         gh issue edit --help
         gh issue view --json
         gh --version

       If gh needs re-authenticating or reinstalling, 'gh auth status' and
       'brew upgrade gh' are the two things to try, then re-run this command."
  fi

  if [ -n "$missing" ]; then
    die "REFUSED — MISSING CAPABILITY: this gh cannot write and read issue
       relationships natively. $NOTHING

       Missing:

$missing
       $(gh_version_with_gap "$GH_VERSION")

       Upgrade it and re-run this command:

         brew upgrade gh"
  fi

  echo "gh capability     ok (gh $GH_VERSION; native --parent/--blocked-by/--blocking, and --json parent,blockedBy,blocking)"
}

probe_gh_capability

# ---------------------------------------------------------------------------
# From here on calls go to the network. Everything down to the confirmation
# prompt is still READ-ONLY: nothing creates or changes anything until the
# prompt is answered yes.
# ---------------------------------------------------------------------------

BOARD_JSON="$(mktemp -t file_issue_board)"
BOARD_ERR="$(mktemp -t file_issue_boarderr)"
cleanup() { rm -f "$BOARD_JSON" "$BOARD_ERR" "${BOARD_JSON}.2" "${TITLES_JSON:-}" "${ADOPT_BODY:-}" ; }
trap cleanup EXIT

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

# ---------------------------------------------------------------------------
# Adopt: the POST-FETCH stage of the gate. Reads the issue, then refuses on a
# closed issue, on the parenting rule, and on any relationship that contradicts
# the answers given. Still before any write.
# ---------------------------------------------------------------------------

FOUND_PARENT=""
FOUND_BLOCKED=""
FOUND_BLOCKING=""

if [ "$MODE" = adopt ]; then
  ADOPT_JSON="$(gh issue view "$ADOPT" --repo "$REPO" --json state,body,parent,blockedBy,blocking 2>/dev/null)"
  if [ -z "$(printf '%s' "$ADOPT_JSON" | tr -d '[:space:]')" ] \
     || [ "$(printf '%s' "$ADOPT_JSON" | jq -r 'has("state")' 2>/dev/null)" != "true" ]; then
    die "ERROR: --adopt $ADOPT — issue #$ADOPT could not be read from $REPO.
       Check that the number exists and that 'gh auth status' is healthy.
       $NOTHING"
  fi

  ADOPT_STATE="$(printf '%s' "$ADOPT_JSON" | jq -r '.state // ""')"
  case "$ADOPT_STATE" in
    OPEN|open) ;;
    *) die "ERROR: --adopt $ADOPT — issue #$ADOPT is ${ADOPT_STATE:-not open}, not open.
       A closed issue is not outstanding work, so it does not go on the board.
       Reopen it first if it should be, then re-run this command. $NOTHING" ;;
  esac

  ADOPT_BODY="$(mktemp -t file_issue_adoptbody)"
  printf '%s' "$ADOPT_JSON" | jq -r '.body // ""' >"$ADOPT_BODY"
  parenting_rule "$ADOPT_BODY"

  FOUND_PARENT="$(printf '%s' "$ADOPT_JSON" | jq -r '.parent.number // ""' | tr -d '[:space:]')"
  FOUND_BLOCKED="$(printf '%s' "$ADOPT_JSON" | jq -r '[(.blockedBy.nodes // [])[].number] | sort | .[]' | tr '\n' ' ')"
  FOUND_BLOCKING="$(printf '%s' "$ADOPT_JSON" | jq -r '[(.blocking.nodes // [])[].number] | sort | .[]' | tr '\n' ' ')"
  FOUND_BLOCKED="$(printf '%s' "$FOUND_BLOCKED" | sed 's/ *$//')"
  FOUND_BLOCKING="$(printf '%s' "$FOUND_BLOCKING" | sed 's/ *$//')"

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

         gh issue edit $ADOPT --repo $REPO --remove-parent"
  fi

  UNASKED_BLOCKED=""
  for n in $FOUND_BLOCKED; do
    in_set "$n" "$ASKED_BLOCKED" || UNASKED_BLOCKED="$UNASKED_BLOCKED $n"
  done
  UNASKED_BLOCKED="${UNASKED_BLOCKED# }"
  if [ -n "$UNASKED_BLOCKED" ]; then
    die "ERROR: --adopt $ADOPT — blocked-by links already there were not named by
       this invocation. $NOTHING
       found:     #$ADOPT is already blocked by [$FOUND_BLOCKED]
       asked for: [${ASKED_BLOCKED:-none}]
       not named: [$UNASKED_BLOCKED]

       This refuses rather than reconciling. Clear them, then re-run:

         gh issue edit $ADOPT --repo $REPO --remove-blocked-by $(printf '%s' "$UNASKED_BLOCKED" | tr ' ' ',')"
  fi

  UNASKED_BLOCKING=""
  for n in $FOUND_BLOCKING; do
    in_set "$n" "$ASKED_BLOCKING" || UNASKED_BLOCKING="$UNASKED_BLOCKING $n"
  done
  UNASKED_BLOCKING="${UNASKED_BLOCKING# }"
  if [ -n "$UNASKED_BLOCKING" ]; then
    die "ERROR: --adopt $ADOPT — blocks links already there were not named by this
       invocation. $NOTHING
       found:     #$ADOPT already blocks [$FOUND_BLOCKING]
       asked for: [${ASKED_BLOCKING:-none}]
       not named: [$UNASKED_BLOCKING]

       This refuses rather than reconciling. Clear them, then re-run:

         gh issue edit $ADOPT --repo $REPO --remove-blocking $(printf '%s' "$UNASKED_BLOCKING" | tr ' ' ',')"
  fi
fi

# ---------------------------------------------------------------------------
# The neighbour check. Read-only; still creates and changes nothing.
# ---------------------------------------------------------------------------

read_board() {
  # Ordered "<number>\t<title>" lines. A truncated board is fatal, because a
  # truncated board is exactly what hid #164.
  local out="$1"
  if ! bash "$SCRIPT_DIR/board.sh" "$out" 2>"$BOARD_ERR"; then
    printf 'ERROR: the board listing is not trustworthy — %s\n' "$(tr '\n' ' ' <"$BOARD_ERR")" >&2
    printf 'A truncated board reads exactly like a short one. Refusing to go on.\n' >&2
    return 1
  fi
  jq -s -r '[.[].data.user.projectV2.items.nodes[]]
            | .[] | select(.content.number != null)
            | "\(.content.number)\t\(.content.title)"' "$out"
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
  TITLES_JSON="$(mktemp -t file_issue_titles)"
  gh issue list --repo "$REPO" --state open --limit 500 --json number,title >"$TITLES_JSON" 2>/dev/null \
    || die "ERROR: could not list open issues to check for duplicates. Nothing was created."
  DUPES="$(python3 "$SCRIPT_DIR/issue_text.py" dupes "$TITLE" "$TITLES_JSON")"
  if [ -n "$DUPES" ]; then
    echo "########################################################################"
    echo "## POSSIBLE DUPLICATES — read these before you answer                  #"
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

printf '%s' "$( [ "$MODE" = adopt ] && printf 'Wire it? [y/N] ' || printf 'Create it? [y/N] ' )"
read -r ANSWER || ANSWER=""
case "$ANSWER" in
  y|Y|yes|YES) ;;
  *) die "Not confirmed. $NOTHING" ;;
esac

# ---------------------------------------------------------------------------
# Apply. This is the ONE place the two modes legitimately differ: create folds
# the relationships into the create call so no window exists in which the issue
# exists unwired; adopt writes the ones that are not already there.
# ---------------------------------------------------------------------------

BLOCKED_CSV="$(csv_of "$BLOCKED_LIST")"
BLOCKS_CSV="$(csv_of "$BLOCKS_LIST")"

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
  # a "could not look" refusal clearable instead of a dead end.
  printf '  bash scripts/file_issue.sh --adopt %s %s %s --blocked-by %s --blocks %s\n' \
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
  # never showed the issue and the corroborating single-issue read never showed
  # it either. Both queries hit the same Projects store and share its
  # replication lag, so their agreement is a weak signal — the refusal rests on
  # the EXHAUSTED BOUND, not on that agreement. Nothing here proved the wiring
  # wrong, so nothing here may tell the operator to re-file.
  half_wired_head "$1"
  printf 'Read %s times over %ss; the board never showed it and a direct read of the\n' \
    "$READBACK_ATTEMPTS" "$READBACK_WAITED" >&2
  printf "issue's project items did not show it either.\n" >&2
  printf 'The item-add and the position write both returned WITHOUT error before this\n' >&2
  printf 'read, so this is as likely a listing that has not caught up as a write that\n' >&2
  printf 'never landed. Check the board yourself, and re-run the check once it settles:\n' >&2
  reverify_command >&2
  exit 1
}

half_wired_unverified() {
  # POSITION UNVERIFIED. Membership IS proven — a direct read of the issue's
  # project items returned an item on project 2. Position is an index into the
  # board listing, and the listing never caught up, so there was nothing to
  # compare it against. This is not a failed write and must never read as one.
  half_wired_head "$1"
  printf 'Membership is PROVEN: a direct read of the project items of #%s returned an\n' "$NUM" >&2
  printf 'item on project %s. Only the POSITION is unverified — the board listing was\n' "$PROJECT_NUMBER" >&2
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

if [ "$MODE" = create ]; then
  # One call. Parent and both blocking directions are set BY the create, so no
  # window exists in which the issue exists unwired. A relationship answered
  # `none` omits its flag entirely — never passes it empty.
  CREATE_ARGS=(--repo "$REPO" --title "$TITLE" --body-file "$BODY_FILE" "${LABELS[@]}")
  [ -n "$PARENT" ] && CREATE_ARGS+=(--parent "$PARENT")
  [ -n "$BLOCKED_CSV" ] && CREATE_ARGS+=(--blocked-by "$BLOCKED_CSV")
  [ -n "$BLOCKS_CSV" ] && CREATE_ARGS+=(--blocking "$BLOCKS_CSV")

  URL="$(gh issue create "${CREATE_ARGS[@]}" | tail -1 | tr -d '[:space:]')"
  [ -n "$URL" ] || die "ERROR: gh issue create produced no issue URL. Nothing to read back."
  NUM="${URL##*/}"
  case "$NUM" in *[!0-9]*) die "ERROR: could not read an issue number out of: $URL" ;; esac
  HALF_WIRED_PROVENANCE="It is left HALF-WIRED — the create succeeded and this relationship did not."
  HALF_WIRED_NEXT="Finish it by hand, or delete #$NUM and re-run. Do not assume it is fine."
  echo "created #$NUM  $URL"
else
  NUM="$ADOPT"
  URL="https://github.com/$REPO/issues/$NUM"
  HALF_WIRED_PROVENANCE="It is left PARTLY WIRED — relationships this run wrote may have landed, and this one did not agree."
  HALF_WIRED_NEXT="Finish it by hand with gh issue edit, then re-run this command. Do not delete #$NUM — nothing here proved its wiring wrong."

  # A DELTA, not a set. `gh issue edit` is NOT idempotent on either kind of
  # relationship — measured against the live board on 2026-08-24 with gh
  # 2.98.0, recorded on #233. Re-adding a link that is already there fails the
  # WHOLE call:
  #   gh issue edit 234 --add-blocked-by 233 -> Validation failed: Target issue
  #        has already been taken (addBlockedBy), exit 1
  #   gh issue edit 234 --parent 240         -> Issue may not contain duplicate
  #        sub-issues (addSubIssue), exit 1
  # The pre-existing link survived both, so it is a refusal, not corruption.
  # A flag is therefore passed ONLY for a relationship that is NOT already
  # there. A contradicting one has already been refused above; an already
  # matching one is skipped. If the delta is empty no edit is issued at all —
  # and the read-back still runs, because it is the only proof anything holds.
  EDIT_ARGS=()
  [ -n "$PARENT" ] && [ "$PARENT" != "$FOUND_PARENT" ] && EDIT_ARGS+=(--parent "$PARENT")

  ADD_BLOCKED=""
  for n in $ASKED_BLOCKED; do
    in_set "$n" "$FOUND_BLOCKED" || ADD_BLOCKED="$ADD_BLOCKED,$n"
  done
  ADD_BLOCKED="${ADD_BLOCKED#,}"
  [ -n "$ADD_BLOCKED" ] && EDIT_ARGS+=(--add-blocked-by "$ADD_BLOCKED")

  ADD_BLOCKING=""
  for n in $ASKED_BLOCKING; do
    in_set "$n" "$FOUND_BLOCKING" || ADD_BLOCKING="$ADD_BLOCKING,$n"
  done
  ADD_BLOCKING="${ADD_BLOCKING#,}"
  [ -n "$ADD_BLOCKING" ] && EDIT_ARGS+=(--add-blocking "$ADD_BLOCKING")

  if [ "${#EDIT_ARGS[@]}" -eq 0 ]; then
    echo "relationships     every one asked for is already there; no edit issued"
    echo "                  (the read-back below is the only proof of that)"
  else
    if ! gh issue edit "$NUM" --repo "$REPO" "${EDIT_ARGS[@]}" >/dev/null; then
      # NOT fatal here, and NOT evidence that nothing landed. One rejected flag
      # fails the whole call server-side while the others may already have been
      # applied, so the read-back below is what establishes the true state.
      echo "WARNING: gh issue edit exited non-zero for #$NUM." >&2
      echo "         Relationships it carried MAY still have been written." >&2
      echo "         The read-back below reports each one separately." >&2
    fi
  fi
  echo "wiring #$NUM  $URL"
fi

# ---------------------------------------------------------------------------
# SHARED BOARD HALF. Both modes call these, in the current shell.
# ---------------------------------------------------------------------------

board_item_id() {
  # $1 issue number, $2 an optional jq comment marking WHICH lookup this is.
  # The query travels in a temp file, so the only argv-visible text is the
  # --jq expression; the marker rides there so the two lookups can be told
  # apart by anything reading the invocation.
  #
  # RETURNS the item id on stdout, and gh's own exit status. That status is the
  # whole point: `2>/dev/null` makes an ERRORED query look exactly like an
  # ABSENT item, and the --after call site read that silence as "the item is
  # not there" and refused with half_wired() — the did-not-land refusal, the
  # one that prints "delete #N and re-run" — over a READ that failed. A caller
  # that cannot tell the two apart cannot pick the right refusal, so this hands
  # it the distinction and each call site decides for itself.
  local num="$1" marker="${2-}" q id rc
  q="$(mktemp -t file_issue_q)"
  cat >"$q" <<'GRAPHQL'
query($n: Int!) {
  repository(owner: "jffriend", name: "photo-consolidation") {
    issue(number: $n) {
      projectItems(first: 20) { nodes { id project { number } } }
    }
  }
}
GRAPHQL
  id="$(gh api graphql -F "query=@$q" -F n="$num" \
    --jq ".data.repository.issue.projectItems.nodes[] | select(.project.number == $PROJECT_NUMBER) | .id $marker" 2>/dev/null \
    | head -1 | tr -d '[:space:]')"
  rc=$?
  rm -f "$q"
  case "$id" in null) id="" ;; esac
  printf '%s\n' "$id"
  return "$rc"
}

board_membership_corroboration() {
  # The SECOND query path over the same Projects store, issued on EVERY
  # read-back attempt on which the board listing does not show the issue.
  #
  # A POSITIVE result is conclusive: the listing was stale and membership is
  # proven. Agreement on ABSENCE is a weaker signal — both queries hit the
  # same store and share its replication lag — and is never what a refusal
  # rests on; the refusal rests on the exhausted bound.
  #
  # The marker is carried in the --jq expression because the GraphQL text
  # travels as `-F query=@tempfile` and never reaches argv. Without a marker
  # this call is indistinguishable from the --after lookup, and the test
  # fake — which matches on argv substrings — would answer both identically,
  # leaving `test_missing_from_the_board_fails_loudly` unable to fail.
  board_item_id "$1" "# boardMembershipCorroboration"
}

board_item_by_issue_number() {
  # Resolves the project item id BY ISSUE NUMBER, so an issue already on the
  # board does not depend on item-add's output. The create path takes the id
  # from item-add and refuses when it is empty; for an adopted issue already on
  # the board that would abort a correctly wired filing.
  board_item_id "$1" "# boardItemByIssueNumber"
}

board_item_after() {
  # The item to position after. Same query, different subject.
  board_item_id "$1"
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
  local after_item after_rc
  ITEM_ID=""
  if [ "$MODE" = adopt ]; then
    ITEM_ID="$(board_item_by_issue_number "$NUM")"
  fi
  if [ -z "$ITEM_ID" ]; then
    ITEM_ID="$(gh project item-add "$PROJECT_NUMBER" --owner "$OWNER" --url "$URL" --format json | jq -r '.id')"
  fi
  [ -n "$ITEM_ID" ] && [ "$ITEM_ID" != "null" ] || half_wired "the board (project 2) did not return an item id for #$NUM"

  if [ "$TOP" -eq 1 ]; then
    gh api graphql -f query='mutation($p:ID!,$i:ID!){updateProjectV2ItemPosition(input:{projectId:$p,itemId:$i}){clientMutationId}}' \
      -f p="$PROJECT_ID" -f i="$ITEM_ID" >/dev/null \
      || half_wired "the board position write failed for #$NUM"
  else
    after_item="$(board_item_after "$AFTER")"
    after_rc=$?
    # ERRORED and ABSENT are different answers and get different refusals. A
    # query that failed proves nothing about #$AFTER, so it must never reach
    # half_wired(), whose next action includes deleting the issue.
    [ "$after_rc" -eq 0 ] \
      || half_wired_unreadable "the board item for #$AFTER could not be read, so #$NUM could not be positioned"
    [ -n "$after_item" ] || half_wired "could not find the board item for #$AFTER, so #$NUM could not be positioned"
    gh api graphql -f query='mutation($p:ID!,$i:ID!,$a:ID!){updateProjectV2ItemPosition(input:{projectId:$p,itemId:$i,afterId:$a}){clientMutationId}}' \
      -f p="$PROJECT_ID" -f i="$ITEM_ID" -f a="$after_item" >/dev/null \
      || half_wired "the board position write failed for #$NUM"
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
# and tests/test_file_issue_gating.py scans for a second copy.
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
      # shows the issue there is nothing to compare.
      if [ -n "$(board_membership_corroboration "$NUM")" ]; then
        member_proven=1
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
  if [ "$TOP" -eq 1 ]; then
    echo "  board position     ok (top)"
  else
    echo "  board position     ok (after #$AFTER)"
  fi

  # One call for all three relationships. Each dependency field is
  # {nodes: [...], totalCount: N}; parent is an object or null.
  REL_JSON="$(gh issue view "$NUM" --repo "$REPO" --json parent,blockedBy,blocking)"
  REL_RC=$?
  # THREE CHECKS, because emptiness alone was a vacuous pass. Any JSON that
  # simply lacks the three fields — `{"message":"Not Found"}` is the one that
  # reproduced it — makes all three jq extractions yield empty, and empty
  # compares EQUAL to the empty answer set. On the commonest filing shape,
  # `--no-parent --blocked-by none --blocks none`, the run printed three
  # `ok (none)` lines and exited 0 having proven NOTHING at all. The adopt
  # pre-fetch already validates its reply with has("state"); this is the same
  # check, on the fields this comparison actually reads.
  #
  # All three are COULD NOT LOOK, never did not land: a read that failed says
  # nothing about the write, and its refusal must not offer to delete anything.
  [ "$REL_RC" -eq 0 ] || half_wired_unreadable "the relationships of #$NUM could not be read back — gh exited $REL_RC"
  [ -n "$REL_JSON" ] || half_wired_unreadable "the relationships of #$NUM could not be read back at all"
  [ "$(printf '%s' "$REL_JSON" | jq -r 'has("parent") and has("blockedBy") and has("blocking")' 2>/dev/null)" = "true" ] \
    || half_wired_unreadable "the relationships of #$NUM came back in an unrecognised shape — the reply carries no parent/blockedBy/blocking fields to compare"

  PARENT_READ="$(printf '%s' "$REL_JSON" | jq -r '.parent.number // ""' | tr -d '[:space:]')"
  if [ -n "$PARENT" ]; then
    [ "$PARENT_READ" = "$PARENT" ] || half_wired "parent — asked for #$NUM to sit under #$PARENT; it reads back as ${PARENT_READ:-no parent}"
    echo "  parent             ok (#$PARENT)"
  else
    [ -z "$PARENT_READ" ] || half_wired "parent — asked for no parent; #$NUM reads back under #$PARENT_READ"
    echo "  parent             ok (none)"
  fi

  BLOCKED_READ="$(printf '%s' "$REL_JSON" | jq -r '[(.blockedBy.nodes // [])[].number] | sort | join(",")')"
  BLOCKED_WANT="$(norm "$(printf '%s' "$BLOCKED_LIST" | tr '\n' ' ')")"
  [ "$BLOCKED_READ" = "$BLOCKED_WANT" ] \
    || half_wired "blocked-by — asked for [${BLOCKED_WANT:-none}]; #$NUM reads back as [${BLOCKED_READ:-none}]"
  echo "  blocked-by         ok (${BLOCKED_WANT:-none})"

  BLOCKING_READ="$(printf '%s' "$REL_JSON" | jq -r '[(.blocking.nodes // [])[].number] | sort | join(",")')"
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
if [ "$ADOPT_MOVED" -eq 1 ]; then
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
slot shown on the confirmation screen immediately before the move."

  # BEST EFFORT, AND LOUD WHEN IT FAILS. The wiring has already landed and
  # already been verified by the time this runs. So a failed comment must not
  # call die or any half_wired_* function: those print the delete-and-re-run
  # remedy, which on a correctly wired issue is destructive advice. It must
  # also not be silent, or the promise that a move is always recorded becomes
  # one the tool quietly breaks. So: warn on stderr, carry both positions in
  # text the operator can paste, and still exit 0 — because the wiring did
  # succeed.
  #
  # `gh issue comment` is the one write in this project that legitimately
  # bypasses this script (docs/WORKFLOW.md § 7 names it), because a comment
  # creates no issue and touches no board field. This relies on that existing
  # carve-out; it does not widen it.
  MOVE_RC=0
  MOVE_ERR="$(gh issue comment "$NUM" --repo "$REPO" --body "$MOVE_COMMENT" 2>&1)" \
    || MOVE_RC=$?
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
    echo "  gh issue comment exited $MOVE_RC: ${MOVE_ERR:-(no output)}"          >&2
    echo "POST THIS ON #$NUM BY HAND:"                                           >&2
    printf '%s\n' "$MOVE_COMMENT"                                               >&2
    echo "########################################################################" >&2
  fi
fi

echo
if [ "$MODE" = adopt ]; then
  echo "#$NUM is wired and every relationship read back matching. $URL"
else
  echo "#$NUM is created and every relationship read back matching. $URL"
fi
