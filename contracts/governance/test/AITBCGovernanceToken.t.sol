// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../src/AITBCGovernanceToken.sol";

contract AITBCGovernanceTokenTest is Test {
    AITBCGovernanceToken token;
    address owner;
    address user1;
    address user2;

    function setUp() public {
        owner = address(this);
        user1 = address(0x1);
        user2 = address(0x2);

        token = new AITBCGovernanceToken();
    }

    function testInitialState() public {
        assertEq(token.name(), "AITBC Governance Token");
        assertEq(token.symbol(), "GOV");
        assertEq(token.decimals(), 18);
        assertEq(token.totalSupply(), 1_000_000_000 * 10**18);
        assertEq(token.balanceOf(owner), 1_000_000_000 * 10**18);
    }

    function testStakeTokens() public {
        uint256 stakeAmount = 1000 * 10**18;
        uint256 lockPeriod = 30 days;

        // Transfer tokens to user1
        token.transfer(user1, stakeAmount);

        vm.startPrank(user1);
        token.stake(stakeAmount, lockPeriod);
        vm.stopPrank();

        uint256 staked = token.stakedTokens(user1);
        assertEq(staked, stakeAmount);

        uint256 votingPower = token.getVotingPower(user1);
        // Voting power = balance (0) + staked * 2 = 2000 * 10**18
        assertEq(votingPower, stakeAmount * 2);
    }

    function testStakeMinimumLockPeriod() public {
        uint256 stakeAmount = 1000 * 10**18;
        uint256 lockPeriod = 29 days; // Below minimum

        token.transfer(user1, stakeAmount);

        vm.startPrank(user1);
        vm.expectRevert("Lock period too short");
        token.stake(stakeAmount, lockPeriod);
        vm.stopPrank();
    }

    function testCannotStakeTwice() public {
        uint256 stakeAmount = 1000 * 10**18;
        uint256 lockPeriod = 30 days;

        token.transfer(user1, stakeAmount * 2);

        vm.startPrank(user1);
        token.stake(stakeAmount, lockPeriod);

        vm.expectRevert("Already staking");
        token.stake(stakeAmount, lockPeriod);
        vm.stopPrank();
    }

    function testUnstakeTokens() public {
        uint256 stakeAmount = 1000 * 10**18;
        uint256 lockPeriod = 30 days;

        token.transfer(user1, stakeAmount);

        vm.startPrank(user1);
        token.stake(stakeAmount, lockPeriod);

        // Fast forward past lock period
        vm.warp(block.timestamp + lockPeriod + 1);

        token.unstake(stakeAmount);
        vm.stopPrank();

        assertEq(token.balanceOf(user1), stakeAmount);

        uint256 staked = token.stakedTokens(user1);
        assertEq(staked, 0);
    }

    function testCannotUnstakeBeforeLockPeriod() public {
        uint256 stakeAmount = 1000 * 10**18;
        uint256 lockPeriod = 30 days;

        token.transfer(user1, stakeAmount);

        vm.startPrank(user1);
        token.stake(stakeAmount, lockPeriod);

        vm.expectRevert("Stake still locked");
        token.unstake(stakeAmount);
        vm.stopPrank();
    }

    function testVotingPowerCalculation() public {
        uint256 balance = 5000 * 10**18;
        uint256 stakeAmount = 1000 * 10**18;

        token.transfer(user1, balance);

        vm.startPrank(user1);
        token.stake(stakeAmount, 30 days);
        vm.stopPrank();

        uint256 votingPower = token.getVotingPower(user1);
        // Voting power = balance (4000) + staked * 2 (2000) = 6000 * 10**18
        assertEq(votingPower, (balance - stakeAmount) + (stakeAmount * 2));
    }
}
