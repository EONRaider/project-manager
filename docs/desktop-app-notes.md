# Dated notes: rules that work around current app behaviour

The method in `skills/pm` states no rule that depends on a particular version of the Claude
desktop app or CLI. Those rules live here, each dated, with the versions it was seen on and what
to re-check. Each entry is a CLAIM until its "Measured" line says otherwise.

## The plan-approval screen blocks messages

- Seen: 2026-10, desktop app. A session parked on the plan-approval screen reads no messages.
- Rule: a planning lane sends the PM a pointer to its plan and ends its turn without opening the
  approval screen. It opens the screen only after the PM's review arrives.
- Re-check: whether a session on the approval screen now receives a `SendMessage`.
- Measured: not yet.

## Cloud sessions and messaging

- Seen: 2026-11-05, Claude Code 2.1.318 in a cloud session. Two tool descriptions disagree: the
  session-listing tool says a cloud session "cannot message any session back yet"; the remote
  send-message tool says the target "can reply with its own send_message".
- Rule: until measured, a cloud lane posts its reports as comments on its unit's sub-issue, and
  the PM reads them there.
- Re-check: start a cloud lane, send it a message, and see whether its reply arrives.
- Measured: not yet.

## `ListAgents` lists local sessions

- Seen: 2026-11, desktop app and CLI. `ListAgents` lists sessions on the same machine (and, with
  Remote Control, the account's other sessions).
- Rule: address the PM by its current title from `ListAgents`, never an address from an earlier
  message.

## Titles may come back escaped

- Seen: 2026-10, desktop app. A session title holding `->` may be returned as `-&gt;` or `→`.
- Rule: read all three as `->` when matching "Handed Off" or "On hold"; always write a plain `->`.

## Where a usage reading comes from

- Seen: 2026-10 and 2026-11.
  - A local desktop session's session-management `get_usage` tool returned the 5-hour and weekly
    percentages with reset times. No Anthropic page documents the tool.
  - A cloud session's `get_session` reports `rate_limit_info` (`status`, `resetsAt`,
    `rateLimitType`, `isUsingOverage`) with no percentage. `allowed_warning` tracks pace, not a
    level, so `allowed` is no evidence of headroom. `isUsingOverage: true` means paid extra
    usage.
  - Otherwise, the decider's screenshot of the usage popover.
- Rule: a warning can raise a usage row; only a percentage can lower one.
- Re-check: after each Claude Code update.

## Hooks in worktree sessions

- Seen: 2026-10, desktop app. A desktop session working in a git worktree runs the hooks of the
  main checkout, read live from its working tree.
- Rule: a change to the project's own settings file reaches desktop sessions only once the main
  checkout carries it.

## Cloud sessions and pushes to the rulings branch

- Seen: 2026-11-05. A cloud session can be told to push only to its own assigned branch.
- Rule: a handoff whose push is refused goes inline into the child's prompt, with its sha256.
- Re-check: a direct push to the rulings branch from a cloud session.
- Measured: 2026-11-05, Claude Code 2.1.318: a cloud session pushed a new orphan `pm-records`
  branch to an attached repository. The session's own assigned-branch rule did not cover that
  repository, so the refused case is still unmeasured.

## GitHub tools in a cloud session

- Seen: 2026-11-05, cloud session. The GitHub MCP tools offered had no tools for Projects,
  labels or issue dependencies, and `gh` was not signed in for writes.
- Rule: such a session posts "Pending for the PM" comments for board, label and dependency
  changes.

## The Stop hook's send-back is labelled an error

- Seen: 2026-11-05, Claude Code 2.1.318, headless. When the plain-language Stop hook sends a
  reply back (`decision: block`, exit 0), the app notifies "Stop hook error occurred".
- Rule: nothing to change in the hook; tell the decider the label is the app's, not a failure.
- Measured: yes, as above.
