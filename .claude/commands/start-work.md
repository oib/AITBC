---
description: Start work on a new Linear ticket with proper workflow
argument-hint: [AITBC-number]
allowed-tools: [Read, Write, Edit, Bash, Grep, Glob, mcp__linear-mcp__*]
---

You are starting work on a new Linear ticket.

**Workflow Authority**: This harness command provides execution steps. CONTRIBUTING.md is the northstar for conventions (branch naming, commit format, SAFe patterns). Follow both:

## Pre-Flight Checklist

1. **Linear Ticket Exists?**
   - If no ticket number provided in arguments, ask user for Linear ticket number
   - Verify ticket exists in Linear using `mcp__linear-mcp__get_issue`
   - Confirm ticket is in appropriate status (Todo, In Progress)

2. **Stop-the-Line: AC/DoD Check** (MANDATORY)
   - Verify ticket has **Acceptance Criteria** or **Definition of Done**
   - If AC/DoD is missing or unclear:
     - **STOP** - Do not proceed with implementation
     - Route back to BSA/POPM to define AC/DoD
     - Dev agents are NOT responsible for inventing AC/DoD
   - Work begins ONLY when AC/DoD exists

3. **Branch Naming**
   - Format: `AITBC-{number}-{short-description}`
   - Must start with AITBC- and ticket number
   - Use lowercase with hyphens

4. **Start from Latest main**
   - Ensure starting from clean main branch: `git checkout main && git pull origin main`
   - Verify no uncommitted changes

5. **Create Feature Branch**
   - Create branch: `git checkout -b AITBC-{number}-{description}`
   - Confirm branch created successfully
   - If the feature branch already exists, update it before continuing: `git fetch origin && git rebase origin/main` (resolve conflicts before working)

## Workflow

If argument provided ($1):

- Use as ticket number (e.g., `/start-work 347` → AITBC-347)
- Fetch ticket details from Linear
- Suggest branch name based on ticket title
- Execute checkout workflow

If no argument:

- Ask user for Linear ticket number
- Proceed with workflow

## Success Criteria

- ✅ Linear ticket verified
- ✅ AC/DoD confirmed (Stop-the-Line gate passed)
- ✅ On latest main branch
- ✅ Feature branch created with correct naming
- ✅ Ready to begin work

Report status and any blockers. If AC/DoD is missing, report blocker and route to BSA.
