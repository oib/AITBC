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
        string metadataURI; // Added to match broader plan
        uint256 price;
        uint256 totalSales;
        bool isActive;
    }
    
    struct Purchase {
        uint256 graphId;
        address buyer;
        uint256 timestamp;
        string encryptedKey; // The decryption key encrypted with the buyer's public key
    }

    mapping(uint256 => KnowledgeGraph) public graphs;
    mapping(uint256 => mapping(address => bool)) public hasPurchased;
    
    // graphId => array of purchases
    mapping(uint256 => Purchase[]) public purchases;

    event GraphListed(uint256 indexed id, address indexed creator, string cid, string metadataURI, uint256 price);
    event GraphUpdated(uint256 indexed id, uint256 newPrice, bool isActive);
    event GraphPurchased(uint256 indexed id, address indexed buyer, uint256 price);
    event KeyDelivered(uint256 indexed id, address indexed buyer, string encryptedKey);

    constructor(address _aitbcToken) {
        aitbcToken = IERC20(_aitbcToken);
    }

    function listGraph(string calldata _cid, string calldata _metadataURI, uint256 _price) external returns (uint256) {
        uint256 id = graphCounter++;
        graphs[id] = KnowledgeGraph(id, msg.sender, _cid, _metadataURI, _price, 0, true);
        emit GraphListed(id, msg.sender, _cid, _metadataURI, _price);
        return id;
    }

    function updateGraph(uint256 _id, uint256 _newPrice, bool _isActive) external {
        KnowledgeGraph storage graph = graphs[_id];
        require(graph.creator == msg.sender, "Not creator");
        
        graph.price = _newPrice;
        graph.isActive = _isActive;
        
        emit GraphUpdated(_id, _newPrice, _isActive);
    }

    function purchaseGraph(uint256 _id) external nonReentrant {
        KnowledgeGraph storage graph = graphs[_id];
        require(graph.isActive, "Graph inactive");
        require(!hasPurchased[_id][msg.sender], "Already purchased");
        require(graph.creator != msg.sender, "Cannot buy own graph");

        uint256 fee = (graph.price * platformFeePercentage) / 10000;
        uint256 creatorAmount = graph.price - fee;

        aitbcToken.safeTransferFrom(msg.sender, address(this), fee); // Treasury
        aitbcToken.safeTransferFrom(msg.sender, graph.creator, creatorAmount);

        graph.totalSales++;
        hasPurchased[_id][msg.sender] = true;
        
        purchases[_id].push(Purchase({
            graphId: _id,
            buyer: msg.sender,
            timestamp: block.timestamp,
            encryptedKey: ""
        }));

        emit GraphPurchased(_id, msg.sender, graph.price);
    }

    function deliverDecryptionKey(uint256 _id, address _buyer, string calldata _encryptedKey) external {
        KnowledgeGraph storage graph = graphs[_id];
        require(graph.creator == msg.sender, "Not creator");
        require(hasPurchased[_id][_buyer], "Buyer has not purchased");
        
        Purchase[] storage graphPurchases = purchases[_id];
        bool found = false;
        for (uint i = 0; i < graphPurchases.length; i++) {
            if (graphPurchases[i].buyer == _buyer) {
                graphPurchases[i].encryptedKey = _encryptedKey;
                found = true;
                break;
            }
        }
        require(found, "Purchase record not found");

        emit KeyDelivered(_id, _buyer, _encryptedKey);
    }

    function getMyPurchaseKey(uint256 _id) external view returns (string memory) {
        require(hasPurchased[_id][msg.sender], "Not purchased");
        
        Purchase[] storage graphPurchases = purchases[_id];
        for (uint i = 0; i < graphPurchases.length; i++) {
            if (graphPurchases[i].buyer == msg.sender) {
                return graphPurchases[i].encryptedKey;
            }
        }
        return "";
    }
}
