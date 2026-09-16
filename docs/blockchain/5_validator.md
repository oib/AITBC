# Validator Operations

**Last Updated:** 2026-09-16

Guide for running a validator node in the network.

> There is no `aitbc-chain validator` binary and no self-serve registration
> command. Validator membership is **operator-controlled** through the node
> configuration, and inspected through `aitbc blockchain consensus`.

## Becoming a Validator

### Requirements

| Requirement | Value |
|-------------|-------|
| Membership | Address listed in `VALIDATOR_SET` on every node |
| Signing key | Address → private-key entry in local `VALIDATOR_KEYS` |
| Node uptime | 24/7 operation expected |
| Software | Same `/opt/aitbc` revision as the rest of the fleet |

### Configuration

Validator set membership is configured, not registered on-chain. On every
node in the fleet (`/etc/aitbc/blockchain.env` or `node.env`):

```bash
MULTI_VALIDATOR_CONSENSUS_ENABLED=true
# JSON list — identical on all nodes
VALIDATOR_SET='[{"address":"0xaaa...","stake":"1000"},
                {"address":"0xbbb...","stake":"1000"}]'
MULTI_VALIDATOR_MIN_ATTESTATIONS=2
```

On the validator node itself, the signing key lives in
`/etc/aitbc/validator-secrets.env` (loaded only by the blockchain units):

```bash
# JSON mapping of validator address -> private key this node controls
VALIDATOR_KEYS='{"0xaaa...":"<private key>"}'
# Single-proposer mode also uses PROPOSER_KEY / keystore/proposer.json
```

Keep `VALIDATOR_KEYS` out of the repository and out of shared env files — it
holds raw private keys. Restart the node to pick up changes:

```bash
systemctl restart aitbc-blockchain-node
journalctl -u aitbc-blockchain-node -f
```

## Validator Duties

### Block Production

Validators take turns producing blocks under `MultiValidatorPoA`:

- Round-robin proposer selection over the active validator set, rotating on
  `consensus_validator_set_epoch_blocks` (default 7200) epoch boundaries
- `block_time_seconds` block interval (default 10s)
- If the scheduled proposer misses its slot, the round derived from the
  parent block's timestamp advances and the next validator takes over
  (`consensus_proposer_round_seconds`, default 60)
- Blocks carry the proposer's signature plus at least
  `multi_validator_min_attestations` (default 2) validator attestations

### Transaction Validation

- Verify transaction signatures
- Check sender balance and nonce
- Validate state-transition and smart contract execution

### Network Participation

- Maintain the gossip mesh (`gossip_mesh_peer_urls`, validator-only)
- Attest to proposals within `multi_validator_attestation_timeout_seconds`
- Participate in PBFT phases when `pbft_consensus_enabled` (off on the live fleet)

## Validator Monitoring

```bash
# Consensus mode, epoch, view, active/total validators
aitbc blockchain consensus status --chain-id ait-hub.aitbc.bubuit.net

# Validator set: address, stake weight, reputation, role, last proposed
aitbc blockchain consensus validators --chain-id ait-hub.aitbc.bubuit.net

# Detected slashing events (condition, rate, amount, height)
aitbc blockchain consensus slashing-history --chain-id ait-hub.aitbc.bubuit.net
```

Add `--node-url http://<host>:8202` to query a remote node, or hit the backing
RPC endpoints directly: `GET /rpc/consensus/status`, `/rpc/consensus/validators`,
`/rpc/consensus/slashing-history`.

## Rewards and Slashing — Not Token Economics

No block-reward or token-slashing economics are wired into block production.
Do not plan operations around proposer rewards, uptime multipliers, or
stake-percentage penalties — none of them move account balances.

What does exist inside the MV-PoA engine:

- **Consensus bookkeeping only.** `SlashingManager` records `SlashingEvent`s
  (double-sign, unavailability, invalid block, slow response) with a *rate*
  applied to the validator's `validator_set` stake weight — an internal score,
  not a wallet balance. `consensus_slashing_enabled` (default true) and
  `consensus_byzantine_threshold` (default 3 strikes before deactivation)
  govern detection and demotion to standby.
- **Attestation gating.** Blocks produced without enough validator
  attestations are rejected during sync — that is the enforcement, not a
  balance deduction.
- **Inspection.** `aitbc blockchain consensus slashing-history` shows detected
  events; `Amount Slashed` reads "not levied" when an event was detected but
  never applied to the consensus record.

## Next

- [Node Quick Start](../getting-started/node-quickstart.md) — Get started
- [Consensus](./4_consensus.md) — Consensus mechanism
- [Monitoring](./7_monitoring.md) — Monitoring
