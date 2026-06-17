# Voting Mechanisms - v0.4.12

**Release**: v0.4.12
**Date**: June 7, 2026
**Status**: ✅ Implementation Complete

## Overview

AITBC v0.4.12 introduces multiple voting mechanisms for governance, including token-weighted voting, quadratic voting, and delegated voting.

## Token-Weighted Voting

### CLI Command

```bash
aitbc governance vote --proposal-id prop_... --vote yes
```

### Voting Power Calculation

```
voting_power = token_balance + staked_tokens * 2
```

### Features
- **Simple**: Direct correlation between tokens and voting power
- **Transparent**: Easy to understand voting power
- **Standard**: Common governance mechanism

## Quadratic Voting

### CLI Command

```bash
aitbc governance vote --proposal-id prop_... --vote yes --quadratic --credits 100
```

### Quadratic Voting Formula

```
vote_cost = vote_count^2
total_credits = sqrt(token_balance)
```

### Features
- **Prevents concentration**: Reduces influence of large token holders
- **Encourages participation**: Incentivizes broader participation
- **Complex**: More complex voting mechanism

## Delegated Voting

### Delegate Voting Power

```bash
# Delegate voting power
aitbc governance delegate --to 0x... --amount 1000
```

### Vote on Behalf of Delegators

```bash
# Vote on behalf of delegators
aitbc governance vote --proposal-id prop_... --vote yes --as-delegate
```

### Features
- **Proxy voting**: Delegate voting power to trusted addresses
- **Expertise**: Delegate to experts in specific areas
- **Flexibility**: Can revoke delegation at any time

## CLI Commands

### Voting

```bash
# Vote on proposal
aitbc governance vote --proposal-id prop_abc123 --vote yes

# Delegate voting power
aitbc governance delegate --to 0x... --amount 1000

# View voting power
aitbc governance voting-power
```

---

*Last Updated: 2026-06-07*
