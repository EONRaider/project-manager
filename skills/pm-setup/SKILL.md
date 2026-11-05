---
name: pm-setup
description: One-time setup of a project for the project-manager method. Writes the project's settings file (.claude/project-manager.json), checks the repository's issue types, prepares the GitHub Project board (a Deferred status, the close workflow switched off), creates the orphan rulings branch with an empty register, and adds the records worktree. Confirms each write with the user before making it. Use when the user runs /project-manager:pm-setup, or when /project-manager:pm finds no settings file. Run it in a local session whose GitHub CLI is signed in with the project scope.
license: MIT (see plugin root LICENSE)
compatibility: Claude Code. Needs git, and the GitHub CLI (gh) signed in with the repo and project scopes for the board steps; without the project scope it finishes every other step and lists the board steps for the user.
---

# pm-setup

Prepare this project for `/project-manager:pm`. Each step checks what already exists and only
adds what is missing, so running it again is safe. Ask the user before each write, in plain
words, with `AskUserQuestion`; a step the user declines is listed at the end as not done.

## 1. Facts

Find, and show the user in one short list:

- the repository (`gh repo view --json nameWithOwner,defaultBranchRef,owner`, or the `origin`
  remote) and whether its owner is a user or an organization;
- whether `gh auth status` shows the `project` scope;
- whether `.claude/project-manager.json` exists (check it with
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm_settings.py" --project-dir "$(git rev-parse --show-toplevel)"`);
- the repository's issue types: `gh api repos/<owner>/<repo>/issue-types --jq '.[].name'`.
  When the list is empty, plans use `type:task` and `type:bug` labels instead, created in step 4.

## 2. The settings file

Ask the user for the values the file needs, with a recommended default for each:

- `tracker_repo`: the repository that holds plans and units, as `owner/name`, default this one;
- `decider`: the name sessions use for the user;
- `project`: the GitHub Project for status, an existing one by number or a new one (step 3);
- `notes_dir`: an absolute path outside the repository for working files, default
  `$HOME/pm-notes/<repo>` expanded to its full path (the settings check refuses a relative one);
- `barred_paths`: folders no session may open or list, written as git pathspec exclusions such
  as `:(top,exclude)secrets/`; none by default. Prefer folders: a pattern with no fixed folder,
  such as `:(top,exclude,icase)*private*`, still guards Bash searches, but the Grep and Glob
  tools can't take exclusions, so the guard refuses them only when their root matches it;
- which hooks to switch on (all off by default): `question_check` (refuses a question to the user
  that carries ids or file names), `plain_language_stop` (sends back a reply that does),
  `tracker_write_notice` (reminds a session to tell the PM after a GitHub write),
  `barred_paths` (refuses opening or searching the barred paths; a convenience for honest
  sessions with limits listed in its script, not a sandbox: a command inside a script, alias or
  function is not seen, and `git diff` or `git log -p` over a whole range can still show
  barred content);
- `shorthand.id_prefixes`: the project's own ticket prefixes, if any, for the plain-language
  checks.

Write the file from `${CLAUDE_PLUGIN_ROOT}/skills/pm/templates/settings.example.json`, check it
with `pm_settings.py`, and commit it on a branch for the user to merge; never push to the
default branch. Tell the user the hooks take effect in sessions started after the merge.

## 3. The Project board

Needs the `project` scope; without it, list these steps for the user and move on.

1. Use the named Project, or create one: `gh project create --owner <owner> --title "<repo>"`,
   then `gh project link <number> --owner <owner> --repo <repo>`.
2. Read its fields: `gh project field-list <number> --owner <owner> --format json`. The `Status`
   field should hold `Todo`, `In Progress`, `Done` and `Deferred`.
3. If `Deferred` is missing: on a board with no items, it may be added through the GraphQL
   `updateProjectV2Field` mutation, which **replaces** the whole option list, so every existing
   option must be sent back with its `id`. Get the user's yes first, and re-read the field after.
   On a board that already has items, don't call it: ask the user to add `Deferred` in the
   board's web page (the Status field's settings, "Add option").
4. Ask the user to open the board's Workflows page and turn off **Item closed**, so closing an
   issue as not planned doesn't mark it Done. Keep **Pull request merged** on.
5. If the board has no `Priority` field, create it:
   `gh project field-create <number> --owner <owner> --name Priority --data-type SINGLE_SELECT
   --single-select-options P0,P1,P2,P3`.

## 4. Labels

Create `pm:stage`, for stage issues (`gh label create pm:stage --description "A stage of
plans"`). Only when the repository has no issue types, also create `type:task` and `type:bug`.
Nothing else needs a label.

## 5. The rulings branch

1. If `origin` has no `<rulings_branch>`, create it as an orphan branch holding only the register,
   without touching the user's checkout:

   ```bash
   git worktree add --orphan -b <rulings_branch> "<notes_dir>/records"
   ```

   (Git older than 2.42 has no `--orphan` for worktrees: create the branch with
   `git switch --orphan` in a temporary clone instead.) Copy
   `${CLAUDE_PLUGIN_ROOT}/skills/pm/templates/rulings-register.md` to `<rulings_path>` with its
   example row removed, commit "Start the rulings register", and push it.
2. If it exists, add the worktree from it: `git worktree add "<notes_dir>/records" <rulings_branch>`.
3. Check whether a branch ruleset or protection rule would refuse a direct push to it
   (`gh api repos/<owner>/<repo>/rules/branches/<rulings_branch>`), and whether the project's CI
   runs on every branch push; tell the user about either.

## 6. Report

A short plain list: what was set up, what the user still has to do (merge the settings branch,
board steps without the scope, the close workflow), and how to start a PM:
`/project-manager:pm` in a session titled `<pm_title_prefix><topic>`.
