#!/bin/bash
# The only supported way to put an issue on the board, whether created here or already existing.
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
#         [--dry-run] [--file-anyway] [--no-board]
#
#   ADOPT an issue that already exists and wire it:
#     bash file_issue.sh --config config.json --adopt N \
#         (--parent N | --no-parent) \
#         (--after N | --top) \
#         (--blocked-by N,N | --blocked-by none) \
#         (--blocks N,N | --blocks none) \
#         [--dry-run] [--no-board]
#
#   In cloud mode the position answer is --position-later in place of
#   (--after N | --top); see CLOUD MODE below.
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
#   CLOUD MODE (a Claude Code cloud session). The session's GitHub proxy
#   refuses the project board itself, so the board cannot be read, added to
#   or placed on. Cloud mode turns on when CLAUDE_CODE_REMOTE=true. Without
#   it, --no-board reads the board first and turns cloud mode on only if the
#   read is refused with the cloud proxy's "sessions are bound to their
#   configured repositories" message; a readable board refuses --no-board,
#   and any other failed read stops the run as it does locally. Cloud mode
#   skips every board call, takes --position-later as the position answer
#   (--after and --top are refused, since nothing could check them), runs the
#   duplicate check, writes the parent and both kinds of blocking link, and
#   labels the issue needs-board. It reads all of that back, prints the two
#   board lines as "not checked (cloud mode)", and ends with a notice that the
#   board was not checked: the issue may already be on it at a spot nobody
#   chose, since sub-issues can be added automatically. --dry-run shows the
#   duplicate check and the summary; there is no board neighbourhood. Place
#   the issue later with a local adopt naming --after N or --top; once that
#   placement reads back, the adopt removes the needs-board label.
#
#   WHERE ONLY GRAPHQL IS REFUSED. Every call goes over GitHub's REST API
#   except the board-position write, which has no REST route. In a session
#   that reaches the board over REST but not GraphQL, a position write
#   refused with HTTP 403 still files and wires the issue, reads every
#   relationship back, and exits 0. The read-back says the board position is
#   NOT SET, the issue sits wherever the board put it (usually the bottom),
#   and a notice prints the adopt command that places it from a session
#   where GraphQL works. No move comment is written in that case, because
#   nothing moved; the adopt run that places it later records its own move.
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

# Retry the read-back's READ, never the write, within 30 SECONDS; the bound is not calibrated to measured lag.
READBACK_ATTEMPTS="${FILE_ISSUE_READBACK_ATTEMPTS:-5}"
READBACK_DELAY="${FILE_ISSUE_READBACK_DELAY:-1}"
READBACK_WAITED=0

CONFIG=""
TITLE=""
BODY_FILE=""
SHAPE=""
ADOPT=""
# Adopt's move record, latched once by the POSITION_LINE block; defaulted here because create mode never sets it (set -u).
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
# Cloud mode skips the board the proxy refuses. Only CLAUDE_CODE_REMOTE, or --no-board plus a proxy refusal, enables it.
NO_BOARD=0
POSITION_LATER=0
CLOUD=0
CLOUD_REASON=""
CLOUD_UNCONFIRMED=0
CLOUD_PROXY_REFUSAL="sessions are bound to their configured repositories"
BOARD_PENDING_LABEL="needs-board"
FOUND_LABEL=""

die() { printf '%s\n' "$*" >&2; exit 1; }

# Zero attempts would make the read-back pass vacuously; a zero delay is legitimate (tests use it).
case "$READBACK_ATTEMPTS" in
  ''|*[!0-9]*) die "ERROR: FILE_ISSUE_READBACK_ATTEMPTS must be a whole number of attempts (got: $READBACK_ATTEMPTS)." ;;
esac
[ "$READBACK_ATTEMPTS" -ge 1 ] || die "ERROR: FILE_ISSUE_READBACK_ATTEMPTS must be at least 1; a read-back that never reads verifies nothing."
case "$READBACK_DELAY" in
  ''|*[!0-9]*) die "ERROR: FILE_ISSUE_READBACK_DELAY must be a whole number of seconds (got: $READBACK_DELAY)." ;;
esac

# Enforce the 30s ceiling: sum the doubling waits, stopping once over so a huge count cannot overflow.
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
    --no-board)   NO_BOARD=1; shift ;;
    --position-later) POSITION_LATER=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    *)            die "ERROR: unknown flag: $1" ;;
  esac
done

# Only the exact value Claude Code sets in a cloud session counts (#14 KTD2).
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
  CLOUD=1
  CLOUD_REASON="CLAUDE_CODE_REMOTE=true"
fi
if [ "$NO_BOARD" -eq 1 ]; then
  # Position answers are checked offline as cloud-mode; without the env var, the board read must prove the proxy refusal.
  [ "$CLOUD" -eq 1 ] || CLOUD_UNCONFIRMED=1
  CLOUD=1
  CLOUD_REASON="${CLOUD_REASON:+$CLOUD_REASON and }--no-board"
fi

if [ -n "$ADOPT" ]; then MODE=adopt; else MODE=create; fi
if [ "$MODE" = adopt ]; then NOTHING="Nothing was changed."; else NOTHING="Nothing was created."; fi

# Load and validate --config before any network call, so a bad field fails offline and is named.

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
FILE_ISSUE_CMD="$(jq -r '.file_issue_cmd // empty' "$CONFIG")"
DESIGN_LINE_REQUIRED="$(jq -r 'if (.design_line_required // false) then "true" else "false" end' "$CONFIG")"
# Check the type: jq's // treats false as absent, and a string "true" would pass a value check.
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

# Offline gate; adopt's post-fetch stage runs later because the parenting rule needs the fetched body.

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
  LABEL_FIELDS=()
  while IFS= read -r lbl; do
    [ -n "$lbl" ] && LABEL_FIELDS+=(-f "labels[]=$lbl")
  done <<<"$SHAPE_LABELS"
  # In the create itself, so a cloud-filed issue never exists without it (#14 R8).
  [ "$CLOUD" -eq 1 ] && LABEL_FIELDS+=(-f "labels[]=$BOARD_PENDING_LABEL")
fi

if [ -n "$PARENT" ] && [ "$NO_PARENT" -eq 1 ]; then
  die "ERROR: --parent and --no-parent are contradictory. Pass exactly one. $NOTHING"
fi
if [ -z "$PARENT" ] && [ "$NO_PARENT" -eq 0 ]; then
  die "ERROR: no parent answer. Pass --parent <N> or --no-parent.
       Every issue answers this. There is no default."
fi
# Digit-validate --parent now: a typo caught only at read-back leaves a real issue with no parent.
if [ -n "$PARENT" ]; then
  case "$PARENT" in
    *[!0-9]*) die "ERROR: --parent takes an issue number (got: $PARENT). $NOTHING" ;;
  esac
fi

# Cloud mode can't see the board, so it takes --position-later and refuses --after/--top (#14 R5-R7).
if [ "$CLOUD" -eq 1 ]; then
  if [ -n "$AFTER" ] || [ "$TOP" -eq 1 ]; then
    die "ERROR: cloud mode ($CLOUD_REASON) cannot see the board, so it cannot check
       --after or --top. Pass --position-later instead; the issue is labelled
       $BOARD_PENDING_LABEL and placed later from a local session. $NOTHING"
  fi
  [ "$POSITION_LATER" -eq 1 ] || die "ERROR: no board-position answer. In cloud mode ($CLOUD_REASON) pass
       --position-later: the board cannot be seen from here, so the position is
       decided later, from a local session. $NOTHING"
else
  [ "$POSITION_LATER" -eq 0 ] || die "ERROR: --position-later is for cloud mode only (a Claude Code cloud
       session, or --no-board). This run can see the board, so pass --after <N>
       or --top. $NOTHING"
  if [ -n "$AFTER" ] && [ "$TOP" -eq 1 ]; then
    die "ERROR: --after and --top are contradictory. Pass exactly one. $NOTHING"
  fi
  if [ -z "$AFTER" ] && [ "$TOP" -eq 0 ]; then
    die "ERROR: no board-position answer. Pass --after <N> or --top.
       Every issue answers this. There is no default — an unpositioned issue
       lands wherever the board put it, which is not a priority decision."
  fi
fi
# --after must be digits: board lookups use grep, where an unchecked value is a regex (`1.4` matches `144`).
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
  local raw="$1" n
  case "$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')" in
    none|"") return 0 ;;
  esac
  # Trailing newline: read drops an unterminated last line. sort -nu dedupes to match what the server reads back.
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

# A parent is required when the body's Design: field marks it plan-derived; adopt applies this to the fetched body.
parenting_rule() {
  local body_file="$1" design_line
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

# Capability probe: only gh on PATH is checked; its version is printed for the record and never decides.

gh_version_fact() {
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

if [ "$CLOUD" -eq 1 ] && [ "$CLOUD_UNCONFIRMED" -eq 0 ]; then
  echo "cloud mode        on ($CLOUD_REASON): the board is not read or written"
fi
probe_gh_capability

# Network from here; everything up to the --dry-run exit and the duplicates stop is read-only.

BOARD_JSON="$(mktemp -t file_issue_board.XXXXXX)"
BOARD_ERR="$(mktemp -t file_issue_boarderr.XXXXXX)"
GH_API_ERR="$(mktemp -t file_issue_ghapierr.XXXXXX)"
cleanup() { rm -f "$BOARD_JSON" "$BOARD_ERR" "$GH_API_ERR" "${BOARD_JSON}.2" "${TITLES_JSON:-}" "${ADOPT_BODY:-}" ; }
trap cleanup EXIT

# gh_api keeps stderr in $GH_API_ERR; gh_api_failed_with matches only gh's "(HTTP NNN)" suffix.
gh_api() { gh api "$@" 2>"$GH_API_ERR"; }
gh_api_failed_with() { grep -qF "(HTTP $1)" "$GH_API_ERR"; }
gh_api_err() { tr '\n' ' ' <"$GH_API_ERR"; }

board_untrusted() {
  printf 'ERROR: the board listing is not trustworthy — %s\n' "$(tr '\n' ' ' <"$BOARD_ERR")" >&2
  printf 'A truncated board reads exactly like a short one. Refusing to go on.\n' >&2
}

# --no-board without the env var (#14 R2): a proxy refusal confirms cloud mode, a readable board refuses the flag.
if [ "$CLOUD_UNCONFIRMED" -eq 1 ]; then
  if bash "$SCRIPT_DIR/board.sh" --config "$CONFIG" "$BOARD_JSON" 2>"$BOARD_ERR"; then
    die "REFUSED: --no-board is for a session whose board read is refused by the
       Claude Code cloud proxy. This session read the board, so it must check
       the position against it: drop --no-board and --position-later and pass
       --after <N> or --top. $NOTHING"
  fi
  # Require both the proxy's phrase and gh's 403 suffix, so another failure quoting the phrase can't pass.
  if ! grep -qF "$CLOUD_PROXY_REFUSAL" "$BOARD_ERR" \
     || ! grep -qF "(HTTP 403)" "$BOARD_ERR"; then
    board_untrusted
    exit 1
  fi
  CLOUD_REASON="--no-board, and the cloud proxy refused the board"
  echo "cloud mode        on ($CLOUD_REASON): the board is not read or written"
fi

issue_numeric_id() {
  # Prints the issue's REST id; returns 0 found, 2 on HTTP 404, 1 unreadable (only a 404 means it doesn't exist).
  local reply id
  reply="$(gh_api "repos/$REPO/issues/$1")" || { gh_api_failed_with 404 && return 2; return 1; }
  id="$(printf '%s\n' "$reply" \
    | jq -r 'if (.id | type) == "number" and .number != null then .id else empty end' 2>/dev/null)"
  [ -n "$id" ] || return 1
  printf '%s\n' "$id"
}

# Sorted, de-duplicated, comma-joined; -u matches parse_list since the server never holds a link twice.
norm() { printf '%s' "$1" | tr ' ' '\n' | sed '/^$/d' | sort -nu | paste -sd, - ; }
csv_of() { printf '%s' "$1" | tr '\n' ',' | sed 's/,$//'; }
in_set() {
  local n="$1" h
  for h in $2; do [ "$h" = "$n" ] && return 0; done
  return 1
}

# Adopt's pre-fetch and the read-back parse the same REST replies here, so a reply is never read two ways.
issue_reply_parent() {
  # Prints the parent number, nothing for no parent, or BAD; GitHub omits parent_issue_url when there is none.
  local out
  out="$(printf '%s' "$1" | jq -r '
    .parent_issue_url as $u
    | if $u == null then ""
      elif ($u | type) == "string" and ($u | test("/[0-9]+$")) then ($u | capture("/(?<n>[0-9]+)$").n)
      else "BAD" end' 2>/dev/null)" || out="BAD"
  printf '%s\n' "$out"
}

issue_reply_label() {
  # Prints present, absent or BAD; requires a labels array, or an error reply would read as absent (#14 KTD6).
  local out
  out="$(printf '%s' "$1" | jq -r --arg l "$2" '
    if (.labels | type) == "array"
    then (if any(.labels[]; (if type == "object" then .name else . end) == $l)
          then "present" else "absent" end)
    else "BAD" end' 2>/dev/null)" || out="BAD"
  printf '%s\n' "${out:-BAD}"
}

dependency_entries() {
  # Prints number:id:owner/name per link, or BAD unless the reply is an array; links can point to other repos.
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
  printf '%s\n' "$1" | sed '/^$/d' | cut -d: -f1 | tr '\n' ' ' | sed 's/ *$//'
}


FOUND_PARENT=""
FOUND_BLOCKED=""
FOUND_BLOCKING=""
FOUND_BLOCKED_PAIRS=""
FOUND_BLOCKING_PAIRS=""
SELF_ID=""

if [ "$MODE" = adopt ]; then
  # Check each reply's shape, not emptiness: empty is legal for all three, and a wrong-shaped reply extracts as empty.
  ADOPT_JSON="$(gh_api "repos/$REPO/issues/$ADOPT")"
  if [ -z "$(printf '%s' "$ADOPT_JSON" | tr -d '[:space:]')" ] \
     || [ "$(printf '%s' "$ADOPT_JSON" | jq -r 'has("state") and has("number") and ((.id | type) == "number")' 2>/dev/null)" != "true" ]; then
    die "ERROR: --adopt $ADOPT — issue #$ADOPT could not be read from $REPO.
       Check that the number exists and that 'gh auth status' is healthy.
       $NOTHING"
  fi
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

  # A cloud adopt adds the board-pending label only if absent; a local placement removes it only if present (#14 KTD7).
  FOUND_LABEL="$(issue_reply_label "$ADOPT_JSON" "$BOARD_PENDING_LABEL")"
  [ "$FOUND_LABEL" != "BAD" ] || die "ERROR: --adopt $ADOPT — the labels of #$ADOPT could not be read from $REPO.
       The reply carries no labels list. $NOTHING"

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

  # KD2: refuse to reconcile, since overwriting a link would be invisible; each refusal names the command that clears it.
  if [ -n "$FOUND_PARENT" ] && [ "$FOUND_PARENT" != "$PARENT" ]; then
    die "ERROR: --adopt $ADOPT — the parent already there contradicts the answer given.
       $NOTHING
       found:     #$ADOPT sits under #$FOUND_PARENT
       asked for: $( [ -n "$PARENT" ] && printf '#%s' "$PARENT" || printf 'no parent' )

       This refuses rather than reconciling: overwriting a parent would be
       invisible afterwards. Clear it, then re-run this command:

         gh api -X DELETE repos/$REPO/issues/$FOUND_PARENT/sub_issue -F sub_issue_id=$SELF_ID"
  fi

  # A blocks link is the blocked issue's blocked-by link, so it is cleared on that issue using #$ADOPT's id.
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


read_board() {
  # Prints number, title, item node id and item numeric id, tab-separated, for Issue rows only; a truncated board is fatal.
  local out="$1"
  if ! bash "$SCRIPT_DIR/board.sh" --config "$CONFIG" "$out" 2>"$BOARD_ERR"; then
    board_untrusted
    return 1
  fi
  jq -s -r '[.[][]]
            | .[] | select(.content_type == "Issue" and .content.number != null)
            | "\(.content.number)\t\(.content.title)\t\(.node_id)\t\(.id)"' "$out"
}

if [ "$CLOUD" -eq 1 ]; then
  # Cloud mode reads no board (#14 R10): nothing to check --after against, no neighbourhood to show (R11).
  BOARD_ROWS=""
  BOARD_NUMS=""
  echo "BOARD NEIGHBOURHOOD — not available in cloud mode (the board is not read)"
  echo
else
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
fi

if [ "$MODE" = create ]; then
  TITLES_JSON="$(mktemp -t file_issue_titles.XXXXXX)"
  TITLES_LIMIT=500
  # Pull requests share the issues listing, so count them toward TITLES_LIMIT before dropping them.
  titles_raw=0
  titles_page=1
  titles_pages=""
  while [ "$titles_raw" -lt "$TITLES_LIMIT" ]; do
    page_json="$(gh_api "repos/$REPO/issues?state=open&per_page=100&page=$titles_page")" \
      || die "ERROR: could not list open issues to check for duplicates ($(gh_api_err)). Nothing was created."
    # Fail closed: a non-array reply would read as an empty page and end the listing as "no duplicates".
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
  # A full listing may hide more open issues; checking past the limit is #19.
  if [ "$titles_raw" -ge "$TITLES_LIMIT" ]; then
    echo "WARNING: the duplicate check read only the first $TITLES_LIMIT open issues."
    echo "         The repo may have more, and a duplicate among them would be missed."
    echo
  fi
  # Fail closed: a crashed checker must not read as "none found".
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
  if [ "$CLOUD" -eq 1 ]; then
    # No board rows in cloud mode; the issue reply carries its own title (R9).
    ADOPT_TITLE="$(printf '%s' "$ADOPT_JSON" | jq -r '.title // ""' 2>/dev/null)"
  else
    ADOPT_TITLE="$(printf '%s\n' "$BOARD_ROWS" | awk -F'\t' -v n="$ADOPT" '$1 == n {print $2; exit}')"
  fi
  echo "ABOUT TO WIRE AN EXISTING ISSUE"
  echo "  issue      #$ADOPT ${ADOPT_TITLE:-(not currently on the board)}"
else
  echo "ABOUT TO CREATE"
  echo "  title      $TITLE"
  echo "  shape      $SHAPE"
fi
echo "  parent     ${PARENT:-none}"

# Adopt can move a boarded issue, so name its current slot beside the requested one and say when confirming moves it.
POSITION_LINE="$( [ "$TOP" -eq 1 ] && echo "top of board" || echo "after #$AFTER" )"
if [ "$CLOUD" -eq 1 ]; then
  # Cloud mode moves nothing: no current slot to name, no move comment.
  POSITION_LINE="decided later (cloud mode; labelled $BOARD_PENDING_LABEL for a local session to place)"
elif [ "$MODE" = adopt ]; then
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
      # Latch here, where "this MOVES it" is printed, so the move record matches what the operator saw.
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

# No confirmation prompt: possible duplicates without --file-anyway exit 3, the one judgement the engine can't make.
if [ "$MODE" = create ] && [ -n "$DUPES" ] && [ "$FILE_ANYWAY" -eq 0 ]; then
  printf '%s\n' "STOPPED: possible duplicates listed above. $NOTHING
       If none of them is the same work, re-run the same command with
       --file-anyway." >&2
  exit 3
fi

# Apply: create writes the issue and every link, adopt only missing links; the shared read-back decides.

half_wired_head() {
  # Shared by every failure; only the provenance and next action differ between modes.
  printf '\n' >&2
  printf 'MISMATCH: %s\n' "$1" >&2
  printf '\n' >&2
  printf 'Issue #%s EXISTS at %s.\n' "$NUM" "$URL" >&2
  printf '%s\n' "$HALF_WIRED_PROVENANCE" >&2
  printf 'Requested: parent=%s, position=%s, blocked-by=[%s], blocks=[%s].\n' \
    "${PARENT:-none}" \
    "$( [ "$CLOUD" -eq 1 ] && echo "decided later" || { [ "$TOP" -eq 1 ] && echo top || echo "after #$AFTER"; } )" \
    "$(printf '%s' "$BLOCKED_LIST" | tr '\n' ' ')" \
    "$(printf '%s' "$BLOCKS_LIST" | tr '\n' ' ')" >&2
}

reverify_command() {
  # The adopt re-run: safe on a wired issue, REST-only, led by file_issue_cmd or this run's paths; $1 overrides the position answer.
  local position="${1-}"
  if [ -z "$position" ]; then
    if [ "$CLOUD" -eq 1 ]; then
      position="--position-later"
      [ "$NO_BOARD" -eq 1 ] && position="--no-board $position"
    elif [ "$TOP" -eq 1 ]; then
      position="--top"
    else
      position="--after $AFTER"
    fi
  fi
  local cmd="$FILE_ISSUE_CMD"
  [ -n "$cmd" ] || cmd="$(printf 'bash %q --config %q' "${BASH_SOURCE[0]}" "$CONFIG")"
  printf '  %s --adopt %s %s %s --blocked-by %s --blocks %s\n' \
    "$cmd" \
    "$NUM" \
    "$( [ -n "$PARENT" ] && printf -- '--parent %s' "$PARENT" || printf -- '--no-parent' )" \
    "$position" \
    "$( [ -n "$BLOCKED_LIST" ] && csv_of "$BLOCKED_LIST" || printf 'none' )" \
    "$( [ -n "$BLOCKS_LIST" ] && csv_of "$BLOCKS_LIST" || printf 'none' )"
}

half_wired() {
  # DID NOT LAND: the server contradicts the answer; the only case whose next action may be re-filing.
  half_wired_head "$1"
  printf '%s\n' "$HALF_WIRED_NEXT" >&2
  exit 1
}

half_wired_absent() {
  # DID NOT LAND within the bounded wait: both reads share replication lag, so never tell the operator to re-file.
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
  # POSITION UNVERIFIED: membership is proven, but the listing never caught up to show position; not a failed write.
  [ "$MODE" = adopt ] && HALF_WIRED_PROVENANCE="Its wiring is not yet verified, and nothing here proved any of it wrong."
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
  # COULD NOT LOOK: the read failed, not the write; not being able to look is not evidence of absence.
  [ "$MODE" = adopt ] && HALF_WIRED_PROVENANCE="Its wiring is not yet verified, and nothing here proved any of it wrong."
  half_wired_head "$1"
  printf 'The READ failed, not the write. Nothing here says the write did not land, and\n' >&2
  printf 'no relationship was proven wrong. Re-run the check once the board reads again:\n' >&2
  reverify_command >&2
  exit 1
}

resolve_or_refuse() {
  # Sets RESOLVED_ID or refuses before any write; call in the current shell so die exits the script.
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
  # A failed call only warns: it can fail after the server applied it, so the read-back decides.
  local what="$1"
  shift
  if ! gh_api -X POST "$@" >/dev/null; then
    LINK_WRITE_FAILED=1
    echo "WARNING: writing $what for #$NUM exited non-zero: $(gh_api_err)" >&2
  fi
}

write_links() {
  # $1 parent or empty, $2 "number:id" blockers, $3 blocked numbers; a blocks link carries #$NUM's id.
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
  # Resolve every referenced issue first (#14 KTD3); a blocker's link write takes its id.
  [ -n "$PARENT" ] && resolve_or_refuse --parent "$PARENT"
  CREATE_BLOCKER_PAIRS=""
  for n in $BLOCKED_LIST; do
    resolve_or_refuse --blocked-by "$n"
    CREATE_BLOCKER_PAIRS="$CREATE_BLOCKER_PAIRS $n:$RESOLVED_ID"
  done
  for n in $BLOCKS_LIST; do
    resolve_or_refuse --blocks "$n"
  done

  # Issue first, then each link (#14 KTD4); a failed link only warns and the read-back names the fix.
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
  # Lead with the adopt command (REST, writes only missing links); delete-and-re-run needs GraphQL, so local only.
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

  # Write a delta, not a set: gh refused repeated links, and REST is assumed (not measured) to do the same.
  ADD_PARENT=""
  [ -n "$PARENT" ] && [ "$PARENT" != "$FOUND_PARENT" ] && ADD_PARENT="$PARENT"
  [ -n "$ADD_PARENT" ] && resolve_or_refuse --parent "$ADD_PARENT"

  ADD_BLOCKED_PAIRS=""
  for n in $ASKED_BLOCKED; do
    in_set "$n" "$FOUND_BLOCKED" && continue
    resolve_or_refuse --blocked-by "$n"
    ADD_BLOCKED_PAIRS="$ADD_BLOCKED_PAIRS $n:$RESOLVED_ID"
  done

  ADD_BLOCKING=""
  for n in $ASKED_BLOCKING; do
    in_set "$n" "$FOUND_BLOCKING" && continue
    resolve_or_refuse --blocks "$n"
    ADD_BLOCKING="$ADD_BLOCKING $n"
  done

  if [ -z "$ADD_PARENT$ADD_BLOCKED_PAIRS$ADD_BLOCKING" ]; then
    echo "relationships     every one asked for is already there; no write issued"
    echo "                  (the read-back below is the only proof of that)"
  else
    write_links "$ADD_PARENT" "$ADD_BLOCKED_PAIRS" "$ADD_BLOCKING"
  fi
  if [ "$CLOUD" -eq 1 ] && [ "$FOUND_LABEL" = absent ]; then
    post_link "the $BOARD_PENDING_LABEL label" "repos/$REPO/issues/$NUM/labels" \
      -f "labels[]=$BOARD_PENDING_LABEL"
  fi
  echo "wiring #$NUM  $URL"
fi

# Shared board half: both modes call these in the current shell.

ITEM_ID=""             # the item's node id, which the position write takes
ITEM_REST_ID=""        # its numeric REST id, which the single-item read takes
POSITION_DEGRADED=0    # 1 once GitHub has refused the position write (#14 KTD2)
ADD_PROVED_MEMBER=0    # 1 once item-add refused with "already exists", which proves membership

board_row_item() {
  # Prints the issue's "<node id>\t<numeric id>" from board rows $1, or nothing if it isn't a row.
  printf '%s\n' "$1" | awk -F'\t' -v n="$2" '$1 == n {print $3 "\t" $4; exit}'
}

take_item() {
  # Sets ITEM_ID and ITEM_REST_ID only when both are valid, so the caller's fallback runs otherwise.
  local node="${1%%	*}" id="${1#*	}"
  case "$node" in ''|null) return 1 ;; esac
  case "$id" in ''|*[!0-9]*) return 1 ;; esac
  ITEM_ID="$node"
  ITEM_REST_ID="$id"
}

board_membership_corroboration() {
  # Second query path (#14 KTD5): a hit proves membership; a miss is weak (shared lag) and never grounds a refusal.
  local reply
  [ -n "$ITEM_REST_ID" ] || return 1
  reply="$(gh_api "$PROJECT_PATH/items/$ITEM_REST_ID")" || return 1
  [ "$(printf '%s' "$reply" | jq -r --argjson n "$1" '.content.number == $n' 2>/dev/null)" = "true" ]
}

write_position() {
  # The one GraphQL call left: no REST route sets position (#14 KTD2). A 403 degrades position; else half-wired.
  if [ -z "$1" ]; then
    gh_api graphql -f query='mutation($p:ID!,$i:ID!){updateProjectV2ItemPosition(input:{projectId:$p,itemId:$i}){clientMutationId}}' \
      -f p="$PROJECT_ID" -f i="$ITEM_ID" >/dev/null && return 0
  else
    gh_api graphql -f query='mutation($p:ID!,$i:ID!,$a:ID!){updateProjectV2ItemPosition(input:{projectId:$p,itemId:$i,afterId:$a}){clientMutationId}}' \
      -f p="$PROJECT_ID" -f i="$ITEM_ID" -f a="$1" >/dev/null && return 0
  fi
  if gh_api_failed_with 403; then
    # An adopted issue already in the asked-for slot didn't move; leave its position to the read-back, not NOT SET.
    [ "$MODE" = adopt ] && [ -n "$ADOPT_IDX" ] && [ "$ADOPT_MOVED" -eq 0 ] && return 0
    POSITION_DEGRADED=1
    return 0
  fi
  half_wired "the board position write failed for #$NUM: $(gh_api_err)"
}

board_half() {
  # No arguments: the failure path prints the globals $NUM and $URL. Call in the current shell; it calls half_wired.
  local add_err="" after_item rows
  # Cloud mode never touches the board (#14 R10); returning here keeps the call site a bare line.
  [ "$CLOUD" -eq 1 ] && return 0
  # Use the pre-write listing's item for an issue already on the board; item-add refuses it.
  if [ "$MODE" = adopt ]; then
    take_item "$(board_row_item "$BOARD_ROWS" "$NUM")"
  fi
  if [ -z "$ITEM_ID" ]; then
    take_item "$(gh_api -X POST "$PROJECT_PATH/items" -f type=Issue -F id="$SELF_ID" \
      | jq -r '"\(.node_id)\t\(.id)"' 2>/dev/null)" \
      || add_err="$(gh_api_err)"
  fi
  # Auto-add can board a new issue first, making item-add refuse; find it in a fresh listing (unreadable is could-not-look).
  if [ -z "$ITEM_ID" ]; then
    rows="$(read_board "${BOARD_JSON}.2")" \
      || half_wired_unreadable "the board (project $PROJECT_NUMBER) could not be re-read to find the item for #$NUM"
    take_item "$(board_row_item "$rows" "$NUM")"
  fi
  # A 422 "already exists" proves membership while the listing lags; the issue's own projectItems carries the item.
  if [ -z "$ITEM_ID" ] && printf '%s' "$add_err" | grep -qF "Content already exists"; then
    ADD_PROVED_MEMBER=1
    take_item "$(gh_api graphql -f query='query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){issue(number:$n){projectItems(first:100){nodes{id databaseId project{id}}}}}}' \
      -f o="${REPO%%/*}" -f r="${REPO#*/}" -F n="$NUM" \
      | jq -r --arg p "$PROJECT_ID" '.data.repository.issue.projectItems.nodes[]? | select(.project.id == $p) | "\(.id)\t\(.databaseId)"' 2>/dev/null \
      | head -1)" \
      || { add_err="$(gh_api_err)"; half_wired_unreadable "#$NUM is already on the board (project $PROJECT_NUMBER), but its board item could not be read${add_err:+ ($add_err)}"; }
  fi
  [ -n "$ITEM_ID" ] || half_wired "the board (project $PROJECT_NUMBER) did not return an item id for #$NUM${add_err:+ ($add_err)}"

  if [ "$TOP" -eq 1 ]; then
    write_position ""
  else
    # Row from the pre-write listing, which the gate proved holds #$AFTER; no node id means unreadable, not absent.
    after_item="$(board_row_item "$BOARD_ROWS" "$AFTER" | cut -f1)"
    case "$after_item" in
      ''|null) half_wired_unreadable "the board item for #$AFTER could not be read, so #$NUM could not be positioned" ;;
    esac
    write_position "$after_item"
  fi
}

# Current shell: in a command substitution, half_wired's exit would kill only the subshell and the run would pass.
board_half

# >>> SHARED READ-BACK START
# An exit code is not evidence; both modes use this one implementation, and a test scans for a second copy.
DEPENDENCY_NUMBERS=""
read_dependency_numbers() {
  # Sets DEPENDENCY_NUMBERS or refuses as COULD NOT LOOK; call in the current shell so the refusal exits.
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

read_back_board() {
  # Board half of read_back: not yet visible, did not land and could not look are refused apart; only reads retry (KD1).
  local attempt=1 delay="$READBACK_DELAY"
  local in_listing=0 member_proven="$ADD_PROVED_MEMBER" position_ok=0 position_msg=""
  # Proof is latched: once the server has shown a wrong position, later listing silence doesn't unsettle it.
  local position_proven_wrong=0
  READBACK_WAITED=0

  while : ; do
    # A failed page, page cap or truncation is fatal, never a reason to keep waiting.
    BOARD2_ROWS="$(read_board "${BOARD_JSON}.2")" \
      || half_wired_unreadable "the board (project $PROJECT_NUMBER) could not be re-read to verify #$NUM"
    BOARD2_NUMS="$(printf '%s\n' "$BOARD2_ROWS" | cut -f1)"

    if printf '%s\n' "$BOARD2_NUMS" | grep -qxF -- "$NUM"; then
      in_listing=1
      member_proven=1
      # A degraded position was never written, so membership is the whole board check (#14 KTD8).
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
      # Listing silent: ask the store directly. A hit proves membership; position still needs the listing unless degraded.
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
    # No position was written, so membership is the whole verdict.
    [ "$member_proven" -eq 1 ] \
      || half_wired_absent "#$NUM is not on the board (project $PROJECT_NUMBER) after being added to it"
  else
    # Read the latch only if no attempt saw the right position: proven wrong, then silent, is not UNVERIFIED.
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

    # The landing index, kept where it is proven, so the move record never names an unverified position.
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
      # Highest DELAY the ceiling allows at this ATTEMPTS; stop doubling once past the ceiling to avoid 64-bit wraparound.
      warn_pow2=1; warn_i=1
      while [ "$warn_i" -lt "$READBACK_ATTEMPTS" ] && [ "$warn_pow2" -le "$READBACK_CEILING" ]; do
        warn_pow2=$(( warn_pow2 * 2 ))
        warn_i=$(( warn_i + 1 ))
      done
      warn_denom=$(( warn_pow2 - 1 ))
      [ "$warn_denom" -lt 1 ] && warn_denom=1
      warn_suggested=$(( READBACK_CEILING / warn_denom ))
      # Name a DELAY only if it helps; from ATTEMPTS=6 the quotient floors to 0.
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
}

read_back() {
  # No arguments: the failure path prints the globals $NUM and $URL. Call in the current shell.
  echo
  echo "READ-BACK"

  if [ "$CLOUD" -eq 1 ]; then
    echo "  board membership   not checked (cloud mode)"
    echo "  board position     not checked (cloud mode)"
  else
    read_back_board
  fi

  # Three REST reads (#14 KTD6), each shape-checked since an error reply extracts as empty; failures never offer delete.
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

  # The board-pending label keeps a cloud filing from being lost, so it must read back present (#14 R12).
  if [ "$CLOUD" -eq 1 ]; then
    LABEL_READ="$(issue_reply_label "$REL_JSON" "$BOARD_PENDING_LABEL")"
    [ "$LABEL_READ" != "BAD" ] \
      || half_wired_unreadable "the labels of #$NUM came back in an unrecognised shape — the issue reply carries no labels list"
    [ "$LABEL_READ" = "present" ] \
      || half_wired "$BOARD_PENDING_LABEL label — asked for, because cloud mode did not place #$NUM on the board; it reads back absent"
    printf '  %-19s%s\n' "$BOARD_PENDING_LABEL" "ok (present)"
  fi
}
# <<< SHARED READ-BACK END

# In the CURRENT SHELL, for the same reason board_half is.
read_back

# Record the move: read_back passed, so the position is proven; a degraded position records nothing (#14 KTD8).
if [ "$ADOPT_MOVED" -eq 1 ] && [ "$POSITION_DEGRADED" -eq 0 ]; then
  # Name each side's ordinal and what it follows; an ordinal alone means nothing once the board shifts.
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

  # Best effort: the wiring is verified, so a failed comment warns with pasteable text and exits 0, never offering delete.
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

# Clear the board-pending label (#14 R15, R16) once a local adopt has placed the issue; best effort, skipped if NOT SET.
if [ "$MODE" = adopt ] && [ "$CLOUD" -eq 0 ] && [ "$POSITION_DEGRADED" -eq 0 ] \
   && [ "$FOUND_LABEL" = present ]; then
  UNLABEL_RC=0
  gh_api -X DELETE "repos/$REPO/issues/$NUM/labels/$BOARD_PENDING_LABEL" >/dev/null \
    || UNLABEL_RC=$?
  UNLABEL_ERR="$(gh_api_err)"
  # Read it whatever the DELETE's exit: a call can fail after the server applied it.
  LABEL_AFTER_REMOVAL="$(issue_reply_label "$(gh_api "repos/$REPO/issues/$NUM")" "$BOARD_PENDING_LABEL")"
  if [ "$LABEL_AFTER_REMOVAL" = absent ]; then
    printf '  %-19s%s\n' "$BOARD_PENDING_LABEL" "removed"
  elif [ "$LABEL_AFTER_REMOVAL" = BAD ]; then
    # COULD NOT LOOK, never "still there": a second DELETE could remove a label re-added since.
    echo "########################################################################" >&2
    echo "## WARNING: #$NUM is PLACED, but whether its $BOARD_PENDING_LABEL label is gone is UNKNOWN" >&2
    echo "########################################################################" >&2
    echo "#$NUM is correctly wired and every relationship read back matching."   >&2
    echo "Nothing is half-wired and there is nothing here to undo. The label"     >&2
    echo "DELETE exited $UNLABEL_RC${UNLABEL_ERR:+ ($UNLABEL_ERR)}, and the read that would" >&2
    echo "confirm it did not come back as an issue. Check it by hand:"            >&2
    echo "  gh api repos/$REPO/issues/$NUM --jq '[.labels[].name]'"              >&2
    echo "########################################################################" >&2
  else
    echo "########################################################################" >&2
    echo "## WARNING: #$NUM is PLACED but its $BOARD_PENDING_LABEL label was NOT removed" >&2
    echo "########################################################################" >&2
    echo "#$NUM is correctly wired and every relationship read back matching."   >&2
    echo "Nothing is half-wired and there is nothing here to undo. Only the label" >&2
    echo "is left, still saying the issue needs placing."                         >&2
    if [ "$UNLABEL_RC" -ne 0 ]; then
      echo "  the label DELETE exited $UNLABEL_RC: ${UNLABEL_ERR:-(no output)}"   >&2
    else
      echo "  the label DELETE returned ok, but a fresh read of #$NUM did not show it gone" >&2
    fi
    echo "REMOVE IT BY HAND:"                                                     >&2
    echo "  gh api -X DELETE repos/$REPO/issues/$NUM/labels/$BOARD_PENDING_LABEL" >&2
    echo "########################################################################" >&2
  fi
fi

echo
DONE_VERB="$( [ "$MODE" = adopt ] && echo wired || echo created )"
if [ "$CLOUD" -eq 1 ]; then
  # Never "not on the board": it may be auto-added; say only that the run did not look (#14 R14).
  echo "#$NUM is $DONE_VERB and every relationship read back matching, but the board was not checked from the cloud. It may already be on it, at a spot nobody chose (sub-issues can be added to the bottom automatically). It carries the $BOARD_PENDING_LABEL label. $URL"
  # Loud, exit 0: every cloud write landed; placing needs the board, so the command is for a local session.
  echo "########################################################################" >&2
  echo "## BOARD NOT CHECKED                                                   #" >&2
  echo "########################################################################" >&2
  echo "Cloud mode does not read or write the board, so nothing has checked" >&2
  echo "where #$NUM sits on it, or whether it is there at all. It carries the" >&2
  echo "$BOARD_PENDING_LABEL label so it can be found. Place it from a local session," >&2
  echo "choosing --after <N> or --top there; the adopt run writes only what is" >&2
  echo "missing, reads everything back, and removes the label:" >&2
  reverify_command "(--after N | --top)" >&2
  echo "########################################################################" >&2
elif [ "$POSITION_DEGRADED" -eq 0 ]; then
  echo "#$NUM is $DONE_VERB and every relationship read back matching. $URL"
else
  echo "#$NUM is $DONE_VERB and every relationship read back matching, but its board position is NOT SET. $URL"
  # Loud, exit 0: every write landed; the position needs GraphQL, so the re-run is for a session that has it.
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
