// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title AITokenRegistry
/// @notice Tracks permitted providers and staking requirements for AIToken minting
contract AITokenRegistry is AccessControl {
    bytes32 public constant COORDINATOR_ROLE = keccak256("COORDINATOR_ROLE");

    struct ProviderInfo {
        bool active;
        uint256 collateral;
    }

    mapping(address => ProviderInfo) public providers;

    event ProviderRegistered(address indexed provider, uint256 collateral);
    event ProviderUpdated(address indexed provider, bool active, uint256 collateral);

    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
    }

    function registerProvider(address provider, uint256 collateral) external onlyRole(COORDINATOR_ROLE) {
        require(provider != address(0), "invalid provider");
        require(!providers[provider].active, "already registered");
        providers[provider] = ProviderInfo({active: true, collateral: collateral});
        emit ProviderRegistered(provider, collateral);
    }

    function updateProvider(
        address provider,
        bool active,
        uint256 collateral
    ) external onlyRole(COORDINATOR_ROLE) {
        require(provider != address(0), "invalid provider");
        require(providers[provider].active || active, "provider not registered");
        providers[provider] = ProviderInfo({active: active, collateral: collateral});
        emit ProviderUpdated(provider, active, collateral);
    }

    function providerInfo(address provider) external view returns (ProviderInfo memory) {
        return providers[provider];
    }
}
