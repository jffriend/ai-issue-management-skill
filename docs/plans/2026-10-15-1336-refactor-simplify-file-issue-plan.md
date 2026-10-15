---
title: Simplify the file-issue skill and engine - Plan
type: refactor
date: 2026-10-15
topic: simplify-file-issue
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-brainstorm
execution: code
---

# Simplify the file-issue skill and engine - Plan

## Goal Capsule

- **Objective:** An agent puts work on the board with as few steps as the review setting allows, never stalls a session over a possible duplicate, and files only work it shouldn't just fix in place.
- **Means:** Simplify the engine (`file_issue.sh`) and the skill (`SKILL.template.md`) before porting the engine to REST, so issue #14 ports less code.
- **Product authority:** Joe, the only user of this tool today (this repo and pluckd).
- **Mechanism:** The engine stops before writing when it finds possible duplicates, unless told to file anyway (KTD1, KTD2); the stdin prompt goes away (KTD3).
- **Open blockers:** None. Issue #14 is blocked on this work.
- **Stop conditions:** Stop if keeping R14's guards unchanged turns out to conflict with removing the prompt. Do not touch the `gh` version check or start the REST port (#14).
- **Ships as:** one PR on branch `worktree-simplify-file-issue-brainstorm`, carrying this plan and the code, closing #15.

---

## Product Contract

### Summary

`human_review_required` becomes `true` or `false`. With review off, the agent files without a confirmation prompt and handles possible duplicates itself without stopping the session. With review on, a human approves a preview and then the engine runs. The skill drops the two-run comparison and the audit comment, and it starts by asking whether the work should be fixed in the session instead of filed.

### Problem Frame

Filing an issue today takes the agent two engine runs. The first, with `--dry-run`, shows a preview. The second pipes `y` into the engine's `Create it? [y/N]` prompt, because Claude Code cannot answer that prompt interactively. Because the board can change between runs, the skill also makes the agent compare the two outputs. It then posts an audit comment naming who approved the filing. Three review tiers (`required`, `optional`, `agent`) control who may say yes. Together these make up most of the skill's 387 lines.

Pluckd, the main consumer, runs with `human_review_required: "agent"`. There, the agent approves its own filings, so the preview, the comparison, and the audit comment protect little. Every extra step is also code that #14 has to port to GitHub's REST API so filing works from Claude Code cloud sessions.

Separately, agents over-file. Small bugs and doc fixes in files the session is already editing get turned into issues when they should be fixed in that session.

### Key Decisions

- **The review setting is a boolean named `human_review_required`.** (session-settled: user-directed — chosen over keeping the three tiers and over dropping human review entirely: the tier names were confusing and `optional` was unused.) Governs R1, R2, R3.
- **No migration path for old values.** (session-settled: user-directed — chosen over a dedicated refusal message for `optional`: Joe is the only user.) Governs R1.
- **A possible duplicate never blocks the session.** (session-settled: user-directed — chosen over refusing until the agent acknowledges each match, and over always stopping for a human: filing must not block other work.) Governs R5, R6, R7.
- **The agent, not the engine, judges duplicates.** (session-settled: user-directed — chosen over having the engine decide by title match, which cannot tell likely from certain.) Governs R5, R6, R7.
- **The audit comment is dropped.** (session-settled: user-directed — chosen over an engine-written comment on every filing and over a comment only on surprises.) Governs R10.
- **Fix in place before filing.** (session-settled: user-approved — the agent proposed the boundary "small fixes in files the session is already touching"; Joe confirmed.) Governs R9.
- **This ships as its own issue, ahead of #14.** (session-settled: user-directed — chosen over folding the simplification into the REST port: separate changes are easier to review and keep the guards in `docs/solutions/` from breaking unnoticed in a mixed rewrite.)

### Requirements

**Review setting and engine runs**

- R1. `human_review_required` accepts `true` or `false`; a missing key means `true`, and any other value is refused.
- R2. With review off, a filing with no possible duplicates completes in one engine run, with no confirmation prompt.
- R3. With review on, the human sees the engine's preview verbatim and approves it before the real run; the engine itself never prompts for confirmation.
- R4. `--dry-run` stays available at either setting and writes nothing.

**Possible duplicates (review off)**

- R5. The agent sees any possible-duplicate matches before anything is written.
- R6. When the agent is confident the work duplicates an existing issue, it adds the new details as a comment on that issue and files nothing.
- R7. When the agent is unsure, it files nothing, reports the matches in chat with the option to file anyway, and continues the session's other work.

**Adopt moves (review off)**

- R8. An adopt that moves an issue proceeds without stopping; the engine's existing comment recording the old and new slot stays.

**Skill**

- R9. The skill opens with a check: small bugs, doc fixes, and similar small fixes in files the session is already touching are fixed in the session, not filed.
- R10. The skill no longer posts an audit comment.
- R11. The skill no longer compares the output of two engine runs.
- R12. The skill describes only the two review settings and the steps R2 through R8 need.

**Docs and unchanged guards**

- R13. `docs/USAGE.md`, `docs/CONCEPTS.md`, `docs/SETUP.md`, and `config.example.json` describe the boolean setting and the new run flow, and no longer mention `optional`, `agent`, or the y/N prompt.
- R14. Every other guard behaves as today: the four placement refusals, the truncated-board stop, adopt refusing unnamed links, delta writes, the read-back, and the move-record comment.

### Acceptance Examples

- AE1. **Covers R2.** **Given** review off and no title matches, **when** the agent files a new issue, **then** one engine run creates it, wires it, and prints the read-back.
- AE2. **Covers R5, R6.** **Given** review off and an open issue that clearly covers the same work, **when** the agent goes to file, **then** nothing is created and the existing issue gets a comment with the new details.
- AE3. **Covers R5, R7.** **Given** review off and a match the agent isn't sure about, **when** the agent goes to file, **then** nothing is created, the chat names the match and offers to file anyway, and the session carries on.
- AE4. **Covers R1, R3.** **Given** a config with no `human_review_required` key, **when** the agent files, **then** it shows the preview and waits for a human yes before the real run.
- AE5. **Covers R1.** **Given** a config with `"human_review_required": "agent"`, **when** the engine starts, **then** it refuses and names the allowed values.
- AE6. **Covers R9.** **Given** a session editing `docs/USAGE.md` that notices a typo in that file, **when** it would otherwise file an issue, **then** it fixes the typo in the session instead.

### Scope Boundaries

- Moving the engine to REST, and changing or removing the `gh` version check, belong to #14.
- The engine does not judge duplicates by itself.
- No migration or special message for the removed `optional` value.
- No replacement for the audit comment.

### Dependencies / Assumptions

- Pluckd's `scripts/file-issue.config.json` says `"agent"` and must change to `false` when pluckd takes this version. That edit happens in pluckd.
- Assumed acceptable: with review on, a board change between the preview and the real run is caught only by the read-back.
- Assumed acceptable: work the agent declined to file as a possible duplicate exists only in chat, and is lost if nobody answers.

### Outstanding Questions

Both planning questions are resolved in the Planning Contract: R5's mechanism is KTD1, and R7's "file anyway" path is the flag in KTD2.

### Sources / Research

- Issue #14 (REST port) and its comment measuring REST blocked-by links.
- Pluckd's cloud-session plan, `docs/plans/2026-10-15-1312-chore-cloud-sessions-workflow-plan.md` in the pluckd repo: position is best-effort, issue work is required.
- `docs/solutions/` holds the four learnings behind the read-back and delta-write guards that R14 keeps.
- `docs/plans/2026-08-31-002-feat-configurable-human-review-plan.md` introduced the three tiers this plan replaces.

---

## Planning Contract

### Key Technical Decisions

- KTD1. **The engine stops before any write when the duplicate check finds matches.** In create mode, a non-dry run that finds possible duplicates prints the full preview, says nothing was created, and exits 3. A run with no matches goes straight on to write. Chosen over "the agent always runs `--dry-run` first," which costs every filing a second engine run and breaks R2. The agent still judges the matches; the engine only refuses to write past them unasked. Governs R2, R5, R7.
- KTD2. **`--file-anyway` lets a create run write past listed matches.** It still prints the duplicate block, so the run's output shows what was waved through. Adopt mode refuses it, the same way it refuses `--shape`, because adopt has no duplicate check. Chosen over a plain re-run, which would stop on the same matches again. Governs R7.
- KTD3. **The engine never reads stdin.** The `Create it? / Wire it? [y/N]` block is deleted. Where the prompt was, a non-dry run either stops (KTD1) or writes. Adopt mode has no duplicate check, so an adopt, including one that moves an issue, writes in one run. (session-settled: user-directed — chosen over keeping the interactive prompt: Claude Code cannot answer it and agents pipe `y` into it.) Governs R2, R3, R8.
- KTD4. **`human_review_required` is validated by JSON type.** The engine reads the key's `type` with `jq`: absent means `true`, `"boolean"` is accepted, anything else (including the strings `"true"` and `"agent"`) is refused with a message naming `true` and `false`. The engine does nothing else with the value; the skill reads it and decides whether to preview first. Checking `type` avoids the trap where `jq`'s `//` treats `false` as absent. (session-settled: user-directed — chosen over keeping the three string tiers or adding a migration message: Joe is the only user.) Governs R1.
- KTD5. **Exit 3 means "stopped for possible duplicates."** Every other refusal exits 1 through `die`, and success exits 0. A distinct code lets the skill tell "go judge these matches" from "the engine refused" without parsing text. Governs R5, R7.
- KTD6. **The skill uses `--dry-run` only when review is on.** With review on: dry-run, show the output verbatim, wait for a human yes, then run the same command, adding `--file-anyway` if the human approved past listed matches. With review off: run once, and on exit 3 judge each match per R6 and R7. Governs R2, R3, R6, R7, R12.

### Assumptions

- The skill's existing "one exception" for posting a comment with `gh issue comment` covers R6's comment on the existing issue. Only the reason given for the exception changes, since the audit step it cited is gone.
- `tests/test_engine_skill.py` does not scan `SKILL.template.md` today, so no skill conformance test has to be retargeted.

### Not built

- A conformance scan of `SKILL.template.md`. The origin project's scan was left behind at extraction, and `docs/solutions/best-practices/the-exemption-that-makes-a-guard-writable-is-the-hole.md` shows a quickly built scan is easy to make hollow. Revisit when issue #1 installs a real skill wrapper.
- Catching a board change between a review-on preview and the real run. The Product Contract accepts that only the read-back catches it.

### Code anchors

- `file_issue.sh`: config parsing (`HUMAN_REVIEW_REQUIRED=`), the duplicate block (`DUPES=` / `POSSIBLE DUPLICATES`), and the prompt block (`read -r ANSWER`).
- `tests/test_engine_gating.py`: `Harness.run(..., stdin=...)`, about 60 `stdin="y\n"` call sites, `test_answering_no_at_the_prompt_creates_nothing`, `test_an_empty_answer_at_the_prompt_creates_nothing`, and the five `test_human_review_required_*` tests.
- `docs/solutions/design-patterns/make-the-lossy-half-recoverable-before-removing-the-gate.md`: removing the gate is safe only because the adopt move-record comment makes the lost slot recoverable. R8 and R14 keep it.
- `docs/solutions/best-practices/when-empty-is-a-legal-answer-a-guard-must-check-shape-not-emptiness.md` and `docs/solutions/developer-experience/gh-issue-edit-is-not-idempotent-write-a-delta-not-a-set.md`: the read-back and delta-write code this plan leaves untouched.

---

## Implementation Units

### U1. Boolean review setting in the engine

**Goal:** The engine accepts only `true`, `false`, or a missing key for `human_review_required`.

**Requirements:** R1. **Dependencies:** none.

**Files:** `file_issue.sh`, `tests/test_engine_gating.py`

**Approach:** Replace the string read and the `required|optional|agent` case with KTD4's type check. The refusal names the key, the value it got, and `true`/`false`.

**Test scenarios:**
- Covers AE4. Missing key: a `--dry-run` run succeeds.
- JSON `true` and `false`: each accepted.
- Covers AE5. `"agent"`: refused; output names `human_review_required`, `agent`, `true`, and `false`; nothing created.
- String `"true"`, `"required"`, `null`, and `1`: each refused.
- The three tests asserting the old tiers (`..._optional_is_accepted`, `..._wrong_case_refuses`, `..._json_false_refuses_rather_than_defaulting`) are replaced by the above.

**Verification:** the new tests pass and no test asserts the old string values.

### U2. Remove the prompt; stop on possible duplicates

**Goal:** One engine run files when there are no matches, and stops before writing when there are.

**Requirements:** R2, R4, R5, R7, R8, R14. **Dependencies:** U1.

**Files:** `file_issue.sh`, `tests/test_engine_gating.py`, `tests/test_engine_skill.py`

**Approach:**
1. Add the `--file-anyway` parser arm and refuse it in adopt mode alongside the other create-only flags (KTD2).
2. Delete the prompt block (KTD3).
3. After the summary and the `--dry-run` exit, stop with exit 3 when create mode found matches and `--file-anyway` was not given (KTD1, KTD5). The message says nothing was created and names `--file-anyway`.
4. Update the header comment and help block: remove "makes a human say yes" and "confirmation summary" wording, and document `--file-anyway` and exit 3.
5. Tests: drop `stdin="y\n"` from call sites, replace the two prompt-answer tests with the scenarios below, and add `--file-anyway` to the expected flags in `tests/test_engine_skill.py`.

**Execution note:** do not edit the read-back, delta-write, or move-record code. If a test covering them fails, the change is in the wrong place.

**Test scenarios:**
- Covers AE1. No matches, no stdin: issue created, wired, read-back printed, exit 0.
- Matches, no `--file-anyway`: exit 3, `POSSIBLE DUPLICATES` and the match number printed, no `issue create` call.
- Matches with `--file-anyway`: duplicate block printed, issue created, exit 0.
- Matches with `--dry-run`: exit 0, nothing created.
- Adopt with `--file-anyway`: refused, nothing written.
- Adopt that moves an issue, no stdin: writes in one run and posts the move-record comment.
- A run fed `n` on stdin still files, proving stdin is ignored.
- Every existing guard test (placement refusals, truncated board, adopt refusals, delta writes, read-back states, move record) passes with only its `stdin` argument dropped.

**Verification:** the full suite passes, and `file_issue.sh` contains no `read -r ANSWER` or `[y/N]`.

### U3. Rewrite the skill template

**Goal:** `SKILL.template.md` describes the one-run flow, the two review settings, and the fix-it-here check.

**Requirements:** R3, R6, R7, R9, R10, R11, R12. **Dependencies:** U2.

**Files:** `SKILL.template.md`

**Approach:**
1. Add a first step before the placement questions: small bugs, doc fixes, and similar small fixes in files the session is already touching get fixed in the session, not filed (R9).
2. Replace Steps 3 and 4 with KTD6's flow. Describe `true` and `false` only. Treat a missing key or an unreadable config as `true`.
3. Describe exit 3. Confident duplicate: comment the new details on the existing issue with `gh issue comment` and file nothing (R6). Unsure: file nothing, report the matches in chat with the offer to re-run with `--file-anyway`, and continue other work (R7).
4. Delete the two-run comparison, the audit comment, the `printf 'y\n'` pipe, and the `optional`/`agent` sections (R10, R11). Keep Step 5's read-back reporting and the move-record warning handling.
5. Update "What this skill must never do" to match.

**Test scenarios:** Test expectation: none -- prose template with no automated scan (see Not built).

**Verification:** the template no longer mentions `optional`, `agent` as a review value, the audit comment, `y/N`, or piping `y`, and it is well under 387 lines.

### U4. Docs and example config

**Goal:** Setup and usage docs match the new setting and flow.

**Requirements:** R13. **Dependencies:** U2.

**Files:** `docs/USAGE.md`, `docs/CONCEPTS.md`, `docs/SETUP.md`, `config.example.json`

**Approach:** Describe `human_review_required` as a boolean defaulting to `true`, the one-run flow, exit 3 and `--file-anyway`, and `--dry-run` as optional at either setting. Remove every mention of the old string values and the y/N prompt. Add `"human_review_required": true` to `config.example.json`.

**Test scenarios:** Test expectation: none -- documentation. `config.example.json` stays valid JSON the engine accepts.

**Verification:** none of the three docs mentions the old values or the prompt.

---

## Verification Contract

- `python3 -m unittest discover tests` (the CI command in `.github/workflows/`) passes.
- `bash -n file_issue.sh` passes.
- The read-back, delta-write, and move-record functions (`read_back`, `board_half`, the `half_wired*` family) have no diff beyond comment wording.

## Definition of Done

- U1–U4 complete and their verification passes.
- R1–R14 each trace to a unit or KTD.
- No abandoned-attempt code left in the diff.
- PR body says "Closes #15" and notes that pluckd's `scripts/file-issue.config.json` must change `"agent"` to `false` when pluckd takes this version.
