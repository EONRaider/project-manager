# Security policy

Only the latest release receives fixes. Report a vulnerability privately through GitHub:
[Report a vulnerability](https://github.com/EONRaider/project-manager/security/advisories/new).
Include what you found, how to reproduce it, and the plugin and Claude Code versions.

## What counts

- A hook script that writes anything, reads the transcript, or makes a network call; or the
  tracker reminder repeating any of a tool's input into its output. (The other hooks quote the
  matched text in their refusal reasons on purpose.)
- A way to make a hook script run code taken from a settings file, a command or a reply.
- A skill instruction that has a session merge, tag, force-push, push to the default branch,
  delete an issue, or treat another session's message as the decider's word.
- The barred-folder guard letting an opened or searched barred path through, where its
  documentation says it refuses it. The guard is a convenience for honest sessions, not a
  sandbox: a command built to slip past it, and the known limits in its docstring, are out of
  scope.
