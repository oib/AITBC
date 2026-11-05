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

    IERC20 public paymentToken;

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

    // Phase C1 policy layer (Sepolia vault evolution — #1143). Zero values = legacy
    // self-custody agent (owner still controls policy via agents[].owner).
    mapping(address => address) public agentPolicyOwner;
    mapping(address => uint256) public periodSpendLimit;
    mapping(address => uint256) public periodSpent;
    mapping(address => uint256) public periodWindowEnd;
    mapping(address => bool) public allowlistRequired;
    mapping(address => mapping(address => bool)) public allowedRecipient;
    mapping(address => uint256) public periodDurationSeconds;
    uint256 public constant MAX_PURPOSE_BYTES = 256;

    // Events
    event AgentRegistered(address indexed agent, address indexed owner);
    event AgentDeactivated(address indexed agent);
    event FundsDeposited(address indexed agent, uint256 amount);
    event FundsWithdrawn(address indexed agent, uint256 amount);
    event SpendingLimitUpdated(address indexed agent, uint256 newLimit);
    event MicroTransactionExecuted(uint256 indexed txId, address indexed agent, address indexed recipient, uint256 amount, string purpose);
    event ManagedAgentRegistered(address indexed agent, address indexed policyOwner);
    event RecipientAllowlistUpdated(address indexed agent, address indexed recipient, bool allowed);
    event AllowlistEnforcementUpdated(address indexed agent, bool required);

    // Modifiers
    modifier onlyAgentOwner(address _agent) {
        require(_policyAuthority(_agent) == msg.sender, "Not agent owner");
        _;
    }

    modifier onlyPolicyOwner(address _agent) {
        require(_policyAuthority(_agent) == msg.sender, "Not policy owner");
        _;
    }

    function _policyAuthority(address _agent) internal view returns (address) {
        address explicitOwner = agentPolicyOwner[_agent];
        if (explicitOwner != address(0)) {
            return explicitOwner;
        }
        return agents[_agent].owner;
    }

    function _rollPeriod(address _agent) internal {
        uint256 duration = periodDurationSeconds[_agent];
        if (duration == 0 || periodSpendLimit[_agent] == 0) {
            return;
        }
        if (periodWindowEnd[_agent] == 0 || block.timestamp >= periodWindowEnd[_agent]) {
            periodSpent[_agent] = 0;
            periodWindowEnd[_agent] = block.timestamp + duration;
        }
    }

    modifier onlyActiveAgent(address _agent) {
        require(agents[_agent].isActive, "Agent is not active");
        _;
    }

    constructor(address _paymentToken) {
        require(_paymentToken != address(0), "Invalid token address");
        paymentToken = IERC20(_paymentToken);
    }

    /**
     * @dev Register a new agent wallet
     * @param _agent The address of the agent
     * @param _initialSpendingLimit The max the agent can spend
     */
    function registerAgent(address _agent, uint256 _initialSpendingLimit) external {
        require(_agent != address(0), "Invalid agent address");
        // A registrant may only claim ownership of itself — otherwise a
        // front-runner owns the record for any agent address it watches
        // and can withdraw tokens deposited for it (#1101).
        require(msg.sender == _agent, "Only the agent can register itself");
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
     * @dev Register an agent whose spending policy is controlled by a distinct owner (Phase C1).
     * The agent EOA executes micro-txs; the policy owner manages limits and allowlists.
     */
    function registerManagedAgent(
        address _agent,
        uint256 _lifetimeLimit,
        uint256 _periodLimit,
        uint256 _periodDurationSeconds_
    ) external {
        require(_agent != address(0), "Invalid agent address");
        require(agents[_agent].owner == address(0), "Agent already registered");
        agentPolicyOwner[_agent] = msg.sender;
        agents[_agent] = Agent({
            owner: _agent,
            balance: 0,
            spendingLimit: _lifetimeLimit,
            totalSpent: 0,
            isActive: true
        });
        periodSpendLimit[_agent] = _periodLimit;
        periodDurationSeconds[_agent] = _periodDurationSeconds_;
        if (_periodLimit > 0 && _periodDurationSeconds_ > 0) {
            periodWindowEnd[_agent] = block.timestamp + _periodDurationSeconds_;
        }
        emit ManagedAgentRegistered(_agent, msg.sender);
        emit AgentRegistered(_agent, msg.sender);
    }

    function setRecipientAllowed(address _agent, address _recipient, bool _allowed) external onlyPolicyOwner(_agent) {
        require(_recipient != address(0), "Invalid recipient");
        allowedRecipient[_agent][_recipient] = _allowed;
        emit RecipientAllowlistUpdated(_agent, _recipient, _allowed);
    }

    function setAllowlistRequired(address _agent, bool _required) external onlyPolicyOwner(_agent) {
        allowlistRequired[_agent] = _required;
        emit AllowlistEnforcementUpdated(_agent, _required);
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
        paymentToken.safeTransferFrom(msg.sender, address(this), _amount);

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
        paymentToken.safeTransfer(msg.sender, _amount);

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
        require(bytes(_purpose).length <= MAX_PURPOSE_BYTES, "Purpose too long");

        Agent storage agent = agents[msg.sender];

        require(agent.balance >= _amount, "Insufficient balance");
        require(agent.totalSpent + _amount <= agent.spendingLimit, "Spending limit exceeded");
        if (allowlistRequired[msg.sender]) {
            require(allowedRecipient[msg.sender][_recipient], "Recipient not allowed");
        }
        if (periodSpendLimit[msg.sender] > 0) {
            _rollPeriod(msg.sender);
            require(periodSpent[msg.sender] + _amount <= periodSpendLimit[msg.sender], "Period limit exceeded");
            periodSpent[msg.sender] += _amount;
        }

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
        paymentToken.safeTransfer(_recipient, _amount);

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
