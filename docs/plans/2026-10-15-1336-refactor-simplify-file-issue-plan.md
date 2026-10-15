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
- **Open blockers:** None. Issue #14 is blocked on this work.

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

**Deferred to Planning**

- How R5 works mechanically: the engine stopping before writing when matches exist, or the agent running a preview-only check first. Either way, a run with no matches must still file in one run (R2).
- Whether the "file anyway" path in R7 needs an engine flag or is a plain re-run.

### Sources / Research

- Issue #14 (REST port) and its comment measuring REST blocked-by links.
- Pluckd's cloud-session plan, `docs/plans/2026-10-15-1312-chore-cloud-sessions-workflow-plan.md` in the pluckd repo: position is best-effort, issue work is required.
- `docs/solutions/` holds the four learnings behind the read-back and delta-write guards that R14 keeps.
- `docs/plans/2026-08-31-002-feat-configurable-human-review-plan.md` introduced the three tiers this plan replaces.
