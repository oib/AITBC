// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../src/AgentDAO.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/governance/utils/IVotes.sol";

/// Minimal IVotes token: checkpointed power = balance recorded at mint.
/// The DAO's GovernorVotes base requires an IVotes token (#1117).
contract MockVotesToken is IERC20, IVotes {
    string public constant name = "Mock";
    string public constant symbol = "MCK";
    uint8 public constant decimals = 18;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    mapping(address => uint256[]) _ckBlocks;
    mapping(address => uint256[]) _ckVotes;
    uint256[] _supBlocks;
    uint256[] _supValues;

    function _checkpointVotes(address acct) internal {
        _ckBlocks[acct].push(block.number);
        _ckVotes[acct].push(balanceOf[acct]);
        _supBlocks.push(block.number);
        _supValues.push(totalSupply);
    }

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        totalSupply += amount;
        _checkpointVotes(to);
    }
    function transfer(address to, uint256 amount) external returns (bool) {
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        _checkpointVotes(to);
        return true;
    }
    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }
    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
    // IVotes
    function clock() public view returns (uint48) { return uint48(block.number); }
    function CLOCK_MODE() public pure returns (string memory) { return "mode=blocknumber"; }
    function getVotes(address account) external view returns (uint256) { return balanceOf[account]; }
    function getPastVotes(address account, uint256 blockNumber) public view returns (uint256) {
        require(blockNumber < block.number, "future lookup");
        uint256[] storage votes = _ckVotes[account];
        uint256[] storage blocks = _ckBlocks[account];
        uint256 i = blocks.length;
        while (i > 0) {
            if (blocks[i - 1] <= blockNumber) return votes[i - 1];
            i--;
        }
        return 0;
    }
    function getPastTotalSupply(uint256 blockNumber) external view returns (uint256) {
        uint256 i = _supBlocks.length;
        while (i > 0) {
            if (_supBlocks[i - 1] <= blockNumber) return _supValues[i - 1];
            i--;
        }
        return 0;
    }
    function delegates(address account) external pure returns (address) { return account; }
    function delegate(address) external pure {}
    function delegateBySig(address, uint256, uint256, uint8, bytes32, bytes32) external pure {}
}

contract AgentDAO1117Test is Test {
    MockVotesToken token;
    TimelockController timelock;
    AgentDAO dao;
    address voter = address(0x11);
    address noPower = address(0x22);

    function setUp() public {
        token = new MockVotesToken();
        address[] memory proposers = new address[](1);
        proposers[0] = address(this);
        address[] memory executors = new address[](1);
        executors[0] = address(0);
        timelock = new TimelockController(0, proposers, executors, address(this));
        dao = new AgentDAO(address(token), timelock);
        timelock.grantRole(timelock.PROPOSER_ROLE(), address(dao));

        // voter holds 4% (< 5% cap); filler holders make up quorum supply
        token.mint(voter, 4_000e18);
        token.mint(address(0x99), 96_000e18);
        vm.roll(block.number + 1); // power must be strictly before the snapshot
    }

    function _propose(AgentDAO.ProposalType t) internal returns (uint256 pid) {
        address[] memory targets = new address[](1);
        targets[0] = address(this);
        uint256[] memory values = new uint256[](1);
        bytes[] memory calldatas = new bytes[](1);
        calldatas[0] = "";
        vm.startPrank(voter);
        token.approve(address(dao), 1000e18);
        pid = dao.propose(targets, values, calldatas, "test", t);
        vm.stopPrank();
    }

    // Pin 1: the dead vote path — snapshot power is real now, so a vote
    // through the custom entrypoint actually succeeds.
    function test_VoteSucceedsWithRealSnapshotPower() public {
        uint256 pid = _propose(AgentDAO.ProposalType.PARAMETER_CHANGE);
        vm.roll(block.number + 86401);
        vm.prank(voter);
        uint256 votes = dao.castVoteWithReason(pid, 1, "yes");
        assertGt(votes, 0);
    }

    // Pin 2a: inherited castVote is not a bypass — a challenged proposal
    // still refuses a vote through it.
    function test_InheritedCastVoteHonorsChallengeFreeze() public {
        uint256 pid = _propose(AgentDAO.ProposalType.PARAMETER_CHANGE);
        vm.prank(voter);
        token.approve(address(dao), 1000e18);
        vm.prank(voter);
        dao.challengeProposal(pid);
        vm.roll(block.number + 86401);
        vm.prank(voter);
        vm.expectRevert("Proposal challenged");
        dao.castVote(pid, 1);
    }

    // Pin 2b: inherited castVote still enforces real snapshot power.
    function test_InheritedCastVoteRejectsNoPower() public {
        uint256 pid = _propose(AgentDAO.ProposalType.PARAMETER_CHANGE);
        vm.roll(block.number + 86401);
        vm.prank(noPower);
        vm.expectRevert("No voting power");
        dao.castVote(pid, 1);
    }

    // Pin 3: the multi-sig count is real — an EMERGENCY execute needs
    // three distinct signer approvals, not a hard-coded 0.
    function test_MultiSigCountGatesEmergencyExecute() public {
        uint256 pid = _propose(AgentDAO.ProposalType.EMERGENCY_ACTION);
        assertEq(dao.getMultiSigApprovals(pid), 0);
        dao.addMultiSigSigner(address(0xA1));
        dao.addMultiSigSigner(address(0xA2));
        vm.prank(address(0xA1));
        dao.approveMultiSig(pid);
        vm.prank(address(0xA1));
        vm.expectRevert("Already approved");
        dao.approveMultiSig(pid); // no double-count
        assertEq(dao.getMultiSigApprovals(pid), 1);
        vm.prank(address(0xA2));
        dao.approveMultiSig(pid);
        dao.approveMultiSig(pid); // deployer is signer #3
        assertEq(dao.getMultiSigApprovals(pid), 3);
    }
}
