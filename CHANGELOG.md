# Changelog

## Unreleased

### Added

- `/project-manager:pm`, the PM working method, with references for the standing rules, review,
  GitHub tracking, the lane rules block, and usage limits and handoffs.
- `/project-manager:pm-setup`, one-time project setup.
- Templates: lane start prompt, PM handoff, state note, rulings register, settings file.
- Four opt-in hooks: `question_check`, `plain_language_stop`, `tracker_write_notice` and
  `barred_paths`, each reading `.claude/project-manager.json`.
- Dated notes for rules that work around current app behaviour.
