# Multi-Validator PoA Soak

**Level**: Advanced
**Prerequisites**: [Scenario 15 Blockchain Monitoring](./15_blockchain_monitoring.md), [Scenario 17 Governance Voting](./17_governance_voting.md)
**Estimated Time**: 30 minutes
**Last Updated**: 2026-08-23
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Multi-Validator PoA Soak

---

## See Also

- **Previous Scenario**: [Scenario 49 Auto Reinvest Escrow](./49_auto_reinvest_escrow.md)
- **Feature Documentation**: [Multi-Validator PoA source](../../apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py)
- **Closed cycle**: [DESIGN_CYCLE.md](../DESIGN_CYCLE.md) P1.4

---

## Scenario Overview

This scenario runs a local, short-duration soak of the `MultiValidatorPoA` consensus path before it is enabled in production. It verifies that multiple validators can rotate proposers, produce signed blocks, and survive a temporary partition, while confirming the single-proposer fallback still works when `MULTI_VALIDATOR_CONSENSUS_ENABLED=false`.

> **Operator play:** This scenario is an operator-driven validation of a consensus upgrade. It must pass on a test/staging node before `MULTI_VALIDATOR_CONSENSUS_ENABLED` is flipped in `/etc/aitbc/blockchain.env` on the live hub or shop.

### Use Case

The live network currently runs single-proposer PoA (`PROPOSER_ID` from `blockchain.env`). Enabling `MultiValidatorPoA` requires a configured validator set, per-validator signing keys, and a successful soak. This play exercises the code without changing the live default.

### What You'll Learn

- How to configure `VALIDATOR_SET` and validator signing keys for a local node
- How to enable `MULTI_VALIDATOR_CONSENSUS_ENABLED` for a local soak
- How to submit transactions and observe proposer rotation
- How to run the included soak tests and read the proposer-switch metric
- Why the live `blockchain.env` still disables multi-validator consensus by default

---

## Prerequisites

### Knowledge Required

- Single-proposer PoA vs. round-robin multi-validator consensus
- How `blockchain.env` overrides `config.py` defaults

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- `pytest` and the blockchain-node test dependencies

### Setup Required

- A local or staging blockchain-node checkout, not the live hub/shop
- Three local wallets/keys to act as validators (do not use live wallets)

---

## Step-by-Step Workflow

### Step 1: Configure a local validator set

Create or edit a local environment file (do not edit `/etc/aitbc/blockchain.env` on the live nodes):

```bash
# /tmp/multi-validator-soak.env
MULTI_VALIDATOR_CONSENSUS_ENABLED=true
VALIDATOR_SET='[{"address":"0xvalidator1...","stake":"1000"},{"address":"0xvalidator2...","stake":"1000"},{"address":"0xvalidator3...","stake":"1000"}]'
VALIDATOR_KEYS='{"0xvalidator1...":"0xkey1...","0xvalidator2...":"0xkey2...","0xvalidator3...":"0xkey3..."}'
PROPOSER_KEY=0xkey1...
```

Generate wallets with `aitbc wallet create --name mv-soak-1` if you need fresh addresses. Use the private keys from the wallet backups.

### Step 2: Run the unit and soak tests

From the repo root:

```bash
cd /opt/aitbc
PYTHONPATH=/opt/aitbc/apps/blockchain-node/src:/opt/aitbc/packages/py \
  python3 -m pytest apps/blockchain-node/tests/consensus/test_multi_validator_poa.py \
                   apps/blockchain-node/tests/consensus/test_multi_validator_poa_soak.py \
                   apps/blockchain-node/tests/consensus/test_pbft.py \
                   apps/blockchain-node/tests/consensus/test_rotation.py \
                   -q --override-ini="addopts="
```

**Expected output:** all tests pass. The soak test runs 1000 rounds of proposer selection with partition simulation.

### Step 3: Start a local node with multi-validator enabled

```bash
cd /opt/aitbc
source /tmp/multi-validator-soak.env
python3 -m aitbc_chain.main
```

Watch `journalctl` or the node log for messages like:

```text
[PROPOSE] Selected proposer 0xvalidator2... for height 42
[PROPOSE] Selected proposer 0xvalidator3... for height 43
```

### Step 4: Submit a test job and observe rotation

In another terminal, with the local node API on `http://localhost:8202`:

```bash
aitbc wallet create --name soak-wallet
aitbc wallet fund --name soak-wallet --amount 1000
aitbc ai submit --prompt "multi-validator soak" --wallet soak-wallet --payment 1
```

Query block status and check the proposer changes across heights:

```bash
aitbc blockchain status
aitbc monitor metrics
```

Look for `poa_proposer_switches_total` increasing and `poa_blocks_proposed_total_*` split across validators.

### Step 5: Confirm single-proposer fallback when disabled

Stop the node, unset the flag, and restart:

```bash
MULTI_VALIDATOR_CONSENSUS_ENABLED=false python3 -m aitbc_chain.main
```

Blocks should resume with the configured `PROPOSER_ID` and the same chain state.

---

## Validation

- Unit and soak tests pass: `50 passed` in `apps/blockchain-node/tests/consensus`.
- Local block production shows at least two distinct proposers over 50 blocks.
- `poa_proposer_switches_total` > 0 in the metrics endpoint (`http://localhost:9009/metrics`).
- Reverting `MULTI_VALIDATOR_CONSENSUS_ENABLED=false` returns the node to single-proposer without corrupting the chain.

---

## Cleanup

- Stop the local node.
- Remove `/tmp/multi-validator-soak.env`.
- Do not commit local wallet backups.

---

## Important: live enablement

The live `/etc/aitbc/blockchain.env` on `aitbc3` and `hub.aitbc` contains:

```text
MULTI_VALIDATOR_CONSENSUS_ENABLED=false
```

Do **not** change this on the live nodes until:

1. This scenario (or equivalent staging soak) passes on identical hardware and network conditions.
2. A `VALIDATOR_SET` and `VALIDATOR_KEYS` mapping are generated for the live validator set.
3. All validators are reachable over the P2P/gossip backend.
4. The operator has a rollback plan to set `MULTI_VALIDATOR_CONSENSUS_ENABLED=false` and restart.

After live enablement, `PoAProposer` will stop using the single `PROPOSER_ID` and rotate through the configured validator set.
