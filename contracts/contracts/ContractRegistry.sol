// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "../interfaces/IModularContracts.sol";

/**
 * @title ContractRegistry
 * @dev Central registry for all modular puzzle pieces
 * @notice Enables seamless inter-contract communication and supports upgrades
 */
contract ContractRegistry is IContractRegistry, Ownable, ReentrancyGuard, Pausable {
    
    // State variables
    uint256 public version = 1;
    mapping(bytes32 => address) public contractAddresses;
    mapping(bytes32 => uint256) public contractVersions;
    mapping(address => bytes32) public addressToId;
    bytes32[] public contractIds;
    
    // Events
    event ContractRegistered(bytes32 indexed contractId, address indexed contractAddress, uint256 version);
    event ContractUpdated(bytes32 indexed contractId, address indexed oldAddress, address indexed newAddress);
    event ContractDeregistered(bytes32 indexed contractId, address indexed contractAddress);
    event RegistryPaused(address indexed pausedBy);
    event RegistryUnpaused(address indexed unpausedBy);
    
    // Errors
    error ContractAlreadyRegistered(bytes32 contractId);
    error ContractNotFound(bytes32 contractId);
    error InvalidAddress(address contractAddress);
    error RegistryPausedError();
    error NotAuthorized();
    
    modifier whenNotPausedRegistry() {
        if (paused()) revert RegistryPausedError();
        _;
    }
    
    modifier validAddress(address contractAddress) {
        if (contractAddress == address(0)) revert InvalidAddress(contractAddress);
        _;
    }
    
    modifier onlyAuthorized() {
        if (msg.sender != owner() && !isContract(msg.sender)) revert NotAuthorized();
        _;
    }
    
    constructor() {
        // Register the registry itself
        bytes32 registryId = keccak256(abi.encodePacked("ContractRegistry"));
        contractAddresses[registryId] = address(this);
        contractVersions[registryId] = version;
        addressToId[address(this)] = registryId;
        contractIds.push(registryId);
        
        emit ContractRegistered(registryId, address(this), version);
    }
    
    /**
     * @dev Initialize the registry (implements IModularContract)
     */
    function initialize(address /*registry*/) external pure override {
        // Registry doesn't need external initialization
        revert("Self-initialization not allowed");
    }
    
    /**
     * @dev Upgrade the registry version
     */
    function upgrade(address /*newImplementation*/) external override onlyOwner {
        version++;
        emit ContractUpdated(keccak256(abi.encodePacked("ContractRegistry")), address(this), address(this));
    }
    
    /**
     * @dev Pause the registry
     */
    function pause() external override onlyOwner {
        _pause();
        emit RegistryPaused(msg.sender);
    }
    
    /**
     * @dev Unpause the registry
     */
    function unpause() external override onlyOwner {
        _unpause();
        emit RegistryUnpaused(msg.sender);
    }
    
    /**
     * @dev Get the current version
     */
    function getVersion() external view override returns (uint256) {
        return version;
    }
    
    /**
     * @dev Register a new contract
     */
    function registerContract(bytes32 contractId, address contractAddress) 
        external 
        override 
        onlyAuthorized 
        whenNotPausedRegistry 
        validAddress(contractAddress)
        nonReentrant 
    {
        if (contractAddresses[contractId] != address(0)) {
            revert ContractAlreadyRegistered(contractId);
        }
        
        contractAddresses[contractId] = contractAddress;
        contractVersions[contractId] = 1;
        addressToId[contractAddress] = contractId;
        contractIds.push(contractId);
        
        emit ContractRegistered(contractId, contractAddress, 1);
    }
    
    /**
     * @dev Get a contract address by ID
     */
    function getContract(bytes32 contractId) external view override returns (address) {
        address contractAddress = contractAddresses[contractId];
        if (contractAddress == address(0)) {
            revert ContractNotFound(contractId);
        }
        return contractAddress;
    }
    
    /**
     * @dev Update an existing contract address
     */
    function updateContract(bytes32 contractId, address newAddress) 
        external 
        override 
        onlyAuthorized 
        whenNotPausedRegistry 
        validAddress(newAddress)
        nonReentrant 
    {
        address oldAddress = contractAddresses[contractId];
        if (oldAddress == address(0)) {
            revert ContractNotFound(contractId);
        }
        
        contractAddresses[contractId] = newAddress;
        contractVersions[contractId]++;
        delete addressToId[oldAddress];
        addressToId[newAddress] = contractId;
        
        emit ContractUpdated(contractId, oldAddress, newAddress);
    }
    
    /**
     * @dev Deregister a contract
     */
    function deregisterContract(bytes32 contractId) external onlyAuthorized whenNotPausedRegistry nonReentrant {
        address contractAddress = contractAddresses[contractId];
        if (contractAddress == address(0)) {
            revert ContractNotFound(contractId);
        }
        
        delete contractAddresses[contractId];
        delete contractVersions[contractId];
        delete addressToId[contractAddress];
        
        // Remove from contractIds array
        for (uint256 i = 0; i < contractIds.length; i++) {
            if (contractIds[i] == contractId) {
                contractIds[i] = contractIds[contractIds.length - 1];
                contractIds.pop();
                break;
            }
        }
        
        emit ContractDeregistered(contractId, contractAddress);
    }
    
    /**
     * @dev List all registered contracts
     */
    function listContracts() external view override returns (bytes32[] memory, address[] memory) {
        bytes32[] memory ids = new bytes32[](contractIds.length);
        address[] memory addresses = new address[](contractIds.length);
        
        for (uint256 i = 0; i < contractIds.length; i++) {
            ids[i] = contractIds[i];
            addresses[i] = contractAddresses[contractIds[i]];
        }
        
        return (ids, addresses);
    }
    
    /**
     * @dev Get contract version
     */
    function getContractVersion(bytes32 contractId) external view returns (uint256) {
        return contractVersions[contractId];
    }
    
    /**
     * @dev Check if an address is a registered contract
     */
    function isRegisteredContract(address contractAddress) external view returns (bool) {
        bytes32 contractId = addressToId[contractAddress];
        return contractAddresses[contractId] != address(0);
    }
    
    /**
     * @dev Get contract ID by address
     */
    function getContractId(address contractAddress) external view returns (bytes32) {
        return addressToId[contractAddress];
    }
    
    /**
     * @dev Batch register contracts
     */
    function batchRegisterContracts(bytes32[] memory _contractIds, address[] memory _contractAddresses) 
        external 
        onlyAuthorized 
        whenNotPausedRegistry
    {
        require(_contractIds.length == _contractAddresses.length, "Array length mismatch");
        
        for (uint256 i = 0; i < _contractIds.length; i++) {
            if (_contractAddresses[i] != address(0) && contractAddresses[_contractIds[i]] == address(0)) {
                contractAddresses[_contractIds[i]] = _contractAddresses[i];
                contractVersions[_contractIds[i]] = 1;
                addressToId[_contractAddresses[i]] = _contractIds[i];
                
                emit ContractRegistered(_contractIds[i], _contractAddresses[i], 1);
            }
        }
    }
    
    /**
     * @dev Check if address is a contract
     */
    function isContract(address addr) internal view returns (bool) {
        uint256 size;
        assembly {
            size := extcodesize(addr)
        }
        return size > 0;
    }
    
    /**
     * @dev Get registry statistics
     */
    function getRegistryStats() external view returns (
        uint256 totalContracts,
        uint256 totalVersion,
        bool isPaused,
        address owner
    ) {
        return (
            contractIds.length,
            version,
            paused(),
            this.owner()
        );
    }
}
