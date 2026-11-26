# Release Documentation Maintenance

**Last Updated**: November 26, 2026
**Version**: 2.0
**Maintainers**: Documentation Team

## Purpose

This document provides guidelines for maintaining the AITBC release documentation
structure, including how to add new release notes and supporting artifacts under
the topic-organized layout introduced by DOCS-RELEASES-TOPIC-REORG-1 (#2974).

## Current Structure

```
docs/releases/
  README.md              - release history index (version -> 2026 index anchors)
  STATUS.md              - release status tracker
  MAINTENANCE.md         - this file
  RELEASE_PREP.md        - upcoming-release preparation notes
  2026/
    README.md            - topic index + per-version -> topic-files index
    MANIFEST.csv         - reorg accounting (old path -> new path, hashes)
    <topic>_release.log  - running per-topic history, versions as sections
    versions/<vX.Y>/     - supporting artifacts, byte-identical per version dir
```

The 14 topic files (`consensus`, `bridge`, `market`, `escrow`, `agent`,
`wallet`, `cli`, `deploy_ops`, `security`, `website`, `testing`,
`performance`, `docs_meta`, `general`) each hold every release's sections
for that subsystem as `## vX.Y.Z` groups, newest first. Version-level
material (overviews, verification summaries, breaking changes, migration
guides) lives in `general_release.log`.

Historical note: the pre-#2974 tree was version-organized (`vX.Y/`
directories of `*_change.log` + supporting files). It is preserved in git
history; `MANIFEST.csv` accounts for every file. The old `archive/`
subdirectory (v0.0.x–v0.4.x single-file releases) folded into
`2026/versions/`.

## Adding New Releases

### Step 1: Write the release notes into topic files

For each subsystem section in the release's notes, append it under a
`## vX.Y.Z` heading in the matching `2026/<topic>_release.log`, placed in
version-descending order. Version-level sections (Overview, Verification,
Breaking Changes, Migration Guide, Dependencies) go to
`general_release.log`. Keep the existing heading style: `## vX.Y.Z` for the
version group, `### <section name>` for each section.

### Step 2: Add supporting artifacts

Per-version supporting documents (`AGENTS.md` task logs, `suggestions.md`,
plans, audits, unsectioned notes) go **byte-identical** to
`docs/releases/2026/versions/vX.Y/` — one directory per minor version, same
convention as the retired `vX.Y/` dirs. Relative links between files in the
same version dir keep working.

### Step 3: Update indexes

1. `docs/releases/2026/README.md` — add the version to the Version index
   with links to each topic file that gained a `## vX.Y.Z` section.
2. `docs/releases/README.md` — add the version to Release History, linking
   to `2026/README.md#v<x.y.z>`.
3. `docs/MASTER_INDEX.md` — regenerate with
   `python3 scripts/docs/gen_master_index.py` (do not hand-edit).

### Step 4: Update root AGENTS.md

If the release is the current in-flight release, update `/opt/aitbc/AGENTS.md`
release sections as before.

## Deprecation Notices

When features are deprecated:

1. Add a deprecation notice at the top of relevant documentation files
2. Include the version number when the deprecation occurred
3. Explain what replaced the deprecated feature
4. Provide migration guidance if applicable

## Documentation Standards

### File Naming

- Topic logs: `2026/<topic>_release.log` (snake_case, `_release.log` suffix)
- Supporting artifacts: `2026/versions/vX.Y/<original-filename>`
- Use descriptive names for extra topic files

### Markdown Formatting

- Topic logs are `.log` files but follow markdown conventions
- Use consistent heading levels: `## vX.Y.Z` version groups, `###` sections
- Include metadata at the top of files:

  ```markdown
  **Last Updated**: YYYY-MM-DD
  **Version**: X.Y
  **Status**: Planned/In Progress/Complete
  ```

- Use code blocks for commands and code examples
- Use tables for structured data

### Link References

- Use relative paths for internal links
- Links between `versions/` files keep the old `vX.Y/` relative shape
- Links to split release logs should target `2026/README.md#v<x.y.z>`
  (the per-version index) rather than a single topic file
- Test links after adding them

## Version References in Documentation

When referencing specific versions in documentation:

1. Prefer version-agnostic language when possible
2. When specific versions are necessary, explain why
3. Update version references when new releases are made
4. Consider using "latest" or "current" for user-facing documentation

## Maintenance Checklist

When adding a new release:

- [ ] Append sections to the matching `2026/<topic>_release.log` files
- [ ] Add version-level sections to `general_release.log`
- [ ] Place supporting artifacts under `2026/versions/vX.Y/`
- [ ] Update `2026/README.md` version index
- [ ] Update `docs/releases/README.md` release history
- [ ] Regenerate `docs/MASTER_INDEX.md`
- [ ] Update root AGENTS.md if applicable
- [ ] Check for deprecated features to document
- [ ] Update cross-references in other documentation
- [ ] Test all links

## Common Issues

### Issue: Dangling links after the reorg

**Symptom**: Links to `docs/releases/vX.Y/...` return 404

**Solution**: The old tree only exists in git history. Point links at
`docs/releases/2026/README.md#v<x.y.z>` (version index) for split logs, or
`docs/releases/2026/versions/vX.Y/<file>` for moved artifacts. The reorg's
`MANIFEST.csv` maps every old path to its new location.

### Issue: Release Index Out of Date

**Symptom**: New releases not listed in the indexes

**Solution**: Follow Step 3 in "Adding New Releases" above

## Contact

For questions about release documentation maintenance, contact the documentation team or refer to the main [Documentation Home](../README.md).

---

*Last Updated: November 26, 2026*
*Version: 2.0*
