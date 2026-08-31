## Residual Review Findings

- **P2 — `docs/CONCEPTS.md:55` — USAGE.md and CONCEPTS.md give different lists of adopt-refusal triggers.**
  `docs/USAGE.md` lists three conditions that make adopt refuse (issue is closed, parent mismatch, blocked-by/blocks mismatch), matching `file_issue.sh`'s own header comment. `docs/CONCEPTS.md`'s parallel section lists only two, omitting the closed-issue case.
  Suggested fix: add the closed-issue condition to `docs/CONCEPTS.md`'s "Adopt Refuses Rather Than Reconciles" section, matching `docs/USAGE.md` and `file_issue.sh`'s header comment.
  Confidence: 75 (single reviewer, `correctness`). Not applied automatically — below the auto-apply bar (needs confidence 100, or 75 with a second corroborating reviewer).
  Not filed as a tracker ticket: this repo's own guardrail (`file_issue.sh`) requires four human-answered placement questions and a confirmed dry-run preview before anything reaches the project board, and raw `gh issue create` is explicitly prohibited by this repo's own `README.md`/`CLAUDE.md`. Neither path is available in an unattended run, so the finding is recorded here instead.

Source: `ce-code-review` run `20260831-103734-docs`, reviewing branch `worktree-docs-friendly-user-docs` against base `cc8419f1d3b21443fefd003598d976c80187f848`.
