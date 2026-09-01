---
title: Issue Templates - Plan
type: feat
date: 2026-08-31
topic: issue-templates
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
execution: code
---

# Issue Templates - Plan

## Goal Capsule

- **Objective:** Define this repo's issue-body shapes (work, bug, investigation) and how they're delivered, replacing the inconsistent structure issues 1, 5, 6, and 7 currently use, and ship a copy consuming repos can adopt and customize.
- **Product authority:** [Issue 6](https://github.com/jffriend/ai-issue-management-skill/issues/6), plus this conversation's decisions on shape structure and field-vs-body placement, informed by `photo-consolidation`'s existing `.github/ISSUE_TEMPLATE/` set.
- **Open blockers:** None. All inputs needed to plan this work were resolved in dialogue.
- **Execution profile:** Config, template, and doc files, plus one live `gh` setup command against this repo's board (U5). No server or runtime code.
- **Stop conditions:** Stop before running U5's `gh project field-create` if the installed `gh` version's `--help` doesn't carry the expected single-select-option flags. Stop and report (don't silently rename) if `tests/test_engine_gating.py`'s PHOTOS_CONFIG-driven tests fail after U1's `config.example.json` change for a reason other than a hardcoded old shape name.
- **Tail ownership:** This plan owns everything through Definition of Done. Issue 7 owns writing a Size *value* onto a specific issue. A not-yet-filed follow-up issue owns the prose-scan-to-dependency-enforcement idea (see Product Contract Scope Boundaries).

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
- R11. Each shape's body-skeleton content is derived from its native-template file by stripping the YAML frontmatter, for the agent to fill in and pass to `file_issue.sh --body-file`.
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
- `config.json` (this repo) — current single `work` shape.
- `config.example.json` (this repo) — current four-shape `photo-consolidation`-mirroring vocabulary (`work`/`decision`/`your-run`/`plan-parent`), consuming-repo default-and-copy convention, and the fixture `tests/test_engine_gating.py`'s `PHOTOS_CONFIG` loads directly.
- `gh project field-list 3 --owner jffriend` — confirms no `Size`/`Estimate` field exists on this repo's board today.
- `/Users/jfriend/Projects/photo-consolidation/.github/ISSUE_TEMPLATE/{work,decision,plan-parent,your-run}.md` — prior-art template set; source of the "Binds this work" and body-text Size/Placement patterns this plan explicitly departs from.
- Issues [#6](https://github.com/jffriend/ai-issue-management-skill/issues/6), [#7](https://github.com/jffriend/ai-issue-management-skill/issues/7), [#1](https://github.com/jffriend/ai-issue-management-skill/issues/1), [#5](https://github.com/jffriend/ai-issue-management-skill/issues/5) (this repo) — originating request and examples of the current inconsistent shape.

Key Flows are omitted: this plan defines content shape (what an issue body and a project field contain) rather than a multi-step interaction — the filing flow itself (`file_issue.sh`'s preview/confirm/read-back sequence) is unchanged.

---

## Planning Contract

**Product Contract preservation:** Product Contract unchanged.

### Key Technical Decisions

- KTD1. **One canonical template file per shape, not two.** `.github/ISSUE_TEMPLATE/<shape>.md` carries YAML frontmatter plus the body. The CLI skeleton required by R11 is derived by stripping the frontmatter block from that same file — never a second physical file kept in sync by hand. Governs R10, R11.
- KTD2. **Size-field creation is a one-time manual `gh` command, not new `file_issue.sh` functionality.** Documented in `docs/SETUP.md`, run once per repo (U5), following this repo's own "match rigor to lifespan and blast radius" rule for low-frequency, board-schema-level setup. Governs R7, R9.
- KTD3. **Issue-body section structure is enforced by convention only.** No new `config.json` schema field or `file_issue.sh` validation checks that a body actually contains What/How/Done when, etc. `config.json`'s `shapes` entries carry only `name` and `labels` today (verified), and no Product Contract requirement calls for automated body-structure validation — adding one would be scope creep beyond R1–R13. Governs R1, R2, R3, R4.
- KTD4. **`.github/ISSUE_TEMPLATE/config.yml` sets `blank_issues_enabled: false`.** Matches `photo-consolidation`'s prior art. Forces every web-filed issue through one of the three shapes rather than a fully blank issue — a small extra guardrail at no cost, even though it can't restore the board-neighborhood preview, duplicate check, or relationship wiring `file_issue.sh` provides. Governs R12.
- KTD5. **`investigation` omits the `Design:` line.** Investigations aren't typically plan-derived, so the line has no home there. Resolves the Product Contract's "Deferred to Planning" question on this point. Governs R4, R6.
- KTD6. **Per-size time-boundary documentation lives in `docs/SETUP.md`, as a new subsection.** `SETUP.md` already documents config customization for consuming repos, so the per-repo Size vocabulary belongs beside it rather than in a new file. Resolves the Product Contract's "Deferred to Planning" question on doc location. Governs R9.
- KTD7. **Consuming repos copy this repo's own `.github/ISSUE_TEMPLATE/*.md` files — no separate example-templates directory.** GitHub only reads issue templates from a repository's own root, not from a submodule path, so a consuming repo needs its own copies regardless; there is no reason to also maintain a second, parallel example set the way `config.example.json` mirrors `config.json`. Governs R13.

### Risks & Dependencies

- The idempotence of writing a Size *value* onto a specific issue (a future `updateProjectV2ItemFieldValue` GraphQL mutation) is unmeasured. None of this plan's units write a per-issue Size value, so it isn't a risk here — but issue 7, which owns that capability, should measure it live against a scratch issue before choosing a delta-vs-set write path, the same way this repo's existing `--blocked-by`/`--parent` idempotence was measured (`docs/solutions/developer-experience/gh-issue-edit-is-not-idempotent-write-a-delta-not-a-set.md`).
- `config.example.json` currently drives `PHOTOS_CONFIG`-parametrized tests in `tests/test_engine_gating.py`, loaded live rather than hand-copied. `test_unknown_shape` hardcodes `plan-parent` in its assertion — U1's approach names the fix directly; confirm no other test carries a similar hardcoded old shape name before treating the config change as done.

---

## Output Structure

`.github/ISSUE_TEMPLATE/` is new in this repo:

```text
.github/ISSUE_TEMPLATE/
  config.yml         -- blank_issues_enabled: false
  work.md            -- feature work and tech debt
  bug.md             -- bug reports
  investigation.md   -- decision-producing tasks
```

---

## Implementation Units

### U1. Add `bug` and `investigation` shapes, with tests

- **Goal:** This repo's `config.json` and the shipped `config.example.json` both offer `work`, `bug`, and `investigation` as valid shapes, each backed by a real GitHub label.
- **Requirements:** R1
- **Dependencies:** None
- **Files:**
  - `config.json`
  - `config.example.json`
  - `tests/test_engine_gating.py`
- **Approach:**
  1. In `config.json`, set `"shapes"` to `work` → `["work"]`, `bug` → `["bug"]`, `investigation` → `["investigation"]`.
  2. In `config.example.json`, replace only its `"shapes"` array with the same three-shape set. Leave `repo`, `owner`, `project_number`, `project_id`, `plan_dir`, and `design_line_required` untouched.
  3. Create the `investigation` label on this repo (`bug` and `work` already exist).
  4. Search `tests/test_engine_gating.py` for assertions hardcoding the old `config.example.json` shape names and update them. `test_unknown_shape` asserts `self.assertIn("plan-parent", out)` against the refusal message — `plan-parent` won't exist once step 2 lands, so change that assertion to check for one of the new shape names (e.g. `investigation`) instead. Confirm `test_missing_shape` has no equivalent hardcoded name.
- **Patterns to follow:** The existing `{name, labels}` shape-entry format; the existing `PHOTOS_CONFIG`-driven parametrized test style in `tests/test_engine_gating.py`.
- **Test scenarios:**
  - `--shape bug` produces a `gh issue create` call carrying `--label bug` in the fake-`gh`-logged argv.
  - `--shape investigation` produces `--label investigation`.
  - `--shape work` continues to produce `--label work` unchanged (regression).
  - `--shape nonexistent` still refuses with the existing unknown-shape error, now against the 3-shape config (edge case).
  - `config.example.json`'s new shapes list still passes the `PHOTOS_CONFIG`-driven parametrized tests with no hardcoded-old-name failures (integration).
- **Verification:** `python3 -m unittest discover tests` passes. `gh label list --repo jffriend/ai-issue-management-skill` shows `investigation`.

### U2. Canonical shape template files under `.github/ISSUE_TEMPLATE/`

- **Goal:** GitHub's web "New issue" picker on this repo offers exactly the three shapes, each with the sections R2–R6 require and none of the sections R5/R8 exclude.
- **Requirements:** R2, R3, R4, R5, R6, R8, R10, R12. Governed by KTD1, KTD4.
- **Dependencies:** U1 (label names must match)
- **Files:**
  - `.github/ISSUE_TEMPLATE/config.yml`
  - `.github/ISSUE_TEMPLATE/work.md`
  - `.github/ISSUE_TEMPLATE/bug.md`
  - `.github/ISSUE_TEMPLATE/investigation.md`
- **Approach:**
  1. `config.yml` sets `blank_issues_enabled: false` (KTD4).
  2. Each `<shape>.md` carries YAML frontmatter (`name`, `about`, `title`, `labels: <shape's label>`, `assignees`) plus an HTML-comment reminder that filing through `file_issue.sh` is preferred because this form skips its guardrails (R12), then the shape's required sections as blank headings with a one-line guidance comment each, in the repo's own What/How/Why voice — active voice, no filler (see issue 5 as the standing example, and `docs/solutions/` "Issue body style" convention).
  3. `work.md`: What / How / Impact if skipped / Done when, plus an optional trailing `Design:` line.
  4. `bug.md`: What's broken / Repro steps / Expected vs Actual / Impact if skipped / Done when, plus an optional trailing `Design:` line.
  5. `investigation.md`: Question to answer / Recommendation / Impact if skipped / Write-up link / Done when — no `Design:` line (KTD5).
  6. None of the three includes a Placement, Binds this work, or Size section (R5, R8).
- **Technical design (directional):**

  ```markdown
  ---
  name: Work
  about: Feature work or technical debt for this repo
  title: ''
  labels: work
  assignees: ''
  ---

  <!-- File through file_issue.sh instead, when you can -- it shows the board
       neighborhood and checks for duplicates before writing anything. See
       CLAUDE.md. This form skips those checks. -->

  ## What

  ## How

  ## Impact if skipped

  ## Done when

  <!-- Optional. Link to the plan section that holds the how, or delete this line. -->
  Design:
  ```

  `bug.md` and `investigation.md` follow the same shape with their own section lists (step 4–5 above); `investigation.md` additionally opens its guidance comment with "Anyone can pick this up — the agent or a person — the output is a recommendation or a decision, not code," per R4.
- **Patterns to follow:** `photo-consolidation`'s `.github/ISSUE_TEMPLATE/work.md` (HTML-comment guidance style, adapted to this repo's terser voice).
- **Test scenarios:** Test expectation: none — content files with no executable behavior; the shape/label wiring they depend on is covered by U1.
- **Verification:** GitHub's web "New issue" page for this repo (or `gh api repos/jffriend/ai-issue-management-skill/contents/.github/ISSUE_TEMPLATE`) lists all three shapes and no "Open a blank issue" option.

### U3. Document the web-UI guardrail-bypass boundary

- **Goal:** A reader of `docs/CONCEPTS.md` knows exactly what filing through GitHub's web "New issue" button preserves and what it skips, before they use it.
- **Requirements:** R12 (supporting)
- **Dependencies:** U2
- **Files:** `docs/CONCEPTS.md`
- **Approach:** Add a short subsection near the existing "Nothing Writes Without a Preview Shown First" guard, stating plainly what the web path preserves (correct labels, a shape to fill in, no fully blank issues) and what it skips (the board-neighborhood preview, duplicate check, and relationship read-back `file_issue.sh` provides). State the boundary precisely rather than a comfortable approximation of it — a vaguely-stated exemption is the shape a future bypass finds first (`docs/solutions/best-practices/the-exemption-that-makes-a-guard-writable-is-the-hole.md`).
- **Test scenarios:** Test expectation: none — documentation only.
- **Verification:** The new subsection names both what's preserved and what's skipped, without a generic "use the CLI instead" deflection.

### U4. Update `SKILL.template.md` and `docs/SETUP.md`

- **Goal:** An agent filing through `file_issue.sh` knows how to derive body content from the shape templates, and a person setting up a consuming repo knows about the Size field and where its per-repo meaning is documented.
- **Requirements:** R9, R11, R13. Governed by KTD1, KTD2, KTD6, KTD7.
- **Dependencies:** U1, U2, U5 (SETUP.md's documented `gh project field-create` command must match what U5 actually confirmed and ran, not an assumed flag syntax)
- **Files:** `SKILL.template.md`, `docs/SETUP.md`
- **Approach:**
  1. `SKILL.template.md`: replace the `{{BODY_FIELDS_NOTE}}` header-comment example (currently names "Size" as a body field) with guidance that body fields are whatever the repo's shape templates define, and Size is a project field, not a body field. Update the `{{SHAPES_LIST}}` example in Step 2 to the new three-shape default. Add an instruction to the filing procedure: read the matching `.github/ISSUE_TEMPLATE/<shape>.md`, strip the YAML frontmatter block (everything between the two `---` lines), and pass the remainder as `--body-file` content (KTD1).
  2. `docs/SETUP.md`: add a subsection documenting the Size field setup step (the `gh project field-create` command from U5) and a placeholder table for what XS/S/M/L/XL mean in time, marked as a per-repo setting (KTD6). Add `.github/ISSUE_TEMPLATE/*.md` to the existing "files a consuming repo copies" list alongside `config.example.json` and `SKILL.template.md` (KTD7).
- **Patterns to follow:** The existing `{{PLACEHOLDER}}` convention in `SKILL.template.md`; the existing walkthrough structure in `docs/SETUP.md`.
- **Test scenarios:** Test expectation: none — documentation only; `test_engine_skill.py` scans `file_issue.sh`'s own flag parser, not `SKILL.template.md` prose (verified), so no existing test enforces this content.
- **Verification:** A reader following `docs/SETUP.md`'s walkthrough can find the Size field setup step and the frontmatter-stripping instruction without needing to ask.

### U5. Create the Size field on this repo's board

- **Goal:** This repo's live GitHub Project board has a `Size` single-select field with options XS, S, M, L, XL.
- **Requirements:** R7
- **Dependencies:** None
- **Files:** None — a one-time `gh` command against the live board, not a code change.
- **Approach:** Confirm the installed `gh` version's `--help` output for `gh project field-create` carries the needed single-select-option flags (same offline-first-check discipline as `file_issue.sh`'s `probe_gh_capability`, KTD2), then run it against project 3 / owner `jffriend` with name `Size` and options XS/S/M/L/XL.
- **Test scenarios:** Test expectation: none — a one-time board-setup action, not code.
- **Verification:** `gh project field-list 3 --owner jffriend` lists `Size` as a `ProjectV2SingleSelectField` with options XS, S, M, L, XL.

---

## Verification Contract

- `python3 -m unittest discover tests` — proves U1's shape/label wiring and confirms no regression in existing tests.
- `gh project field-list 3 --owner jffriend` — confirms U5's `Size` field exists with the right options.
- `gh api repos/jffriend/ai-issue-management-skill/contents/.github/ISSUE_TEMPLATE` (or GitHub's web "New issue" page) — confirms U2's three shapes and no blank-issue option.

---

## Definition of Done

- All five units complete.
- `python3 -m unittest discover tests` passes.
- The `investigation` label exists on this repo; `config.json` and `config.example.json` list `work`, `bug`, and `investigation` with matching labels.
- `.github/ISSUE_TEMPLATE/{work,bug,investigation}.md` and `config.yml` exist, match each shape's required sections, and contain no Placement, Binds this work, or Size section.
- The `Size` single-select field (XS/S/M/L/XL) exists on this repo's live Project board.
- `docs/CONCEPTS.md`, `docs/SETUP.md`, and `SKILL.template.md` reflect the new shapes, the frontmatter-stripping skeleton step, and the Size-field setup step.
- No dead-end or experimental code left in the diff.
