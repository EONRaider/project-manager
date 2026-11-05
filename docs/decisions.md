# Decisions

The decider's rulings on this plugin, in the order they were made. Each row quotes the option the
decider chose.

| Date | Ruling | Decider's choice |
|---|---|---|
| 2026-11-05 | The plugin lives in its own repository, in the same marketplace as `simplicity`, which it depends on | "We'll need to create this plugin under a new repo called EONRaider/project-manager" |
| 2026-11-05 | The design note at `docs/design-note.md` (sha256 `cc1fa18a1368f1aeba41d1f4b3dc40109af2ea0898e56e3e381d891123945687`) is approved, including the author's fix to the plan-approval order raised in the second review | "Approve" |
| 2026-11-05 | The trial runs from a cloud session against a throwaway repository, and also settles whether cloud sessions can reply | "Cloud trial from here" |
| 2026-11-05 | A fourth hook, the barred-path guard, ships off by default | "Include it, off by default" |
| 2026-11-05 | The GitHub Project board is the only status store; a session that can't write it queues the change as a comment | "Board only, changes queued" |
| 2026-11-05 | The trial plan is approved, and one extra review of the barred-folder guard runs past the two-round limit | "Approve" |
| 2026-11-05 | Pull request 1 merges now; the tag waits for the board check and the security scan | "Merge now, tag later" |
| 2026-11-05 | The PM makes its last tracker write and re-reads GitHub before committing a handoff | "Yes, re-read first" |
| 2026-11-05 | Each unit review's outcome is also posted as a comment on the unit's pull request | "Yes, both places" |
| 2026-11-05 | The state-note refresh at handoff stays as written, without a review | "Keep it unreviewed" |

Defaults the decider can override: the marketplace entry lands after the trial passes and the
decider tags the release; the rulings branch is `pm-records`; `simplicity` is a dependency with no
version range.
