---
title: When empty is a legal answer, a guard must check shape, not emptiness
date: 2026-08-24
category: best-practices
module: scripts/file_issue.sh
problem_type: best_practice
component: tooling
severity: critical
applies_when:
  - "A guard compares a parsed reply against an expected value, and the expected value may legitimately be empty"
  - "A check treats non-empty output as evidence the reply is usable"
  - "Field extraction runs over a reply whose shape was never validated"
  - "A tool's exit status is discarded because its stdout was inspected instead"
  - "Reviewing a guard whose most common input is also its least tested one"
tags:
  - guard-design
  - vacuous-truth
  - shape-validation
  - read-back
  - silent-pass
  - gh-cli
related_components:
  - development_workflow
---

> Carried over from photo-consolidation's `docs/solutions/` on 2026-08-31, when this file's subject code (`file_issue.sh` and its tests) was extracted into this repo. Repo names, exact file paths, and command examples below may still say `photo-consolidation` or `tests/test_file_issue_*` from before the move -- the lesson is unchanged, the examples are historical.


# When empty is a legal answer, a guard must check shape, not emptiness

## Context

`scripts/file_issue.sh` writes an issue's relationships to GitHub and then reads
every one of them back, because an exit code is not evidence that a write landed.
The read-back fetches parent, blocked-by and blocks in one call and compares each
against what was asked for.

It guarded that reply with a single test — is the output non-empty:

```bash
REL_JSON="$(gh issue view "$num" --repo "$REPO" --json parent,blockedBy,blocking)"
[ -n "$REL_JSON" ] || half_wired_unreadable "...could not be read back at all"
```

Feed it a reply that is well-formed, non-empty, and simply not the reply it expected
— `{"message":"Not Found"}` — and all three field extractions yield empty strings.
Against the commonest filing shape of all, `--no-parent --blocked-by none
--blocks none`, the expected values are *also* empty. Empty equals empty, three
times. The run printed

```
  parent             ok (none)
  blocked-by         ok (none)
  blocks             ok (none)
```

and exited 0, having verified nothing whatsoever. Reproduced against the script's own
test harness by pointing the read-back's fake response at that JSON.

The script's exit status was never consulted either. The only signal it consumed was
that stdout was not empty.

## Guidance

**1. Non-empty is not well-formed.** These are separate claims. A reply can arrive
intact, parse cleanly, and contain none of the fields the comparison reads. Every
extraction then returns the parser's "absent" value, and the guard compares those
absences against whatever it expected.

**2. When empty is a legal answer, emptiness cannot be the refusal.** This is what
separates this failure from its sibling,
[`an-empty-comparison-set-makes-a-guard-pass-while-proving-nothing.md`](an-empty-comparison-set-makes-a-guard-pass-while-proving-nothing.md).
There, an empty comparison set is *always* wrong, so refusing on emptiness is the
whole fix. Here an issue genuinely may have no parent and no blockers — empty is a
correct, common answer — so a guard that refuses on empty would refuse most real
filings. The two cases are indistinguishable by content. The only thing that
separates them is whether the reply had the right **shape**, so that is what has to
be checked:

```bash
[ "$REL_RC" -eq 0 ] || half_wired_unreadable "...gh exited $REL_RC"
[ -n "$REL_JSON" ] || half_wired_unreadable "...could not be read back at all"
[ "$(printf '%s' "$REL_JSON" | jq -r 'has("parent") and has("blockedBy") and has("blocking")' 2>/dev/null)" = "true" ] \
  || half_wired_unreadable "...came back in an unrecognised shape"
```

Ask of any comparison: *if the reply were the wrong shape, would both sides extract
to the same value?* If yes, shape validation is load-bearing and emptiness checking
is not enough.

**3. Consume the exit status as well as the output.** Inspecting stdout is not a
substitute for asking whether the command succeeded. Both are cheap; neither implies
the other.

**4. Look for the correct pattern already in your own file.** The same script's adopt
pre-fetch validated its reply properly the whole time, a few dozen lines from the
defect:

```bash
if [ -z "$(printf '%s' "$ADOPT_JSON" | tr -d '[:space:]')" ] \
   || [ "$(printf '%s' "$ADOPT_JSON" | jq -r 'has("state")' 2>/dev/null)" != "true" ]; then
```

Two reads of the same endpoint, in one file, written days apart, and only one of them
checked what came back. When a file already contains the right shape of check, the
cheapest review question is whether every comparable site uses it.

**5. The commonest input is the dangerous one.** The bug was invisible precisely on
the filing shape used most often. A test suite written around the interesting cases —
a real parent, real blockers — populates both sides of every comparison and never
reaches the state where both are empty. The all-`none` case looks too trivial to test,
and it is the only case where this defect shows.

## Why This Matters

This guard exists because the tool it protects had already produced four false alarms
on correctly wired issues, each advising a deletion that would have destroyed correct
work. The whole point of hardening it was to stop it lying. A shape hole in the
hardened version means the guard can now lie in the opposite and worse direction —
reporting success on an issue it never checked — and reports it in the same words it
uses when everything genuinely landed.

Nothing in the ordinary signal path distinguishes the two. Exit code 0. Three `ok`
lines. A read did happen and a comparison did run. The output of a guard that verified
three relationships and the output of a guard that verified nothing are byte-identical.

The path to it was not carelessness. The emptiness check was added deliberately, as a
hardening step, by someone who had the sibling learning in view. It guards the case
where the reply is *absent*. The case where the reply is *present and wrong* is one
step further out, and the check that catches the first reads as though it catches
both.

## When to Apply

Any guard that parses a reply and compares extracted fields, where the expected value
may legitimately be empty, absent, null, or zero. The question to ask of each:

- If this reply arrived with the wrong shape, what would each extraction return?
- Is that value distinguishable from a legitimate answer?
- If not, what validates the shape?

In this project that includes every read-back in `scripts/file_issue.sh`, and applies
to any code reading a JSON API through a field extractor — the extractor is designed
to return "absent" quietly, which is exactly what makes it dangerous as the sole input
to a comparison.

## Examples

**The reply that passes the emptiness check and defeats the comparison:**

```json
{"message":"Not Found"}
```

Non-empty. Valid JSON. Carries no `parent`, `blockedBy` or `blocking`. Every
extraction returns empty; every comparison against a `none` answer succeeds.

**The test that catches it** — note it asserts on the wrong-shape case specifically,
which no other test in the suite covered:

```python
def test_a_reply_without_the_three_fields_is_not_a_pass(self):
    h = Harness(
        "**Design:** none\n",
        boards=[PRE_BOARD, self.BOARD_AFTER],
        responses=override(create_responses([], []),
                           "--json parent,blockedBy,blocking",
                           stdout=json.dumps({"message": "Not Found"})),
    )
    r = h.run(*full_args(h.body_file), "--no-parent", "--after", "101",
              stdin="y\n")
```

**Why this is a could-not-look, not a did-not-land.** A read that failed says nothing
about whether the write succeeded, so its refusal must not offer to delete anything.
All three of the new checks route to the unreadable refusal, which names the
re-verification command instead.

## Related

- [`an-empty-comparison-set-makes-a-guard-pass-while-proving-nothing.md`](an-empty-comparison-set-makes-a-guard-pass-while-proving-nothing.md)
  — the sibling. There the comparison set is empty and refusing on emptiness is the
  fix; here empty is a legal answer, so shape is the only thing left to check. A guard
  can have either failure, both, or neither.
- [`a-guard-scan-only-catches-the-shape-it-was-taught.md`](a-guard-scan-only-catches-the-shape-it-was-taught.md)
  — the same lesson about a scanner rather than a comparison.
- [`../developer-experience/gh-issue-edit-is-not-idempotent-write-a-delta-not-a-set.md`](../developer-experience/gh-issue-edit-is-not-idempotent-write-a-delta-not-a-set.md)
  — the other learning from the same work, on the write side of the same tool.
- [`../workflow-issues/skipping-the-skills-costs-what-the-skills-catch.md`](../workflow-issues/skipping-the-skills-costs-what-the-skills-catch.md)
  — this defect was found by an independently dispatched adversarial reviewer, not by
  reading the diff. Seven other reviewers on the same change did not find it.
