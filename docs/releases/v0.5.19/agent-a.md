# v0.5.19 Tech Debt Cleanup — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Create a ReputationDTO that can be used across contexts without direct model import.

**Working directory**: `/opt/aitbc/aitbc/` or `packages/aitbc-shared/`

**Prerequisite**: v0.5.18 ✅.

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `ReputationDTO` dataclass — fields needed by certification context (agent_id, reputation_score, total_tasks, success_rate, etc.) | Medium | `packages/aitbc-shared/aitbc_shared/models/reputation.py` (new or extend) | ✅ complete |
| A2 | Unit tests for ReputationDTO | Low | `tests/unit/test_reputation_dto.py` (new) | ✅ complete |

---

## A1: ReputationDTO

Create a DTO that certification context can use instead of directly importing `AgentReputation`:

```python
@dataclass
class ReputationDTO:
    """DTO for cross-context reputation data access."""
    agent_id: str
    reputation_score: float
    total_tasks: int
    success_rate: float
    # Add fields as needed by certification context
```

Place in `packages/aitbc-shared/aitbc_shared/models/reputation.py` or a new shared location.

---

## A2: Unit tests for ReputationDTO

Create `tests/unit/test_reputation_dto.py` with tests for:
- ReputationDTO serialization
- Field validation
- Conversion from AgentReputation model

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.19 — Tech Debt Cleanup
**Agent**: Agent A (Shared Core)
