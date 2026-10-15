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
                              bash path/to/ai-issue-management-skill/file_issue.sh --config path/to/your-config.json
    {{CONFIG_PATH}}       — the repo-relative path to your own config.json
                            (e.g. scripts/file-issue.config.json). Needed
                            even when {{FILE_ISSUE_CMD}} is a wrapper that
                            hides this path internally, because Step 3 reads
                            `human_review_required` from it directly. This
                            MUST be the same config.json {{FILE_ISSUE_CMD}}
                            itself loads — if a wrapper bakes in a different
                            or outdated --config path, Step 3 reads a value
                            that does not govern what the engine actually
                            enforces.
    {{SHAPES_LIST}}       — the shape names and one-line meaning of each,
                            copied from the `shapes` list in your own
                            config.json (see config.example.json in this
                            repo). The shipped default has three:
                            `work`/`bug`/`investigation`; yours may differ.
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
    {{BODY_FIELDS_NOTE}}  — the required body sections for each shape, copied
                            from your `.github/ISSUE_TEMPLATE/<shape>.md`
                            files (e.g. the shipped default's `work` shape
                            requires `What` / `How` / `Impact if skipped` /
                            `Done when`). Size is a project-board field, not
                            a body field — do not list it here.

  Delete this comment block once every placeholder below it is filled in.
-->

# Put work on {{BOARD_NAME}}

Every open item in this project is a GitHub issue on {{BOARD_NAME}}.
**{{FILE_ISSUE_CMD}} is the only supported way to put one there** — to create
a new issue, and to wire an issue that already exists.

## First: fix it here, or file it?

Before filing anything, ask whether the work belongs in this session instead.
**Small bugs, doc fixes, and similar small fixes in files this session is
already touching get fixed now, not filed.** A typo in a doc you are editing,
a wrong comment in a function you just changed, a broken link in a file you
have open: fix it and say so.

File an issue when the work is outside the files you are touching, is more
than a small fix, or needs a decision you cannot make here.

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
creates no issue and touches no board field, and Step 4 uses it to add
details to an issue that already covers the work. The ban covers creating an issue, editing one, and touching the
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
  your config's `shapes` list for the exact names and labels. Build the body
  file from `.github/ISSUE_TEMPLATE/<shape>.md`: read it, drop the leading
  HTML comment (it's addressed to a human using GitHub's web form, not to
  you), strip the YAML frontmatter block (everything between the two `---`
  lines), and fill in the remainder. If the frontmatter's `title:` carries a
  prefix (e.g. `'Decide: '`), start `--title` with that prefix too.
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

## Step 3 — run it, the way `human_review_required` says

**Read `human_review_required` from {{CONFIG_PATH}} first.** It is `true` or
`false`. Treat a missing key as `true`, and treat a config you cannot read
(missing file, invalid JSON, an unfilled placeholder) as `true`. A config you
cannot read cannot have turned review off.

The engine never asks for confirmation. A run without `--dry-run` writes.

### `false` — run it once

Run the command you built:

```bash
{{FILE_ISSUE_CMD}} <the arguments you built>
```

With no possible duplicates, this one run creates the issue, wires it, and
prints the read-back. Go to Step 5. If it exits 3, go to Step 4.

An adopt that moves an issue proceeds too. The engine records the slot it
came from in a comment on the issue once the read-back proves the move.

### `true` — a human approves a preview first

Run the command **with `--dry-run` appended**. It prints the board
neighbourhood, the possible duplicates (create mode only), and the summary,
and writes nothing.

```bash
{{FILE_ISSUE_CMD}} <the arguments you built> --dry-run
```

**Show the caller that output verbatim.** Do not summarise it. The caller has
to be able to spot a near-duplicate or a wrong position themselves, in the
tool's own words. In adopt mode, the position line says whether the run will
MOVE the issue.

Wait for a reply to that preview. A clearly affirmative reply is approval;
then run the same command without `--dry-run`. If the preview listed possible
duplicates and the caller approved anyway, add `--file-anyway`. Anything other
than a clear yes means don't file: give the caller the exact command to run
themselves and stop.

If the real run exits 3 because a new possible duplicate appeared since the
preview, show that output to the caller and wait again.

### Either setting

If the board listing cannot be trusted, the engine stops rather than filing
against a partial board. Never work around that refusal, or any other.

## Step 4 — exit 3: possible duplicates

A create run that finds possible duplicates prints them, creates nothing, and
exits 3. Read each match and judge it yourself. Do not stop the session for
it.

- **You are confident it is the same work.** File nothing. Add the new
  details as a comment on the existing issue with `gh issue comment`, and tell
  the caller which issue you commented on.
- **You are not sure.** File nothing. Tell the caller the matches by number
  and title, and offer to file anyway, which means re-running the same command
  with `--file-anyway`. Then carry on with the session's other work.
- **None of them is the same work.** Re-run the same command with
  `--file-anyway`.

Under `true`, the caller has already seen the matches in the preview; follow
their answer.

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
from is written down nowhere, and the run still exits 0. Post the comment body
the engine printed, with `gh issue comment`, then tell the caller it failed
and that you posted it by hand. Never treat a zero exit as evidence the move
record landed.

## What this skill does not cover

Filing and wiring, only. Closing an issue whose work was removed, retitling
an issue whose unit was renamed, and re-anchoring a `Design:` link after a
renumbering are not covered here — see {{CONVENTIONS_DOC}} for how your repo
handles those, if it does. Do not assume this skill covers them because it
covers filing.

## What this skill must never do

- Write to the board by any route other than {{FILE_ISSUE_CMD}}.
- File work that is a small fix in a file this session is already touching.
- Run without `--dry-run` under `human_review_required: true` before a human
  has approved the verbatim preview.
- Pass `--file-anyway` without having read every listed match.
- Work around any refusal the engine raises. Every one of them was paid for.
- Restate the engine's flags from memory instead of reading its usage.
