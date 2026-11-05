// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

/// Purchases are escrowed in this contract until the creator delivers the
/// decryption key (or the delivery window lapses and the buyer refunds).
/// The creator can no longer be paid for a key that never arrives, and the
/// buyer's price is bounded by maxPrice at purchase time.
contract KnowledgeGraphMarket is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public paymentToken;
    uint256 public graphCounter;
    uint256 public platformFeePercentage = 250; // 2.5%
    uint256 public constant DELIVERY_WINDOW = 7 days;
    // Platform fees accumulate here and are only moved by withdrawPlatformFees,
    // so the owner can never sweep escrowed buyer funds.
    uint256 public accruedPlatformFees;

    struct KnowledgeGraph {
        uint256 id;
        address creator;
        string cid;
        string metadataURI;
        uint256 price;
        uint256 totalSales;
        bool isActive;
    }

    struct Purchase {
        uint256 graphId;
        address buyer;
        uint256 timestamp;
        uint256 paid;
        string encryptedKey;
        bool delivered;
        bool refunded;
    }

    mapping(uint256 => KnowledgeGraph) public graphs;
    mapping(uint256 => mapping(address => bool)) public hasPurchased;

    // graphId => buyer => Purchase — indexed by buyer, so delivery and key
    // reads are O(1) instead of a linear scan.
    mapping(uint256 => mapping(address => Purchase)) public purchases;

    event GraphListed(uint256 indexed id, address indexed creator, string cid, string metadataURI, uint256 price);
    event GraphUpdated(uint256 indexed id, uint256 newPrice, bool isActive);
    event GraphPurchased(uint256 indexed id, address indexed buyer, uint256 price);
    event KeyDelivered(uint256 indexed id, address indexed buyer, string encryptedKey);
    event PurchaseRefunded(uint256 indexed id, address indexed buyer, uint256 amount);
    event PlatformFeesWithdrawn(address indexed to, uint256 amount);

    constructor(address _paymentToken) {
        paymentToken = IERC20(_paymentToken);
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

    function purchaseGraph(uint256 _id, uint256 _maxPrice) external nonReentrant {
        KnowledgeGraph storage graph = graphs[_id];
        require(graph.isActive, "Graph inactive");
        require(!hasPurchased[_id][msg.sender], "Already purchased");
        require(graph.creator != msg.sender, "Cannot buy own graph");
        // A price raised between quote and purchase can never cost the buyer
        // more than _maxPrice.
        require(graph.price <= _maxPrice, "Price above maxPrice");

        // Escrow the full price in this contract; the creator is paid only on
        // key delivery, the platform fee on withdrawal.
        paymentToken.safeTransferFrom(msg.sender, address(this), graph.price);

        graph.totalSales++;
        hasPurchased[_id][msg.sender] = true;

        Purchase storage p = purchases[_id][msg.sender];
        // A refunded purchase leaves the slot populated (refunded=true,
        // delivered=false, delivered key intact); re-purchasing must reset it
        // or the new escrow would be undeliverable (#1154).
        p.graphId = _id;
        p.buyer = msg.sender;
        p.timestamp = block.timestamp;
        p.paid = graph.price;
        p.delivered = false;
        p.refunded = false;
        p.encryptedKey = "";

        emit GraphPurchased(_id, msg.sender, graph.price);
    }

    function deliverDecryptionKey(uint256 _id, address _buyer, string calldata _encryptedKey) external nonReentrant {
        KnowledgeGraph storage graph = graphs[_id];
        require(graph.creator == msg.sender, "Not creator");
        require(hasPurchased[_id][_buyer], "Buyer has not purchased");

        Purchase storage p = purchases[_id][_buyer];
        require(!p.delivered, "Key already delivered");
        require(!p.refunded, "Purchase refunded");

        p.encryptedKey = _encryptedKey;
        p.delivered = true;

        // Release the escrowed payment: fee accrues to the contract, the rest
        // goes to the creator.
        uint256 fee = (p.paid * platformFeePercentage) / 10000;
        accruedPlatformFees += fee;
        paymentToken.safeTransfer(graph.creator, p.paid - fee);

        emit KeyDelivered(_id, _buyer, _encryptedKey);
    }

    /// Buyer refund once the delivery window lapses without a key. The full
    /// escrowed amount returns to the buyer; no fee is taken on refunds.
    function refundPurchase(uint256 _id) external nonReentrant {
        require(hasPurchased[_id][msg.sender], "Not purchased");
        Purchase storage p = purchases[_id][msg.sender];
        require(!p.delivered, "Key delivered");
        require(!p.refunded, "Already refunded");
        require(block.timestamp >= p.timestamp + DELIVERY_WINDOW, "Delivery window still open");

        p.refunded = true;
        hasPurchased[_id][msg.sender] = false;
        uint256 amount = p.paid;
        p.paid = 0;
        paymentToken.safeTransfer(msg.sender, amount);

        emit PurchaseRefunded(_id, msg.sender, amount);
    }

    /// Owner withdraws only the accrued platform fees — escrowed buyer funds
    /// can never be swept.
    function withdrawPlatformFees(address _to) external onlyOwner {
        uint256 amount = accruedPlatformFees;
        require(amount > 0, "No fees accrued");
        accruedPlatformFees = 0;
        paymentToken.safeTransfer(_to, amount);
        emit PlatformFeesWithdrawn(_to, amount);
    }

    function getMyPurchaseKey(uint256 _id) external view returns (string memory) {
        require(hasPurchased[_id][msg.sender], "Not purchased");
        return purchases[_id][msg.sender].encryptedKey;
    }
}
