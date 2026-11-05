// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/TreasuryManager.sol";
import "../contracts/ContractRegistry.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockToken1104 is ERC20 {
    constructor() ERC20("Mock Token", "MTK") {
        _mint(msg.sender, 1_000_000 * 10**18);
    }
}

/// @dev Pins for #1104: allocations reserve against the unreserved balance,
/// emergencyWithdraw is capped at the unreserved part, releases free the
/// reserve, and the DAO-only governanceWithdraw is the escape path.
contract TreasuryReserve1104Test is Test {
    TreasuryManager public treasury;
    ContractRegistry public registry;
    MockToken1104 public token;
    address public owner;
    address public user1;
    address public dao;

    uint256 internal constant BALANCE = 100_000 * 10**18;
    uint256 internal constant ALLOC = 60_000 * 10**18;

    function setUp() public {
        owner = address(this);
        user1 = address(0x1);

        token = new MockToken1104();
        registry = new ContractRegistry();

        treasury = new TreasuryManager(address(token));
        registry.registerContract(keccak256(abi.encodePacked("TreasuryManager")), address(treasury));
        // registerContract requires code at the address and one id per
        // address; a second registry instance stands in as the DAO.
        dao = address(new ContractRegistry());
        registry.registerContract(keccak256(abi.encodePacked("DAOGovernance")), dao);
        treasury.initialize(address(registry));

        token.transfer(address(treasury), BALANCE);
        vm.prank(owner);
        treasury.createBudgetCategory("ops", 1_000_000 * 10**18);
    }

    function test_SecondAllocationCannotExceedUnreservedBalance() public {
        vm.prank(owner);
        treasury.allocateFunds("ops", user1, ALLOC);
        assertEq(treasury.reservedByToken(address(token)), ALLOC);

        // Budget still has room (1M - 60k) but only 40k is unreserved.
        vm.prank(owner);
        vm.expectPartialRevert(TreasuryManager.InsufficientBalance.selector);
        treasury.allocateFunds("ops", user1, 50_000 * 10**18);

        // Exactly the unreserved remainder still fits.
        vm.prank(owner);
        treasury.allocateFunds("ops", user1, 40_000 * 10**18);
        assertEq(treasury.reservedByToken(address(token)), BALANCE);
    }

    function test_EmergencyWithdrawCappedAtUnreserved() public {
        vm.prank(owner);
        treasury.allocateFunds("ops", user1, ALLOC);

        uint256 unreserved = BALANCE - ALLOC;
        uint256 ownerBefore = token.balanceOf(owner);

        vm.prank(owner);
        vm.expectPartialRevert(TreasuryManager.InsufficientBalance.selector);
        treasury.emergencyWithdraw(address(token), unreserved + 1);

        vm.prank(owner);
        treasury.emergencyWithdraw(address(token), unreserved);
        assertEq(token.balanceOf(owner) - ownerBefore, unreserved);
        assertEq(token.balanceOf(address(treasury)), ALLOC);
    }

    function test_ReleaseFreesReserve() public {
        vm.prank(owner);
        treasury.allocateFundsWithVesting("ops", user1, ALLOC, 30 days);
        assertEq(treasury.reservedByToken(address(token)), ALLOC);

        vm.warp(block.timestamp + 31 days);
        vm.prank(user1);
        treasury.releaseVestedFunds(1);

        assertEq(token.balanceOf(user1), ALLOC);
        assertEq(treasury.reservedByToken(address(token)), 0);

        // With the reserve freed the owner can withdraw everything left in
        // the treasury (the released 60k already went to the recipient).
        uint256 remaining = BALANCE - ALLOC;
        uint256 ownerBefore = token.balanceOf(owner);
        vm.prank(owner);
        treasury.emergencyWithdraw(address(token), remaining);
        assertEq(token.balanceOf(owner) - ownerBefore, remaining);
        assertEq(token.balanceOf(address(treasury)), 0);
    }

    function test_GovernanceWithdrawSweepsReservedOnlyForDao() public {
        vm.prank(owner);
        treasury.allocateFunds("ops", user1, ALLOC);

        // Non-DAO callers cannot use the escape path.
        vm.prank(owner);
        vm.expectRevert(TreasuryManager.NotAuthorized.selector);
        treasury.governanceWithdraw(address(token), 1);

        // DAO sweeps part of the reserve; the reserve shrinks with it.
        vm.prank(dao);
        treasury.governanceWithdraw(address(token), 20_000 * 10**18);
        assertEq(treasury.reservedByToken(address(token)), 40_000 * 10**18);

        // Owner emergencyWithdraw is still capped at balance - reserved.
        vm.prank(owner);
        vm.expectPartialRevert(TreasuryManager.InsufficientBalance.selector);
        treasury.emergencyWithdraw(address(token), 50_000 * 10**18);
    }

    /// @dev Simulates a pre-upgrade allocation: reserveCounted == false and no
    /// reserve recorded. First release must count the outstanding amount into
    /// the reserve exactly once (no double count, no leak).
    function test_LegacyAllocationCountedLazily() public {
        vm.prank(owner);
        treasury.allocateFundsWithVesting("ops", user1, ALLOC, 30 days);

        // Rewind to the pre-upgrade state for allocation 1: flag cleared and
        // the reserve contribution removed. allocations mapping is slot 5;
        // reserveCounted is struct offset 11; reservedByToken is slot 8.
        bytes32 structBase = keccak256(abi.encode(uint256(1), uint256(5)));
        vm.store(address(treasury), bytes32(uint256(structBase) + 11), bytes32(0));

        // reservedByToken is mapping(address=>uint256) at slot 8.
        bytes32 reservedSlot = keccak256(abi.encode(address(token), uint256(8)));
        vm.store(address(treasury), reservedSlot, bytes32(0));

        vm.warp(block.timestamp + 31 days);
        uint256 userBefore = token.balanceOf(user1);
        vm.prank(user1);
        treasury.releaseVestedFunds(1);

        assertEq(token.balanceOf(user1) - userBefore, ALLOC);
        // Outstanding was counted then immediately freed by the release.
        assertEq(treasury.reservedByToken(address(token)), 0);
    }
}
