# Auth Migration Split Plan: Agent A + Agent B Collaboration

## Overview

The JWT auth infrastructure is complete (Agent A). The router migration phase can be split between Agent A and Agent B for parallel execution.

## Work Split Strategy

### Agent A: High-Risk & Critical Routers

**Priority**: High (security-sensitive, financial, admin)

**Routers to migrate**:
1. Admin routes (`/routers/admin`, `/contexts/admin/*`)
2. Security routes (`/contexts/security/*`)
3. Payment routes (`/contexts/payments/*`)
4. Settlement routes (`/contexts/settlement/*`)
5. Staking routes (`/contexts/staking/*`)
6. Rewards routes (`/contexts/rewards/*`)

**Estimated effort**: 3-4 days

**Rationale**:
- Agent A has security context from previous auth work
- These routes require careful testing
- Financial routes need extra attention
- Admin routes are security-critical

### Agent B: Medium & Low-Risk Routers

**Priority**: Medium (client-facing, miner-facing, read-only)

**Routers to migrate**:
1. Health & docs (already public, just verify)
2. Client routes (`/routers/client`, `/contexts/certification/*`)
3. Miner routes (`/routers/miner`, `/contexts/marketplace/*`)
4. Agent coordination (`/contexts/agent_coordination/*`)
5. Agent identity (`/contexts/agent_identity/*`)
6. Hermes routes (`/contexts/hermes/*`)
7. Analytics routes (`/contexts/analytics/*`, `/contexts/ai_analytics/*`)
8. Monitoring routes (`/contexts/infrastructure/*`)
9. All other contexts (ecosystem, community, bounty, knowledge, etc.)

**Estimated effort**: 3-4 days

**Rationale**:
- These are less security-critical
- More volume of routers
- Good fit for Agent B's structural refactoring expertise
- Can be done in parallel with Agent A's work

## Coordination Points

### 1. Shared Resources

Both agents will use:
- JWT auth infrastructure (already complete)
- Security matrix (already complete)
- Migration guide (already complete)
- Example implementation (already complete)

### 2. Avoid Conflicts

- **No overlapping routers**: Clear split ensures no conflicts
- **Same import pattern**: Both use `from ..auth import ClientDep` etc.
- **Same dependency pattern**: Both use `user: ClientDep` etc.
- **Same error handling**: Both use JWT error responses

### 3. Testing Strategy

**Agent A**:
- Test high-risk routers thoroughly
- Focus on security edge cases
- Test financial transaction flows
- Verify admin role enforcement

**Agent B**:
- Test medium/low-risk routers
- Focus on functional correctness
- Test client/miner workflows
- Verify role-based access

### 4. Integration Testing

After both complete:
1. Run full test suite
2. Test cross-context workflows
3. Verify security matrix enforcement
4. Load test with JWT auth
5. Monitor auth failure rates

## Timeline

**Week 1**: Coordination & setup
- Day 1: Review split plan, confirm approach
- Day 2: Both agents start on their assigned routers
- Day 3-5: Parallel migration work

**Week 2**: Completion & integration
- Day 1-2: Complete remaining routers
- Day 3: Integration testing
- Day 4: Fix issues found in testing
- Day 5: Final verification

## Communication

### Daily Sync

Each day, both agents should:
1. Report progress (routers migrated)
2. Report any issues/blockers
3. Share learnings/observations
4. Update shared documentation

### Issue Resolution

If issues arise:
1. Document in shared issue tracker
2. Discuss in daily sync
3. Escalate if needed
4. Update migration guide with lessons learned

## Success Criteria

### Agent A Success Criteria
- ✅ All high-risk routers migrated
- ✅ Security tests pass
- ✅ Financial flows verified
- ✅ Admin role enforcement verified
- ✅ No regressions in critical paths

**Completed Routers**:
- ✅ `/routers/admin` - 5 endpoints migrated
- ✅ `/contexts/security/routers/security_router.py` - 16 endpoints migrated
- ✅ `/contexts/payments/routers/payments.py` - 7 endpoints migrated
- ✅ `/contexts/settlement/routers/settlement.py` - 4 endpoints migrated
- ✅ `/contexts/staking/routers/staking.py` - No auth deps (verified)
- ✅ `/contexts/rewards/routers/rewards.py` - No auth deps (verified)

**Total**: 32 endpoints migrated to JWT auth

### Agent B Success Criteria
- ✅ All medium/low-risk routers migrated
- ✅ Functional tests pass
- ✅ Client/miner workflows verified
- ✅ Role-based access verified
- ✅ No regressions in user-facing paths

### Joint Success Criteria
- ✅ All routers migrated to JWT auth
- ✅ Full test suite passes
- ✅ No API key auth remaining (or deprecated)
- ✅ Documentation updated
- ✅ Zero production incidents

## Rollback Plan

If issues arise during migration:

**Individual Rollback**:
- Each agent can rollback their specific routers
- Revert to API key auth for affected routers
- Document issues for future reference

**Full Rollback**:
- Disable JWT middleware
- Revert all router changes
- Keep JWT infrastructure for future use
- Document what went wrong

## Documentation Updates

Both agents should:
1. Update migration guide with their learnings
2. Document any edge cases encountered
3. Share best practices discovered
4. Update security matrix if needed

## Next Steps

1. **Agent A**: Review this split plan, confirm acceptance
2. **Agent B**: Review this split plan, confirm acceptance
3. **Both**: Start migration on assigned routers
4. **Daily**: Sync progress and issues
5. **Weekly**: Integration testing and verification

## Questions?

If questions arise during migration:
1. Review this split plan
2. Check migration guide
3. Consult with the other agent
4. Open a discussion issue
