// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

contract KnowledgeGraphMarket is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public aitbcToken;
    uint256 public graphCounter;
    uint256 public platformFeePercentage = 250; // 2.5%

    struct KnowledgeGraph {
        uint256 id;
        address creator;
        string cid;
        uint256 price;
        uint256 totalSales;
        bool isActive;
    }

    mapping(uint256 => KnowledgeGraph) public graphs;
    mapping(uint256 => mapping(address => bool)) public hasPurchased;

    event GraphListed(uint256 indexed id, address indexed creator, string cid, uint256 price);
    event GraphPurchased(uint256 indexed id, address indexed buyer, uint256 price);

    constructor(address _aitbcToken) {
        aitbcToken = IERC20(_aitbcToken);
    }

    function listGraph(string calldata _cid, uint256 _price) external returns (uint256) {
        uint256 id = graphCounter++;
        graphs[id] = KnowledgeGraph(id, msg.sender, _cid, _price, 0, true);
        emit GraphListed(id, msg.sender, _cid, _price);
        return id;
    }

    function purchaseGraph(uint256 _id) external nonReentrant {
        KnowledgeGraph storage graph = graphs[_id];
        require(graph.isActive, "Graph inactive");
        require(!hasPurchased[_id][msg.sender], "Already purchased");

        uint256 fee = (graph.price * platformFeePercentage) / 10000;
        uint256 creatorAmount = graph.price - fee;

        aitbcToken.safeTransferFrom(msg.sender, address(this), graph.price);
        aitbcToken.safeTransfer(graph.creator, creatorAmount);

        graph.totalSales++;
        hasPurchased[_id][msg.sender] = true;

        emit GraphPurchased(_id, msg.sender, graph.price);
    }
}
