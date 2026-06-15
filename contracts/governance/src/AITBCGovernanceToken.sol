// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract AITBCGovernanceToken is ERC20, Ownable {
    string public constant NAME = "AITBC Governance Token";
    string public constant SYMBOL = "GOV";
    uint8 public constant DECIMALS = 18;
    uint256 public constant TOTAL_SUPPLY = 1_000_000_000 * 10**18;

    mapping(address => uint256) public stakedTokens;
    mapping(address => uint256) public votingPower;
    mapping(address => uint256) public stakeLockEnd;

    uint256 public constant MIN_LOCK_PERIOD = 30 days;
    uint256 public constant STAKING_MULTIPLIER = 2; // 2x voting power

    event TokensStaked(address indexed staker, uint256 amount, uint256 lockPeriod);
    event TokensUnstaked(address indexed staker, uint256 amount);
    event VotingPowerUpdated(address indexed account, uint256 newPower);

    constructor() ERC20(NAME, SYMBOL) Ownable(msg.sender) {
        _mint(msg.sender, TOTAL_SUPPLY);
    }

    function stake(uint256 amount, uint256 lockPeriod) external {
        require(balanceOf(msg.sender) >= amount, "Insufficient balance");
        require(lockPeriod >= MIN_LOCK_PERIOD, "Lock period too short");
        require(stakedTokens[msg.sender] == 0, "Already staking");

        _transfer(msg.sender, address(this), amount);
        stakedTokens[msg.sender] = amount;
        stakeLockEnd[msg.sender] = block.timestamp + lockPeriod;

        uint256 newVotingPower = balanceOf(msg.sender) + (amount * STAKING_MULTIPLIER);
        votingPower[msg.sender] = newVotingPower;

        emit TokensStaked(msg.sender, amount, lockPeriod);
        emit VotingPowerUpdated(msg.sender, newVotingPower);
    }

    function unstake(uint256 amount) external {
        require(stakedTokens[msg.sender] >= amount, "Insufficient staked tokens");
        require(block.timestamp >= stakeLockEnd[msg.sender], "Stake still locked");

        stakedTokens[msg.sender] -= amount;
        _transfer(address(this), msg.sender, amount);

        uint256 newVotingPower = balanceOf(msg.sender) + (stakedTokens[msg.sender] * STAKING_MULTIPLIER);
        votingPower[msg.sender] = newVotingPower;

        emit TokensUnstaked(msg.sender, amount);
        emit VotingPowerUpdated(msg.sender, newVotingPower);
    }

    function getVotingPower(address account) external view returns (uint256) {
        return votingPower[account];
    }

    function _update(address from, address to, uint256 value) internal override {
        super._update(from, to, value);

        // Recalculate voting power for both parties
        if (from != address(0)) {
            votingPower[from] = balanceOf(from) + (stakedTokens[from] * STAKING_MULTIPLIER);
            emit VotingPowerUpdated(from, votingPower[from]);
        }
        if (to != address(0)) {
            votingPower[to] = balanceOf(to) + (stakedTokens[to] * STAKING_MULTIPLIER);
            emit VotingPowerUpdated(to, votingPower[to]);
        }
    }
}
