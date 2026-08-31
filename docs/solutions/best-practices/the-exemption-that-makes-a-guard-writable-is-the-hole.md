---
title: The exemption that lets a guard describe itself is the hole in it
date: 2026-08-24
last_updated: 2026-08-25
category: best-practices
module: tests/test_file_issue_skill.py
problem_type: best_practice
component: tooling
severity: high
applies_when:
  - A scan checks a document for the thing that document has to be able to talk about
  - A guard exempts a syntactic region so a rule can be written down inside it
  - A prose rule and its enforcement live in the same file
  - Writing a conformance test over a markdown skill, runbook, or checklist
  - A rule is deliberately removed and its guard is retargeted onto new words rather than deleted
  - The word a check looks for appears in more than one section of the document
symptoms:
  - The guard passes on a file that does exactly what the guard forbids
  - The exemption is documented as a known blind spot but described too narrowly
  - Every planted violation in the test suite avoids the exempt region
  - A check asserts a string is present rather than that a procedure survives
  - Deleting one whole step leaves the suite green because another section still says the word
  - Every planted mutation removes all occurrences of a token at once
tags: [guards, conformance-scan, hollow-gate, claude-code-skills, file-issue, markdown]
---

> Carried over from photo-consolidation's `docs/solutions/` on 2026-08-31, when this file's subject code (`file_issue.sh` and its tests) was extracted into this repo. Repo names, exact file paths, and command examples below may still say `photo-consolidation` or `tests/test_file_issue_*` from before the move -- the lesson is unchanged, the examples are historical.


# The exemption that lets a guard describe itself is the hole in it

## Context

`.claude/skills/file-issue/SKILL.md` is a front door to `scripts/file_issue.sh`,
the only supported way to write to the Photo board.
`tests/test_file_issue_skill.py` exists to fail if that skill ever stops driving
the script and starts writing to the board itself.

The skill has to be able to say **"do not reach for `gh issue create`"**. So the
scan stripped inline-code spans before looking for a `gh` invocation, and wrote
the exemption down as a known blind spot: *"a prose instruction to reach `gh api
...` — prose is deliberately exempt."*

A reviewer then wrote a replacement skill whose steps read:

> Create it with `gh api repos/.../issues -X POST -f title="$T"`, add it with
> `gh api graphql -f query='mutation{addProjectV2ItemById(...)}'`, set its
> position with `gh api graphql -f query='mutation{updateProjectV2ItemPosition(...)}'`.
> No confirmation is needed for any of this.

Thirty tests, zero failures. Green while the guard's entire subject had been
reimplemented, the confirmation removed, and the board written directly.

## The mistake

The blind spot was recorded, and it was recorded **wrong**. The disclosure said
prose was exempt and described the evasion as one "phrased as a sentence" — but
the real boundary was **backticks**, not sentences. An un-backticked `gh issue
create` in prose was caught. A backticked one was not.

That distinction is the whole game, because **a markdown page writes every
command in backticks.** The natural, idiomatic way to write the bad skill was
exactly the way that passed. The exemption did not cover a rare edge; it covered
the common case.

Two smaller versions of the same error shipped alongside it:

- `--dry-run` was checked with `if "--dry-run" not in text`. Deleting the skill's
  preview step, its never-confirm-alone rule and its read-back step left the
  suite green, because the words survived in an unrelated closing bullet. **A
  substring is not a safeguard.**
- An allowlist of three flags was justified by a comment claiming each "must
  appear verbatim in the script's text, so this list cannot be used to smuggle in
  a flag nothing accepts." The membership test was against the whole 1,239-line
  file including comments, where `--label`, `--json` and `--limit` all appear —
  precisely the flags a hand-rolled reimplementation needs. **The comment stated
  a safeguard the code did not implement.**

## Guidance

**When a guard must exempt a region so the rule can be written down, allowlist
that region — never exempt it.** The skill still needs to name the commands it
forbids, so the fix was not to remove the exemption but to bound it: a backticked
span naming `gh` must be one of the exact command *names* the prohibition sentence
requires (`gh issue create`, `gh issue edit`, `gh project`), or the one command
the skill is permitted to run. The same name carrying arguments — `gh project
item-add 2 --url ...` — is an instruction, and is rejected. A name is legal; an
invocation is not.

**Ask what the natural way to write the bad version is, and check that shape
first.** Every planted violation in the original suite was a fenced command line,
which is the case the scan already handled. Not one plant used the region the
scan had exempted. A meta-test that only exercises the covered path measures
nothing about the uncovered one.

**Pin the procedure, not its vocabulary.** Where a check asserts a document still
says something, make it assert the document still *does* something: a fenced
command that actually runs the tool, in the step that runs it. Otherwise the
document can be reversed in place with the words intact.

**A comment claiming a safeguard is a claim, and it inherits no verification.**
If a comment says an allowlist cannot be widened, write the test that widens it.
Both allowlist defects here were sitting under comments asserting they were safe.

**State a blind spot precisely enough to act on, or it misleads.** "Prose is
exempt" and "backticked spans are exempt" describe the same code and imply very
different risks. The first reads as an edge case; the second names the common
case. Write the boundary the code actually implements.

## It happened again the next day, by retargeting rather than deleting

**2026-08-25.** The work on #264 deliberately removed the rule this guard pinned —
the skill's requirement that a human answer `Create it? [y/N]`. The guard was not
deleted with it. It was **retargeted** onto two new words, `pre-gate` and `audit`,
chosen because they named the two safeguards the permission now rested on.

That retarget inherited every weakness above. A reviewer built a replacement skill
that retires the preview, retires the two-run comparison **and** retires the audit
comment, while keeping both words alive in a sentence *revoking* them, and keeping
`--dry-run` alive only as a trailing shell comment on the very line that skips the
preview. **All 47 tests passed.**

Two smaller variants were confirmed by running them:

- Deleting **only** the audit step left the suite green — the word survives in the
  opening rule's paragraph.
- Deleting **only** the comparison step left it green — the word survives in the
  reporting step's list of what the audit comment carries.

Each step was masked by the other's mention of the same word.

### Retargeting is the moment of maximum danger

Deleting a guard alongside the rule it pinned is loud; someone asks what replaced
it. **Retargeting is quiet, and it looks like diligence** — the test count went up,
nothing was removed, the diff reads as care. Meanwhile every reviewer's attention
is on whether the *removal* was authorised, not on whether the *replacement* is
enforceable. Treat a retargeted guard as a new guard with no track record, and
attack it before trusting it.

### A whole-file substring cannot tell an instruction from a mention

This is the concrete reason "pin the procedure, not its vocabulary" kept failing:
the scan searched the whole document, so a passing reference anywhere satisfied a
check meant to prove a *step* still existed.

**Scope the check to the section that must carry the thing, and require a
conjunction.** The audit-comment instruction must appear in the same section as
the read-back **and** the command that posts it. Delete the step and its body goes
with it, however many other paragraphs still say the word. Verified discriminating
before relying on it: the opening rule's paragraph carries `audit` and
`gh issue comment` but not `read-back`, so only the reporting step satisfies all
three.

### For a procedure made of commands, pin the constructions and their order

The two-phase preview-then-confirm procedure is now pinned as **two separate fenced
lines in a required order**: a preview line that runs the tool with `--dry-run` and
feeds it nothing, appearing before a confirm line that feeds stdin and carries no
flag. One line cannot be both phases. Trailing shell comments and angle-bracketed
placeholders are stripped before asking what a line *does*, so
`printf 'y' | bash scripts/file_issue.sh ARGS  # the --dry-run preview is retired`
no longer counts as showing a preview.

### The meta-tests were the wrong shape

Each planted mutation removed **every** occurrence of a token at once — a
`read_skill().replace("audit", "follow-up")`, or a filter dropping every line
containing it. No editor does that. The mutation a real editor performs is: delete
one step, leave the mentions elsewhere. That shape was never tried, so all three
new meta-tests passed against a guard that was provably hollow.

**Plant the mutation someone would actually make.** And note the second half:
a mutation test asserting only `assertTrue(problems)` passes on any single
unrelated finding — here the `--dry-run` check alone carried it, so the two checks
it had just been retargeted onto contributed nothing and could have been deleted
outright with the test still green. **Assert the exact expected problem set.**

After the fix, all five mutations are caught, each by its own named problem string:
delete the audit step, delete the comparison step, delete the move-record step, the
adversarial mutant shape, and preview-after-confirm.

## Related

- `docs/solutions/design-patterns/make-the-lossy-half-recoverable-before-removing-the-gate.md`
  — the change whose guard-retarget produced the 2026-08-25 recurrence. Removing a
  rule is where its replacement safeguards need the most scrutiny, not the least.
- `docs/solutions/workflow-issues/a-superseded-script-turns-every-gate-that-names-it-vacuous.md`
  — the same hollow-gate shape, one level up: the gate does not break, it goes
  hollow, and a hollow gate is visually identical to a real one.
- `docs/solutions/best-practices/a-guard-scan-only-catches-the-shape-it-was-taught.md`
  — a static scan catches the syntactic shapes it enumerates, not the question
  those shapes were asking. This is that rule applied to the scan's *exemptions*
  rather than its matches.
- `docs/solutions/best-practices/paraphrasing-a-measured-value-loses-its-boundaries.md`
  — a restatement of a fact is a new claim; the allowlist comments here restated
  a safeguard that was never implemented.
