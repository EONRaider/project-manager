# Releasing

Users install project-manager through the `eonraider` marketplace (`EONRaider/claude-plugins`),
which pins each plugin to a tag and a commit SHA. Merging to `main` alone ships nothing.

1. **Trial.** Before the first release, the trial in the design note's section 17 has passed, or
   the decider has waived a step in writing.
2. **Rerun the evals that cover simplicity.** This plugin depends on simplicity by name, with no
   version range, so it follows simplicity's latest release. Rerun the handoff steps of the trial
   after each simplicity release.
3. **Bump the version** in `.claude-plugin/plugin.json`.
4. **Security scan** each skill with SkillArtisan's `scripts/security_scan.py` (needs
   `gitleaks`) and commit the `.security-scan-passed` markers.
5. **Validate**: `claude plugin validate --strict .`
6. **Date the changelog.**
7. **Merge to `main`**, then the decider tags the merge commit `vX.Y.Z` and pushes the tag.
8. **Update the marketplace**: in `EONRaider/claude-plugins`, add or edit the `project-manager`
   entry in `.claude-plugin/marketplace.json` with the tag as `ref`, the tagged commit as `sha`,
   and the version; validate it with `claude plugin validate .claude-plugin/marketplace.json`.
