# project-manager

A Claude Code plugin for running a project through one coordinating session and several worker
sessions, with a person deciding and git and GitHub holding the record.

- **The PM** (`/project-manager:pm`) plans, has plans and work reviewed by agents that wrote none
  of it, asks the decider, records rulings and status on GitHub, relays, and hands off at the
  context limit. It never implements.
- **Lanes** are ordinary sessions started from a prompt the PM writes. Each implements one unit
  on its own branch and reports back. Every lane carries the same rules block.
- **The decider** is you: every plan approval, merge, tag and spending decision is yours.

## What it ships

| Part | What it does |
|---|---|
| `/project-manager:pm` | The method: plan, review, approve, dispatch, supervise, record, hand off |
| `/project-manager:pm-setup` | One-time setup: settings file, board status, rulings branch |
| Lane rules block | Fourteen rules pasted into every lane's start prompt |
| Templates | Lane start prompt, PM handoff (verified by sha256), state note, rulings register, settings |
| Hooks (all off until switched on) | Plain-language check on questions and replies, a reminder after GitHub writes, a barred-folder guard |
| [Dated notes](docs/desktop-app-notes.md) | Rules that only work around current app behaviour |

## Tracking

Only git and GitHub:

- a GitHub issue for each plan, and one sub-issue for each unit;
- the GitHub Project board's Status field: Todo, In Progress, Done, Deferred;
- issue comments for rulings and reports;
- an orphan branch that never gets a pull request, holding the rulings register, the approved
  plan texts, the PM's handoffs and its state note.

## Install

Once the first release is listed in the marketplace:

```bash
claude plugin marketplace add EONRaider/claude-plugins
```

```bash
claude plugin install project-manager@eonraider
```

This also installs [simplicity](https://github.com/EONRaider/simplicity), which handles session
handoffs. Then, in the project, run `/project-manager:pm-setup` once, in a local session whose
GitHub CLI is signed in with the `project` scope (`gh auth refresh -s project`).

## Settings

Per-project values live in `.claude/project-manager.json`, committed in the project, because a
plugin's own configuration is stored per user. See
[the example](skills/pm/templates/settings.example.json). Every hook reads this file and does
nothing unless its own flag is `true`.

## Requirements

Claude Code, Python 3.10 or later for the hooks, git, and the GitHub MCP server or the GitHub CLI.

## Design

The approved design and the decisions behind it: [docs/design-note.md](docs/design-note.md),
[docs/decisions.md](docs/decisions.md).

## License

MIT
