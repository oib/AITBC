// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/ContractRegistry.sol";

contract DummyRegistered {
    uint256 public marker;
}

/**
 * Pins issue #1122:
 *  - batchRegisterContracts never pushed ids onto contractIds, so
 *    listContracts missed every batch-registered contract;
 *  - nothing checked a registered address holds code;
 *  - two ids could share one address, so updating or deregistering one
 *    erased the other's reverse lookup.
 */
contract ContractRegistryIntegrityTest is Test {
    ContractRegistry registry;
    DummyRegistered c1;
    DummyRegistered c2;

    bytes32 idA = keccak256("A");
    bytes32 idB = keccak256("B");
    bytes32 idC = keccak256("C");

    function setUp() public {
        registry = new ContractRegistry();
        c1 = new DummyRegistered();
        c2 = new DummyRegistered();
    }

    function testBatchRegisteredContractsAreListed() public {
        bytes32[] memory ids = new bytes32[](2);
        address[] memory addrs = new address[](2);
        ids[0] = idA;
        ids[1] = idB;
        addrs[0] = address(c1);
        addrs[1] = address(c2);

        registry.batchRegisterContracts(ids, addrs);

        (bytes32[] memory listedIds, address[] memory listedAddrs) = registry.listContracts();
        // self-registration + the two batch entries
        assertEq(listedIds.length, 3);
        assertEq(listedAddrs.length, 3);

        bool foundA;
        bool foundB;
        for (uint256 i = 0; i < listedIds.length; i++) {
            if (listedIds[i] == idA) foundA = listedAddrs[i] == address(c1);
            if (listedIds[i] == idB) foundB = listedAddrs[i] == address(c2);
        }
        assertTrue(foundA && foundB);

        // And they deregister cleanly (the array entry exists to be removed).
        registry.deregisterContract(idA);
        vm.expectRevert(abi.encodeWithSelector(ContractRegistry.ContractNotFound.selector, idA));
        registry.getContract(idA);
    }

    function testRegisterRejectsAddressWithoutCode() public {
        vm.expectRevert(abi.encodeWithSelector(ContractRegistry.NoCodeAtAddress.selector, address(0xdead)));
        registry.registerContract(idA, address(0xdead));
    }

    function testBatchRejectsAddressWithoutCode() public {
        bytes32[] memory ids = new bytes32[](1);
        address[] memory addrs = new address[](1);
        ids[0] = idA;
        addrs[0] = address(0xdead);

        vm.expectRevert(abi.encodeWithSelector(ContractRegistry.NoCodeAtAddress.selector, address(0xdead)));
        registry.batchRegisterContracts(ids, addrs);
    }

    function testUpdateRejectsAddressWithoutCode() public {
        registry.registerContract(idA, address(c1));
        vm.expectRevert(abi.encodeWithSelector(ContractRegistry.NoCodeAtAddress.selector, address(0xdead)));
        registry.updateContract(idA, address(0xdead));
    }

    function testSecondIdForSameAddressReverts() public {
        registry.registerContract(idA, address(c1));
        vm.expectRevert(
            abi.encodeWithSelector(ContractRegistry.AddressAliasedToOtherId.selector, address(c1), idA)
        );
        registry.registerContract(idB, address(c1));
    }

    function testUpdateToAliasedAddressReverts() public {
        registry.registerContract(idA, address(c1));
        registry.registerContract(idB, address(c2));
        vm.expectRevert(
            abi.encodeWithSelector(ContractRegistry.AddressAliasedToOtherId.selector, address(c2), idB)
        );
        registry.updateContract(idA, address(c2));
    }

    function testDeregisterFreesAddressForNewId() public {
        registry.registerContract(idA, address(c1));
        registry.deregisterContract(idA);
        // After deregistration the reverse lookup is cleared, so a new id
        // may claim the address.
        registry.registerContract(idC, address(c1));
        assertEq(registry.getContractId(address(c1)), idC);
    }

    function testUpdateKeepsReverseLookupConsistent() public {
        registry.registerContract(idA, address(c1));
        registry.updateContract(idA, address(c2));
        assertEq(registry.getContractId(address(c1)), bytes32(0));
        assertEq(registry.getContractId(address(c2)), idA);
    }
}
