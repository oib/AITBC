# Certification Context

**Description:** Agent certification, badges, and partnership management

## Structure

| Component | Path |
|---|---|
| `domain` | `domain/` |
| `routers` | `routers/` |
| `services` | `services/` |
| `storage` | `storage/` |

## Domain Dependencies

| Domain Module | Imported Symbols |
|---|---|
| `app/domain/certification.py` | `AchievementBadge`, `AgentBadge`, `BadgeType`, `AgentCertification` |
| `app/domain/reputation.py` | `AgentReputation` |

> **Note:** These imports cross the context boundary into the shared `app/domain/` layer. See [P2 audit](../../docs/releases/v0.5.12/p2_cross_context_import_audit.md) for details.
