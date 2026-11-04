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
    uint256 public totalStakedTokens;

    // Voting-power checkpoints: AITBCVoting reads power at proposal start
    // (#1118) so tokens cannot be voted twice by moving between addresses
    // while a vote is open.
    struct PowerCheckpoint {
        uint256 timestamp;
        uint256 power;
    }
    mapping(address => PowerCheckpoint[]) private _powerCheckpoints;

    function _setVotingPower(address account, uint256 newPower) internal {
        votingPower[account] = newPower;
        PowerCheckpoint[] storage cps = _powerCheckpoints[account];
        uint256 len = cps.length;
        if (len > 0 && cps[len - 1].timestamp == block.timestamp) {
            cps[len - 1].power = newPower;
        } else {
            cps.push(PowerCheckpoint({timestamp: block.timestamp, power: newPower}));
        }
    }

    /// @dev Voting power strictly BEFORE a timestamp: tokens moved in the
    /// same block the proposal was created must not count (#1118).
    function getPastVotingPower(address account, uint256 timestamp) external view returns (uint256) {
        PowerCheckpoint[] storage cps = _powerCheckpoints[account];
        uint256 len = cps.length;
        if (len == 0 || cps[0].timestamp >= timestamp) return 0;
        uint256 lo = 0;
        uint256 hi = len - 1;
        while (lo < hi) {
            uint256 mid = (lo + hi + 1) / 2;
            if (cps[mid].timestamp < timestamp) lo = mid;
            else hi = mid - 1;
        }
        return cps[lo].power;
    }

    /// @dev Total possible voting power: liquid balances plus staked at the
    /// multiplier — the denominator quorum percentages should count (#1118).
    function getTotalVotingPower() external view returns (uint256) {
        return totalSupply() + (totalStakedTokens * (STAKING_MULTIPLIER - 1));
    }

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
        totalStakedTokens += amount;
        stakeLockEnd[msg.sender] = block.timestamp + lockPeriod;

        uint256 newVotingPower = balanceOf(msg.sender) + (amount * STAKING_MULTIPLIER);
        _setVotingPower(msg.sender, newVotingPower);

        emit TokensStaked(msg.sender, amount, lockPeriod);
        emit VotingPowerUpdated(msg.sender, newVotingPower);
    }

    function unstake(uint256 amount) external {
        require(stakedTokens[msg.sender] >= amount, "Insufficient staked tokens");
        require(block.timestamp >= stakeLockEnd[msg.sender], "Stake still locked");

        stakedTokens[msg.sender] -= amount;
        totalStakedTokens -= amount;
        _transfer(address(this), msg.sender, amount);

        uint256 newVotingPower = balanceOf(msg.sender) + (stakedTokens[msg.sender] * STAKING_MULTIPLIER);
        _setVotingPower(msg.sender, newVotingPower);

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
            uint256 powerFrom = balanceOf(from) + (stakedTokens[from] * STAKING_MULTIPLIER);
            _setVotingPower(from, powerFrom);
            emit VotingPowerUpdated(from, powerFrom);
        }
        if (to != address(0)) {
            uint256 powerTo = balanceOf(to) + (stakedTokens[to] * STAKING_MULTIPLIER);
            _setVotingPower(to, powerTo);
            emit VotingPowerUpdated(to, powerTo);
        }
    }
}
