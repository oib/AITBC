// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/**
 * @title DAOGovernance
 * @dev Multi-jurisdictional DAO framework with regional councils and staking.
 */
contract DAOGovernance is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public governanceToken;
    
    // Staking Parameters
    uint256 public minStakeAmount;
    uint256 public unbondingPeriod = 7 days;

    struct Staker {
        uint256 amount;
        uint256 unbondingAmount;
        uint256 unbondingCompleteTime;
        uint256 lastStakeTime;
    }

    mapping(address => Staker) public stakers;
    uint256 public totalStaked;

    // Proposal Parameters
    enum ProposalState { Pending, Active, Canceled, Defeated, Succeeded, Queued, Expired, Executed }
    
    struct Proposal {
        uint256 id;
        address proposer;
        string region; // "" for global
        string descriptionHash;
        uint256 forVotes;
        uint256 againstVotes;
        uint256 startTime;
        uint256 endTime;
        bool executed;
        bool canceled;
        mapping(address => bool) hasVoted;
    }

    uint256 public proposalCount;
    mapping(uint256 => Proposal) public proposals;
    
    // Regional Councils
    mapping(string => mapping(address => bool)) public isRegionalCouncilMember;
    mapping(string => address[]) public regionalCouncilMembers;

    // Events
    event Staked(address indexed user, uint256 amount);
    event Unstaked(address indexed user, uint256 amount);
    event ProposalCreated(uint256 indexed id, address proposer, string region, string descriptionHash);
    event VoteCast(address indexed voter, uint256 indexed proposalId, bool support, uint256 weight);
    event ProposalExecuted(uint256 indexed id);

    constructor(address _governanceToken, uint256 _minStakeAmount) {
        governanceToken = IERC20(_governanceToken);
        minStakeAmount = _minStakeAmount;
    }

    // --- Staking ---

    function stake(uint256 _amount) external nonReentrant {
        require(_amount > 0, "Cannot stake 0");
        
        governanceToken.safeTransferFrom(msg.sender, address(this), _amount);
        
        stakers[msg.sender].amount += _amount;
        stakers[msg.sender].lastStakeTime = block.timestamp;
        totalStaked += _amount;
        
        require(stakers[msg.sender].amount >= minStakeAmount, "Below min stake");
        
        emit Staked(msg.sender, _amount);
    }

    function initiateUnstake(uint256 _amount) external nonReentrant {
        Staker storage staker = stakers[msg.sender];
        require(_amount > 0 && staker.amount >= _amount, "Invalid amount");
        require(staker.unbondingAmount == 0, "Unbonding already in progress");

        staker.amount -= _amount;
        staker.unbondingAmount = _amount;
        staker.unbondingCompleteTime = block.timestamp + unbondingPeriod;
        totalStaked -= _amount;
    }

    function completeUnstake() external nonReentrant {
        Staker storage staker = stakers[msg.sender];
        require(staker.unbondingAmount > 0, "Nothing to unstake");
        require(block.timestamp >= staker.unbondingCompleteTime, "Unbonding not complete");

        uint256 amount = staker.unbondingAmount;
        staker.unbondingAmount = 0;
        
        governanceToken.safeTransfer(msg.sender, amount);
        
        emit Unstaked(msg.sender, amount);
    }

    // --- Proposals & Voting ---

    function createProposal(string calldata _region, string calldata _descriptionHash, uint256 _votingPeriod) external returns (uint256) {
        require(stakers[msg.sender].amount >= minStakeAmount, "Must be staked to propose");
        
        // If regional, must be a council member
        if (bytes(_region).length > 0) {
            require(isRegionalCouncilMember[_region][msg.sender], "Not a council member");
        }

        proposalCount++;
        Proposal storage p = proposals[proposalCount];
        p.id = proposalCount;
        p.proposer = msg.sender;
        p.region = _region;
        p.descriptionHash = _descriptionHash;
        p.startTime = block.timestamp;
        p.endTime = block.timestamp + _votingPeriod;
        
        emit ProposalCreated(p.id, msg.sender, _region, _descriptionHash);
        return p.id;
    }

    function castVote(uint256 _proposalId, bool _support) external {
        Proposal storage p = proposals[_proposalId];
        require(block.timestamp >= p.startTime && block.timestamp <= p.endTime, "Voting closed");
        require(!p.hasVoted[msg.sender], "Already voted");
        
        uint256 weight = stakers[msg.sender].amount;
        require(weight > 0, "No voting weight");

        // If regional, must be a council member
        if (bytes(p.region).length > 0) {
            require(isRegionalCouncilMember[p.region][msg.sender], "Not a council member");
            weight = 1; // 1 member = 1 vote in council
        }

        p.hasVoted[msg.sender] = true;

        if (_support) {
            p.forVotes += weight;
        } else {
            p.againstVotes += weight;
        }

        emit VoteCast(msg.sender, _proposalId, _support, weight);
    }

    function executeProposal(uint256 _proposalId) external nonReentrant {
        Proposal storage p = proposals[_proposalId];
        require(block.timestamp > p.endTime, "Voting not ended");
        require(!p.executed && !p.canceled, "Already executed or canceled");
        require(p.forVotes > p.againstVotes, "Proposal defeated");

        p.executed = true;
        // The actual execution logic (e.g., transferring treasury funds) would happen here
        // Usually involves calling other contracts via target[] and callData[] arrays.
        
        emit ProposalExecuted(_proposalId);
    }

    // --- Admin Functions ---

    function setRegionalCouncilMember(string calldata _region, address _member, bool _status) external onlyOwner {
        isRegionalCouncilMember[_region][_member] = _status;
        if (_status) {
            regionalCouncilMembers[_region].push(_member);
        }
        // Simplified array management for hackathon/demo purposes
    }
}
