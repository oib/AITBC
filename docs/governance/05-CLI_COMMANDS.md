# CLI Commands

## Overview

The AITBC CLI provides a `governance` command group for interacting with the governance service (port 8105). Commands cover creating, voting on, closing, and executing proposals, plus service status and cross-chain propagation. Token staking lives under `aitbc wallet stake`, not in this group.

## Command Group

```bash
aitbc governance --help
```

## Commands

### propose

Create a governance proposal. The service assigns the proposal ID (`prop_<hex8>`); the caller does not choose it.

```bash
aitbc governance propose --title <title> --description <desc> --proposer-id <id>
```

**Options:**

- `--title` (required): Proposal title
- `--description` (required): Proposal description
- `--proposer-id` (required): Proposer profile ID
- `--type` (optional): Proposal type (default: parameter_change)
- `--category` (optional): Proposal category (default: general)
- `--proposer-address` (optional): Proposer wallet address (for on-chain submission)
- `--params` (optional): JSON-encoded parameters for parameter_change proposals
- `--voting-days` (optional): Voting period in days (default: 7)
- `--format` (optional): Output format (table/json, default: table)

**Example:**

```bash
aitbc governance propose --title "Lower tx fee" --description "Reduce the base fee" --category economics --proposer-id operator-1 --voting-days 7
```

**Response:**

```json
{
  "proposal_id": "prop_1a2b3c4d",
  "title": "Lower tx fee",
  "category": "economics",
  "status": "active",
  "voting_ends": "2026-09-21T00:00:00Z"
}
```

### vote

Vote on a governance proposal.

```bash
aitbc governance vote --proposal-id <id> --voter-id <id> --vote <option>
```

**Options:**

- `--proposal-id` (required): Proposal ID to vote on
- `--voter-id` (required): Voter profile ID
- `--vote` (required): Vote option (for, against, abstain)
- `--voter-address` (optional): Voter wallet address (for on-chain voting power)
- `--voting-power` (optional): Voting power to use (default: 0; auto-calculated from on-chain balance if enabled)
- `--reason` (optional): Vote reason
- `--format` (optional): Output format (table/json, default: table)

**Example:**

```bash
aitbc governance vote --proposal-id prop_1a2b3c4d --voter-id voter-1 --vote for --reason "Support this proposal"
```

**Response:**

```json
{
  "proposal_id": "prop_1a2b3c4d",
  "voter_id": "voter-1",
  "vote_type": "for",
  "voting_power": 1000,
  "reason": "Support this proposal"
}
```

### list

List governance proposals with optional filters.

```bash
aitbc governance list [--status <status>] [--category <category>] [--proposer-id <id>]
```

**Options:**

- `--status` (optional): Filter by status (draft, active, succeeded, defeated, executed, cancelled)
- `--category` (optional): Filter by category
- `--proposer-id` (optional): Filter by proposer ID
- `--format` (optional): Output format (table/json, default: table)

**Example:**

```bash
aitbc governance list --status active
```

### get

Get details of a specific proposal.

```bash
aitbc governance get --proposal-id <id>
```

**Options:**

- `--proposal-id` (required): Proposal ID to query
- `--format` (optional): Output format (table/json, default: table)

**Example:**

```bash
aitbc governance get --proposal-id prop_1a2b3c4d
```

**Response:**

```json
{
  "proposal_id": "prop_1a2b3c4d",
  "proposer_id": "operator-1",
  "title": "Lower tx fee",
  "description": "Reduce the base fee",
  "status": "active",
  "voting_ends": "2026-09-21T00:00:00Z"
}
```

### status

Show the global status of the governance system.

```bash
aitbc governance status
```

**Options:**

- `--format` (optional): Output format (table/json, default: table)

**Example:**

```bash
aitbc governance status --format json
```

### close

Close a governance proposal and tally the final votes.

```bash
aitbc governance close --proposal-id <id>
```

**Options:**

- `--proposal-id` (required): Proposal ID to close
- `--format` (optional): Output format (table/json, default: table)

**Example:**

```bash
aitbc governance close --proposal-id prop_1a2b3c4d
```

### execute

Execute a passed proposal.

```bash
aitbc governance execute --proposal-id <id>
```

**Options:**

- `--proposal-id` (required): Proposal ID to execute
- `--executor-address` (optional): Executor wallet address (for on-chain execution)
- `--format` (optional): Output format (table/json, default: table)

**Example:**

```bash
aitbc governance execute --proposal-id prop_1a2b3c4d
```

**Response:**

```json
{
  "proposal_id": "prop_1a2b3c4d",
  "status": "executed",
  "executed_at": "2026-09-21T00:00:00Z"
}
```

**Errors:**

- Proposal not found (404)
- Proposal not in succeeded state (400)

### propagate

Propagate a proposal to target chains.

```bash
aitbc governance propagate --proposal-id <id> --target-chains <chain1,chain2>
```

**Options:**

- `--proposal-id` (required): Proposal ID to propagate
- `--target-chains` (required): Comma-separated list of target chain IDs
- `--format` (optional): Output format (table/json, default: table)

**Example:**

```bash
aitbc governance propagate --proposal-id prop_1a2b3c4d --target-chains ait-side-1,ait-side-2
```

### aggregate-votes

Aggregate and tally cross-chain votes for a proposal.

```bash
aitbc governance aggregate-votes --proposal-id <id>
```

**Options:**

- `--proposal-id` (required): Proposal ID
- `--format` (optional): Output format (table/json, default: table)

**Example:**

```bash
aitbc governance aggregate-votes --proposal-id prop_1a2b3c4d
```

### execute-cross-chain

Execute a governance proposal across target chains.

```bash
aitbc governance execute-cross-chain --proposal-id <id>
```

**Options:**

- `--proposal-id` (required): Proposal ID
- `--format` (optional): Output format (table/json, default: table)

**Example:**

```bash
aitbc governance execute-cross-chain --proposal-id prop_1a2b3c4d
```

## Configuration

The commands talk to the governance service REST API. The base URL comes from the
`governance_service_url` config field (set via `GOVERNANCE_SERVICE_URL` in the
environment, `.aitbc.yaml`, or `~/.aitbc/credentials.env`) and defaults to
`http://localhost:8105`.

## Profiles and Wallet Addresses

Commands identify actors by profile ID (`--proposer-id`, `--voter-id`), not by
wallet name — this group takes no `--wallet` flag. Optional
`--proposer-address`, `--voter-address`, and `--executor-address` fields carry
wallet addresses used for on-chain submission and voting power. To look up an
address:

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
aitbc governance list --format table
```

### JSON

Machine-readable JSON output.

```bash
aitbc governance list --format json
```

## Error Handling

Common errors:

- **Network Error:** Cannot connect to governance service
- **Invalid Address:** Invalid wallet address format
- **Insufficient Balance:** Not enough tokens for operation
- **Proposal Not Found:** Proposal ID does not exist
- **Already Voted:** Address has already voted on proposal

## Examples

### Complete Proposal Workflow

```bash
# Create proposal (the service assigns the prop_<hex8> id)
aitbc governance propose --title "Lower tx fee" --description "Reduce the base fee" --proposer-id operator-1

# Vote on proposal
aitbc governance vote --proposal-id prop_1a2b3c4d --voter-id voter-1 --vote for

# Check proposal details
aitbc governance get --proposal-id prop_1a2b3c4d

# Close voting and tally
aitbc governance close --proposal-id prop_1a2b3c4d

# Execute proposal (after it passes)
aitbc governance execute --proposal-id prop_1a2b3c4d
```

### Cross-Chain Workflow

```bash
# Propagate to target chains
aitbc governance propagate --proposal-id prop_1a2b3c4d --target-chains ait-side-1,ait-side-2

# Tally cross-chain votes
aitbc governance aggregate-votes --proposal-id prop_1a2b3c4d

# Execute across chains
aitbc governance execute-cross-chain --proposal-id prop_1a2b3c4d
```

## Help

Get help for any command:

```bash
aitbc governance --help
aitbc governance propose --help
aitbc governance vote --help
```
