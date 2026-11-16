"""Poll-cycle runtime for the bridge monitor (split from main.py, #1860).

Health checks, block scanning, deposit routing and the run loop — the
methods below are byte-identical moves; ``BridgeMonitor`` inherits them.
"""

import asyncio
import os
import sys
import time
from decimal import Decimal
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../.."))
from aitbc.aitbc_logging import get_logger
from aitbc.utils.units import ait_to_units, units_to_ait

from .storage import (
    BridgeDepositStatus,
    canon_tx_hash,
    count_pending_retry,
    create_deposit,
    depositor_tx_hashes,
    fail_stale_manual_pending,
    get_cursor,
    get_stranded_deposits,
    get_submitted_deposits,
    record_outbound,
    release_sources,
    set_cursor,
    sum_committed_ait,
    update_deposit,
)

# Same logger name as main.py so journal lines keep their [bridge_monitor.main] tag.
logger = get_logger("bridge_monitor.main")


class BridgeMonitorRuntime:
    """Poll-cycle runtime mixin for BridgeMonitor — see main.py."""

    def _fail_orphaned_manual_payouts(self) -> None:
        """Fail stale ``manual-*`` rows stuck in PENDING (#1433).

        Only the admin command advances a manual row out of PENDING; a
        crash mid-command orphans it where no sweep looks — the retry
        queue reads ``pending_retry`` only and a manual row's zero ETH
        amount could never be priced anyway. Restricted to the
        ``manual-%`` prefix: every other 'pending' row belongs to the
        wallet side's own deposit flow and must never be touched here.
        """
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(seconds=self.manual_orphan_seconds)).isoformat()
        try:
            failed = fail_stale_manual_pending(cutoff)
            if failed:
                logger.warning("Failed %s orphaned manual payout row(s) stuck in PENDING", failed)
        except Exception as e:  # noqa: BLE001 - orphan sweep containment — a sweep failure must not kill the poll cycle
            logger.warning("orphaned manual payout sweep failed: %s", e)

    def _check_queue_health(self) -> None:
        """Alert on head-of-line blocking the sweep cannot fix itself.

        Serialization means the oldest SUBMITTED row gates every payout
        queued behind it. A row that sealed-failed (kept for operator
        review) or that fails the abandon proof stays SUBMITTED forever —
        without an alert here, every later deposit silently queues.
        """
        try:
            submitted = get_submitted_deposits()
            if submitted and self.stuck_payout_blocks > 0:
                head = self._head_height()
                # BRIDGE-MON-ALERT-1 (#1436): a NULL submitted_height (the
                # sign-time /rpc/head fetch failed) is UNKNOWN age, not
                # "now" — falling back to the current head made the row
                # look brand new and suppressed this alert on exactly the
                # rows most likely to be stuck. Unknown reads as oldest.
                oldest_tx, oldest_height = min(
                    ((d["eth_tx_hash"], int(d.get("submitted_height") or 0)) for d in submitted),
                    key=lambda t: t[1],
                )
                if head is not None and head - oldest_height > self.stuck_payout_blocks:
                    # #1706: throttled — the slot stays blocked until an
                    # operator acts, so an unthrottled critical repeated
                    # every poll cycle (~12/hour at the default interval).
                    self._float_alert(
                        "queue_slot_blocked",
                        f"ALERT: payout slot blocked — deposit {oldest_tx} SUBMITTED for "
                        f"{head - oldest_height} blocks (>{self.stuck_payout_blocks}); "
                        f"{len(submitted)} row(s) holding the slot, retry queue cannot drain. "
                        "Release via admin.py abandon-and-resign (nonce passed + unsealed) "
                        "or write-off after review",
                    )
                elif head is not None:
                    # Cleared — let a recurrence alert immediately.
                    self._float_alert_last.pop("queue_slot_blocked", None)
            else:
                self._float_alert_last.pop("queue_slot_blocked", None)
            depth = count_pending_retry()
            if depth >= self.queue_alert_depth:
                self._float_alert(
                    "retry_queue_depth",
                    f"ALERT: {depth} deposits in PENDING_RETRY (>= {self.queue_alert_depth}) — "
                    "check payout float, RPC health, and any blocked SUBMITTED row gating the queue",
                )
            else:
                self._float_alert_last.pop("retry_queue_depth", None)
        except Exception as e:  # noqa: BLE001 - queue health-check containment
            logger.warning("queue health check failed: %s", e)

    def _check_stranded_deposits(self) -> None:
        """Alert on non-terminal rows older than the horizon that no
        worklist will pick up (#1919 ETH-DEPOSITS-VOCAB-1).

        The block scan never revisits old txs, the retry queue reads only
        ``pending_retry`` and the seal sweep only ``submitted`` — so a row
        flipped to a wallet-vocabulary state (``verified`` by the wallet
        admin route), left in ``pending``/``processing`` by a crash, or
        carrying an unrecognized status is invisible to all of them:
        funds received, never paid, and silent on both sides. Throttled
        per row like the other #1706 alerts; a row's key clears once it
        reaches a terminal or worklist-owned status.
        """
        from datetime import UTC, datetime, timedelta

        try:
            cutoff = (datetime.now(UTC) - timedelta(hours=self.stranded_deposit_hours)).isoformat()
            stranded = get_stranded_deposits(cutoff)
            seen = {d["eth_tx_hash"] for d in stranded}
            for d in stranded:
                tx_hash = d["eth_tx_hash"]
                self._float_alert(
                    f"stranded:{tx_hash}",
                    f"ALERT: deposit {tx_hash} stranded in status '{d.get('status')}' "
                    f"(created {d.get('created_at')}) — older than {self.stranded_deposit_hours}h and "
                    "no worklist owns it; resolve deliberately (admin.py write-off / manual-payout, "
                    "or the wallet-side mint/complete flow). Do NOT pay it automatically — a "
                    "'verified' row's wallet-side TRANSFER may already have landed",
                )
            for key in [k for k in self._float_alert_last if k.startswith("stranded:")]:
                if key.removeprefix("stranded:") not in seen:
                    self._float_alert_last.pop(key, None)
        except Exception as e:  # noqa: BLE001 - stranded-check containment
            logger.warning("stranded deposit check failed: %s", e)

    def _payout_wallet_balance(self) -> int | None:
        """Payout account balance in units from the local RPC."""
        try:
            import httpx

            resp = httpx.get(f"{self.blockchain_rpc_url}/rpc/account/{self.genesis_wallet_address}", timeout=5)
            if resp.status_code == 200:
                return int(resp.json().get("balance", 0))
        except (httpx.HTTPError, AttributeError, TypeError, ValueError) as e:
            logger.warning("payout balance fetch failed: %s", e)
        return None

    def _exceeds_payout_cap(self, ait_amount: Decimal) -> tuple[bool, str]:
        """True when a single payout exceeds BRIDGE_MAX_PAYOUT_FRACTION of
        the wallet balance — one outsized send cannot drain the float.
        RPC failure fails open on the fraction check only — an absolute
        BRIDGE_MAX_PAYOUT_AIT still applies since it needs no balance. The
        float check already alerts on balance visibility loss, and blocking
        payouts entirely on a probe failure would trade a soft cap for a
        hard outage."""
        abs_cap = Decimal(ait_to_units(self.max_payout_ait)) if self.max_payout_ait is not None else None
        balance = self._payout_wallet_balance()
        if balance is None:
            # The fraction cap needs the balance; the absolute ceiling does
            # not. An unreadable balance fails open on the fraction only —
            # BRIDGE_MAX_PAYOUT_AIT still bounds the payout.
            if abs_cap is not None and Decimal(ait_to_units(ait_amount)) > abs_cap:
                return True, (
                    f"{ait_amount} AIT > payout cap {units_to_ait(abs_cap)} AIT (BRIDGE_MAX_PAYOUT_AIT; balance unknown)"
                )
            return False, "balance unknown — cap unevaluated"
        cap = Decimal(balance) * self.max_payout_fraction
        origin = f"{self.max_payout_fraction} of float"
        if abs_cap is not None and abs_cap < cap:
            cap, origin = abs_cap, "BRIDGE_MAX_PAYOUT_AIT"
        if Decimal(ait_to_units(ait_amount)) > cap:
            return True, (
                f"{ait_amount} AIT > payout cap {units_to_ait(cap)} AIT ({origin}; float {units_to_ait(balance)} AIT)"
            )
        return False, ""

    def _float_alert(self, key: str, message: str) -> None:
        """Emit a CRITICAL alert at most once per float_alert_interval."""
        now = time.monotonic()
        if now - self._float_alert_last.get(key, -self.float_alert_interval) >= self.float_alert_interval:
            logger.critical(message)
            self._float_alert_last[key] = now

    def _check_float(self) -> None:
        """Alert (throttled) when the payout wallet is running dry.

        The committed sum matters: non-terminal rows (submitted envelopes
        that may still seal, queued payouts yet to send) already own part of
        the balance, so the *available* float is what can pay the next
        deposit — not the raw account figure."""
        balance = self._payout_wallet_balance()
        if balance is not None:
            committed = ait_to_units(sum_committed_ait())
            available = max(0, balance - committed)
            if available < self.low_float_units:
                self._float_alert(
                    "ait_float",
                    f"ALERT: bridge payout float low — {available} units free of {balance} "
                    f"({committed} committed to unsealed/queued payouts, threshold {self.low_float_units}); "
                    "deposits will pile up in PENDING_RETRY",
                )
            else:
                self._float_alert_last.pop("ait_float", None)
        try:
            wei = int(self.eth_rpc.get_balance(self.bridge_eth_address).get("wei", 0))
            eth = Decimal(wei) / Decimal(10**18)
            if eth < self.low_float_eth:
                self._float_alert(
                    "eth_float",
                    f"ALERT: bridge ETH float low — {eth.normalize()} ETH (< {self.low_float_eth}); cannot cover refund/withdrawal gas",
                )
            else:
                self._float_alert_last.pop("eth_float", None)
        except Exception as e:  # noqa: BLE001 - float-check containment
            logger.warning("ETH float check failed: %s", e)

    def _record_outbound(self, w3, tx, block_num: int) -> None:
        """Ledger a send *from* the bridge wallet into bridge_outbound (B13).

        Kind, by strongest evidence first: the tx hash itself appearing in
        the wallet's ``eth_withdrawals`` (release leg) -> ``withdrawal``;
        ``to`` a recorded depositor -> ``refund`` (matched_deposit_tx set);
        ``to`` a funding source -> ``withdrawal`` (float return); a send to
        the wallet itself -> ``self_send`` (only gas is lost — the value
        returns, so it must not count as outbound). Anything else is
        ``unidentified`` — the reconcile reads that as untrusted.
        A receipt failure records the row ungassed rather than losing the
        leg; ``record_outbound`` dedupes on tx_hash so re-scans are safe.
        """
        tx_hash = canon_tx_hash(tx.hash.hex())
        to_address = (tx.get("to") or "").lower()
        value_wei = int(tx.get("value", 0) or 0)
        gas_wei: int | None = None
        note: str | None = None
        try:
            receipt = w3.eth.get_transaction_receipt(tx.hash)
            if receipt is not None:
                gas_wei = int(receipt["gasUsed"]) * int(receipt["effectiveGasPrice"])
                if int(receipt.get("status", 1)) == 0:
                    note = f"tx failed — gas burned, intended {value_wei} wei not moved"
                    value_wei = 0  # a reverted send moves no value; only gas is outbound
        except Exception as e:  # noqa: BLE001 - receipt probe: an unreadable receipt must not blank the row
            note = f"receipt unavailable: {e}"

        depositors = depositor_tx_hashes()
        matched: str | None = None
        release_source = release_sources().get(canon_tx_hash(tx_hash))
        if release_source is not None:
            kind = "withdrawal"
            if release_source:
                note = "; ".join(x for x in (note, release_source) if x)
        elif to_address == self.bridge_eth_address:
            kind = "self_send"
        elif to_address in depositors:
            kind, matched = "refund", depositors[to_address]
        elif to_address in self.funding_sources:
            kind = "withdrawal"
            note = (note + "; " if note else "") + "float return to funding source"
        else:
            kind = "unidentified"
            logger.warning("Outbound send %s -> %s matched nothing (unidentified)", tx_hash, to_address)
        written = record_outbound(
            tx_hash, to_address, value_wei, block_num, kind, gas_wei, matched_deposit_tx=matched, note=note
        )
        if written:
            logger.info("Outbound %s recorded: %s -> %s", kind, tx_hash, to_address)

    def _watch_eth_head(self, latest_block: int) -> None:
        """Alert when the connected ETH endpoint stops serving new heads.

        A stale backend (a load-balanced pool member behind in sync) answers
        requests fine but never advances its head — deposits seal on the
        real chain while the scan range stays frozen, and no exception ever
        fires to explain the silence. A restart "fixes" it only because the
        fresh connection lands on a different backend. Throttled like the
        float alerts; clears as soon as the head moves again.
        """
        now = time.monotonic()
        if self._last_eth_head is None or latest_block > self._last_eth_head:
            self._last_eth_head = latest_block
            self._eth_head_stall_since = now
            self._float_alert_last.pop("eth_head_stall", None)
            return
        since = self._eth_head_stall_since if self._eth_head_stall_since is not None else now
        if now - since >= self.head_stall_seconds:
            self._float_alert(
                "eth_head_stall",
                f"ALERT: ETH head stuck at {latest_block} for {int(now - since)}s — endpoint is "
                "likely serving stale state; deposits sealing on-chain are not being scanned",
            )

    def poll_ethereum(self) -> None:
        """Poll Ethereum for new transactions to bridge address."""
        try:
            self._check_float()
            w3 = self.eth_rpc._get_web3()
            # Only pay for deposits buried by BRIDGE_CONFIRMATIONS blocks —
            # a reorg of an unconfirmed deposit must never have been paid.
            latest_block = max(0, w3.eth.block_number - self.confirmations)
            self._poll_fail_streak = 0  # RPC answered — endpoint is live
            # Poll recovered — a later outage alerts immediately, not on the
            # throttle's remaining interval (#1706).
            self._float_alert_last.pop("eth_poll_failures", None)
            self._watch_eth_head(latest_block)
            logger.debug("Latest confirmed block: %s", latest_block)

            # Use persistent cursor; bootstrap from latest_block - 10 on first run
            cursor = get_cursor("last_processed_block")
            if cursor is not None:
                start_block = cursor + 1
            else:
                start_block = max(0, latest_block - 10)

            if start_block > latest_block:
                logger.debug("No new blocks since cursor (%s)", start_block - 1)
                return

            self._scan_block_range(w3, start_block, latest_block)
        except Exception as e:  # noqa: BLE001 - poll containment — failures streak-count toward the alert
            self._poll_fail_streak += 1
            if self._poll_fail_streak >= 3:
                # #1706: throttled — while the RPC stays down this fired on
                # every failed poll; the streak count keeps climbing in the
                # message so each hourly reminder shows the damage.
                self._float_alert(
                    "eth_poll_failures",
                    f"ALERT: Ethereum poll failed {self._poll_fail_streak} consecutive times — "
                    f"deposits are NOT being scanned: {e}",
                )
            else:
                logger.error("Error polling Ethereum (%s consecutive): %s", self._poll_fail_streak, e)

    def _scan_block_range(self, w3: Any, start_block: int, latest_block: int) -> None:
        """Scan blocks start..latest, advancing the cursor per fully-processed
        block. Bounded by cycle_timeout so a dribbling endpoint cannot pin
        the payout sweep in silence; a breach holds the cursor."""
        # Bound the scan: each get_block has a per-request timeout, but
        # a large catch-up range (or a dribbling endpoint resetting the
        # inter-byte timer) can otherwise pin the whole cycle — and the
        # payout sweep with it — in silence. A breach keeps the cursor
        # on the last fully processed block; the next poll resumes.
        scan_deadline = time.monotonic() + self.cycle_timeout
        for block_num in range(start_block, latest_block + 1):
            if time.monotonic() > scan_deadline:
                logger.critical(
                    "ALERT: poll scan exceeded %ss at block %s of %s — cursor held at %s, remainder next cycle",
                    self.cycle_timeout,
                    block_num,
                    latest_block,
                    block_num - 1,
                )
                break
            block = w3.eth.get_block(block_num, full_transactions=True)
            if not block or not block.get("transactions"):
                set_cursor("last_processed_block", block_num)
                continue
            block_ok = True
            for tx in block["transactions"]:
                if not self._handle_block_tx(w3, tx, block_num):
                    block_ok = False
            # Advance cursor only after every deposit in this block is
            # in a terminal or PENDING_RETRY state (or was skipped).
            if not block_ok:
                # A deposit in this block has no ledger row and was not
                # queued — hold the cursor so the next poll rescans the
                # whole block instead of losing the inflow silently.
                break
            set_cursor("last_processed_block", block_num)

    def _handle_block_tx(self, w3: Any, tx: Any, block_num: int) -> bool:
        """Route one transaction: outbound ledgering, funding rows, dust
        FAILED rows, or full deposit processing. False means the deposit
        could not be processed OR queued — the block cursor must hold."""
        from_address = tx.get("from", "")
        if from_address and from_address.lower() == self.bridge_eth_address:
            # The bridge's own outbound sends are never deposits —
            # otherwise the wallet key holder could mint AIT
            # payouts for the price of gas. They are ledgered as
            # bridge_outbound rows (B13): refund to a known
            # depositor, release-leg or funding return as
            # withdrawal, anything else unidentified.
            self._record_outbound(w3, tx, block_num)
            return True
        to_address = tx.get("to", "")
        if not (to_address and to_address.lower() == self.bridge_eth_address):
            return True
        value = tx.get("value", 0)
        eth_amount = Decimal(value) / Decimal(10**18)
        tx_hash = canon_tx_hash(tx.hash.hex())
        if from_address.lower() in self.funding_sources:
            if create_deposit(
                tx_hash,
                from_address,
                str(eth_amount),
                "",
                status=BridgeDepositStatus.FUNDING,
                deposit_address=self.bridge_eth_address,
            ):
                logger.info("Operator funding recorded: %s from %s, amount: %s ETH", tx_hash, from_address, eth_amount)
            return True
        tx_data = tx.get("input", "0x")
        # An EXCHANGE_DEPOSIT tag is explicit user intent and
        # costs no payout — it bypasses the dust floor and
        # reaches the prepay lane at any amount.
        exchange_tag = (
            self._parse_exchange_deposit_tag(tx_data)
            if os.getenv("EXCHANGE_SETTLEMENT_ENABLED", "false").lower() == "true"
            else None
        )
        if eth_amount < self.min_eth_deposit and exchange_tag is None:
            self._record_dust_deposit(tx_hash, from_address, eth_amount, tx.get("input", "0x"))
            return True
        logger.info("Found deposit: %s from %s, amount: %s ETH", tx_hash, from_address, eth_amount)
        return self._safe_process_deposit(tx_hash, from_address, eth_amount, tx_data, block_num)

    def _record_dust_deposit(self, tx_hash: str, from_address: str, eth_amount: Decimal, tx_input: str) -> None:
        """Dust is still an inflow — record it so the ledger (and the payout
        audit) accounts for every wei that reached the bridge wallet.
        FAILED is terminal: an operator resolves it deliberately (refund /
        write-off), never paid."""
        if create_deposit(
            tx_hash,
            from_address,
            str(eth_amount),
            self.parse_ait_recipient(tx_input) or "",
            deposit_address=self.bridge_eth_address,
        ):
            update_deposit(
                tx_hash,
                status=BridgeDepositStatus.FAILED,
                error_message=(
                    f"below MIN_ETH_DEPOSIT {self.min_eth_deposit} — dust inflow; resolve deliberately (refund or write-off)"
                ),
            )
            logger.info(
                "Sub-minimum deposit %s recorded as FAILED (%s ETH < %s)",
                tx_hash,
                eth_amount,
                self.min_eth_deposit,
            )

    def _safe_process_deposit(
        self, tx_hash: str, from_address: str, eth_amount: Decimal, tx_data: str, block_num: int
    ) -> bool:
        """process_deposit with retry-queue fallback; False when even the
        retry mark failed — the caller holds the block cursor."""
        try:
            self.process_deposit(tx_hash, from_address, eth_amount, tx_data)
            return True
        except Exception:
            logger.exception("Unexpected error processing deposit %s, marking for retry", tx_hash)
            try:
                self._mark_for_retry(tx_hash, "Unexpected error during processing")
            except Exception:
                logger.exception("Failed to mark deposit %s for retry", tx_hash)
                # #1706: throttled per deposit — the cursor
                # stays held and this re-fires every poll
                # until the row lands or is resolved.
                self._float_alert(
                    f"block_cursor:{tx_hash}",
                    f"ALERT: block {block_num} deposit {tx_hash} could not be processed "
                    "or queued — block cursor held so the next poll retries it",
                )
                return False
            return True

    async def run(self) -> None:
        """Main polling loop.

        Sleeps in 1s ticks so a kick is noticed within ~1-2s. A fresh kick
        mtime starts a burst (polls every burst_interval for burst_window);
        between bursts the loop keeps the slow poll_interval as safety net.
        """
        logger.info("Starting bridge monitor polling loop")
        next_poll = 0.0
        while True:
            now = time.monotonic()
            kick = self._kick_mtime()
            if kick is not None and kick > self._last_kick_seen:
                self._last_kick_seen = kick
                self._burst_until = now + self.burst_window
                next_poll = 0.0
                logger.info("Poll kick received - burst polling for %ss", self.burst_window)
            if now >= next_poll:
                started = time.monotonic()
                try:
                    self.poll_ethereum()
                    self.process_retry_queue()
                    self.process_submitted_deposits()
                    self._fail_orphaned_manual_payouts()
                    self._check_queue_health()
                    self._check_stranded_deposits()
                except Exception as e:  # noqa: BLE001 - monitor service-loop containment
                    logger.error("Error in polling loop: %s", e)
                elapsed = time.monotonic() - started
                interval = self.burst_interval if now < self._burst_until else self.poll_interval
                # Heartbeat: an idle cycle used to log nothing at INFO, so a
                # frozen/hung cycle was indistinguishable from "nothing to
                # scan" — the exact shape of the missed-deposit outage.
                logger.info("poll cycle done in %.1fs — next poll in %ss", elapsed, interval)
                if elapsed > self.cycle_timeout:
                    logger.critical(
                        "ALERT: poll cycle ran %.0fs (limit %.0fs) — deposits went unscanned for that span",
                        elapsed,
                        self.cycle_timeout,
                    )
                next_poll = time.monotonic() + interval
            await asyncio.sleep(1.0)
