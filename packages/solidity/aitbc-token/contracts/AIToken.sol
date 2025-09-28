// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

/// @title AIToken
/// @notice ERC20 token that mints units for providers based on attested compute receipts
contract AIToken is ERC20, AccessControl {
    using ECDSA for bytes32;
    using MessageHashUtils for bytes32;

    bytes32 public constant COORDINATOR_ROLE = keccak256("COORDINATOR_ROLE");
    bytes32 public constant ATTESTOR_ROLE = keccak256("ATTESTOR_ROLE");

    /// @notice Tracks consumed receipt hashes to prevent replay
    mapping(bytes32 => bool) public consumedReceipts;

    event ReceiptConsumed(bytes32 indexed receiptHash, address indexed provider, uint256 units, address indexed attestor);

    constructor(address admin) ERC20("AIToken", "AIT") {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
    }

    /// @notice Mint tokens for a provider when coordinator submits a valid attested receipt
    /// @param provider Address of the compute provider receiving minted tokens
    /// @param units Amount of tokens to mint
    /// @param receiptHash Unique hash representing the off-chain receipt
    /// @param signature Coordinator-attested signature authorizing the mint
    function mintWithReceipt(
        address provider,
        uint256 units,
        bytes32 receiptHash,
        bytes calldata signature
    ) external onlyRole(COORDINATOR_ROLE) {
        require(provider != address(0), "invalid provider");
        require(units > 0, "invalid units");
        require(!consumedReceipts[receiptHash], "receipt already consumed");

        bytes32 digest = _mintDigest(provider, units, receiptHash);
        address attestor = digest.recover(signature);
        require(hasRole(ATTESTOR_ROLE, attestor), "invalid attestor signature");

        consumedReceipts[receiptHash] = true;
        _mint(provider, units);

        emit ReceiptConsumed(receiptHash, provider, units, attestor);
    }

    /// @notice Helper to compute the signed digest required for minting
    function mintDigest(address provider, uint256 units, bytes32 receiptHash) external view returns (bytes32) {
        return _mintDigest(provider, units, receiptHash);
    }

    function _mintDigest(address provider, uint256 units, bytes32 receiptHash) internal view returns (bytes32) {
        bytes32 structHash = keccak256(abi.encode(block.chainid, address(this), provider, units, receiptHash));
        return structHash.toEthSignedMessageHash();
    }
}
