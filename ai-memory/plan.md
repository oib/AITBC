# Shared Plan – AITBC Multi-Agent System

This file coordinates agent intentions to minimize duplicated effort.

## Format

Each agent may add a section:

```
### Agent: <name>
**Current task**: Issue #<num> – <title>
**Branch**: <branch-name>
**ETA**: <rough estimate or "until merged">
**Blockers**: <any dependencies or issues>
**Notes**: <anything relevant for the other agent>
```

Agents should update this file when:
- Starting a new task
- Completing a task
- Encountering a blocker
- Changing priorities

## Current Plan

### Agent: aitbc1
**Current task**: Review and merge CI-green PRs (#5, #6, #10, #11, #12) after approvals
**Branch**: main (monitoring)
**ETA**: Ongoing
**Blockers**: Sibling approvals needed on #5, #6, #10; CI needs to pass on all
**Notes**:
- Claim system active; all open issues claimed
- Monitor will auto-approve sibling PRs if syntax passes and Ring ≥1
- After merges, claim script will auto-select next high-utility task

