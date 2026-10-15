# ai-issue-management-skill

**A guardrail for putting work on a GitHub Projects (v2) board, so that an
agent — or a person moving fast — cannot skip the bookkeeping that makes a
board trustworthy.**

## Why this exists

Writing directly to a GitHub Projects board with the GitHub CLI creates or
edits exactly what you asked for and stops there. It never asks where the
new issue sits in priority order, what blocks it, or what it blocks — so
that bookkeeping gets left for "a later step" that rarely comes. This
repo's engine makes those questions mandatory instead of optional; see
[Why These Guards Exist](docs/CONCEPTS.md#why-these-guards-exist) in
`docs/CONCEPTS.md` for the fuller story, including what happened on the
board this tool was extracted from.

## What this repo ships

This repo ships the engine — `file_issue.sh` and its two helpers,
`board.sh` and `issue_text.py` — plus two templates a consuming repo
customizes: `config.example.json` and `SKILL.template.md`. It talks to
GitHub Issues and GitHub Projects (v2) only, with no backend abstraction.
There's no package or CLI distribution yet: a consuming repo adds this
repo as a git submodule.

## Scope

- GitHub Issues and GitHub Projects (v2) only — no pluggable backend.
- Filing and wiring (create and adopt) only — closing an issue, retitling
  one, or re-anchoring a plan link isn't covered.
- No installable package yet — git submodule is the supported integration
  path.

## Where to go next

- **Setting this up in your own repo?** Start with `docs/SETUP.md` — it
  walks through adding the submodule, writing your config, and filling in
  the skill template.
- **Ready to file or adopt an issue?** `docs/USAGE.md` covers create mode,
  adopt mode, the four placement answers, what `--dry-run` shows you, and
  what happens when a filing looks like a duplicate.
- **Want to know why the tool works the way it does?** `docs/CONCEPTS.md`
  defines its vocabulary and explains the reasoning behind every guard.
