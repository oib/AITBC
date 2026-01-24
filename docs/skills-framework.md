# Cascade Skills Framework

## Overview

The Cascade Skills Framework provides a powerful way to automate complex, multi-step workflows in the AITBC project. Skills bundle together scripts, templates, documentation, and procedures that Cascade can intelligently invoke to execute tasks consistently.

## Skills Directory Structure

```
.windsurf/skills/
├── deploy-production/          # Production deployment workflow
│   ├── SKILL.md               # Skill definition and documentation
│   ├── pre-deploy-checks.sh   # Pre-deployment validation script
│   ├── environment-template.env # Production environment template
│   ├── rollback-steps.md      # Emergency rollback procedures
│   └── health-check.py        # Post-deployment health verification
│
└── blockchain-operations/      # Blockchain node management
    ├── SKILL.md               # Skill definition and documentation
    ├── node-health.sh         # Node health monitoring script
    ├── tx-tracer.py          # Transaction debugging tool
    ├── mining-optimize.sh    # GPU mining optimization script
    ├── sync-monitor.py       # Real-time sync monitoring
    └── network-diag.py       # Network diagnostics tool
```

## Using Skills

### Automatic Invocation
Skills are automatically invoked when Cascade detects relevant keywords or context:
- "deploy production" → triggers deploy-production skill
- "check node status" → triggers blockchain-operations skill
- "debug transaction" → triggers blockchain-operations skill
- "optimize mining" → triggers blockchain-operations skill

### Manual Invocation
You can manually invoke skills by mentioning them directly:
- "Use the deploy-production skill"
- "Run blockchain-operations skill"

## Creating New Skills

1. Create a new directory under `.windsurf/skills/<skill-name>/`
2. Add a `SKILL.md` file with YAML frontmatter:
   ```yaml
   ---
   name: skill-name
   description: Brief description of the skill
   version: 1.0.0
   author: Cascade
   tags: [tag1, tag2, tag3]
   ---
   ```
3. Add supporting files (scripts, templates, documentation)
4. Test the skill functionality
5. Commit to repository

## Skill Components

### Required
- **SKILL.md** - Main skill definition with frontmatter

### Optional (but recommended)
- Shell scripts for automation
- Python scripts for complex operations
- Configuration templates
- Documentation files
- Test scripts

## Best Practices

1. **Keep skills focused** on a specific domain or workflow
2. **Include comprehensive documentation** in SKILL.md
3. **Add error handling** to all scripts
4. **Use logging** for debugging and audit trails
5. **Include rollback procedures** for destructive operations
6. **Test thoroughly** before deploying
7. **Version your skills** using semantic versioning

## Example Skill: Deploy-Production

The deploy-production skill demonstrates best practices:
- Comprehensive pre-deployment checks
- Environment configuration template
- Detailed rollback procedures
- Post-deployment health verification
- Clear documentation and usage examples

## Integration with AITBC

Skills integrate seamlessly with AITBC components:
- Coordinator API interactions
- Blockchain node management
- Mining operations
- Exchange and marketplace functions
- Wallet daemon operations

## Recent Success Stories

### Ollama GPU Inference Testing (2026-01-24)
Using the blockchain-operations skill with Ollama testing enhancements:
- Executed end-to-end GPU inference workflow testing
- Fixed coordinator API bug (missing _coerce_float function)
- Verified complete job lifecycle from submission to receipt generation
- Documented comprehensive testing scenarios and automation scripts
- Achieved successful job completion with proper payment calculations

### Service Maintenance (2026-01-21)
Using the blockchain-operations skill framework:
- Successfully diagnosed and fixed all failing AITBC services
- Resolved duplicate service conflicts
- Implemented SSH access for automated management
- Restored full functionality to 7 core services

### Production Deployment (2025-01-19)
Using the deploy-production skill:
- Automated deployment validation
- Environment configuration management
- Health check automation
- Rollback procedure documentation

## Future Enhancements

- Skill marketplace for sharing community skills
- Skill dependencies and composition
- Skill versioning and updates
- Skill testing framework
- Skill analytics and usage tracking
