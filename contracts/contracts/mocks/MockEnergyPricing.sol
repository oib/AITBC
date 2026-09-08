// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "../IEnergyPricing.sol";

contract MockEnergyPricing is IEnergyPricing {
    EnergyProfile private _profile;
    EnergyRate private _rate;
    uint256 private _floor;
    bool private _floorValid;

    address public override energyPublisher;

    constructor(
        address provider,
        string memory modelId,
        uint256 floor,
        uint256 aitPerEur
    ) {
        _profile = EnergyProfile({
            enabled: true,
            revision: 1,
            modelId: modelId,
            provider: provider,
            tdpWatts: 200,
            eurPerKwh: 30
        });
        _rate = EnergyRate({
            enabled: true,
            version: 1,
            aitPerEur: aitPerEur,
            observedAt: block.timestamp,
            submittedAt: block.timestamp,
            sourceKind: "mock"
        });
        _floor = floor;
        _floorValid = true;
    }

    function getEnergyProfile(string calldata) external view override returns (EnergyProfile memory) {
        return _profile;
    }

    function getEnergyRate() external view override returns (EnergyRate memory) {
        return _rate;
    }

    function getEnergyFloor(
        string calldata,
        uint256,
        uint256,
        uint256
    ) external view override returns (uint256 netFloor, bool valid, string memory reason) {
        return (_floor, _floorValid, "");
    }

    function setEnergyPublisher(address publisher) external override {
        energyPublisher = publisher;
    }

    function registerEnergyProfile(
        string calldata,
        address,
        string calldata,
        uint256,
        uint256
    ) external override {}

    function setResourceTariff(string calldata, uint256) external override {}

    function publishEnergyRate(
        uint256 aitPerEur,
        uint256 observedAt,
        string calldata sourceKind
    ) external override {
        _rate.aitPerEur = aitPerEur;
        _rate.observedAt = observedAt;
        _rate.sourceKind = sourceKind;
    }

    function setMaxRateAge(uint256) external override {}
}
