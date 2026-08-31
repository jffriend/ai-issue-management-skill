---
title: Make the lossy half recoverable before you remove the gate over it
date: 2026-08-25
category: design-patterns
module: scripts/file_issue.sh
problem_type: design_pattern
component: tooling
severity: high
applies_when:
  - Removing a human confirmation, approval step, or manual gate from a tool
  - Deciding whether an automation may act unattended
  - A gate is defended as "the safety check" without anyone checking what it enforces
  - A tool performs one operation that cannot be undone or noticed afterwards
tags:
  - gates
  - confirmation
  - reversibility
  - automation
  - sequencing
  - file_issue
---

> Carried over from photo-consolidation's `docs/solutions/` on 2026-08-31, when this file's subject code (`file_issue.sh` and its tests) was extracted into this repo. Repo names, exact file paths, and command examples below may still say `photo-consolidation` or `tests/test_file_issue_*` from before the move -- the lesson is unchanged, the examples are historical.


## Context

`scripts/file_issue.sh` ended with `Create it? [y/N]`, and the `/file-issue` skill
forbade answering it without a human saying yes in the conversation first. That cost a
round trip on every filing. The question was whether it could be dropped.

The tempting arguments are both wrong. "It is the safety check, so it stays" assumes the
gate enforces something. "It costs a round trip every time, so it goes" assumes it
enforces nothing. Neither had been checked.

## Guidance

**Do not argue about the gate. Enumerate what it actually enforces, then ask which of
the remainder is lossy.**

Four steps, in order.

**1. List every guard and ask which ones the gate is load-bearing for.** Measured against
the script rather than assumed: the four mandatory placement answers, the plan-derived
parent rule, the fatal truncated-board refusal, adopt's refuse-rather-than-reconcile
behaviour, and the entire read-back **all fire regardless of who answers `y`**. They are
argument-gate and post-write checks. The confirmation enforced none of them.

**2. Isolate what only the gate covered.** Here, exactly two judgements the script can
compute but cannot judge: *is this a duplicate*, and *is this position right*.

**3. Of those, ask which is lossy — irreversible AND invisible afterwards.** Both
properties are required. A wrongly created issue is irreversible-ish but highly visible,
and closing it is one command. A wrongly moved board position was neither recoverable nor
noticeable: nothing kept the previous slot and nothing named it. One of two.

**4. Make that one recoverable. Then, and only then, remove the gate.** Adopt now comments
on the issue naming both slots, written only after the read-back proves the position
landed.

### The ordering is the deliverable, not housekeeping

The trace shipped in one commit and the permission in the next, and the commit order was
checked as a gate in the plan's verification contract. Reversed, there is a window — however
short — in which an unattended run can perform the lossy operation with neither a human
watching nor a record afterwards. That window is the exact hole the work exists to close,
so opening it in the middle of closing it is not a technicality.

This is why "one PR that does both" is the wrong shape even when both halves land the same
day. Two commits in sequence make the ordering reviewable; one commit makes it unfalsifiable.

### Give the permission a named expiry condition

The skill states, in the step that grants it, what the permission depends on:

> That is fixed in the script, and the fix is what this permission rests on … If that ever
> stops being true, this permission stops being justified.

A permission whose justification is written down can be re-evaluated when the ground moves.
One granted with no stated condition silently outlives its reason.

**Then check the condition is observable.** Review caught that the move record is
best-effort: when the comment fails to post, the script warns and still exits 0, because
the wiring genuinely landed. So the condition could fail while every success signal stayed
green. A named condition that nothing checks is a comment, not a guarantee — the tool now
prints a distinct warning and the skill instructs the caller to look for it and post the
record by hand.

## Why This Matters

The default move when a gate is questioned is to keep it, because keeping it feels safe and
removing it needs an argument. That default is expensive and, worse, imprecise: it charges
a permanent cost for every operation in order to watch one of them.

The default in the other direction — remove it because it is annoying — is how a lossy
operation becomes silent.

Enumerating what the gate enforces is what makes the decision small. In this case a gate
that felt like the safety net turned out to enforce nothing at all; the whole question
reduced to one operation, and that operation needed a comment, not a human.

**Recording beats watching.** Requiring a person to be present at the moment a priority slot
is overwritten does not make it recoverable; it only makes it witnessed, and only when
someone is actually looking. A durable record makes it recoverable whether anyone was
watching or not, and costs one API call instead of a round trip per filing.

## When to Apply

- Any proposal to remove, weaken, or automate past a confirmation or approval step.
- Any decision about whether an agent may act unattended.
- When someone defends a gate as "the safety check" — that is the moment to enumerate.
- When someone proposes removing one because it is slow — same moment, same enumeration.

**Where this does not apply.** This is about a gate over an operation whose blast radius is
recoverable in principle. The issue tracker is not the photo library. Nothing here licenses
removing a confirmation in front of an irreversible operation on irreplaceable data — see
`../workflow-issues/match-rigor-to-lifespan-and-blast-radius.md` for that calibration, and
`CLAUDE.md`'s non-negotiable safety rules, which are not subject to this reasoning.

## Examples

The enumeration, written out as it was decided:

| What | Fires without the gate? | Lossy? |
|---|---|---|
| Four mandatory placement answers | yes | — |
| Plan-derived parent rule | yes | — |
| Truncated-board refusal | yes | — |
| Adopt refuses unnamed links | yes | — |
| Read-back of every relationship | yes | — |
| **Is this a duplicate?** | **no — gate only** | no: visible, closed in one command |
| **Is this position right?** | **no — gate only** | **YES: irreversible and invisible** |

One cell drove the whole design.

The record the fix produces:

```
Moved from position 7 (following #257) to position 9 (following #256).
```

Each side names what it follows, because a bare ordinal stops meaning anything once the
board shifts under it.

## Related

- `../workflow-issues/input-gated-scripts-cannot-be-driven-by-claude-code.md` — the
  constraint this was designed against. Its split-the-roles guidance is the right default;
  this is the documented case where a gate was lifted instead, and the conditions that made
  that safe.
- `../workflow-issues/match-rigor-to-lifespan-and-blast-radius.md` — where the "the tracker
  is not the library" half of the reasoning comes from.
- `../best-practices/the-exemption-that-makes-a-guard-writable-is-the-hole.md` — the
  replacement safeguards for a removed rule need their own enforcement, and getting that
  wrong is how this nearly shipped hollow.
