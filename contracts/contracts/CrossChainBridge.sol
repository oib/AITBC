// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";

/**
 * @title CrossChainBridge
 * @dev Secure cross-chain asset transfer protocol with ZK proof validation
 * @notice Enables bridging of assets between different blockchain networks
 */
contract CrossChainBridge is Ownable, ReentrancyGuard, Pausable, EIP712 {
    using SafeERC20 for IERC20;
    using ECDSA for bytes32;

    // Constants
    uint256 public constant BRIDGE_FEE_PERCENTAGE = 50; // 0.5% bridge fee
    uint256 public constant BASIS_POINTS = 10000;
    uint256 public constant MAX_FEE = 500; // Maximum 5% fee
    // Quorum floor (#795): a bridge request can never require fewer than
    // MIN_QUORUM active confirmations, and removeValidator cannot shrink the
    // live set below it, so the floor is reachable by construction.
    uint256 public constant MIN_QUORUM = 2;
    // Cap on the validator set: confirm/finalize loop over activeValidators,
    // so the set size bounds their gas.
    uint256 public constant MAX_VALIDATORS = 16;
    uint256 public constant BRIDGE_TIMEOUT = 24 hours;
    uint256 public constant COMPLETION_TIMEOUT = 24 hours;
    uint256 public constant MAX_BRIDGE_AMOUNT = 1000000 * 1e18; // Max 1M tokens per bridge

    // EIP-712 typehash for validator bridge confirmations (#1463). The signed
    // struct binds requestId + lockTxHash; the domain separator binds the
    // digest to this chain (chainid) and this deployment (verifyingContract =
    // address(this)). The previous scheme hashed
    // keccak256(abi.encodePacked(requestId, lockTxHash, block.chainid)) under
    // an "Ethereum Signed Message" prefix -- it carried chainid but NOT the
    // contract address, so a validator signature minted for one bridge
    // deployment replayed on any other deployment of the same contract on the
    // same chain (requestIds are per-contract counters starting at 1, so
    // collisions are trivial -- e.g. across the #795 redeploys).
    //
    // DEPLOYMENT NOTE: this changes the signed digest format. Every existing
    // deployment (e.g. the live Sepolia bridge) keeps verifying the OLD format
    // until it is replaced; validators must sign the EIP-712 digest produced
    // by confirmationDigest() and the new bytecode must be deployed for the
    // change to take effect. Signatures in the old format are rejected.
    bytes32 private constant CONFIRMATION_TYPEHASH = keccak256(
        "BridgeConfirmation(uint256 requestId,bytes32 lockTxHash)"
    );

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
        // Quorum snapshot taken at initiation (#795): later validator-set or
        // policy changes never rewrite an in-flight request's threshold.
        uint256 requiredAtCreation;
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
        uint256 avgBlockTime;
    }

    struct Validator {
        address validatorAddress;
        bool isActive;
        // Reserved for a future weighted-quorum design (#795 residual):
        // stored and emitted but deliberately unused in confirmation
        // counting — confirmBridge tallies one vote per validator. Kept in
        // the API (param + ValidatorAdded event) for tooling stability; do
        // not read it as a live weight until weighted quorum ships.
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
    // internal: the flattened auto-getter exceeds the ABI encoder stack
    // (>=14 return values) without the optimizer; use getBridgeRequest().
    mapping(uint256 => BridgeRequest) internal bridgeRequests;
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
    event BridgeFinalized(uint256 indexed requestId);
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

    constructor(address _feeRecipient) EIP712("CrossChainBridge", "1") {
        feeRecipient = _feeRecipient;

        // Initialize with Ethereum mainnet
        _addChain(1, ChainType.ETHEREUM, "Ethereum", true, address(0), 12);
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
        require(amount <= MAX_BRIDGE_AMOUNT, "Amount exceeds max bridge amount");
        require(targetChainId != block.chainid, "Same chain bridging not allowed");
        // The floor guard keeps quorumFor(n) >= MIN_QUORUM satisfiable: with
        // fewer than MIN_QUORUM active validators no request could ever reach
        // quorum, so bridging is disabled rather than silently bricked.
        require(activeValidators.length >= MIN_QUORUM, "Not enough active validators");

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
        request.requiredAtCreation = quorumFor(activeValidators.length);

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

        // Verify signature. The digest is EIP-712 (#1463): the domain
        // separator binds it to this chain and this contract deployment, so
        // a signature minted for another bridge instance cannot be replayed
        // here even when requestId and lockTxHash collide.
        bytes32 digest = _confirmationDigest(requestId, lockTxHash);
        require(_verifySignature(digest, signature, msg.sender), "Invalid signature");

        // Record confirmation. Every confirmer must sign the SAME lock tx
        // hash — each signature binds (requestId, lockTxHash, chainId), so
        // without this check a quorum could be assembled across two
        // different lock hashes with the last confirmer's value winning
        // (#795 residual, BRIDGE-RESIDUALS-1).
        require(request.confirmations == 0 || request.lockTxHash == lockTxHash, "Confirmations must agree on lock tx hash");
        request.hasConfirmed[msg.sender] = true;
        request.confirmations++;
        request.lockTxHash = lockTxHash;
        validators[msg.sender].lastValidation = block.timestamp;
        validators[msg.sender].totalValidations++;

        // Check if quorum is met — the same check finalizeConfirmed uses, so
        // there is one definition of "quorum met" on this contract.
        if (_quorumMet(request)) {
            _setConfirmed(requestId, request);
        }

        emit BridgeConfirmed(requestId, msg.sender, lockTxHash);
    }

    /**
     * @dev Permissionlessly finalizes a PENDING request whose effective
     * confirmations already meet its snapshot quorum (#795). Covers the
     * stuck-request case: validators may stop confirming once the threshold
     * was already reachable (e.g. a validator was removed after confirming),
     * and no further confirmBridge call may ever arrive to flip the state.
     */
    function finalizeConfirmed(uint256 requestId)
        external
        nonReentrant
        validRequest(requestId)
    {
        BridgeRequest storage request = bridgeRequests[requestId];
        require(request.status == BridgeStatus.PENDING, "Request not pending");
        require(block.timestamp <= request.createdAt + BRIDGE_TIMEOUT, "Bridge request expired");
        require(_quorumMet(request), "Quorum not met");
        _setConfirmed(requestId, request);
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

        // PENDING cancels once the initiation timeout passes; CONFIRMED
        // expires on the source chain once the completion timeout passes —
        // the only exit for a confirmed-but-never-completed request (#795).
        // Caller is the request's sender or the owner. The refund is the
        // principal only (ruling 2C): the fee paid for the attempt.
        if (request.status == BridgeStatus.PENDING) {
            require(block.timestamp > request.createdAt + BRIDGE_TIMEOUT, "Bridge not expired");
        } else {
            require(request.status == BridgeStatus.CONFIRMED, "Request not pending or confirmed");
            require(block.timestamp > request.confirmedAt + COMPLETION_TIMEOUT, "Confirmed request not expired");
        }
        require(
            msg.sender == request.sender || msg.sender == owner(),
            "Not authorized to cancel"
        );

        // Refund tokens to sender. Only request.amount is still held: the fee was
        // already forwarded to feeRecipient in initiateBridge, so refunding
        // amount + fee would always revert on insufficient balance.
        uint256 refundAmount = request.amount;
        IERC20(request.sourceToken).safeTransfer(request.sender, refundAmount);

        // Update status
        request.status = BridgeStatus.CANCELLED;

        emit BridgeCancelled(requestId);
        emit BridgeFailed(requestId, reason);
    }

    /**
     * @dev Gets bridge request details
     * @param requestId The bridge request ID
     * @return sourceChainId The source chain ID
     * @return targetChainId The destination chain ID
     * @return sourceToken The source token address
     * @return amount The amount to bridge
     * @return recipient The recipient address
     * @return status The request status
     * @return createdAt The request timestamp
     */
    function getBridgeRequest(uint256 requestId)
        external
        view
        validRequest(requestId)
        returns (
            uint256 sourceChainId,
            uint256 targetChainId,
            address sourceToken,
            uint256 amount,
            address recipient,
            BridgeStatus status,
            uint256 createdAt,
            uint256 requiredAtCreation
        )
    {
        BridgeRequest storage request = bridgeRequests[requestId];
        return (
            request.sourceChainId,
            request.targetChainId,
            request.sourceToken,
            request.amount,
            request.recipient,
            request.status,
            request.createdAt,
            request.requiredAtCreation
        );
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
        bytes32 digest = _confirmationDigest(requestId, lockTxHash);
        address recoveredAddress = digest.recover(signature);
        return validators[recoveredAddress].isActive;
    }

    /**
     * @dev The exact digest validators must sign to confirm a bridge request
     * (#1463). Exposed so off-chain signer tooling can compute it without
     * re-implementing the EIP-712 domain separator: sign this 32-byte digest
     * directly (eth_sign / EIP-191 is NOT applied -- the digest is already
     * the EIP-712 \x19\x01 digest).
     * @param requestId The bridge request ID
     * @param lockTxHash The lock transaction hash
     * @return The EIP-712 digest to sign
     */
    function confirmationDigest(uint256 requestId, bytes32 lockTxHash)
        external
        view
        returns (bytes32)
    {
        return _confirmationDigest(requestId, lockTxHash);
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
     * @param avgBlockTime Average block time in seconds
     */
    function addSupportedChain(
        uint256 chainId,
        ChainType chainType,
        string memory name,
        address bridgeContract,
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
        // Bound the set: confirm/finalize cost grows linearly with it.
        require(activeValidators.length < MAX_VALIDATORS, "Validator cap reached");

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
        // Floor guard (#795): the live set can never shrink below MIN_QUORUM,
        // so quorumFor(n) >= MIN_QUORUM is always satisfiable and a request
        // can never be stranded below the floor.
        require(activeValidators.length - 1 >= MIN_QUORUM, "Validator floor reached");

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

    /**
     * @dev Quorum for a validator set of size n (#795, operator-approved
     * card 1B): exact BFT-style ⌊2n/3⌋+1 with a hard floor of MIN_QUORUM.
     * Truth table: n=2→2, 3→3, 4→3, 5→4, 6→5, 7→5, 8→6. Constants, not
     * owner-tunable — a Safe owner cannot configure below the floor, and
     * changing the policy means a redeploy (the safer failure mode).
     */
    function quorumFor(uint256 n) public pure returns (uint256) {
        uint256 q = (2 * n) / 3 + 1;
        return q > MIN_QUORUM ? q : MIN_QUORUM;
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    // Internal functions

    /// @dev EIP-712 struct hash + domain separator for a bridge confirmation.
    /// The domain carries name "CrossChainBridge", version "1", block.chainid
    /// and address(this), so the digest cannot be replayed on another chain
    /// or another deployment of this contract (#1463).
    function _confirmationDigest(uint256 requestId, bytes32 lockTxHash)
        internal
        view
        returns (bytes32)
    {
        bytes32 structHash = keccak256(
            abi.encode(CONFIRMATION_TYPEHASH, requestId, lockTxHash)
        );
        return _hashTypedDataV4(structHash);
    }

    /// @dev `digest` is already the EIP-712 digest -- recover directly, with
    /// no "\x19Ethereum Signed Message" prefix (that prefix belonged to the
    /// pre-#1463 format and is what made the digest chain/contract-agnostic).
    function _verifySignature(
        bytes32 digest,
        bytes memory signature,
        address signer
    ) internal pure returns (bool) {
        return digest.recover(signature) == signer;
    }

    /// @dev Effective confirmations = active validators that confirmed.
    /// A validator removed after confirming stops counting on pending
    /// requests immediately (gap 3, #795); the raw `confirmations` counter
    /// is kept only for the first-confirmer lock-hash check.
    function _effectiveConfirmations(BridgeRequest storage request)
        internal
        view
        returns (uint256 count)
    {
        for (uint256 i = 0; i < activeValidators.length; i++) {
            if (request.hasConfirmed[activeValidators[i]]) {
                count++;
            }
        }
    }

    /// @dev Threshold is the request's creation snapshot, clamped to the
    /// current live set (which the floor guard keeps >= MIN_QUORUM).
    function _quorumMet(BridgeRequest storage request) internal view returns (bool) {
        uint256 live = activeValidators.length;
        uint256 threshold = request.requiredAtCreation < live
            ? request.requiredAtCreation
            : live;
        return _effectiveConfirmations(request) >= threshold;
    }

    function _setConfirmed(uint256 requestId, BridgeRequest storage request) internal {
        request.status = BridgeStatus.CONFIRMED;
        request.confirmedAt = block.timestamp;
        emit BridgeFinalized(requestId);
    }

    function _addChain(
        uint256 chainId,
        ChainType chainType,
        string memory name,
        bool isActive,
        address bridgeContract,
        uint256 avgBlockTime
    ) internal {
        supportedChains[chainId] = ChainConfig({
            chainId: chainId,
            chainType: chainType,
            name: name,
            isActive: isActive,
            bridgeContract: bridgeContract,
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
