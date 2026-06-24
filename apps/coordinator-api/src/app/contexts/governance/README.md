# Governance Context

**Description:** DAO governance, proposals, voting, and treasury

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
| `app/domain/governance.py` | `GovernanceProfile`, `Proposal`, `Vote`, `VoteType` |
| `app/domain/dao_governance.py` | `DAOMember`, `DAOProposal`, `ProposalState`, `ProposalType` |

> **Note:** These imports cross the context boundary into the shared `app/domain/` layer. See [P2 audit](../../docs/releases/v0.5.12/p2_cross_context_import_audit.md) for details.
