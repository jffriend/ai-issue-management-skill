# Day-to-Day Usage

**Get an issue onto the board, either by creating it fresh or by wiring up one that already exists.**

Everything here runs through `file_issue.sh`. Both of its modes — create and adopt — ask the same four placement questions. A run without `--dry-run` writes; there is no confirmation prompt.

## The two modes

**Choose create when the issue doesn't exist yet, and adopt when it does.**

### Create

Create mode files a brand-new issue and wires it onto the board in one step. You supply:

* A **title**.
* A file holding the issue **body** (`--body-file`).
* A **shape** (`--shape`) — one of the names listed in your config's `shapes` list. This sets which labels the issue gets.
* The four placement answers, described below.

```bash
bash file_issue.sh --config config.json \
    --title "..." --body-file body.md --shape work \
    (--parent N | --no-parent) \
    (--after N | --top) \
    (--blocked-by N,N | --blocked-by none) \
    (--blocks N,N | --blocks none) \
    [--dry-run] [--file-anyway]
```

### Adopt

Adopt mode wires up an issue that already exists (`--adopt N`) to the same four placement answers, without creating anything new. Because the issue already has a title, a body, and a shape, adopt refuses `--title`, `--body-file`, and `--shape` outright.

```bash
bash file_issue.sh --config config.json --adopt 123 \
    (--parent N | --no-parent) \
    (--after N | --top) \
    (--blocked-by N,N | --blocked-by none) \
    (--blocks N,N | --blocks none) \
    [--dry-run]
```

Adopt **refuses rather than reconciles**. If the issue is closed, already sits under a different parent, or already carries a `blocked-by` or `blocks` link this invocation didn't name, the run stops and prints the exact `gh api -X DELETE ...` command that would clear the contradiction. It never silently overwrites a placement decision someone already made.

Board position is the one exception. All four answers are mandatory, so adopt always names a position and moves the issue there — but the preview shows the slot the issue holds today next to the slot it's headed for, so the cost of the move is visible in the run's output. Once the move is verified, a comment on the issue records the slot it came from and the slot it went to, so the move stays recoverable afterward.

## The four placement answers

**Every issue on the board answers the same four questions, and none of them has a silent default.**

| Question | Flag | Real "none" value? |
|---|---|---|
| Which plan parent does it hang under? | `--parent N` or `--no-parent` | No |
| Where does it sit in priority order? | `--after N` or `--top` | No |
| What must finish before it can start? | `--blocked-by N,N` or `--blocked-by none` | Yes — the literal word `none` |
| What must not start until it's done? | `--blocks N,N` or `--blocks none` | Yes — the literal word `none` |

This is worth stating precisely, because the rule isn't the same for all four. **`blocked-by` and `blocks` accept the literal word `none` as a real answer**, and there's no such word for parent or position.

Parent takes either a real issue number or the explicit `--no-parent` flag — there's no `--parent none`. Position always needs a real target: either `--after N` naming the issue it goes after, or `--top` for the front of the queue. There's no equivalent of "no position." The one exception is cloud mode, where the board can't be seen: there the position answer is `--position-later`, and `--after` and `--top` are refused (see below).

All four flags are required either way. Leaving one blank isn't accepted as an answer — a missing answer stops the run and tells you exactly which flag to add.

## Possible duplicates stop a create run (`--file-anyway`)

**A create run that finds open issues with a similar title prints them, creates nothing, and exits with code 3.**

Read the matches. If one of them is the same work, add your details to it as a comment instead of filing. If none of them is, run the same command again with `--file-anyway`, and it files. Every other refusal exits with code 1. Adopt mode has no duplicate check, so it refuses `--file-anyway`.

## Preview without writing (`--dry-run`)

**Pass `--dry-run` to see exactly what would happen, with nothing created and nothing changed.**

Both modes support it, whatever `human_review_required` is set to. When you pass `--dry-run`, the run stops right after showing you:

1. The **board neighborhood** — the issues around the position you named, so you can see the ordering context you're placing this issue into.
2. **Possible duplicates** — create mode only, since adopt already points at a specific existing issue. This lists open issues with a similar title, so you can catch a refile before it happens.
3. A **summary** — what would be written, including (for adopt) the board slot the issue holds today next to the slot it would move to.

Nothing is created and nothing is changed at this point. Run the same command without `--dry-run` once the preview looks right. With `human_review_required` set to `true` (the default), the skill always previews first and waits for a person to approve.

## Filing from a cloud session (cloud mode, `needs-board`)

**A Claude Code cloud session can file and adopt issues, but it can't touch the project board. The issue is labelled `needs-board` and placed later from a local session.**

The cloud session's GitHub proxy refuses the board itself, not only GraphQL. So the tool runs in **cloud mode** there. It turns on by itself when the session sets `CLAUDE_CODE_REMOTE=true`, or with `--no-board` in any session. A board read that fails never turns it on: in a local session that still stops the run.

In cloud mode:

- The position answer is `--position-later`. `--after` and `--top` are refused, because nothing could check them.
- The run creates or adopts the issue, checks for duplicates, writes the parent and blocking links, and labels it `needs-board` (in the create itself, or added on adopt if it's missing).
- It reads all of that back. The two board lines say `not checked (cloud mode)`.
- It exits 0 and ends by saying the issue is NOT on the board yet, with the local adopt command that places it.
- `--dry-run` shows the duplicate check and the summary. There's no board neighborhood.

```bash
bash file_issue.sh --config config.json \
    --title "..." --body-file body.md --shape work \
    --no-parent --position-later --blocked-by none --blocks none
```

To place a `needs-board` issue, run adopt from a local session with a real position (`--after N` or `--top`). Once the position reads back, adopt removes the `needs-board` label and prints `needs-board        removed`. If the removal fails, a warning prints the `gh api -X DELETE` command to finish it by hand; the placement stands either way.

## Where only GraphQL is refused (`board position NOT SET`)

**Filing works where GitHub's GraphQL API is refused, except for setting the board position.**

Every call the tool makes goes over GitHub's REST API, with one exception: moving an issue to its board position. GitHub has no REST route for that, so it still uses GraphQL. This section is for a session that reaches the board over REST but not GraphQL. A Claude Code cloud session is refused the whole board, so it uses cloud mode instead.

When the position write is refused (HTTP 403), the run still creates the issue, adds it to the board, writes its parent and blocking links, and reads all of them back. It exits 0. The read-back shows:

```
  board position     NOT SET (GitHub refused the position write; see the notice below)
```

The issue sits wherever the board put it, usually at the bottom. A `BOARD POSITION NOT SET` notice prints an adopt command. Run that command from a local session, where GraphQL works, and it moves the issue to the position you asked for. It re-checks every other relationship and writes nothing that is already there.

No move comment is written when the position is not set, because the issue did not move. The local adopt run that places it records its own move.

Any 403 on the position write is treated this way, including one caused by a token without project access or a rate limit. The notice is loud on purpose.

## Where the full step-by-step procedure lives

**`SKILL.template.md`, filled in for your repo, is the authority on the exact procedure an agent should follow.**

This page covers what the two modes do and what they ask for. For the full agent-driven sequence — deciding whether to file at all, when to preview, and what to do with possible duplicates — see your repo's filled-in copy of `SKILL.template.md`. Each script's `--help` output also lists the current flag set.
