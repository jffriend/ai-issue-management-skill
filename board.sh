#!/bin/bash
# Usage: bash board.sh --config config.json OUTFILE (either order). Reads the board over REST, one JSON array per page.
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

BASE="users/$OWNER/projectsV2/$PROJECT_NUMBER"

# The items endpoint's `fields` takes numeric field ids, not names (HTTP 400), so the Status id is looked up once.
fields=$(gh api "$BASE/fields?per_page=100") || { echo "QUERY FAILED reading the project's fields" >&2; exit 1; }
status_id=$(printf '%s\n' "$fields" \
  | jq -r -n 'input | if type == "array" then (map(select(.name == "Status"))[0].id // empty) else error("not a field list") end') \
  || { echo "QUERY FAILED reading the project's fields — the reply is not a field list" >&2; exit 1; }
query="per_page=100"
[ -n "$status_id" ] && query="$query&fields=$status_id"

: > "$OUT"; cursor=""; page=0
while :; do
  page=$((page + 1))
  if [ -z "$cursor" ]; then
    path="$BASE/items?$query"
  else
    path="$BASE/items?$query&after=$cursor"
  fi
  # -i exposes the Link header, the only source of the next cursor; --paginate gives no page count or cap.
  raw=$(gh api -i "$path") || { echo "QUERY FAILED on page $page" >&2; exit 1; }
  headers=$(printf '%s\n' "$raw" | awk '{sub(/\r$/, "")} /^$/ {exit} {print}')
  # A non-array body would count as zero rows, and a short page reads like a short board.
  printf '%s\n' "$raw" | awk 'inbody {print; next} {sub(/\r$/, "")} /^$/ {inbody=1}' \
    | jq -c -n 'input | if type == "array" then . else error("not an item array") end' >> "$OUT" 2>/dev/null \
    || { echo "QUERY FAILED on page $page — the reply is not a list of board items" >&2; exit 1; }
  next=$(printf '%s\n' "$headers" | grep -i '^link:' | tr ',' '\n' | grep 'rel="next"')
  [ -n "$next" ] || break
  cursor=$(printf '%s\n' "$next" | sed -n 's/.*[?&]after=\([^&>]*\).*/\1/p' | head -1)
  # A next link without a cursor must fail, not end the loop as a short board.
  [ -n "$cursor" ] || { echo "QUERY FAILED on page $page — its next-page link carries no cursor" >&2; exit 1; }
  [ "$page" -ge 20 ] && { echo "PAGE CAP HIT — pagination is not advancing" >&2; exit 1; }
done
# Self-check: rows != distinct issues means the cursor didn't advance and a page repeated.
rows=$(jq -s '[.[][]] | length' "$OUT")
uniq=$(jq -s '[.[][].content.number] | unique | length' "$OUT")
echo "pages=$page rows=$rows distinct=$uniq" >&2
[ "$rows" = "$uniq" ] || { echo "TRUNCATED BOARD — rows != distinct" >&2; exit 1; }
