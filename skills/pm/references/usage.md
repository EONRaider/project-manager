# Usage limits, context, and handing off

Two budgets can end a session's useful work: its context window and the plan's usage limits.

## Context

simplicity's context hook is the only context signal. It suggests a shift when the session's
context use reaches its threshold (60% of the model's window by default, then again every 10
points; the `SIMPLICITY_SHIFT_THRESHOLD` environment variable changes it). This method adds no
limits of its own, so a session never answers to two context policies.

- **At every suggestion**, the PM commits its state note to the rulings branch.
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
  screenshot) depends on the app version: `${CLAUDE_PLUGIN_ROOT}/docs/desktop-app-notes.md`.
  A reading that warns can raise a row; only a percentage can lower one.

## Handing off

When the decider has said to shift, before anything else is committed:

1. Write `handoffs/part-<N>.md` on the rulings branch from `templates/handoff.md`: every lane
   with its title, unit, branch, SHA and whether that is on `origin`; reviews in flight and their
   round; the decider's open questions word for word; every unanswered message copied in; the
   next step; the plan issues. It is committed, so it holds nothing secret.
2. Commit and push it. Record the commit SHA and the file's hash:
   `git show <commit>:handoffs/part-<N>.md | sha256sum`.
3. Run `/simplicity:shift-session`. Its handoff prompt is written by that skill; put these three
   values into the prompt's Next step, word for word: "Read handoff `<path>` at commit `<sha>` on
   `<rulings_branch>`; its sha256 must be `<hash>`." Its tracker step comments only on the plan
   issues you own.
4. **If the push in step 2 is refused**, put the handoff's full text into the prompt's Context
   section instead, with its sha256, and tell the child to commit it once it can.

The child PM verifies the hash before trusting a word of the handoff (SKILL.md, step 1).
