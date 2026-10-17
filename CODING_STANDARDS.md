# Coding Standards

## Code style
- Don't write comments that restate what the code does.
- Never add comments about the change itself: no bug history, date stamps, or "fixed X" / "updated to use Y" notes.
- Comment only when the reason for the code isn't obvious (a workaround, a constraint, a surprising decision). One line, no essays.
- When editing a function, remove existing comments in it that break these rules.
- Make the smallest change that solves the problem.
- Don't add abstractions, helpers, or wrappers unless there are at least two real uses.
- Don't add config options or error handling for cases that can't happen unless I ask.
- Don't refactor code outside the task.

## Project rules
- The engine carries no project-specific vocabulary. Repo, owner, project number, issue shapes, labels, and provenance conventions come from the consuming repo's `config.json`.
- Use only `bash`, `jq`, `python3`, and `gh`. Don't add other tools or dependencies.
  - Exception: lint tools (shellcheck, ruff) may run in CI only. Nothing new runs when a consumer files an issue.
- Before changing the read-back or delta-write logic, read the entries in `docs/solutions/`. They document real bugs in that code.
- The placement refusals, duplicate check, dry-run, and read-back verification are the product. Each exists because the case it guards really happened. Never remove or weaken them as unneeded error handling.
