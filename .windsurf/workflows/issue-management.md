---
description: Workflow for managing and documenting issues from current to resolved
---

# Issue Management Workflow

This workflow handles the lifecycle of issues from identification to resolution and archival.

## Prerequisites

// turbo
- Ensure you have write access to the docs directory
- Check if the issue is already tracked in docs/currentissue.md

## Steps

### 1. Identify New Issue
```bash
# Check if currentissue.md already exists and has content
cat /home/oib/windsurf/aitbc/docs/currentissue.md
```

### 2. Document Issue in currentissue.md
If tracking a new issue:
- Add section with clear, descriptive title
- Include date, status, description
- List affected components
- Document attempted fixes
- Update status regularly

### 3. Monitor Progress
- Update the issue status as work progresses
- Add resolution details when fixed
- Include code changes, configuration updates, etc.

### 4. When Issue is Resolved
```bash
# Move to issues folder with machine-readable name
mv /home/oib/windsurf/aitbc/docs/currentissue.md \
   /home/oib/windsurf/aitbc/docs/issues/YYYY-MM-DD_brief-description.md

# Example:
# mv docs/currentissue.md docs/issues/2026-01-29_cross-site-sync-resolved.md
```

### 5. Create New Empty currentissue.md
```bash
# Create fresh currentissue.md
cat > /home/oib/windsurf/aitbc/docs/currentissue.md << 'EOF'
# Current Issues

*No current issues to report.*

---

## Usage Guidelines

When tracking a new issue:
1. Add a new section with a descriptive title
2. Include the date and current status
3. Describe the issue, affected components, and any fixes attempted
4. Update status as progress is made
5. Once resolved, move this file to `docs/issues/` with a machine-readable name

## Recent Resolved Issues

See `docs/issues/` for resolved issues and their solutions.
EOF
```

## Naming Convention for Archived Issues

Use format: `YYYY-MM-DD_brief-description.md`
- Date: Year-Month-Day of resolution
- Description: Brief, lowercase, hyphen-separated summary
- Examples:
  - `2026-01-29_cross-site-sync-resolved.md`
  - `2026-01-15_pytest-warnings-fixed.md`
  - `2026-01-10_database-migration-issue.md`

## Best Practices

1. **For Complex Issues**: Use `docs/currentissue.md` as the central tracking document
2. **Regular Updates**: Update status daily for active issues
3. **Detailed Resolution**: Document root cause and solution clearly
4. **Cross-References**: Link to related code changes, PRs, or documentation
5. **Archive Promptly**: Move resolved issues within 24 hours of resolution

## Integration with Other Workflows

- Use with `/docs` workflow to keep documentation current
- Reference resolved issues in `docs/done.md`
- Link technical details in `docs/reports/` as needed

## Memory Aid

Remember: For hard-to-track or complex issues spanning multiple components, always use `docs/currentissue.md` as the single source of truth for current status and resolution progress.
