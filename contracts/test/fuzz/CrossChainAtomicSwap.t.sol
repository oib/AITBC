// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/CrossChainAtomicSwap.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockToken is ERC20 {
    constructor() ERC20("Mock Token", "MTK") {
        _mint(msg.sender, 1_000_000 * 10**18);
    }
}

contract CrossChainAtomicSwapFuzzTest is Test {
    CrossChainAtomicSwap public swap;
    MockToken public token;
    address public initiator;
    address public participant;

    function setUp() public {
        initiator = address(0x1);
        participant = address(0x2);

        token = new MockToken();
        swap = new CrossChainAtomicSwap();

        token.transfer(initiator, 500_000 * 10**18);
        vm.deal(initiator, 100 ether);
    }

    function _initiateErc20(bytes32 swapId, uint256 amount, bytes32 hashlock) internal returns (uint256 timelock) {
        timelock = block.timestamp + 1 hours;
        vm.startPrank(initiator);
        token.approve(address(swap), amount);
        swap.initiateSwap(swapId, participant, address(token), amount, hashlock, timelock);
        vm.stopPrank();
    }

    function testFuzz_InitiateSwapErc20(bytes32 swapId, uint256 amount, bytes32 hashlock) public {
        amount = bound(amount, 1, 400_000 * 10**18);

        _initiateErc20(swapId, amount, hashlock);

        (address init, address part, address tok, uint256 amt, bytes32 lock, , CrossChainAtomicSwap.SwapStatus status) =
            swap.swaps(swapId);
        assertEq(init, initiator);
        assertEq(part, participant);
        assertEq(tok, address(token));
        assertEq(amt, amount);
        assertEq(lock, hashlock);
        assertEq(uint256(status), uint256(CrossChainAtomicSwap.SwapStatus.OPEN));
        assertEq(token.balanceOf(address(swap)), amount);
    }

    function testFuzz_InitiateSwapNative(bytes32 swapId, uint256 amount, bytes32 hashlock) public {
        amount = bound(amount, 1, 50 ether);

        vm.prank(initiator);
        swap.initiateSwap{value: amount}(swapId, participant, address(0), amount, hashlock, block.timestamp + 1 hours);

        assertEq(address(swap).balance, amount);
    }

    function testFuzz_InitiateSwapRejectsDuplicateId(bytes32 swapId, uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        _initiateErc20(swapId, amount, bytes32(uint256(1)));

        vm.startPrank(initiator);
        token.approve(address(swap), amount);
        vm.expectRevert("Swap ID already exists");
        swap.initiateSwap(swapId, participant, address(token), amount, bytes32(uint256(2)), block.timestamp + 1 hours);
        vm.stopPrank();
    }

    function testFuzz_InitiateSwapRejectsPastTimelock(bytes32 swapId, uint256 timelock) public {
        vm.assume(timelock <= block.timestamp);

        vm.expectRevert("Timelock must be in the future");
        swap.initiateSwap(swapId, participant, address(token), 1, bytes32(0), timelock);
    }

    function testFuzz_InitiateSwapRejectsZeroAmount(bytes32 swapId) public {
        vm.expectRevert("Amount must be > 0");
        swap.initiateSwap(swapId, participant, address(token), 0, bytes32(0), block.timestamp + 1 hours);
    }

    function testFuzz_InitiateSwapRejectsZeroParticipant(bytes32 swapId) public {
        vm.expectRevert("Invalid participant");
        swap.initiateSwap(swapId, address(0), address(token), 1, bytes32(0), block.timestamp + 1 hours);
    }

    function testFuzz_InitiateSwapRejectsMismatchedNativeValue(bytes32 swapId, uint256 amount) public {
        amount = bound(amount, 1, 50 ether);

        vm.prank(initiator);
        vm.expectRevert("Incorrect ETH amount sent");
        swap.initiateSwap{value: amount - 1}(swapId, participant, address(0), amount, bytes32(0), block.timestamp + 1 hours);
    }

    function testFuzz_InitiateSwapRejectsEthWithToken(bytes32 swapId, uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);

        vm.startPrank(initiator);
        token.approve(address(swap), amount);
        vm.expectRevert("ETH sent but ERC20 token specified");
        swap.initiateSwap{value: 1}(swapId, participant, address(token), amount, bytes32(0), block.timestamp + 1 hours);
        vm.stopPrank();
    }

    function testFuzz_CompleteSwap(bytes32 swapId, bytes32 secret, uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        bytes32 hashlock = sha256(abi.encodePacked(secret));
        _initiateErc20(swapId, amount, hashlock);

        swap.completeSwap(swapId, secret);

        assertEq(token.balanceOf(participant), amount);
        (, , , , , , CrossChainAtomicSwap.SwapStatus status) = swap.swaps(swapId);
        assertEq(uint256(status), uint256(CrossChainAtomicSwap.SwapStatus.COMPLETED));
    }

    function testFuzz_CompleteSwapNative(bytes32 swapId, bytes32 secret, uint256 amount) public {
        amount = bound(amount, 1, 50 ether);
        bytes32 hashlock = sha256(abi.encodePacked(secret));

        vm.prank(initiator);
        swap.initiateSwap{value: amount}(swapId, participant, address(0), amount, hashlock, block.timestamp + 1 hours);

        uint256 before = participant.balance;
        swap.completeSwap(swapId, secret);
        assertEq(participant.balance, before + amount);
    }

    function testFuzz_CompleteSwapRejectsWrongSecret(bytes32 swapId, bytes32 secret, bytes32 wrongSecret, uint256 amount)
        public
    {
        vm.assume(sha256(abi.encodePacked(wrongSecret)) != sha256(abi.encodePacked(secret)));
        amount = bound(amount, 1, 100_000 * 10**18);
        _initiateErc20(swapId, amount, sha256(abi.encodePacked(secret)));

        vm.expectRevert("Invalid secret");
        swap.completeSwap(swapId, wrongSecret);
    }

    function testFuzz_CompleteSwapRevertsAfterExpiry(bytes32 swapId, bytes32 secret, uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        uint256 timelock = _initiateErc20(swapId, amount, sha256(abi.encodePacked(secret)));

        vm.warp(timelock);
        vm.expectRevert("Swap timelock expired");
        swap.completeSwap(swapId, secret);
    }

    function testFuzz_RefundSwap(bytes32 swapId, uint256 amount, bytes32 hashlock) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        uint256 timelock = _initiateErc20(swapId, amount, hashlock);

        vm.warp(timelock);
        uint256 before = token.balanceOf(initiator);
        swap.refundSwap(swapId);

        assertEq(token.balanceOf(initiator), before + amount);
        (, , , , , , CrossChainAtomicSwap.SwapStatus status) = swap.swaps(swapId);
        assertEq(uint256(status), uint256(CrossChainAtomicSwap.SwapStatus.REFUNDED));
    }

    function testFuzz_RefundSwapNative(bytes32 swapId, uint256 amount, bytes32 hashlock) public {
        amount = bound(amount, 1, 50 ether);

        vm.prank(initiator);
        swap.initiateSwap{value: amount}(swapId, participant, address(0), amount, hashlock, block.timestamp + 1 hours);

        uint256 before = initiator.balance;
        vm.warp(block.timestamp + 1 hours + 1);
        swap.refundSwap(swapId);
        assertEq(initiator.balance, before + amount);
    }

    function testFuzz_RefundRevertsBeforeExpiry(bytes32 swapId, uint256 amount, bytes32 hashlock) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        _initiateErc20(swapId, amount, hashlock);

        vm.expectRevert("Swap timelock not yet expired");
        swap.refundSwap(swapId);
    }

    function testFuzz_CompleteRevertsIfNotOpen(bytes32 swapId, bytes32 secret) public {
        vm.expectRevert("Swap is not open");
        swap.completeSwap(swapId, secret);
    }

    function testFuzz_DoubleCompleteReverts(bytes32 swapId, bytes32 secret, uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        _initiateErc20(swapId, amount, sha256(abi.encodePacked(secret)));
        swap.completeSwap(swapId, secret);

        vm.expectRevert("Swap is not open");
        swap.completeSwap(swapId, secret);
    }
}
