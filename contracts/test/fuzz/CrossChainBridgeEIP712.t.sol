// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/CrossChainBridge.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// #1463 property pins: the EIP-712 confirmation digest must be unique per
/// (requestId, lockTxHash) and bound to BOTH domain fields -- chainid and
/// verifyingContract -- so a validator signature cannot be replayed across
/// chains or across redeployments of the same contract.
///
/// Scope note: the signed struct is BridgeConfirmation(uint256 requestId,
/// bytes32 lockTxHash). requestId is the per-contract nonce; there is no
/// deadline field -- signature freshness is enforced separately by
/// BRIDGE_TIMEOUT at confirm time, not by the digest.
contract MockEIP712Token is ERC20 {
    constructor() ERC20("Mock Token", "MTK") {
        _mint(msg.sender, 1_000_000 * 10**18);
    }
}

contract CrossChainBridgeEIP712PropertyTest is Test {
    uint256 internal constant V1_PK = 0x1001;
    uint256 internal constant V2_PK = 0x1002;
    uint256 internal constant V3_PK = 0x1003;
    uint256 internal constant TARGET_CHAIN = 1; // seeded by the constructor

    CrossChainBridge public bridge;
    CrossChainBridge public bridge2;
    MockEIP712Token public sourceToken;
    address public feeRecipient;
    address public user;
    address public recipient;
    address public validator1;
    address public validator2;
    address public validator3;

    function setUp() public {
        feeRecipient = address(0x10);
        user = address(0x20);
        recipient = address(0x30);
        validator1 = vm.addr(V1_PK);
        validator2 = vm.addr(V2_PK);
        validator3 = vm.addr(V3_PK);

        sourceToken = new MockEIP712Token();
        bridge = new CrossChainBridge(feeRecipient);
        bridge2 = new CrossChainBridge(feeRecipient);

        CrossChainBridge[2] memory instances = [bridge, bridge2];
        for (uint256 i = 0; i < instances.length; i++) {
            instances[i].addSupportedToken(address(sourceToken), 500_000 * 10**18, 0, false);
            instances[i].addValidator(validator1, 1);
            instances[i].addValidator(validator2, 1);
            instances[i].addValidator(validator3, 1);
        }

        sourceToken.transfer(user, 400_000 * 10**18);
    }

    // ---------- digest construction (mirrors the contract's _confirmationDigest) ----------

    function _domainSeparator(address verifyingContract, uint256 chainId) internal pure returns (bytes32) {
        bytes32 domainTypehash = keccak256(
            "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
        );
        return keccak256(
            abi.encode(
                domainTypehash,
                keccak256("CrossChainBridge"),
                keccak256("1"),
                chainId,
                verifyingContract
            )
        );
    }

    function _structHash(uint256 requestId, bytes32 lockTxHash) internal pure returns (bytes32) {
        return keccak256(
            abi.encode(
                keccak256("BridgeConfirmation(uint256 requestId,bytes32 lockTxHash)"),
                requestId,
                lockTxHash
            )
        );
    }

    /// Digest parameterized by domain -- used to mint "foreign" digests a
    /// conforming signer would produce on another chain/deployment.
    function _digestFor(address verifyingContract, uint256 chainId, uint256 requestId, bytes32 lockTxHash)
        internal
        view
        returns (bytes32)
    {
        return keccak256(abi.encodePacked("\x19\x01", _domainSeparator(verifyingContract, chainId), _structHash(requestId, lockTxHash)));
    }

    function _digest(uint256 requestId, bytes32 lockTxHash) internal view returns (bytes32) {
        return _digestFor(address(bridge), block.chainid, requestId, lockTxHash);
    }

    /// Sanity: the local construction must equal the contract's own view so
    /// the property tests pin the REAL digest, not a parallel universe.
    function test_DigestMatchesContractHelper() public view {
        uint256 requestId = 7;
        bytes32 lockTxHash = keccak256("lock");
        assertEq(_digest(requestId, lockTxHash), bridge.confirmationDigest(requestId, lockTxHash));
    }

    // ---------- uniqueness over the signed fields ----------

    function testFuzz_DigestUniquePerRequestId(uint256 idA, uint256 idB, bytes32 lockTxHash) public view {
        vm.assume(idA != idB);
        assertTrue(_digest(idA, lockTxHash) != _digest(idB, lockTxHash), "requestId must bind the digest");
    }

    function testFuzz_DigestUniquePerLockTxHash(uint256 requestId, bytes32 lockA, bytes32 lockB) public view {
        vm.assume(lockA != lockB);
        assertTrue(_digest(requestId, lockA) != _digest(requestId, lockB), "lockTxHash must bind the digest");
    }

    // ---------- domain binding ----------

    function testFuzz_DigestBindsChainId(uint256 requestId, bytes32 lockTxHash, uint64 chainA, uint64 chainB) public view {
        vm.assume(chainA != chainB);
        assertTrue(
            _digestFor(address(bridge), chainA, requestId, lockTxHash)
                != _digestFor(address(bridge), chainB, requestId, lockTxHash),
            "chainid must bind the digest"
        );
    }

    function testFuzz_DigestBindsVerifyingContract(uint256 requestId, bytes32 lockTxHash) public view {
        assertTrue(
            _digestFor(address(bridge), block.chainid, requestId, lockTxHash)
                != _digestFor(address(bridge2), block.chainid, requestId, lockTxHash),
            "verifyingContract must bind the digest"
        );
    }

    // ---------- end-to-end: a signature stops verifying when the domain moves ----------

    function _initiate(uint256 amount) internal returns (uint256 requestId) {
        vm.startPrank(user);
        sourceToken.approve(address(bridge), amount);
        requestId = bridge.initiateBridge(address(sourceToken), address(sourceToken), amount, TARGET_CHAIN, recipient);
        vm.stopPrank();
    }

    function _signFor(address target, uint256 chainId, uint256 pk, uint256 requestId, bytes32 lockTxHash)
        internal
        view
        returns (bytes memory)
    {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, _digestFor(target, chainId, requestId, lockTxHash));
        return abi.encodePacked(r, s, v);
    }

    /// A validator signature minted under chainId A must not confirm a
    /// request once the chain reports chainId B -- ecrecover over the new
    /// domain yields a non-validator address.
    function testFuzz_SignatureInvalidAfterChainIdChange(uint256 amount, bytes32 lockTxHash, uint64 newChainId) public {
        amount = bound(amount, 1e18, 1_000e18);
        uint256 homeChainId = block.chainid;
        vm.assume(newChainId != 0 && newChainId != homeChainId);

        uint256 requestId = _initiate(amount);

        // Control: the correctly-scoped signature verifies on the home chain.
        bytes memory goodSig = _signFor(address(bridge), homeChainId, V1_PK, requestId, lockTxHash);
        vm.prank(validator1);
        bridge.confirmBridge(requestId, lockTxHash, goodSig);

        // A second request, then the domain moves: the signature a validator
        // produced under the OLD chainid must now be rejected.
        uint256 requestId2 = _initiate(amount);

        // The validator signs NOW, under the home chainid -- exactly what a
        // conforming signer produces before the domain moves. The signature
        // bytes are all that persists; only the digest scope changes.
        bytes32 staleDigest = _digestFor(address(bridge), homeChainId, requestId2, lockTxHash);
        // Sanity: this must be the digest the contract itself reports pre-switch.
        assertEq(staleDigest, bridge.confirmationDigest(requestId2, lockTxHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(V1_PK, staleDigest);
        bytes memory staleSig = abi.encodePacked(r, s, v);

        vm.chainId(newChainId);

        vm.prank(validator1);
        vm.expectRevert("Invalid signature");
        bridge.confirmBridge(requestId2, lockTxHash, staleSig);

        // And a signature scoped to the NEW chainid still works.
        vm.prank(validator1);
        bridge.confirmBridge(requestId2, lockTxHash, _signFor(address(bridge), newChainId, V1_PK, requestId2, lockTxHash));
    }

    /// Same property across deployments: requestId counters on two bridge
    /// instances collide (both start at 1), so only the domain separator's
    /// verifyingContract keeps a signature from replaying.
    function testFuzz_SignatureInvalidAcrossDeployments(uint256 amount, bytes32 lockTxHash) public {
        amount = bound(amount, 1e18, 1_000e18);

        uint256 requestId1 = _initiate(amount);
        vm.startPrank(user);
        sourceToken.approve(address(bridge2), amount);
        uint256 requestId2 = bridge2.initiateBridge(address(sourceToken), address(sourceToken), amount, TARGET_CHAIN, recipient);
        vm.stopPrank();
        assertEq(requestId1, requestId2); // per-contract counters start at 1

        // Validator signs for bridge (deployment 1); replaying it against
        // bridge2's identical-looking request must fail.
        bytes memory sigForBridge1 = _signFor(address(bridge), block.chainid, V1_PK, requestId1, lockTxHash);
        vm.prank(validator1);
        vm.expectRevert("Invalid signature");
        bridge2.confirmBridge(requestId2, lockTxHash, sigForBridge1);
    }
}
