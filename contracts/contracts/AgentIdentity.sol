// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title AgentIdentity
 * @notice Stores lightweight identity metadata for OpenClaw agents.
 * @dev v0.17.0 adds a `themePreference` mapping so an agent's UI theme
 *      persists across devices and edge nodes.
 */
contract AgentIdentity {
    /// @notice Owner of the contract.
    address public owner;

    /// @notice Registered agent names (optional).
    mapping(address => bytes32) public agentName;

    /// @notice Encoded theme preference per agent wallet.
    mapping(address => bytes32) public themePreference;

    event ThemePreferenceSet(address indexed wallet, bytes32 preferenceId);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /**
     * @notice Set the theme preference for the calling agent.
     * @param preferenceId A bytes32 preference identifier (e.g. keccak256("dark")).
     */
    function setThemePreference(bytes32 preferenceId) external {
        themePreference[msg.sender] = preferenceId;
        emit ThemePreferenceSet(msg.sender, preferenceId);
    }

    /**
     * @notice Register or update an agent name.
     */
    function registerAgent(bytes32 name) external onlyOwner {
        agentName[msg.sender] = name;
    }

    /**
     * @notice Read the theme preference for a wallet.
     */
    function getThemePreference(address wallet) external view returns (bytes32) {
        return themePreference[wallet];
    }
}
