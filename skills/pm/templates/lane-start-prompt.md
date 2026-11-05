# Lane start prompt

The PM fills every `<...>` and sends the result as the lane's first message. Everything the lane
needs is in the prompt itself.

---

Rename this session `<lane title>` if it isn't already.

You are a lane on `<repository>`. Your unit: **<unit name>**, tracked as sub-issue
`<sub-issue URL>` of plan issue `<plan issue URL>`.

**Goal.** <what the unit delivers, in two or three sentences>

**Start from.** Commit `<base SHA>` (`<on origin | local only: why>`). Create branch
`<branch>` from it:

```bash
git fetch origin
git switch -c <branch> <base SHA>
git rev-parse HEAD
```

The last command must print `<base SHA>` in full. Stop and tell the PM if any command fails or
it prints anything else.

**Steps.**
<the sub-issue's steps, in order>

**Checks that prove it.** Run each and paste its result into your report:
<commands>

**Keep these unchanged.** <invariants the unit must not break>

**When done.** Push the branch, open a pull request against `<default branch>` that names the
sub-issue, and send the PM your finished-unit report (rule 3). A reviewer that wrote none of your
work will review it.

**The PM** is the session titled `<PM title>`.

<the lane rules block from references/lane-rules.md, filled in>
