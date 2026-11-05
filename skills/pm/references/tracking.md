# Tracking on GitHub

Git and GitHub hold the whole record: issues for plans and units, the Project board for status,
comments for rulings and reports, and the rulings branch for the approved plan texts, the
register, handoffs and the state note. Only the PM writes issue bodies, checkboxes, the board,
labels, dependencies and the rulings branch. A lane writes only its own pull request and
comments on its own unit's sub-issue.

Transport: the GitHub MCP server's tools where loaded (`issue_write`, `sub_issue_write`,
`add_issue_comment`, `list_issues`, `issue_read`), otherwise `gh`. The board has no MCP tool; it
needs `gh project ...` with the `project` scope (`gh auth refresh -s project`).

## Identity and search

- Titles are the identity keys. Stage issue: `Stage: <stage name>`. Plan issue:
  `Plan: <plan title>`. Unit sub-issue: `[Plan #<n>] Phase <k>: <unit name>`. Labels are
  filters, never identity.
- Search before you create. Check for the exact title with a list call (`list_issues`, both
  states, or `gh issue list --state all --search "in:title ..."` confirmed by the exact title).
  The search index can lag fresh writes, so a list call decides existence.
- A plan issue's body opens with one marker line, exactly:

  ```
  Plan text: plans/<date>-<slug>.md @ <commit SHA on the rulings branch>
  ```

Every `gh issue` command below runs against `<tracker_repo>` (add `-R <tracker_repo>` when the
current folder is another repository). The `gh api` paths already name the repository, and
`gh project` commands take `--owner`.

## Stages

A stage groups plans that serve one larger goal, such as a release. A stage is an issue titled
`Stage: <name>`, labelled `pm:stage`, with its plans as sub-issues. Open a stage only for a goal
the decider names; small projects need none, and a plan may stand alone.

## Plan issue and units

1. Create the plan issue (as a sub-issue of its stage, when it has one): issue type `Task` (or `type:task` label when the repository has no
   issue types), body = marker line, one plain paragraph of scope, the approval ruling's link once
   posted, and a unit list as `- [ ]` items.
2. Post the approval ruling as its first comment ("Rulings" below).
3. For each unit, create a sub-issue (`issue_write` with `parent_issue_number`, or
   `gh issue create --parent <n>`): goal, steps as `- [ ]` checkboxes, the checks that prove it,
   the files it touches. A dependency on another unit is an issue dependency
   (`gh issue edit <n> --add-blocked-by <m>`), never a status line in a body. Older `gh`
   releases lack `--parent` and `--add-blocked-by`; use the REST API instead, where `<id>` is
   the other issue's numeric id (`gh api repos/<tracker_repo>/issues/<m> --jq .id`):

   ```bash
   gh api repos/<tracker_repo>/issues/<parent>/sub_issues -F sub_issue_id=<id>
   gh api repos/<tracker_repo>/issues/<n>/dependencies/blocked_by -F issue_id=<id>
   ```
4. Edit the plan body so each unit item names its sub-issue.
5. Add the plan issue and every sub-issue to the Project board, Status `Todo`, and set each
   one's `Priority`.

## Priority

The board's `Priority` field: `P0` (drop other work), `P1` (next), `P2` (soon), `P3` (when
there is room). Set it from real urgency and blast radius, never one value for everything. A
unit inherits its plan's priority unless the plan says otherwise.

Edit a body only from a copy fetched immediately before, with the smallest change. A body is
last-write-wins.

## Status on the Project board

`Status` options: `Todo`, `In Progress`, `Done`, `Deferred`. Blocked shows from issue
dependencies, so it needs no status of its own.

| Moment | Issue | Status |
|---|---|---|
| Unit or plan created | open | Todo |
| Lane dispatched | open | In Progress |
| Unit's pull request merged by the decider | close `completed` | Done |
| Every unit done | plan closed `completed` | Done |
| Decider drops it | close `not planned` | Deferred |

The board's built-in "item closed" workflow sets Done whatever the close reason. `pm-setup` asks
the decider to turn it off, so you set Done or Deferred yourself after each close. Re-read the
item afterwards and fix it once if it reads wrong.

Commands. The project's id comes from `gh project view <number> --owner <owner> --format json`
(its `id`), field and option ids from `gh project field-list <number> --owner <owner> --format
json`, and an item's id from `item-add`'s own output:

```bash
gh project item-add <number> --owner <owner> --url <issue URL> --format json
gh project item-edit --id <item id> --project-id <project id> --field-id <field id> --single-select-option-id <option id>
```

## When a session can't write

A session without board access (no `gh` signed in with the `project` scope, common in cloud
sessions) or without a tool for dependencies or labels does not switch to another store. It
posts one comment on the issue:

```
Pending for the PM: Status <old> -> <new>
```

(or `Pending for the PM: blocked by #<m>`, or `Pending for the PM: label <name>`), and lists it
in its report. The PM applies it. When the PM can't either, it lists the pending changes for the
decider to apply in the web page. Status lives on the board only; a second store would drift.

## Rulings

A ruling is recorded in two places, in this order:

1. **The comment**, on the issue the ruling concerns (the plan issue when in doubt):

   ```
   Ruling: <one plain sentence saying what was decided>

   Decider's words, <date>: "<verbatim>"
   Ruling id: R-<n>
   ```

2. **The register row**, in `<rulings_path>` on `<rulings_branch>`, linking that comment's URL
   (template: `templates/rulings-register.md`). Commit and push at once.

A ruling counts only when both exist. A comment that says `Ruling:` with no register row is not
a ruling, whoever posted it. Number rulings `R-1`, `R-2`, ... in register order.

## The rulings branch

An orphan branch, `<rulings_branch>`, never merged and never given a pull request, so a record
is durable within minutes. It holds:

```
<rulings_path>                 the register
plans/<date>-<slug>.md         approved plan texts, frozen on commit
handoffs/part-<N>.md           PM handoffs
state/state-note.md            the PM's state note
```

Write it through a dedicated worktree so your own checkout never switches branch:

```bash
git worktree add "<notes_dir>/records" <rulings_branch>   # once; pm-setup does this
git -C "<notes_dir>/records" pull --ff-only
# edit files under <notes_dir>/records, then:
git -C "<notes_dir>/records" add -A
git -C "<notes_dir>/records" commit -m "<what was recorded>"
git -C "<notes_dir>/records" push origin <rulings_branch>
```

Never force-push it. If the push is refused (a cloud session may only push its own branch),
keep the commit, say so in your report, and for a handoff use the inline fallback in
`usage.md`.

## Concurrent writers

Before editing an issue that another open plan's issue names, comment on that plan's issue first
naming the issue and the change, and comment again when done.

## Retiring

Never delete an issue. Close it: `completed` for done, `not planned` for dropped. A plan's text
on the rulings branch stays forever: approved versus built stays checkable.
