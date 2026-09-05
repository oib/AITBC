// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/AgentIdentity.sol";

contract AgentIdentityFuzzTest is Test {
    event ThemePreferenceSet(address indexed wallet, bytes32 preferenceId);

    AgentIdentity public identity;
    address public owner;
    address public user1;
    address public user2;

    function setUp() public {
        owner = address(this);
        user1 = address(0x1);
        user2 = address(0x2);
        identity = new AgentIdentity();
    }

    function testFuzz_SetThemePreference(bytes32 preferenceId) public {
        vm.prank(user1);
        identity.setThemePreference(preferenceId);

        assertEq(identity.getThemePreference(user1), preferenceId);
        assertEq(identity.themePreference(user1), preferenceId);
    }

    function testFuzz_ThemePreferenceIsolation(bytes32 pref1, bytes32 pref2) public {
        vm.prank(user1);
        identity.setThemePreference(pref1);
        vm.prank(user2);
        identity.setThemePreference(pref2);

        assertEq(identity.getThemePreference(user1), pref1);
        assertEq(identity.getThemePreference(user2), pref2);
    }

    function testFuzz_ThemePreferenceDefaultsToZero(address wallet) public {
        vm.assume(wallet != user1);

        vm.prank(user1);
        identity.setThemePreference(keccak256("dark"));

        assertEq(identity.getThemePreference(wallet), bytes32(0));
    }

    function testFuzz_RegisterAgentOnlyOwner(address caller, bytes32 name) public {
        vm.assume(caller != owner);

        vm.prank(caller);
        vm.expectRevert("not owner");
        identity.registerAgent(name);
    }

    function testFuzz_RegisterAgentAsOwner(bytes32 name) public {
        identity.registerAgent(name);
        assertEq(identity.agentName(owner), name);
    }

    function testFuzz_SetThemePreferenceEmitsEvent(bytes32 preferenceId) public {
        vm.expectEmit(true, false, false, true, address(identity));
        emit ThemePreferenceSet(user1, preferenceId);
        vm.prank(user1);
        identity.setThemePreference(preferenceId);
    }
}
