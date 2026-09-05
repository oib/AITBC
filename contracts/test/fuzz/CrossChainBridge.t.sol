// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/CrossChainBridge.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockToken is ERC20 {
    constructor() ERC20("Mock Token", "MTK") {
        _mint(msg.sender, 1_000_000 * 10**18);
    }
}

contract CrossChainBridgeFuzzTest is Test {
    uint256 internal constant V1_PK = 0x1001;
    uint256 internal constant V2_PK = 0x1002;
    uint256 internal constant V3_PK = 0x1003;
    uint256 internal constant TARGET_CHAIN = 1; // added by constructor as Ethereum

    CrossChainBridge public bridge;
    MockToken public sourceToken;
    MockToken public targetToken;
    address public owner;
    address public feeRecipient;
    address public user;
    address public recipient;
    address public validator1;
    address public validator2;
    address public validator3;

    function setUp() public {
        owner = address(this);
        feeRecipient = address(0x10);
        user = address(0x20);
        recipient = address(0x30);
        validator1 = vm.addr(V1_PK);
        validator2 = vm.addr(V2_PK);
        validator3 = vm.addr(V3_PK);

        sourceToken = new MockToken();
        targetToken = new MockToken();
        bridge = new CrossChainBridge(feeRecipient);

        bridge.addSupportedToken(address(sourceToken), 500_000 * 10**18, 0, false);
        bridge.addValidator(validator1, 1);
        bridge.addValidator(validator2, 1);
        bridge.addValidator(validator3, 1);

        sourceToken.transfer(user, 400_000 * 10**18);
        targetToken.transfer(address(bridge), 400_000 * 10**18);
    }

    function _sign(uint256 pk, uint256 requestId, bytes32 lockTxHash) internal view returns (bytes memory) {
        bytes32 messageHash = keccak256(abi.encodePacked(requestId, lockTxHash, block.chainid));
        bytes32 ethSigned = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, ethSigned);
        return abi.encodePacked(r, s, v);
    }

    function _initiate(uint256 amount) internal returns (uint256 requestId) {
        vm.startPrank(user);
        sourceToken.approve(address(bridge), amount);
        requestId = bridge.initiateBridge(address(sourceToken), address(targetToken), amount, TARGET_CHAIN, recipient);
        vm.stopPrank();
    }

    function _initiateAndConfirm(uint256 amount) internal returns (uint256 requestId) {
        requestId = _initiate(amount);
        bytes32 lockTxHash = keccak256("lock-tx");
        vm.prank(validator1);
        bridge.confirmBridge(requestId, lockTxHash, _sign(V1_PK, requestId, lockTxHash));
        vm.prank(validator2);
        bridge.confirmBridge(requestId, lockTxHash, _sign(V2_PK, requestId, lockTxHash));
        vm.prank(validator3);
        bridge.confirmBridge(requestId, lockTxHash, _sign(V3_PK, requestId, lockTxHash));
    }

    // ---------- admin ----------

    function testFuzz_AddSupportedToken(address token, uint256 limit, uint256 fee) public {
        vm.assume(token != address(0));
        fee = bound(fee, 0, 500);

        bridge.addSupportedToken(token, limit, fee, false);
        (address tokenAddress, bool isActive, uint256 bridgeLimit, uint256 feePercentage, ) =
            bridge.supportedTokens(token);
        assertEq(tokenAddress, token);
        assertTrue(isActive);
        assertEq(bridgeLimit, limit);
        assertEq(feePercentage, fee);
    }

    function testFuzz_AddSupportedTokenRejectsHighFee(uint256 fee) public {
        vm.assume(fee > 500 && fee <= type(uint64).max);

        vm.expectRevert("Fee too high");
        bridge.addSupportedToken(address(0x99), 1000, fee, false);
    }

    function testFuzz_AddSupportedTokenRejectsZero() public {
        vm.expectRevert("Invalid token address");
        bridge.addSupportedToken(address(0), 1000, 0, false);
    }

    function testFuzz_AddSupportedTokenOnlyOwner(address caller) public {
        vm.assume(caller != owner);

        vm.prank(caller);
        vm.expectRevert("Ownable: caller is not the owner");
        bridge.addSupportedToken(address(0x99), 1000, 0, false);
    }

    function testFuzz_AddSupportedChain(uint256 chainId, string calldata name) public {
        vm.assume(chainId > 0);
        vm.assume(chainId != block.chainid);
        vm.assume(bytes(name).length <= 64);

        bridge.addSupportedChain(chainId, CrossChainBridge.ChainType.POLYGON, name, address(0), 1, 12);
        (, , , bool isActive, , , ) = bridge.supportedChains(chainId);
        assertTrue(isActive);
    }

    function testFuzz_AddSupportedChainRejectsCurrent() public {
        vm.expectRevert("Cannot add current chain");
        bridge.addSupportedChain(block.chainid, CrossChainBridge.ChainType.ETHEREUM, "self", address(0), 1, 12);
    }

    function testFuzz_AddValidatorOnlyOwner(address caller, address newValidator) public {
        vm.assume(caller != owner);
        vm.assume(newValidator != address(0));

        vm.prank(caller);
        vm.expectRevert("Ownable: caller is not the owner");
        bridge.addValidator(newValidator, 1);
    }

    function testFuzz_AddValidatorRejectsDuplicate() public {
        vm.expectRevert("Validator already exists");
        bridge.addValidator(validator1, 1);
    }

    function testFuzz_RemoveValidator(address newValidator) public {
        vm.assume(newValidator != address(0));
        vm.assume(newValidator != validator1 && newValidator != validator2 && newValidator != validator3);

        bridge.addValidator(newValidator, 1);
        bridge.removeValidator(newValidator);

        (, bool isActive, , , ) = bridge.validators(newValidator);
        assertFalse(isActive);
    }

    function testFuzz_RemoveValidatorRejectsInactive(address notValidator) public {
        vm.assume(notValidator != validator1 && notValidator != validator2 && notValidator != validator3);

        vm.expectRevert("Validator not active");
        bridge.removeValidator(notValidator);
    }

    function testFuzz_SetFeeRecipient(address newRecipient) public {
        vm.assume(newRecipient != address(0));

        bridge.setFeeRecipient(newRecipient);
        assertEq(bridge.feeRecipient(), newRecipient);
    }

    function testFuzz_SetFeeRecipientRejectsZero() public {
        vm.expectRevert("Invalid address");
        bridge.setFeeRecipient(address(0));
    }

    function testFuzz_UpdateMerkleRoot(bytes32 root) public {
        bridge.updateMerkleRoot(root);
        assertEq(bridge.merkleRoot(), root);
    }

    // ---------- initiate ----------

    function testFuzz_InitiateBridge(uint256 amount) public {
        amount = bound(amount, 1, 400_000 * 10**18);

        uint256 requestId = _initiate(amount);

        assertEq(requestId, 1);
        (uint256 srcChain, uint256 tgtChain, address srcToken, uint256 amt, address rcp, CrossChainBridge.BridgeStatus st,) =
            bridge.getBridgeRequest(requestId);
        assertEq(srcChain, block.chainid);
        assertEq(tgtChain, TARGET_CHAIN);
        assertEq(srcToken, address(sourceToken));
        assertEq(amt, amount);
        assertEq(rcp, recipient);
        assertEq(uint256(st), uint256(CrossChainBridge.BridgeStatus.PENDING));
        assertEq(bridge.totalBridgedAmount(), amount);

        uint256[] memory history = bridge.getUserBridgeHistory(user);
        assertEq(history.length, 1);
        assertEq(history[0], requestId);
    }

    function testFuzz_InitiateBridgeCollectsFee(uint256 amount, uint256 feePct) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        feePct = bound(feePct, 1, 500);
        uint256 fee = (amount * feePct) / 10000;
        vm.assume(fee > 0);

        bridge.addSupportedToken(address(sourceToken), 500_000 * 10**18, feePct, false);

        vm.startPrank(user);
        sourceToken.approve(address(bridge), amount + fee);
        bridge.initiateBridge(address(sourceToken), address(targetToken), amount, TARGET_CHAIN, recipient);
        vm.stopPrank();

        assertEq(sourceToken.balanceOf(feeRecipient), fee);
        assertEq(bridge.totalFeesCollected(), fee);
    }

    function testFuzz_InitiateRejectsUnsupportedToken(address token) public {
        vm.assume(token != address(sourceToken));

        vm.expectRevert("Token not supported");
        bridge.initiateBridge(token, address(targetToken), 1, TARGET_CHAIN, recipient);
    }

    function testFuzz_InitiateRejectsUnsupportedChain(uint256 chainId) public {
        vm.assume(chainId != TARGET_CHAIN);
        vm.assume(chainId != block.chainid);

        vm.expectRevert("Chain not supported");
        bridge.initiateBridge(address(sourceToken), address(targetToken), 1, chainId, recipient);
    }

    function testFuzz_InitiateRejectsOverLimit(uint256 amount) public {
        amount = bound(amount, 500_000 * 10**18 + 1, type(uint96).max);

        vm.expectRevert("Amount exceeds bridge limit");
        bridge.initiateBridge(address(sourceToken), address(targetToken), amount, TARGET_CHAIN, recipient);
    }

    function testFuzz_InitiateRejectsZeroRecipient(uint256 amount) public {
        amount = bound(amount, 1, 1000);

        vm.expectRevert("Invalid recipient");
        bridge.initiateBridge(address(sourceToken), address(targetToken), amount, TARGET_CHAIN, address(0));
    }

    function testFuzz_InitiateRejectsZeroAmount() public {
        vm.expectRevert("Amount must be greater than 0");
        bridge.initiateBridge(address(sourceToken), address(targetToken), 0, TARGET_CHAIN, recipient);
    }

    function testFuzz_InitiateRevertsWhenPaused(uint256 amount) public {
        amount = bound(amount, 1, 1000);

        bridge.pause();
        vm.expectRevert("Pausable: paused");
        bridge.initiateBridge(address(sourceToken), address(targetToken), amount, TARGET_CHAIN, recipient);
        bridge.unpause();
    }

    // ---------- confirm ----------

    function testFuzz_ConfirmBridgeThreeValidators(uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);

        uint256 requestId = _initiateAndConfirm(amount);

        (, , , , , CrossChainBridge.BridgeStatus st, ) = bridge.getBridgeRequest(requestId);
        assertEq(uint256(st), uint256(CrossChainBridge.BridgeStatus.CONFIRMED));
    }

    function testFuzz_ConfirmBridgePartialStaysPending(uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        uint256 requestId = _initiate(amount);

        bytes32 lockTxHash = keccak256("lock-tx");
        vm.prank(validator1);
        bridge.confirmBridge(requestId, lockTxHash, _sign(V1_PK, requestId, lockTxHash));

        (, , , , , CrossChainBridge.BridgeStatus st, ) = bridge.getBridgeRequest(requestId);
        assertEq(uint256(st), uint256(CrossChainBridge.BridgeStatus.PENDING));
    }

    function testFuzz_ConfirmBridgeRejectsDoubleConfirm(uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        uint256 requestId = _initiate(amount);

        bytes32 lockTxHash = keccak256("lock-tx");
        vm.startPrank(validator1);
        bridge.confirmBridge(requestId, lockTxHash, _sign(V1_PK, requestId, lockTxHash));
        vm.expectRevert("Already confirmed");
        bridge.confirmBridge(requestId, lockTxHash, _sign(V1_PK, requestId, lockTxHash));
        vm.stopPrank();
    }

    function testFuzz_ConfirmBridgeRejectsNonValidator(address caller, uint256 amount) public {
        vm.assume(caller != validator1 && caller != validator2 && caller != validator3);
        amount = bound(amount, 1, 100_000 * 10**18);
        uint256 requestId = _initiate(amount);

        vm.prank(caller);
        vm.expectRevert("Not an active validator");
        bridge.confirmBridge(requestId, keccak256("x"), "");
    }

    function testFuzz_ConfirmBridgeRejectsBadSignature(uint256 amount, uint256 badPk) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        badPk = bound(badPk, 1, type(uint160).max);
        address badSigner = vm.addr(badPk);
        vm.assume(badSigner != validator1 && badSigner != validator2 && badSigner != validator3);

        uint256 requestId = _initiate(amount);
        bytes32 lockTxHash = keccak256("lock-tx");

        vm.prank(validator1);
        vm.expectRevert("Invalid signature");
        bridge.confirmBridge(requestId, lockTxHash, _sign(badPk, requestId, lockTxHash));
    }

    function testFuzz_ConfirmBridgeRevertsAfterTimeout(uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        uint256 requestId = _initiate(amount);

        vm.warp(block.timestamp + 24 hours + 1);
        bytes32 lockTxHash = keccak256("lock-tx");
        vm.prank(validator1);
        vm.expectRevert("Bridge request expired");
        bridge.confirmBridge(requestId, lockTxHash, _sign(V1_PK, requestId, lockTxHash));
    }

    function testFuzz_ValidateBridgeRequest(uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        uint256 requestId = _initiate(amount);

        bytes32 lockTxHash = keccak256("lock-tx");
        assertTrue(bridge.validateBridgeRequest(requestId, lockTxHash, _sign(V1_PK, requestId, lockTxHash)));
        assertFalse(bridge.validateBridgeRequest(requestId, lockTxHash, _sign(0x9999, requestId, lockTxHash)));
    }

    // ---------- complete ----------

    function testFuzz_CompleteBridge(uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        uint256 requestId = _initiateAndConfirm(amount);

        bytes32 leaf = keccak256(abi.encodePacked(requestId, recipient, amount));
        bridge.updateMerkleRoot(leaf);

        vm.chainId(TARGET_CHAIN);
        bytes32[] memory proof = new bytes32[](0);
        bridge.completeBridge(requestId, keccak256("unlock-tx"), proof);

        assertEq(targetToken.balanceOf(recipient), amount);
        (, , , , , CrossChainBridge.BridgeStatus st, ) = bridge.getBridgeRequest(requestId);
        assertEq(uint256(st), uint256(CrossChainBridge.BridgeStatus.COMPLETED));
    }

    function testFuzz_CompleteBridgeRejectsWrongChain(uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        uint256 requestId = _initiateAndConfirm(amount);

        bytes32[] memory proof = new bytes32[](0);
        vm.expectRevert("Wrong chain");
        bridge.completeBridge(requestId, keccak256("unlock-tx"), proof);
    }

    function testFuzz_CompleteBridgeRejectsBadProof(uint256 amount, bytes32 wrongRoot) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        bytes32 leaf = keccak256(abi.encodePacked(uint256(1), recipient, amount));
        vm.assume(wrongRoot != leaf);

        uint256 requestId = _initiateAndConfirm(amount);
        bridge.updateMerkleRoot(wrongRoot);

        vm.chainId(TARGET_CHAIN);
        bytes32[] memory proof = new bytes32[](0);
        vm.expectRevert("Invalid Merkle proof");
        bridge.completeBridge(requestId, keccak256("unlock-tx"), proof);
    }

    function testFuzz_CompleteBridgeRejectsUnconfirmed(uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        uint256 requestId = _initiate(amount);

        vm.chainId(TARGET_CHAIN);
        bytes32[] memory proof = new bytes32[](0);
        vm.expectRevert("Request not confirmed");
        bridge.completeBridge(requestId, keccak256("unlock-tx"), proof);
    }

    // ---------- cancel ----------

    function testFuzz_CancelBridgeRefunds(uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        uint256 requestId = _initiate(amount); // token registered with fee = 0 in setUp

        uint256 before = sourceToken.balanceOf(user);
        vm.warp(block.timestamp + 24 hours + 1);
        vm.prank(user);
        bridge.cancelBridge(requestId, "timed out");

        assertEq(sourceToken.balanceOf(user), before + amount);
        (, , , , , CrossChainBridge.BridgeStatus st, ) = bridge.getBridgeRequest(requestId);
        assertEq(uint256(st), uint256(CrossChainBridge.BridgeStatus.CANCELLED));
    }

    function testFuzz_CancelBridgeRevertsBeforeTimeout(uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        uint256 requestId = _initiate(amount);

        vm.prank(user);
        vm.expectRevert("Bridge not expired");
        bridge.cancelBridge(requestId, "too early");
    }

    function testFuzz_CancelBridgeOnlySenderOrOwner(address caller, uint256 amount) public {
        vm.assume(caller != user && caller != owner);
        amount = bound(amount, 1, 100_000 * 10**18);
        uint256 requestId = _initiate(amount);

        vm.warp(block.timestamp + 24 hours + 1);
        vm.prank(caller);
        vm.expectRevert("Not authorized to cancel");
        bridge.cancelBridge(requestId, "nope");
    }

    /**
     * @dev Regression test: when a fee was charged, initiateBridge already forwarded
     *      it to feeRecipient, so cancelBridge must refund only `amount` (the
     *      previously written `amount + fee` always reverted on insufficient balance).
     */
    function testFuzz_CancelBridgeWithFeeRefundsAmount(uint256 amount, uint256 feePct) public {
        amount = bound(amount, 10_000, 100_000 * 10**18);
        feePct = bound(feePct, 1, 500);
        uint256 fee = (amount * feePct) / 10000;
        vm.assume(fee > 0);

        bridge.addSupportedToken(address(sourceToken), 500_000 * 10**18, feePct, false);

        vm.startPrank(user);
        sourceToken.approve(address(bridge), amount + fee);
        uint256 requestId = bridge.initiateBridge(
            address(sourceToken), address(targetToken), amount, TARGET_CHAIN, recipient
        );
        vm.stopPrank();

        uint256 before = sourceToken.balanceOf(user);
        vm.warp(block.timestamp + 24 hours + 1);
        vm.prank(user);
        bridge.cancelBridge(requestId, "timed out");

        assertEq(sourceToken.balanceOf(user), before + amount);
        (, , , , , CrossChainBridge.BridgeStatus st, ) = bridge.getBridgeRequest(requestId);
        assertEq(uint256(st), uint256(CrossChainBridge.BridgeStatus.CANCELLED));
    }

    // ---------- misc ----------

    function testFuzz_GetBridgeRequestRejectsInvalidId(uint256 requestId) public {
        vm.assume(requestId == 0 || requestId > bridge.requestCounter());

        vm.expectRevert("Invalid request ID");
        bridge.getBridgeRequest(requestId);
    }

    function testFuzz_EmergencyWithdraw(uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        _initiate(amount);

        uint256 before = sourceToken.balanceOf(owner);
        bridge.emergencyWithdraw(address(sourceToken), amount);
        assertEq(sourceToken.balanceOf(owner), before + amount);
    }

    function testFuzz_EmergencyWithdrawOnlyOwner(address caller, uint256 amount) public {
        vm.assume(caller != owner);
        amount = bound(amount, 1, 1000);

        vm.prank(caller);
        vm.expectRevert("Ownable: caller is not the owner");
        bridge.emergencyWithdraw(address(sourceToken), amount);
    }
}
