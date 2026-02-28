// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "../interfaces/IModularContracts.sol";
import "./ContractRegistry.sol";

/**
 * @title DAOGovernanceEnhanced
 * @dev Enhanced multi-jurisdictional DAO framework with modular integrations
 * @notice Integrates with TreasuryManager, CrossChainGovernance, and PerformanceAggregator
 */
contract DAOGovernanceEnhanced is IModularContract, Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;
    
    // State variables
    uint256 public version = 2; // Enhanced version
    IERC20 public governanceToken;
    ContractRegistry public registry;
    ITreasuryManager public treasuryManager;
    ICrossChainGovernance public crossChainGovernance;
    IPerformanceAggregator public performanceAggregator;
    
    // Staking Parameters
    uint256 public minStakeAmount;
    uint256 public unbondingPeriod = 7 days;
    
    // Enhanced Staker struct
    struct Staker {
        uint256 amount;
        uint256 unbondingAmount;
        uint256 unbondingCompleteTime;
        uint256 lastStakeTime;
        uint256 reputationScore;
        uint256 votingPower;
        bool isActive;
    }
    
    // Enhanced Proposal struct
    enum ProposalState { Pending, Active, Canceled, Defeated, Succeeded, Queued, Expired, Executed }
    enum ProposalType { TREASURY_ALLOCATION, PARAMETER_CHANGE, CROSS_CHAIN, REWARD_DISTRIBUTION }
    
    struct Proposal {
        uint256 id;
        address proposer;
        string region; // "" for global
        string descriptionHash;
        uint256 forVotes;
        uint256 againstVotes;
        uint256 abstainVotes;
        uint256 startTime;
        uint256 endTime;
        bool executed;
        bool canceled;
        ProposalState state;
        ProposalType proposalType;
        address targetContract;
        bytes callData;
        uint256 value;
        mapping(address => bool) hasVoted;
        mapping(address => uint8) voteType; // 0=against, 1=for, 2=abstain
    }
    
    // Cross-chain proposal
    struct CrossChainProposal {
        uint256 sourceChainId;
        bytes32 proposalHash;
        uint256 localProposalId;
        bool isValidated;
        uint256 validationTime;
        address validator;
        bytes32 validationProof;
    }
    
    // Mappings
    mapping(address => Staker) public stakers;
    mapping(uint256 => Proposal) public proposals;
    mapping(string => mapping(address => bool)) public isRegionalCouncilMember;
    mapping(string => address[]) public regionalCouncilMembers;
    mapping(uint256 => CrossChainProposal) public crossChainProposals;
    mapping(uint256 => uint256) public proposalToCrossChain;
    
    // Counters
    uint256 public proposalCount;
    uint256 public totalStaked;
    uint256[] public activeProposalIds;
    
    // Events
    event Staked(address indexed user, uint256 amount);
    event Unstaked(address indexed user, uint256 amount);
    event ProposalCreated(uint256 indexed id, address proposer, string region, ProposalType proposalType);
    event VoteCast(address indexed voter, uint256 indexed proposalId, uint8 voteType, uint256 weight);
    event ProposalExecuted(uint256 indexed id);
    event CrossChainProposalSubmitted(uint256 indexed localId, uint256 sourceChainId, bytes32 proposalHash);
    event ReputationUpdated(address indexed staker, uint256 newReputation);
    event VotingPowerUpdated(address indexed staker, uint256 newVotingPower);
    
    // Errors
    error InvalidAmount(uint256 amount);
    error InsufficientStake(uint256 required, uint256 available);
    error ProposalNotFound(uint256 proposalId);
    error ProposalNotActive(uint256 proposalId);
    error AlreadyVoted(uint256 proposalId, address voter);
    error InvalidVoteType(uint8 voteType);
    error NotCouncilMember(string region, address member);
    error RegistryNotSet();
    error CrossChainValidationFailed(uint256 proposalId);
    
    modifier validAmount(uint256 amount) {
        if (amount == 0) revert InvalidAmount(amount);
        _;
    }
    
    modifier validProposal(uint256 proposalId) {
        if (proposals[proposalId].id == 0) revert ProposalNotFound(proposalId);
        _;
    }
    
    modifier onlyActiveStaker() {
        if (stakers[msg.sender].amount < minStakeAmount) revert InsufficientStake(minStakeAmount, stakers[msg.sender].amount);
        _;
    }
    
    modifier onlyCouncilMember(string memory region) {
        if (bytes(region).length > 0 && !isRegionalCouncilMember[region][msg.sender]) {
            revert NotCouncilMember(region, msg.sender);
        }
        _;
    }
    
    modifier registrySet() {
        if (address(registry) == address(0)) revert RegistryNotSet();
        _;
    }
    
    constructor(address _governanceToken, uint256 _minStakeAmount) {
        governanceToken = IERC20(_governanceToken);
        minStakeAmount = _minStakeAmount;
    }
    
    /**
     * @dev Initialize the enhanced DAO governance (implements IModularContract)
     */
    function initialize(address _registry) external override {
        require(address(registry) == address(0), "Already initialized");
        registry = ContractRegistry(_registry);
        
        // Register this contract
        bytes32 contractId = keccak256(abi.encodePacked("DAOGovernanceEnhanced"));
        registry.registerContract(contractId, address(this));
        
        // Get integration addresses from registry
        treasuryManager = ITreasuryManager(registry.getContract(keccak256(abi.encodePacked("TreasuryManager"))));
        crossChainGovernance = ICrossChainGovernance(registry.getContract(keccak256(abi.encodePacked("CrossChainGovernance"))));
        performanceAggregator = IPerformanceAggregator(registry.getContract(keccak256(abi.encodePacked("PerformanceAggregator"))));
    }
    
    /**
     * @dev Upgrade the contract
     */
    function upgrade(address newImplementation) external override onlyOwner {
        version++;
        // Implementation upgrade logic would go here
    }
    
    /**
     * @dev Pause the contract
     */
    function pause() external override onlyOwner {
        // Implementation would use Pausable mixin
    }
    
    /**
     * @dev Unpause the contract
     */
    function unpause() external override onlyOwner {
        // Implementation would use Pausable mixin
    }
    
    /**
     * @dev Get current version
     */
    function getVersion() external view override returns (uint256) {
        return version;
    }
    
    // --- Enhanced Staking ---
    
    function stake(uint256 _amount) external nonReentrant validAmount(_amount) {
        governanceToken.safeTransferFrom(msg.sender, address(this), _amount);
        
        Staker storage staker = stakers[msg.sender];
        staker.amount += _amount;
        staker.lastStakeTime = block.timestamp;
        staker.isActive = true;
        totalStaked += _amount;
        
        // Update voting power based on reputation
        _updateVotingPower(msg.sender);
        
        require(staker.amount >= minStakeAmount, "Below min stake");
        
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
        
        // Update voting power
        _updateVotingPower(msg.sender);
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
    
    // --- Enhanced Proposals & Voting ---
    
    function createProposal(
        string calldata _region,
        string calldata _descriptionHash,
        uint256 _votingPeriod,
        ProposalType _proposalType,
        address _targetContract,
        bytes calldata _callData,
        uint256 _value
    ) external onlyActiveStaker onlyCouncilMember(_region) nonReentrant returns (uint256) {
        proposalCount++;
        Proposal storage p = proposals[proposalCount];
        
        p.id = proposalCount;
        p.proposer = msg.sender;
        p.region = _region;
        p.descriptionHash = _descriptionHash;
        p.startTime = block.timestamp;
        p.endTime = block.timestamp + _votingPeriod;
        p.state = ProposalState.Active;
        p.proposalType = _proposalType;
        p.targetContract = _targetContract;
        p.callData = _callData;
        p.value = _value;
        
        activeProposalIds.push(proposalCount);
        
        emit ProposalCreated(p.id, msg.sender, _region, _proposalType);
        return p.id;
    }
    
    function castVote(uint256 _proposalId, uint8 _voteType) external validProposal(_proposalId) nonReentrant {
        Proposal storage p = proposals[_proposalId];
        require(block.timestamp >= p.startTime && block.timestamp <= p.endTime, "Voting closed");
        require(!p.hasVoted[msg.sender], "Already voted");
        require(_voteType <= 2, "Invalid vote type");
        
        uint256 weight = _calculateVotingWeight(msg.sender, p.region);
        require(weight > 0, "No voting weight");
        
        p.hasVoted[msg.sender] = true;
        p.voteType[msg.sender] = _voteType;
        
        if (_voteType == 0) { // Against
            p.againstVotes += weight;
        } else if (_voteType == 1) { // For
            p.forVotes += weight;
        } else { // Abstain
            p.abstainVotes += weight;
        }
        
        emit VoteCast(msg.sender, _proposalId, _voteType, weight);
    }
    
    function executeProposal(uint256 _proposalId) external validProposal(_proposalId) nonReentrant {
        Proposal storage p = proposals[_proposalId];
        require(block.timestamp > p.endTime, "Voting not ended");
        require(p.state == ProposalState.Active, "Invalid proposal state");
        
        // Check if proposal passed
        uint256 totalVotes = p.forVotes + p.againstVotes + p.abstainVotes;
        bool passed = p.forVotes > p.againstVotes && totalVotes > 0;
        
        if (passed) {
            p.state = ProposalState.Succeeded;
            _executeProposalAction(_proposalId);
            p.state = ProposalState.Executed;
        } else {
            p.state = ProposalState.Defeated;
        }
        
        // Remove from active proposals
        _removeFromActiveProposals(_proposalId);
        
        emit ProposalExecuted(_proposalId);
    }
    
    // --- Cross-Chain Integration ---
    
    function submitCrossChainProposal(
        uint256 _sourceChainId,
        bytes32 _proposalHash,
        string calldata _descriptionHash
    ) external onlyActiveStaker nonReentrant returns (uint256) {
        // Create local proposal for cross-chain validation
        bytes memory callData = abi.encodeWithSignature("validateCrossChainProposal(uint256,bytes32)", _sourceChainId, _proposalHash);
        
        uint256 localProposalId = _createCrossChainProposal(
            _descriptionHash,
            7 days,
            ProposalType.CROSS_CHAIN,
            address(crossChainGovernance),
            callData,
            0
        );
        
        // Store cross-chain reference
        crossChainProposals[localProposalId] = CrossChainProposal({
            sourceChainId: _sourceChainId,
            proposalHash: _proposalHash,
            localProposalId: localProposalId,
            isValidated: false,
            validationTime: 0,
            validator: address(0),
            validationProof: bytes32(0)
        });
        
        proposalToCrossChain[localProposalId] = _sourceChainId;
        
        emit CrossChainProposalSubmitted(localProposalId, _sourceChainId, _proposalHash);
        
        return localProposalId;
    }
    
    function _createCrossChainProposal(
        string calldata _descriptionHash,
        uint256 _votingPeriod,
        ProposalType _proposalType,
        address _targetContract,
        bytes memory _callData,
        uint256 _value
    ) internal onlyActiveStaker nonReentrant returns (uint256) {
        proposalCount++;
        Proposal storage p = proposals[proposalCount];
        
        p.id = proposalCount;
        p.proposer = msg.sender;
        p.region = "";
        p.descriptionHash = _descriptionHash;
        p.startTime = block.timestamp;
        p.endTime = block.timestamp + _votingPeriod;
        p.state = ProposalState.Active;
        p.proposalType = _proposalType;
        p.targetContract = _targetContract;
        p.callData = _callData;
        p.value = _value;
        
        activeProposalIds.push(proposalCount);
        
        emit ProposalCreated(p.id, msg.sender, "", _proposalType);
        return p.id;
    }
    
    function validateCrossChainVote(uint256 _proposalId, bytes32 _voteProof) external {
        if (address(crossChainGovernance) != address(0)) {
            crossChainGovernance.validateCrossChainVote(_proposalId, _voteProof);
        }
    }
    
    // --- Internal Functions ---
    
    function _calculateVotingWeight(address _voter, string memory _region) internal view returns (uint256) {
        Staker memory staker = stakers[_voter];
        
        // Regional council members have equal voting power
        if (bytes(_region).length > 0 && isRegionalCouncilMember[_region][_voter]) {
            return 1;
        }
        
        // Global voting based on stake and reputation
        return staker.votingPower;
    }
    
    function _executeProposalAction(uint256 _proposalId) internal {
        Proposal storage p = proposals[_proposalId];
        
        if (p.targetContract != address(0) && p.callData.length > 0) {
            // Execute the proposal action
            (bool success, ) = p.targetContract.call{value: p.value}(p.callData);
            require(success, "Execution failed");
        }
    }
    
    function _updateVotingPower(address _staker) internal {
        Staker storage staker = stakers[_staker];
        
        // Base voting power is stake amount
        uint256 basePower = staker.amount;
        
        // Apply reputation multiplier
        uint256 reputationMultiplier = 10000; // 1x default
        if (address(performanceAggregator) != address(0)) {
            uint256 reputation = performanceAggregator.getReputationScore(_staker);
            reputationMultiplier = performanceAggregator.calculateAPYMultiplier(reputation);
        }
        
        staker.votingPower = (basePower * reputationMultiplier) / 10000;
        staker.reputationScore = performanceAggregator.getReputationScore(_staker);
        
        emit VotingPowerUpdated(_staker, staker.votingPower);
        emit ReputationUpdated(_staker, staker.reputationScore);
    }
    
    function _removeFromActiveProposals(uint256 _proposalId) internal {
        for (uint256 i = 0; i < activeProposalIds.length; i++) {
            if (activeProposalIds[i] == _proposalId) {
                activeProposalIds[i] = activeProposalIds[activeProposalIds.length - 1];
                activeProposalIds.pop();
                break;
            }
        }
    }
    
    // --- View Functions ---
    
    function getStakerInfo(address _staker) external view returns (
        uint256 amount,
        uint256 votingPower,
        uint256 reputationScore,
        bool isActive
    ) {
        Staker memory staker = stakers[_staker];
        return (
            staker.amount,
            staker.votingPower,
            staker.reputationScore,
            staker.isActive
        );
    }
    
    function getProposalInfo(uint256 _proposalId) external view returns (
        address proposer,
        string memory region,
        ProposalState state,
        ProposalType proposalType,
        uint256 forVotes,
        uint256 againstVotes,
        uint256 abstainVotes,
        uint256 startTime,
        uint256 endTime
    ) {
        Proposal storage p = proposals[_proposalId];
        return (
            p.proposer,
            p.region,
            p.state,
            p.proposalType,
            p.forVotes,
            p.againstVotes,
            p.abstainVotes,
            p.startTime,
            p.endTime
        );
    }
    
    function getActiveProposals() external view returns (uint256[] memory) {
        return activeProposalIds;
    }
    
    function getRegionalCouncilMembers(string memory _region) external view returns (address[] memory) {
        return regionalCouncilMembers[_region];
    }
    
    // --- Admin Functions ---
    
    function setRegionalCouncilMember(string calldata _region, address _member, bool _status) external onlyOwner {
        isRegionalCouncilMember[_region][_member] = _status;
        if (_status) {
            regionalCouncilMembers[_region].push(_member);
        }
    }
    
    function setMinStakeAmount(uint256 _minStakeAmount) external onlyOwner {
        minStakeAmount = _minStakeAmount;
    }
    
    function setUnbondingPeriod(uint256 _unbondingPeriod) external onlyOwner {
        unbondingPeriod = _unbondingPeriod;
    }
    
    function emergencyPause() external onlyOwner {
        // Emergency pause functionality
    }
    
    function emergencyUnpause() external onlyOwner {
        // Emergency unpause functionality
    }
}
