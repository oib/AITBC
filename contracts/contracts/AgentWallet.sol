// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

/**
 * @title AgentWallet
 * @dev Isolated agent-specific wallet for micro-transactions, funded by user allowances.
 */
contract AgentWallet is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public aitbcToken;

    // Structs
    struct Agent {
        address owner;
        uint256 balance;
        uint256 spendingLimit;
        uint256 totalSpent;
        bool isActive;
    }

    struct Transaction {
        uint256 txId;
        address agent;
        address recipient;
        uint256 amount;
        uint256 timestamp;
        string purpose;
    }

    // State Variables
    uint256 public txCounter;
    mapping(address => Agent) public agents;
    mapping(uint256 => Transaction) public transactions;
    mapping(address => uint256[]) public agentTransactions;

    // Events
    event AgentRegistered(address indexed agent, address indexed owner);
    event AgentDeactivated(address indexed agent);
    event FundsDeposited(address indexed agent, uint256 amount);
    event FundsWithdrawn(address indexed agent, uint256 amount);
    event SpendingLimitUpdated(address indexed agent, uint256 newLimit);
    event MicroTransactionExecuted(uint256 indexed txId, address indexed agent, address indexed recipient, uint256 amount, string purpose);

    // Modifiers
    modifier onlyAgentOwner(address _agent) {
        require(agents[_agent].owner == msg.sender, "Not agent owner");
        _;
    }

    modifier onlyActiveAgent(address _agent) {
        require(agents[_agent].isActive, "Agent is not active");
        _;
    }

    constructor(address _aitbcToken) {
        require(_aitbcToken != address(0), "Invalid token address");
        aitbcToken = IERC20(_aitbcToken);
    }

    /**
     * @dev Register a new agent wallet
     * @param _agent The address of the agent
     * @param _initialSpendingLimit The max the agent can spend
     */
    function registerAgent(address _agent, uint256 _initialSpendingLimit) external {
        require(_agent != address(0), "Invalid agent address");
        require(agents[_agent].owner == address(0), "Agent already registered");

        agents[_agent] = Agent({
            owner: msg.sender,
            balance: 0,
            spendingLimit: _initialSpendingLimit,
            totalSpent: 0,
            isActive: true
        });

        emit AgentRegistered(_agent, msg.sender);
    }

    /**
     * @dev Deactivate an agent
     * @param _agent The address of the agent
     */
    function deactivateAgent(address _agent) external onlyAgentOwner(_agent) {
        agents[_agent].isActive = false;
        emit AgentDeactivated(_agent);
    }

    /**
     * @dev Update the spending limit for an agent
     * @param _agent The address of the agent
     * @param _newLimit The new spending limit
     */
    function updateSpendingLimit(address _agent, uint256 _newLimit) external onlyAgentOwner(_agent) {
        agents[_agent].spendingLimit = _newLimit;
        emit SpendingLimitUpdated(_agent, _newLimit);
    }

    /**
     * @dev Deposit AITBC tokens into an agent's wallet
     * @param _agent The address of the agent
     * @param _amount The amount to deposit
     */
    function deposit(address _agent, uint256 _amount) external onlyActiveAgent(_agent) nonReentrant {
        require(_amount > 0, "Amount must be greater than 0");
        
        // Transfer tokens from the caller to this contract
        aitbcToken.safeTransferFrom(msg.sender, address(this), _amount);
        
        // Update agent balance
        agents[_agent].balance += _amount;
        
        emit FundsDeposited(_agent, _amount);
    }

    /**
     * @dev Withdraw AITBC tokens from an agent's wallet back to the owner
     * @param _agent The address of the agent
     * @param _amount The amount to withdraw
     */
    function withdraw(address _agent, uint256 _amount) external onlyAgentOwner(_agent) nonReentrant {
        require(_amount > 0, "Amount must be greater than 0");
        require(agents[_agent].balance >= _amount, "Insufficient balance");
        
        // Update agent balance
        agents[_agent].balance -= _amount;
        
        // Transfer tokens back to the owner
        aitbcToken.safeTransfer(msg.sender, _amount);
        
        emit FundsWithdrawn(_agent, _amount);
    }

    /**
     * @dev Execute a micro-transaction from the agent to a recipient
     * @param _recipient The address of the recipient
     * @param _amount The amount to send
     * @param _purpose The purpose of the transaction
     */
    function executeMicroTransaction(
        address _recipient, 
        uint256 _amount, 
        string calldata _purpose
    ) external onlyActiveAgent(msg.sender) nonReentrant returns (uint256) {
        require(_recipient != address(0), "Invalid recipient");
        require(_amount > 0, "Amount must be greater than 0");
        
        Agent storage agent = agents[msg.sender];
        
        require(agent.balance >= _amount, "Insufficient balance");
        require(agent.totalSpent + _amount <= agent.spendingLimit, "Spending limit exceeded");
        
        // Update agent balances
        agent.balance -= _amount;
        agent.totalSpent += _amount;
        
        // Create transaction record
        uint256 txId = txCounter++;
        transactions[txId] = Transaction({
            txId: txId,
            agent: msg.sender,
            recipient: _recipient,
            amount: _amount,
            timestamp: block.timestamp,
            purpose: _purpose
        });
        
        agentTransactions[msg.sender].push(txId);
        
        // Transfer tokens to the recipient
        aitbcToken.safeTransfer(_recipient, _amount);
        
        emit MicroTransactionExecuted(txId, msg.sender, _recipient, _amount, _purpose);
        
        return txId;
    }

    /**
     * @dev Get transaction history for an agent
     * @param _agent The address of the agent
     */
    function getAgentTransactions(address _agent) external view returns (uint256[] memory) {
        return agentTransactions[_agent];
    }
}
