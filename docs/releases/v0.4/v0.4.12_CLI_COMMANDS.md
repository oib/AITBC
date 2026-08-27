# CLI Commands - v0.4.12

**Release**: v0.4.12
**Date**: June 7, 2026
**Status**: ✅ Implementation Complete

## Overview

AITBC v0.4.12 introduces comprehensive CLI commands for governance operations, including proposal management, voting, token management, and delegation.

## Proposal Management

### Create Proposal

```bash
aitbc governance propose --type marketplace_rule --title "Adjust escrow fee" --description "Reduce escrow fee from 1% to 0.5%" --value 0.005
```

### List Proposals

```bash
aitbc governance list --status active
```

### Get Proposal Details

```bash
aitbc governance get prop_abc123
```

### Execute Passed Proposal

```bash
aitbc governance execute prop_abc123
```

## Voting

### Vote on Proposal

```bash
aitbc governance vote --proposal-id prop_abc123 --vote yes
```

### Delegate Voting Power

```bash
aitbc governance delegate --to 0x... --amount 1000
```

### View Voting Power

```bash
aitbc governance voting-power
```

## Token Management

### Stake Tokens

```bash
aitbc governance stake --amount 1000 --lock-period 30d
```

### Unstake Tokens

```bash
aitbc governance unstake --amount 1000
```

### Claim Rewards

```bash
aitbc governance rewards claim
```

### View Balance

```bash
aitbc governance balance
```

## New Commands in v0.4.12

- `aitbc governance stake` - Stake tokens for enhanced voting power
- `aitbc governance delegate` - Delegate voting power to another address
- `aitbc governance execute` - Execute a passed proposal
- `aitbc governance voting-power` - Get voting power for an address

---

*Last Updated: 2026-06-07*
