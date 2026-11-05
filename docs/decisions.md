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

Defaults the decider can override: the marketplace entry lands after the trial passes and the
decider tags the release; the rulings branch is `pm-records`; `simplicity` is a dependency with no
version range.
