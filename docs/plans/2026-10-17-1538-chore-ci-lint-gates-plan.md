---
title: CI Lint Gates - Plan
type: chore
date: 2026-10-17
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-plan-bootstrap
execution: code
origin: https://github.com/jffriend/ai-issue-management-skill/issues/29
---

# CI Lint Gates - Plan

## Goal Capsule

- **Objective:** A pull request that adds a shellcheck or ruff finding to the engine fails CI on the PR, so quoting, word-splitting, and masked-return mistakes in the bash are flagged before review instead of reaching consumers' boards.
- **Means:** a separate `lint` job in `.github/workflows/tests.yml` running pinned shellcheck and ruff (KTD1, KTD2), with today's findings fixed or suppressed (KTD3, KTD4).
- **Authority:** issue #29, then this plan's R-IDs, then KTDs.
- **Stop conditions:** a lint fix would change runtime behavior of `file_issue.sh` or `board.sh`; a pinned tool version cannot be installed from PyPI.
- **Execution profile:** small config and lint-fix change; verify by running the linters and the existing suite.
- **Finishes and ships:** the calling pipeline (`lfg`).

---

## Product Contract

### Summary

Add a CI lint job that runs shellcheck on the two bash scripts and ruff (rules F, E9, B) on the Python. Fix or suppress the four shellcheck notes and one ruff finding that exist today. Add a CI-only exception to the tool rule in `CODING_STANDARDS.md`.

### Problem Frame

CI runs only `python3 -m unittest discover tests`. `file_issue.sh` is about 1,200 lines of bash, and the repo's real bugs have been bash mistakes. Nothing catches quoting, word-splitting, or masked-return mistakes unless a test happens to cover the exact path.

### Requirements

**Lint gate**

- R1. CI fails when shellcheck reports any finding in `file_issue.sh` or `board.sh`.
- R2. CI fails when `ruff check --select F,E9,B` reports any finding in `issue_text.py` or `tests/`.
- R3. Lint runs on the same triggers as the test job, including the existing docs-only `paths-ignore`.

**Current findings**

- R4. Every current finding is fixed, or suppressed at its site with a one-line reason.
- R5. No fix changes the runtime behavior of `file_issue.sh`, `board.sh`, or the tests.

**Standards**

- R6. `CODING_STANDARDS.md` states that lint tools may run in CI only, and that nothing new runs when a consumer files an issue.

### Scope Boundaries

- No type checker (issue #29: no annotations, small Python, little gain).
- No ruff default rule set. It reports 98 findings, mostly style (60 are UP031).
- No local pre-commit hook or `ruff.toml`. The CI command is the single source of the rule selection.
- Not covered by this gate: an unguarded `VAR="$(cmd)"` whose failure is ignored under `set -uo pipefail` without `-e`. shellcheck 0.11.0 reports nothing for it, so that class of bug stays the tests' job.
- Not covered by this change: making `lint` a required status check on `main`. `main` has no branch protection today, so a red `lint` job reports but does not block a merge. That is a repo setting for the owner, and the docs-only `paths-ignore` would leave a required check pending on docs-only PRs.
- Considered and not built: a unittest that shells out to shellcheck. It would make the test suite depend on a tool consumers don't have. The CI job already fails on findings.

---

## Planning Contract

### Key Technical Decisions

- KTD1. **A separate `lint` job in `tests.yml`, not extra steps in the `test` job.** A lint failure then never hides test results, and the two run in parallel. Keeping it in `tests.yml` inherits the existing triggers and `paths-ignore` (R3), as issue #29 asked.
- KTD2. **Install both tools with one pinned pip install: `ruff==0.17.1` and `shellcheck-py==0.11.0.1`.** Both versions match the local tools today and both exist on PyPI. The runner's preinstalled shellcheck is an older apt build whose version moves with the image, so a pin keeps CI and local output identical. `shellcheck-py` ships the official shellcheck binary as a wheel.
- KTD3. **Suppress SC2015 in `half_wired_head` with a local `# shellcheck disable=SC2015` directive above the `Requested:` printf, reason: every branch only echoes, so C cannot run after a true A.** The warning is a false positive here. Suppressing it leaves runtime code untouched (R5), whereas a rewrite would edit an untested failure-report line and need new tests to prove it unchanged.
- KTD4. **Suppress the three SC2016 notes with a `# shellcheck disable=SC2016` directive at each site, reason: GraphQL `$variables` must stay literal.** Two sites are in `write_position`, one in `board_half`. A file-wide disable in `.shellcheckrc` would hide a real future quoting mistake, so the directive stays local. Place the `write_position` directive before the `if` so one line covers both mutations.
- KTD5. **Fix B904 in `scan_for_duplicated_comparisons` (`tests/test_engine_gating.py`) by adding `from exc` to the `raise AssertionError(...)`.** It only chains the traceback; the assertion message and failure are unchanged.

### Assumptions

- The issue counted 3 shellcheck notes; shellcheck 0.11.0 reports 4 today (one SC2015, three SC2016). The third SC2016 is the `projectItems` query added in the latest merge. All four are covered.
- shellcheck's default severity (style and up) is the gate. Every current finding is level `info`, so a stricter `--severity` would let them through and is not used.

---

## Implementation Units

### U1. Fix and suppress the current lint findings

- **Goal:** both linters exit 0 on the current tree.
- **Requirements:** R4, R5
- **Dependencies:** none
- **Files:** `file_issue.sh`, `tests/test_engine_gating.py` (the KTD5 fix only)
- **Approach:**
  1. Add the SC2015 directive in `half_wired_head` per KTD3.
  2. Add the SC2016 directives in `write_position` and `board_half` per KTD4.
  3. Add `from exc` in `scan_for_duplicated_comparisons` per KTD5.
- **Patterns to follow:** existing one-line comments in `file_issue.sh` (short, reason-only). `CODING_STANDARDS.md` forbids change-history comments.
- **Execution note:** read `docs/solutions/` first per `CODING_STANDARDS.md`; `board_half` sits on the read-back path. Every change in `file_issue.sh` is a comment line only.
- **Test expectation:** none new -- the `file_issue.sh` edits are lint directives and the KTD5 edit only chains a traceback. The full existing suite must still pass.
- **Verification:** `shellcheck file_issue.sh board.sh` and `ruff check --select F,E9,B issue_text.py tests` both exit 0; `python3 -m unittest discover tests` passes.

### U2. Add the CI lint job

- **Goal:** CI fails on any new shellcheck or ruff finding.
- **Requirements:** R1, R2, R3
- **Dependencies:** U1
- **Files:** `.github/workflows/tests.yml`
- **Approach:** add a `lint` job beside `test` (KTD1) that checks out, sets up Python 3.12, pip-installs the pinned tools (KTD2), then runs the two lint commands as separate steps so the failing tool is named in the CI log.
- **Patterns to follow:** the existing `test` job's checkout and `setup-python` steps.
- **Test expectation:** none -- CI config. Prove it by smoke check instead.
- **Verification:**
  - On the PR, the `lint` job runs and passes.
  - A scratch copy with a deliberate finding (for example an unquoted `$var` in a `[ ]` test, or an unused import) makes the matching command exit non-zero locally. This check is not committed.

### U3. State the CI-only exception

- **Goal:** the tool rule no longer contradicts the CI lint job.
- **Requirements:** R6
- **Dependencies:** none
- **Files:** `CODING_STANDARDS.md`
- **Approach:** add one line under the `bash`, `jq`, `python3`, `gh` rule allowing lint tools that run only in CI, never when a consumer files an issue.
- **Test expectation:** none -- docs only.
- **Verification:** the rule and the exception read as one consistent statement.

---

## Verification Contract

| Check | Command | Applies to |
|---|---|---|
| Shell lint | `shellcheck file_issue.sh board.sh` exits 0 | U1, U2 |
| Python lint | `ruff check --select F,E9,B issue_text.py tests` exits 0 | U1, U2 |
| Test suite | `python3 -m unittest discover tests` passes | U1 |
| CI | the PR's `lint` and `test` jobs both pass | U2 |

---

## Definition of Done

- Both lint commands exit 0 on the branch, locally and in CI.
- The test suite passes; the only test change is KTD5.
- `file_issue.sh` and `board.sh` differ from `main` only by comment lines.
- A deliberate new finding makes the relevant lint command fail.
- `CODING_STANDARDS.md` carries the CI-only exception.
- No scratch files or abandoned attempts remain in the diff.
