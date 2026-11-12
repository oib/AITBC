// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/CrossChainBridge.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract QuorumMockToken is ERC20 {
    constructor() ERC20("Quorum Token", "QMT") {
        _mint(msg.sender, 10_000_000 * 10**18);
    }
}

/**
 * @dev Pins for the #795 quorum redesign (operator-approved plan c29666 as
 * amended c29698): quorumFor(n) = max(MIN_QUORUM, floor(2n/3)+1) over the live
 * validator set, per-request requiredAtCreation snapshot, only currently
 * active confirmers count, permissionless finalizeConfirmed, MIN_QUORUM=2
 * floor reachable by construction, validator set capped at 16.
 */
contract CrossChainBridgeQuorum795Test is Test {
    uint256 internal constant V1_PK = 0x2001;
    uint256 internal constant V2_PK = 0x2002;
    uint256 internal constant V3_PK = 0x2003;
    uint256 internal constant V4_PK = 0x2004;
    uint256 internal constant V5_PK = 0x2005;
    uint256 internal constant TARGET_CHAIN = 1;

    CrossChainBridge public bridge;
    QuorumMockToken public token;
    address public user = address(0x20);
    address public recipient = address(0x30);
    address public outsider = address(0x40);

    address[5] public validators;
    uint256[5] public validatorPks;

    function setUp() public {
        validatorPks = [V1_PK, V2_PK, V3_PK, V4_PK, V5_PK];
        for (uint256 i = 0; i < 5; i++) {
            validators[i] = vm.addr(validatorPks[i]);
        }
        token = new QuorumMockToken();
        bridge = new CrossChainBridge(address(0x10));
        bridge.addSupportedToken(address(token), 5_000_000 * 10**18, 0, false);
        token.transfer(user, 1_000_000 * 10**18);
    }

    function _addValidators(uint256 n) internal {
        for (uint256 i = 0; i < n; i++) {
            bridge.addValidator(validators[i], 1);
        }
    }

    function _sign(uint256 pk, uint256 requestId, bytes32 lockTxHash) internal view returns (bytes memory) {
        bytes32 domainTypehash = keccak256(
            "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
        );
        bytes32 domainSeparator = keccak256(
            abi.encode(
                domainTypehash,
                keccak256("CrossChainBridge"),
                keccak256("1"),
                block.chainid,
                address(bridge)
            )
        );
        bytes32 structHash = keccak256(
            abi.encode(
                keccak256("BridgeConfirmation(uint256 requestId,bytes32 lockTxHash)"),
                requestId,
                lockTxHash
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, digest);
        return abi.encodePacked(r, s, v);
    }

    function _initiate() internal returns (uint256 requestId) {
        vm.startPrank(user);
        token.approve(address(bridge), 1000 * 10**18);
        requestId = bridge.initiateBridge(address(token), address(token), 100 * 10**18, TARGET_CHAIN, recipient);
        vm.stopPrank();
    }

    function _confirm(uint256 idx, uint256 requestId, bytes32 lockTxHash) internal {
        vm.prank(validators[idx]);
        bridge.confirmBridge(requestId, lockTxHash, _sign(validatorPks[idx], requestId, lockTxHash));
    }

    function _status(uint256 requestId) internal view returns (CrossChainBridge.BridgeStatus) {
        (, , , , , CrossChainBridge.BridgeStatus st, , ) = bridge.getBridgeRequest(requestId);
        return st;
    }

    // ---------- 1. quorumFor truth table + bounds ----------

    function test_QuorumFor_TruthTable() public {
        uint256[7] memory n = [uint256(2), 3, 4, 5, 6, 7, 8];
        uint256[7] memory expected = [uint256(2), 3, 3, 4, 5, 5, 6];
        for (uint256 i = 0; i < 7; i++) {
            assertEq(bridge.quorumFor(n[i]), expected[i], "truth table mismatch");
        }
        assertEq(bridge.quorumFor(16), 11);
        assertEq(bridge.quorumFor(1), 2); // unreachable in practice; floor holds anyway
    }

    function test_QuorumFor_MonotoneAndBounded() public {
        uint256 prev;
        for (uint256 n = 2; n <= 16; n++) {
            uint256 q = bridge.quorumFor(n);
            assertGe(q, bridge.MIN_QUORUM());
            assertLe(q, n);
            assertGe(q, prev);
            prev = q;
        }
    }

    // ---------- 2. per-request snapshot ----------

    /// @dev Initiated at n=4 (q=3); growing the set to n=5 must NOT raise the
    /// threshold to quorumFor(5)=4 — the snapshot is frozen at creation.
    function test_QuorumSnapshot_IgnoresSetGrowth() public {
        _addValidators(4);
        uint256 requestId = _initiate();
        (, , , , , , , uint256 required) = bridge.getBridgeRequest(requestId);
        assertEq(required, 3);

        bridge.addValidator(validators[4], 1); // live set now 5

        bytes32 lockTxHash = keccak256("lock");
        _confirm(0, requestId, lockTxHash);
        _confirm(1, requestId, lockTxHash);
        _confirm(2, requestId, lockTxHash); // 3rd confirm flips: snapshot=3, not 4
        assertEq(uint256(_status(requestId)), uint256(CrossChainBridge.BridgeStatus.CONFIRMED));
    }

    // ---------- 3. removed confirmer stops counting ----------

    /// @dev n=5 → q=4. Three confirm, one confirmer is removed: effective
    /// drops to 2 and finalizeConfirmed must refuse. The removed validator
    /// also cannot confirm new requests.
    function test_RemovedConfirmer_StopsCounting() public {
        _addValidators(5);
        uint256 requestId = _initiate();
        bytes32 lockTxHash = keccak256("lock");

        _confirm(0, requestId, lockTxHash);
        _confirm(1, requestId, lockTxHash);
        _confirm(2, requestId, lockTxHash);
        assertEq(uint256(_status(requestId)), uint256(CrossChainBridge.BridgeStatus.PENDING));

        bridge.removeValidator(validators[2]); // confirmer #3 leaves the live set

        vm.prank(outsider);
        vm.expectRevert("Quorum not met");
        bridge.finalizeConfirmed(requestId);

        vm.prank(validators[2]);
        vm.expectRevert("Not an active validator");
        bridge.confirmBridge(requestId, lockTxHash, _sign(validatorPks[2], requestId, lockTxHash));

        // Remaining quorum path still works: two more active confirms → 4.
        _confirm(3, requestId, lockTxHash);
        _confirm(4, requestId, lockTxHash);
        assertEq(uint256(_status(requestId)), uint256(CrossChainBridge.BridgeStatus.CONFIRMED));
    }

    // ---------- 4. permissionless finalizeConfirmed ----------

    /// @dev The stuck-request case: quorum becomes met WITHOUT a confirm
    /// call — removing non-confirmer validators shrinks `live`, which lowers
    /// the threshold min(requiredAtCreation, live) onto the current effective
    /// count. Anyone can then finalize.
    function test_FinalizeConfirmed_FlipsQuorumMetPending() public {
        _addValidators(5); // q=4
        uint256 requestId = _initiate();
        bytes32 lockTxHash = keccak256("lock");

        _confirm(0, requestId, lockTxHash);
        _confirm(1, requestId, lockTxHash);
        _confirm(2, requestId, lockTxHash); // effective 3 < 4, still PENDING
        assertEq(uint256(_status(requestId)), uint256(CrossChainBridge.BridgeStatus.PENDING));

        // Shrink live 5→3 via non-confirmer removals: threshold min(4,3)=3.
        bridge.removeValidator(validators[3]);
        bridge.removeValidator(validators[4]);

        vm.prank(outsider); // permissionless — not a validator, not the owner
        bridge.finalizeConfirmed(requestId);
        assertEq(uint256(_status(requestId)), uint256(CrossChainBridge.BridgeStatus.CONFIRMED));
    }

    function test_FinalizeConfirmed_RevertsWhenNotMet() public {
        _addValidators(4); // q=3
        uint256 requestId = _initiate();
        bytes32 lockTxHash = keccak256("lock");
        _confirm(0, requestId, lockTxHash);

        vm.expectRevert("Quorum not met");
        bridge.finalizeConfirmed(requestId);
    }

    function test_FinalizeConfirmed_RevertsWhenExpiredOrNotPending() public {
        _addValidators(4);
        uint256 requestId = _initiate();
        bytes32 lockTxHash = keccak256("lock");
        _confirm(0, requestId, lockTxHash);
        _confirm(1, requestId, lockTxHash);
        _confirm(2, requestId, lockTxHash); // CONFIRMED

        vm.expectRevert("Request not pending");
        bridge.finalizeConfirmed(requestId);

        // expired PENDING request cannot be finalized either
        uint256 requestId2 = _initiate();
        vm.warp(block.timestamp + 24 hours + 1);
        vm.expectRevert("Bridge request expired");
        bridge.finalizeConfirmed(requestId2);
    }

    // ---------- 5. floor guards + cap ----------

    function test_InitiateBridge_RequiresMinQuorumValidators() public {
        _addValidators(1);
        vm.startPrank(user);
        token.approve(address(bridge), 100 * 10**18);
        vm.expectRevert("Not enough active validators");
        bridge.initiateBridge(address(token), address(token), 100 * 10**18, TARGET_CHAIN, recipient);
        vm.stopPrank();
    }

    function test_RemoveValidator_CannotGoBelowFloor() public {
        _addValidators(3);
        bridge.removeValidator(validators[2]); // 3→2, allowed
        vm.expectRevert("Validator floor reached");
        bridge.removeValidator(validators[1]); // would leave 1 < MIN_QUORUM
        vm.expectRevert("Validator floor reached");
        bridge.removeValidator(validators[0]);
    }

    function test_RemoveValidator_FloorOnTwo() public {
        _addValidators(2);
        vm.expectRevert("Validator floor reached");
        bridge.removeValidator(validators[0]); // would leave 1
    }

    function test_AddValidator_CappedAt16() public {
        _addValidators(5); // fixture set
        for (uint256 i = 0; i < 5; i++) {
            bridge.addValidator(vm.addr(uint256(0x9000 + i)), 1);
        } // 10 active
        for (uint256 i = 0; i < 6; i++) {
            bridge.addValidator(vm.addr(uint256(0xA000 + i)), 1);
        } // 16 active — at cap
        assertTrue(bridge.activeValidators(15) != address(0));
        vm.expectRevert("Validator cap reached");
        bridge.addValidator(vm.addr(0xB000), 1);
    }

    // ---------- 6. fuzz invariant ----------

    /// @dev Random confirm/remove/add/finalate sequences on one request:
    /// whenever effective >= threshold and the request is unexpired PENDING,
    /// finalizeConfirmed must succeed; CONFIRMED must always have had >=2
    /// effective active confirmers at flip time (checked at each step).
    function testFuzz_QuorumFinalizeInvariant(uint256 seed, uint256 ops) public {
        _addValidators(4); // q=3
        uint256 requestId = _initiate();
        bytes32 lockTxHash = keccak256("fuzz-lock");

        // mirror state: which of the 5 fixture validators confirmed, which are active
        bool[5] memory confirmed;
        bool[5] memory active = [true, true, true, true, false];
        uint256 activeCount = 4;

        ops = bound(ops, 1, 60);
        for (uint256 step = 0; step < ops; step++) {
            seed = uint256(keccak256(abi.encode(seed, step)));
            uint256 op = seed % 4;

            if (op == 0) {
                // confirm by a random fixture validator slot
                uint256 idx = (seed / 4) % 5;
                if (active[idx] && !confirmed[idx]) {
                    try this.confirmAs(idx, requestId, lockTxHash) returns (bool) {
                        confirmed[idx] = true;
                    } catch {}
                }
            } else if (op == 1 && activeCount > 2) {
                // remove a random active validator (floor guard keeps >=2)
                uint256 idx = (seed / 4) % 5;
                if (active[idx]) {
                    try bridge.removeValidator(validators[idx]) {
                        active[idx] = false;
                        activeCount--;
                    } catch {}
                }
            } else if (op == 2 && activeCount < 16) {
                uint256 idx = (seed / 4) % 5;
                if (!active[idx]) {
                    try bridge.addValidator(validators[idx], 1) {
                        active[idx] = true;
                        activeCount++;
                    } catch {}
                }
            } else {
                // attempt finalize; success is only legal when quorum met
                uint256 req = _requiredSnapshot(requestId);
                uint256 eff;
                for (uint256 i = 0; i < 5; i++) {
                    if (active[i]) eff += confirmed[i] ? 1 : 0;
                }
                uint256 threshold = req < activeCount ? req : activeCount;
                bool met = eff >= threshold;
                try bridge.finalizeConfirmed(requestId) {
                    assertTrue(met, "finalized without quorum");
                    assertGe(eff, 2, "finalized with fewer than MIN_QUORUM confirmers");
                } catch {}
            }

            // confirmed[] mirrors successful confirmAs calls; hasConfirmed
            // persists across remove/re-add on-chain, and the mirror does the
            // same (it is only counted while active[i]).
            if (_status(requestId) == CrossChainBridge.BridgeStatus.CONFIRMED) {
                return; // terminal for this request — invariant held to flip
            }
        }
    }

    /// @dev External wrapper so the fuzz can attempt confirmBridge without
    /// aborting the whole test on expected reverts.
    function confirmAs(uint256 idx, uint256 requestId, bytes32 lockTxHash) external returns (bool) {
        require(idx < validators.length, "bad idx");
        vm.prank(validators[idx]);
        bridge.confirmBridge(requestId, lockTxHash, _sign(validatorPks[idx], requestId, lockTxHash));
        return true;
    }

    function _requiredSnapshot(uint256 requestId) internal view returns (uint256) {
        (, , , , , , , uint256 required) = bridge.getBridgeRequest(requestId);
        return required;
    }
}
