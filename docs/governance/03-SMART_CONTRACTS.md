# Smart Contracts

## Overview

The AITBC Governance system includes two smart contracts deployed on the blockchain: AITBCGovernanceToken (ERC20 with staking) and AITBCVoting (proposal management and voting).

## AITBCGovernanceToken.sol

### Description

ERC20 token with staking capabilities for enhanced voting power. Staked tokens receive a 2x voting power multiplier.

### Location

`/opt/aitbc/contracts/governance/src/AITBCGovernanceToken.sol`

### Features

- **Token Supply:** 1,000,000,000 GOV tokens
- **Decimals:** 18
- **Staking:** Minimum 30-day lock period
- **Voting Power Multiplier:** 2x for staked tokens
- **Automatic Recalculation:** Voting power updates on transfers

### Key Functions

#### stake(amount, lockPeriod)
Stake tokens for enhanced voting power.

**Parameters:**
- `amount` (uint256): Amount of tokens to stake
- `lockPeriod` (uint256): Lock period in seconds (minimum 30 days)

**Requirements:**
- Sufficient token balance
- Lock period >= 30 days
- No existing active stake

**Events:**
- `TokensStaked(staker, amount, lockPeriod)`
- `VotingPowerUpdated(account, newPower)`

#### unstake(amount)
Unstake tokens after lock period expires.

**Parameters:**
- `amount` (uint256): Amount of tokens to unstake

**Requirements:**
- Sufficient staked tokens
- Lock period expired

**Events:**
- `TokensUnstaked(staker, amount)`
- `VotingPowerUpdated(account, newPower)`

#### getVotingPower(address)
Get total voting power for an address.

**Parameters:**
- `address` (address): Address to query

**Returns:**
- `uint256`: Total voting power (balance + staked * 2)

### State Variables

| Variable | Type | Description |
|----------|------|-------------|
| stakedTokens | mapping(address → uint256) | Staked token amounts |
| votingPower | mapping(address → uint256) | Voting power per address |
| stakeLockEnd | mapping(address → uint256) | Lock end timestamps |
| MIN_LOCK_PERIOD | uint256 | 30 days |
| STAKING_MULTIPLIER | uint256 | 2 |

### Test Coverage

**7/7 tests passing:**
- testInitialState
- testStakeTokens
- testStakeMinimumLockPeriod
- testCannotStakeTwice
- testUnstakeTokens
- testCannotUnstakeBeforeLockPeriod
- testVotingPowerCalculation

## AITBCVoting.sol

### Description

Proposal creation, voting, and execution contract with quorum requirements and execution delays.

### Location

`/opt/aitbc/contracts/governance/src/AITBCVoting.sol`

### Features

- **Proposal Creation:** Configurable voting periods (1-30 days)
- **Token-Weighted Voting:** Voting power from token contract
- **Quorum Requirement:** 10% of total supply
- **Execution Delay:** 1 day after voting ends
- **Proposal Types:** parameter_change, spending, contract_upgrade, emergency, other

### Key Functions

#### createProposal(type, title, description, value, votingPeriod)
Create a new governance proposal.

**Parameters:**
- `type` (string): Proposal type
- `title` (string): Proposal title
- `description` (string): Proposal description
- `value` (bytes): Proposal value/data
- `votingPeriod` (uint256): Voting period in seconds

**Requirements:**
- Voting period >= 1 day
- Voting period <= 30 days

**Returns:**
- `bytes32`: Proposal ID

**Events:**
- `ProposalCreated(proposalId, proposer)`

#### vote(proposalId, support)
Vote on a proposal.

**Parameters:**
- `proposalId` (bytes32): Proposal to vote on
- `support` (bool): True for yes, False for no

**Requirements:**
- Proposal is active
- Voting period has started
- Voting period has not ended
- Address has not already voted
- Address has voting power > 0

**Events:**
- `VoteCast(proposalId, voter, support, power)`

#### executeProposal(proposalId)
Execute a passed proposal.

**Parameters:**
- `proposalId` (bytes32): Proposal to execute

**Requirements:**
- Proposal is active
- Voting period has ended
- Execution delay has passed (1 day)
- Quorum met (10% of total supply)
- More yes votes than no votes

**Events:**
- `ProposalExecuted(proposalId)`

#### getProposal(proposalId)
Get proposal details.

**Parameters:**
- `proposalId` (bytes32): Proposal to query

**Returns:**
- `Proposal`: Proposal struct with all details

#### hasVotedOn(voter, proposalId)
Check if an address has voted on a proposal.

**Parameters:**
- `voter` (address): Voter address
- `proposalId` (bytes32): Proposal to check

**Returns:**
- `bool`: True if voted, False otherwise

### State Variables

| Variable | Type | Description |
|----------|------|-------------|
| proposals | mapping(bytes32 → Proposal) | Proposal storage |
| hasVoted | mapping(bytes32 → mapping(address → bool)) | Vote tracking |
| governanceToken | AITBCGovernanceToken | Token contract reference |
| QUORUM_PERCENTAGE | uint256 | 10% |
| EXECUTION_DELAY | uint256 | 1 day |
| MIN_VOTING_PERIOD | uint256 | 1 day |
| MAX_VOTING_PERIOD | uint256 | 30 days |

### Proposal Struct

```solidity
struct Proposal {
    bytes32 id;
    address proposer;
    string proposalType;
    string title;
    string description;
    bytes value;
    ProposalStatus status;
    uint256 votingStart;
    uint256 votingEnd;
    uint256 quorumRequired;
    uint256 yesVotes;
    uint256 noVotes;
}
```

### ProposalStatus Enum

- Draft
- Active
- Passed
- Rejected
- Executed

### Test Coverage

**7/7 tests passing:**
- testCreateProposal
- testCreateProposalInvalidVotingPeriod
- testVoteOnProposal
- testCannotVoteTwice
- testCannotVoteAfterVotingEnds
- testExecuteProposal
- testCannotExecuteRejectedProposal

## Testing

### Running Tests

```bash
cd /opt/aitbc/contracts/governance
forge test
```

### Test Results

```
Ran 7 tests for test/AITBCGovernanceToken.t.sol:AITBCGovernanceTokenTest
[PASS] testCannotStakeTwice() (gas: 184953)
[PASS] testCannotUnstakeBeforeLockPeriod() (gas: 164498)
[PASS] testInitialState() (gas: 28987)
[PASS] testStakeMinimumLockPeriod() (gas: 81151)
[PASS] testStakeTokens() (gas: 166131)
[PASS] testUnstakeTokens() (gas: 188993)
[PASS] testVotingPowerCalculation() (gas: 184584)

Ran 7 tests for test/AITBCVoting.t.sol:AITBCVotingTest
[PASS] testCannotExecuteRejectedProposal() (gas: 413762)
[PASS] testCannotVoteAfterVotingEnds() (gas: 328630)
[PASS] testCannotVoteTwice() (gas: 377182)
[PASS] testCreateProposal() (gas: 341315)
[PASS] testCreateProposalInvalidVotingPeriod() (gas: 17347)
[PASS] testExecuteProposal() (gas: 428985)
[PASS] testVoteOnProposal() (gas: 376474)

Total: 14/14 tests passing
```

## Deployment

### Prerequisites

- Foundry installed
- OpenZeppelin contracts installed
- Testnet/Mainnet RPC endpoint configured

### Deployment Steps

1. **Compile contracts:**
   ```bash
   forge build
   ```

2. **Deploy AITBCGovernanceToken:**
   ```bash
   forge create src/AITBCGovernanceToken.sol:AITBCGovernanceToken \
     --rpc-url <RPC_URL> \
     --private-key <PRIVATE_KEY>
   ```

3. **Deploy AITBCVoting:**
   ```bash
   forge create src/AITBCVoting.sol:AITBCVoting \
     --rpc-url <RPC_URL> \
     --private-key <PRIVATE_KEY> \
     --constructor-args <TOKEN_ADDRESS>
   ```

4. **Verify deployment:**
   ```bash
   cast call <TOKEN_ADDRESS> "totalSupply()" --rpc-url <RPC_URL>
   cast call <VOTING_ADDRESS> "governanceToken()" --rpc-url <RPC_URL>
   ```

## Gas Optimization

The contracts include several gas optimization techniques:

- **Packed structs:** Proposal struct uses efficient data types
- **Event indexing:** Key parameters indexed for filtering
- **View functions:** Read-only functions marked as view
- **Storage optimization:** Mappings for efficient lookups

## Security Considerations

- **Reentrancy:** No external calls in critical paths
- **Integer Overflow:** Solidity 0.8+ has built-in overflow protection
- **Access Control:** Only proposal creator can execute (simplified for v0.4.12)
- **Time Manipulation:** Block timestamp used with delays to prevent manipulation
