# Trial log

The decider ruled the trial runs from a cloud session against a throwaway repository
(`EONRaider/pm-trial`). Results are labelled MEASURED with the configuration seen.

## 2026-11-05, Claude Code 2.1.318, cloud container, Python 3.13, git 2.43, gh 2.89

Done:

1. **Plugin loads with its dependency.** MEASURED: `claude -p --plugin-dir <simplicity>
   --plugin-dir <project-manager>` listed `project-manager:pm`, `project-manager:pm-setup` and
   simplicity's skills.
2. **Barred-folder guard.** MEASURED: in a headless session with the hook on and `secrets/`
   barred, `cat secrets/key.pem` was refused with "Command refused: secrets/key.pem is barred".
3. **Plain-language Stop hook.** MEASURED: a reply carrying a commit hash was sent back once; the
   plain rewrite passed; no loop. The app labels the send-back "Stop hook error occurred" in its
   notifications, though the hook exited 0.
4. **Tracker-write reminder.** MEASURED: after a successful `gh issue comment` (a stand-in `gh`),
   the session received the reminder text. It does not fire after a failed command.
5. **Question check.** Not measured: headless sessions have no question tool. Unit tests only.
6. **Trial repository set up.** MEASURED: settings file on `main`, checked "valid"; orphan
   `pm-records` branch with an empty register pushed from this cloud session.
7. **Board access.** MEASURED: `gh` in this cloud session is not signed in (token invalid), so the
   board steps fall back to "Pending for the PM" comments, as designed.
8. **Plan review.** A one-unit plan draft was reviewed by a fresh agent: 0 Blocker, 1 Major (its
   check compared against `origin/main` before any fetch), 1 Minor (a `test "$(cat ...)"` check
   that ignores trailing newlines).

9. **Extra guard review** (the decider ordered one past the two-round cap). It found that the
   last fix let grep, cut and openssl read a barred file named without a slash; fixed with tests
   in the same session (188 tests).
10. **Plan approval and records.** MEASURED on `EONRaider/pm-trial`: the plan's revision passed a
    second fresh review (0 Blocker, 0 Major, 1 Minor, folded in); the decider approved it; the
    approved text is frozen on `pm-records`; the plan issue carries the approval ruling as its
    first comment; the register row links it; the unit's sub-issue was created and attached in
    one call; issue type Task applied on a user-owned repository.
11. **Lane exchange.** MEASURED: a cloud lane started with `create_session` implemented the unit,
    pushed its branch, opened a pull request, and sent its finished-unit report with the remote
    `send_message` tool; it reached the PM session as a new turn. So a cloud session started by
    another can message its parent. It also posted the report on its sub-issue, and wrote to no
    other issue.
12. **Lane handoff.** MEASURED: the lane ran `/simplicity:shift-session` by name, started a child
    titled "Lane hello file -> Part 2", and commented only on its own sub-issue.
13. **Unit review.** A fresh reviewer found nothing to fix; the PM re-checked the commit's diff
    and content.
14. **PM handoff.** MEASURED: the PM committed `handoffs/part-1.md` to `pm-records` and started
    a fresh PM session with the commit, path and sha256. The fresh PM matched the hash, found the
    handoff commit at the branch tip, checked ruling R-1 in both places, matched the lane's branch
    head to the pull request's, and reported to its parent by message. It found three
    disagreements and let GitHub win each:
    - The handoff said the unit review was still waiting; a comment posted 43 seconds after the
      handoff commit closed it with no findings. The "GitHub wins" check caught the stale line,
      as designed.
    - The review lived only as a comment on the sub-issue, so the pull request itself shows no
      review. Expected: the PM's reviewer never approves a pull request.
    - The state note was still the blank template. The handoff steps never said to refresh it;
      fixed in `skills/pm/references/usage.md`, "Handing off", step 1.

Not yet done:

1. Close an issue as not planned and record the Status the board shows (needs the decider's board
   access).
2. The decider merges or closes the trial pull request; then delete the trial repository.

Open follow-ups for the decider to rule on (suggested by the outgoing trial PM; not applied,
since each changes the method and no review round is open):

1. Write the handoff only after the turn's last tracker write, or re-read GitHub just before
   committing it, so it is not stale by one event.
2. Post each unit review's outcome as a comment on the pull request too, not only on the
   sub-issue, so someone reading only the pull request sees it.
