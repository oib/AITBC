// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/CrossChainBridge.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract OwnerSafeMockToken is ERC20 {
    constructor() ERC20("Mock Token", "MTK") {
        _mint(msg.sender, 1_000_000 * 10**18);
    }
}

/**
 * @dev Minimal 2-of-3 multisig standing in for a Safe owner. Faithful to the
 * real contract in the ways that matter to the bridge: owner() is a contract
 * (no private key can act directly), every call needs two ECDSA signatures
 * from distinct owners presented in ascending signer order (the real Safe
 * sorts signers too), and a per-tx nonce gives replay protection.
 */
contract MockSafe {
    address public immutable owner1;
    address public immutable owner2;
    address public immutable owner3;
    uint256 public nonce;

    constructor(address a, address b, address c) {
        require(a < b && b < c, "owners sorted ascending");
        owner1 = a;
        owner2 = b;
        owner3 = c;
    }

    function isOwner(address a) public view returns (bool) {
        return a == owner1 || a == owner2 || a == owner3;
    }

    /**
     * @param signatures two packed (r,s,v) sigs over the tx hash; signers
     * must be distinct owners in ascending address order.
     */
    function execTransaction(address to, bytes memory data, bytes memory signatures)
        external
        returns (bool)
    {
        require(signatures.length == 130, "need exactly 2 signatures");
        bytes32 txHash = keccak256(abi.encodePacked(address(this), nonce, to, keccak256(data)));
        bytes32 ethSigned = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", txHash));

        address prev = address(0);
        for (uint256 i = 0; i < 2; i++) {
            bytes32 r;
            bytes32 s;
            uint8 v;
            uint256 off;
            assembly {
                off := add(signatures, add(32, mul(i, 65)))
                r := mload(off)
                s := mload(add(off, 32))
                v := byte(0, mload(add(off, 64)))
            }
            address signer = ecrecover(ethSigned, v, r, s);
            require(isOwner(signer), "not an owner");
            require(signer > prev, "signers must be distinct and ascending");
            prev = signer;
        }
        nonce++;

        (bool ok, bytes memory ret) = to.call(data);
        if (!ok) {
            assembly {
                revert(add(ret, 32), mload(ret))
            }
        }
        return true;
    }

    receive() external payable {}
}

contract CrossChainBridgeOwnerSafeTest is Test {
    uint256 internal constant V1_PK = 0x1001;
    uint256 internal constant V2_PK = 0x1002;
    uint256 internal constant V3_PK = 0x1003;
    uint256 internal constant S1_PK = 0xA1;
    uint256 internal constant S2_PK = 0xB2;
    uint256 internal constant S3_PK = 0xC3;
    uint256 internal constant TARGET_CHAIN = 1;

    CrossChainBridge public bridge;
    MockSafe public safe;
    OwnerSafeMockToken public sourceToken;
    OwnerSafeMockToken public targetToken;

    address public deployer;
    address public feeRecipient = address(0x10);
    address public user = address(0x20);
    address public recipient = address(0x30);
    address public outsider = address(0x40);
    address public validator1;
    address public validator2;
    address public validator3;

    // safe signer pubkeys, kept in ascending address order
    uint256[3] public signerPks;

    function setUp() public {
        deployer = address(this);
        validator1 = vm.addr(V1_PK);
        validator2 = vm.addr(V2_PK);
        validator3 = vm.addr(V3_PK);

        // order the three safe signer keys by derived address (ascending),
        // the same ordering execTransaction requires of the signatures
        uint256[3] memory pks = [S1_PK, S2_PK, S3_PK];
        for (uint256 i = 0; i < 3; i++) {
            for (uint256 j = i + 1; j < 3; j++) {
                if (vm.addr(pks[j]) < vm.addr(pks[i])) {
                    (pks[i], pks[j]) = (pks[j], pks[i]);
                }
            }
        }
        signerPks = pks;

        safe = new MockSafe(vm.addr(pks[0]), vm.addr(pks[1]), vm.addr(pks[2]));
        sourceToken = new OwnerSafeMockToken();
        targetToken = new OwnerSafeMockToken();
        bridge = new CrossChainBridge(feeRecipient);

        // token/target-chain plumbing a deployment would do as owner
        bridge.addSupportedToken(address(sourceToken), 500_000 * 10**18, 0, false);
        bridge.addValidator(validator1, 1);
        bridge.addValidator(validator2, 1);
        bridge.addValidator(validator3, 1);

        sourceToken.transfer(user, 400_000 * 10**18);
        targetToken.transfer(address(bridge), 400_000 * 10**18);
    }

    // ---------- helpers ----------

    function _safeTxHash(address to, bytes memory data) internal view returns (bytes32) {
        bytes32 h = keccak256(abi.encodePacked(address(safe), safe.nonce(), to, keccak256(data)));
        return keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", h));
    }

    /// two signatures over the current safe nonce for (to, data); signers are
    /// the two lowest-numbered keys — their addresses are already ascending
    function _twoSigs(address to, bytes memory data) internal view returns (bytes memory) {
        bytes32 h = _safeTxHash(to, data);
        (uint8 v1, bytes32 r1, bytes32 s1) = vm.sign(signerPks[0], h);
        (uint8 v2, bytes32 r2, bytes32 s2) = vm.sign(signerPks[1], h);
        return abi.encodePacked(r1, s1, v1, r2, s2, v2);
    }

    function _twoSigsFor(address to, bytes memory data, uint256 pkA, uint256 pkB)
        internal
        view
        returns (bytes memory)
    {
        bytes32 h = _safeTxHash(to, data);
        (uint8 va, bytes32 ra, bytes32 sa) = vm.sign(pkA, h);
        (uint8 vb, bytes32 rb, bytes32 sb) = vm.sign(pkB, h);
        // order by signer address, as execTransaction requires
        if (vm.addr(pkA) < vm.addr(pkB)) {
            return abi.encodePacked(ra, sa, va, rb, sb, vb);
        }
        return abi.encodePacked(rb, sb, vb, ra, sa, va);
    }

    function _exec(address to, bytes memory data) internal {
        safe.execTransaction(to, data, _twoSigs(to, data));
    }

    // ---------- 1. owner-path matrix: every onlyOwner fn rejected for a non-owner ----------

    function test_OnlyOwnerCallsRejectedForNonOwner() public {
        address target = address(bridge);
        bytes[] memory calls = new bytes[](12);
        calls[0] = abi.encodeCall(CrossChainBridge.addSupportedToken, (address(0x99), 1000, 0, false));
        calls[1] = abi.encodeCall(
            CrossChainBridge.addSupportedChain, (uint256(56), CrossChainBridge.ChainType.BSC, "bsc", address(0), 1, 3)
        );
        calls[2] = abi.encodeCall(CrossChainBridge.addValidator, (address(0x77), 1));
        calls[3] = abi.encodeCall(CrossChainBridge.removeValidator, (validator1));
        calls[4] = abi.encodeCall(CrossChainBridge.updateMerkleRoot, (bytes32(uint256(1))));
        calls[5] = abi.encodeCall(CrossChainBridge.setFeeRecipient, (address(0x66)));
        calls[6] = abi.encodeCall(CrossChainBridge.pause, ());
        calls[7] = abi.encodeCall(CrossChainBridge.unpause, ());
        calls[8] = abi.encodeCall(CrossChainBridge.emergencyWithdraw, (address(sourceToken), 1));
        calls[9] = abi.encodeCall(CrossChainBridge.emergencyPause, ());
        calls[10] = abi.encodeCall(Ownable.transferOwnership, (outsider));
        calls[11] = abi.encodeCall(Ownable.renounceOwnership, ());

        for (uint256 i = 0; i < calls.length; i++) {
            vm.prank(outsider);
            (bool ok, ) = target.call(calls[i]);
            assertFalse(ok, string.concat("onlyOwner call ", vm.toString(i), " succeeded for non-owner"));
        }
    }

    // ---------- 2. multisig owner: safe controls every admin path ----------

    function test_SafeOwnerRunsEveryAdminFunction() public {
        // hand the bridge to the 2-of-3 safe
        bridge.transferOwnership(address(safe));
        assertEq(bridge.owner(), address(safe));

        // the old EOA owner is now powerless on every path
        bytes[] memory calls = new bytes[](4);
        calls[0] = abi.encodeCall(CrossChainBridge.addValidator, (address(0x77), 1));
        calls[1] = abi.encodeCall(CrossChainBridge.pause, ());
        calls[2] = abi.encodeCall(CrossChainBridge.updateMerkleRoot, (bytes32(uint256(9))));
        calls[3] = abi.encodeCall(CrossChainBridge.emergencyWithdraw, (address(sourceToken), 1));
        for (uint256 i = 0; i < calls.length; i++) {
            (bool ok, ) = address(bridge).call(calls[i]);
            assertFalse(ok, "former EOA owner still has power");
        }

        // each admin call routed through the safe with 2 of 3 signatures
        _exec(address(bridge), abi.encodeCall(CrossChainBridge.addValidator, (address(0x77), 5)));
        (address vaddr, bool isActive, uint256 weight, , ) = bridge.validators(address(0x77));
        assertTrue(isActive);
        assertEq(vaddr, address(0x77));
        assertEq(weight, 5);

        _exec(address(bridge), abi.encodeCall(CrossChainBridge.removeValidator, (address(0x77))));
        (, bool stillActive, , , ) = bridge.validators(address(0x77));
        assertFalse(stillActive);

        _exec(
            address(bridge),
            abi.encodeCall(CrossChainBridge.addSupportedToken, (address(targetToken), 1000 * 10**18, 25, false))
        );
        (address ta, bool tActive, uint256 tLimit, uint256 tFee, ) = bridge.supportedTokens(address(targetToken));
        assertTrue(tActive);
        assertEq(ta, address(targetToken));
        assertEq(tFee, 25);

        _exec(
            address(bridge),
            abi.encodeCall(
                CrossChainBridge.addSupportedChain, (uint256(56), CrossChainBridge.ChainType.BSC, "bsc", address(0), 1, 3)
            )
        );
        (, , , bool cActive, , , ) = bridge.supportedChains(56);
        assertTrue(cActive);

        _exec(address(bridge), abi.encodeCall(CrossChainBridge.updateMerkleRoot, (bytes32(uint256(42)))));
        assertEq(bridge.merkleRoot(), bytes32(uint256(42)));

        _exec(address(bridge), abi.encodeCall(CrossChainBridge.setFeeRecipient, (address(0x66))));
        assertEq(bridge.feeRecipient(), address(0x66));
        // restore for the round-trip test's fee assertions
        _exec(address(bridge), abi.encodeCall(CrossChainBridge.setFeeRecipient, (feeRecipient)));

        _exec(address(bridge), abi.encodeCall(CrossChainBridge.pause, ()));
        assertTrue(bridge.paused());
        _exec(address(bridge), abi.encodeCall(CrossChainBridge.unpause, ()));
        assertFalse(bridge.paused());

        _exec(address(bridge), abi.encodeCall(CrossChainBridge.emergencyPause, ()));
        assertTrue(bridge.paused());
        _exec(address(bridge), abi.encodeCall(CrossChainBridge.unpause, ()));

        // emergencyWithdraw lands the tokens AT the safe — reachable, not burned
        uint256 amt = 500 * 10**18;
        _exec(address(bridge), abi.encodeCall(CrossChainBridge.emergencyWithdraw, (address(targetToken), amt)));
        assertEq(targetToken.balanceOf(address(safe)), amt);

        // ownership can leave the safe again via the safe itself
        _exec(address(bridge), abi.encodeCall(Ownable.transferOwnership, (deployer)));
        assertEq(bridge.owner(), deployer);
    }

    // ---------- 3. the safe itself enforces 2-of-3 ----------

    function test_SafeRejectsSingleSignature() public {
        bridge.transferOwnership(address(safe));
        bytes memory data = abi.encodeCall(CrossChainBridge.pause, ());
        bytes32 h = _safeTxHash(address(bridge), data);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerPks[0], h);
        bytes memory oneSig = abi.encodePacked(r, s, v);
        vm.expectRevert("need exactly 2 signatures");
        safe.execTransaction(address(bridge), data, oneSig);
        assertFalse(bridge.paused());
    }

    function test_SafeRejectsNonOwnerSignature() public {
        bridge.transferOwnership(address(safe));
        bytes memory data = abi.encodeCall(CrossChainBridge.pause, ());
        // signerPks[0] + an outsider key (pk 0xDEAD)
        bytes memory sigs = _twoSigsFor(address(bridge), data, signerPks[0], 0xDEAD);
        vm.expectRevert("not an owner");
        safe.execTransaction(address(bridge), data, sigs);
    }

    function test_SafeRejectsDuplicateSigner() public {
        bridge.transferOwnership(address(safe));
        bytes memory data = abi.encodeCall(CrossChainBridge.pause, ());
        bytes memory sigs = _twoSigsFor(address(bridge), data, signerPks[0], signerPks[0]);
        vm.expectRevert("signers must be distinct and ascending");
        safe.execTransaction(address(bridge), data, sigs);
    }

    function test_SafeReplayProtection() public {
        bridge.transferOwnership(address(safe));
        bytes memory data = abi.encodeCall(CrossChainBridge.pause, ());
        bytes memory sigs = _twoSigs(address(bridge), data);
        safe.execTransaction(address(bridge), data, sigs);
        assertTrue(bridge.paused());
        // same signed bundle must not execute twice (nonce moved on)
        vm.expectRevert("not an owner");
        safe.execTransaction(address(bridge), data, sigs);
    }

    // ---------- 4. deposit → withdraw round trip under multisig ownership ----------

    function _signValidator(uint256 pk, uint256 requestId, bytes32 lockTxHash) internal view returns (bytes memory) {
        bytes32 messageHash = keccak256(abi.encodePacked(requestId, lockTxHash, block.chainid));
        bytes32 ethSigned = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, ethSigned);
        return abi.encodePacked(r, s, v);
    }

    function test_DepositWithdrawRoundTrip_SafeOwned() public {
        // bridge owned by the 2-of-3 safe for the whole lifecycle
        bridge.transferOwnership(address(safe));

        uint256 amount = 1_000 * 10**18;
        // deposit: user locks sourceToken on this chain
        vm.startPrank(user);
        sourceToken.approve(address(bridge), amount);
        uint256 requestId =
            bridge.initiateBridge(address(sourceToken), address(targetToken), amount, TARGET_CHAIN, recipient);
        vm.stopPrank();

        assertEq(sourceToken.balanceOf(address(bridge)), amount);
        assertEq(sourceToken.balanceOf(user), 400_000 * 10**18 - amount);

        // validators confirm the lock
        bytes32 lockTxHash = keccak256("lock-tx");
        vm.prank(validator1);
        bridge.confirmBridge(requestId, lockTxHash, _signValidator(V1_PK, requestId, lockTxHash));
        vm.prank(validator2);
        bridge.confirmBridge(requestId, lockTxHash, _signValidator(V2_PK, requestId, lockTxHash));
        vm.prank(validator3);
        bridge.confirmBridge(requestId, lockTxHash, _signValidator(V3_PK, requestId, lockTxHash));

        // owner path needed mid-flight: publish the withdrawal merkle root via the safe
        bytes32 leaf = keccak256(abi.encodePacked(requestId, recipient, amount));
        _exec(address(bridge), abi.encodeCall(CrossChainBridge.updateMerkleRoot, (leaf)));

        // withdraw: on the target chain the bridge releases targetToken to recipient
        vm.chainId(TARGET_CHAIN);
        bytes32[] memory proof = new bytes32[](0);
        bridge.completeBridge(requestId, keccak256("unlock-tx"), proof);

        assertEq(targetToken.balanceOf(recipient), amount);
        (, , , , , CrossChainBridge.BridgeStatus st, ) = bridge.getBridgeRequest(requestId);
        assertEq(uint256(st), uint256(CrossChainBridge.BridgeStatus.COMPLETED));
    }

    function test_DepositWithdrawRoundTrip_EoaOwned() public {
        // same round trip with a plain EOA owner — the control case
        uint256 amount = 2_000 * 10**18;
        vm.startPrank(user);
        sourceToken.approve(address(bridge), amount);
        uint256 requestId =
            bridge.initiateBridge(address(sourceToken), address(targetToken), amount, TARGET_CHAIN, recipient);
        vm.stopPrank();

        bytes32 lockTxHash = keccak256("lock-tx-2");
        vm.prank(validator1);
        bridge.confirmBridge(requestId, lockTxHash, _signValidator(V1_PK, requestId, lockTxHash));
        vm.prank(validator2);
        bridge.confirmBridge(requestId, lockTxHash, _signValidator(V2_PK, requestId, lockTxHash));
        vm.prank(validator3);
        bridge.confirmBridge(requestId, lockTxHash, _signValidator(V3_PK, requestId, lockTxHash));

        bytes32 leaf = keccak256(abi.encodePacked(requestId, recipient, amount));
        bridge.updateMerkleRoot(leaf);

        vm.chainId(TARGET_CHAIN);
        bytes32[] memory proof = new bytes32[](0);
        bridge.completeBridge(requestId, keccak256("unlock-tx-2"), proof);
        assertEq(targetToken.balanceOf(recipient), amount);
    }

    // ---------- 5. cancelBridge keeps working through the safe owner ----------

    function test_CancelBridgeBySafeOwnerAfterTimeout() public {
        bridge.transferOwnership(address(safe));
        uint256 amount = 100 * 10**18;
        vm.startPrank(user);
        sourceToken.approve(address(bridge), amount);
        uint256 requestId =
            bridge.initiateBridge(address(sourceToken), address(targetToken), amount, TARGET_CHAIN, recipient);
        vm.stopPrank();

        // a stranger cannot cancel even after expiry
        vm.warp(block.timestamp + 24 hours + 1);
        vm.prank(outsider);
        vm.expectRevert("Not authorized to cancel");
        bridge.cancelBridge(requestId, "intruder");

        // the safe owner can (msg.sender == owner())
        uint256 before = sourceToken.balanceOf(user);
        _exec(address(bridge), abi.encodeCall(CrossChainBridge.cancelBridge, (requestId, "timed out")));
        assertEq(sourceToken.balanceOf(user), before + amount);
    }
}
