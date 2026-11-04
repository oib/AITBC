// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../src/AITBCGovernanceToken.sol";
import "../src/AITBCVoting.sol";

/// #1118 pins: vote weight is read at proposal start (moved tokens cannot
/// vote twice), a proposer needs minimum power, same-block same-title
/// proposals no longer overwrite, and execute must run a real call.

contract MockExecTarget {
    uint256 public calls;
    function bump() external {
        calls++;
    }
}

contract AITBCVoting1118Test is Test {
    AITBCGovernanceToken token;
    AITBCVoting voting;
    MockExecTarget target;
    address whale = address(0x1);
    address holder = address(0x2);
    address relay1 = address(0x3);
    address relay2 = address(0x4);
    address dust = address(0x5);

    function setUp() public {
        token = new AITBCGovernanceToken();
        voting = new AITBCVoting(address(token));
        target = new MockExecTarget();
        token.transfer(whale, 200_000_000 * 10**18); // 20% — quorum-capable
        token.transfer(holder, 2_000_000 * 10**18);  // above MIN_PROPOSAL_POWER
        vm.warp(block.timestamp + 1); // let checkpoints age past mint/transfer
    }

    function _propose(address proposer) internal returns (bytes32) {
        vm.prank(proposer);
        return voting.createProposal("t", "title", "d", abi.encode(address(target), abi.encodeCall(MockExecTarget.bump, ())), 7 days);
    }

    function test_MovedTokensCannotRevote() public {
        bytes32 pid = _propose(whale);
        vm.prank(holder);
        voting.vote(pid, true); // holder's power at snapshot counts

        // move the same tokens to a fresh address and try to vote again
        vm.prank(holder);
        token.transfer(relay1, 2_000_000 * 10**18);
        vm.prank(relay1);
        vm.expectRevert("No voting power"); // relay1 had 0 power at votingStart
        voting.vote(pid, true);

        // and a second hop is equally dead
        vm.prank(relay1);
        token.transfer(relay2, 2_000_000 * 10**18);
        vm.prank(relay2);
        vm.expectRevert("No voting power");
        voting.vote(pid, true);
    }

    function test_PowerGainedAfterCreationDoesNotVote() public {
        bytes32 pid = _propose(whale);
        // dust (zero power before creation) receives a big bag AFTER
        vm.prank(whale);
        token.transfer(dust, 100_000_000 * 10**18);
        vm.prank(dust);
        vm.expectRevert("No voting power");
        voting.vote(pid, true);
    }

    function test_DustProposerCannotOpen() public {
        vm.prank(dust);
        vm.expectRevert("Below proposal threshold");
        voting.createProposal("t", "t", "d", bytes(""), 7 days);
    }

    function test_SameBlockSameTitleKeepsBoth() public {
        bytes32 a = _propose(whale);
        bytes32 b = _propose(whale); // same sender, same timestamp, same title
        assertTrue(a != b, "second proposal must not overwrite the first");
        AITBCVoting.Proposal memory pa = voting.getProposal(a);
        AITBCVoting.Proposal memory pb = voting.getProposal(b);
        assertEq(pa.proposer, whale);
        assertEq(pb.proposer, whale);
    }

    function test_ExecuteRunsTheRealCall() public {
        bytes32 pid = _propose(whale);
        vm.prank(whale);
        voting.vote(pid, true);
        vm.warp(block.timestamp + 7 days + EXEC_DELAY());
        voting.executeProposal(pid);
        assertEq(target.calls(), 1, "the encoded call actually ran");
    }

    function test_ExecuteWithGarbageValueReverts() public {
        vm.prank(whale);
        bytes32 pid = voting.createProposal("t", "junk", "d", abi.encode("test_value"), 7 days);
        vm.prank(whale);
        voting.vote(pid, true);
        vm.warp(block.timestamp + 7 days + EXEC_DELAY());
        vm.expectRevert(); // undecodable value cannot be marked Executed
        voting.executeProposal(pid);
        AITBCVoting.Proposal memory p = voting.getProposal(pid);
        assertTrue(p.status != AITBCVoting.ProposalStatus.Executed);
    }

    function EXEC_DELAY() internal pure returns (uint256) {
        return 1 days + 1; // voting end + execution delay margin
    }
}
