---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
origin: https://github.com/jffriend/ai-issue-management-skill/issues/4
created: 2026-08-31
---

# feat: Add CI that runs tests on code changes, skip docs-only diffs

## Product Contract preservation

No prior Product Contract exists for this work. This plan was bootstrapped
directly from GitHub issue #4.

---

## Summary

This repo (`file_issue.sh`, `board.sh`, `issue_text.py`) has 186 passing
`unittest` tests but no automated way to run them — a regression can merge
without anyone running `python3 -m unittest discover tests` by hand. Add a
GitHub Actions workflow that runs the suite on every push and pull request,
skipping runs that touch only documentation so pure-prose commits don't burn
CI minutes on a suite they can't affect.

## Problem Frame

The repo's own toolset section names `bash`, `jq`, `python3`, and `gh` as the
only tooling — no CI exists (`CLAUDE.md`; confirmed no `.github/`
directory in the repo). Tests are self-contained stdlib `unittest`: they fake
`gh` on `PATH` rather than shelling out to the real GitHub CLI or network, so
CI needs no secrets, tokens, or `gh auth`. The full suite currently takes
~124s locally on Python 3.9.6.

## Requirements

- **R1**: A GitHub Actions workflow runs `python3 -m unittest discover tests`
  automatically on every push to `main` and on every pull request (against
  any base branch). Restricting `push` to `main` avoids double-running the
  suite for every commit on a branch that already has an open PR.
- **R2**: A commit that changes only `README.md`, files under `docs/**`, or
  `CLAUDE.md` does not trigger the test-suite run.
- **R3**: A future doc-specific check (link validation, style lint) is not
  precluded by R2's exemption — the exemption applies to the code test suite
  job only, not to the workflow file as a whole.

## Key Technical Decisions

**KTD1: Use `paths-ignore` on the workflow's `push`/`pull_request` triggers,
not a job-level `paths` filter.**
This repo has exactly one CI job today (the test suite), so a trigger-level
`paths-ignore` is equivalent in effect to a job-level `paths` filter but
simpler to read. `on:` triggers apply to the whole workflow file, not per
job — so per R3, a future doc-specific check must live in its **own**
workflow file with its own triggers, not as a second job appended to this
one (a same-file job would inherit this file's `paths-ignore` and also be
skipped on docs-only diffs, which is exactly what R3 rules out). If a
same-file job is ever preferred instead, it needs a path-filter action (e.g.
`dorny/paths-filter`) driving a job-level `if:`, not a per-job trigger block
— GitHub Actions has no such per-job trigger mechanism.

**KTD2: Pin a single, currently-supported Python version via
`actions/setup-python`, not a version matrix.**
The codebase has no `python_requires` declaration and the test suite uses
only stdlib features with no version-sensitive syntax found during research.
A matrix adds job minutes and maintenance surface with no evidence the suite
is version-fragile. Pin to Python 3.12 rather than "latest" (so an upstream
Python release can't silently break CI before anyone opts in) and rather
than matching the local 3.9.6 (which is already past its end-of-life and
unsuitable for a fresh CI pin).

**KTD3: Run on `ubuntu-latest`, no custom container.**
The suite needs only `python3`; GitHub's hosted Ubuntu runner ships it along
with `git`, satisfying `actions/checkout`. No dependency installation step is
needed — the repo declares no `requirements.txt` or package manifest.

## Implementation Units

### U1. Add the test-suite GitHub Actions workflow

**Goal:** Running `python3 -m unittest discover tests` automatically on push
and PR, skipping doc-only diffs.

**Requirements:** R1, R2, R3 (KTD1, KTD2, KTD3)

**Dependencies:** None

**Files:**
- `.github/workflows/tests.yml` (new)

**Approach:**
1. Trigger on `push` restricted to `branches: [main]`, and on `pull_request`
   (any base branch) — both with a top-level `paths-ignore` listing
   `README.md`, `docs/**`, and `CLAUDE.md` (KTD1).
2. Single job `test`, `runs-on: ubuntu-latest`.
3. Steps: `actions/checkout@v4`, `actions/setup-python@v5` pinned to Python
   `3.12` (KTD2), then run `python3 -m unittest discover tests`.
4. No dependency-install step — the suite has none (KTD3).

**Patterns to follow:** None locally — this is the first workflow file in
the repo. Follow the standard `actions/checkout` + `actions/setup-python` +
run-step shape used across GitHub's own starter workflows for Python
projects.

**Test scenarios:**
- Test expectation: none -- a GitHub Actions trigger/path-filter definition
  isn't something `unittest` can exercise locally. Verification is a real
  push/PR observed on GitHub (see Verification below), not a written test.

**Verification:**
- A push or PR that touches `file_issue.sh`, `board.sh`, `issue_text.py`, or
  any file under `tests/` shows a `test` job run in the GitHub Actions tab,
  and it reports the same "Ran 186 tests ... OK" result the local run
  produces.
- A push or PR that touches only `README.md`, a file under `docs/**`, or
  `CLAUDE.md` shows no `test` job run triggered for that commit.
- The workflow file parses as valid GitHub Actions YAML — confirmed by
  GitHub itself: a malformed `.github/workflows/tests.yml` shows as a
  workflow syntax error in the Actions tab on push, rather than a silent
  no-op. No local YAML-parsing tool is needed (the repo's toolset is
  `bash`, `jq`, `python3`, `gh` — no `pip install` step).

---

## Scope Boundaries

### Deferred to Follow-Up Work
- A doc-specific check (link validation, style-guide lint) that *does* run
  on docs-only changes — issue #4 names this as a possible future addition,
  not part of this change (R3 only requires this workflow not preclude it).
- Version matrix testing (multiple Python versions) — no evidence today that
  the suite is version-sensitive; add if that changes.
- Caching `pip`/dependency installs — moot until the repo has a dependency
  manifest to cache against.

## Verification Contract

- CI is green on this branch's own PR: the `test` job runs and passes.
- A docs-only commit (e.g., a trivial edit to `docs/USAGE.md` made as a
  throwaway check, not part of this PR) does not trigger the `test` job.

## Definition of Done

- `.github/workflows/tests.yml` exists, is syntactically valid, and matches
  the approach in U1.
- The workflow's own PR shows the `test` job running and passing in the
  GitHub Actions tab.
- A docs-only commit (a change touching only `README.md`, `docs/**`, or
  `CLAUDE.md`) does not trigger the `test` job, per the Verification
  Contract.
