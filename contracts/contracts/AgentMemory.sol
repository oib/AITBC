// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

contract AgentMemory is Ownable, ReentrancyGuard {
    struct MemoryAnchor {
        string cid;
        uint256 timestamp;
        uint256 version;
    }

    mapping(address => MemoryAnchor[]) public agentMemories;
    mapping(address => uint256) public agentMemoryVersions;

    event MemoryAnchored(address indexed agent, string cid, uint256 version, uint256 timestamp);

    function anchorMemory(string calldata _cid) external nonReentrant {
        require(bytes(_cid).length > 0, "Invalid CID");
        
        uint256 nextVersion = agentMemoryVersions[msg.sender] + 1;
        
        agentMemories[msg.sender].push(MemoryAnchor({
            cid: _cid,
            timestamp: block.timestamp,
            version: nextVersion
        }));
        
        agentMemoryVersions[msg.sender] = nextVersion;
        
        emit MemoryAnchored(msg.sender, _cid, nextVersion, block.timestamp);
    }

    function getLatestMemory(address _agent) external view returns (MemoryAnchor memory) {
        require(agentMemories[_agent].length > 0, "No memory anchored");
        return agentMemories[_agent][agentMemories[_agent].length - 1];
    }
}
