---
title: Strip history from engine and test docstrings - Plan
type: refactor
date: 2026-10-17
topic: docstring-history-cleanup
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-plan-bootstrap
execution: code
---

# Strip history from engine and test docstrings - Plan

## Goal Capsule

- **Objective:** A reader opening `issue_text.py` or any test learns what each function or test guarantees and why, without reading dates, bug stories, or notes about how the code used to be.
- **Means:** Rewrite the offending docstrings in place (KTD1); history already recorded in `docs/` is deleted, not moved (KTD2).
- **Product authority:** Joe; issue #27 is the spec.
- **Stop conditions:** Stop if a docstring holds history that is recorded nowhere else and is needed to understand a guard; record it with `ce-compound` before deleting it. Never change test logic, assertions, or fixture data.
- **Ships as:** one PR on branch `worktree-issue-27-docstring-cleanup`, closing #27.

## Product Contract

### Summary

Remove date stamps, bug stories, and change notes from the docstrings in `issue_text.py` and `tests/*.py`. Keep each docstring's statement of what the code guarantees and the reason it exists. Fix references to files that do not exist in this repo.

### Problem Frame

`CODING_STANDARDS.md` bans bug history, date stamps, and change notes in comments. An earlier audit cleaned `#` comments but skipped docstrings. The code was extracted from `photo-consolidation`, so its docstrings still tell that project's story: "A truncated board listing hid #164 on 2026-08-19", "That instruction was violated three times in one day", "The old test was `flag in script_text`". About 30 docstrings in `tests/test_engine_gating.py` name a date, a measurement, or an old version. Several docstrings also point at files this repo does not have: `scripts/file_issue.sh` (now `file_issue.sh` at the root), `docs/WORKFLOW.md`, `board_audit.py`, and "the photo library". New docstrings copy the pattern.

### Requirements

**Content**

- R1. No docstring in `issue_text.py` or `tests/*.py` holds a calendar date, a story of a past incident, a measurement tied to a past date or tool version, or a description of what an earlier version of the code or test did.
- R2. Each rewritten docstring still states what the function, class, or test guarantees, and the reason when the reason is not obvious from the name.
- R3. Docstrings name only files and tools that exist in this repo; `scripts/file_issue.sh` becomes `file_issue.sh`.
- R4. The "Ported from Photos'…" preambles in `tests/test_engine_gating.py` and `tests/test_engine_skill.py` are removed.

**Behavior**

- R5. No test logic, assertion, fixture, or engine behavior changes; the suite passes unchanged in count.

### Scope Boundaries

- Issue numbers used as fixture data (`#200`, `#101`, `#55`, and the like inside test bodies and fixtures) are test inputs, not history; leave them.
- This repo's own traceability tags, such as `#14 U1` and `R9`, point at this repo's issues and plans; keep them (KTD3).
- `#` comments are out of scope; the earlier audit covered them.
- `file_issue.sh` and `board.sh` are bash and carry no docstrings; out of scope.

## Planning Contract

### Key Technical Decisions

- KTD1. **Rewrite in place, one docstring at a time.** A regex can find candidates but cannot tell history from explanation; "so 'years before 1975' does not count" is a legitimate example of what a guard rejects, while "the naive version reported 34 of 66" is history. Each candidate gets a human-judgment rewrite.
- KTD2. **Delete history already recorded elsewhere; do not duplicate it.** The origin story (a rule broken three times in one sitting, the sixteen unrecorded constraints) is in `docs/CONCEPTS.md`. The `gh issue edit` non-idempotence measurement is in `docs/solutions/developer-experience/gh-issue-edit-is-not-idempotent-write-a-delta-not-a-set.md`. Docstrings may link to those docs by path when the link helps a reader understand a guard.
- KTD3. **Origin-project issue numbers go; this repo's references stay.** Numbers like `#164`, `#176`, `#233`, `#265` belong to `photo-consolidation` and do not resolve here. `#14` resolves here (the REST API filing issue) and the `U<N>`/`R<N>` tags trace to `docs/plans/`, so they remain.
- KTD4. **Keep the guarantee, drop the narrative.** Where a docstring explains a guard by telling the incident ("a truncated board listing hid #164"), restate it as the failure the guard prevents ("a truncated board listing can hide an existing issue, so the tool treats truncation as fatal").

### Assumptions

- No docstring holds history that is both unrecorded elsewhere and needed to understand a guard. If one does, the stop condition applies and the history goes to `docs/solutions/` via `ce-compound` before deletion.

## Implementation Units

### U1. `issue_text.py` docstrings

- **Goal:** The module docstring and `states_prose_ordering` describe what the code does and why, with no dates or incident numbers.
- **Requirements:** R1, R2, R3
- **Dependencies:** none
- **Files:** `issue_text.py`
- **Approach:**
  1. Module docstring: replace the `#164`/`#176` and "2026-08-19 ordering audit found 16" passages with the failure each check prevents (KTD4). Change `scripts/file_issue.sh` to `file_issue.sh`. Replace the `docs/WORKFLOW.md` reference with the rule itself or a link to `docs/CONCEPTS.md`.
  2. `states_prose_ordering`: drop "The naive version of this reported 34 of 66"; keep the two rules (a weak cue counts only when it names other work, template boilerplate is excluded) and the note that direction checking belongs to the caller, without naming `board_audit.py`. No engine path calls this function (`file_issue.sh` uses only `plan-derived`, `design-line`, and `dupes`), so say it is library logic for a consumer's board audit, and reword the module docstring's "the issue-filing gate and the board audit" framing so it does not claim the engine runs it.
  3. Check every other docstring in the file against R1.
- **Test scenarios:** Test expectation: none -- docstring-only change; R5 is checked by the existing suite.
- **Verification:** No date, origin-project issue number, or "old/naive/previous version" wording remains in the file's docstrings.

### U2. `tests/test_engine_issue_text.py` and `tests/test_engine_skill.py`

- **Goal:** Module and class docstrings in the two smaller test files describe what they test.
- **Requirements:** R1, R2, R3, R4
- **Dependencies:** none
- **Files:** `tests/test_engine_issue_text.py`, `tests/test_engine_skill.py`
- **Approach:**
  1. `test_engine_issue_text.py` module docstring: remove the "violated three times in one day" and `#164`/`#176` story and the `docs/WORKFLOW.md` and "photo library" references; keep the list of the three pieces of logic and what each guarantees.
  2. `ProseOrdering`: drop "An earlier naive regex reported 34 of 66"; keep what the detector must reject and why.
  3. `test_engine_skill.py` module docstring: remove the "Ported from Photos'…" preamble and the list of classes left behind (R4); keep the "WHY THIS EXISTS" content, retitled without "(from the original file…)".
  4. `test_mere_presence_in_the_script_does_not_make_a_flag_a_remedy` and `test_the_gh_remedy_flags_are_only_allowed_because_the_script_prints_them`: drop "the old comment"/"The old test was"; keep the property tested.
  5. Check every other docstring in both files against R1.
- **Test scenarios:** Test expectation: none -- docstring-only change.
- **Verification:** Both files pass R1 and R4 on re-read.

### U3. `tests/test_engine_gating.py`

- **Goal:** The roughly 30 docstrings in the gating tests describe what each test or helper proves, with no dates, measurements tied to dates, or past-version stories.
- **Requirements:** R1, R2, R3, R4
- **Dependencies:** none
- **Files:** `tests/test_engine_gating.py`
- **Approach:**
  1. Module docstring: remove the "Ported from Photos'…" paragraph and the dated incident story (KTD2, KTD4); keep the four placement questions, the duplicate preview, the truncated-board rule, and "HOW THESE TESTS AVOID THE REAL BOARD".
  2. `AdoptDelta`: drop "measured against the live board on 2026-08-24 with gh 2.98.0 and recorded on #233"; keep the error examples and the delta rule, and link the `docs/solutions/` entry (KTD2).
  3. `test_the_warning_names_a_delay_the_ceiling_will_actually_accept` and similar: drop "#265: the old text said" and "a prior version of this test"; keep the property and the reason the test avoids sleeping.
  4. Walk every remaining docstring in the file; apply R1 and KTD3. Leave fixture issue numbers alone.
- **Test scenarios:** Test expectation: none -- docstring-only change.
- **Verification:** A scan of the file's docstrings for `20\d\d-\d\d`, `old `, `previous`, `prior version`, `naive`, `measured`, `Photos`, `WORKFLOW.md`, and origin-project issue numbers finds nothing that R1 bans.

## Verification Contract

| Check | Command or method | Applies to |
| --- | --- | --- |
| Suite passes, same test count as before | `python3 -m unittest discover tests` (CI runs the same) | U1, U2, U3 |
| No banned history in docstrings | Parse each file with Python's `ast`, print every docstring matching the U3 scan terms, and judge each hit against R1 | U1, U2, U3 |
| Only docstrings changed | `git diff` touches only docstring text | R5 |

## Definition of Done

- R1 through R5 hold for `issue_text.py` and all three test files.
- The suite passes with the same number of tests as on `main`.
- Any history that met the stop condition is recorded in `docs/solutions/` first.
- The diff contains no edits outside docstrings and no leftover scratch scripts.
