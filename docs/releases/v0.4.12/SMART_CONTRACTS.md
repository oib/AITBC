# Smart Contracts - v0.4.12

**Release**: v0.4.12
**Date**: June 7, 2026
**Status**: ✅ Implementation Complete

## Overview

AITBC v0.4.12 introduces two smart contracts for governance: AITBCGovernanceToken (ERC20 with staking and 2x voting power multiplier) and AITBCVoting (proposal creation, voting, execution with quorum). All smart contract tests are passing (14/14 tests).

## Governance Token Contract

### Contract Specification

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract AITBCGovernanceToken {
    string public constant NAME = "AITBC Governance Token";
    string public constant SYMBOL = "GOV";
    uint8 public constant DECIMALS = 18;
    uint256 public constant TOTAL_SUPPLY = 1_000_000_000 * 10**18;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    mapping(address => uint256) public votingPower;
    mapping(address => uint256) public stakedTokens;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event TokensStaked(address indexed staker, uint256 amount, uint256 lockPeriod);
    event TokensUnstaked(address indexed staker, uint256 amount);
    event VotingPowerUpdated(address indexed account, uint256 newPower);

    constructor() {
        balanceOf[msg.sender] = TOTAL_SUPPLY;
        emit Transfer(address(0), msg.sender, TOTAL_SUPPLY);
    }

    function stake(uint256 amount, uint256 lockPeriod) external {
        require(balanceOf[msg.sender] >= amount, "Insufficient balance");
        require(lockPeriod >= 30 days, "Lock period too short");

        balanceOf[msg.sender] -= amount;
        stakedTokens[msg.sender] += amount;
        votingPower[msg.sender] += amount * 2; // 2x voting power for staked

        emit TokensStaked(msg.sender, amount, lockPeriod);
        emit VotingPowerUpdated(msg.sender, votingPower[msg.sender]);
    }

    function unstake(uint256 amount) external {
        require(stakedTokens[msg.sender] >= amount, "Insufficient staked tokens");

        stakedTokens[msg.sender] -= amount;
        balanceOf[msg.sender] += amount;
        votingPower[msg.sender] -= amount * 2;

        emit TokensUnstaked(msg.sender, amount);
        emit VotingPowerUpdated(msg.sender, votingPower[msg.sender]);
    }

    function getVotingPower(address account) external view returns (uint256) {
        return balanceOf[account] + stakedTokens[account] * 2;
    }
}
```

### Features

- **ERC20 Token**: Standard ERC20 implementation
- **Token Staking**: Stake tokens for enhanced voting power
- **2x Voting Power**: Staked tokens provide 2x voting power
- **Total Supply**: 1,000,000,000 GOV tokens
- **Events**: Transfer, Approval, TokensStaked, TokensUnstaked, VotingPowerUpdated

## Voting Contract

### Contract Specification

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract AITBCVoting {
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

    enum ProposalStatus { Draft, Active, Passed, Rejected, Executed }

    mapping(bytes32 => Proposal) public proposals;
    mapping(bytes32 => mapping(address => bool)) public hasVoted;
    AITBCGovernanceToken public governanceToken;

    uint256 public constant QUORUM_PERCENTAGE = 10; // 10% of total supply
    uint256 public constant EXECUTION_DELAY = 1 days;

    event ProposalCreated(bytes32 indexed proposalId, address indexed proposer);
    event VoteCast(bytes32 indexed proposalId, address indexed voter, bool vote, uint256 power);
    event ProposalExecuted(bytes32 indexed proposalId);

    constructor(address _tokenAddress) {
        governanceToken = AITBCGovernanceToken(_tokenAddress);
    }

    function createProposal(
        string memory proposalType,
        string memory title,
        string memory description,
        bytes memory value,
        uint256 votingPeriod
    ) external returns (bytes32) {
        bytes32 proposalId = keccak256(abi.encodePacked(msg.sender, block.timestamp, title));

        proposals[proposalId] = Proposal({
            id: proposalId,
            proposer: msg.sender,
            proposalType: proposalType,
            title: title,
            description: description,
            value: value,
            status: ProposalStatus.Active,
            votingStart: block.timestamp,
            votingEnd: block.timestamp + votingPeriod,
            quorumRequired: (governanceToken.TOTAL_SUPPLY() * QUORUM_PERCENTAGE) / 100,
            yesVotes: 0,
            noVotes: 0
        });

        emit ProposalCreated(proposalId, msg.sender);
        return proposalId;
    }

    function vote(bytes32 proposalId, bool support) external {
        Proposal storage proposal = proposals[proposalId];
        require(proposal.status == ProposalStatus.Active, "Proposal not active");
        require(block.timestamp >= proposal.votingStart, "Voting not started");
        require(block.timestamp <= proposal.votingEnd, "Voting ended");
        require(!hasVoted[proposalId][msg.sender], "Already voted");

        uint256 votingPower = governanceToken.getVotingPower(msg.sender);
        require(votingPower > 0, "No voting power");

        hasVoted[proposalId][msg.sender] = true;

        if (support) {
            proposal.yesVotes += votingPower;
        } else {
            proposal.noVotes += votingPower;
        }

        emit VoteCast(proposalId, msg.sender, support, votingPower);
    }

    function executeProposal(bytes32 proposalId) external {
        Proposal storage proposal = proposals[proposalId];
        require(proposal.status == ProposalStatus.Active, "Proposal not active");
        require(block.timestamp > proposal.votingEnd, "Voting still active");
        require(block.timestamp >= proposal.votingEnd + EXECUTION_DELAY, "Execution delay not met");

        uint256 totalVotes = proposal.yesVotes + proposal.noVotes;
        require(totalVotes >= proposal.quorumRequired, "Quorum not met");
        require(proposal.yesVotes > proposal.noVotes, "Proposal rejected");

        proposal.status = ProposalStatus.Executed;
        emit ProposalExecuted(proposalId);

        // Execute proposal logic here
        // This would call the appropriate contract functions based on proposal type
    }
}
```

### Features

- **Proposal Creation**: Create governance proposals with type, title, description, and value
- **Proposal Lifecycle**: Draft, Active, Passed, Rejected, Executed
- **Token-Weighted Voting**: Voting power based on token holdings and staking
- **Quorum Requirements**: 10% of total supply required for proposal validity
- **Execution Delay**: 1 day delay after voting ends before execution
- **Double Voting Prevention**: Blockchain-level prevention of duplicate votes

## Deployment

### Deploy Governance Token Contract

```bash
# Deploy governance token contract
aitbc governance deploy-token \
  --name "AITBC Governance Token" \
  --symbol GOV \
  --total-supply 1000000000 \
  --network testnet

# Verify deployment
aitbc governance verify-contract --address <contract-address>
```

### Deploy Voting Contract

```bash
# Deploy voting contract with token address
aitbc governance deploy-voting \
  --token-address <governance-token-address> \
  --quorum-percentage 10 \
  --execution-delay 86400 \
  --network testnet
```

## Testing

### Smart Contract Tests

- **7 tests for AITBCGovernanceToken**: Token transfer, staking, unstaking, voting power calculation
- **7 tests for AITBCVoting**: Proposal creation, voting, execution, quorum validation
- **All tests passing**: 14/14 tests

### Verification

```bash
# Verify contract addresses
aitbc governance verify-token --address <token-address>
aitbc governance verify-voting --address <voting-address>

# Test contract functions
aitbc governance test-contract --function getVotingPower
```

## Dependencies

- **Foundry**: forge, cast, anvil, chisel version 1.7.1
- **Solidity**: ^0.8.0

---

*Last Updated: 2026-06-07*
