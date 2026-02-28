// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "./ZKReceiptVerifier.sol";

contract AgentMemory is Ownable, ReentrancyGuard {
    ZKReceiptVerifier public zkVerifier;

    struct MemoryAnchor {
        string cid;
        string memoryType; // e.g., "vector_db", "knowledge_graph"
        bytes32 zkProofHash;
        bool isEncrypted;
        uint256 timestamp;
        uint256 version;
    }

    mapping(address => MemoryAnchor[]) public agentMemories;
    mapping(address => uint256) public agentMemoryVersions;

    event MemoryAnchored(
        address indexed agent, 
        string cid, 
        string memoryType,
        bytes32 zkProofHash,
        bool isEncrypted,
        uint256 version, 
        uint256 timestamp
    );

    constructor(address _zkVerifierAddress) {
        if (_zkVerifierAddress != address(0)) {
            zkVerifier = ZKReceiptVerifier(_zkVerifierAddress);
        }
    }

    function updateZKVerifier(address _newVerifier) external onlyOwner {
        require(_newVerifier != address(0), "Invalid address");
        zkVerifier = ZKReceiptVerifier(_newVerifier);
    }

    function anchorMemory(
        string calldata _cid,
        string calldata _memoryType,
        bytes32 _zkProofHash,
        bytes calldata _proof,
        bool _isEncrypted
    ) external nonReentrant {
        require(bytes(_cid).length > 0, "Invalid CID");
        require(bytes(_memoryType).length > 0, "Invalid memory type");

        // Verify ZK Proof if provided and verifier is set
        if (_zkProofHash != bytes32(0) && address(zkVerifier) != address(0)) {
            require(_proof.length > 0, "Proof required for hash");
            bool isValid = zkVerifier.verifyReceipt(_proof, _zkProofHash);
            require(isValid, "ZK Proof verification failed");
        }
        
        uint256 nextVersion = agentMemoryVersions[msg.sender] + 1;
        
        agentMemories[msg.sender].push(MemoryAnchor({
            cid: _cid,
            memoryType: _memoryType,
            zkProofHash: _zkProofHash,
            isEncrypted: _isEncrypted,
            timestamp: block.timestamp,
            version: nextVersion
        }));
        
        agentMemoryVersions[msg.sender] = nextVersion;
        
        emit MemoryAnchored(
            msg.sender, 
            _cid, 
            _memoryType,
            _zkProofHash,
            _isEncrypted,
            nextVersion, 
            block.timestamp
        );
    }

    function getLatestMemory(address _agent) external view returns (MemoryAnchor memory) {
        require(agentMemories[_agent].length > 0, "No memory anchored");
        return agentMemories[_agent][agentMemories[_agent].length - 1];
    }
    
    function getMemoryCount(address _agent) external view returns (uint256) {
        return agentMemories[_agent].length;
    }
}
