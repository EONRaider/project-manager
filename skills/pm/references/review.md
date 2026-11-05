# Review: one review, one review of the changes

Every plan and every unit gets at most two reviewer rounds: one review, and one review of the
changes when round one found a Blocker or Major. The author never reviews its own work, and the
PM never reviews its own writing.

## Round one

1. **Freeze.** Name exactly what is reviewed: a plan draft by its sha256 in
   `<notes_dir>/reviews/<slug>/`, or a unit by its branch and head SHA.
2. **Brief.** Start one fresh agent that wrote none of it, on `<review_model>`. The brief, inline:
   - what to read: the frozen target, and how to verify the hash or SHA first;
   - the rules the target must meet: the plan or unit brief, the decider's rulings it cites,
     quoted from the register;
   - the barred paths, as exclusions to put inside every search;
   - read-only: no edits, no commits, no GitHub writes, no messages;
   - severity: Blocker (it can't work, ships a serious defect, or breaks a ruling), Major (a real
     defect the build would hit), Minor (clarity or low risk); no style points;
   - every finding quotes the target's lines, labels its evidence MEASURED, READ or CLAIM, and
     carries a concrete fix or a clearly framed decision for the decider;
   - the reply: counts by severity, then each finding, then "Checked and found sound" and "Not
     checked".

   The brief carries none of your own conclusions about the target. A reviewer handed your view
   checks your view instead of the work.
3. **Verify.** Check every Blocker and Major against its source yourself: the file at the named
   commit, the page, the plan line. Mark each "verified" with what you read, or "reviewer's
   reading" when you could not re-read it. Drop a finding the source disproves, and say why.
4. **Triage.** Each Blocker or Major gets a fix the author makes, or a question for the decider.
   Minors need no question; they go into the revision brief.
5. **Revision brief.** One brief to the author: every finding to fix and its fix, each decider
   ruling in the decider's own words, and the Minors. Have the advisor read it first.

## Round two: the changes only

A round one with no Blocker or Major closes the review: its Minors go into the revision brief
and need no second round.

1. When the author reports the revision ready, freeze it the same way.
2. Start one fresh agent that took no part in round one. It reads only the changes (the diff from
   the first frozen version to the new one) against round one's findings: did each fix land, did
   any fix break something else, and one fresh pass for contradictions in the changed text.
3. The review closes on this round if it finds no Blocker or Major.
4. If it still finds one, check the fix against its source yourself, then the decider decides.
   There is never a third reviewer round.
5. Minors left over go into the unit's next brief, or a plan's first unit brief.

## After the review

Re-run the unit's own checks yourself and spot-check the diff before you call the unit reviewed.
A review report is evidence toward your own check, never a substitute for it.

Record the outcome on the unit's sub-issue (or the plan issue): counts by severity, what was
fixed, what the decider ruled, and where the full findings live. For a unit, post the same
outcome as a comment on its pull request too, so someone reading only the pull request sees it.
Never approve the pull request.
