// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/DAOGovernanceEnhanced.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract DrainMockToken is ERC20 {
    constructor() ERC20("Mock Token", "MTK") {
        _mint(msg.sender, 1_000_000 * 10 ** 18);
    }
}

// A benign stand-in for an allowlisted integration contract.
contract MockTarget {
    uint256 public calls;

    function poke() external {
        calls++;
    }
}

/**
 * Pins issue #1110: a lone staker holding the default quorum must not be able
 * to propose, vote and execute a governanceToken.transfer to itself and drain
 * the staked-token balance. Before the fix there was no minimum voting
 * period, no execution delay and no target restriction, so the whole attack
 * completed in two blocks.
 */
contract DAOGovernanceEnhancedDrainTest is Test {
    DrainMockToken token;
    DAOGovernanceEnhanced dao;
    MockTarget target;

    address owner = address(this);
    address attacker = address(0xA77AC);
    address voter2 = address(0xB);
    address voter3 = address(0xC);

    uint256 constant MIN_STAKE = 100 * 10 ** 18;
    uint256 constant QUORUM = 1000 * 10 ** 18;

    function setUp() public {
        token = new DrainMockToken();
        dao = new DAOGovernanceEnhanced(address(token), MIN_STAKE);
        target = new MockTarget();
        dao.setTargetAllowed(address(target), true);

        token.transfer(attacker, 10_000 * 10 ** 18);
        token.transfer(voter2, 10_000 * 10 ** 18);
        token.transfer(voter3, 10_000 * 10 ** 18);
    }

    function _stake(address who, uint256 amount) internal {
        vm.startPrank(who);
        token.approve(address(dao), amount);
        dao.stake(amount);
        vm.stopPrank();
    }

    function testLoneQuorumHolderCannotDrainStakedTokens() public {
        // Attacker holds enough stake to meet the default quorum alone.
        _stake(attacker, QUORUM + MIN_STAKE);
        _stake(voter2, MIN_STAKE);
        uint256 daoBalance = token.balanceOf(address(dao));
        assertGt(daoBalance, 0);

        bytes memory steal = abi.encodeWithSignature(
            "transfer(address,uint256)", attacker, daoBalance
        );

        // The classic attack: period 0 + the governance token as target.
        vm.prank(attacker);
        vm.expectRevert(
            abi.encodeWithSelector(
                DAOGovernanceEnhanced.VotingPeriodOutOfBounds.selector, uint256(0)
            )
        );
        dao.createProposal("", "drain", 0, DAOGovernanceEnhanced.ProposalType.TREASURY_ALLOCATION, address(token), steal, 0);

        // A long period does not help: the governance token can never be a
        // proposal target, and the owner cannot allowlist it either.
        vm.prank(attacker);
        vm.expectRevert(
            abi.encodeWithSelector(DAOGovernanceEnhanced.TargetNotAllowed.selector, address(token))
        );
        dao.createProposal("", "drain", 7 days, DAOGovernanceEnhanced.ProposalType.TREASURY_ALLOCATION, address(token), steal, 0);

        vm.expectRevert("Governance token is not a proposal target");
        dao.setTargetAllowed(address(token), true);

        // An arbitrary un-allowlisted contract is refused the same way.
        vm.prank(attacker);
        vm.expectRevert(
            abi.encodeWithSelector(DAOGovernanceEnhanced.TargetNotAllowed.selector, attacker)
        );
        dao.createProposal("", "drain", 7 days, DAOGovernanceEnhanced.ProposalType.TREASURY_ALLOCATION, attacker, steal, 0);

        // The staked balance never moved.
        assertEq(token.balanceOf(address(dao)), daoBalance);
        assertEq(token.balanceOf(attacker), 10_000 * 10 ** 18 - QUORUM - MIN_STAKE);
    }

    function testVotingPeriodBounds() public {
        _stake(attacker, MIN_STAKE);
        vm.startPrank(attacker);
        vm.expectRevert(
            abi.encodeWithSelector(
                DAOGovernanceEnhanced.VotingPeriodOutOfBounds.selector, uint256(1 days - 1)
            )
        );
        dao.createProposal("", "x", 1 days - 1, DAOGovernanceEnhanced.ProposalType.PARAMETER_CHANGE, address(0), "", 0);
        vm.expectRevert(
            abi.encodeWithSelector(
                DAOGovernanceEnhanced.VotingPeriodOutOfBounds.selector, uint256(30 days + 1)
            )
        );
        dao.createProposal("", "x", 30 days + 1, DAOGovernanceEnhanced.ProposalType.PARAMETER_CHANGE, address(0), "", 0);
        vm.stopPrank();
    }

    function testExecutionWaitsForTimelock() public {
        _stake(attacker, QUORUM);
        vm.roll(block.number + 1);
        vm.prank(attacker);
        uint256 pid = dao.createProposal(
            "", "poke", 1 days, DAOGovernanceEnhanced.ProposalType.PARAMETER_CHANGE, address(target),
            abi.encodeWithSignature("poke()"), 0
        );

        vm.prank(attacker);
        dao.castVote(pid, 1);

        // Voting over but timelock still running: execute must refuse.
        vm.warp(block.timestamp + 1 days + 1);
        vm.expectRevert(
            abi.encodeWithSelector(
                DAOGovernanceEnhanced.TimelockNotExpired.selector, uint256(block.timestamp - 1 + dao.executionDelay())
            )
        );
        dao.executeProposal(pid);

        // Past the delay a quorum-passing proposal executes normally.
        vm.warp(block.timestamp + dao.executionDelay());
        dao.executeProposal(pid);
        assertEq(target.calls(), 1);
    }

    function testStakeAfterSnapshotCannotVote() public {
        _stake(voter2, MIN_STAKE);
        vm.roll(block.number + 1);
        vm.prank(voter2);
        uint256 pid = dao.createProposal(
            "", "x", 1 days, DAOGovernanceEnhanced.ProposalType.PARAMETER_CHANGE, address(0), "", 0
        );

        // voter3 had no stake when the proposal opened: staking now does not
        // buy a vote on it.
        _stake(voter3, QUORUM);
        vm.prank(voter3);
        vm.expectRevert(
            abi.encodeWithSelector(DAOGovernanceEnhanced.StakeAfterSnapshot.selector, pid, voter3)
        );
        dao.castVote(pid, 1);

        // voter2's pre-snapshot stake still votes.
        vm.prank(voter2);
        dao.castVote(pid, 1);
    }

    function testRegionalProposalUsesCouncilVoteCount() public {
        dao.setRegionalCouncilMember("eu", voter2, true);
        dao.setRegionalCouncilMember("eu", voter3, true);
        _stake(voter2, MIN_STAKE);
        _stake(voter3, MIN_STAKE);

        vm.prank(voter2);
        uint256 pid = dao.createProposal(
            "eu", "regional", 1 days, DAOGovernanceEnhanced.ProposalType.PARAMETER_CHANGE, address(0), "", 0
        );

        // One council vote (weight 1) is below regionalQuorum (2): defeated.
        vm.prank(voter2);
        dao.castVote(pid, 1);
        vm.warp(block.timestamp + 1 days + dao.executionDelay() + 1);
        dao.executeProposal(pid);
        (, , DAOGovernanceEnhanced.ProposalState state, , , , , , ) = dao.getProposalInfo(pid);
        assertEq(uint256(state), uint256(DAOGovernanceEnhanced.ProposalState.Defeated));

        // Two council votes reach it.
        vm.prank(voter2);
        uint256 pid2 = dao.createProposal(
            "eu", "regional2", 1 days, DAOGovernanceEnhanced.ProposalType.PARAMETER_CHANGE, address(0), "", 0
        );
        vm.prank(voter2);
        dao.castVote(pid2, 1);
        vm.prank(voter3);
        dao.castVote(pid2, 1);
        vm.warp(block.timestamp + 1 days + dao.executionDelay() + 1);
        dao.executeProposal(pid2);
        (, , state, , , , , , ) = dao.getProposalInfo(pid2);
        assertEq(uint256(state), uint256(DAOGovernanceEnhanced.ProposalState.Executed));
    }

    function testSubmitCrossChainProposalDoesNotRevertOnNestedGuard() public {
        // _createCrossChainProposal used to carry its own nonReentrant, so the
        // call reverted under OZ 4.9 before reaching any logic (issue #1111).
        _stake(attacker, MIN_STAKE);
        vm.prank(attacker);
        uint256 pid = dao.submitCrossChainProposal(1, bytes32(uint256(1)), "cc");
        assertGt(pid, 0);
    }
}
