---
description: Comprehensive documentation management and update workflow
title: AITBC Documentation Management
version: 2.0
auto_execution_mode: 3
---

# AITBC Documentation Management Workflow

This workflow manages and updates all AITBC project documentation, ensuring consistency and accuracy across the documentation ecosystem.

## Priority Documentation Updates

### High Priority Files
```bash
# Update core project documentation first
docs/beginner/02_project/5_done.md
docs/beginner/02_project/2_roadmap.md

# Then update other key documentation
docs/README.md
docs/MASTER_INDEX.md
docs/project/README.md
docs/project/WORKING_SETUP.md
```

## Documentation Structure

### Current Documentation Organization
```
docs/
├── README.md                    # Main documentation entry point
├── MASTER_INDEX.md              # Complete documentation index
├── beginner/                    # Beginner-friendly documentation
│   ├── 02_project/             # Project-specific docs
│   │   ├── 2_roadmap.md       # Project roadmap
│   │   └── 5_done.md           # Completed tasks
│   ├── 06_github_resolution/   # GitHub integration
│   └── ...                     # Other beginner docs
├── project/                     # Project management docs
│   ├── README.md               # Project overview
│   ├── WORKING_SETUP.md        # Development setup
│   └── ...                     # Other project docs
├── infrastructure/              # Infrastructure documentation
├── development/                 # Development guides
├── summaries/                   # Documentation summaries
└── ...                         # Other documentation categories
```

## Workflow Steps

### 1. Update Priority Documentation
```bash
# Update completed tasks documentation
cd /opt/aitbc
echo "## Recent Updates" >> docs/beginner/02_project/5_done.md
echo "- $(date): Updated project structure" >> docs/beginner/02_project/5_done.md

# Update roadmap with current status
echo "## Current Status" >> docs/beginner/02_project/2_roadmap.md
echo "- Project consolidation completed" >> docs/beginner/02_project/2_roadmap.md
```

### 2. Update Core Documentation
```bash
# Update main README
echo "## Latest Updates" >> docs/README.md
echo "- Project consolidated to /opt/aitbc" >> docs/README.md

# Update master index
echo "## New Documentation" >> docs/MASTER_INDEX.md
echo "- CLI enhancement documentation" >> docs/MASTER_INDEX.md
```

### 3. Update Technical Documentation
```bash
# Update infrastructure docs
echo "## Service Configuration" >> docs/infrastructure/infrastructure.md
echo "- Coordinator API: port 8000" >> docs/infrastructure/infrastructure.md
echo "- Exchange API: port 8001" >> docs/infrastructure/infrastructure.md
echo "- Blockchain RPC: port 8006" >> docs/infrastructure/infrastructure.md

# Update development guides
echo "## Environment Setup" >> docs/development/setup.md
echo "source /opt/aitbc/venv/bin/activate" >> docs/development/setup.md
```

### 4. Generate Documentation Summaries
```bash
# Create summary of recent changes
echo "# Documentation Update Summary - $(date)" > docs/summaries/latest_updates.md
echo "## Key Changes" >> docs/summaries/latest_updates.md
echo "- Project structure consolidation" >> docs/summaries/latest_updates.md
echo "- CLI enhancement documentation" >> docs/summaries/latest_updates.md
echo "- Service port updates" >> docs/summaries/latest_updates.md
```

### 5. Validate Documentation
```bash
# Check for broken links
find docs/ -name "*.md" -exec grep -l "\[.*\](.*.md)" {} \;

# Verify all referenced files exist
find docs/ -name "*.md" -exec markdownlint {} \; 2>/dev/null || echo "markdownlint not available"

# Check documentation consistency
grep -r "aitbc-cli" docs/ | head -10
```

## Quick Documentation Commands

### Update Specific Sections
```bash
# Update CLI documentation
echo "## CLI Commands" >> docs/project/cli_reference.md
echo "./aitbc-cli --help" >> docs/project/cli_reference.md

# Update API documentation
echo "## API Endpoints" >> docs/infrastructure/api_endpoints.md
echo "- Coordinator: http://localhost:8000" >> docs/infrastructure/api_endpoints.md

# Update service documentation
echo "## Service Status" >> docs/infrastructure/services.md
systemctl status aitbc-coordinator-api.service >> docs/infrastructure/services.md
```

### Generate Documentation Index
```bash
# Create comprehensive index
echo "# AITBC Documentation Index" > docs/DOCUMENTATION_INDEX.md
echo "Generated on: $(date)" >> docs/DOCUMENTATION_INDEX.md
find docs/ -name "*.md" | sort | sed 's/docs\///' >> docs/DOCUMENTATION_INDEX.md
```

### Documentation Review
```bash
# Review recent documentation changes
git log --oneline --since="1 week ago" -- docs/

# Check documentation coverage
find docs/ -name "*.md" | wc -l
echo "Total markdown files: $(find docs/ -name "*.md" | wc -l)"

# Find orphaned documentation
find docs/ -name "*.md" -exec grep -L "README" {} \;
```

## Documentation Standards

### Formatting Guidelines
- Use standard markdown format
- Include table of contents for long documents
- Use proper heading hierarchy (##, ###, ####)
- Include code blocks with language specification
- Add proper links between related documents

### Content Guidelines
- Keep documentation up-to-date with code changes
- Include examples and usage instructions
- Document all configuration options
- Include troubleshooting sections
- Add contact information for support

### File Organization
- Use descriptive file names
- Group related documentation in subdirectories
- Keep main documentation in root docs/
- Use consistent naming conventions
- Include README.md in each subdirectory

## Integration with Workflows

### CI/CD Documentation Updates
```bash
# Update documentation after deployments
echo "## Deployment Summary - $(date)" >> docs/deployments/latest.md
echo "- Services updated" >> docs/deployments/latest.md
echo "- Documentation synchronized" >> docs/deployments/latest.md
```

### Feature Documentation
```bash
# Document new features
echo "## New Features - $(date)" >> docs/features/latest.md
echo "- CLI enhancements" >> docs/features/latest.md
echo "- Service improvements" >> docs/features/latest.md
```

## Recent Updates (v2.0)

### Documentation Structure Updates
- **Current Paths**: Updated to reflect `/opt/aitbc` structure
- **Service Ports**: Updated API endpoint documentation
- **CLI Integration**: Added CLI command documentation
- **Project Consolidation**: Documented new project structure

### Enhanced Workflow
- **Priority System**: Added priority-based documentation updates
- **Validation**: Added documentation validation steps
- **Standards**: Added documentation standards and guidelines
- **Integration**: Enhanced CI/CD integration

### New Documentation Categories
- **Summaries**: Added documentation summaries directory
- **Infrastructure**: Enhanced infrastructure documentation
- **Development**: Updated development guides
- **CLI Reference**: Added CLI command reference