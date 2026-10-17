---
title: Plugin Distribution - Plan
type: feat
date: 2026-10-17
topic: plugin-distribution
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-brainstorm
execution: code
---

# Plugin Distribution - Plan

## Goal Capsule

- **Objective:** Every repo that uses the guardrail runs the current release without anyone hand-copying or hand-editing files, and a fix reaches every repo on a machine with one update command.
- **Means:** Ship the skill and the engine together as one Claude Code plugin from this repo, with set-up offered the first time someone files in an unconfigured repo.
- **Product authority:** Joe (repo owner). This plan replaces the approach in issue #1, which stays open as the parent for this work.
- **Open blockers:** None for planning. R12 rests on an unverified assumption that planning must test first (see Dependencies / Assumptions).

---

## Product Contract

### Summary

This repo becomes a Claude Code plugin that ships the skill and the engine together. A consuming repo keeps only its config, its issue templates, and a settings entry naming the plugin, and the skill reads that config at run time. An unconfigured repo gets an offer to set up, and pluckd, photos, and photo-consolidation move onto the plugin.

### Problem Frame

Each consuming repo carries its own copy of the engine and a hand-filled copy of the skill, and fixes don't reach them. photos is pinned 84 commits behind the engine, pluckd 5 behind. pluckd has rebuilt its skill copy by hand on each of its last three pin bumps, and its copy still carries the doubled-article bug fixed upstream in 1b7ef3a. photos' skill copy predates the template and has no `human_review_required` handling or cloud section. photo-consolidation never moved off its pre-extraction copy of `file_issue.sh`.

Most of the hand-filled text is redundant. Of the template's seven placeholders, `{{FILE_ISSUE_CMD}}`, `{{SHAPES_LIST}}` (names only), and `{{DESIGN_LINE_BLOCK}}` restate config fields, `{{BODY_FIELDS_NOTE}}` restates the repo's issue templates, and `{{CONFIG_PATH}}` is the config's own location. Only the board's display name, the conventions-doc path, and each shape's one-line meaning have no home in the config today.

Cloud filing works only through a pluckd-specific workaround: its wrapper downloads the engine files at the pinned commit, and keeps a hand-maintained file list that has to be re-checked on every pin bump. A new user faces five manual setup steps with nothing checking that the placeholders were filled or the config is valid.

### Key Decisions

- **Ship as a Claude Code plugin, skill and engine together.** One install and one update cover both, so they can't drift apart. (session-settled: user-directed — chosen over a GitHub CLI extension plus a separately installed skill, and over copying into each repo with a sync command: the extension still leaves a skill copy to drift, and per-repo copies are what drifted today.) Governs R1, R2, R4.
- **Design for about two installers, and record the extra steps a public release would need without building them.** (session-settled: user-directed — chosen over designing for anyone installing publicly: about two people are expected, but the repo is public.) Governs the deferred list in Scope Boundaries.
- **Updates move a whole machine at once.** (session-settled: user-directed — chosen over automatic updates in every repo, and over per-repo pinning: automatic spreads one bad release everywhere, and per-repo pinning falls behind.) Governs R2, R3.
- **Cloud sessions take the newest published release.** (session-settled: user-directed — chosen over a version each repo names, and over dropping cloud filing: a per-repo version setting brings back a value that falls behind.) Governs R12, R13, R14.
- **An unconfigured repo gets a setup offer, which takes in issue #1.** (session-settled: user-directed — chosen over refusing and pointing to docs, and over staying out of the way: refusing leaves setup manual, and staying out of the way leaves a repo with no guardrail.) Governs R9, R10, R11.
- **All three existing repos migrate as part of this work.** (session-settled: user-directed — chosen over migrating only the two submodule repos, or none: migrating proves the plugin on real boards, and photo-consolidation would otherwise keep drifting.) Governs R17.
- **Release safety comes from a check before publishing and a fast rollback, without per-repo pinning.** Cloud sessions all take the newest release, so the release itself is the only gate. Governs R13, R14.
- **The three values with no config home become optional config fields.** The other placeholders already restate config or repo files, so the skill derives them instead. Governs R5, R6, R7.

### Requirements

**Packaging and updates**

- R1. The skill and the engine ship together as one Claude Code plugin published from this repo, and one install per machine makes them available in every repo on that machine.
- R2. One update command moves every repo on the machine to the newest published release.
- R3. Installed copies change only when a release is published, never when a commit lands on main without a release.

**What a consuming repo keeps**

- R4. A consuming repo keeps only its config, its `.github/ISSUE_TEMPLATE/` files, and a settings entry naming the plugin, with no submodule, wrapper script, or skill copy.
- R5. The skill takes every repo-specific value from the repo's config and issue templates at run time, so nothing is filled in by hand.
- R6. The config gains three optional fields: the board's display name, the path to the repo's conventions doc, and a one-line meaning per shape. Without them the skill falls back to a neutral wording.
- R7. An existing config that passes today's validation keeps working without edits.
- R8. Follow-up commands the engine prints run as printed in a local session of the same repo.

**Repos with no config**

- R9. When asked to file or adopt in a repo with no config, the skill files nothing and offers to run setup.
- R10. Setup asks for the values it can't look up, including `human_review_required`. It writes and validates the config, copies the issue templates, and adds the settings entry before it reports success.
- R11. Setup never overwrites an existing config, issue template, or settings entry without asking first.

**Cloud sessions**

- R12. A cloud session with one repo attached gets the newest published release when it starts, with no per-repo version setting and no download workaround in the repo.

**Release safety**

- R13. A release is published only after the test suite passes and one dry run against a real board succeeds using the release candidate.
- R14. A rollback re-publishes the previous release. It reaches a machine through the same update command (R2) and a cloud session at its next start (R12).

**Guardrails unchanged**

- R15. The placement refusals, duplicate check, dry-run, and read-back behave the same once packaged as they do today, and this work doesn't change the read-back or delta-write logic.
- R16. The skill stays the only supported way to write to the board in a configured repo, and it still tells the agent never to reach for the GitHub CLI to create or place an issue.

**Migration**

- R17. pluckd, photos, and photo-consolidation each run on the plugin. Each drops its submodule, wrapper, skill copy, and (photo-consolidation) its own engine copy, then files or adopts one real issue whose read-back passes.
- R18. This repo files its own issues through the plugin, and its `CLAUDE.md` filing instructions point at the skill in place of the bare command.

### Key Flows

- F1. Set up a new repo
  - **Trigger:** Someone asks the agent to file an issue in a repo with the plugin installed and no config.
  - **Steps:** The skill refuses to file and offers setup (R9). On yes, setup asks its questions, writes and validates the config, copies the issue templates, and adds the settings entry (R10, R11). The original filing request then runs as normal.
  - **Outcome:** The repo is configured, and the first issue goes on the board through the guardrail.
- F2. Ship a fix
  - **Trigger:** A change on main is ready to reach consuming repos.
  - **Steps:** The release check runs (R13), the release is published, each machine runs the update command (R2), and cloud sessions pick it up at their next start (R12).
  - **Outcome:** Every repo on an updated machine, and every new single-repo cloud session, runs the fix.
- F3. Roll back a bad release
  - **Trigger:** A published release breaks filing.
  - **Steps:** The previous release is re-published (R14), and machines run the update command.
  - **Outcome:** Filing works again without editing any consuming repo.

### Acceptance Examples

- AE1. **Covers R9, R10.** Given a repo with the plugin installed and no config, when the agent is asked to file an issue, then nothing is written to the board, and the agent offers setup before doing anything else.
- AE2. **Covers R11.** Given a repo that already has issue templates but no config, when setup runs, then it asks before replacing any existing template.
- AE3. **Covers R7.** Given photos' current config, which has no `file_issue_cmd` or `human_review_required` field, when the skill runs, then filing works and human review defaults to required.
- AE4. **Covers R3.** Given a commit on main with no published release, when a machine runs the update command, then its installed copy doesn't change.
- AE5. **Covers R6.** Given a config with no board display name, when the skill describes the board, then it uses the neutral wording and leaves no unfilled placeholder text.

### Success Criteria

- A second person, on their own machine, installs the plugin and sets up a new repo with no manual copy-and-edit step. This is the Done-when of issue #1, tested on a real second install.
- After all three migrations, one release reaches every migrated repo on a machine with one update command, and none of those repos needs a commit to receive it.

### Scope Boundaries

- **Multi-repo cloud sessions.** Claude Code may not install a plugin named in repo settings when more than one repo is attached. In that case no skill loads, and the agent could write to the board with the GitHub CLI unguarded. The likely fix is installing the plugin from the cloud environment's setup script. It is owned by a child issue of #1, after the core work.
- **Other agents and tools.** The plugin works only in Claude Code. Use from Codex, Cursor, or other agents is out of scope.
- **Running the engine by hand.** A person can still run the engine from a terminal, but that is not a goal of this work, and nothing here makes it easier.
- **The submodule path.** The submodule stops being a supported way to install once the three repos have migrated.
- **Deferred for a public release:** a listing in a public plugin catalog, release notes for each version, a promise not to change behavior within a minor version, and install docs written for a stranger.

### Dependencies / Assumptions

- **Assumption, unverified:** a repo's settings entry makes a Claude Code cloud session install the plugin when the session starts. Claude Code's docs confirm this for local sessions of a trusted folder and don't mention cloud sessions. R12 depends on it.
- **Assumption, unmeasured:** a multi-repo cloud session ignores repo settings. The only source is pluckd's `docs/cloud-sessions.md`, which marks it "not measured", and it shapes the multi-repo boundary above.
- GitHub reads issue templates only from a repo's own `.github/ISSUE_TEMPLATE/`, so every consuming repo keeps its own copy (R4). The existing `docs/SETUP.md` step 4 relies on the same behavior.

### Outstanding Questions

**Deferred to Planning**

- Does a repo's settings entry install the plugin in a single-repo cloud session? Test this before building anything else. If not, R12 needs another way to get the plugin, such as the environment setup script.
- What should `file_issue_cmd` hold once the engine lives in the plugin, so that R8 holds in local sessions?
- Where does the release check (R13) run: by hand, in CI, or both?

### Sources / Research

- Issue #1 and its comment linking `docs/plans/2026-08-31-002-feat-configurable-human-review-plan.md`, the setup question for `human_review_required`.
- `SKILL.template.md` header comment, which lists the seven placeholders.
- `docs/SETUP.md`, the five manual steps this replaces.
- `docs/plans/2026-10-16-1712-feat-cloud-mode-filing-plan.md`: "Nothing enforces `SKILL.template.md`... that belongs with the installed skill wrapper (#1)."
- pluckd `scripts/file_issue.sh`, its cloud download path and `ENGINE_FILES` list, and pluckd `docs/cloud-sessions.md` ("One repository per session").
- Claude Code plugins reference: `${CLAUDE_PLUGIN_ROOT}` is substituted inside skill content, but not in the environment of commands the agent runs. Marketplace sources accept a `ref` or `sha`, and installed copies change only when the plugin's version changes.
- `docs/solutions/`, which must be read before any change near the read-back or delta-write logic (R15).
