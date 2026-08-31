---
title: Friendly User Documentation - Plan
type: docs
date: 2026-08-31
topic: friendly-user-docs
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
---

# Friendly User Documentation - Plan

## Goal Capsule

- **Objective:** Give this repo user-facing documentation that's approachable for first-time setup and clearly explains the tool's capabilities and the reasoning behind them, split across a slim `README.md` and three focused docs.
- **Product authority:** Brainstorm dialogue with the repo owner (2026-08-31); decisions below are session-settled.
- **Open blockers:** None. Ready for planning.

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
