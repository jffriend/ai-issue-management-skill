---
name: file-issue
description: Put work on the {{BOARD_NAME}} — file a new issue, or wire an issue that already exists. Use this whenever an issue needs creating, whenever outstanding work has to go on the board, whenever a plan files or adopts its unit issues, and any time you are about to reach for the GitHub CLI to create an issue or put one on the board. Drives {{FILE_ISSUE_CMD}}, which is the only supported way to write to the board.
argument-hint: [what the issue is about, or "adopt <N>"]
---

<!--
  TEMPLATE — copy this file into your own repo's skill directory and fill in
  every {{PLACEHOLDER}} before using it. The placeholders and what belongs in
  them:

    {{BOARD_NAME}}       — a short name for your project's board, e.g. "the
                            Roadmap board" or "project board #1".
    {{FILE_ISSUE_CMD}}    — the exact command prefix your repo invokes the
                            engine with, e.g.:
                              bash scripts/file_issue.sh
                            (a thin wrapper that execs the submodule's
                            file_issue.sh with your --config baked in) or,
                            with no wrapper:
                              bash path/to/file-issue-tool/file_issue.sh --config path/to/your-config.json
    {{SHAPES_LIST}}       — the shape names and one-line meaning of each,
                            copied from the `shapes` list in your own
                            config.json (see config.example.json in this
                            repo). Photos' config has four:
                            `work`/`decision`/`your-run`/`plan-parent`;
                            yours may differ.
    {{CONVENTIONS_DOC}}   — the path to your own repo's conventions doc (the
                            place that documents issue-body shape, the
                            Design-line/plan-derived link convention if you
                            use one, and how ordering constraints get
                            recorded). Photos' is `docs/WORKFLOW.md`.
    {{DESIGN_LINE_BLOCK}} — include the "If the issue comes from a plan..."
                            paragraph below only if your config sets
                            `design_line_required: true`. Delete it (and the
                            tripwire paragraph under it) if your config
                            leaves plan-derivation unenforced.
    {{BODY_FIELDS_NOTE}}  — if your conventions doc requires specific fields
                            in an issue body per shape (Photos requires
                            `Impact if skipped` and `Size` for its
                            work/decision/your-run shapes), name them here.
                            Delete the paragraph if you have no such
                            convention.

  Delete this comment block once every placeholder below it is filled in.
-->

# Put work on {{BOARD_NAME}}

Every open item in this project is a GitHub issue on {{BOARD_NAME}}.
**{{FILE_ISSUE_CMD}} is the only supported way to put one there** — to create
a new issue, and to wire an issue that already exists.

## The one rule

Do not create or edit an issue, and do not touch the project board, with the
GitHub CLI directly. Not `gh issue create`, not `gh issue edit`, not any
`gh project` command. They write what you asked for and stop, leaving every
other relationship for a later step that may not come. That is not a style
preference — it is the reason this tool exists: a written rule alone did not
hold, in a session that had just read it.

This skill never writes to the board itself. It drives the engine, and the
engine does every write.

**One exception, named so it does not have to be guessed at.** Posting a
*comment* on an issue is permitted — `gh issue comment` — because a comment
creates no issue and touches no board field, and the audit step in Step 5
depends on it. The ban covers creating an issue, editing one, and touching the
project board.

## Before you comment: does the comment correct the body?

A comment may **add** — a measurement, a decision, progress. It may **not**
leave the body saying something the comment contradicts. **If what you are
about to write corrects the body — the order of steps, the command, the
target path, the done-when, or whether the work is still needed — rewrite the
body in the same action.**

Rewrite it to be correct and self-contained, put a dated note at the top of
the body saying it was rewritten and why, and leave the comments as the
record with *where they disagree with the body, the body wins.*

This engine cannot do that edit: adopt mode refuses `--body-file`, because an
issue that already exists has a body. So the body edit is a bare
`gh issue edit`, the one board write this skill sends you elsewhere for,
rather than the one it lets you skip. See {{CONVENTIONS_DOC}} for your repo's
narrow exception for a label-only correction, if it has one.

Why it matters: GitHub renders the body first and above the fold, so a
superseded instruction left standing in the body is the one in the reading
position — a comment correcting it is easy to miss.

Run every command from wherever {{FILE_ISSUE_CMD}} expects to be invoked from.

## Step 1 — answer the four placement questions, before anything is written

The engine refuses to write until all four are answered, and it is right to.
Ask the caller now, as questions, rather than discovering a refusal later.
**Every question must be answered explicitly. There is no default, and
leaving a flag off is not an answer.**

Each question has its own way of saying "nothing" — **the literal word `none`
is only an answer to the last two.** Getting this wrong costs a wasted preview
cycle, because the engine digit-validates the first two and refuses.

1. **Parent** — which plan does this belong to? Either the plan-parent issue
   number, or an explicit *no parent*. The word `none` is **not** accepted
   here.
2. **Position** — where on the board? Either the issue number it should sit
   behind, or *top of board*. There is no "none" at all: an unpositioned issue
   lands wherever the board dropped it, which is not a priority decision.
3. **Blocked by** — what must finish before this can start? Issue numbers, or
   the literal `none`.
4. **Blocks** — what must not start until this is done? Issue numbers, or the
   literal `none`. This is the direction sessions forget. "Do this before the
   upload" is recorded as *blocking* the upload.

{{DESIGN_LINE_BLOCK}}

**If the issue comes from a plan, and your config requires it, its body must
carry a `Design:` line** linking to the plan heading it implements. That is a
positive obligation, not just a tripwire: the engine decides whether an issue
is plan-derived by reading that line out of the body, so an omitted `Design:`
field does not satisfy the rule — it silently exempts the issue from it, and
the issue lands with no parent and no link back to the plan.

The tripwire is the other half of the same rule: when the body *does* carry
that line, a parent is required, and saying it has no parent is refused with
the `Design:` line quoted back. If you hit that refusal, supply the parent.
Deleting the line to make the refusal go away is the one response that makes
things worse.

{{CONVENTIONS_DOC}} has the body shape for each issue type and the anchor
pattern for the link.

## Step 2 — build the command

Two modes. Both answer the same four questions.

- **Create** a new issue: give it a title, a file holding its body, and its
  shape. The shape is one of {{SHAPES_LIST}}, and it sets the labels — see
  your config's `shapes` list for the exact names and labels.
- **Adopt** an issue that already exists: give `--adopt <N>` instead of the
  title, body and shape — the issue already has all three, and passing them
  is refused.

{{BODY_FIELDS_NOTE}}

**Do not reproduce a flag table here or from memory.** Read the tool's own
usage instead, which is always current:

```bash
{{FILE_ISSUE_CMD}} --help
```

The full rules, and why each question has no default, are in
{{CONVENTIONS_DOC}}.

**Adopt mode refuses rather than reconciles.** If the issue is closed, sits
under a different parent, or carries a blocked-by or blocks link this
invocation did not name, it stops before writing anything and prints the
exact `--remove-parent` / `--remove-blocked-by` / `--remove-blocking` command
that clears what it found. Note the shape of that: a link that already exists
must be *named in your answer* or explicitly cleared. A closed blocker still
counts as a link.

## Step 3 — preview it. This step is not optional

Run the command you built **with `--dry-run` appended**. It stops right
before the confirmation, having created and changed nothing.

```bash
{{FILE_ISSUE_CMD}} <the arguments you built> --dry-run
```

Then **show the caller that output verbatim.** Do not summarise it, do not
paraphrase the board neighbourhood, and do not describe the duplicate list in
your own words. The whole reason this step exists is that the caller has to
be able to spot a near-duplicate or a wrong position *themselves*, in the
tool's own words.

What the preview contains:

- the `gh` capability line
- **BOARD NEIGHBOURHOOD** — where the issue would land, with three issues
  either side
- **POSSIBLE DUPLICATES** — near-duplicate open titles. **Create mode only.**
  Adopt mode prints none, and that is correct rather than broken: an issue
  that already exists cannot be a new duplicate. Say so to the caller so its
  absence is never read as a failure.
- the **ABOUT TO CREATE** / **ABOUT TO WIRE AN EXISTING ISSUE** summary —
  parent, position, blocked by, blocks. In adopt mode the position line also
  names where the issue sits *today* and says plainly whether confirming will
  MOVE it.

If the board listing cannot be trusted, the engine stops rather than filing
against a partial board. A truncated board once hid an issue well enough that
a session filed a duplicate of it. Never work around that refusal.

## Step 4 — read the preview, then run it

The engine ends with `Create it? [y/N]` (or `Wire it? [y/N]` when adopting),
read from stdin. Under Claude Code stdin is never a terminal, so the answer
has to be supplied before the process starts.

**You may supply that answer yourself, once you have read the Step 3 output.**
That is a deliberate decision — see the note below on why it is safe. It is
not permission to skip the preview. Answering without having read the
neighbourhood and the duplicate list is confirming blind, and that is still
the failure this step exists to prevent.

So:

1. Run Step 3 and **actually read** the output — the board neighbourhood, the
   duplicate list, and the summary.
2. **Show it to the caller verbatim** before the real run, so the decision is
   visible to a human even though it did not wait for one.
3. Re-run **the identical command without `--dry-run`**, feeding `y` on
   stdin, and capture everything it prints. In practice that means piping a
   single `y` into the run:

```bash
printf 'y\n' | {{FILE_ISSUE_CMD}} <the same arguments, no --dry-run>
```

This is the one piece of invocation knowledge `--help` does not cover, which
is why it is written out here. If the answer never arrives the engine exits
with "Not confirmed. Nothing was created." — the failure is safe.

### Why answering it yourself is safe

The confirmation never enforced the engine's guards. The four placement
refusals, the plan-derived parent rule (if your config requires one), the
fatal truncated board, adopt refusing links the invocation did not name, and
the whole read-back all fire regardless of who answers `y`. It covers only
the two things the engine computes but cannot judge: **is this a duplicate**,
and **is this position right**.

Of those, only one is lossy. A wrongly created issue is visible on the board
and closed in one command. A wrongly moved priority slot is neither visible
nor recoverable unless the engine records the slot it came from.

**That is what makes self-confirmation safe here:** an adopt that moves an
issue comments on it naming both slots, written only after the read-back
proves the move landed. The slot it came from is recoverable from the issue's
own timeline.

### Stop and ask anyway when the preview says something you did not expect

Self-confirmation is not a reason to push past a surprise. Stop and put it to
the caller when the Step 3 output shows any of:

- a **POSSIBLE DUPLICATE** you cannot confidently rule out;
- a board position that does not match what was asked for;
- in adopt mode, **`this MOVES it`** when the intent was to leave the issue
  where it is — the move will be recorded, but a recorded mistake is still a
  mistake;
- anything the engine refuses. Never work around a refusal.

**If no answer comes back, do not file.** Print the exact command for a human
to run and stop there. Stopping is the correct outcome — self-confirmation
covers a preview that matches what was asked for, and it never covers one of
these. An unattended filing that waves past a surprise is worse than a
filing that waits.

### Compare the two runs before you trust the result

Phase two is a separate process. It reads the board again, and prints its own
neighbourhood, duplicate list and summary — which nobody read before the
answer was consumed. So compare that whole pre-gate block against the one
shown in Step 3.

If any of it differs, **say so loudly and treat the result as unconfirmed**:
the board moved between the two reads. The two differences most worth
catching are the ones a neighbourhood-only check misses — a duplicate someone
else filed in between, and, in adopt mode, the line saying whether confirming
MOVES the issue. Tell the caller exactly what changed and let them decide
whether to keep it.

## Step 5 — report what the server actually says

The engine reads every relationship back after writing and prints a
`READ-BACK` block: board membership, board position, parent, blocked-by,
blocks.

**Quote those lines.** Do not assert that the filing succeeded — an exit code
is not evidence that a write landed. Report position and dependencies as
set-and-read-back, in the tool's own words.

If it reports **HALF-WIRED** or **PARTLY WIRED**, do not retry blindly and do
not assume it is fine. The message names what is missing and what to do next;
follow it, and surface it to the caller.

**In adopt mode there is a third outcome, and the exit code does not carry
it.** When the issue moved, the engine prints a `move recorded` line. If
instead it prints `WARNING: the move LANDED but recording it FAILED`, the
wiring is correct and there is nothing to undo — but the slot the issue came
from is written down nowhere, and the run still exits 0 and still ends with
the success sentence. That is the one condition under which the permission in
Step 4 does not hold, so it cannot be allowed to pass silently. Post the
comment body the engine printed, with `gh issue comment`, then tell the
caller it failed and that you posted it by hand. Never treat a zero exit as
evidence the move record landed.

Then post the **audit comment** on the filed issue. With no human required in
the loop it is the only record that a filing was sound, so it names each
judgement rather than summarising them — mirroring the Step 4 stop list one
for one:

- who approved it, saying plainly when that was you rather than a human;
- the duplicate list, and the verdict on each entry, or `none found`;
- the position asked for, and the neighbourhood it landed in;
- in adopt mode, whether the summary said `this MOVES it`, and whether that
  was intended;
- whether the two pre-gate blocks were identical;
- then both runs' pre-gate output, verbatim. That comment is what keeps an
  unsound confirmation detectable afterwards instead of invisible, and now
  that no human has to be present it is the only thing that does. Use
  `gh issue comment` — this is the permitted exception named at the top,
  because a comment creates no issue and touches no board field.

## What this skill does not cover

Filing and wiring, only. Closing an issue whose work was removed, retitling
an issue whose unit was renamed, and re-anchoring a `Design:` link after a
renumbering are not covered here — see {{CONVENTIONS_DOC}} for how your repo
handles those, if it does. Do not assume this skill covers them because it
covers filing.

## What this skill must never do

- Write to the board by any route other than {{FILE_ISSUE_CMD}}.
- Supply the confirmation answer without the Step 3 preview having been run,
  shown to the caller verbatim, and quoted in the audit comment.
- Skip the `--dry-run` preview, or show it to the caller after the
  confirmation rather than before.
- Work around any refusal the engine raises. Every one of them was paid for.
- Restate the engine's flags from memory instead of reading its usage.
