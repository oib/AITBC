// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/contracts/ContractRegistry.sol";

contract ContractRegistryFuzzTest is Test {
    ContractRegistry public registry;
    address public owner;
    address public user1;
    address public user2;
    address public contract1;
    address public contract2;

    function setUp() public {
        owner = address(this);
        user1 = address(0x1);
        user2 = address(0x2);
        contract1 = address(0x3);
        contract2 = address(0x4);

        vm.prank(owner);
        registry = new ContractRegistry();
    }

    function testFuzz_RegisterContract(bytes32 contractId, address contractAddress) public {
        vm.assume(contractAddress != address(0));
        vm.assume(contractId != bytes32(0));

        vm.prank(owner);
        registry.registerContract(contractId, contractAddress);

        assertEq(registry.getContract(contractId), contractAddress);
    }

    function testFuzz_RevertIfZeroAddress(bytes32 contractId) public {
        vm.assume(contractId != bytes32(0));

        vm.prank(owner);
        vm.expectRevert("Invalid address");
        registry.registerContract(contractId, address(0));
    }

    function testFuzz_RevertIfAlreadyRegistered(bytes32 contractId, address contractAddress) public {
        vm.assume(contractAddress != address(0));
        vm.assume(contractId != bytes32(0));

        vm.prank(owner);
        registry.registerContract(contractId, contractAddress);

        vm.prank(owner);
        vm.expectRevert("ContractAlreadyRegistered");
        registry.registerContract(contractId, contractAddress);
    }

    function testFuzz_UpdateContract(bytes32 contractId, address oldAddress, address newAddress) public {
        vm.assume(oldAddress != address(0));
        vm.assume(newAddress != address(0));
        vm.assume(oldAddress != newAddress);
        vm.assume(contractId != bytes32(0));

        vm.prank(owner);
        registry.registerContract(contractId, oldAddress);

        vm.prank(owner);
        registry.updateContract(contractId, newAddress);

        assertEq(registry.getContract(contractId), newAddress);
    }

    function testFuzz_DeregisterContract(bytes32 contractId, address contractAddress) public {
        vm.assume(contractAddress != address(0));
        vm.assume(contractId != bytes32(0));

        vm.prank(owner);
        registry.registerContract(contractId, contractAddress);

        vm.prank(owner);
        registry.deregisterContract(contractId);

        vm.expectRevert("ContractNotFound");
        registry.getContract(contractId);
    }

    function testFuzz_BatchRegister(bytes32[] calldata contractIds, address[] calldata addresses) public {
        vm.assume(contractIds.length == addresses.length);
        vm.assume(contractIds.length > 0);
        vm.assume(contractIds.length <= 100);

        for (uint256 i = 0; i < addresses.length; i++) {
            vm.assume(addresses[i] != address(0));
            vm.assume(contractIds[i] != bytes32(0));
        }

        vm.prank(owner);
        registry.batchRegisterContracts(contractIds, addresses);

        for (uint256 i = 0; i < contractIds.length; i++) {
            assertEq(registry.getContract(contractIds[i]), addresses[i]);
        }
    }

    function testFuzz_ListContracts(uint256 numContracts) public {
        vm.assume(numContracts > 0);
        vm.assume(numContracts <= 50);

        bytes32[] memory contractIds = new bytes32[](numContracts);
        address[] memory addresses = new address[](numContracts);

        for (uint256 i = 0; i < numContracts; i++) {
            contractIds[i] = keccak256(abi.encodePacked(i));
            addresses[i] = address(uint160(i + 100));

            vm.prank(owner);
            registry.registerContract(contractIds[i], addresses[i]);
        }

        (bytes32[] memory listedIds, address[] memory listedAddresses) = registry.listContracts();
        assertEq(listedIds.length, numContracts + 1); // +1 for registry itself
        assertEq(listedAddresses.length, numContracts + 1);
    }

    function testFuzz_GetContractVersion(bytes32 contractId, address contractAddress) public {
        vm.assume(contractAddress != address(0));
        vm.assume(contractId != bytes32(0));

        vm.prank(owner);
        registry.registerContract(contractId, contractAddress);

        uint256 version = registry.getContractVersion(contractId);
        assertEq(version, 1);
    }

    function testFuzz_IsRegisteredContract(address contractAddress) public {
        vm.assume(contractAddress != address(0));

        bool isRegistered = registry.isRegisteredContract(contractAddress);
        
        if (contractAddress == address(registry)) {
            assertTrue(isRegistered);
        } else {
            assertFalse(isRegistered);
        }
    }

    function testFuzz_GetContractId(address contractAddress, bytes32 contractId) public {
        vm.assume(contractAddress != address(0));
        vm.assume(contractId != bytes32(0));

        vm.prank(owner);
        registry.registerContract(contractId, contractAddress);

        bytes32 retrievedId = registry.getContractId(contractAddress);
        assertEq(retrievedId, contractId);
    }

    function testFuzz_GetRegistryStats() public {
        (uint256 totalContracts, uint256 totalVersion, bool isPaused, address registryOwner) = registry.getRegistryStats();
        
        assertEq(totalContracts, 1); // Registry itself
        assertEq(totalVersion, 1);
        assertFalse(isPaused);
        assertEq(registryOwner, owner);
    }
}
