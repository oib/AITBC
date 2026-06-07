# CLI Commands

## Overview

The AITBC CLI provides a `governance` command group for interacting with the governance system. Commands support staking, delegation, voting, and proposal execution.

## Command Group

```bash
aitbc governance --help
```

## Commands

### stake

Stake tokens for enhanced voting power.

```bash
aitbc governance stake --address <address> --amount <amount> --lock-days <days>
```

**Options:**
- `--address` (required): Staker wallet address
- `--amount` (required): Amount of tokens to stake
- `--lock-days` (optional): Lock period in days (default: 30, minimum: 30)
- `--format` (optional): Output format (table/json, default: table)

**Example:**
```bash
aitbc governance stake --address 0x1234567890abcdef --amount 1000 --lock-days 30
```

**Response:**
```json
{
  "stake_id": "uuid",
  "staker_address": "0x1234567890abcdef",
  "amount_staked": 1000,
  "lock_period_days": 30,
  "unstakes_at": "2026-07-07T00:00:00Z",
  "voting_power": 2000
}
```

**Error:**
- Lock period must be at least 30 days

### delegate

Delegate voting power to another address.

```bash
aitbc governance delegate --delegator <address> --delegate <address> --amount <amount>
```

**Options:**
- `--delegator` (required): Delegator wallet address
- `--delegate` (required): Delegate wallet address
- `--amount` (required): Amount of voting power to delegate
- `--format` (optional): Output format (table/json, default: table)

**Example:**
```bash
aitbc governance delegate --delegator 0x1234567890abcdef --delegate 0x0987654321fedcba --amount 500
```

**Response:**
```json
{
  "delegation_id": "uuid",
  "delegator_address": "0x1234567890abcdef",
  "delegate_address": "0x0987654321fedcba",
  "voting_power": 500,
  "created_at": "2026-06-07T00:00:00Z"
}
```

**Error:**
- Insufficient voting power

### execute

Execute a passed proposal.

```bash
aitbc governance execute <proposal_id>
```

**Arguments:**
- `proposal_id`: Proposal ID to execute

**Options:**
- `--format` (optional): Output format (table/json, default: table)

**Example:**
```bash
aitbc governance execute prop_123
```

**Response:**
```json
{
  "proposal_id": "prop_123",
  "status": "executed",
  "executed_at": "2026-06-15T00:00:00Z"
}
```

**Errors:**
- Proposal not found (404)
- Proposal not in succeeded state (400)

### voting-power

Get voting power for an address.

```bash
aitbc governance voting-power <address>
```

**Arguments:**
- `address`: Wallet address to query

**Options:**
- `--format` (optional): Output format (table/json, default: table)

**Example:**
```bash
aitbc governance voting-power 0x1234567890abcdef
```

**Response:**
```json
{
  "address": "0x1234567890abcdef",
  "voting_power": 2000,
  "calculated_at": 1717756800
}
```

### vote

Vote on a governance proposal.

```bash
aitbc governance vote <proposal_id> --vote <option> --wallet <wallet>
```

**Arguments:**
- `proposal_id`: Proposal ID to vote on

**Options:**
- `--vote` (required): Vote option (for, against, abstain)
- `--wallet` (required): Wallet name for signing
- `--voting-power` (optional): Voting power to use (default: 0)
- `--reason` (optional): Vote reason
- `--format` (optional): Output format (table/json, default: table)

**Example:**
```bash
aitbc governance vote prop_123 --vote for --wallet mywallet --reason "Support this proposal"
```

**Response:**
```json
{
  "vote_id": "uuid",
  "proposal_id": "prop_123",
  "voter_address": "0x1234567890abcdef",
  "vote_type": "for",
  "voting_power": 1000,
  "reason": "Support this proposal",
  "chain_id": "ait-hub.aitbc.bubuit.net"
}
```

### proposal

Create a governance proposal.

```bash
aitbc governance proposal --proposal-id <id> --title <title> --description <desc> --wallet <wallet>
```

**Options:**
- `--proposal-id` (required): Unique proposal ID
- `--title` (required): Proposal title
- `--description` (required): Proposal description
- `--category` (optional): Proposal category (default: general)
- `--wallet` (required): Wallet name for signing
- `--voting-days` (optional): Voting period in days (default: 7)
- `--format` (optional): Output format (table/json, default: table)

**Example:**
```bash
aitbc governance proposal --proposal-id prop_123 --title "Test Proposal" --description "Test description" --wallet mywallet --voting-days 7
```

**Response:**
```json
{
  "proposal_id": "prop_123",
  "proposer_address": "0x1234567890abcdef",
  "title": "Test Proposal",
  "description": "Test description",
  "category": "general",
  "voting_starts": "2026-06-07T00:00:00Z",
  "voting_ends": "2026-06-14T00:00:00Z",
  "chain_id": "ait-hub.aitbc.bubuit.net"
}
```

### get-proposal

Get a governance proposal from blockchain.

```bash
aitbc governance get-proposal <proposal_id>
```

**Arguments:**
- `proposal_id`: Proposal ID to query

**Options:**
- `--format` (optional): Output format (table/json, default: table)

**Example:**
```bash
aitbc governance get-proposal prop_123
```

**Response:**
```json
{
  "proposal_id": "prop_123",
  "proposer_address": "0x1234567890abcdef",
  "title": "Test Proposal",
  "description": "Test description",
  "status": "active",
  "voting_starts": "2026-06-07T00:00:00Z",
  "voting_ends": "2026-06-14T00:00:00Z"
}
```

## Configuration

The CLI uses the following configuration from `~/.aitbc/config.toml`:

```toml
[governance]
service_url = "http://localhost:8105"
```

## Wallet Integration

Commands that require signing use the AITBC wallet system:

```bash
# List available wallets
aitbc wallet list

# Create a new wallet
aitbc wallet create mywallet

# Get wallet address
aitbc wallet show mywallet
```

## Output Formats

### Table (Default)
Human-readable table output.

```bash
aitbc governance voting-power 0x123... --format table
```

### JSON
Machine-readable JSON output.

```bash
aitbc governance voting-power 0x123... --format json
```

## Error Handling

Common errors:
- **Network Error:** Cannot connect to governance service
- **Invalid Address:** Invalid wallet address format
- **Insufficient Balance:** Not enough tokens for operation
- **Proposal Not Found:** Proposal ID does not exist
- **Already Voted:** Address has already voted on proposal

## Examples

### Complete Staking Workflow

```bash
# Check current voting power
aitbc governance voting-power 0x1234567890abcdef

# Stake tokens
aitbc governance stake --address 0x1234567890abcdef --amount 1000 --lock-days 30

# Verify increased voting power
aitbc governance voting-power 0x1234567890abcdef
```

### Complete Proposal Workflow

```bash
# Create proposal
aitbc governance proposal --proposal-id prop_123 --title "Test" --description "Test" --wallet mywallet

# Vote on proposal
aitbc governance vote prop_123 --vote for --wallet mywallet

# Check proposal status
aitbc governance get-proposal prop_123

# Execute proposal (after voting ends)
aitbc governance execute prop_123
```

### Delegation Workflow

```bash
# Delegate voting power
aitbc governance delegate --delegator 0x123... --delegate 0x456... --amount 500

# Check delegate's voting power
aitbc governance voting-power 0x456...
```

## Help

Get help for any command:

```bash
aitbc governance --help
aitbc governance stake --help
aitbc governance vote --help
```
