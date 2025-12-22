// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "./Groth16Verifier.sol";

/**
 * @title ZKReceiptVerifier
 * @dev Contract for verifying zero-knowledge proofs for receipt attestation
 */
contract ZKReceiptVerifier is Groth16Verifier {
    
    // Events
    event ProofVerified(
        bytes32 indexed receiptHash,
        uint256 settlementAmount,
        uint256 timestamp,
        address indexed verifier
    );
    
    event ProofVerificationFailed(
        bytes32 indexed receiptHash,
        string reason
    );
    
    // Mapping to prevent double-spending
    mapping(bytes32 => bool) public verifiedReceipts;
    
    // Mapping for authorized verifiers
    mapping(address => bool) public authorizedVerifiers;
    
    // Address of the settlement contract
    address public settlementContract;
    
    // Circuit version
    uint256 public constant CIRCUIT_VERSION = 1;
    
    // Minimum settlement amount
    uint256 public constant MIN_SETTLEMENT_AMOUNT = 0;
    
    // Maximum timestamp drift (in seconds)
    uint256 public constant MAX_TIMESTAMP_DRIFT = 3600; // 1 hour
    
    modifier onlyAuthorized() {
        require(
            authorizedVerifiers[msg.sender] || 
            msg.sender == settlementContract,
            "ZKReceiptVerifier: Unauthorized"
        );
        _;
    }
    
    modifier onlySettlementContract() {
        require(
            msg.sender == settlementContract,
            "ZKReceiptVerifier: Only settlement contract"
        );
        _;
    }
    
    constructor() {
        // Deployer is initially authorized
        authorizedVerifiers[msg.sender] = true;
    }
    
    /**
     * @dev Verify a ZK proof for receipt attestation
     * @param a Proof parameter a
     * @param b Proof parameter b
     * @param c Proof parameter c
     * @param publicSignals Public signals from the proof
     * @return valid Whether the proof is valid
     */
    function verifyProof(
        uint[2] calldata a,
        uint[2][2] calldata b,
        uint[2] calldata c,
        uint[2] calldata publicSignals
    ) external view returns (bool valid) {
        // Extract public signals
        bytes32 receiptHash = bytes32(publicSignals[0]);
        uint256 settlementAmount = publicSignals[1];
        uint256 timestamp = publicSignals[2];
        
        // Validate public signals
        if (!_validatePublicSignals(receiptHash, settlementAmount, timestamp)) {
            return false;
        }
        
        // Verify the proof using Groth16
        return this.verifyProof(a, b, c, publicSignals);
    }
    
    /**
     * @dev Verify and record a proof for settlement
     * @param a Proof parameter a
     * @param b Proof parameter b
     * @param c Proof parameter c
     * @param publicSignals Public signals from the proof
     * @return success Whether verification succeeded
     */
    function verifyAndRecord(
        uint[2] calldata a,
        uint[2][2] calldata b,
        uint[2] calldata c,
        uint[2] calldata publicSignals
    ) external onlyAuthorized returns (bool success) {
        // Extract public signals
        bytes32 receiptHash = bytes32(publicSignals[0]);
        uint256 settlementAmount = publicSignals[1];
        uint256 timestamp = publicSignals[2];
        
        // Check if receipt already verified
        if (verifiedReceipts[receiptHash]) {
            emit ProofVerificationFailed(receiptHash, "Receipt already verified");
            return false;
        }
        
        // Validate public signals
        if (!_validatePublicSignals(receiptHash, settlementAmount, timestamp)) {
            emit ProofVerificationFailed(receiptHash, "Invalid public signals");
            return false;
        }
        
        // Verify the proof
        bool valid = this.verifyProof(a, b, c, publicSignals);
        
        if (valid) {
            // Mark as verified
            verifiedReceipts[receiptHash] = true;
            
            // Emit event
            emit ProofVerified(receiptHash, settlementAmount, timestamp, msg.sender);
            
            return true;
        } else {
            emit ProofVerificationFailed(receiptHash, "Invalid proof");
            return false;
        }
    }
    
    /**
     * @dev Validate public signals
     * @param receiptHash Hash of the receipt
     * @param settlementAmount Amount to settle
     * @param timestamp Receipt timestamp
     * @return valid Whether the signals are valid
     */
    function _validatePublicSignals(
        bytes32 receiptHash,
        uint256 settlementAmount,
        uint256 timestamp
    ) internal view returns (bool valid) {
        // Check minimum amount
        if (settlementAmount < MIN_SETTLEMENT_AMOUNT) {
            return false;
        }
        
        // Check timestamp is not too far in the future
        if (timestamp > block.timestamp + MAX_TIMESTAMP_DRIFT) {
            return false;
        }
        
        // Check timestamp is not too old (optional)
        if (timestamp < block.timestamp - 86400) { // 24 hours ago
            return false;
        }
        
        // Check receipt hash is not zero
        if (receiptHash == bytes32(0)) {
            return false;
        }
        
        return true;
    }
    
    /**
     * @dev Set the settlement contract address
     * @param _settlementContract Address of the settlement contract
     */
    function setSettlementContract(address _settlementContract) external {
        require(msg.sender == authorizedVerifiers[msg.sender], "ZKReceiptVerifier: Unauthorized");
        settlementContract = _settlementContract;
    }
    
    /**
     * @dev Add an authorized verifier
     * @param verifier Address to authorize
     */
    function addAuthorizedVerifier(address verifier) external {
        require(msg.sender == authorizedVerifiers[msg.sender], "ZKReceiptVerifier: Unauthorized");
        authorizedVerifiers[verifier] = true;
    }
    
    /**
     * @dev Remove an authorized verifier
     * @param verifier Address to remove
     */
    function removeAuthorizedVerifier(address verifier) external {
        require(msg.sender == authorizedVerifiers[msg.sender], "ZKReceiptVerifier: Unauthorized");
        authorizedVerifiers[verifier] = false;
    }
    
    /**
     * @dev Check if a receipt has been verified
     * @param receiptHash Hash of the receipt
     * @return verified Whether the receipt has been verified
     */
    function isReceiptVerified(bytes32 receiptHash) external view returns (bool verified) {
        return verifiedReceipts[receiptHash];
    }
    
    /**
     * @dev Batch verify multiple proofs
     * @param proofs Array of proof data
     * @return results Array of verification results
     */
    function batchVerify(
        BatchProof[] calldata proofs
    ) external view returns (bool[] memory results) {
        results = new bool[](proofs.length);
        
        for (uint256 i = 0; i < proofs.length; i++) {
            results[i] = this.verifyProof(
                proofs[i].a,
                proofs[i].b,
                proofs[i].c,
                proofs[i].publicSignals
            );
        }
    }
    
    // Struct for batch verification
    struct BatchProof {
        uint[2] a;
        uint[2][2] b;
        uint[2] c;
        uint[2] publicSignals;
    }
}
