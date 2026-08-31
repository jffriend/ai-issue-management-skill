---
title: Configurable Human Review - Plan
type: feat
date: 2026-08-31
topic: configurable-human-review
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
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
- R6. One approval statement covering a batch of filings authorizes every filing carried out as part of that same task, not only the first.
- R7. Under `agent`, the agent answers the confirmation prompt itself without waiting for or looking for approval language, subject to R8.
- R8. Regardless of `human_review_required`'s value, the existing stop-on-surprise conditions — a possible duplicate that can't be confidently ruled out, a board position that doesn't match what was asked for, an adopt that unexpectedly MOVES the issue, or the script refusing — always halt the automatic path and require a human answer. No value of the setting authorizes proceeding past a surprise.

**Audit record**

- R9. Every filing, at every value of `human_review_required`, gets an audit comment posted on the issue after the read-back, naming who approved it (the human, via their affirmative reply, or "agent, self-confirmed"), whether the stop-on-surprise checks passed, and the board position filed to.
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

- Depends on issue #1 for the automated setup flow F1 is written for. Until #1 ships, a repo can still hand-set `human_review_required` in `config.json` following the manual setup steps in `README.md`.
- Assumes the existing "no answer, do not file" fallback: under `required` or `optional`-without-prior-approval, if no affirmative reply comes, the agent does not file and instead prints the exact command for a human to run themselves — matching the origin design this procedure was ported from.
- Assumes an explicit in-the-moment instruction overriding the standing setting for one filing (e.g., "wait, let me look at this one first," even under `agent`) is always honored as ordinary conversational deference, not a new mechanism this plan needs to build.
- Assumes existing repos that already generated a static `SKILL.md` from the current (unconditional self-confirm) template are unaffected until they rerun setup; this plan changes the template and the default for new and re-run setups, not files already generated.

### Outstanding Questions

- **Deferred to Planning:** The exact branching prose to insert into `SKILL.template.md`'s existing Steps 3-5, and whether `config.example.json`'s field-documentation table needs a new row for `human_review_required` (mechanical, no open product judgment).

---

## How This Work Fits Together

<!-- ce-section: work-relationships -->

This plan owns the `human_review_required` setting and the filing procedure's branching behavior. It is not a redesign of issue #1's setup flow as a whole.

- Issue #1 (automated setup) — **Depends on:** this plan's F1 supplies the exact question issue #1's interview should ask when it writes `config.json`; the rest of #1's interview (copying files, prompting for repo/owner/project number) is unaffected and unplanned here.
- This plan **can proceed independently of** #1 shipping: the config field and the template branching can be built and hand-set today; #1 only adds the interview that asks the question automatically.

---

## Sources / Research

- `file_issue.sh` — the existing preview/confirm/read-back mechanism and the `Create it? / Wire it? [y/N]` prompt this plan makes conditional.
- `SKILL.template.md` (Steps 3-5) — the already-shipped, currently unconditional self-confirmation procedure (verbatim preview, self-confirm, stop-on-surprise list, two-run comparison, audit comment) this plan makes configurable.
- `README.md`, "What this enforces" — states the self-confirm design philosophy and that `design_line_required` is the existing precedent for a config-shaped guard, which R1/KD7 follow.
- `docs/solutions/design-patterns/make-the-lossy-half-recoverable-before-removing-the-gate.md` — the enumerate-what-the-gate-enforces method behind the original decision to allow self-confirmation; R8's stop-on-surprise requirement preserves the same enumeration regardless of tier.
- `docs/solutions/best-practices/the-exemption-that-makes-a-guard-writable-is-the-hole.md` — history of this project's confirmation step being weakened while looking intact; motivates keeping the audit comment (R9) mandatory rather than conditional.
- `photo-consolidation`'s `.claude/skills/file-issue/SKILL.md` — the origin implementation this repo's template was ported from; its audit-comment format (full verbatim run dumps plus a per-judgment breakdown) is what R10 trims.
