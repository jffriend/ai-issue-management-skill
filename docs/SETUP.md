# Setup

**Goal:** wire this tool into your repo so it can file and update issues on your project board, safely.

You'll do five things: add this repo's code to yours, tell it which board and repo to talk to, give your Claude Code agent a skill file that knows how to drive it, give your own repo a matching set of GitHub issue templates, and make sure the code is present in any fresh checkout. Each step below has the exact commands to run.

## Add the tool to your repo

**Goal:** finish these five steps with a working `config.json` and a filled-in skill file.

1. **Add this repo as a git submodule, pinned to a specific commit.**
   - A submodule keeps this tool's code available inside your repo without copying it in, locked to an exact version you choose rather than whatever is newest.
   - Run:

     ```bash
     git submodule add <this-repo-url> path/to/ai-issue-management-skill
     git -C path/to/ai-issue-management-skill checkout <commit-you're-pinning-to>
     git add .gitmodules path/to/ai-issue-management-skill
     ```

2. **Write your own `config.json`, starting from `config.example.json`.**
   - Your config tells the tool which GitHub repo and project board to write to, and what issue types ("shapes") it should recognize.
   - See the [Config schema](#config-schema) section below for what each field means.
   - Most repos commit this file at a path like `scripts/file-issue.config.json`, outside the submodule.

3. **Copy `SKILL.template.md` into your own repo's skill directory, and fill in every placeholder.**
   - For a Claude Code project, that's typically `.claude/skills/file-issue/SKILL.md`.
   - The template's own header comment names every placeholder it needs filled in.
   - `{{BOARD_NAME}}` — a short name for your project's board, e.g. "the Roadmap board" or "project board #1".
   - `{{FILE_ISSUE_CMD}}` — the exact command your repo uses to invoke the engine, e.g. `bash scripts/file_issue.sh`.
   - `{{CONFIG_PATH}}` — the repo-relative path to your own `config.json`, e.g. `scripts/file-issue.config.json`. Needed even when `{{FILE_ISSUE_CMD}}` is a wrapper that hides this path, because the skill reads `human_review_required` from it directly.
   - `{{SHAPES_LIST}}` — the shape names and a one-line meaning of each, copied from the `shapes` list in your own `config.json`.
   - `{{CONVENTIONS_DOC}}` — the path to your own repo's conventions doc, the place that documents issue-body shape and how ordering constraints get recorded.
   - `{{DESIGN_LINE_BLOCK}}` — a paragraph to keep only if your config sets `design_line_required: true`, and to delete otherwise.
   - `{{BODY_FIELDS_NOTE}}` — the required body sections for each shape, copied from your `.github/ISSUE_TEMPLATE/<shape>.md` files. Size is a board field, not a body field — see [Setting up the Size field](#setting-up-the-size-field) below.
   - Most repos also want a thin wrapper script, at a stable path like `scripts/file_issue.sh`, that runs the submodule's `file_issue.sh` with your `--config` path already baked in. That way callers and tests don't need to know the submodule's internal layout, and that wrapper script is what `{{FILE_ISSUE_CMD}}` should point at.
   - Delete the template's header comment block once every placeholder below it is filled in.

4. **Copy `.github/ISSUE_TEMPLATE/` into your own repo's root, and edit it to your conventions.**
   - GitHub only reads issue templates from a repository's own root, never from a submodule path, so a copy is required even if you never change a word of it.
   - Copy `.github/ISSUE_TEMPLATE/{config.yml,work.md,bug.md,investigation.md}` from this tool's repo into the same path at your own repo's root.
   - Each `<shape>.md`'s `labels:` frontmatter must match a `name` in your `config.json`'s `shapes` list — add, remove, or rename shapes on both sides together.

5. **Initialize the submodule in any fresh checkout, before first use.**
   - A submodule's code isn't pulled down automatically by a plain `git clone`, so this step is required every time someone checks out your repo fresh.
   - Run:

     ```bash
     git submodule update --init
     ```

## Config schema

**Goal:** know what each field in `config.json` means before you fill it in.

`config.example.json` documents the shape. Every field below is required unless the **Meaning** column says otherwise.

| Field | Type | Meaning |
|---|---|---|
| `repo` | string | `OWNER/NAME` of the GitHub repository issues are created in. |
| `owner` | string | The GitHub login that owns the project board (usually the same as the repo owner, but Projects v2 boards are owned independently of any one repo). |
| `project_number` | integer | The project board's number, as shown in its URL (`.../projects/<N>`). |
| `project_id` | string | The project board's GraphQL node ID. It is used only to set an issue's board position, the one write that still goes through GraphQL; everything else uses `project_number`. Find it with `gh project view <project_number> --owner <owner> --format json` and paste the `id` field. |
| `shapes` | array of `{name, labels}` | Your issue-type vocabulary. Each entry's `name` is a valid value for `--shape`; `labels` is the list of GitHub labels applied when an issue of that shape is created. At least one shape is required, and every shape needs at least one label. |
| `plan_dir` | string | The directory (repo-relative) that plan documents live in — used to recognize a `Design:` line in an issue body as pointing at a real plan. Required if `design_line_required` is `true`; otherwise unused. |
| `design_line_required` | boolean | Whether a plan-derived issue (one whose body carries a `Design:` line into `plan_dir`) is required to have a parent. Set `false` if your repo has no such convention. |
| `human_review_required` | boolean | Whether a person approves a preview before each filing. `true` (a human has to say yes to the `--dry-run` preview) or `false` (the agent files in one run). Optional — defaults to `true` if omitted. See `docs/CONCEPTS.md` for what each value does. |

The tool checks all of this before making any network call. A missing or empty required field, a `repo` not in `OWNER/NAME` form, a non-numeric `project_number`, an empty `shapes` list, a shape with no labels, or a `human_review_required` value other than `true`/`false` all fail immediately with the specific field named, rather than surfacing later as a confusing error partway through a write.

### Choosing `human_review_required`

There's no automated setup interview for this yet — you're setting the value in `config.json` by hand, the same as every other field above. Ask yourself how much you trust an agent to judge, on its own, whether a filing is a duplicate and whether its board position is right:

- Not sure yet, or this is a new repo? Leave it unset, or set it to `true`. Every filing waits for you to say yes to the preview.
- You've watched this tool work and trust the agent to file unattended? Set it to `false`. The agent files in one run. If the tool finds a possible duplicate, the agent either adds its details to the existing issue or, when unsure, files nothing and tells you the matches. Either way the session carries on.

## Setting up the Size field

**Goal:** give your project board a `Size` field, and know what each option means for your repo.

Size is a board field, not something any issue template asks for in its body. Create it once per board:

```bash
gh project field-create <project_number> --owner <owner> \
    --name "Size" --data-type "SINGLE_SELECT" \
    --single-select-options "XS,S,M,L,XL"
```

What each option means in time is your call, not something this tool or its templates define. Write your own table here once you've decided, for example:

| Size | Meaning |
|---|---|
| XS | |
| S | |
| M | |
| L | |
| XL | |
