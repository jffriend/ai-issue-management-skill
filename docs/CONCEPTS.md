# Concepts

**What this page does:** explains the words this tool uses and the reasoning behind every guard it enforces, so nothing in day-to-day use feels arbitrary.

If you just want to get set up or run a command, you don't need this page. Come here when you want to know *why* the tool insists on something, or what a term in its output means.

## Vocabulary

**Four terms recur through this tool's output and docs.** Knowing them up front makes everything else on this page easier to follow.

### Placement answers

Every issue answers four questions before it can go on the board: which plan it belongs under, where it sits in priority order, what has to finish before it can start, and what can't start until it's done.

All four are required. Two of them — what blocks it, what it blocks — have an honest "none" as a real answer, but leaving them blank is not the same thing. There's no default for any of the four, because a default is exactly what gets accepted silently, and an ordering rule that only lives in an issue's prose is invisible to whatever list a team actually works from.

### Adopt

Wiring an issue that already exists to its placement answers, instead of creating a new issue and wiring it in one step.

Think of it as finishing a job someone started by hand, not starting over. If the issue already has a parent or a link this command didn't ask for, adopt stops rather than guessing what to do with it — see [Adopt Refuses Rather Than Reconciles](#adopt-refuses-rather-than-reconciles) below for what that stop looks like.

### Half-wired

The state of an issue that exists on the board but whose placement didn't fully land — its parent, its position, or a blocking link is missing.

This label is earned, not assumed. A board read that came back empty, or didn't come back at all, is not proof that anything is wrong; it might just mean the board hasn't caught up yet or the read itself failed. Calling that half-wired would tell you to fix an issue that was never broken, which is worse than saying nothing.

### Read-back

Reading every relationship back from the server after writing it, and checking what actually landed against what was asked for.

A command exiting successfully is not proof that anything changed — the write can report success and not take, and a server reply can look complete and still not contain what you'd need to confirm anything at all. So the read-back checks the *shape* of what comes back, not just whether something came back, and it settles on one of three outcomes: present, genuinely absent, or could-not-look. Only the read is ever retried on a short, bounded wait — the write itself is never repeated, because repeating a write you're not sure landed is how you end up with duplicates.

## Why These Guards Exist

**Every guard on this page traces back to one incident: a board where the honor system had already failed.**

This tool's guardrails weren't designed in the abstract. They came from an audit of a real project board, after a written rule — "always record the ordering constraint" — was broken three times in one sitting, by a session that had *just read the rule*. The audit that followed found sixteen stated ordering constraints with no corresponding link anywhere on the board, including one piece of work sitting forty positions ahead of the item that made it unsafe to even start.

The fix wasn't a stronger reminder — reminders were exactly what had just failed. It was removing the option to skip the bookkeeping at all: one script that is the only supported way to write to the board, that won't write until all four placement questions are answered on purpose, that shows a person the board neighborhood and any likely duplicates before anything is confirmed, and that checks its own work afterward instead of trusting its exit code. Every guard below is a piece of that fix.

## What This Enforces

**Every check below holds no matter whose config is loaded.** A consuming repo can change its issue-shape names, its labels, and one parenting rule — nothing else about these guards bends to config, and the two that do are called out explicitly.

### The Four Placement Answers Have No Default

Parent, board position, blocked-by, and blocks are all required flags — there's no flag you can simply omit and have the tool assume something reasonable. Two of them accept an explicit "none"; the other two don't, because "none" is itself a decision worth stating on purpose rather than a byproduct of leaving a field blank.

Each numeric answer is checked offline, before any network call, to confirm it's really a plain number. That way a typo gets caught immediately instead of surfacing later as a relationship that silently never landed on a real issue.

### Adopt Refuses Rather Than Reconciles

If you try to adopt an issue that already has a parent, or a blocked-by or blocks link this run didn't name, the tool stops. It prints the exact `gh issue edit --remove-*` command that would clear the conflict, rather than guessing which value you actually meant and overwriting the other one silently.

Position is the one exception. Since a position answer is always required, adopt always moves the issue to the position you named — but it shows you the slot the issue holds today next to the slot it's headed for, before you confirm anything, and it writes a comment afterward recording the move.

A real example of that comment, from this tool's own history: "Moved from position 7 (following #257) to position 9 (following #256)." Naming what each side follows matters, because a bare number stops meaning anything once the board shifts around it.

The reasoning behind treating position differently from the other three, and why a recorded comment is what makes an overwritten priority decision recoverable afterward, is the subject of [Make the lossy half recoverable before you remove the gate over it](solutions/design-patterns/make-the-lossy-half-recoverable-before-removing-the-gate.md).

### Every Write Gets Read Back, and the Read-Back Checks Shape, Not Just Presence

After every write, the tool reads the relationship straight back from GitHub's servers and compares it to what it asked for. It doesn't stop at "did something come back" — it checks that the reply actually has the fields being compared, before it trusts any of their values.

That distinction matters more than it sounds like it should. A reply like `{"message":"Not Found"}` is a real, well-formed, non-empty response — and every field you'd try to pull from it comes back empty, which is exactly what a clean "no parent, no blockers" issue also looks like. A guard that only asked "is this non-empty" would call that a match and report success having verified nothing.

Checking the reply's shape first — do the expected fields even exist — is what tells the two cases apart.

The full story of how this gap was found, and the exact fix, is in [When empty is a legal answer, a guard must check shape, not emptiness](solutions/best-practices/when-empty-is-a-legal-answer-a-guard-must-check-shape-not-emptiness.md).

### The Read-Back Resolves Three States, and Retries Only the Read

A GitHub Projects (v2) board isn't guaranteed to show you your own write the instant after you make it. So when a fresh listing doesn't show something you just wrote, that could mean the write hasn't caught up yet, that it genuinely didn't land, or that this one read attempt simply failed.

Collapsing all three into a single "not found means broken" answer once mislabeled four correctly-wired issues as half-wired — and the fix it suggested was to delete and refile them, which would have thrown away work that was actually fine. Now the read-back retries only the *read itself*, on a short capped wait, and never re-issues the write. It only calls something half-wired once a position or relationship has been positively proven wrong, not merely unconfirmed.

### Adopt Writes a Delta, Never the Full Desired Set

`gh issue edit` isn't forgiving about relationships you send it twice. Re-adding a link an issue already has doesn't quietly do nothing — it fails the entire call, exactly the same way for every kind of relationship, parent included. Real error text from the GitHub CLI: a repeated blocked-by link fails with "Target issue has already been taken," and a repeated parent link fails with "Issue may not contain duplicate sub-issues."

Because adopt exists specifically to finish wiring issues that are already partly correct, sending the full desired state every time would fail on exactly the issues adopt is for. So this engine reads the issue's current relationships first and sends only what's genuinely missing. If nothing is missing, it issues no write call at all — and it still reads the state back afterward, because skipping the write isn't the same thing as knowing the state is right.

The measurement behind this, including the live GitHub API responses that proved it, is recorded in [gh issue edit is not idempotent on relationships — write a delta, not a set](solutions/developer-experience/gh-issue-edit-is-not-idempotent-write-a-delta-not-a-set.md).

### A Truncated Board Listing Is a Hard Stop

Before showing you a board neighborhood or a duplicate-title check, the tool confirms the listing it read is actually complete. If it isn't, that's a hard stop — not a warning you can read past and continue anyway.

This exists because a silently truncated listing once hid an existing issue well enough that a duplicate of it got filed anyway. Refusing to proceed on an unproven listing is what makes that specific mistake structurally harder to repeat.

### Nothing Writes Without a Preview Shown First — Who Confirms Is Configurable

Running with `--dry-run` stops the tool right after it shows you the board neighborhood and any duplicate-title matches — nothing gets created or changed. That preview is the only thing that lets a person catch the two calls this tool can compute but can't actually judge: whether something is a duplicate, and whether a position is right.

Who confirms after that preview is a setting — `human_review_required` in your config. `required` (the default) means a human has to say yes to that specific preview before anything is written. `optional` means the agent can confirm on its own, but only when the request that asked for the filing already said so up front; otherwise it behaves like `required`. `agent` means the agent always confirms on its own, once it has shown the preview.

Whichever value applies, the preview still has to be shown to a human **verbatim** first — never summarized, never paraphrased. That word is load-bearing: a summary can quietly drop the one duplicate match or the one out-of-place position that mattered, and the confirmation step exists to catch precisely those two judgment calls.

**A surprise always wins, at every value.** A possible duplicate the agent can't confidently rule out, a board position that doesn't match what was asked for, an adopt that unexpectedly moves the issue, or the tool refusing outright — any of those stops the automatic path and hands the decision to a human, even under `agent`. The setting only ever controls the routine, no-surprise case; it never authorizes pushing past something unexpected.

### GitHub's Own "New Issue" Button Skips Every Guard on This Page

The three issue-shape templates under `.github/ISSUE_TEMPLATE/` give GitHub's web "New issue" picker the right shape and the right label for `work`, `bug`, and `investigation` — and `blank_issues_enabled: false` rules out a fourth, fully freeform option. That is all filing through the web UI preserves.

Everything else on this page is `file_issue.sh`-only. Filing from the web skips the board-neighborhood preview, the duplicate-title check, and every placement answer this tool otherwise refuses to let go unstated — no parent, no position, no blocked-by, no blocks, and no read-back proving any of it landed. An issue filed this way sits on the board exactly as unwired as one filed with a bare `gh issue create` before this tool existed.

Each template's own header comment says to use `file_issue.sh` instead when you can. That comment is a reminder, not an enforcement mechanism — stating the boundary precisely here is what keeps a future "well, the template says preferred, not required" reading from becoming the place this tool's guarantees quietly stop applying.

### Three Guards Are Intentionally Config-Shaped

Three things about this tool's behavior come from your config file rather than being fixed in the code, and that's by design, not a weaker version of the guard. First, your issue-shape vocabulary: what `--shape work` means, and whether "work" is even a valid shape at all, comes entirely from your config's `shapes` list. Second, the parenting rule — whether a plan-derived issue is *required* to carry a parent — is enforced only when your config sets `design_line_required: true`. Third, how much review a filing gets before anything is written is set by `human_review_required`, described above.

Every other guard on this page holds identically no matter what your config says. These three are the only places where "it depends on your repo" is a true statement about this tool's behavior.

### A Version Gap in gh Gets Caught Before It Can Leave an Issue Half-Wired

Before any write, the tool checks the installed `gh` binary for the specific flags and `--json` fields the run is about to need — it doesn't assume a flag exists just because an older version of `gh` had it. That check resolves to one of three states: "present," "absent," or "undeterminable."

Finding a missing flag mid-write is exactly how an issue ends up half-wired with no clean way to finish the job from where it stopped. Checking first, instead of finding out partway through a write, is what this guard exists to prevent.
