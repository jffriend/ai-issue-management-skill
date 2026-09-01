---
title: Configurable Human Review - Plan
type: feat
date: 2026-08-31
topic: configurable-human-review
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
execution: code
---

# Configurable Human Review - Plan

## Goal Capsule

- **Objective:** Add a `human_review_required` setting that controls how the filing engine's existing preview-then-confirm procedure decides who has to approve a write, and wire the choice into issue #1's automated setup interview.
- **Product authority:** Brainstorm dialogue with the repo owner (2026-08-31); decisions below are session-settled.
- **Open blockers:** None for this plan's own scope. Depends on issue #1 shipping the setup interview this plan's Key Flow F1 is written for (see [How This Work Fits Together](#how-this-work-fits-together)); until then the field can still be hand-set in `config.json`.

---

## Product Contract

**Product Contract preservation:** unchanged. Planning added Planning Contract, Implementation Units, Verification Contract, and Definition of Done below; it did not alter Requirements, Key Decisions, Actors, Key Flows, Acceptance Examples, Scope Boundaries, or Dependencies/Assumptions.

### Summary

Add `human_review_required` (`required` default, `optional`, `agent`) to `config.json`, and make the filing engine's existing preview-then-self-confirm procedure branch on it: `required` waits for an affirmative reply to the shown preview, `optional` also accepts approval stated up front in the request, and `agent` self-confirms without waiting. All three keep the existing stop-on-surprise escalation and get a (trimmed) audit comment.

### Problem Frame

`file_issue.sh` and its skill template already implement a full preview-then-confirm-then-audit procedure: the agent shows a dry-run preview verbatim in the same conversation, then re-runs for real and answers the confirmation prompt itself, then compares the two board reads for drift, then posts an audit comment. That procedure is currently unconditional — every repo that installs the skill template gets standing self-confirm permission, with no way to require an actual human "yes" instead. This repo's own project history (`docs/solutions/design-patterns/make-the-lossy-half-recoverable-before-removing-the-gate.md`, `docs/solutions/best-practices/the-exemption-that-makes-a-guard-writable-is-the-hole.md`) records that this exact confirmation step was removed once before, and that a removed or loosened gate is easy to make look intact — via a hollow guard, a template that says one thing but enforces another, or a lost audit trail — even when nobody intends that. This plan makes the review posture a config choice instead of a permanent default, while keeping the safeguards the earlier history says matter.

### Key Decisions

- **KD1. Generalize for any repo, not just this one, and wire the choice into setup** (session-settled: user-directed — chosen over scoping this to only this repo's own filing friction: the goal is every repo using this engine, and the choice belongs in issue #1's setup flow rather than a value someone hand-edits). Governs R1, R2.
- **KD2. A reply counts as human-yes under `required`; the agent doesn't force a separate yes/no question** (session-settled: user-directed — chosen over making the agent ask a direct question about the specific preview before proceeding: lighter-weight, keeps filing conversational). Governs R4.
- **KD3. Approval language under `optional` is read in plain English, not a fixed keyword** (session-settled: user-directed — chosen over requiring a literal token like "approved" before treating a request as pre-approved). Governs R5.
- **KD4. Surprises always escalate, at every tier** (session-settled: user-directed — chosen over letting `agent` push through a possible duplicate or an unexpected board move: the setting governs the routine, no-surprise path only). Governs R8.
- **KD5. The audit comment stays mandatory at every tier, trimmed down from the original format** (session-settled: user-directed — chosen over reserving it for self-confirmed filings only, and over the original judgment-by-judgment breakdown with both dry-run runs' output reproduced verbatim). Governs R9, R10.
- **KD6. One approval covers a whole batch of filings, not each one separately** (session-settled: user-directed — chosen over requiring fresh approval language for every issue when several are filed as part of one task). Governs R6.
- **KD7. The tier lives in `config.json`, not baked into the generated skill file at setup** (session-settled: user-directed — chosen over templating three fixed skill-file variants and having setup pick one to write permanently: keeps the policy in the one place this engine already treats as the source of truth, the same pattern `design_line_required` already uses). Governs R1, R3.

### Requirements

**Configuration**

- R1. `config.json` gains a `human_review_required` field with three legal values — `required`, `optional`, `agent` — defaulting to `required` when the field is absent.
- R2. Issue #1's setup interview asks the repo owner to choose a value for `human_review_required` (see Key Flow F1) and writes the answer to `config.json`, defaulting to `required` on no input.

**Filing procedure**

- R3. The skill template's existing preview-then-confirm procedure reads `human_review_required` from `config.json` before deciding how to answer the confirmation prompt, and follows one of the three branches below rather than always self-confirming.
- R4. Under `required`, after the dry-run preview is shown verbatim, the agent waits for a reply in that conversation and treats a clearly affirmative reply to that specific preview as approval; it does not answer the confirmation prompt on any other basis.
- R5. Under `optional`, the agent treats approval language already present in the request that asked for the filing (e.g., "file this and go ahead") as sufficient and proceeds without waiting for a further reply; absent such language, it behaves as under `required`.
- R6. Under `optional`, one approval statement covering a batch of filings authorizes every filing carried out as part of that same task, not only the first.
- R7. Under `agent`, the agent answers the confirmation prompt itself without waiting for or looking for approval language, subject to R8.
- R8. Regardless of `human_review_required`'s value, the existing stop-on-surprise conditions — a possible duplicate that can't be confidently ruled out, a board position that doesn't match what was asked for, an adopt that unexpectedly MOVES the issue, or the script refusing — always halt the automatic path and require a human answer. No value of the setting authorizes proceeding past a surprise.

**Audit record**

- R9. Every filing, at every value of `human_review_required`, gets an audit comment posted on the issue after the read-back, naming who approved it — the human, via a reply to the shown preview; the human, via approval language already given for the batch under `optional`; or "agent, self-confirmed" — whether the stop-on-surprise checks passed, and the board position filed to.
- R10. The audit comment omits the original design's verbatim reproduction of both dry-run runs' output and its itemized per-judgment breakdown, carrying only the fields in R9.

### Actors

- A1. Repo owner — answers the setup question once and sets the standing review posture in `config.json`.
- A2. Filing agent — reads `human_review_required`, drives `file_issue.sh`, judges affirmative replies and approval language, posts the audit comment.
- A3. Human reviewer — whoever is in the conversation when a preview is shown; usually the repo owner, but not necessarily.

### Key Flows

- **F1. Setup asks for the review tier.** Covers R2.
  - **Trigger:** Issue #1's setup interview reaches the point of writing `config.json`.
  - **Prompt text:**
    ```
    How much should the agent be trusted to confirm a filing on its own?

      1) required (default) — always wait for you to say yes before writing anything.
      2) optional — the agent can confirm on its own if you say so up front
         ("file this and go ahead"); otherwise it waits, same as required.
      3) agent — the agent always confirms on its own once it's shown you the preview.

      A surprise (a possible duplicate, an unexpected board move, or the tool
      refusing) always stops and asks you, no matter which you pick.

    Choice [1]:
    ```
  - **Outcome:** The chosen value (or `required` on no input) is written to `human_review_required` in `config.json`.

- **F2. Filing an issue.** Covers R3, R4, R5, R6, R7, R8, R9.
  - **Trigger:** An issue is ready to file (create or adopt) and `human_review_required` is set in `config.json`.
  - **Steps:** The dry-run preview is shown verbatim to whoever is in the conversation. The confirmation step then branches:
    - **required:** wait for a reply to that preview; a clear affirmative counts as yes.
    - **optional:** if the request that asked for this filing already carried approval language, proceed without waiting — and that same approval covers every other filing in the same task (R6); otherwise, behave as `required`.
    - **agent:** proceed without waiting for or looking for approval language.
  - Then, on every branch: the stop-on-surprise check runs (R8) before the live run; the live run executes; the read-back confirms what landed; the audit comment is posted (R9, R10).

### Acceptance Examples

- AE1. **Given** `human_review_required: required`, **when** the agent shows the dry-run preview and the human's next message says "yes, go ahead," **then** the agent proceeds to the live run, treating that reply as the approval. Covers R4.
- AE2. **Given** `human_review_required: required`, **when** the human's next message doesn't address the preview (changes topic, or no reply comes), **then** the agent does not file — it prints the exact command for a human to run themselves and stops. Covers R4.
- AE3. **Given** `human_review_required: optional` and a request that said "file these three and go ahead, I trust the checks," **when** the agent files all three as part of that task, **then** none of the three waits for further approval, and each still gets its own stop-on-surprise check and audit comment. Covers R5, R6, R8, R9.
- AE4. **Given** `human_review_required: agent` and the dry-run preview shows a possible duplicate the agent can't confidently rule out, **when** the agent reaches the confirmation step, **then** it stops and asks a human, even though the tier would otherwise self-confirm. Covers R7, R8.

### Scope Boundaries

- Out of scope: a new batch-filing flag or capability in `file_issue.sh` itself. R6's "one approval covers a batch" is about approval scope across several separate invocations run back to back in one task, not a new engine feature — the engine still files one issue per invocation.
- Out of scope: forcing an explicit yes/no question under `required` (KD2) or a fixed approval keyword under `optional` (KD3) — both considered and rejected in dialogue.
- Deferred to issue #1: everything about its setup flow other than the wording of F1's question — file-copying automation, prompting for `repo`/`owner`/`project_number`, and the rest of that interview are issue #1's own scope.

### Dependencies / Assumptions

- Depends on issue #1 for the automated setup flow F1 is written for. Until #1 ships, a repo can still hand-set `human_review_required` in `config.json` following the manual setup steps in `docs/SETUP.md`.
- Assumes the existing "no answer, do not file" fallback: under `required` or `optional`-without-prior-approval, if no affirmative reply comes, the agent does not file and instead prints the exact command for a human to run themselves — matching the origin design this procedure was ported from.
- Assumes an explicit in-the-moment instruction overriding the standing setting for one filing (e.g., "wait, let me look at this one first," even under `agent`) is always honored as ordinary conversational deference, not a new mechanism this plan needs to build.
- Assumes existing repos that already generated a static `SKILL.md` from the current (unconditional self-confirm) template are unaffected until they rerun setup; this plan changes the template and the default for new and re-run setups, not files already generated.

### Outstanding Questions

None. Planning resolved both items deferred from the brainstorm: the branching structure for `SKILL.template.md`'s Steps 4-5 (see Planning Contract KTD3 and U2), and where the field is documented — the config field table lives in `docs/SETUP.md`, not `config.example.json` (which carries no inline comments); see U4.

---

## Planning Contract

### Key Technical Decisions

- KTD1. **Validate `human_review_required` in `file_issue.sh`'s existing offline config-validation block**, next to `design_line_required` (`file_issue.sh` around the `DESIGN_LINE_REQUIRED=` read). Default to `required` when the field is absent; refuse — naming the field and its three legal values — before any network call when present but not one of `required`/`optional`/`agent`. Rationale: centralizes the field's legality in the one place this engine already validates config, rather than leaving each consuming skill to guess at valid values. Instantiates R1.
- KTD2. **Add a `{{CONFIG_PATH}}` placeholder to `SKILL.template.md`**, alongside the existing placeholder set. `{{FILE_ISSUE_CMD}}` cannot reliably resolve to a config path: it may be a thin wrapper that bakes `--config` in internally, giving the filled-in skill no path to read `human_review_required` from directly. Rationale: the branching in KTD3 needs an explicit, always-resolvable path to the repo's `config.json`. Instantiates R3.
- KTD3. **One Step 4 with a decision point at the top, not three duplicated Step 4/5 pairs.** The filled-in skill reads `human_review_required` from `{{CONFIG_PATH}}` once, then follows one of three named sub-procedures (`required` / `optional` / `agent`); the preview display, stop-on-surprise check, live run, read-back, and audit comment stay written once since none of them vary by tier. Rationale: avoids tripling shared prose and the drift risk of three near-identical copies. Instantiates R3-R8.

### Assumptions

- `jq` remains available in every environment `file_issue.sh` runs in (already a hard dependency per this repo's `CLAUDE.md` toolset) — KTD1's validation uses it, matching every other config field read.
- `SKILL.template.md` is markdown consumed by an LLM agent, not executable code; U2's correctness is verified by review against the cited Requirements and Acceptance Examples, not by a test run (see U2's Test Scenarios).

---

## Implementation Units

### U1. Validate `human_review_required` in `file_issue.sh`

- **Goal:** `file_issue.sh` reads `human_review_required` from `--config`, defaults it to `required` when absent, and refuses before any network call when the value is present but illegal.
- **Requirements:** R1. KTD1.
- **Dependencies:** None.
- **Files:**
  - `file_issue.sh` (config-loading block, near the existing `DESIGN_LINE_REQUIRED=` read)
  - `tests/test_engine_gating.py` (extend `ConfigValidation`)
- **Approach:**
  1. After the existing `DESIGN_LINE_REQUIRED=` read, add `HUMAN_REVIEW_REQUIRED="$(jq -r '.human_review_required // "required"' "$CONFIG")"`.
  2. Validate `HUMAN_REVIEW_REQUIRED` is exactly one of `required`, `optional`, `agent` (case-sensitive); `die` naming the field, the value found, and the three legal values otherwise — same shape as the existing `--shape must be one of: $SHAPE_NAMES (got: $SHAPE)` refusal.
  3. Do not otherwise consume `HUMAN_REVIEW_REQUIRED` in this script — per KTD3, the tier's behavior is a skill-template (agent) concern, not a script (network-write) concern; the script's own confirmation prompt (`Create it? / Wire it? [y/N]`) is unchanged.
- **Patterns to follow:** The existing `--shape` flag's validation in `file_issue.sh` — it dies naming the value it got and the legal shape names when `--shape` doesn't match the config's `shapes` list (see `tests/test_engine_gating.py`'s `test_unknown_shape`). Both this new field and `--shape` validate offline, before the capability probe.
- **Test Scenarios:**
  - Happy path: config with `"human_review_required": "optional"` is accepted; `--dry-run` still exits 0.
  - Happy path: config with no `human_review_required` key behaves identically to `"human_review_required": "required"` being present (both accepted, no behavior difference visible to the script).
  - Edge case: config with `"human_review_required": "sometimes"` refuses before any network call, naming the field, the bad value, and `required`/`optional`/`agent`.
  - Edge case: config with `"human_review_required": "REQUIRED"` (wrong case) refuses the same way — case is significant.
- **Verification:** `python3 tests/test_engine_gating.py` passes, including the new `ConfigValidation` cases.

### U2. Branch `SKILL.template.md`'s confirmation procedure on `human_review_required`

- **Goal:** The filled-in skill reads `human_review_required` and follows the matching tier's procedure, per Product Contract F2, while keeping the shared preview/stop-on-surprise/read-back/audit-comment prose written once.
- **Requirements:** R3, R4, R5, R6, R7, R8, R9, R10. AE1-AE4. KTD2, KTD3.
- **Dependencies:** None (independent file from U1; keep the three value names identical to U1's).
- **Files:** `SKILL.template.md` (header placeholder-list comment, Step 4, Step 5, and the "what this skill must never do" list)
- **Approach:**
  1. Add `{{CONFIG_PATH}}` to the header comment's placeholder list (KTD2): the repo-relative path to the consuming repo's `config.json`, e.g. `scripts/file-issue.config.json`.
  2. At the top of Step 4, add a decision point: read `human_review_required` from `{{CONFIG_PATH}}` (defaulting to `required` if absent, matching U1), then follow exactly one of three named sub-procedures:
     - **required** — after showing the Step 3 preview verbatim, wait for a reply in the conversation; treat a clearly affirmative reply to that specific preview as approval (R4); anything else (a reply that doesn't address the preview, or none) means don't file — print the exact non-`--dry-run` command for a human to run and stop (matches the existing "if no answer comes back, do not file" fallback already in Step 4).
     - **optional** — if the request that asked for this filing already carried approval language ("file this and go ahead"), read in plain language rather than a fixed keyword (R5), proceed without waiting; that same approval covers every other filing carried out as part of the same task (R6). Absent such language, behave as `required`.
     - **agent** — proceed without waiting for or looking for approval language (R7).
  3. Keep the existing stop-on-surprise list (a possible duplicate that can't be confidently ruled out, a board position that doesn't match what was asked for, an adopt that unexpectedly MOVES the issue, or the script refusing) as a check that runs on every branch before the live run, unconditionally (R8) — do not gate it behind any tier.
  4. Rewrite Step 5's audit-comment instructions to the trimmed, always-posted format (R9, R10; Product Contract KD5): every filing gets a comment naming who approved it (the human, via a reply to the preview; the human, via approval language already given for the batch under `optional`; or `agent, self-confirmed`), whether the stop-on-surprise checks passed, and the position filed to. Remove the existing instructions to reproduce both dry-run runs' output verbatim and the full per-judgment breakdown (duplicate verdict, MOVES-it flag, pre-gate-match check) — those fields are replaced, not kept alongside the trimmed ones.
  5. Update the "what this skill must never do" list's bullet on supplying the confirmation answer — it currently forbids self-supplied confirmation conditioned only on the preview having been shown and audited, with no tier check, so it still reads as blanket permission after step 2 makes that tier-dependent. Align its wording with the branching in step 2: self-supplied confirmation is never permitted under `required` (except as the affirmative-reply path itself), is conditional under `optional`, and is unconditional (subject to the stop-on-surprise check) under `agent`.
- **Technical design (directional):**
  ```
  Step 4 — read the preview, then answer it
    read human_review_required from {{CONFIG_PATH}} (default: required)
    case human_review_required:
      required:  wait for a reply to the Step 3 preview -> affirmative? apply : stop, print command
      optional:  request already approved? apply (covers whole batch) : same as required
      agent:     apply
    always, before applying: stop-on-surprise check -> any hit? escalate to a human, regardless of tier
  Step 5 — read-back, then the audit comment (every tier)
    audit comment: approver, surprise-check result, position filed to
  ```
- **Patterns to follow:** The existing Step 3 ("preview it — not optional") stays unchanged; only Step 4's confirmation logic and Step 5's audit-comment content change.
- **Test Scenarios:** Test expectation: none -- `SKILL.template.md` is markdown consumed by an LLM agent, not executable code, and this repo's test suite intentionally does not scan skill-template prose (see `tests/test_engine_skill.py`'s docstring: that conformance-scan concept was dropped at extraction because this repo "has no SKILL.md and no skill-wrapper concept"). Verify by re-reading the rewritten Steps 4-5 against R3-R10 and AE1-AE4 line by line.
- **Verification:** Manual review against Product Contract R3-R10 and AE1-AE4; confirm no leftover reference to the old unconditional "you may supply that answer yourself" permission remains.

### U3. Document the setting in `docs/CONCEPTS.md`

- **Goal:** `docs/CONCEPTS.md`'s guard explanations describe `human_review_required` accurately, replacing the current unconditional framing.
- **Requirements:** R1, R3, R8. Product Contract KD1, KD4.
- **Dependencies:** U1, U2 (describe their shipped behavior; keep field name and values identical).
- **Files:** `docs/CONCEPTS.md`
- **Approach:**
  1. Rewrite the "Nothing Writes Without a Human Seeing the Real Preview First" section: it currently states self-confirmation as always available once the preview is shown. Replace with a description of the three tiers and their defaults, plus the always-on stop-on-surprise carve-out (R8).
  2. Extend the "Two Guards Are Intentionally Config-Shaped" section to name `human_review_required` as a third config-shaped guard, alongside `shapes` and `design_line_required`.
- **Test Scenarios:** Test expectation: none -- documentation content, not executable.
- **Verification:** Manual review: the section accurately names all three values and their defaulting behavior, and does not contradict `docs/SETUP.md`'s field table (U4).

### U4. Document the field in `docs/SETUP.md`

- **Goal:** A repo owner setting up this tool by hand today (before issue #1 automates setup) can find and understand `human_review_required` the same way they already find `design_line_required`.
- **Requirements:** R1, R2. Product Contract F1, KD1, KD7.
- **Dependencies:** U1 (same field name and values).
- **Files:** `docs/SETUP.md`
- **Approach:**
  1. Add a row to the config schema table for `human_review_required`: type string, values `required` (default) / `optional` / `agent`, one-line meaning matching R1/R4/R5/R7.
  2. Add the setup-time guidance from Product Contract F1's prompt text as prose immediately following the table — framed as what to consider when choosing a value by hand, since issue #1's automated interview does not exist yet. This is the manual-setup equivalent of F1; when issue #1 ships, its interview supersedes this prose as the primary path, but the table row stays.
- **Test Scenarios:** Test expectation: none -- documentation content, not executable.
- **Verification:** Manual review: the table row and prose match U1's actual default and legal values exactly.

---

## Verification Contract

| Command | Applies to | Done signal |
|---|---|---|
| `python3 tests/test_engine_gating.py` | U1 | All tests pass, including new `ConfigValidation` cases for `human_review_required`. |
| `python3 tests/test_engine_skill.py` | U1, U2 | Passes unchanged — U1 doesn't touch the flag parser this file scans, and U2 is intentionally out of this scan's scope (see U2's Test Scenarios). |
| Manual review against Product Contract | U2, U3, U4 | Every R3-R10 and AE1-AE4 requirement is visibly satisfied in the rewritten `SKILL.template.md` text, and `docs/CONCEPTS.md` / `docs/SETUP.md` describe the same three values and defaults as `file_issue.sh` actually validates. |

No CI is configured in this repo yet (tracked separately as issue #4); run both test files locally before committing.

## Definition of Done

- All four units (U1-U4) complete.
- `python3 tests/test_engine_gating.py` and `python3 tests/test_engine_skill.py` both pass.
- `file_issue.sh --help`'s behavior is unchanged for every existing flag; only the new config-field validation is added.
- `docs/CONCEPTS.md`, `docs/SETUP.md`, and `SKILL.template.md` describe `human_review_required`'s three values and `required` default consistently with each other and with `file_issue.sh`'s actual validation.
- No leftover reference to the old unconditional self-confirm permission remains in `SKILL.template.md`.
- No dead-end or experimental code from an abandoned approach remains in the diff.

---

## How This Work Fits Together

<!-- ce-section: work-relationships -->

This plan owns the `human_review_required` setting and the filing procedure's branching behavior. It is not a redesign of issue #1's setup flow as a whole.

- Issue #1 (automated setup) — **Depends on:** this plan's F1 supplies the exact question issue #1's interview should ask when it writes `config.json`; the rest of #1's interview (copying files, prompting for repo/owner/project number) is unaffected and unplanned here.
- This plan **can proceed independently of** #1 shipping: the config field and the template branching can be built and hand-set today; #1 only adds the interview that asks the question automatically.

---

## Sources / Research

- `file_issue.sh` — the existing preview/confirm/read-back mechanism and the `Create it? / Wire it? [y/N]` prompt whose answering logic this plan makes conditional (the prompt itself is unchanged; see U1).
- `SKILL.template.md` (Steps 3-5) — the already-shipped, currently unconditional self-confirmation procedure (verbatim preview, self-confirm, stop-on-surprise list, two-run comparison, audit comment) this plan makes configurable.
- `docs/CONCEPTS.md`, "What This Enforces" — states the self-confirm design philosophy and that `design_line_required` is the existing precedent for a config-shaped guard, which R1/KD7 follow.
- `docs/solutions/design-patterns/make-the-lossy-half-recoverable-before-removing-the-gate.md` — the enumerate-what-the-gate-enforces method behind the original decision to allow self-confirmation; R8's stop-on-surprise requirement preserves the same enumeration regardless of tier.
- `docs/solutions/best-practices/the-exemption-that-makes-a-guard-writable-is-the-hole.md` — history of this project's confirmation step being weakened while looking intact; motivates keeping the audit comment (R9) mandatory rather than conditional.
- `photo-consolidation`'s `.claude/skills/file-issue/SKILL.md` — the origin implementation this repo's template was ported from; its audit-comment format (full verbatim run dumps plus a per-judgment breakdown) is what R10 trims.
- `docs/CONCEPTS.md`, `docs/SETUP.md` — a docs restructure landed on `main` after the brainstorm dialogue: the "What this enforces" prose (U3's target) now lives in `CONCEPTS.md`, and the config field table (U4's target) now lives in `SETUP.md`, not `README.md` as the brainstorm's Sources originally cited.
- `tests/test_engine_gating.py`'s `ConfigValidation` class (`file_issue.sh` config-field validation tests) — the pattern U1's new test cases follow.
- `tests/test_engine_skill.py`'s docstring — records that this repo's extraction deliberately dropped the origin project's `SKILL.md` prose-conformance scan ("no SKILL.md and no skill-wrapper concept"); grounds U2's `Test expectation: none` rather than inventing a new scan.
