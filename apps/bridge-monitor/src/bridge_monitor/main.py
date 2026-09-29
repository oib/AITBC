"""Bridge monitor service - polls Ethereum for ETH deposits and sends AIT."""

import asyncio
import json
import os
import sys
import time
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../.."))
from aitbc.aitbc_logging import configure_logging, get_logger
from aitbc.ethereum_rpc import EthereumRPCClient
from aitbc.oracles.price_oracle import get_price_oracle
from aitbc.utils.units import DEFAULT_TX_FEE_UNITS, ait_to_units

from .storage import (
    BridgeDepositStatus,
    create_deposit,
    get_cursor,
    get_deposit,
    get_deposits_for_retry,
    get_submitted_deposits,
    init_db,
    set_cursor,
    update_deposit,
)

configure_logging(level="INFO", service_name="bridge-monitor", to_file=True)
logger = get_logger(__name__)


class BridgeMonitor:
    """Monitor Ethereum wallet for deposits and bridge to AIT."""

    def __init__(self) -> None:
        self.eth_rpc = EthereumRPCClient()
        self.price_oracle = get_price_oracle()
        bridge_eth = os.getenv("BRIDGE_ETH_ADDRESS")
        if not bridge_eth:
            raise RuntimeError("BRIDGE_ETH_ADDRESS environment variable is required")
        self.bridge_eth_address = bridge_eth.lower()
        # Dedicated payout wallet: BRIDGE_PAYOUT_* is the production path.
        # GENESIS_WALLET_* is kept as a transitional fallback only.
        self.genesis_wallet_address = os.getenv("BRIDGE_PAYOUT_ADDRESS") or os.getenv("GENESIS_WALLET_ADDRESS")
        if not self.genesis_wallet_address:
            raise RuntimeError("BRIDGE_PAYOUT_ADDRESS or GENESIS_WALLET_ADDRESS environment variable is required")
        self.genesis_private_key = os.getenv("BRIDGE_PAYOUT_PRIVATE_KEY") or os.getenv("GENESIS_WALLET_PRIVATE_KEY")
        if not self.genesis_private_key:
            logger.warning("BRIDGE_PAYOUT_PRIVATE_KEY not set - cannot sign AIT transfers")
        elif not os.getenv("BRIDGE_PAYOUT_PRIVATE_KEY"):
            logger.warning("Payouts signed with GENESIS_WALLET_PRIVATE_KEY; configure a dedicated BRIDGE_PAYOUT_PRIVATE_KEY")
        self.poll_interval = int(os.getenv("BRIDGE_POLL_INTERVAL", "30"))
        self.min_eth_deposit = Decimal(os.getenv("MIN_ETH_DEPOSIT", "0.001"))
        self.min_ait_deposit = Decimal(os.getenv("BRIDGE_MIN_DEPOSIT_AIT", "1"))
        # Deposits are only paid once the source chain has buried them this
        # deep — a reorg can otherwise undo a deposit that was already paid.
        # Sepolia is forgiving; mainnet wants >=12.
        self.confirmations = int(os.getenv("BRIDGE_CONFIRMATIONS", "3"))
        # Critical-logged when the payout wallet drops below roughly a day of
        # expected payouts — otherwise deposits pile up in PENDING_RETRY.
        self.low_float_units = ait_to_units(Decimal(os.getenv("BRIDGE_LOW_FLOAT_AIT", "50")))
        # Same on the ETH side: the bridge wallet pays refund/withdrawal gas;
        # ~0.01 ETH covers hundreds of plain sends.
        self.low_float_eth = Decimal(os.getenv("BRIDGE_LOW_FLOAT_ETH", "0.01"))
        # Payout confirmation lifecycle: a deposit is COMPLETED only once
        # its payout tx is sealed this deep. A SUBMITTED payout that hasn't
        # sealed after REBROADCAST_BLOCKS is rebroadcast with the *same*
        # signed envelope — never re-signed (a fresh nonce would double-pay
        # if the original then landed).
        self.payout_seal_depth = int(os.getenv("PAYOUT_SEAL_DEPTH", "2"))
        self.rebroadcast_blocks = int(os.getenv("PAYOUT_REBROADCAST_BLOCKS", "6"))
        self.max_rebroadcasts = int(os.getenv("PAYOUT_MAX_REBROADCAST", "5"))
        self.blockchain_rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8202")
        # Demand-triggered bursts: the wallet's public /v1/bridge/poll-request
        # route (and the deposit-instruction call) touches this file; a fresh
        # mtime switches the loop to BURST_INTERVAL for BURST_WINDOW seconds
        # (~3 polls in 60s) while the slow poll_interval remains the safety net
        # for depositors who never trigger a kick.
        self.kick_file = os.getenv("BRIDGE_KICK_FILE", "/var/lib/aitbc/bridge_poll_kick")
        self.burst_window = float(os.getenv("BRIDGE_BURST_WINDOW", "60"))
        self.burst_interval = float(os.getenv("BRIDGE_BURST_INTERVAL", "20"))
        self._last_kick_seen = self._kick_mtime() or 0.0
        self._burst_until = 0.0
        init_db()
        logger.info("BridgeMonitor initialized - watching %s", self.bridge_eth_address)

    def _kick_mtime(self) -> float | None:
        try:
            return os.path.getmtime(self.kick_file)
        except OSError:
            return None

    def parse_ait_recipient(self, tx_data: str | bytes) -> str | None:
        """Parse AIT recipient address from transaction data field."""
        if isinstance(tx_data, bytes | bytearray):
            tx_data = "0x" + tx_data.hex()
        if not tx_data or tx_data == "0x":
            return None
        try:
            data = tx_data[2:] if tx_data.startswith("0x") else tx_data
            if len(data) % 2:
                data = "0" + data
            decoded = bytes.fromhex(data).decode("utf-8")
            if decoded.startswith("0x"):
                return decoded
        except (ValueError, UnicodeDecodeError):
            pass
        try:
            data = tx_data[2:] if tx_data.startswith("0x") else tx_data
            if len(data) == 40:
                return "0x" + data
        except ValueError:
            pass
        return None

    def calculate_ait_amount(self, eth_amount: Decimal, eth_usd=None, ait_usd=None) -> Decimal | None:
        """Calculate AIT amount based on ETH amount and oracle prices.

        Accepts pre-fetched prices to avoid redundant oracle calls.
        """
        try:
            if eth_usd is None:
                eth_usd_result = self.price_oracle.get_price("ETH", "USD")
                eth_usd = eth_usd_result.price if eth_usd_result else None
            if ait_usd is None:
                ait_usd_result = self.price_oracle.get_price("AIT", "USD")
                ait_usd = ait_usd_result.price if ait_usd_result else None
            if eth_usd is None or ait_usd is None:
                logger.error("Cannot get prices for ETH/USD or AIT/USD")
                return None
            if ait_usd == 0:
                logger.error("AIT/USD price is zero")
                return None
            ait_amount = eth_amount * Decimal(eth_usd) / Decimal(ait_usd)
            logger.info("Price calculation: %s ETH * $%s / $%s = %s AIT", eth_amount, eth_usd, ait_usd, ait_amount)
            return ait_amount
        except Exception as e:
            logger.error("Error calculating AIT amount: %s", e)
            return None

    @staticmethod
    def _envelope_tx_hash(transaction: dict) -> str:
        """Local copy of mempool.compute_tx_hash — sha256 of canonical JSON.

        Deriving the hash at sign time means the payout is trackable even if
        the first POST never returns (accepted-then-timeout), and proves a
        rebroadcast carries the identical envelope.
        """
        import hashlib
        import json

        canonical = json.dumps(transaction, sort_keys=True, separators=(",", ":")).encode()
        return "0x" + hashlib.sha256(canonical).hexdigest()

    def _build_signed_transfer(self, to_address: str, amount: Decimal) -> dict | None:
        """Build and sign the payout TRANSFER envelope (no network submit)."""
        if not self.genesis_private_key:
            logger.error("Cannot build payout - no private key")
            return None
        try:
            import json

            import httpx
            from eth_keys import keys
            from eth_utils import keccak, to_checksum_address

            sender_response = httpx.get(f"{self.blockchain_rpc_url}/rpc/account/{self.genesis_wallet_address}", timeout=5)
            if sender_response.status_code != 200:
                logger.error("Failed to get sender account: %s", sender_response.text)
                return None
            nonce = int(sender_response.json().get("nonce", 0))

            chain_id = os.getenv("CHAIN_ID", "ait-localnet")
            tx_amount = ait_to_units(amount)
            transaction = {
                "type": "TRANSFER",
                "chain_id": chain_id,
                "from": to_checksum_address(self.genesis_wallet_address),
                "to": to_checksum_address(to_address),
                "amount": tx_amount,
                "nonce": nonce,
                "fee": DEFAULT_TX_FEE_UNITS,
                "payload": {"amount": tx_amount},
            }
            private_key_hex = self.genesis_private_key.removeprefix("0x")
            private_key = keys.PrivateKey(bytes.fromhex(private_key_hex))
            signed_fields = {k: v for k, v in transaction.items() if k != "signature"}
            message = json.dumps(signed_fields, sort_keys=True, separators=(",", ":")).encode()
            signature = private_key.sign_msg_hash(keccak(message))
            transaction["signature"] = signature.to_bytes().hex()
            logger.info("Built signed payout: %s units (%s AIT) to %s (nonce=%s)", tx_amount, amount, to_address, nonce)
            return transaction
        except Exception as e:
            logger.error("Error building signed payout: %s", e)
            return None

    def _post_signed_tx(self, transaction: dict) -> str | None:
        """POST an already-signed payout envelope; returns its chain tx hash."""
        try:
            import httpx

            submit_response = httpx.post(
                f"{self.blockchain_rpc_url}/rpc/transaction",
                json=transaction,
                timeout=10,
            )
            if submit_response.status_code == 200:
                result = submit_response.json()
                tx_hash: str | None = result.get("transaction_hash") or result.get("tx_hash")
                logger.info("AIT transfer submitted: %s", tx_hash)
                return tx_hash
            logger.error("Failed to submit AIT transfer: %s", submit_response.text)
            return None
        except Exception as e:
            logger.error("Error submitting AIT transfer: %s", e)
            return None

    def submit_ait_transfer(self, to_address: str, amount: Decimal) -> str | None:
        """Build, sign and submit a payout; returns the chain tx hash."""
        transaction = self._build_signed_transfer(to_address, amount)
        if not transaction:
            return None
        return self._post_signed_tx(transaction)

    def _head_height(self) -> int | None:
        """Current chain head height from the local RPC."""
        try:
            import httpx

            resp = httpx.get(f"{self.blockchain_rpc_url}/rpc/head", timeout=5)
            if resp.status_code == 200:
                return int(resp.json().get("height", 0))
        except Exception as e:
            logger.warning("head height fetch failed: %s", e)
        return None

    def process_deposit(self, tx_hash: str, from_address: str, eth_amount: Decimal, tx_data: str) -> None:
        """Process a single ETH deposit.

        Every code path leaves the deposit in a terminal or PENDING_RETRY
        state so the block cursor can safely advance.
        """
        logger.info("Processing deposit: %s from %s, amount: %s ETH", tx_hash, from_address, eth_amount)
        existing = get_deposit(tx_hash)
        if existing:
            status = existing.get("status")
            if status in (
                BridgeDepositStatus.COMPLETED.value,
                BridgeDepositStatus.FAILED.value,
                BridgeDepositStatus.WRITTEN_OFF.value,
            ):
                logger.info("Deposit %s already terminal (%s), skipping", tx_hash, status)
                return
            if status == BridgeDepositStatus.SUBMITTED.value or existing.get("signed_tx"):
                # A signed payout envelope already exists — the confirmation
                # sweep owns it. Re-signing here would risk a double payout
                # if the original lands.
                logger.info("Deposit %s already has a submitted payout, skipping", tx_hash)
                return
            # PROCESSING / PENDING_RETRY with no envelope — crash before the
            # first signed submit. Retry is safe: nothing was broadcast.
            logger.warning("Deposit %s in non-terminal state %s, marking for retry", tx_hash, status)
            self._mark_for_retry(tx_hash, f"Recovered from non-terminal state: {status}")
            return
        ait_recipient = self.parse_ait_recipient(tx_data)
        if not ait_recipient:
            logger.warning("Could not parse AIT recipient from tx data: %s", tx_data)
            create_deposit(tx_hash, from_address, str(eth_amount), "")
            update_deposit(tx_hash, status=BridgeDepositStatus.FAILED, error_message="Invalid AIT recipient address")
            logger.critical(
                "ALERT: deposit %s permanently FAILED — %s ETH from %s received but cannot be paid (no recipient)",
                tx_hash,
                eth_amount,
                from_address,
            )
            return
        # Fetch oracle prices once for both calculation and storage
        eth_usd_result = self.price_oracle.get_price("ETH", "USD")
        ait_usd_result = self.price_oracle.get_price("AIT", "USD")
        eth_usd = eth_usd_result.price if eth_usd_result else None
        ait_usd = ait_usd_result.price if ait_usd_result else None
        ait_amount = self.calculate_ait_amount(eth_amount, eth_usd=eth_usd, ait_usd=ait_usd)
        if not ait_amount:
            # Temporary failure (oracle/RPC outage): keep the recipient and
            # leave the row PENDING_RETRY so a later pass recomputes the
            # price — never strand funds received.
            logger.error("Could not calculate AIT amount — deposit stays PENDING_RETRY")
            create_deposit(tx_hash, from_address, str(eth_amount), ait_recipient)
            self._mark_for_retry(tx_hash, "Price oracle unavailable")
            return
        if ait_amount < self.min_ait_deposit:
            logger.warning("Deposit %s: AIT amount %s below minimum %s, rejecting", tx_hash, ait_amount, self.min_ait_deposit)
            create_deposit(tx_hash, from_address, str(eth_amount), ait_recipient)
            update_deposit(
                tx_hash,
                ait_amount=str(ait_amount),
                status=BridgeDepositStatus.FAILED,
                error_message=f"AIT amount {ait_amount} below minimum {self.min_ait_deposit}",
            )
            logger.critical(
                "ALERT: deposit %s permanently FAILED — %s ETH received but below minimum payout", tx_hash, eth_amount
            )
            return
        deposit_id = create_deposit(tx_hash, from_address, str(eth_amount), ait_recipient)
        if not deposit_id:
            logger.info("Deposit %s already exists in database", tx_hash)
            return
        if not self._submit_payout(
            tx_hash,
            ait_recipient,
            ait_amount,
            eth_usd_price=str(eth_usd) if eth_usd else None,
            ait_usd_price=str(ait_usd) if ait_usd else None,
        ):
            self._mark_for_retry(tx_hash, "Failed to build signed payout")

    def _submit_payout(self, tx_hash: str, ait_recipient: str, ait_amount: Decimal, **price_fields: str | None) -> bool:
        """Build, sign, persist and broadcast a payout for an existing row.

        Ledger-first: the signed envelope (and its derived hash) is on
        disk before it can hit the mempool. A crash between POST and any
        later update can never leave an untracked payout, and recovery
        rebroadcasts this exact envelope instead of re-signing. Returns
        False when no transaction could be built (caller decides retry).
        """
        transaction = self._build_signed_transfer(ait_recipient, ait_amount)
        if not transaction:
            return False
        ait_tx_hash = self._envelope_tx_hash(transaction)
        update_deposit(
            tx_hash,
            ait_amount=str(ait_amount),
            signed_tx=json.dumps(transaction),
            envelope_hash=ait_tx_hash,
            submitted_height=self._head_height(),
            rebroadcast_count=0,
            ait_tx_hash=ait_tx_hash,
            status=BridgeDepositStatus.SUBMITTED,
            **price_fields,
        )
        posted = self._post_signed_tx(transaction)
        if posted and posted != ait_tx_hash:
            # The RPC normalized the tx differently — its hash is what the
            # chain/mempool will store, so seal lookups must use it. The
            # derived envelope_hash stays as the envelope-integrity anchor.
            logger.warning("RPC returned hash %s differing from derived %s", posted, ait_tx_hash)
            update_deposit(tx_hash, ait_tx_hash=posted)
        if posted:
            logger.info(
                "Payout for deposit %s broadcast as %s — awaiting %s-block seal",
                tx_hash,
                ait_tx_hash,
                self.payout_seal_depth,
            )
        else:
            update_deposit(tx_hash, error_message="Submit failed — awaiting rebroadcast")
            logger.warning("Payout %s submit failed; sweep will rebroadcast the same envelope", ait_tx_hash)
        return True

    def _mark_for_retry(self, tx_hash: str, error_message: str) -> None:
        """Mark a deposit for retry instead of immediate failure."""
        from datetime import UTC, datetime, timedelta

        deposit = get_deposit(tx_hash)
        retry_count = (deposit.get("retry_count", 0) if deposit else 0) + 1
        max_retries = 5
        if retry_count >= max_retries:
            # Retries exhausted = funds received but not paid — alert, don't
            # let it disappear.
            logger.critical(
                "ALERT: deposit %s exhausted %s retries — funds received but not paid: %s",
                tx_hash,
                max_retries,
                error_message,
            )
            update_deposit(
                tx_hash,
                status=BridgeDepositStatus.FAILED,
                error_message=error_message,
                retry_count=retry_count,
                next_retry_at=None,
            )
            return
        # Exponential backoff: 30s, 2m, 10m, 1h, 4h
        backoff_seconds = [30, 120, 600, 3600, 14400]
        delay = backoff_seconds[min(retry_count - 1, len(backoff_seconds) - 1)]
        next_retry = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()
        logger.warning(
            "Deposit %s marked PENDING_RETRY (attempt %s/%s, next in %ss): %s",
            tx_hash,
            retry_count,
            max_retries,
            delay,
            error_message,
        )
        update_deposit(
            tx_hash,
            status=BridgeDepositStatus.PENDING_RETRY,
            error_message=error_message,
            retry_count=retry_count,
            next_retry_at=next_retry,
        )

    def process_retry_queue(self) -> None:
        """Re-attempt deposits in PENDING_RETRY status whose next_retry_at has passed."""
        deposits = get_deposits_for_retry()
        if not deposits:
            return
        logger.info("Retry queue: %s deposit(s) to re-attempt", len(deposits))
        for d in deposits:
            tx_hash = d["eth_tx_hash"]
            ait_recipient = d["ait_recipient"]
            ait_amount_str = d.get("ait_amount")
            if not ait_amount_str:
                # Price was unavailable when first seen — recompute now from
                # the stored ETH amount rather than marking FAILED (funds
                # were received; this is a temporary failure, not permanent).
                try:
                    ait_amount = self.calculate_ait_amount(Decimal(d["eth_amount"]))
                except Exception as e:
                    logger.error("Retry %s price recalculation error: %s", tx_hash, e)
                    self._mark_for_retry(tx_hash, f"Price recalculation error: {e}")
                    continue
                if not ait_amount:
                    self._mark_for_retry(tx_hash, "Price oracle still unavailable")
                    continue
                ait_amount_str = str(ait_amount)
                update_deposit(tx_hash, ait_amount=ait_amount_str)
            ait_amount = Decimal(ait_amount_str)
            if d.get("signed_tx"):
                # A payout envelope already exists — hand it to the
                # confirmation sweep. Re-signing would risk a double payout.
                logger.info("Retry deposit %s already has a signed payout, moving to SUBMITTED", tx_hash)
                update_deposit(tx_hash, status=BridgeDepositStatus.SUBMITTED)
                continue
            logger.info("Retrying deposit %s: %s AIT to %s", tx_hash, ait_amount, ait_recipient)
            transaction = self._build_signed_transfer(ait_recipient, ait_amount)
            if not transaction:
                self._mark_for_retry(tx_hash, "Retry: failed to build signed payout")
                continue
            payout_hash = self._envelope_tx_hash(transaction)
            update_deposit(
                tx_hash,
                signed_tx=json.dumps(transaction),
                envelope_hash=payout_hash,
                submitted_height=self._head_height(),
                rebroadcast_count=0,
                ait_tx_hash=payout_hash,
                status=BridgeDepositStatus.SUBMITTED,
                retry_count=d.get("retry_count", 0),
            )
            posted = self._post_signed_tx(transaction)
            if posted:
                logger.info("Retry payout for deposit %s broadcast as %s", tx_hash, posted)
            else:
                # Stay SUBMITTED — the sweep rebroadcasts the same envelope.
                update_deposit(tx_hash, error_message="Retry submit failed — awaiting rebroadcast")

    def process_submitted_deposits(self) -> None:
        """Confirm or rebroadcast payouts whose deposits are SUBMITTED.

        COMPLETED requires the payout sealed PAYOUT_SEAL_DEPTH deep. A
        payout that vanished from the mempool without sealing is rebroadcast
        with the stored envelope — identical signature, identical hash. A
        payout that sealed but failed at apply stays SUBMITTED and alerts:
        funds may or may not have moved; an operator decides, not the code.
        """
        try:
            import httpx
        except ImportError:
            return
        deposits = get_submitted_deposits()
        if not deposits:
            return
        head = self._head_height()
        for d in deposits:
            tx_hash = d["eth_tx_hash"]
            payout_hash = d.get("ait_tx_hash")
            signed_raw = d.get("signed_tx")
            if not signed_raw:
                # Corrupt row — signed with an unknown key shape we cannot
                # rebroadcast; alert rather than guess.
                logger.critical("ALERT: deposit %s is SUBMITTED with no stored envelope", tx_hash)
                continue
            sealed_height = None
            failed_on_chain = False
            if payout_hash:
                try:
                    resp = httpx.get(f"{self.blockchain_rpc_url}/rpc/transaction/{payout_hash}", timeout=5)
                    if resp.status_code == 200:
                        body = resp.json()
                        sealed_height = body.get("block_height")
                        st = (body.get("status") or "").lower()
                        if st and st not in ("pending", "confirmed", "success", ""):
                            failed_on_chain = True
                except Exception as e:
                    logger.warning("payout status fetch failed for %s: %s", payout_hash, e)
            if failed_on_chain:
                logger.critical(
                    "ALERT: payout %s for deposit %s sealed with failed status — staying SUBMITTED for operator review",
                    payout_hash,
                    tx_hash,
                )
                continue
            if sealed_height and head and head - int(sealed_height) >= self.payout_seal_depth:
                update_deposit(tx_hash, status=BridgeDepositStatus.COMPLETED, error_message="")
                logger.info("Payout %s sealed at height %s — deposit %s COMPLETED", payout_hash, sealed_height, tx_hash)
                continue
            # Not sealed deep enough (or not sealed at all).
            submitted_height = d.get("submitted_height") or (head or 0)
            rebroadcast_count = int(d.get("rebroadcast_count") or 0)
            if head is None:
                continue  # can't judge distance — try next poll
            if head - int(submitted_height) <= self.rebroadcast_blocks:
                continue  # still within the seal window
            if rebroadcast_count >= self.max_rebroadcasts:
                logger.critical(
                    "ALERT: payout %s for deposit %s unsealed after %s rebroadcasts — staying SUBMITTED",
                    payout_hash,
                    tx_hash,
                    rebroadcast_count,
                )
                continue
            envelope = json.loads(signed_raw)
            derived = self._envelope_tx_hash(envelope)
            expected = d.get("envelope_hash") or d.get("ait_tx_hash")
            if expected and derived != expected:
                logger.error("Stored envelope hash mismatch for %s (expected %s) — refusing rebroadcast", derived, expected)
                continue
            posted = self._post_signed_tx(envelope)
            new_count = rebroadcast_count + 1
            if posted:
                logger.warning(
                    "Rebroadcast unsealed payout %s for deposit %s (attempt %s) — identical envelope",
                    payout_hash,
                    tx_hash,
                    new_count,
                )
                update_deposit(
                    tx_hash,
                    rebroadcast_count=new_count,
                    submitted_height=head,
                    error_message="",
                )
            else:
                update_deposit(tx_hash, rebroadcast_count=new_count, error_message="Rebroadcast failed")

    def _account_nonce(self, address: str) -> int | None:
        """On-chain nonce of an account from the local RPC."""
        try:
            import httpx

            resp = httpx.get(f"{self.blockchain_rpc_url}/rpc/account/{address}", timeout=5)
            if resp.status_code == 200:
                return int(resp.json().get("nonce", 0))
        except Exception as e:
            logger.warning("account nonce fetch failed for %s: %s", address, e)
        return None

    def _tx_on_chain(self, tx_hash: str) -> bool | None:
        """True if tx_hash is sealed in a block, False if absent/mempool, None if unknown."""
        try:
            import httpx

            resp = httpx.get(f"{self.blockchain_rpc_url}/rpc/transaction/{tx_hash}", timeout=5)
            if resp.status_code == 200:
                return resp.json().get("block_height") is not None
            if resp.status_code == 404:
                return False
        except Exception as e:
            logger.warning("tx status fetch failed for %s: %s", tx_hash, e)
        return None

    def abandon_payout(self, tx_hash: str) -> tuple[bool, str]:
        """Abandon a stuck SUBMITTED payout so it may be re-signed.

        Re-signing is only safe when the stored envelope can no longer
        land, which requires BOTH: the payout account's on-chain nonce
        has already passed the envelope's nonce, and the envelope's hash
        is not sealed on chain. Anything less refuses — a premature
        re-sign is how double payments happen.
        """
        d = get_deposit(tx_hash)
        if not d:
            return False, f"no deposit row {tx_hash}"
        if d.get("status") != BridgeDepositStatus.SUBMITTED.value:
            return False, f"deposit {tx_hash} is {d.get('status')}, not submitted"
        signed_raw = d.get("signed_tx")
        if not signed_raw:
            return False, f"deposit {tx_hash} has no stored envelope"
        envelope = json.loads(signed_raw)
        env_nonce = int(envelope.get("nonce", -1))
        payout_hash = d.get("ait_tx_hash") or d.get("envelope_hash") or self._envelope_tx_hash(envelope)
        chain_nonce = self._account_nonce(self.genesis_wallet_address)
        if chain_nonce is None:
            return False, "cannot read payout account nonce — refusing"
        if chain_nonce <= env_nonce:
            return False, (
                f"payout account nonce {chain_nonce} has not passed envelope nonce {env_nonce} "
                "— the envelope can still land; refusing to re-sign"
            )
        sealed = self._tx_on_chain(payout_hash)
        if sealed is None:
            return False, "cannot verify payout seal status — refusing"
        if sealed:
            return False, f"payout {payout_hash} IS sealed on chain — the deposit will complete normally; refusing"
        # The envelope can never land: its nonce slot is taken by a later
        # sealed transaction and the hash itself is not on chain. Free the
        # row for a fresh payout — the retry path builds it ledger-first.
        # The envelope fields are cleared (empty string = falsy) so no
        # path hands the dead envelope back to the sweep.
        update_deposit(
            tx_hash,
            signed_tx="",
            envelope_hash="",
            ait_tx_hash="",
            status=BridgeDepositStatus.PENDING_RETRY,
            error_message=(
                f"Abandoned payout {payout_hash}: account nonce {chain_nonce} > envelope nonce {env_nonce}, "
                "envelope not sealed — safe to re-sign"
            ),
            next_retry_at=None,
        )
        return True, f"payout {payout_hash} abandoned; deposit {tx_hash} queued for a fresh payout"

    def _check_float(self) -> None:
        """Alert once per poll when the payout wallet is running dry."""
        try:
            import httpx

            resp = httpx.get(f"{self.blockchain_rpc_url}/rpc/account/{self.genesis_wallet_address}", timeout=5)
            if resp.status_code == 200:
                balance = int(resp.json().get("balance", 0))
                if balance < self.low_float_units:
                    logger.critical(
                        "ALERT: bridge payout float low — %s units left (< %s); deposits will pile up in PENDING_RETRY",
                        balance,
                        self.low_float_units,
                    )
        except Exception as e:
            logger.warning("payout float check failed: %s", e)
        try:
            wei = int(self.eth_rpc.get_balance(self.bridge_eth_address).get("wei", 0))
            eth = Decimal(wei) / Decimal(10**18)
            if eth < self.low_float_eth:
                logger.critical(
                    "ALERT: bridge ETH float low — %s ETH (< %s); cannot cover refund/withdrawal gas",
                    eth.normalize(),
                    self.low_float_eth,
                )
        except Exception as e:
            logger.warning("ETH float check failed: %s", e)

    def poll_ethereum(self) -> None:
        """Poll Ethereum for new transactions to bridge address."""
        try:
            self._check_float()
            w3 = self.eth_rpc._get_web3()
            # Only pay for deposits buried by BRIDGE_CONFIRMATIONS blocks —
            # a reorg of an unconfirmed deposit must never have been paid.
            latest_block = max(0, w3.eth.block_number - self.confirmations)
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

            for block_num in range(start_block, latest_block + 1):
                block = w3.eth.get_block(block_num, full_transactions=True)
                if not block or not block.get("transactions"):
                    set_cursor("last_processed_block", block_num)
                    continue
                for tx in block["transactions"]:
                    from_address = tx.get("from", "")
                    if from_address and from_address.lower() == self.bridge_eth_address:
                        # Self-sends and the bridge's own outbound sends are
                        # never deposits — otherwise the wallet key holder
                        # could mint AIT payouts for the price of gas.
                        logger.debug("Skipping own tx %s", tx.hash.hex())
                        continue
                    to_address = tx.get("to", "")
                    if to_address and to_address.lower() == self.bridge_eth_address:
                        value = tx.get("value", 0)
                        eth_amount = Decimal(value) / Decimal(10**18)
                        if eth_amount < self.min_eth_deposit:
                            logger.debug("Skipping small deposit: %s ETH", eth_amount)
                            continue
                        tx_hash = tx.hash.hex()
                        tx_data = tx.get("input", "0x")
                        logger.info("Found deposit: %s from %s, amount: %s ETH", tx_hash, from_address, eth_amount)
                        try:
                            self.process_deposit(tx_hash, from_address, eth_amount, tx_data)
                        except Exception:
                            logger.exception("Unexpected error processing deposit %s, marking for retry", tx_hash)
                            try:
                                self._mark_for_retry(tx_hash, "Unexpected error during processing")
                            except Exception:
                                logger.exception("Failed to mark deposit %s for retry", tx_hash)
                # Advance cursor only after every deposit in this block is
                # in a terminal or PENDING_RETRY state (or was skipped).
                set_cursor("last_processed_block", block_num)
        except Exception as e:
            logger.error("Error polling Ethereum: %s", e)

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
                try:
                    self.poll_ethereum()
                    self.process_retry_queue()
                    self.process_submitted_deposits()
                except Exception as e:
                    logger.error("Error in polling loop: %s", e)
                interval = self.burst_interval if now < self._burst_until else self.poll_interval
                next_poll = time.monotonic() + interval
            await asyncio.sleep(1.0)


def main() -> None:
    """Main entry point."""
    monitor = BridgeMonitor()
    asyncio.run(monitor.run())


if __name__ == "__main__":
    main()
