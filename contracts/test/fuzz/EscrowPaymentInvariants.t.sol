// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../../contracts/EscrowService.sol";
import "../../contracts/PaymentProcessor.sol";
import "../../contracts/AIPowerRental.sol";
import "../../contracts/AIToken.sol";
import "../../contracts/MockVerifier.sol";

/// @title PaymentProcessor + EscrowService core-invariant fuzz tests (batch v3, items 14-15)
/// @dev Encodes the *correct* escrow/payment invariants and fuzzes the amount,
///      condition and caller inputs:
///        (a) no double-release / double-settle of the same escrow or payment,
///        (b) conservation of funds — an escrow settles exactly once and only
///            ever pays out its recorded amount (+ fees to their owners),
///        (c) refunds only while the release conditions are unmet,
///        (d) access control — non-participants cannot release or refund.
///
///      These tests are regression pins for the batch-v1 audit defects:
///        #1466 — PaymentProcessor.releaseEscrow ignored escrowType /
///                releaseCondition (a beneficiary could drain a
///                PerformanceBased/Conditional escrow immediately).
///        #1471 — EscrowService.releaseEscrow had no branch for Automatic,
///                PerformanceMet or Emergency conditions.
///      #1466/#1471 are fixed on this branch, so the pins below are expected
///      to PASS; any failure is evidence of a remaining defect.
contract PaymentProcessorInvariantFuzzTest is Test {
    AIToken token;
    AIPowerRental rental;
    PaymentProcessor processor;

    address payer = makeAddr("payer");
    address payee = makeAddr("payee");
    address verifier = makeAddr("verifier");
    address stranger = makeAddr("stranger");

    uint256 constant FUZZ_BALANCE = 1e26; // 100M AIT — covers maxPaymentAmount + fees

    function setUp() public {
        token = new AIToken(0);
        vm.warp(block.timestamp + 2 days); // AIToken enforces a 1-day minting cooldown
        MockVerifier zkv = new MockVerifier();
        MockVerifier g16 = new MockVerifier();
        rental = new AIPowerRental(address(token), address(zkv), address(g16));
        processor = new PaymentProcessor(address(token), address(rental));

        processor.authorizePayer(payer);
        processor.authorizePayee(payee);
        processor.authorizeReleaseVerifier(verifier);

        token.mint(payer, FUZZ_BALANCE);
        vm.prank(payer);
        token.approve(address(processor), type(uint256).max);
    }

    function _boundedAmount(uint256 seed) internal view returns (uint256) {
        return bound(seed, processor.minPaymentAmount(), processor.maxPaymentAmount());
    }

    /// (a)+(b) An escrow settles exactly once: after release, neither a second
    /// release nor a refund can move funds again, and the beneficiary received
    /// exactly `amount` — never more.
    function testFuzz_PP_Escrow_SettlesAtMostOnce(uint256 amountSeed, uint8 typeSeed, bool refundFirst) public {
        uint256 amount = _boundedAmount(amountSeed);
        PaymentProcessor.EscrowType escrowType = PaymentProcessor.EscrowType(typeSeed % 4);

        uint256 releaseTime = 0;
        bytes32 condition = bytes32(0);
        if (escrowType == PaymentProcessor.EscrowType.TimeBased) {
            releaseTime = block.timestamp + 1 + (amountSeed % 100);
        } else if (
            escrowType == PaymentProcessor.EscrowType.PerformanceBased ||
            escrowType == PaymentProcessor.EscrowType.Conditional
        ) {
            // #1466: these types now require a committed condition hash.
            condition = keccak256("fuzz-condition");
        }

        vm.prank(payer);
        uint256 escrowId = processor.createEscrow(payee, amount, releaseTime, escrowType, condition);

        if (escrowType == PaymentProcessor.EscrowType.TimeBased) {
            vm.warp(releaseTime + 1);
        }

        if (refundFirst) {
            // (c) refund path: depositor may refund an unsettled escrow; once
            // refunded the escrow can never release.
            vm.prank(payer);
            processor.refundEscrow(escrowId, "fuzz refund");

            vm.prank(payee);
            vm.expectRevert("Escrow already refunded");
            processor.releaseEscrow(escrowId);

            vm.prank(payer);
            vm.expectRevert("Escrow already refunded");
            processor.refundEscrow(escrowId, "second refund");

            PaymentProcessor.EscrowAccount memory acc = processor.getEscrowAccount(escrowId);
            assertFalse(acc.isReleased);
            assertTrue(acc.isRefunded);
            assertEq(token.balanceOf(payee), 0, "refund must not pay beneficiary");
            assertEq(token.balanceOf(payer), FUZZ_BALANCE, "refund must restore depositor exactly");
        } else {
            // (a) release path: verifier-gated types need approval first (#1466).
            if (
                escrowType == PaymentProcessor.EscrowType.PerformanceBased ||
                escrowType == PaymentProcessor.EscrowType.Conditional
            ) {
                // Without approval the release must fail closed (#1466 pin).
                vm.prank(payee);
                vm.expectRevert("Escrow release not approved by verifier");
                processor.releaseEscrow(escrowId);

                vm.prank(verifier);
                processor.approveEscrowRelease(escrowId);
            }

            uint256 beneficiaryBefore = token.balanceOf(payee);
            vm.prank(payee);
            processor.releaseEscrow(escrowId);
            assertEq(token.balanceOf(payee) - beneficiaryBefore, amount, "beneficiary paid exactly once");

            // Second release and any refund must both fail.
            vm.prank(payer);
            vm.expectRevert("Escrow already released");
            processor.releaseEscrow(escrowId);
            vm.prank(payee);
            vm.expectRevert("Escrow already released");
            processor.releaseEscrow(escrowId);
            vm.prank(payer);
            vm.expectRevert("Escrow already released");
            processor.refundEscrow(escrowId, "post-release refund");

            PaymentProcessor.EscrowAccount memory acc = processor.getEscrowAccount(escrowId);
            assertTrue(acc.isReleased);
            assertFalse(acc.isRefunded);
            assertEq(processor.getUserEscrowBalance(payer), 0, "escrow balance accounting cleared");
        }
    }

    /// (b) Conservation: settling an escrow moves exactly `amount` out of the
    /// contract — to the beneficiary on release, back to the depositor on
    /// refund — and the recorded escrow balance is decremented once.
    function testFuzz_PP_Escrow_Conservation(uint256 amountSeed, bool doRelease) public {
        uint256 amount = _boundedAmount(amountSeed);
        vm.prank(payer);
        uint256 escrowId = processor.createEscrow(
            payee,
            amount,
            0,
            PaymentProcessor.EscrowType.Standard,
            bytes32(0)
        );

        uint256 contractBefore = token.balanceOf(address(processor));
        assertEq(processor.getUserEscrowBalance(payer), amount);

        if (doRelease) {
            vm.prank(payee);
            processor.releaseEscrow(escrowId);
            assertEq(token.balanceOf(address(processor)), contractBefore - amount);
            assertEq(processor.getUserEscrowBalance(payer), 0);
        } else {
            vm.prank(payer);
            processor.refundEscrow(escrowId, "conservation refund");
            assertEq(token.balanceOf(address(processor)), contractBefore - amount);
            assertEq(processor.getUserEscrowBalance(payer), 0);
            assertEq(token.balanceOf(payer), FUZZ_BALANCE, "refund restores full balance");
        }
    }

    /// (d) Access control: neither a stranger nor the beneficiary can refund;
    /// only depositor/owner may refund, and only depositor/beneficiary/owner
    /// may release.
    function testFuzz_PP_Escrow_AccessControl(uint256 amountSeed) public {
        uint256 amount = _boundedAmount(amountSeed);
        vm.prank(payer);
        uint256 escrowId = processor.createEscrow(
            payee,
            amount,
            0,
            PaymentProcessor.EscrowType.Standard,
            bytes32(0)
        );

        vm.startPrank(stranger);
        vm.expectRevert("Not authorized to release");
        processor.releaseEscrow(escrowId);
        vm.expectRevert("Only depositor or owner can refund");
        processor.refundEscrow(escrowId, "stranger refund");
        vm.stopPrank();

        // Beneficiary may release but must never refund.
        vm.prank(payee);
        vm.expectRevert("Only depositor or owner can refund");
        processor.refundEscrow(escrowId, "beneficiary refund");
    }

    /// #1466 regression pin: a PerformanceBased/Conditional escrow must stay
    /// locked until an authorized release verifier approves it — the stored
    /// escrowType/releaseCondition are enforced, not advisory.
    function testFuzz_PP_PerformanceEscrow_RequiresVerifier(uint256 amountSeed, uint8 typeSeed) public {
        uint256 amount = _boundedAmount(amountSeed);
        PaymentProcessor.EscrowType escrowType =
            typeSeed % 2 == 0
                ? PaymentProcessor.EscrowType.PerformanceBased
                : PaymentProcessor.EscrowType.Conditional;

        vm.prank(payer);
        uint256 escrowId = processor.createEscrow(
            payee,
            amount,
            0,
            escrowType,
            keccak256("fuzz-perf-condition")
        );

        // Beneficiary cannot self-release without verifier approval (#1466).
        vm.prank(payee);
        vm.expectRevert("Escrow release not approved by verifier");
        processor.releaseEscrow(escrowId);
        // Depositor cannot bypass either.
        vm.prank(payer);
        vm.expectRevert("Escrow release not approved by verifier");
        processor.releaseEscrow(escrowId);

        // A non-verifier cannot approve.
        vm.prank(stranger);
        vm.expectRevert("Not a release verifier");
        processor.approveEscrowRelease(escrowId);

        vm.prank(verifier);
        processor.approveEscrowRelease(escrowId);
        vm.prank(payee);
        processor.releaseEscrow(escrowId);
        assertEq(token.balanceOf(payee), amount);
    }

    /// #1466 creation-time enforcement: TimeBased escrows need a release time
    /// and PerformanceBased/Conditional escrows need a condition hash.
    function testFuzz_PP_Escrow_InvalidTypeParams_Rejected(uint256 amountSeed, uint8 typeSeed) public {
        uint256 amount = _boundedAmount(amountSeed);
        PaymentProcessor.EscrowType escrowType = PaymentProcessor.EscrowType(typeSeed % 4);

        if (escrowType == PaymentProcessor.EscrowType.TimeBased) {
            vm.prank(payer);
            vm.expectRevert("Time-based escrow requires release time");
            processor.createEscrow(payee, amount, 0, escrowType, bytes32(0));
        } else if (
            escrowType == PaymentProcessor.EscrowType.PerformanceBased ||
            escrowType == PaymentProcessor.EscrowType.Conditional
        ) {
            vm.prank(payer);
            vm.expectRevert("Escrow release condition required");
            processor.createEscrow(payee, amount, 0, escrowType, bytes32(0));
        }
    }

    /// (a)+(b) Payments settle at most once across every release condition:
    /// after release a second releasePayment always reverts.
    function testFuzz_PP_Payment_SettlesAtMostOnce(uint256 amountSeed, uint8 condSeed) public {
        uint256 amount = _boundedAmount(amountSeed);
        PaymentProcessor.ReleaseCondition condition = PaymentProcessor.ReleaseCondition(condSeed % 5);

        vm.prank(payer);
        uint256 paymentId = processor.createPayment(
            payee,
            amount,
            keccak256("fuzz-agreement"),
            "fuzz payment",
            condition
        );

        uint256 payeeBefore = token.balanceOf(payee);
        vm.prank(payer);
        processor.confirmPayment(paymentId, keccak256("fuzz-tx"));

        if (condition == PaymentProcessor.ReleaseCondition.TimeBased) {
            vm.warp(block.timestamp + 2 hours);
        }

        if (condition == PaymentProcessor.ReleaseCondition.Immediate) {
            // Immediate releases inside confirmPayment — no explicit release
            // call exists or is needed; fall through to the double-release
            // check below.
        } else {
            if (
                condition == PaymentProcessor.ReleaseCondition.Performance ||
                condition == PaymentProcessor.ReleaseCondition.DisputeResolution
            ) {
                // #1103: verifier approval is mandatory for these conditions.
                vm.prank(payee);
                vm.expectRevert("Release not approved by verifier");
                processor.releasePayment(paymentId);
                vm.prank(verifier);
                processor.approveRelease(paymentId);
            }

            if (condition == PaymentProcessor.ReleaseCondition.Manual) {
                // Manual release is payer-only; the payee must not self-release.
                vm.prank(payee);
                vm.expectRevert("Only payer can release manually");
                processor.releasePayment(paymentId);
            }

            address releaser = condition == PaymentProcessor.ReleaseCondition.Manual ? payer : payee;
            vm.prank(releaser);
            processor.releasePayment(paymentId);
        }
        assertEq(token.balanceOf(payee) - payeeBefore, amount, "payee paid exactly once");

        // (a) No second release — for every condition, including Immediate
        // which already released inside confirmPayment.
        vm.prank(payee);
        vm.expectRevert("Payment not ready for release");
        processor.releasePayment(paymentId);
    }

    /// Invalid amounts are rejected on both payment and escrow creation —
    /// zero, below-minimum and above-maximum values can never lock funds.
    function testFuzz_PP_InvalidAmounts_Rejected(uint256 raw) public {
        uint256 minAmt = processor.minPaymentAmount();
        uint256 maxAmt = processor.maxPaymentAmount();

        // Below-minimum amounts are rejected on both paths. Above-maximum
        // amounts are covered separately below: createPayment enforces
        // maxPaymentAmount but createEscrow does not — see
        // testFuzz_PP_Escrow_AboveMax_IsAccepted defect pin.
        uint256[2] memory badLow = [uint256(0), minAmt - 1];
        for (uint256 i = 0; i < badLow.length; i++) {
            vm.prank(payer);
            vm.expectRevert();
            processor.createPayment(
                payee,
                badLow[i],
                bytes32(0),
                "bad amount",
                PaymentProcessor.ReleaseCondition.Manual
            );
            vm.prank(payer);
            vm.expectRevert();
            processor.createEscrow(
                payee,
                badLow[i],
                0,
                PaymentProcessor.EscrowType.Standard,
                bytes32(0)
            );
        }

        // Above-maximum amounts must be rejected by createPayment.
        uint256[2] memory badHigh = [maxAmt + 1, maxAmt + 1 + (raw % maxAmt)];
        for (uint256 i = 0; i < badHigh.length; i++) {
            vm.prank(payer);
            vm.expectRevert("Amount above maximum");
            processor.createPayment(
                payee,
                badHigh[i],
                bytes32(0),
                "bad amount",
                PaymentProcessor.ReleaseCondition.Manual
            );
        }
    }

    /// SUSPECTED DEFECT (evidence pin, not a known-issue number):
    /// createPayment enforces `amount <= maxPaymentAmount` but createEscrow
    /// only checks the minimum — an escrow of arbitrary size (bounded only
    /// by the payer's balance/allowance) can be locked. The symmetric bound
    /// is the correct invariant; this test FAILS on current code, proving
    /// the missing check. Do not "fix" the test — the contract needs the
    /// `require(_amount <= maxPaymentAmount)` line.
    function testFuzz_PP_Escrow_AboveMax_IsAccepted(uint256 amountSeed) public {
        uint256 overMax = processor.maxPaymentAmount() + 1 + (amountSeed % processor.maxPaymentAmount());
        // overMax <= 2 * maxPaymentAmount << FUZZ_BALANCE, so balance and
        // allowance always suffice — only the (missing) bound check can
        // revert this call.

        vm.prank(payer);
        vm.expectRevert("Amount above maximum");
        processor.createEscrow(
            payee,
            overMax,
            0,
            PaymentProcessor.EscrowType.Standard,
            bytes32(0)
        );
    }
}

/// @title EscrowService core-invariant fuzz tests (batch v3, items 14-15)
contract EscrowServiceInvariantFuzzTest is Test {
    AIToken token;
    AIPowerRental rental;
    PaymentProcessor processor;
    EscrowService escrow;

    address depositor = makeAddr("depositor");
    address beneficiary = makeAddr("beneficiary");
    address arbiter = makeAddr("arbiter");
    address stranger = makeAddr("stranger");
    address oracle = makeAddr("oracle");
    address arb1 = makeAddr("arb1");
    address arb2 = makeAddr("arb2");
    address arb3 = makeAddr("arb3");

    uint256 constant FUZZ_BALANCE = 1e26;

    function setUp() public {
        token = new AIToken(0);
        vm.warp(block.timestamp + 2 days); // AIToken enforces a 1-day minting cooldown
        MockVerifier zkv = new MockVerifier();
        MockVerifier g16 = new MockVerifier();
        rental = new AIPowerRental(address(token), address(zkv), address(g16));
        processor = new PaymentProcessor(address(token), address(rental));
        escrow = new EscrowService(address(token), address(rental), address(processor));

        escrow.authorizeOracle(oracle);
        escrow.authorizeArbiter(arb1);
        escrow.authorizeArbiter(arb2);
        escrow.authorizeArbiter(arb3);

        token.mint(depositor, FUZZ_BALANCE);
        vm.prank(depositor);
        token.approve(address(escrow), type(uint256).max);
    }

    function _boundedAmount(uint256 seed) internal view returns (uint256) {
        return bound(seed, escrow.minEscrowAmount(), escrow.maxEscrowAmount());
    }

    /// Release conditions exercised by the settle-once fuzz: Manual,
    /// Automatic and TimeBased — the three paths a plain createEscrow can
    /// reach without oracle/emergency setup.
    function _plainCondition(uint8 seed) internal pure returns (EscrowService.ReleaseCondition) {
        uint8 pick = seed % 3;
        if (pick == 0) return EscrowService.ReleaseCondition.Manual;
        if (pick == 1) return EscrowService.ReleaseCondition.Automatic;
        return EscrowService.ReleaseCondition.TimeBased;
    }

    /// (a)+(b)+(c) An escrow settles exactly once: release then refund (or
    /// refund then release) — the second settlement path always reverts, and
    /// the beneficiary/depositor is paid exactly the recorded amount (+fee).
    function testFuzz_ES_Escrow_SettlesAtMostOnce(uint256 amountSeed, uint8 condSeed, bool refundFirst) public {
        uint256 amount = _boundedAmount(amountSeed);
        EscrowService.ReleaseCondition condition = _plainCondition(condSeed);

        uint256 releaseTime = 0;
        if (condition == EscrowService.ReleaseCondition.TimeBased) {
            releaseTime = block.timestamp + 1 + (amountSeed % 7200);
        }

        vm.prank(depositor);
        uint256 escrowId = escrow.createEscrow(
            beneficiary,
            arbiter,
            amount,
            EscrowService.EscrowType.Standard,
            condition,
            releaseTime,
            "fuzz escrow"
        );

        (, , , uint256 storedAmount, , , , bool isReleased, bool isRefunded) =
            escrow.getEscrowAccount(escrowId);
        assertEq(storedAmount, amount);
        assertFalse(isReleased);
        assertFalse(isRefunded);

        uint256 fee = (amount * escrow.platformFeePercentage()) / 10000;

        if (refundFirst) {
            // (c) Refund is allowed on an unsettled escrow (Manual /
            // Automatic have no unmet-condition gate; TimeBased requires
            // now < releaseTime, which holds here).
            uint256 depositorBefore = token.balanceOf(depositor);
            vm.prank(depositor);
            escrow.refundEscrow(escrowId, "fuzz refund");
            assertEq(token.balanceOf(depositor) - depositorBefore, amount + fee, "refund returns amount + fee");

            // Once refunded, release must fail for every participant.
            vm.prank(beneficiary);
            vm.expectRevert("Escrow already refunded");
            escrow.releaseEscrow(escrowId, "post-refund release");
            vm.prank(depositor);
            vm.expectRevert("Escrow already refunded");
            escrow.refundEscrow(escrowId, "second refund");

            (,,,,,,, bool rel, bool ref) = escrow.getEscrowAccount(escrowId);
            assertFalse(rel);
            assertTrue(ref);
        } else {
            if (condition == EscrowService.ReleaseCondition.TimeBased) {
                vm.warp(releaseTime + 1);
            }

            // Manual and Automatic releases are depositor/arbiter-triggered —
            // the beneficiary must not be able to self-release (#1471 pin for
            // Automatic; Manual has always required depositor/arbiter).
            if (condition != EscrowService.ReleaseCondition.TimeBased) {
                vm.prank(beneficiary);
                vm.expectRevert();
                escrow.releaseEscrow(escrowId, "beneficiary self-release");
            }

            uint256 beneficiaryBefore = token.balanceOf(beneficiary);
            vm.prank(depositor);
            escrow.releaseEscrow(escrowId, "fuzz release");
            assertEq(token.balanceOf(beneficiary) - beneficiaryBefore, amount, "beneficiary paid exactly once");
            // The platform fee is paid to the owner exactly once.
            assertEq(token.balanceOf(address(this)), fee, "platform fee paid once");

            // (a) Second release and any refund must both fail.
            vm.prank(depositor);
            vm.expectRevert("Escrow already released");
            escrow.releaseEscrow(escrowId, "second release");
            vm.prank(arbiter);
            vm.expectRevert("Escrow already released");
            escrow.releaseEscrow(escrowId, "arbiter second release");
            vm.prank(depositor);
            vm.expectRevert("Escrow already released");
            escrow.refundEscrow(escrowId, "post-release refund");

            (,,,,,,, bool rel, bool ref) = escrow.getEscrowAccount(escrowId);
            assertTrue(rel);
            assertFalse(ref);
        }
    }

    /// (b) Conservation of funds: after settlement the contract's token
    /// balance drops by exactly amount + platformFee, and no escrow can pay
    /// out more than it took in.
    function testFuzz_ES_Escrow_Conservation(uint256 amountSeed, bool doRelease) public {
        uint256 amount = _boundedAmount(amountSeed);
        uint256 fee = (amount * escrow.platformFeePercentage()) / 10000;

        vm.prank(depositor);
        uint256 escrowId = escrow.createEscrow(
            beneficiary,
            arbiter,
            amount,
            EscrowService.EscrowType.Standard,
            EscrowService.ReleaseCondition.Manual,
            0,
            "conservation"
        );

        uint256 contractBefore = token.balanceOf(address(escrow));
        assertEq(contractBefore, amount + fee, "escrow holds principal + fee");

        if (doRelease) {
            vm.prank(depositor);
            escrow.releaseEscrow(escrowId, "release");
            assertEq(token.balanceOf(address(escrow)), contractBefore - amount - fee);
        } else {
            vm.prank(depositor);
            escrow.refundEscrow(escrowId, "refund");
            assertEq(token.balanceOf(address(escrow)), contractBefore - amount - fee);
            assertEq(token.balanceOf(depositor), FUZZ_BALANCE, "refund restores depositor fully");
        }
    }

    /// (d) Access control: a stranger can neither release nor refund; the
    /// beneficiary can never refund.
    function testFuzz_ES_Escrow_AccessControl(uint256 amountSeed) public {
        uint256 amount = _boundedAmount(amountSeed);
        vm.prank(depositor);
        uint256 escrowId = escrow.createEscrow(
            beneficiary,
            arbiter,
            amount,
            EscrowService.EscrowType.Standard,
            EscrowService.ReleaseCondition.Manual,
            0,
            "acl"
        );

        vm.startPrank(stranger);
        vm.expectRevert("Not authorized to release");
        escrow.releaseEscrow(escrowId, "stranger release");
        vm.expectRevert("Not authorized to refund");
        escrow.refundEscrow(escrowId, "stranger refund");
        vm.stopPrank();

        vm.prank(beneficiary);
        vm.expectRevert("Not authorized to refund");
        escrow.refundEscrow(escrowId, "beneficiary refund");
    }

    /// (c) TimeBased gating: release before releaseTime reverts; refund is
    /// only possible while the release time has not passed — after it, the
    /// escrow can only release.
    function testFuzz_ES_TimeBased_GatesReleaseAndRefund(uint256 amountSeed, uint256 timeSeed, bool warpPast) public {
        uint256 amount = _boundedAmount(amountSeed);
        uint256 delay = bound(timeSeed, 1, escrow.maxTimeLock());
        uint256 releaseTime = block.timestamp + delay;

        vm.prank(depositor);
        uint256 escrowId = escrow.createEscrow(
            beneficiary,
            arbiter,
            amount,
            EscrowService.EscrowType.Standard,
            EscrowService.ReleaseCondition.TimeBased,
            releaseTime,
            "time-gate"
        );

        if (!warpPast) {
            // Before releaseTime: release is closed, refund is open.
            vm.prank(depositor);
            vm.expectRevert("Release time not reached");
            escrow.releaseEscrow(escrowId, "too early");
            vm.prank(depositor);
            escrow.refundEscrow(escrowId, "early refund");

            (, , , , , , , bool rel, bool ref) = escrow.getEscrowAccount(escrowId);
            assertFalse(rel);
            assertTrue(ref);
        } else {
            vm.warp(releaseTime + 1);
            // After releaseTime: refund is closed.
            vm.prank(depositor);
            vm.expectRevert("Release time passed, cannot refund");
            escrow.refundEscrow(escrowId, "late refund");

            vm.prank(depositor);
            escrow.releaseEscrow(escrowId, "on time release");
            (, , , , , , , bool rel, bool ref) = escrow.getEscrowAccount(escrowId);
            assertTrue(rel);
            assertFalse(ref);
        }
    }

    /// #1471 regression pin: an Emergency-condition escrow must never
    /// release through releaseEscrow — only the quorum + timelock executor
    /// path may pay the beneficiary, and only once.
    function testFuzz_ES_Emergency_NoDirectRelease(uint256 amountSeed) public {
        uint256 amount = _boundedAmount(amountSeed);
        vm.prank(depositor);
        uint256 escrowId = escrow.createEscrow(
            beneficiary,
            arbiter,
            amount,
            EscrowService.EscrowType.Standard,
            EscrowService.ReleaseCondition.Emergency,
            0,
            "emergency"
        );

        // Every participant — including owner — is rejected by releaseEscrow.
        address[4] memory callers = [depositor, beneficiary, arbiter, address(this)];
        for (uint256 i = 0; i < callers.length; i++) {
            vm.prank(callers[i]);
            vm.expectRevert("Emergency release requires executeEmergencyRelease");
            escrow.releaseEscrow(escrowId, "shortcut");
        }

        // The legitimate path still settles exactly once.
        escrow.setEmergencyReleaseTimelock(1);
        vm.prank(depositor);
        escrow.requestEmergencyRelease(escrowId, "stuck");
        vm.prank(arb1);
        escrow.voteEmergencyRelease(escrowId, true);
        vm.prank(arb2);
        escrow.voteEmergencyRelease(escrowId, true);
        vm.prank(arb3);
        escrow.voteEmergencyRelease(escrowId, true);

        vm.warp(block.timestamp + 2);
        uint256 beneficiaryBefore = token.balanceOf(beneficiary);
        escrow.executeEmergencyRelease(escrowId);
        assertEq(token.balanceOf(beneficiary) - beneficiaryBefore, amount);

        // escrowNotReleased fires before the isExecuted check, so the
        // second execute reverts on the settled-escrow guard.
        vm.expectRevert("Escrow already released");
        escrow.executeEmergencyRelease(escrowId);
        vm.prank(depositor);
        vm.expectRevert("Escrow already released");
        escrow.refundEscrow(escrowId, "post-emergency refund");
    }

    /// #1471 regression pin: OracleVerified and PerformanceMet escrows stay
    /// closed until the oracle path proves the condition — releaseEscrow
    /// reverts for every caller while conditionMet is false.
    function testFuzz_ES_OracleConditions_ClosedUntilProven(uint256 amountSeed, uint8 condSeed) public {
        uint256 amount = _boundedAmount(amountSeed);
        EscrowService.ReleaseCondition condition = condSeed % 2 == 0
            ? EscrowService.ReleaseCondition.OracleVerified
            : EscrowService.ReleaseCondition.PerformanceMet;

        vm.prank(depositor);
        uint256 escrowId = escrow.createEscrow(
            beneficiary,
            arbiter,
            amount,
            EscrowService.EscrowType.Standard,
            condition,
            0,
            "oracle-gated"
        );

        address[3] memory callers = [depositor, beneficiary, arbiter];
        for (uint256 i = 0; i < callers.length; i++) {
            vm.prank(callers[i]);
            vm.expectRevert();
            escrow.releaseEscrow(escrowId, "no proof");
        }

        // Refund is also gated for OracleVerified once a condition exists;
        // with no condition set a depositor refund of an unproven escrow is
        // still allowed for OracleVerified only when conditionMet is false —
        // assert the funds cannot reach the beneficiary regardless.
        assertEq(token.balanceOf(beneficiary), 0, "unproven escrow pays nobody");
    }

    /// Invalid creation inputs are rejected: out-of-range amounts, release
    /// times in the past, and missing/invalid counterparties.
    function testFuzz_ES_InvalidInputs_Rejected(uint256 amountSeed, uint256 timeSeed) public {
        uint256 minAmt = escrow.minEscrowAmount();
        uint256 maxAmt = escrow.maxEscrowAmount();

        uint256[3] memory badAmounts = [uint256(0), minAmt - 1, maxAmt + 1];
        for (uint256 i = 0; i < badAmounts.length; i++) {
            vm.prank(depositor);
            vm.expectRevert("Invalid amount");
            escrow.createEscrow(
                beneficiary,
                arbiter,
                badAmounts[i],
                EscrowService.EscrowType.Standard,
                EscrowService.ReleaseCondition.Manual,
                0,
                "bad"
            );
        }

        // releaseTime must be 0 or strictly in the future.
        uint256 past = block.timestamp - bound(timeSeed, 1, 1 days);
        vm.prank(depositor);
        vm.expectRevert("Invalid release time");
        escrow.createEscrow(
            beneficiary,
            arbiter,
            minAmt,
            EscrowService.EscrowType.Standard,
            EscrowService.ReleaseCondition.TimeBased,
            past,
            "bad time"
        );

        vm.prank(depositor);
        vm.expectRevert("Invalid release time");
        escrow.createEscrow(
            beneficiary,
            arbiter,
            minAmt,
            EscrowService.EscrowType.Standard,
            EscrowService.ReleaseCondition.TimeBased,
            block.timestamp, // == now is not > now
            "bad time"
        );

        // Counterparty validation.
        vm.prank(depositor);
        vm.expectRevert("Invalid beneficiary");
        escrow.createEscrow(
            address(0),
            arbiter,
            minAmt,
            EscrowService.EscrowType.Standard,
            EscrowService.ReleaseCondition.Manual,
            0,
            "bad beneficiary"
        );
        vm.prank(depositor);
        vm.expectRevert("Cannot be own beneficiary");
        escrow.createEscrow(
            depositor,
            arbiter,
            minAmt,
            EscrowService.EscrowType.Standard,
            EscrowService.ReleaseCondition.Manual,
            0,
            "self beneficiary"
        );
    }
}
