# ai-issue-management-skill

A guardrail for putting work on a GitHub Projects (v2) board, so that an
agent — or a person moving fast — cannot skip the bookkeeping that makes a
board trustworthy.

## Why this exists

Writing directly to a GitHub Projects board with the GitHub CLI — `gh issue
create`, `gh issue edit`, `gh project item-*` — creates or edits exactly what
you asked for and stops there. It does not ask where the new issue sits in
priority order, whether anything blocks it or it blocks, or which plan it
belongs to. Those get left for "a later step," and a later step is exactly
the thing that does not reliably come: in the project this tool was
extracted from, a written rule saying "always record the ordering constraint"
was broken three times in one sitting by a session that had just read the
rule. An audit of that board afterward found sixteen stated ordering
constraints with no corresponding link on the board — including one piece of
work sitting forty positions ahead of the item that made it unsafe to start.

The fix was not a stronger reminder. It was removing the option: a script
that is the *only* supported way to write to the board, that refuses to
write until four placement questions are answered explicitly (no defaults),
that shows a human the board neighborhood and any likely duplicates before
anything is confirmed, and that reads every relationship back from the
server afterward instead of trusting its own exit code. That script,
`file_issue.sh`, and its two helpers (`board.sh`, `issue_text.py`), are what
this repository packages — generalized so a second project can point it at
its own board, its own issue-shape vocabulary, and its own labels, without
re-deriving (and inevitably drifting from) the same guardrail by hand.

This repo ships the engine and two templates: `config.example.json` (the
schema a consuming repo fills in) and `SKILL.template.md` (a Claude Code
skill wrapper a consuming repo copies and customizes). It does not ship a
backend abstraction — it talks to GitHub Issues and GitHub Projects (v2)
only — and it does not ship a public-package distribution story; a consuming
repo adds it as a git submodule pinned to a commit.

## Vocabulary

Four terms recur throughout this README and the skill template. Defining
them once here, rather than reintroducing looser versions at each mention:

### Placement answers

The four questions every issue answers before it can go on the board: which
plan parent it hangs under, where it sits in priority order, what must
finish before it can start, and what must not start until it is done.

All four are required, and "none" is a real answer — leaving one blank is
not. There is no default, because a default is what gets taken silently, and
an ordering constraint that lives only in an issue's prose is invisible to
whatever query a team actually picks up work from.

### Adopt

Wiring an issue that already exists to the placement answers, as against
creating a new issue and wiring it in the same step.

Adopt refuses rather than reconciles: where the issue already carries a
parent or a link the invocation did not name, it stops and names the command
that clears the contradiction, because silently overwriting a placement
decision would be invisible afterward. It writes only what is missing —
re-applying a relationship an issue already holds is rejected outright by
the platform, so an adopt that sent the whole desired set would fail on
exactly the part-wired issues it exists to finish. Board position is the one
answer it does not refuse on, so it both discloses the slot the issue
currently holds before moving it and records the move afterward, as a
comment on the issue naming the slot it came from and the slot it went to.
Disclosure alone leaves the cost of a confirmed move impossible to
reconstruct; the record is what makes an overwritten priority decision
recoverable, and it is written only once the read-back has proven the new
position.

### Half-wired

The status of an issue that exists but whose placement did not fully land —
at least one of its parent, its board position, or a blocking link is
missing.

The status is only earned when the wiring was *proven* wrong. A board read
that came back empty, or that did not come back at all, is not evidence of a
half-wired issue; treating it as one produces a refusal whose stated remedy
destroys correct work, which is the failure mode this term exists to keep
visible.

### Read-back

Reading every relationship back from the server after writing it, and
comparing what returned against what was asked for.

An exit code is not evidence. A write can report success and not land; and a
reply can be well-formed, non-empty, and carry none of the fields being
compared, which compares equal to an empty answer and passes while proving
nothing. So a read-back checks the shape of what came back as well as its
contents, names which relationship disagreed rather than failing as a whole,
and resolves three outcomes rather than two — present, genuinely absent, and
could-not-look — because each calls for a different action from the
operator. Writes to a board are not read-your-writes consistent, so a
negative read is retried within a bounded wait before it is believed; the
retry belongs to the read alone and never re-issues the write.

## What this enforces

Everything below holds regardless of which repo's config is loaded — the
vocabulary (shape names, labels, whether a plan-derived link is required)
is configurable, but the checks themselves are not weakened by a different
config. Two are config-shaped by design and are called out as such.

**The four placement answers have no default.** Parent, board position,
blocked-by, and blocks are all required flags. Two have an explicit `none`;
two (parent, position) do not, because "none" is itself a real decision
worth stating on purpose rather than falling out of a blank field. Each
numeric answer is validated as a bare digit string *before* any network
call, so a typo is caught offline instead of surfacing after a real issue
already exists with a relationship that never landed.

**Adopt refuses rather than reconciles.** Adopting an issue that already
carries a parent, or a blocked-by/blocks link this invocation did not name,
stops the run and prints the exact `gh issue edit --remove-*` command that
would clear the contradiction — it never silently overwrites a placement
decision someone already made. Position is the one exception: all four
answers are mandatory, so adopt always names a position and will move the
issue there, but the confirmation screen shows the slot the issue holds
today next to the one it's headed for, so the cost of the move is visible
before anyone says yes, and a `move recorded` comment (written only after
the read-back proves the move landed) makes the old slot recoverable
afterward.

**Every write is read back, and the read-back checks shape, not just
presence.** A GitHub API reply can be well-formed, non-empty, and carry
none of the fields being compared — a `{"message":"Not Found"}`-shaped
error, for instance, extracts to the same "all empty" result as the single
most common filing shape (no parent, no blockers). A check that only asked
"did something come back" would accept that reply as a clean match and
report success having verified nothing. The read-back here checks that the
expected fields are actually present before comparing any of their values,
naming the specific relationship that disagrees rather than failing as an
undifferentiated blob.

**The read-back resolves three states, not two, and retries only the read.**
Writes to a Projects v2 board are not read-your-writes consistent, so a
listing that doesn't yet show a freshly-added item might mean the write
hasn't propagated, that it didn't land, or that this particular read failed.
Collapsing those into a single "not found means broken" declared four
correctly-wired issues [half-wired](#half-wired) in earlier testing and told
the operator to delete and refile them — which would have discarded correct
work. The read-back retries the *read* on a bounded, capped wait (never
re-issuing the write), and only reports half-wired once a position or
relationship has been positively proven wrong, not merely unconfirmed.

**Adopt's writes are a delta against current state, never the full desired
set.** `gh issue edit` is not idempotent: re-sending a relationship an issue
already has fails the whole call outright (a re-added blocked-by link errors
"Target issue has already been taken"; a re-sent parent errors "Issue may
not contain duplicate sub-issues") — even though the existing relationship
was never actually at risk. A script that computed the full desired state
and sent it wholesale would fail on every adopt of an issue that's already
partly wired, which for adopt is most of them. This engine reads current
state first and sends only what's missing, issues no call at all when
nothing is missing, and always reads back regardless of whether a call was
made.

**A truncated board is treated as a failed read, not a short one.** Before
showing anyone a neighborhood or a duplicate check, the engine confirms the
board listing it read is complete. A silently truncated listing once hid an
issue well enough that a duplicate of it got filed; this is the guard that
makes that class of mistake structurally harder, by refusing to proceed on
an unproven listing rather than proceeding on whatever came back.

**Nothing writes without a human seeing the real preview first.** `--dry-run`
stops the run immediately after showing the board neighborhood and any
duplicate-title matches — nothing created, nothing changed. The tool
supports an agent supplying its own confirmation only after that preview has
actually been shown to a person verbatim (never summarized or paraphrased),
on the reasoning that the confirmation prompt itself never enforced any of
the guards above — it only covered the two judgment calls (is this a
duplicate, is this position right) that the machine can compute but not
decide, and the position judgment is the one made recoverable by the
move-recorded comment.

**Two guards are intentionally config-shaped, not weakened by it:** the
shape/label vocabulary (what `--shape work` means, and whether "work" is
even a valid shape) comes entirely from your config's `shapes` list, and the
parenting rule — whether a plan-derived issue is *required* to carry a
parent — is only enforced when your config sets
`design_line_required: true`. Every other guard on this list holds
identically no matter what your config says.

**A version-gap in `gh` is caught before it can leave an issue half-wired.**
Before any write, the engine probes the installed `gh` binary for the
specific flags and `--json` fields the run needs, and resolves to "present,"
"absent," or "undeterminable" rather than assuming a flag exists because a
past version had it. A flag discovered missing mid-write is exactly how an
issue gets left half-wired with no way to finish the job from where it
stopped.

## Setup in a consuming repo

1. **Add this repo as a git submodule**, pinned to a specific commit:

   ```bash
   git submodule add <this-repo-url> path/to/ai-issue-management-skill
   git -C path/to/ai-issue-management-skill checkout <commit-you're-pinning-to>
   git add .gitmodules path/to/ai-issue-management-skill
   ```

2. **Write your own config**, starting from `config.example.json` (see
   [Config schema](#config-schema) below) — typically committed at a path
   like `scripts/file-issue.config.json` in your repo, outside the
   submodule.

3. **Copy `SKILL.template.md`** into your own repo's skill directory (for a
   Claude Code project, something like `.claude/skills/file-issue/SKILL.md`)
   and fill in every `{{PLACEHOLDER}}` — the template's own comment block
   names each one and what belongs in it. Most repos will also want a thin
   wrapper script at a stable path (e.g. `scripts/file_issue.sh`) that
   `exec`s the submodule's `file_issue.sh` with your `--config` path baked
   in, so callers and tests don't need to know the submodule's internal
   layout; that wrapper is what `{{FILE_ISSUE_CMD}}` in the template should
   point at.

4. **Initialize the submodule** in any fresh checkout before first use:

   ```bash
   git submodule update --init
   ```

### Config schema

`config.example.json` documents the shape; every field below is required
unless noted.

| Field | Type | Meaning |
|---|---|---|
| `repo` | string | `OWNER/NAME` of the GitHub repository issues are created in. |
| `owner` | string | The GitHub login that owns the project board (usually the same as the repo owner, but Projects v2 boards are owned independently of any one repo). |
| `project_number` | integer | The project board's number, as shown in its URL (`.../projects/<N>`). |
| `project_id` | string | The project board's GraphQL node ID — needed to write items to it. Find it with `gh project view <project_number> --owner <owner> --format json` (or the GraphQL API) and paste the `id` field. |
| `shapes` | array of `{name, labels}` | Your issue-type vocabulary. Each entry's `name` is a valid value for `--shape`; `labels` is the list of GitHub labels applied when an issue of that shape is created. At least one shape is required, and every shape needs at least one label. |
| `plan_dir` | string | The directory (repo-relative) that plan documents live in — used to recognize a `Design:` line in an issue body as pointing at a real plan. Required if `design_line_required` is `true`; otherwise unused. |
| `design_line_required` | boolean | Whether a plan-derived issue (one whose body carries a `Design:` line into `plan_dir`) is required to have a parent. Set `false` if your repo has no such convention. |

The engine validates all of this offline before making any network call: a
missing or empty required field, a `repo` not in `OWNER/NAME` form, a
non-numeric `project_number`, an empty `shapes` list, or a shape with no
labels all fail immediately with the specific field named, rather than
surfacing later as an opaque GraphQL error mid-write.

## Using it

Both modes ask the same four [placement answers](#placement-answers) and go
through the same preview-then-confirm-then-[read-back](#read-back) sequence;
see `SKILL.template.md` (once filled in for your repo) for the full
step-by-step procedure an agent should follow, and each script's `--help`
for the current flag set.

**Create** — file a brand-new issue: supply a title, a file holding the
body, and a shape (one of the names in your config's `shapes` list), plus
the four placement answers.

**Adopt** — wire an issue that already exists (`--adopt <N>`) to the same
four placement answers, without creating anything. [Adopt](#adopt) refuses
rather than reconciles: see above for what that means when the issue already
carries a parent or a link this invocation didn't name.

Both modes support `--dry-run`, which stops after showing the board
neighborhood and duplicate check (create mode only, for duplicates) and
before the confirmation prompt — nothing is created or changed.

## Two historical bugs this tool exists to not repeat

These are described here in general terms; see this repo's own commit
history and code comments (`file_issue.sh`'s header, and the `read_back`
function) for the specifics.

- **A guard that checks "did something come back" instead of "did the right
  shape come back" can pass on a well-formed error.** The read-back's field
  comparison used to run as soon as the API reply was non-empty. A reply
  like `{"message":"Not Found"}` is non-empty, but every field extraction
  from it comes back empty — which compares equal to the single most common
  filing shape (no parent, no blockers), so the check passed while having
  verified nothing. The fix was to check that the expected keys are actually
  present in the reply before comparing any of their values, so an
  unexpected reply shape fails loudly instead of accidentally resembling a
  legitimate empty answer.

- **`gh issue edit` is not idempotent, and writing the full desired state
  instead of a delta breaks on exactly the issues that are already
  partly correct.** Re-sending a relationship an issue already has doesn't
  no-op — it fails the entire call. That makes "compute what the issue
  should look like and send it" the wrong write strategy for adopt, since
  adopt exists specifically to finish wiring issues that are already
  partway there. The fix was to read current state first and send only the
  delta — the relationships genuinely missing — issuing no call at all when
  nothing is missing, and always reading back afterward regardless.

## Scope

- GitHub Issues and GitHub Projects (v2) only — no pluggable backend in this
  version.
- Filing and wiring (create/adopt) only — closing an issue, retitling one,
  or re-anchoring a `Design:` link after a renumbering are not covered; a
  consuming repo's own conventions doc should say how those are done.
- No installable package or CLI distribution yet — git submodule is the
  supported integration path.
