// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title Energy Pricing Interface
 * @dev View interface for the energy-cost floor used by AIPowerRental and
 * EscrowService. Keeping the interface small lets rental/escrow contracts
 * depend on views rather than importing the full DynamicPricing implementation.
 */
interface IEnergyPricing {
    struct EnergyProfile {
        bool enabled;
        uint256 revision;
        string modelId;
        address provider;
        uint256 tdpWatts;
        uint256 eurPerKwh;
    }

    struct EnergyRate {
        bool enabled;
        uint256 version;
        uint256 aitPerEur;
        uint256 observedAt;
        uint256 submittedAt;
        string sourceKind;
    }

    event EnergyProfileRegistered(string indexed resourceId, address indexed provider, string modelId);
    event EnergyProfileUpdated(string indexed resourceId, uint256 revision);
    event ResourceTariffUpdated(string indexed resourceId, uint256 eurPerKwh);
    event EnergyRatePublished(uint256 version, uint256 aitPerEur, uint256 observedAt, string sourceKind);
    event EnergyPublisherChanged(address indexed publisher);

    function getEnergyProfile(string calldata resourceId)
        external
        view
        returns (EnergyProfile memory profile);

    function getEnergyRate() external view returns (EnergyRate memory rate);

    function getEnergyFloor(
        string calldata resourceId,
        uint256 gpuCount,
        uint256 durationSeconds,
        uint256 settlementUnitScale
    ) external view returns (uint256 netFloor, bool valid, string memory reason);

    function energyPublisher() external view returns (address);

    function setEnergyPublisher(address publisher) external;

    function registerEnergyProfile(
        string calldata resourceId,
        address provider,
        string calldata modelId,
        uint256 tdpWatts,
        uint256 eurPerKwh
    ) external;

    function setResourceTariff(string calldata resourceId, uint256 eurPerKwh) external;

    function publishEnergyRate(
        uint256 aitPerEur,
        uint256 observedAt,
        string calldata sourceKind
    ) external;

    function setMaxRateAge(uint256 _maxRateAge) external;
}
