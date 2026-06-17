# Governance Token System - v0.4.12

**Release**: v0.4.12
**Date**: June 7, 2026
**Status**: ✅ Implementation Complete

## Overview

AITBC v0.4.12 introduces a comprehensive governance token system, including token distribution, staking, rewards, and delegation mechanisms.

## Token Distribution

### Service Providers
- Earn tokens for completing jobs
- Proportional to job value
- Reputation bonuses

### Service Consumers
- Earn tokens for marketplace activity
- Usage-based rewards
- Review bonuses

### Liquidity Providers
- Earn tokens for providing liquidity
- Proportional to liquidity provided
- Duration bonuses

### Governance Participants
- Earn tokens for voting participation
- Proposal creation rewards
- Delegation rewards

### Protocol Contributors
- Earn tokens for code contributions
- Pull request rewards
- Bug bounty rewards

## Token Staking

### Stake Tokens

```bash
# Stake tokens for enhanced voting power
aitbc governance stake --amount 1000 --lock-period 30d
```

### Unstake Tokens

```bash
# Unstake tokens
aitbc governance unstake --amount 1000
```

### Staking Benefits
- **2x voting power**: Staked tokens provide 2x voting power
- **Governance token rewards**: Earn rewards for staking
- **Fee share**: Share of marketplace fees
- **Lock period**: Minimum 30-day lock period

## Token Rewards

### Claim Rewards

```bash
# Claim rewards
aitbc governance rewards claim
```

### View Rewards

```bash
# View rewards
aitbc governance rewards view
```

## CLI Commands

### Token Management

```bash
# Stake tokens
aitbc governance stake --amount 1000 --lock-period 30d

# Unstake tokens
aitbc governance unstake --amount 1000

# Claim rewards
aitbc governance rewards claim

# View balance
aitbc governance balance
```

---

*Last Updated: 2026-06-07*
