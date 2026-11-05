# Contributing to project-manager

Bug reports, fixes and documentation corrections are welcome. For anything larger than a small
fix, open an issue first. Security problems go through [private reporting](SECURITY.md).

## Setup

Python 3.10 or later and Claude Code.

```bash
python3 -m pip install pytest ruff mypy
```

The checks CI runs:

```bash
ruff check scripts tests
ruff format --check scripts tests
mypy --strict scripts tests
pytest -q
```

Try the plugin from a checkout, with simplicity loaded the same way:

```bash
claude --plugin-dir /path/to/simplicity --plugin-dir /path/to/project-manager
```

```bash
claude plugin validate --strict .
```

## Rules for changes

- Hook scripts use the standard library only, fail open, and never read the transcript.
- The method in `skills/pm` names no app-version-specific behaviour; that goes in
  `docs/desktop-app-notes.md`, dated.
- Every hook pattern change comes with a test for a true match and a near miss.
