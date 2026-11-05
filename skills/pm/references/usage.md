# Usage limits, context, and handing off

Two budgets can end a session's useful work: its context window and the plan's usage limits.

## Context

simplicity's context hook is the only context signal. It suggests a shift when the session's
context use reaches its threshold (60% of the model's window by default, then again every 10
points; the `SIMPLICITY_SHIFT_THRESHOLD` environment variable changes it). This method adds no
limits of its own, so a session never answers to two context policies.

- **At every suggestion**, once the decider has answered simplicity's question, the PM commits
  its state note to the rulings branch as its own work: on "Shift now" as part of the handoff
  below, on "Not now" before carrying on. Nothing is committed while the question is open.
- **The shift itself** starts only when the decider answers "Shift now" to simplicity's own
  question, or asks for the shift by name. Then follow "Handing off" below.
- A lane does the same: the decider answers the question in the lane's session. A lane whose
  question nobody answers tells the PM the shift is waiting.

## Usage limits

The 5-hour and weekly windows. Use the stricter row that matches.

| Reading | Action |
|---|---|
| 5-hour under 80% and weekly under 90% | Continue |
| 5-hour 80% or more, or weekly 90% or more | Start no new background agents, workflows or long jobs. Finish the step in flight |
| 5-hour 95% or more, weekly 95% or more, or the step won't finish before the limit | Push committed work, list what is still running, stop, and report |

- **Paid extra usage.** A session that finds itself running on paid extra usage applies the third
  row and says so in its report. No spending goes on without the decider's explicit go-ahead.
- **Push before you wait.** A cloud container left idle through a limit's reset can be
  reclaimed, and background work isn't restored. Push committed work only; never commit
  half-done work just to have something to push.
- **Where a reading comes from** (a local usage tool, a cloud session field, the decider's
  screenshot) depends on the app version: see the plugin's dated notes file,
  `docs/desktop-app-notes.md` under the plugin root that the skill names.
  A reading that warns can raise a row; only a percentage can lower one.

## Handing off

A shift reaches the PM one of two ways, and the handoff file is written first either way:

- **Automatic.** simplicity's context hook starts `/simplicity:shift-session --auto`, which asks
  the decider once. On "Shift now", stop inside that running skill before its step 1, do steps
  1 and 2 below, then let the skill carry on from its step 1. Never start the skill a second
  time.
- **Manual.** The decider asks for the shift by name, which starts the skill. Stop before its
  step 1 as above, do steps 1 and 2 below, then let it carry on. Never start it a second time.

The steps:

1. Make the turn's last tracker write first, then re-read GitHub for every lane and review in
   flight, so the handoff is not a step behind. Write `handoffs/part-<N>.md` on the rulings branch from the pm skill's own
   `templates/handoff.md` (simplicity has no template for it):
   every lane with its title, unit, branch, SHA and whether that is on `origin`; reviews in
   flight and their round; the decider's open questions word for word; every unanswered message copied in; the
   next step; the plan issues. It is committed, so it holds nothing secret. Refresh
   `state/state-note.md` from the same facts in the same commit; never leave it the blank
   template.
2. Commit and push both. Record the commit SHA and the file's hash:
   `git show <commit>:handoffs/part-<N>.md | sha256sum`.
3. In the skill's own steps: put these three values into the child's prompt, in its Next step,
   word for word: "Read handoff `<path>` at commit `<sha>` on `<rulings_branch>`; its sha256
   must be `<hash>`." Its tracker step comments only on the plan issues you own. Its branch scan
   skips the records worktree: that branch is already pushed, and as an orphan branch it has no
   merge base with the default branch, so the scan's diff would fail there.
4. **If the push in step 2 is refused**, put the handoff's full text into the prompt's Context
   section instead, with its sha256, and tell the child to commit it once it can.

The child PM verifies the hash before trusting a word of the handoff (SKILL.md, step 1).
