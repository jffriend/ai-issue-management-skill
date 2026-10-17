# Claude Code Instructions — AI Issue Management Skill

## Project

A config-driven guardrail for putting work on a GitHub project board safely:
refuse-until-answered placement questions (parent, position, blocked-by,
blocks), a board-neighborhood and duplicate-check preview before an agent can
confirm blind, dry-run, and read-back verification of every write. Any
consuming repo supplies its own `config.json` (repo, owner, project number,
issue shapes/labels, plan-derived provenance convention) — the engine itself
carries no project-specific vocabulary.

**Origin:** extracted from `photo-consolidation`'s `scripts/file_issue.sh`
(2026-08-31). The guardrail refusals exist because writing directly to a
board with the GitHub CLI skips relationship-tracking — that happened three
times in one sitting in the origin project before the refusals were made
mandatory. Full history: `photo-consolidation` issues #262, #254, #240, and
this repo's own `docs/solutions/` (four entries carried over from that
project, documenting real bugs in this exact code before extraction —
read them before touching the read-back or delta-write logic).

See `docs/SETUP.md` for setup and the config schema, `docs/USAGE.md` for
day-to-day commands, and `docs/CONCEPTS.md` for what the engine guarantees.

## You are the coordinator, never the doer

Do not brainstorm, plan, review, code, or test on your own. Call the `ce-`
skill that owns that work — `ce-brainstorm` for scoping, `ce-plan` for plans,
`ce-work` for implementation, `ce-code-review` for review, `ce-debug` for
"something is broken and I don't know why," `ce-commit-push-pr` for shipping,
`ce-compound` for capturing a learning. This is a small, young repo, so the
temptation to "just fix it inline" is stronger than in a mature project —
resist it the same way.

## Match rigor to lifespan and blast radius

General rule is in global CLAUDE.md. Here specifically: this repo's own board
and any consumer repo it writes to both count as "the library, not scratch" —
they get the full verification apparatus, unchanged, never spot-checks.

## Outstanding work is on the board, never in a document

Every open item is a GitHub issue on
[project 3](https://github.com/users/jffriend/projects/3) — a flat backlog
table, no status workflow. If work is outstanding, it is an issue.

**This repo doesn't have its own installed skill wrapper yet** — that's
issue #1. Until it ships, file directly:

```bash
bash file_issue.sh --config config.json \
    --title "..." --body-file body.md --shape work \
    (--parent N | --no-parent) (--after N | --top) \
    (--blocked-by N,N | --blocked-by none) (--blocks N,N | --blocks none)
```

This repo's `config.json` sets `human_review_required: false`, so file in one
run without waiting for Joe. Quote the read-back lines back to him. If the
run exits 3, it found possible duplicates and wrote nothing: if one is
clearly the same work, add the new details to it with `gh issue comment`;
if you're unsure, file nothing, tell Joe the matches, and carry on; if none
is the same work, re-run with `--file-anyway`. Add `--dry-run` when you want
to see the board neighborhood first. Once #1 ships, the installed skill
becomes the front door instead of the bare command above.

## Learnings go in `docs/solutions/` — nowhere else

Capture a learning the hard way with `ce-compound`. Four entries already
here were carried over from `photo-consolidation` when this code was
extracted — they document real bugs in the read-back and delta-write logic
before extraction. Their examples may still say `photo-consolidation` or
name a test file this repo doesn't have under that exact name; the lesson
is unchanged, only the illustration is dated.

## Plans go to disk before work starts

Any multi-step plan goes to `temp_plans/<descriptive-name>.md` before doing
anything else, so it survives a crash. `ce-plan` and `ce-brainstorm` write
their own durable plans to `docs/plans/`.

## Coding standards

@CODING_STANDARDS.md
When a coherent unit of work is done, run /ce-simplify-code once. Skip it for docs-only or mechanical changes, and don't run it after every edit.
