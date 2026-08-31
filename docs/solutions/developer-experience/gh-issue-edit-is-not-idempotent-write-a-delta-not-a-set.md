---
title: "gh issue edit is not idempotent on relationships — write a delta, not a set"
date: 2026-08-24
category: developer-experience
module: scripts/file_issue.sh
problem_type: developer_experience
component: tooling
severity: high
applies_when:
  - "A script re-applies issue relationships to an issue that may already be partly wired"
  - "Writing an adopt, sync, or reconcile path that computes a desired state and writes it wholesale"
  - "Several relationship flags travel in one `gh issue edit` call"
  - "A relationship write exits non-zero and the state afterwards is being guessed"
  - "A plan's Open Questions ask whether one API call is idempotent"
tags:
  - gh-cli
  - github-issues
  - idempotence
  - file-issue-sh
  - delta-not-set
  - read-back
  - adopt-mode
related_components:
  - development_workflow
  - documentation
---

> Carried over from photo-consolidation's `docs/solutions/` on 2026-08-31, when this file's subject code (`file_issue.sh` and its tests) was extracted into this repo. Repo names, exact file paths, and command examples below may still say `photo-consolidation` or `tests/test_file_issue_*` from before the move -- the lesson is unchanged, the examples are historical.


# gh issue edit is not idempotent on relationships — write a delta, not a set

Re-adding a relationship that is already there does not quietly succeed. It fails
the whole call, for **both** kinds of relationship, including the parent — the one
nobody thinks to check.

## Context

`scripts/file_issue.sh` is the only supported way to put work on this project's
GitHub board. Adopt mode — `--adopt <N>` — takes an issue that already exists and
wires it to the four placement answers: a parent, what blocks it, what it blocks,
and where it sits on project 2. Its whole reason for existing is that issues on the
board are often *partly* correct already, so the tool has to finish the wiring
without refusing and without silently overwriting.

That makes the behaviour of `gh issue edit` on an already-present link the hinge of
the design. Measured against the live GitHub API on 2026-08-24 with
`gh version 2.98.0 (2026-08-20)`:

```
$ gh issue edit 234 --repo jffriend/photo-consolidation --add-blocked-by 233
failed to update https://github.com/jffriend/photo-consolidation/issues/234:
GraphQL: An error occurred while adding the blocking issue to the issue. Validation failed:
Target issue has already been taken (addBlockedBy)
failed to update 1 issue
exit=1

$ gh issue edit 234 --repo jffriend/photo-consolidation --parent 240
failed to update https://github.com/jffriend/photo-consolidation/issues/234:
GraphQL: Failed to add sub-issue #234 to parent #240. Issue may not contain duplicate
sub-issues (addSubIssue)
failed to update 1 issue
exit=1
```

Both exit 1. In both cases the link that was already there **survived intact** —
reading `blockedBy` back afterwards still returned `[233]`. This is a refusal, not
corruption. Nothing is lost; the call simply does not go through.

The measurement is recorded on issue #233.

## Guidance

**1. Read the current relationships first, then send a flag only for what is
genuinely missing.** A script that computes the full desired set and writes it
wholesale fails every single time it runs against an issue that is already partly
correct — which, for an adopt path, is most of them.

`scripts/file_issue.sh` reads all three relationships in the one `gh issue view`
its adopt gate already makes:

```bash
FOUND_PARENT="$(printf '%s' "$ADOPT_JSON" | jq -r '.parent.number // ""' | tr -d '[:space:]')"
FOUND_BLOCKED="$(printf '%s' "$ADOPT_JSON" | jq -r '[(.blockedBy.nodes // [])[].number] | sort | .[]' | tr '\n' ' ')"
FOUND_BLOCKING="$(printf '%s' "$ADOPT_JSON" | jq -r '[(.blocking.nodes // [])[].number] | sort | .[]' | tr '\n' ' ')"
```

and then builds `EDIT_ARGS` as a difference against what it found, in the adopt-mode
apply step:

```bash
  EDIT_ARGS=()
  [ -n "$PARENT" ] && [ "$PARENT" != "$FOUND_PARENT" ] && EDIT_ARGS+=(--parent "$PARENT")

  ADD_BLOCKED=""
  for n in $ASKED_BLOCKED; do
    in_set "$n" "$FOUND_BLOCKED" || ADD_BLOCKED="$ADD_BLOCKED,$n"
  done
```

**2. One already-present link fails the whole call, not just its own flag.**
`gh issue edit` accepts `--parent`, `--add-blocked-by` and `--add-blocking` together.
The parse succeeds; the apply does not. One rejected relationship takes the entire
invocation down with it, including the flags that would otherwise have landed. So
the delta must be exact — a single stale entry in it costs every other write in the
same call.

**3. If the delta is empty, issue no call at all — and still read the state back.**
Skipping the write is not the same as knowing the state is right. The read-back is
the only proof:

```bash
  if [ "${#EDIT_ARGS[@]}" -eq 0 ]; then
    echo "relationships     every one asked for is already there; no edit issued"
    echo "                  (the read-back below is the only proof of that)"
```

**4. Treat a non-zero exit as "state unknown, go read it back", never as "nothing
happened".** Flags are applied server-side one at a time, so a call that fails on
its third relationship may already have written the first two. `file_issue.sh` makes
the failed edit a warning rather than a fatal error for exactly this reason, and
lets the shared read-back establish the truth:

```bash
    if ! gh issue edit "$NUM" --repo "$REPO" "${EDIT_ARGS[@]}" >/dev/null; then
      # NOT fatal here, and NOT evidence that nothing landed. One rejected flag
      # fails the whole call server-side while the others may already have been
      # applied, so the read-back below is what establishes the true state.
      echo "WARNING: gh issue edit exited non-zero for #$NUM." >&2
```

**5. Ask the idempotence question about every relationship kind, not the one that
prompted the question.** The plan for this work
(`docs/plans/2026-08-24-001-fix-file-issue-readback-and-adopt-plan.md`, PR #238)
carried a step that said to measure `--add-blocked-by` against a scratch issue
before writing the apply step. It named that one flag and no other. `--parent`
turned out to fail the same way, and it was found only because the measurement was
run over the whole flag set rather than the one the plan asked about.

   The planning session had already been near this flag once. Its first draft wrote the
   parent link as `gh issue edit <parent> --add-sub-issue <child>`, which is
   inverse-relative and would have made the parent a child of the adopted issue. A
   reviewer caught the inversion against the installed binary and corrected it to
   `gh issue edit <issue> --parent <parent>`. So `--parent` was examined, tested, and
   fixed — for its *direction*. Nobody then asked whether it was idempotent, because
   the open question had been written about `--add-blocked-by` and stayed written that
   way. Testing one property of a flag is what makes it feel already checked.
   (session history)

## Why This Matters

The failure this would have caused is the exact failure adopt mode was built to
remove. Issue #233 exists because the filing tool covered creation only, so any
issue that already existed had to be wired by hand — and hand-wiring is what puts
half-correct relationships on the board in the first place. Had idempotence been
assumed rather than measured, every adopt of an already-partly-correct issue would
have exited 1. The tool would have refused precisely the issues it was written for,
and the refusal would have looked like a real problem with the issue rather than a
defect in the tool.

The "write the whole desired state" shape is the natural one to reach for. It is
simpler to write, it needs no read first, and it is correct against most APIs. Here
it is correct only on a completely unwired issue — which is the case a developer
tests with, and the case that almost never occurs in practice.

The exit code carries less information than it appears to. Exit 1 on this call means
"at least one flag was rejected". It does not mean the issue is unchanged, and it
does not say which flags landed. Any code that branches on that exit code without
reading the server back afterwards is guessing.

## When to Apply

- Any script that writes GitHub issue relationships to an issue it did not just
  create.
- Any adopt, sync, reconcile, or re-run path against an API where "already in the
  desired state" may be an error rather than a no-op — check, do not assume.
- Before writing code whose shape depends on an API being idempotent: run the call
  twice against a scratch object and read the state back. One minute of measurement,
  and the answer decides the design.
- When a plan's Open Questions name one flag or one endpoint: widen it to the whole
  family before answering. The unasked sibling behaved identically here.
- Whenever a relationship write exits non-zero. Read the state back before saying
  anything about what happened.

## Examples

**The set form, which fails.** Send everything the placement answers call for:

```bash
gh issue edit 234 --repo jffriend/photo-consolidation \
  --parent 240 --add-blocked-by 233 --add-blocking 236
```

Against an issue already blocked by #233, this exits 1 and `--parent` and
`--add-blocking` may or may not have been applied. Against an issue that is fully
correct already, it exits 1 while nothing at all was wrong.

**The delta form, which works.** Read first, subtract, send the remainder:

```
found:     parent #240, blockedBy [233], blocking []
asked for: parent #240, blockedBy [233], blocking [236]
delta:     --add-blocking 236
```

One flag goes out, it succeeds, and the read-back confirms all three.

**The empty delta.** When everything asked for is already there, the correct number
of API calls is zero and the correct number of read-backs is still one. `file_issue.sh`
prints this case explicitly rather than reporting a successful write it never made.

**What the failed calls did not do.** After both exit-1 calls above, `blockedBy` on
#234 still read `[233]`. Refusal, not corruption — which is what makes "go read it
back" a safe response rather than a recovery procedure.

## Related

- [`an-outdated-cli-looks-exactly-like-a-platform-limitation.md`](an-outdated-cli-looks-exactly-like-a-platform-limitation.md)
  — the reason these flags are used at all. `gh` 2.94.0 added them and the project
  hand-rolled the same operations through raw API calls for two months without
  noticing. That doc's rule — measure the environment, do not assume it — is the
  same rule applied one level down, to a flag's behaviour rather than its existence.
- [`an-empty-comparison-set-makes-a-guard-pass-while-proving-nothing.md`](../best-practices/an-empty-comparison-set-makes-a-guard-pass-while-proving-nothing.md)
  — the same habit of asking what a check concludes in the case nobody tested.
- [`a-blank-count-is-not-a-zero-and-a-running-scan-is-not-a-result.md`](../best-practices/a-blank-count-is-not-a-zero-and-a-running-scan-is-not-a-result.md)
  — an absence read as a fact. Here it is a non-zero exit read as "nothing was
  written".
- Issue #233 — records the measurement, and the unit that built adopt mode.
- Issue #236 — folding the write path onto native `gh` flags; blocks #233.
- `docs/plans/2026-08-24-001-fix-file-issue-readback-and-adopt-plan.md` (PR #238) —
  the plan, including the Open Question that asked about only one of the two flags.
- `docs/WORKFLOW.md` § 7, "Filing an issue goes through `scripts/file_issue.sh`" —
  the tool's contract.
