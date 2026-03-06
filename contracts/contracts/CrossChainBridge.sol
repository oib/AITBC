// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";

/**
 * @title CrossChainBridge
 * @dev Secure cross-chain asset transfer protocol with ZK proof validation
 * @notice Enables bridging of assets between different blockchain networks
 */
contract CrossChainBridge is Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;
    using ECDSA for bytes32;

    // Constants
    uint256 public constant BRIDGE_FEE_PERCENTAGE = 50; // 0.5% bridge fee
    uint256 public constant BASIS_POINTS = 10000;
    uint256 public constant MAX_FEE = 500; // Maximum 5% fee
    uint256 public constant MIN_CONFIRMATIONS = 3;
    uint256 public constant BRIDGE_TIMEOUT = 24 hours;
    uint256 public constant MAX_BRIDGE_AMOUNT = 1000000 * 1e18; // Max 1M tokens per bridge

    // Enums
    enum BridgeStatus { PENDING, CONFIRMED, COMPLETED, FAILED, CANCELLED }
    enum ChainType { ETHEREUM, POLYGON, BSC, ARBITRUM, OPTIMISM, AVALANCHE }

    // Structs
    struct BridgeRequest {
        uint256 requestId;
        address sourceToken;
        address targetToken;
        uint256 amount;
        uint256 sourceChainId;
        uint256 targetChainId;
        address recipient;
        address sender;
        uint256 fee;
        bytes32 lockTxHash;
        bytes32 unlockTxHash;
        BridgeStatus status;
        uint256 createdAt;
        uint256 confirmedAt;
        uint256 completedAt;
        uint256 confirmations;
        mapping(address => bool) hasConfirmed;
    }

    struct SupportedToken {
        address tokenAddress;
        bool isActive;
        uint256 bridgeLimit;
        uint256 feePercentage;
        bool requiresWhitelist;
    }

    struct ChainConfig {
        uint256 chainId;
        ChainType chainType;
        string name;
        bool isActive;
        address bridgeContract;
        uint256 minConfirmations;
        uint256 avgBlockTime;
    }

    struct Validator {
        address validatorAddress;
        bool isActive;
        uint256 weight;
        uint256 lastValidation;
        uint256 totalValidations;
    }

    // State variables
    uint256 public requestCounter;
    uint256 public totalBridgedAmount;
    uint256 public totalFeesCollected;
    address public feeRecipient;
    bytes32 public merkleRoot;

    // Mappings
    mapping(uint256 => BridgeRequest) public bridgeRequests;
    mapping(address => SupportedToken) public supportedTokens;
    mapping(uint256 => ChainConfig) public supportedChains;
    mapping(address => Validator) public validators;
    mapping(uint256 => address[]) public chainValidators;
    mapping(bytes32 => bool) public processedTxHashes;
    mapping(address => uint256[]) public userBridgeHistory;

    // Arrays
    address[] public activeValidators;
    uint256[] public supportedChainIds;
    address[] public supportedTokenAddresses;

    // Events
    event BridgeInitiated(
        uint256 indexed requestId,
        address indexed sender,
        address indexed recipient,
        address sourceToken,
        uint256 amount,
        uint256 sourceChainId,
        uint256 targetChainId
    );
    event BridgeConfirmed(uint256 indexed requestId, address indexed validator, bytes32 lockTxHash);
    event BridgeCompleted(uint256 indexed requestId, bytes32 unlockTxHash);
    event BridgeFailed(uint256 indexed requestId, string reason);
    event BridgeCancelled(uint256 indexed requestId);
    event ValidatorAdded(address indexed validator, uint256 weight);
    event ValidatorRemoved(address indexed validator);
    event TokenSupported(address indexed token, uint256 bridgeLimit, uint256 fee);
    event ChainSupported(uint256 indexed chainId, string name, ChainType chainType);

    // Modifiers
    modifier onlyActiveValidator() {
        require(validators[msg.sender].isActive, "Not an active validator");
        _;
    }

    modifier validRequest(uint256 requestId) {
        require(requestId > 0 && requestId <= requestCounter, "Invalid request ID");
        _;
    }

    modifier supportedToken(address token) {
        require(supportedTokens[token].isActive, "Token not supported");
        _;
    }

    modifier supportedChain(uint256 chainId) {
        require(supportedChains[chainId].isActive, "Chain not supported");
        _;
    }

    modifier withinBridgeLimit(address token, uint256 amount) {
        require(amount <= supportedTokens[token].bridgeLimit, "Amount exceeds bridge limit");
        _;
    }

    constructor(address _feeRecipient) {
        feeRecipient = _feeRecipient;
        
        // Initialize with Ethereum mainnet
        _addChain(1, ChainType.ETHEREUM, "Ethereum", true, address(0), 12, 12);
    }

    /**
     * @dev Initiates a cross-chain bridge transfer
     * @param sourceToken Address of the source token
     * @param targetToken Address of the target token
     * @param amount Amount to bridge
     * @param targetChainId Target chain ID
     * @param recipient Recipient address on target chain
     * @return requestId The bridge request ID
     */
    function initiateBridge(
        address sourceToken,
        address targetToken,
        uint256 amount,
        uint256 targetChainId,
        address recipient
    ) 
        external 
        nonReentrant 
        whenNotPaused
        supportedToken(sourceToken)
        supportedChain(targetChainId)
        withinBridgeLimit(sourceToken, amount)
        returns (uint256 requestId) 
    {
        require(sourceToken != address(0), "Invalid source token");
        require(targetToken != address(0), "Invalid target token");
        require(recipient != address(0), "Invalid recipient");
        require(amount > 0, "Amount must be greater than 0");
        require(targetChainId != block.chainid, "Same chain bridging not allowed");

        // Calculate bridge fee
        uint256 fee = (amount * supportedTokens[sourceToken].feePercentage) / BASIS_POINTS;
        uint256 totalAmount = amount + fee;

        // Transfer tokens to contract
        IERC20(sourceToken).safeTransferFrom(msg.sender, address(this), totalAmount);

        // Create bridge request
        requestCounter++;
        requestId = requestCounter;

        BridgeRequest storage request = bridgeRequests[requestId];
        request.requestId = requestId;
        request.sourceToken = sourceToken;
        request.targetToken = targetToken;
        request.amount = amount;
        request.sourceChainId = block.chainid;
        request.targetChainId = targetChainId;
        request.recipient = recipient;
        request.sender = msg.sender;
        request.fee = fee;
        request.status = BridgeStatus.PENDING;
        request.createdAt = block.timestamp;

        // Update statistics
        totalBridgedAmount += amount;
        totalFeesCollected += fee;
        userBridgeHistory[msg.sender].push(requestId);

        // Transfer fee to fee recipient
        if (fee > 0) {
            IERC20(sourceToken).safeTransfer(feeRecipient, fee);
        }

        emit BridgeInitiated(
            requestId,
            msg.sender,
            recipient,
            sourceToken,
            amount,
            block.chainid,
            targetChainId
        );

        return requestId;
    }

    /**
     * @dev Confirms a bridge request by a validator
     * @param requestId The bridge request ID
     * @param lockTxHash The transaction hash of the lock transaction
     * @param signature Validator signature
     */
    function confirmBridge(
        uint256 requestId,
        bytes32 lockTxHash,
        bytes memory signature
    ) 
        external 
        onlyActiveValidator
        validRequest(requestId)
    {
        BridgeRequest storage request = bridgeRequests[requestId];
        
        require(request.status == BridgeStatus.PENDING, "Request not pending");
        require(!request.hasConfirmed[msg.sender], "Already confirmed");
        require(block.timestamp <= request.createdAt + BRIDGE_TIMEOUT, "Bridge request expired");

        // Verify signature
        bytes32 messageHash = keccak256(abi.encodePacked(requestId, lockTxHash, block.chainid));
        require(_verifySignature(messageHash, signature, msg.sender), "Invalid signature");

        // Record confirmation
        request.hasConfirmed[msg.sender] = true;
        request.confirmations++;
        request.lockTxHash = lockTxHash;
        validators[msg.sender].lastValidation = block.timestamp;
        validators[msg.sender].totalValidations++;

        // Check if we have enough confirmations
        uint256 requiredConfirmations = _getRequiredConfirmations(request.sourceChainId);
        if (request.confirmations >= requiredConfirmations) {
            request.status = BridgeStatus.CONFIRMED;
            request.confirmedAt = block.timestamp;
        }

        emit BridgeConfirmed(requestId, msg.sender, lockTxHash);
    }

    /**
     * @dev Completes a bridge request on the target chain
     * @param requestId The bridge request ID
     * @param unlockTxHash The transaction hash of the unlock transaction
     * @param proof Merkle proof for verification
     */
    function completeBridge(
        uint256 requestId,
        bytes32 unlockTxHash,
        bytes32[] calldata proof
    ) 
        external 
        nonReentrant 
        whenNotPaused
        validRequest(requestId)
    {
        BridgeRequest storage request = bridgeRequests[requestId];
        
        require(request.status == BridgeStatus.CONFIRMED, "Request not confirmed");
        require(block.chainid == request.targetChainId, "Wrong chain");
        require(!processedTxHashes[unlockTxHash], "Transaction already processed");

        // Verify Merkle proof
        bytes32 leaf = keccak256(abi.encodePacked(requestId, request.recipient, request.amount));
        require(MerkleProof.verify(proof, merkleRoot, leaf), "Invalid Merkle proof");

        // Mark transaction as processed
        processedTxHashes[unlockTxHash] = true;
        request.unlockTxHash = unlockTxHash;
        request.status = BridgeStatus.COMPLETED;
        request.completedAt = block.timestamp;

        // Transfer tokens to recipient
        IERC20(request.targetToken).safeTransfer(request.recipient, request.amount);

        emit BridgeCompleted(requestId, unlockTxHash);
    }

    /**
     * @dev Cancels a bridge request
     * @param requestId The bridge request ID
     * @param reason Reason for cancellation
     */
    function cancelBridge(uint256 requestId, string memory reason) 
        external 
        nonReentrant 
        validRequest(requestId) 
    {
        BridgeRequest storage request = bridgeRequests[requestId];
        
        require(request.status == BridgeStatus.PENDING, "Request not pending");
        require(
            msg.sender == request.sender || msg.sender == owner(),
            "Not authorized to cancel"
        );
        require(block.timestamp > request.createdAt + BRIDGE_TIMEOUT, "Bridge not expired");

        // Refund tokens to sender
        uint256 refundAmount = request.amount + request.fee;
        IERC20(request.sourceToken).safeTransfer(request.sender, refundAmount);

        // Update status
        request.status = BridgeStatus.CANCELLED;

        emit BridgeCancelled(requestId);
        emit BridgeFailed(requestId, reason);
    }

    /**
     * @dev Gets bridge request details
     * @param requestId The bridge request ID
     * @return request The bridge request details
     */
    function getBridgeRequest(uint256 requestId) 
        external 
        view 
        validRequest(requestId)
        returns (BridgeRequest memory) 
    {
        return bridgeRequests[requestId];
    }

    /**
     * @dev Gets user's bridge history
     * @param user The user address
     * @return requestIds Array of bridge request IDs
     */
    function getUserBridgeHistory(address user) 
        external 
        view 
        returns (uint256[] memory requestIds) 
    {
        return userBridgeHistory[user];
    }

    /**
     * @dev Validates a bridge request signature
     * @param requestId The bridge request ID
     * @param lockTxHash The lock transaction hash
     * @param signature The signature to validate
     * @return isValid Whether the signature is valid
     */
    function validateBridgeRequest(uint256 requestId, bytes32 lockTxHash, bytes memory signature) 
        external 
        view 
        returns (bool isValid) 
    {
        bytes32 messageHash = keccak256(abi.encodePacked(requestId, lockTxHash, block.chainid));
        address recoveredAddress = messageHash.recover(signature);
        return validators[recoveredAddress].isActive;
    }

    // Admin functions

    /**
     * @dev Adds support for a new token
     * @param tokenAddress The token address
     * @param bridgeLimit Maximum bridge amount
     * @param feePercentage Bridge fee percentage
     * @param requiresWhitelist Whether whitelist is required
     */
    function addSupportedToken(
        address tokenAddress,
        uint256 bridgeLimit,
        uint256 feePercentage,
        bool requiresWhitelist
    ) external onlyOwner {
        require(tokenAddress != address(0), "Invalid token address");
        require(feePercentage <= MAX_FEE, "Fee too high");

        supportedTokens[tokenAddress] = SupportedToken({
            tokenAddress: tokenAddress,
            isActive: true,
            bridgeLimit: bridgeLimit,
            feePercentage: feePercentage,
            requiresWhitelist: requiresWhitelist
        });

        supportedTokenAddresses.push(tokenAddress);
        emit TokenSupported(tokenAddress, bridgeLimit, feePercentage);
    }

    /**
     * @dev Adds support for a new blockchain
     * @param chainId The chain ID
     * @param chainType The chain type
     * @param name The chain name
     * @param bridgeContract The bridge contract address on that chain
     * @param minConfirmations Minimum confirmations required
     * @param avgBlockTime Average block time in seconds
     */
    function addSupportedChain(
        uint256 chainId,
        ChainType chainType,
        string memory name,
        address bridgeContract,
        uint256 minConfirmations,
        uint256 avgBlockTime
    ) external onlyOwner {
        require(chainId > 0, "Invalid chain ID");
        require(chainId != block.chainid, "Cannot add current chain");

        supportedChains[chainId] = ChainConfig({
            chainId: chainId,
            chainType: chainType,
            name: name,
            isActive: true,
            bridgeContract: bridgeContract,
            minConfirmations: minConfirmations,
            avgBlockTime: avgBlockTime
        });

        supportedChainIds.push(chainId);
        emit ChainSupported(chainId, name, chainType);
    }

    /**
     * @dev Adds a new validator
     * @param validatorAddress The validator address
     * @param weight The validator weight
     */
    function addValidator(address validatorAddress, uint256 weight) external onlyOwner {
        require(validatorAddress != address(0), "Invalid validator address");
        require(!validators[validatorAddress].isActive, "Validator already exists");

        validators[validatorAddress] = Validator({
            validatorAddress: validatorAddress,
            isActive: true,
            weight: weight,
            lastValidation: 0,
            totalValidations: 0
        });

        activeValidators.push(validatorAddress);
        emit ValidatorAdded(validatorAddress, weight);
    }

    /**
     * @dev Removes a validator
     * @param validatorAddress The validator address
     */
    function removeValidator(address validatorAddress) external onlyOwner {
        require(validators[validatorAddress].isActive, "Validator not active");

        validators[validatorAddress].isActive = false;
        
        // Remove from active validators array
        for (uint i = 0; i < activeValidators.length; i++) {
            if (activeValidators[i] == validatorAddress) {
                activeValidators[i] = activeValidators[activeValidators.length - 1];
                activeValidators.pop();
                break;
            }
        }

        emit ValidatorRemoved(validatorAddress);
    }

    /**
     * @dev Updates the Merkle root for transaction verification
     * @param newMerkleRoot The new Merkle root
     */
    function updateMerkleRoot(bytes32 newMerkleRoot) external onlyOwner {
        merkleRoot = newMerkleRoot;
    }

    /**
     * @dev Sets the fee recipient address
     * @param newFeeRecipient The new fee recipient
     */
    function setFeeRecipient(address newFeeRecipient) external onlyOwner {
        require(newFeeRecipient != address(0), "Invalid address");
        feeRecipient = newFeeRecipient;
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    // Internal functions

    function _verifySignature(
        bytes32 messageHash,
        bytes memory signature,
        address signer
    ) internal pure returns (bool) {
        bytes32 ethSignedMessageHash = keccak256(
            abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash)
        );
        return ethSignedMessageHash.recover(signature) == signer;
    }

    function _getRequiredConfirmations(uint256 chainId) internal view returns (uint256) {
        ChainConfig storage chain = supportedChains[chainId];
        return chain.minConfirmations > 0 ? chain.minConfirmations : MIN_CONFIRMATIONS;
    }

    function _addChain(
        uint256 chainId,
        ChainType chainType,
        string memory name,
        bool isActive,
        address bridgeContract,
        uint256 minConfirmations,
        uint256 avgBlockTime
    ) internal {
        supportedChains[chainId] = ChainConfig({
            chainId: chainId,
            chainType: chainType,
            name: name,
            isActive: isActive,
            bridgeContract: bridgeContract,
            minConfirmations: minConfirmations,
            avgBlockTime: avgBlockTime
        });

        supportedChainIds.push(chainId);
        emit ChainSupported(chainId, name, chainType);
    }

    // Emergency functions

    function emergencyWithdraw(address token, uint256 amount) external onlyOwner {
        IERC20(token).safeTransfer(owner(), amount);
    }

    function emergencyPause() external onlyOwner {
        _pause();
    }
}
