#!/bin/bash
# scripts/board.sh — run with: bash scripts/board.sh /tmp/board.json
set -u
OUT="$1"; : > "$OUT"; cursor=""; page=0
while :; do
  page=$((page + 1))
  if [ -z "$cursor" ]; then args=(); else args=(-f "cursor=$cursor"); fi
  out=$(gh api graphql -f query='
query($cursor: String) {
  user(login: "jffriend") {
    projectV2(number: 2) {
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
