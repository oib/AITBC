# Validator Operations
Guide for running a validator node in the AITBC network.

## Becoming a Validator

### Requirements

| Requirement | Value |
|-------------|-------|
| Stake | 1000 AITBC |
| Node uptime | 99%+ |
| Technical capability | Must run node 24/7 |
| Geographic distribution | One per region preferred |

### Registration

```bash
aitbc-chain validator register --stake 1000
```

### Activate Validator Status

```bash
aitbc-chain validator activate
```

## Validator Duties

### Block Production

Validators take turns producing blocks:
- Round-robin selection
- Fixed 2-second block time
- Missed blocks result in reduced rewards

### Transaction Validation

- Verify transaction signatures
- Check sender balance
- Validate smart contract execution

### Network Participation

- Maintain P2P connections
- Propagate blocks to peers
- Participate in consensus votes

## Validator Rewards

### Block Rewards

| Block Position | Reward |
|----------------|--------|
| Proposer | 1 AITBC |
| Validator (any) | 0.1 AITBC |

### Performance Bonuses

- 100% uptime: 1.5x multiplier
- 99-100% uptime: 1.2x multiplier
- <99% uptime: 1.0x multiplier

## Validator Monitoring

```bash
# Check validator status
aitbc-chain validator status

# View performance metrics
aitbc-chain validator metrics

# Check missed blocks
aitbc-chain validator missed-blocks
```

## Validator Slashing

### Slashing Conditions

| Violation | Penalty |
|-----------|---------|
| Double signing | 5% stake |
| Extended downtime | 1% stake |
| Invalid block | 2% stake |

### Recovery

- Partial slashing can be recovered
- Full slashing requires re-registration

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [Consensus](./4_consensus.md) — Consensus mechanism
- [Monitoring](./7_monitoring.md) — Monitoring
