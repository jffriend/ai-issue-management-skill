---
title: Issue Templates - Plan
type: feat
date: 2026-08-31
topic: issue-templates
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: code
---

# Issue Templates - Plan

## Goal Capsule

- **Objective:** Define this repo's issue-body shapes (work, bug, investigation) and how they're delivered, replacing the inconsistent structure issues 1, 5, 6, and 7 currently use, and ship a copy consuming repos can adopt and customize.
- **Product authority:** [Issue 6](https://github.com/jffriend/ai-issue-management-skill/issues/6), plus this conversation's decisions on shape structure and field-vs-body placement, informed by `photo-consolidation`'s existing `.github/ISSUE_TEMPLATE/` set.
- **Open blockers:** None. All inputs needed to plan this work were resolved in dialogue.

## Product Contract

### Summary

Three issue shapes — work, bug, investigation — each with its own required body sections, replace this repo's single ad hoc "work" shape. Placement (parent/position/blocked-by/blocks) and size stay out of the body entirely: placement is already written to native GitHub fields by `file_issue.sh`, and size becomes a new native Project field. Each shape ships both as a GitHub-native template (for the web "New issue" picker) and as a matching skeleton used before `file_issue.sh`, plus a default copy for consuming repos.

### Requirements

**Shapes and templates**

- R1. This repo's `config.json` gains three issue shapes — `work`, `bug`, `investigation` — replacing the current single `work` shape.
- R2. The `work` shape's body has What / How / Impact if skipped / Done when, and covers both feature work and technical debt — there is no separate tech-debt structure.
- R3. The `bug` shape's body has What's broken / Repro steps / Expected vs Actual / Impact if skipped / Done when, independent of the `work` shape's structure.
- R4. The `investigation` shape's body has Question to answer / Recommendation / Impact if skipped / Write-up link / Done when. It carries no actor restriction — the agent or the user can carry it out, unlike `photo-consolidation`'s Joe-only `decision` shape.
- R5. None of the three shapes' bodies includes a "Binds this work" section or a "Placement" section.
- R6. Each shape's body may include a `Design:` line linking to the plan section that holds the how, following this repo's existing `design_line_required` convention (verified: `file_issue.sh` parses `Design:` mechanically to detect plan-derived issues).

**Fields over body text**

- R7. A `Size` single-select field (options: XS, S, M, L, XL) is added to this repo's GitHub Project board. Verified: `gh project field-list 3 --owner jffriend` currently shows no Size or Estimate field.
- R8. No template asks for a size value in the issue body. Size is set only through the `Size` project field.
- R9. What each size option means in time is documented separately from the templates (not baked into the field's option labels or into template prose), and is a setting each consuming repo — including this one — defines for itself.

**Delivery**

- R10. Each shape ships as a GitHub-native template file under `.github/ISSUE_TEMPLATE/`, so GitHub's web "New issue" picker offers all three shapes.
- R11. Each shape also ships as a body-skeleton file whose content matches its native-template body, for the agent to fill in and pass to `file_issue.sh --body-file`.
- R12. Every native-template file carries a visible reminder that filing through GitHub's web UI skips this tool's guardrails — board-neighborhood preview, duplicate check, relationship wiring — and that `file_issue.sh` is the supported path. This does not close the gap, only documents it (see Scope Boundaries).
- R13. The same three shapes ship as a default template set under this repo's existing "consuming repos copy and edit" convention (alongside `config.example.json` and `SKILL.template.md`), for other repos to copy into their own `.github/ISSUE_TEMPLATE/` and skeleton locations and edit to their own conventions.

### Key Decisions

- **Bug is fully separate from work, not a shared-core variant.** (session-settled: user-directed — chosen over folding bug into a shared What/Impact/Done-when core with add-on sections: bugs need Repro steps and Expected vs Actual that features and tech debt don't carry.) Governs R3.
- **Feature work and tech debt share one `work` shape.** (session-settled: user-directed — chosen over a separate tech-debt structure: tech debt is a flavor of work, not a structurally distinct thing.) Governs R2.
- **`investigation` replaces `photo-consolidation`'s Joe-only `decision` shape.** (session-settled: user-directed — chosen over reusing the Joe-only pattern: this tool's investigations aren't restricted to one person.) Governs R4.
- **Placement and size stay field-only, never body text.** (session-settled: user-directed — chosen over a body-text Size line like `photo-consolidation` uses: matches this tool's existing pattern of writing parent/blocked-by/blocks to native GitHub fields via `file_issue.sh`'s `--parent`/`--blocked-by`/`--blocking` flags rather than body prose.) Governs R5, R7, R8.
- **"Binds this work" is dropped entirely, not kept as a narrower procedural-only section.** (session-settled: user-directed — chosen over keeping free-text constraints: most of what `photo-consolidation`'s "Binds this work" captured isn't a link to another issue at all (e.g. "quit Mylio first"), and the part that is — ordering language naming another issue — is better solved by a dedicated prose-scan-and-enforce check than a free-text field.) Governs R5.

### Success Criteria

- A filled-in template reads at the length and register of issue 5's post-rewrite body (this repo's own stated gold standard) — short enough that following the template is easier than skipping it.
- A person or agent filing a bug, work item, or investigation can tell which shape to use from the three body structures alone, without needing to read this plan.

### Scope Boundaries

- The prose-scan-and-enforce check — detecting ordering language that names another issue and refusing if it doesn't match the `--blocked-by`/`--blocks` flags given — is not built here. It should be filed as its own follow-up issue.
- Actually writing a size value onto a specific issue (a `file_issue.sh` maintenance action) stays with issue 7, which already claims it.
- The concrete time-boundary meaning of each size option for this repo (what "M" means in hours) is not decided here — deferred to setup/documentation.
- `photo-consolidation`'s `your-run` shape (a command only a human can run) is not carried over — this repo has no analogous irreversible-script pattern today.

### Dependencies / Assumptions

- Assumes the installed `gh` CLI supports `gh project field-create` for adding a single-select field to a Projects v2 board; `file_issue.sh` already checks `gh` capability before writes and this should follow the same pattern.
- Assumes the `--parent`/`--blocked-by`/`--blocking` native-field behavior this plan relies on (R5's premise) continues to hold — verified present in `file_issue.sh` as of this writing.

### Outstanding Questions

**Deferred to Planning:**

- Exact label set per shape in `config.json` (`bug` already exists as a default GitHub label; `investigation` does not yet exist and needs creating).
- Where the per-size time-boundary documentation lives (`docs/SETUP.md` vs `docs/CONCEPTS.md` vs a new file).
- Whether `investigation` issues ever carry a `Design:` line, or omit it entirely since investigations aren't typically plan-derived.

### Sources / Research

- `file_issue.sh` (this repo) — confirms `--parent`/`--blocked-by`/`--blocking` write to native GitHub relationship fields on create and edit, and that `design_line_required` mechanically parses a body's `Design:` line.
- `docs/CONCEPTS.md` (this repo) — "Placement answers" and "Three Guards Are Intentionally Config-Shaped" sections; explains why parent/position/blocked-by/blocks have no body-text role.
- `config.json`, `config.example.json` (this repo) — current single `work` shape; consuming-repo default-and-copy convention.
- `gh project field-list 3 --owner jffriend` — confirms no `Size`/`Estimate` field exists on this repo's board today.
- `/Users/jfriend/Projects/photo-consolidation/.github/ISSUE_TEMPLATE/{work,decision,plan-parent,your-run}.md` — prior-art template set; source of the "Binds this work" and body-text Size/Placement patterns this plan explicitly departs from.
- Issues [#6](https://github.com/jffriend/ai-issue-management-skill/issues/6), [#7](https://github.com/jffriend/ai-issue-management-skill/issues/7), [#1](https://github.com/jffriend/ai-issue-management-skill/issues/1), [#5](https://github.com/jffriend/ai-issue-management-skill/issues/5) (this repo) — originating request and examples of the current inconsistent shape.

Key Flows are omitted: this plan defines content shape (what an issue body and a project field contain) rather than a multi-step interaction — the filing flow itself (`file_issue.sh`'s preview/confirm/read-back sequence) is unchanged.
