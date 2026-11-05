# Plan: Add a hello file

A one-unit plan for the project-manager trial.

## Unit 1: Add hello.txt

- Delivers: a file `hello.txt` at the repository root holding the single line `hello from a lane`.
- Files touched: `hello.txt` only.
- Checks that prove it: `test "$(cat hello.txt)" = "hello from a lane"` exits 0; `git diff --stat origin/main...HEAD` lists only `hello.txt`.
- Waits on: nothing.

## Failure and abuse

Not a feature: no user-facing behaviour, nothing to fail or abuse. Recovery is reverting the one commit.

## Outside services

None. The plan rests on no outside service's behaviour.
