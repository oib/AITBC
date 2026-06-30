# Release Documentation Maintenance

**Last Updated**: June 30, 2026
**Version**: 1.0
**Maintainers**: Documentation Team

## Purpose

This document provides guidelines for maintaining the AITBC release documentation structure, including how to update the release index when new releases are added, and the policy for handling legacy documentation.

## Documentation Structure Evolution

### Old Format (v0.0.x - v0.4.x)

**Structure**: Single `RELEASE_vX.Y.Z.md` files in the `/opt/aitbc/docs/releases/` root directory

**Example**: `RELEASE_v0.4.7.md`, `RELEASE_v0.4.22.md`

**Status**: Archived to `archive/` subdirectory (2026-06-30)

### New Format (v0.5.x+)

**Structure**: Versioned directories with structured files

**Directory Structure**:
```
docs/releases/
  vX.Y.Z/
    change.log      - Main release notes
    AGENTS.md       - Agent task assignments
    suggestions.md  - Investigation findings (optional)
```

**Example**: `v0.6.0/change.log`, `v0.6.0/AGENTS.md`

## Adding New Releases

### Step 1: Create Release Directory

When a new release is planned, create a versioned directory:

```bash
mkdir -p /opt/aitbc/docs/releases/vX.Y.Z
```

### Step 2: Create Standard Files

Create the standard files for the new release:

- `change.log` - Main release notes (required)
- `AGENTS.md` - Agent task assignments (required)
- `suggestions.md` - Investigation findings (optional)

### Step 3: Update Release Index

Update `/opt/aitbc/docs/releases/README.md` to include the new release:

1. Add the release to the appropriate section (Current Releases or Legacy Releases)
2. Use the correct link format:
   - For v0.5.x+: `[vX.Y.Z](vX.Y.Z/change.log)`
   - For v0.4.x and earlier: `[vX.Y.Z](RELEASE_vX.Y.Z.md)` (if not archived)
3. Include a brief description of the release
4. Update the "Last Updated" date and version number

### Step 4: Update Root AGENTS.md

If the release is the current in-flight release, update `/opt/aitbc/AGENTS.md`:

1. Add the release to the "Completed Releases" or "Planned Releases" section
2. Update the release sequence diagram if needed
3. Add any scope correction notes

## Legacy Documentation Policy

### Archiving Criteria

Documentation should be archived when:

1. **Format Change**: When the documentation format changes significantly (e.g., single-file to directory structure)
2. **Deprecation**: When features are deprecated and no longer supported
3. **Age**: When documentation is more than 6 months old and superseded by newer versions

### Archiving Process

1. Create an `archive/` subdirectory if it doesn't exist
2. Move legacy files to the archive with appropriate subdirectories:
   ```bash
   mkdir -p /opt/aitbc/docs/releases/archive/v0.4.x
   mv /opt/aitbc/docs/releases/RELEASE_v0.4.*.md /opt/aitbc/docs/releases/archive/v0.4.x/
   ```
3. Update the release index to reference the archived location
4. Add a note explaining why the files were archived

### Archive Structure

```
docs/releases/
  archive/
    v0.3.x/
      RELEASE_v0.3.7.md
      RELEASE_v0.3.8.md
      ...
    v0.4.x/
      RELEASE_v0.4.0.md
      RELEASE_v0.4.1.md
      ...
  vX.Y.Z/
    change.log
    AGENTS.md
    ...
```

## Deprecation Notices

When features are deprecated:

1. Add a deprecation notice at the top of relevant documentation files
2. Include the version number when the deprecation occurred
3. Explain what replaced the deprecated feature
4. Provide migration guidance if applicable

**Example Notice**:
```markdown
> **⚠️ DEPRECATION NOTICE (v0.4.7)**: The GPU-only marketplace with bidding was deprecated in v0.4.7.
> The current marketplace focuses on hardware+software bundles with fixed pricing.
```

## Documentation Standards

### File Naming

- Use lowercase with hyphens for file names: `change.log`, `AGENTS.md`
- Use semantic versioning for directories: `v0.6.0`, `v1.0.0`
- Use descriptive names for topic files: `SERVICE_REPUTATION.md`, `MULTI_GPU_SUPPORT.md`

### Markdown Formatting

- Use consistent heading levels (H1 for titles, H2 for sections)
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
- Use absolute URLs for external references
- Test links after adding them

## Version References in Documentation

When referencing specific versions in documentation:

1. Prefer version-agnostic language when possible
2. When specific versions are necessary, explain why
3. Update version references when new releases are made
4. Consider using "latest" or "current" for user-facing documentation

## Maintenance Checklist

When adding a new release:

- [ ] Create release directory
- [ ] Create standard files (change.log, AGENTS.md)
- [ ] Update release index (README.md)
- [ ] Update root AGENTS.md if applicable
- [ ] Check for deprecated features to document
- [ ] Update cross-references in other documentation
- [ ] Test all links
- [ ] Update this maintenance document if process changes

## Common Issues

### Issue: Release Index Out of Date

**Symptom**: New releases not listed in `/opt/aitbc/docs/releases/README.md`

**Solution**: Follow Step 3 in "Adding New Releases" above

### Issue: Broken Links After Archiving

**Symptom**: Links to archived files return 404

**Solution**: Update all references to point to the new archive location

### Issue: Inconsistent File Formats

**Symptom**: Some releases use old format, some use new format

**Solution**: Archive old format releases, ensure new releases use current format

## Contact

For questions about release documentation maintenance, contact the documentation team or refer to the main [Documentation Home](../README.md).

---

*Last Updated: June 30, 2026*
*Version: 1.0*
