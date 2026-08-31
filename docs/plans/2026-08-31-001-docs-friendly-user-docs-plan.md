---
title: Friendly User Documentation - Plan
type: docs
date: 2026-08-31
topic: friendly-user-docs
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
execution: code
---

# Friendly User Documentation - Plan

## Goal Capsule

- **Objective:** Give this repo user-facing documentation that's approachable for first-time setup and clearly explains the tool's capabilities and the reasoning behind them, split across a slim `README.md` and three focused docs.
- **Product authority:** Brainstorm dialogue with the repo owner (2026-08-31); decisions below are session-settled.
- **Open blockers:** None. Ready for implementation.
- **Execution profile:** Standard docs change — no special engine routing; `ce-work`'s default flow applies.

## Product Contract

### Summary

A friendly, style-guide-driven rewrite of this repo's user-facing documentation: a slim `README.md` that states the tool's value and capabilities in a few sentences and points elsewhere, plus three new docs — `docs/SETUP.md`, `docs/USAGE.md`, and `docs/CONCEPTS.md` — that carry the install walkthrough, the day-to-day command reference, and the why-it-works explanation.

### Problem Frame

The current `README.md` covers setup, capabilities, and the reasoning behind every guard, but in dense, technical prose written for someone already deep in the problem. It also grew organically as the tool was extracted from `photo-consolidation`, so parts of it may no longer describe the behavior the owner actually wants going forward. Rewriting it in a clearer, friendlier voice — split by what a reader actually showed up asking — is also the occasion to review that organically-grown behavior before it gets re-documented as settled.

### Requirements

**Structure and style**

- R1. The documentation set consists of four files: a slimmed `README.md`, `docs/SETUP.md`, `docs/USAGE.md`, and `docs/CONCEPTS.md`.
- R2. `README.md` states the tool's value proposition and a short summary of its capabilities, then points to `docs/SETUP.md`, `docs/USAGE.md`, and `docs/CONCEPTS.md` for everything else — it does not go deep on any one topic itself.
- R3. All four documents follow the attached style guide: warm, active-voice, plain-language tone; strict ATX heading hierarchy; paragraphs of at most 3 sentences; single-sentence bullet steps; `inline code` or **bold** for UI components, filenames, and variables; sequential numbering for step-by-step procedures; language-tagged code blocks; no nested lists deeper than 2 levels; no placeholder text; no robotic filler words ("Furthermore," "Delve," "Moreover," "In summary," "Crucial").

**Document content**

- R4. `docs/SETUP.md` walks a first-time reader through adding the tool to a consuming repo end to end: adding the submodule, writing `config.json` from `config.example.json`, copying and filling in `SKILL.template.md`, and initializing the submodule in a fresh checkout — the same ground as today's README "Setup in a consuming repo" section, restructured as a friendly numbered walkthrough.
- R5. `docs/USAGE.md` is a day-to-day task reference covering create mode and adopt mode, the four placement answers, and what `--dry-run` shows before anything is confirmed.
- R6. `docs/CONCEPTS.md` explains what the tool does and why it works the way it does: the vocabulary (placement answers, adopt, half-wired, read-back) and the reasoning behind each guard in today's README "What this enforces" section.
- R7. `docs/CONCEPTS.md` illustrates guards with brief, current-behavior examples and links to `docs/solutions/` as the source of record, rather than re-narrating the full postmortems that already live there.

**Scope of the rewrite**

- R8. `SKILL.template.md` is not rewritten in this effort. It stays a precise instruction template for an agent reader, not a person reading start to finish.
- R9. `docs/solutions/` content is not modified by this effort.

**Design-question handling during writing**

- R10. When writing surfaces a small, low-stakes design question, it's decided on the spot and the affected doc reflects the resolved behavior.
- R11. When writing surfaces a design question that would actually change tool behavior, or is a real judgment call, it is not decided inline. It's logged and filed as a GitHub issue on the project board, per this repo's board convention, and the doc keeps describing today's actual behavior rather than the reconsidered version.

### Key Decisions

- **Split into four documents, not one.** Setup stays a terse walkthrough; Concepts gets room for the why-it-works explanation without either dragging on the other. Governs R1, R4, R5, R6. (session-settled: user-directed — chosen directly over a single combined guide and a two-file split.)
- **`README.md` becomes a slim landing page.** A value statement, a short capability summary, and pointers to the rest — not a place any one topic goes deep. Governs R2. (session-settled: user-directed.)
- **`SKILL.template.md` and `docs/solutions/` stay untouched.** The friendly rewrite is for human-facing docs only; the template's reader is an agent, and `docs/solutions/` is this repo's separate learnings store. Governs R8, R9. (session-settled: user-directed.)
- **Design questions surfaced while writing are triaged by stakes, not all resolved live.** Small calls happen in the moment; anything that would actually change tool behavior is logged and filed as a board issue instead of decided mid-write. The accepted consequence is that `docs/CONCEPTS.md` may describe behavior that's under active reconsideration until its filed issue is resolved. Governs R10, R11. (session-settled: user-directed.)

### Acceptance Examples

- AE1. **Covers R10, R11.** Given a design question surfaces while writing `docs/CONCEPTS.md`, when it's low-stakes and wouldn't change tool behavior, then it's decided immediately and the doc reflects the resolution. When it would change tool behavior or is a real judgment call, then it's logged, filed as a GitHub issue on the project board, and the doc continues describing today's actual behavior.

### Success Criteria

- SC1. Someone doing first-time setup can complete it end to end using only `docs/SETUP.md`, without needing to read `docs/CONCEPTS.md`, `docs/USAGE.md`, or the source code.
- SC2. Every sentence and structural choice across `README.md`, `docs/SETUP.md`, `docs/USAGE.md`, and `docs/CONCEPTS.md` matches the attached style guide — voice, heading hierarchy, paragraph length, list formatting, code-block language tags, and no filler words.

### Scope Boundaries

- Rewriting `SKILL.template.md`'s voice or structure is out of scope.
- Changing `docs/solutions/` content is out of scope.
- Changing what the tool actually does — `file_issue.sh`, `board.sh`, `issue_text.py` behavior — is out of scope for this effort. Design questions that would change behavior are deferred to filed issues and separate planning, not resolved here.

---

## Planning Contract

**Product Contract preservation:** unchanged. This pass adds the Planning Contract, Implementation Units, Verification Contract, and Definition of Done below; no Requirement, Key Decision, or ID above was altered.

### Key Technical Decisions

- KTD1. **Every internal link becomes a cross-file link where its target heading moved.** `README.md` today links to headings like "Placement answers," "Half-wired," "Read-back," and "Config schema" within itself. Once those headings live in `docs/CONCEPTS.md` or `docs/SETUP.md`, every such link is rewritten to point at the file that now owns the heading (for example, `CONCEPTS.md#half-wired`), so no doc is left pointing at a heading that no longer exists in it. Governs R1, R2, R6.
- KTD2. **The "why this exists" narrative splits, not duplicates.** `README.md` keeps a 2-3 sentence compressed version of the motivation (writing directly to the board skips bookkeeping). The fuller narrative — the audit findings (sixteen stated ordering constraints with no board link, one item forty positions ahead of what made it unsafe) — moves into `docs/CONCEPTS.md` as the opening context for why the guards exist. Neither doc repeats the other's version. Governs R2, R6.
- KTD3. **Each guard gets its own heading in `docs/CONCEPTS.md`.** Today's README states nine bold-lead paragraph bullets under "What this enforces" — one of them ("Two guards are intentionally config-shaped") reads as a cross-cutting note about two of the others rather than a distinct guard, so eight or nine headings are both defensible. The style guide's ATX heading hierarchy fits better with one heading per guard either way, giving each room for a short current-behavior example. Governs R3, R6.
- KTD4. **`docs/solutions/best-practices/the-exemption-that-makes-a-guard-writable-is-the-hole.md` is not linked from `docs/CONCEPTS.md`.** It documents the SKILL.md conformance test suite's own guard integrity, not a runtime guard in `file_issue.sh` — it doesn't map to any of the four vocabulary terms or the eight guards CONCEPTS.md covers. Governs R7.
- KTD5. **The config-schema field table moves into `docs/SETUP.md` as a table, not prose.** The field-by-field types and conditional relationships (e.g., `plan_dir` is required only when `design_line_required: true`) are exactly the uniform, comparative shape the style guide's own allowance for tables fits. Governs R3, R4.

### Assumptions

- README's nine "What this enforces" bullets map to either eight or nine headings in `docs/CONCEPTS.md`, depending on whether "Two guards are intentionally config-shaped" drafts as its own heading or folds into the two guards it's actually describing — that's a small-stakes call under R10, decide it while writing, no need to log it.

### Sequencing

`docs/SETUP.md`, `docs/USAGE.md`, and `docs/CONCEPTS.md` (U1-U3) have no content dependencies on each other and can be drafted in any order. Their KTD1 cross-file links may need a short follow-up pass once all three files exist, since a link drafted before its target heading is written can't be verified until then; the Verification Contract's link-check step catches this regardless of drafting order. `README.md` (U4) depends on all three, since its pointers must resolve to real headings in files that already exist.

---

## Implementation Units

### U1. Write `docs/SETUP.md`

- **Goal:** Give a first-time reader a friendly, accurate, numbered walkthrough for adding this tool to a consuming repo.
- **Requirements:** R3, R4, R10, R11
- **Dependencies:** None
- **Files:** `docs/SETUP.md` (new); `README.md`, `SKILL.template.md`, `config.example.json` (read-only sources)
- **Approach:**
  1. Move README's "Setup in a consuming repo" section into a numbered 1.-4. procedure: add and pin the submodule, write `config.json` from `config.example.json`, copy and fill in `SKILL.template.md`, initialize the submodule in a fresh checkout. Preserve every command (`git submodule add`, `git submodule update --init`, etc.) and every `{{PLACEHOLDER}}` name exactly as `SKILL.template.md` defines them.
  2. Move the config-schema field table verbatim in meaning (KTD5), keeping the `project_id` GraphQL-lookup instruction and the `plan_dir`/`design_line_required` conditional relationship exact.
  3. Rewrite surrounding prose to the style guide's voice, heading, paragraph, and bullet rules. Do not change the semantic content of the table or the command steps while doing so.
  4. Apply KTD1 to any link in this file that now targets a heading in another doc.
  5. If a design question surfaces while writing, apply R10/R11 (see U3 step 7 for the same protocol): decide small calls on the spot, log and file a board issue for anything that would change tool behavior.
- **Patterns to follow:** `bash` for every code fence (the only language used in the current docs); inline code for filenames, flags, and field names; repo-relative paths with no leading `./`.
- **Test scenarios:** Test expectation: none -- pure documentation content; no test in `tests/` references `README.md` or any `docs/*.md` file (confirmed by search).
- **Verification:** A reader unfamiliar with the tool can follow `docs/SETUP.md` alone and end with a valid `config.json` and a filled-in `SKILL.md`, without opening `README.md` or the source scripts (SC1). Every command and placeholder name matches `SKILL.template.md` and `config.example.json` exactly.

### U2. Write `docs/USAGE.md`

- **Goal:** Give a day-to-day task reference for create mode, adopt mode, the four placement answers, and `--dry-run`.
- **Requirements:** R3, R5, R10, R11
- **Dependencies:** None
- **Files:** `docs/USAGE.md` (new); `README.md` (read-only source)
- **Approach:**
  1. Move README's "Using it" section (create vs. adopt, both taking the four placement answers, `--dry-run` behavior) into `docs/USAGE.md`, restructured to the style guide.
  2. Keep the pointer to `SKILL.template.md` as the authority for the full agent-driven procedure — do not re-derive its steps here (R8 keeps `SKILL.template.md` out of scope).
  3. Preserve the asymmetric "none" rule exactly: `blocked-by` and `blocks` accept the literal word `none`; `parent` and `position` have no "none" value (position always needs a real target or `top`; parent needs an explicit no-parent flag).
  4. Apply KTD1 to any link in this file that now targets a heading in another doc.
  5. If a design question surfaces while writing, apply R10/R11 (see U3 step 7 for the same protocol): decide small calls on the spot, log and file a board issue for anything that would change tool behavior.
- **Patterns to follow:** Same as U1.
- **Test scenarios:** Test expectation: none -- pure documentation content; no test in `tests/` references `README.md` or any `docs/*.md` file.
- **Verification:** A reader can determine, from `docs/USAGE.md` alone, which four answers `file_issue.sh` requires and what `--dry-run` shows before anything is confirmed. The asymmetric-none rule reads unambiguously against README's current wording.

### U3. Write `docs/CONCEPTS.md`

- **Goal:** Explain the tool's vocabulary and the reasoning behind each guard, in a friendly, example-driven voice, without changing what any guard is claimed to do.
- **Requirements:** R3, R6, R7, R10, R11
- **Dependencies:** None
- **Files:** `docs/CONCEPTS.md` (new); `README.md` (read-only source); `docs/solutions/best-practices/when-empty-is-a-legal-answer-a-guard-must-check-shape-not-emptiness.md`, `docs/solutions/developer-experience/gh-issue-edit-is-not-idempotent-write-a-delta-not-a-set.md`, `docs/solutions/design-patterns/make-the-lossy-half-recoverable-before-removing-the-gate.md` (read-only sources)
- **Approach:**
  1. Open with README's "Vocabulary" section (placement answers, adopt, half-wired, read-back) as the glossary.
  2. Add the fuller "why this exists" narrative (KTD2) as context for why the guards exist, before naming the guards themselves.
  3. Give each guard from README's "What this enforces" section its own heading (KTD3), with a short current-behavior example where README's own wording already supplies one — the `{"message":"Not Found"}` read-back example, the "Target issue has already been taken" adopt error, the move-recorded-comment example.
  4. Replace README's "Two historical bugs" section with short pointers into `docs/solutions/` instead of re-narrating: link the read-back guard to `when-empty-is-a-legal-answer-a-guard-must-check-shape-not-emptiness.md`, the adopt-delta guard to `gh-issue-edit-is-not-idempotent-write-a-delta-not-a-set.md`, and the adopt-position/move-recorded-comment guard to `make-the-lossy-half-recoverable-before-removing-the-gate.md` (R7). All three postmortems are already summarized in the "What this enforces" wording, so no separate historical-bugs section is needed here.
  5. Do not link `docs/solutions/best-practices/the-exemption-that-makes-a-guard-writable-is-the-hole.md` (KTD4).
  6. Preserve every precision point named in Risks & Dependencies below verbatim in meaning.
  7. While drafting, apply R10/R11 live: decide small wording or scope calls on the spot; log and file a GitHub issue on the project board for anything that would change what a guard actually does, and keep this doc describing today's actual behavior in the meantime.
  8. Apply KTD1 to any link in this file that now targets a heading in another doc.
- **Patterns to follow:** Same as U1, plus KTD3's one-heading-per-guard structure.
- **Test scenarios:** Test expectation: none -- pure documentation content; no test in `tests/` references `README.md` or any `docs/*.md` file.
- **Verification:** Every factual claim about a guard's behavior matches the corresponding `docs/solutions/` entry and README's current wording. AE1 holds: any design question logged while writing is filed as a board issue, and the doc describes only today's actual behavior.

### U4. Slim `README.md`

- **Goal:** Turn `README.md` into a landing page — value statement, short capability summary, scope, and pointers to the other three docs.
- **Requirements:** R1, R2, R3, R10, R11
- **Dependencies:** U1, U2, U3 (its pointers must resolve to real headings that already exist)
- **Files:** `README.md` (rewrite in place)
- **Approach:**
  1. Keep the title and one-line tagline near-verbatim.
  2. Compress "Why this exists" to 2-3 sentences (KTD2) — the board-bookkeeping problem, no audit numbers.
  3. Keep the capability summary (engine plus two templates, no backend abstraction, submodule-only distribution) and the Scope bullets (GitHub Issues/Projects v2 only, filing and wiring only, no package distribution) as short bullets.
  4. Replace every other current section with a pointer to the file that now owns it: `docs/SETUP.md`, `docs/USAGE.md`, `docs/CONCEPTS.md`.
  5. Apply KTD1: rewrite every link that now targets a heading in another file, and confirm no same-file anchor still points at a heading that moved.
  6. If a design question surfaces while writing, apply R10/R11 (see U3 step 7 for the same protocol): decide small calls on the spot, log and file a board issue for anything that would change tool behavior.
- **Patterns to follow:** Same as U1.
- **Test scenarios:** Test expectation: none -- pure documentation content; no test in `tests/` references `README.md` or any `docs/*.md` file.
- **Verification:** `README.md` stands alone as a landing page — a first-time reader gets the value statement and capability summary without opening another file — and every link in it resolves to a real heading in its target file.

---

## Risks & Dependencies

Research against `docs/solutions/` and the current `README.md` found these precision points. A friendly rewrite must preserve each one in meaning, not just in tone:

- The three-state read-back (present / genuinely absent / could-not-look) — only the *read* is retried on a bounded wait, never the write.
- Delta-write on adopt: only missing relationships are sent, because `gh issue edit` fails the whole call on a re-sent existing relationship (exact quoted errors: "Target issue has already been taken," "Issue may not contain duplicate sub-issues"). Use these exact strings if CONCEPTS.md illustrates this guard — don't paraphrase them.
- Adopt refuses on parent/blocked-by/blocks mismatches but never on position — it always moves the issue to the stated position and records the move afterward as a comment.
- A truncated board listing is a hard stop, not a "best effort" warning.
- Self-confirmation is permitted only after the dry-run preview has been shown to a human **verbatim** — never summarized or paraphrased. This exact word ("verbatim") is load-bearing in both `README.md` and `SKILL.template.md`.
- Exactly two guards vary by config — the shape/label vocabulary and `design_line_required`. Every other guard is unconditional across all consuming repos; a rewrite implying broader configurability would misstate the tool's core guarantee.
- The `gh` version-probe resolves to three states — "present," "absent," "undeterminable" — not a simple yes/no capability check.

---

## Verification Contract

No automated test in `tests/` (`test_engine_gating.py`, `test_engine_issue_text.py`, `test_engine_skill.py`) references `README.md` or any `docs/*.md` file, so this plan's verification is manual review, not a test run:

- Run `grep -niE 'furthermore|delve|moreover|in summary|crucial' README.md docs/SETUP.md docs/USAGE.md docs/CONCEPTS.md` and confirm no matches (R3, SC2).
- Read each of the four files and confirm: no heading skips a level in the ATX hierarchy, no paragraph exceeds 3 sentences, every step procedure uses sequential numbering with single-sentence bullets, every code fence names a language, and no list nests deeper than 2 levels (R3, SC2).
- Confirm every internal link resolves to a real heading in its target file — no link points at a heading that moved without being rewritten (KTD1).
- Walk through `docs/SETUP.md` as a first-time reader would, without referring to any other file in the repo, and confirm it's enough to reach a working setup (SC1).
- Cross-check every guard description in `docs/CONCEPTS.md` against its `docs/solutions/` entry and README's current wording (Risks & Dependencies above).

---

## Definition of Done

- `README.md`, `docs/SETUP.md`, `docs/USAGE.md`, and `docs/CONCEPTS.md` all exist with content satisfying R1-R11.
- The Verification Contract checks above all pass.
- `SKILL.template.md`, `docs/solutions/`, `file_issue.sh`, `board.sh`, and `issue_text.py` are unchanged (R8, R9, Scope Boundaries).
- Any design question logged under R11 during writing has a corresponding GitHub issue filed on the project board, referenced from wherever it was logged.
- No leftover draft or scratch files from the writing process remain in the diff.
