#!/bin/bash
# board.sh — run with: bash board.sh --config config.json /tmp/board.json
#
# --config and the output path may come in either order. --config names the
# JSON file that supplies OWNER and PROJECT_NUMBER (see config.example.json);
# this script no longer hardcodes a login or a project number.
set -u

CONFIG=""
OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --config) CONFIG="${2-}"; shift 2 ;;
    *)        OUT="$1"; shift ;;
  esac
done

[ -n "$CONFIG" ] || { echo "ERROR: --config is required, naming the JSON config file (owner, project_number)." >&2; exit 1; }
[ -f "$CONFIG" ] || { echo "ERROR: --config names a file that does not exist: $CONFIG" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required to read --config and was not found on PATH." >&2; exit 1; }
jq -e . "$CONFIG" >/dev/null 2>&1 || { echo "ERROR: --config $CONFIG is not valid JSON." >&2; exit 1; }
[ -n "$OUT" ] || { echo "ERROR: an output path is required." >&2; exit 1; }

OWNER="$(jq -r '.owner // empty' "$CONFIG")"
PROJECT_NUMBER="$(jq -r '.project_number // empty' "$CONFIG")"
[ -n "$OWNER" ] || { echo "ERROR: config $CONFIG is missing required field: owner" >&2; exit 1; }
case "$PROJECT_NUMBER" in
  ''|*[!0-9]*) echo "ERROR: config $CONFIG is missing or has a non-numeric project_number (got: ${PROJECT_NUMBER:-<empty>})." >&2; exit 1 ;;
esac

: > "$OUT"; cursor=""; page=0
while :; do
  page=$((page + 1))
  if [ -z "$cursor" ]; then
    args=(-f "owner=$OWNER" -F "project=$PROJECT_NUMBER")
  else
    args=(-f "owner=$OWNER" -F "project=$PROJECT_NUMBER" -f "cursor=$cursor")
  fi
  out=$(gh api graphql -f query='
query($owner: String!, $project: Int!, $cursor: String) {
  user(login: $owner) {
    projectV2(number: $project) {
      items(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          content {
            ... on Issue {
              number title state
              blockedBy(first: 20) { nodes { number state } }
            }
          }
        }
      }
    }
  }
}' "${args[@]+"${args[@]}"}") || { echo "QUERY FAILED on page $page" >&2; exit 1; }
  echo "$out" >> "$OUT"
  hn=$(echo "$out" | jq -r '.data.user.projectV2.items.pageInfo.hasNextPage')
  cursor=$(echo "$out" | jq -r '.data.user.projectV2.items.pageInfo.endCursor')
  [ "$hn" = "true" ] || break
  [ "$page" -ge 20 ] && { echo "PAGE CAP HIT — pagination is not advancing" >&2; exit 1; }
done
# Self-check: rows must equal distinct issues. If they differ, the cursor never advanced
# and the same page was fetched repeatedly — the board you are reading is not the board.
rows=$(jq -s '[.[].data.user.projectV2.items.nodes[]] | length' "$OUT")
uniq=$(jq -s '[.[].data.user.projectV2.items.nodes[].content.number] | unique | length' "$OUT")
echo "pages=$page rows=$rows distinct=$uniq" >&2
[ "$rows" = "$uniq" ] || { echo "TRUNCATED BOARD — rows != distinct" >&2; exit 1; }
