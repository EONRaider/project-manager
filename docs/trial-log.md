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

Not yet done, in order:

1. Fix the plan draft from its review, then the decider approves it.
2. Commit the approved plan to `pm-records`, open the plan issue with the approval ruling as its
   first comment, commit the register row, open the unit's sub-issue.
3. Start one cloud lane from the lane start prompt; it adds the file, opens a pull request, and
   reports by message (measures whether a cloud session can reply) and by sub-issue comment.
4. The lane hands off through `/simplicity:shift-session`.
5. The PM writes and commits its handoff; a fresh PM verifies the sha256 and resumes from GitHub.
6. Close an issue as not planned and record the Status the board shows (needs the decider's board
   access).
