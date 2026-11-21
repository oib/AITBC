"""
MarketService market-job escrow settlement mixin.

Split from ``jobs.py`` (#1860): the escrow proof, CAS settlement writes
and release/refund paths live here; job lifecycle CRUD, disputes, access
tokens and health checks stay in ``jobs.py``.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, update
from sqlmodel import col, select

from aitbc.aitbc_logging import get_logger
from aitbc.utils.chain_id import resolve_chain_id
from aitbc.utils.units import units_to_ait

from ...config import settings
from ...domain.market import MarketJob, MarketJobPayment

from .shared import (
    _ACCESS_TOKEN_ACTIVE_STATES,
    ESCROW_LOCKED_STATES,
    escrow_addresses_match,
    locked_escrow_matches,
)
from .jobs import _JobsMixin


logger = get_logger(__name__)


class _JobsSettlementMixin(_JobsMixin):
    @staticmethod
    def _pin_payload(job: MarketJob, size: int | None, pin_tx_hash: str | None, provider_confirmed: bool) -> dict[str, Any]:
        """#1922: ``pinned``/``provider_confirmed`` are delivery evidence —
        only the signed provider attestation (``provider_confirmed=True``,
        gated by the route's wallet-signature + cid/size binding check) may
        set them. Unsigned pin-confirm reports stay informational: the
        caller's ``size``/``pin_tx_hash`` are recorded but never prove
        delivery."""
        payload = dict(job.payload or {})
        if provider_confirmed:
            payload["pinned"] = True
            payload["provider_confirmed"] = True
            # #1976: start of the buyer-acceptance window — a provider-signed
            # release is refused until it has elapsed. Kept across re-confirms
            # so the provider cannot restart (or backdate) the clock.
            payload.setdefault("provider_confirmed_at", datetime.now(UTC).replace(tzinfo=None).isoformat())
        if size is not None:
            payload["size"] = size
        if pin_tx_hash:
            payload["pin_tx_hash"] = pin_tx_hash
        return payload

    async def _cas_payment_status(self, payment_id: str, from_statuses: frozenset[str] | str, values: dict[str, Any]) -> bool:
        """#1790: conditional payment-status write — the from_status predicate
        in WHERE is the compare-and-swap; True iff this call won the flip."""
        if isinstance(from_statuses, str):
            status_pred = col(MarketJobPayment.status) == from_statuses
        else:
            status_pred = col(MarketJobPayment.status).in_(from_statuses)
        claim = await self.session.execute(
            update(MarketJobPayment)
            .where(col(MarketJobPayment.id) == payment_id, status_pred)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return getattr(claim, "rowcount", 0) == 1

    async def _cas_settle_terminal(
        self,
        job_id: str,
        *,
        allowed_states: set[str] | frozenset[str],
        job_values: dict[str, Any],
        payment: MarketJobPayment | None,
        payment_from_statuses: frozenset[str] | str,
        payment_values: dict[str, Any],
    ) -> dict[str, Any] | None:
        """#1835 F2: CAS the release/refund terminal writes.

        The payment flip and the job transition are conditional UPDATEs —
        the allowed-state set plus the no-open-dispute clause in WHERE are
        the compare-and-swap; a concurrent cancel/settle/dispute that
        committed during the RPC window wins. Returns None when the job CAS
        won (caller commits); on a lost race the transaction is rolled back
        (reverting the payment flip) and the winning job's dict is returned
        (#1790 pattern).
        """
        if payment is not None:
            await self._cas_payment_status(payment.id, payment_from_statuses, payment_values)
        claim = await self.session.execute(
            update(MarketJob)
            .where(
                col(MarketJob.id) == job_id,
                col(MarketJob.state).in_(allowed_states),
                or_(col(MarketJob.disputed_at).is_(None), col(MarketJob.dispute_cleared_at).is_not(None)),
            )
            .values(**job_values)
            .execution_options(synchronize_session=False)
        )
        if getattr(claim, "rowcount", 0) == 1:
            return None
        await self.session.rollback()
        winner = await self.session.get(MarketJob, job_id)
        return self._job_to_dict(winner) if winner else {}

    @staticmethod
    def _settle_payment_values(
        *,
        status: str,
        tx_hash: str,
        amount: Any,
        now: datetime,
        amount_field: str,
        hash_field: str,
        ts_field: str,
    ) -> dict[str, Any]:
        values: dict[str, Any] = {
            "status": status,
            hash_field: tx_hash,
            ts_field: now,
            "updated_at": now,
        }
        if amount is not None:
            values[amount_field] = Decimal(str(amount))
        return values

    @staticmethod
    def _refundable_job_states(payment: MarketJobPayment | None) -> set[str]:
        """#1835 F2: state set mirroring _guard_refund_settlement — QUEUED/
        RUNNING only when the payment is already refund_pending (cancel
        flagged it), never for a live escrowed payment."""
        states = {"FAILED", "CANCELED", "EXPIRED", "REFUNDED"}
        if payment is not None and payment.status == "refund_pending":
            states |= {"QUEUED", "RUNNING"}
        return states

    @staticmethod
    def _addresses_match(left: Any, right: Any) -> bool:
        """Best-effort address equality — delegates to the shared helper so
        the settlement mixin and the sweeper's pending-payment adoption
        (#2348) apply identical binding rules."""
        return escrow_addresses_match(left, right)

    async def _require_locked_escrow(self, job: MarketJob, payment: MarketJobPayment) -> None:
        """#1564: the pending->escrowed flip needs on-chain escrow proof.

        The chain escrow is keyed by the market job id (``/rpc/escrow/{job_id}``),
        so proof is: the escrow row exists, it is in a locked state (not
        created/released/refunded/expired), and — where the response and the
        job both name them — the locked amount and the buyer/provider parties
        match this job's payment record. Anything less used to flip the
        payment to ``escrowed`` on an HTTP call alone.
        """
        escrow = await self._rpc_client.verify_escrow(job.id)
        if not escrow:
            raise ValueError(f"No on-chain escrow found for job {job.id}; payment cannot be marked escrowed")
        # Whitelist, not blacklist: the node reports contract states
        # (created/funded/job_started/job_completed/disputed/resolved/released/
        # refunded/expired) or the escrow row status (locked/released/refunded/
        # settlement_failed). Only the states where funds are actually locked
        # qualify — anything else (created-but-unfunded, settlement_failed,
        # terminal) must not flip the payment.
        state = str(escrow.get("state") or "").lower()
        if state not in ESCROW_LOCKED_STATES:
            raise ValueError(f"On-chain escrow for job {job.id} is not locked (state={state or 'unknown'})")
        amount = escrow.get("amount")
        if amount is not None:
            try:
                locked = Decimal(str(amount))
            except Exception as e:
                raise ValueError(f"On-chain escrow for job {job.id} has an unreadable amount") from e
            if not locked.is_finite() or locked != payment.amount:
                raise ValueError(f"On-chain escrow amount {locked} does not match job payment amount {payment.amount}")
        for field, expected in (("buyer", job.buyer_address), ("provider", job.provider_address)):
            actual = escrow.get(field)
            if actual and expected and not self._addresses_match(actual, expected):
                raise ValueError(f"On-chain escrow {field} does not match job {job.id}")

    async def _job_token_escrow_verified(self, job: MarketJob, payment: MarketJobPayment | None) -> bool:
        """#2322 MARKET-TOKEN-ESCROW-BIND-1: does this job have locked escrow?

        Shop access tokens (``GET /v1/market/access/{key}``) authorize paid
        shop work, so lifecycle state (QUEUED/RUNNING + TTL) is not enough —
        the escrow must be locked. ``payment.status == "escrowed"`` is itself
        only ever written after ``_require_locked_escrow``'s on-chain proof of
        the escrow keyed by ``job.id``, so it passes directly for
        self-bound jobs (an ``escrow_job_id`` alias record never proved that
        key — it takes the live verify). Every other status — above all ``pending``,
        which is what ``create_market_job`` writes and what the paid
        whisper/ffmpeg/ollama and ``ai submit`` flows keep for the life of
        the token (their escrow lives on-chain but nothing flips the DB row)
        — falls through to a live ``GET /rpc/escrow/{key}`` read applying the
        same locked-state whitelist, amount and party binding as the
        pin-confirm flip. The escrow is keyed by the market job id for the
        ``aitbc market run``/IPFS flows; ``ai submit`` transcribe registers
        its token record under a distinct ``ai_job_*`` id (so the market
        sweeper can never alias the coordinator escrow) and binds the real
        escrow via ``payload["escrow_job_id"]`` instead — the amount/party
        match still binds that proof to this job's declared terms.

        Fails closed: no payment row, an absent/unreadable escrow, a
        non-locked state, or an RPC error all deny the token.

        #2325 MARKET-ESCROW-ALIAS-1: the escrow key is resolved BEFORE the
        escrowed fast-path because ``payment.status == "escrowed"`` only ever
        proved the escrow keyed by ``job.id`` — for an ``escrow_job_id``
        alias record that is the wrong escrow, so alias jobs always take the
        live verify below. And the key must be exclusively claimed by this
        job (``_escrow_key_claimed_by_this_job``): the on-chain record
        carries no market-job reference and every compared field is
        caller-supplied, so uniqueness is the only binding this layer can
        enforce against one escrow authorizing unlimited tokens.
        """
        if payment is None:
            return False
        escrow_key = str((job.payload or {}).get("escrow_job_id") or job.id)
        if not await self._escrow_key_claimed_by_this_job(job, escrow_key):
            return False
        if payment.status == "escrowed" and escrow_key == job.id:
            return True
        try:
            escrow = await self._rpc_client.verify_escrow(escrow_key)
        except Exception as e:  # noqa: BLE001 - unverifiable escrow must deny, not 500
            logger.warning("Access-token escrow check failed for job %s: %s", job.id, e)
            return False
        if not escrow:
            return False
        if not self._locked_escrow_matches(escrow, job, payment):
            return False
        if (job.payload or {}).get("escrow_job_id") and not await self._alias_lock_binds_market_job(escrow, job):
            return False
        return True

    async def _alias_lock_binds_market_job(self, escrow: dict, job: MarketJob) -> bool:
        """#2326: the escrow's signed ESCROW_LOCK tx must name this market job.

        ``ai submit``/``ai pay`` embed ``market_job_id`` in the lock payload
        when the escrow backs a market alias claim, so the on-chain record —
        not caller-supplied job fields — decides which market job an escrow
        may authorize. Escrows locked before the field existed carry no
        binding and fail closed: their in-flight alias tokens expire with the
        job TTL.
        """
        lock_tx_hash = escrow.get("lock_tx_hash")
        if not lock_tx_hash:
            return False
        try:
            chain_id = settings.default_chain_id or resolve_chain_id()
            tx = await self._rpc_client.get_transaction(str(lock_tx_hash), chain_id=chain_id)
        except Exception as e:  # noqa: BLE001 - unverifiable binding must deny, not 500
            logger.warning("Alias escrow lock lookup failed for job %s: %s", job.id, e)
            return False
        payload = (tx or {}).get("payload") or {}
        return payload.get("market_job_id") == job.id

    async def _escrow_key_claimed_by_this_job(self, job: MarketJob, escrow_key: str) -> bool:
        """#2325 MARKET-ESCROW-ALIAS-1: is ``job`` the earliest active claimant of ``escrow_key``?

        The on-chain escrow record carries no market-job reference — its
        ``job_id`` IS the lookup key — so the market layer cannot prove a
        declared ``payload["escrow_job_id"]`` (or a caller-chosen job id that
        names a foreign escrow) belongs to this job: every field the escrow
        check compares (amount, buyer, provider) is caller-supplied at
        ``POST /v1/market/jobs``. One locked escrow could therefore authorize
        unlimited shop tokens. The enforceable binding in this layer is
        uniqueness: one locked escrow may back at most one live market-job
        token. A job claims a key by id (the ``aitbc market run`` convention
        keys the escrow by the market job id itself) or by
        ``payload["escrow_job_id"]`` (the ``ai submit`` coordinator-escrow
        binding). Among active claimants the earliest-created wins, so a
        later alias never mints a second token off the same escrow and
        registering an alias cannot strip the legitimate job's token; when
        the winner's job expires the key is released for the next claimant,
        bounding any squatting alias by its own TTL.
        """
        # #2326 MARKET-ESCROW-SQUAT-1: expired-but-unswept jobs and unpaid
        # jobs cannot hold an escrow claim — a year-2100 expires_at or a
        # zero-amount registration used to squat a key indefinitely and
        # deny the legitimate claimant its token.
        now = datetime.now(UTC).replace(tzinfo=None)
        stmt = (
            select(col(MarketJob.id))
            .where(
                col(MarketJob.state).in_(_ACCESS_TOKEN_ACTIVE_STATES),
                or_(col(MarketJob.expires_at).is_(None), col(MarketJob.expires_at) > now),
                # NULL payment_amount = pre-denormalization row — unknown
                # stake, kept claimable; an explicit 0 is a free job and
                # has no escrow to bind.
                or_(col(MarketJob.payment_amount).is_(None), col(MarketJob.payment_amount) > 0),
                or_(
                    col(MarketJob.id) == escrow_key,
                    col(MarketJob.payload)["escrow_job_id"].as_string() == escrow_key,
                ),
            )
            .order_by(col(MarketJob.created_at), col(MarketJob.id))
            .limit(1)
        )
        earliest = (await self.session.execute(stmt)).scalar_one_or_none()
        return earliest == job.id

    def _locked_escrow_matches(self, escrow: dict, job: MarketJob, payment: MarketJobPayment) -> bool:
        """Bool form of ``_require_locked_escrow``'s checks for the token path.

        Same locked-state whitelist, amount and party binding — but a mismatch
        denies the token (False) instead of raising, since this runs inside a
        read-only verify endpoint. Delegates to the shared
        ``locked_escrow_matches`` so the sweeper's pending-payment adoption
        (#2348) applies identical rules.
        """
        if not locked_escrow_matches(
            escrow,
            amount=payment.amount,
            buyer_address=job.buyer_address,
            provider_address=job.provider_address,
        ):
            return False
        # #2326 MARKET-ESCROW-SQUAT-1: an escrow_job_id alias claim must name
        # its buyer. Every compared field is caller-supplied at creation, so
        # an omitted buyer_address used to skip the party check entirely
        # while a squatter pointed a self-declared job at a victim's locked
        # escrow with copied public terms. The shared proof skips absent
        # fields, so alias claims re-check buyer presence+match here.
        if (job.payload or {}).get("escrow_job_id"):
            actual = escrow.get("buyer")
            expected = job.buyer_address
            if not expected or not actual or not self._addresses_match(actual, expected):
                return False
        return True

    async def confirm_market_job_pin(
        self,
        job_id: str,
        size: int | None = None,
        pin_tx_hash: str | None = None,
        provider_confirmed: bool = False,
    ) -> dict[str, Any]:
        """Confirm a job has been pinned.

        #1922: only ``provider_confirmed=True`` — which the route accepts
        solely with the provider's wallet signature bound to the job's CID
        and reported size — records delivery evidence (``pinned``,
        ``provider_confirmed``) and CASes QUEUED -> RUNNING. Unsigned calls
        are informational: they record ``size``/``pin_tx_hash`` and may flip
        a pending payment to escrowed on verified on-chain proof, but they
        never move the job to RUNNING, so they cannot authorize release.
        """
        try:
            job = await self.session.get(MarketJob, job_id)
            if not job:
                raise ValueError(f"Job not found: {job_id}")

            if job.state not in {"QUEUED", "RUNNING"}:
                return self._job_to_dict(job)

            payment = None
            if job.payment_id:
                payment = await self.session.get(MarketJobPayment, job.payment_id)
            # #1564: pending->escrowed is a settlement claim — it requires the
            # escrow to exist on-chain with matching amount and parties. The
            # check runs before any mutation so a failed proof leaves the job
            # untouched and the provider can retry once the lock lands.
            if payment is not None and payment.status == "pending":
                await self._require_locked_escrow(job, payment)

            # payload is a plain JSON column: reassign, don't mutate in place,
            # or SQLAlchemy never sees the change and the update is dropped.
            payload = self._pin_payload(job, size, pin_tx_hash, provider_confirmed)

            now = datetime.now(UTC).replace(tzinfo=None)

            # #1790: pending->escrowed is a CAS — rowcount decides, and the
            # proof above already ran so a lost race cannot skip it. This
            # flip is settlement bookkeeping backed by the on-chain escrow
            # proof, not delivery evidence: it runs for unsigned reports too
            # so an expired job's escrowed payment can still refund (#1922).
            payment_flipped = False
            if payment is not None and payment.status == "pending":
                payment_flipped = await self._cas_payment_status(
                    payment.id, "pending", {"status": "escrowed", "escrowed_at": now, "updated_at": now}
                )

            # #1790: CAS the lifecycle write. Only the signed provider
            # attestation (``provider_confirmed``, verified at the route)
            # transitions QUEUED -> RUNNING — RUNNING is the release gate's
            # delivery proof, so an unsigned size/pin_tx_hash report must
            # never mint it (#1922). Unsigned calls still reassign payload
            # (recording the reported size/hash) and keep the current state.
            # A concurrent cancel that committed first yields rowcount 0 —
            # roll back (reverting the payment flip) and return the state
            # that actually won instead of overwriting it.
            job_values: dict[str, Any] = {
                "payload": payload,
                "payment_status": "escrowed" if payment_flipped else job.payment_status,
                "updated_at": now,
            }
            if provider_confirmed:
                job_values["state"] = "RUNNING"
            claim = await self.session.execute(
                update(MarketJob)
                .where(col(MarketJob.id) == job_id, col(MarketJob.state).in_({"QUEUED", "RUNNING"}))
                .values(**job_values)
                .execution_options(synchronize_session=False)
            )
            if getattr(claim, "rowcount", 0) != 1:
                await self.session.rollback()
                job = await self.session.get(MarketJob, job_id)
                return self._job_to_dict(job) if job else {}

            await self.session.commit()
            await self.session.refresh(job)

            return self._job_to_dict(job)
        except Exception as e:
            await self.session.rollback()
            logger.error("Error in confirm_market_job_pin: %s: %s", type(e).__name__, e)
            raise

    async def _require_confirmed_settle_tx(self, tx_hash: str, job: MarketJob, expected_type: str) -> dict[str, Any]:
        """Refuse a caller-supplied settle hash that is not THIS job's escrow settlement.

        A caller-supplied hash is evidence, not authority: verify it on-chain
        like complete_bid does before trusting the state flip (#814), and bind
        it to this job — any confirmed transaction used to count (#1564). The
        chain escrow is keyed by the market job id (``/rpc/escrow/{job_id}``),
        so the sealed tx must be an ``expected_type`` transaction whose payload
        ``job_id`` is this job's id.

        #1584 extends the binding to the parties: the payload's
        ``buyer_escrow_addr``/``provider_escrow_addr`` must match the job's
        recorded addresses when present, and the tx recipient must be the
        escrow payee (provider on release, buyer on refund). Returns the
        verified tx so callers can derive settlement amounts from the
        on-chain ``value`` instead of trusting caller-supplied figures.
        """
        chain_id = settings.default_chain_id or resolve_chain_id()
        tx = await self._rpc_client.get_transaction(tx_hash, chain_id=chain_id)
        if not tx or tx.get("status") != "confirmed":
            raise ValueError(f"Supplied tx_hash {tx_hash} is not a confirmed on-chain transaction")
        tx_type = tx.get("type") or tx.get("transaction_type")
        if tx_type != expected_type:
            raise ValueError(f"Transaction {tx_hash} is type {tx_type!r}, not {expected_type}")
        payload = tx.get("payload") or {}
        if payload.get("job_id") != job.id:
            raise ValueError(f"Transaction {tx_hash} is not bound to escrow for job {job.id}")

        is_release = expected_type == "ESCROW_RELEASE"
        payee_field = "provider_escrow_addr" if is_release else "buyer_escrow_addr"
        counterparty_field = "buyer_escrow_addr" if is_release else "provider_escrow_addr"
        job_payee = job.provider_address if is_release else job.buyer_address
        job_counterparty = job.buyer_address if is_release else job.provider_address
        expected_payee = self._canonical_address(str(job_payee or ""))
        expected_counterparty = self._canonical_address(str(job_counterparty or ""))
        payload_payee = payload.get(payee_field)
        payload_counterparty = payload.get(counterparty_field)
        if expected_payee and payload_payee and self._canonical_address(str(payload_payee)) != expected_payee:
            raise ValueError(f"Transaction {tx_hash} payload {payee_field} does not match job {job.id} payee {expected_payee}")
        if (
            expected_counterparty
            and payload_counterparty
            and self._canonical_address(str(payload_counterparty)) != expected_counterparty
        ):
            raise ValueError(
                f"Transaction {tx_hash} payload {counterparty_field} does not match job {job.id} counterparty {expected_counterparty}"
            )
        # The sealed row spells it `recipient`; a mempool-shaped dict uses `to`.
        tx_recipient = self._canonical_address(str(tx.get("recipient") or tx.get("to") or ""))
        effective_payee = self._canonical_address(str(payload_payee)) if payload_payee else expected_payee
        if effective_payee and tx_recipient and tx_recipient != effective_payee:
            raise ValueError(
                f"Transaction {tx_hash} pays {tx_recipient}, not the escrow payee {effective_payee} for job {job.id}"
            )
        return tx

    @staticmethod
    def _settled_amount_ait(tx: dict[str, Any]) -> Decimal | None:
        """AIT value a verified settle tx moved, from its on-chain ``value``.

        The sealed row spells it ``value``; a mempool-shaped dict uses
        ``amount``. Returns None when the tx carries no readable amount —
        callers then leave the settlement amount unset rather than storing a
        caller-supplied figure (#1584).
        """
        raw = tx.get("value", tx.get("amount"))
        if raw is None:
            return None
        try:
            return units_to_ait(int(raw))
        except (TypeError, ValueError):
            return None

    def _guard_release_settlement(
        self, job: MarketJob, payment: MarketJobPayment | None, job_id: str
    ) -> dict[str, Any] | None:
        """#1564 release state guards.

        Only an escrowed payment on a job that is not already
        refunded/cancelled/failed may be released. An already-released pair
        replays idempotently (returns the job dict); anything else raises.
        """
        if payment is None or payment.status not in {"escrowed", "released"}:
            raise ValueError(f"Job {job_id} has no escrowed payment to release")
        if payment.status == "released" and job.state == "RELEASED":
            return self._job_to_dict(job)
        # #1835 F1: an open dispute freezes settlement on every path, not
        # just the sweeper — the chain escrow has no dispute concept, so
        # without this check a dispute-then-release call pays out anyway.
        if job.disputed_at is not None and job.dispute_cleared_at is None:
            raise ValueError(f"Cannot release escrow for job {job_id}: an open dispute freezes settlement")
        if job.state in {"CANCELED", "FAILED", "REFUNDED"}:
            raise ValueError(f"Cannot release escrow for job {job_id} in state {job.state}")
        # Release pays the provider for delivered work. Legitimate callers
        # reach it from RUNNING (pin-confirm is the delivery proof for IPFS
        # rentals) or COMPLETED; QUEUED has no delivery at all and EXPIRED is
        # owned by the refund path — releasing there would race the buyer's
        # refund and could pay the provider for undelivered work (#v11 item
        # 10 residual).
        if job.state not in {"RUNNING", "COMPLETED"}:
            raise ValueError(
                f"Cannot release escrow for job {job_id} in state {job.state}; only RUNNING/COMPLETED jobs release"
            )
        # #1922: RUNNING is only minted by the signed provider pin-confirm,
        # but rows that reached RUNNING before this gate existed may carry
        # no attestation — unsigned pin-confirm used to CAS them there.
        # Fail closed: a RUNNING job without ``provider_confirmed`` in its
        # payload has no verified pin evidence and must not release (it
        # expires into the refund path instead). COMPLETED is exempt: no
        # pin-confirm path sets it, so it is outside this threat model.
        if job.state == "RUNNING" and not (job.payload or {}).get("provider_confirmed"):
            raise ValueError(f"Cannot release escrow for job {job_id}: RUNNING without a provider pin attestation (#1922)")
        return None

    def _guard_refund_settlement(self, job: MarketJob, payment: MarketJobPayment | None, job_id: str) -> dict[str, Any] | None:
        """#1564 refund state guards.

        Refund only escrowed (or already refund-pending) payments, never a
        released one, and never a job that is still queued/running unless
        cancel already flagged the payment refund_pending. An
        already-refunded pair replays idempotently (returns the job dict).
        """
        if payment is None or payment.status not in {"escrowed", "refund_pending", "refunded"}:
            raise ValueError(f"Job {job_id} has no refundable escrowed payment")
        if payment.status == "refunded" and job.state == "REFUNDED":
            return self._job_to_dict(job)
        # #1835 F1: same freeze as release — an open dispute blocks refund.
        if job.disputed_at is not None and job.dispute_cleared_at is None:
            raise ValueError(f"Cannot refund escrow for job {job_id}: an open dispute freezes settlement")
        if payment.status == "released" or job.state in {"RELEASED", "COMPLETED"}:
            raise ValueError(f"Cannot refund escrow for job {job_id}: payment already released")
        if job.state in {"QUEUED", "RUNNING"} and payment.status != "refund_pending":
            raise ValueError(f"Cannot refund escrow for job {job_id} in state {job.state}; cancel it first")
        return None

    async def release_market_job_payment(self, job_id: str, release_data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Release the escrow for a completed market job."""
        try:
            release_data = release_data or {}
            job = await self.session.get(MarketJob, job_id)
            if not job:
                raise ValueError(f"Job not found: {job_id}")

            payment: MarketJobPayment | None = None
            if job.payment_id:
                payment = await self.session.get(MarketJobPayment, job.payment_id)

            replay = self._guard_release_settlement(job, payment, job_id)
            if replay is not None:
                return replay

            tx_hash = release_data.get("tx_hash")
            released_amount = release_data.get("released_amount")
            if tx_hash:
                tx = await self._require_confirmed_settle_tx(tx_hash, job, "ESCROW_RELEASE")
                # The caller's released_amount is a claim, not evidence: store
                # the amount the verified transaction actually moved (#1584).
                released_amount = self._settled_amount_ait(tx)
            else:
                # The chain escrow is keyed by job_id — the market job id is
                # the escrow's job_id (the buyer CLI escrows under it).
                # escrow_contract_id now persists that same job.id at
                # creation (#1634) but remains informational only — the RPC
                # path key is always job.id, never the column (#1564).
                result = await self._rpc_client.release_escrow(job.id)
                if not (result and result.get("success")):
                    raise ValueError(f"Escrow release failed for job {job_id}: {result}")
                tx_hash = str(result.get("tx_hash", ""))
                released_amount = result.get("released_amount")

            now = datetime.now(UTC).replace(tzinfo=None)
            # #1835 F2: terminal writes are CAS via _cas_settle_terminal —
            # RUNNING/COMPLETED + no-open-dispute in WHERE is the swap; a
            # concurrent cancel/dispute that committed during the RPC
            # window wins and its state is reported instead.
            lost = await self._cas_settle_terminal(
                job_id,
                allowed_states={"RUNNING", "COMPLETED"},
                job_values={
                    "state": "RELEASED",
                    "payment_status": "released",
                    "tx_hash": tx_hash,
                    "completed_at": now,
                    "updated_at": now,
                },
                payment=payment,
                payment_from_statuses="escrowed",
                payment_values=self._settle_payment_values(
                    status="released",
                    tx_hash=tx_hash,
                    amount=released_amount,
                    now=now,
                    amount_field="released_amount",
                    hash_field="transaction_hash",
                    ts_field="released_at",
                ),
            )
            if lost is not None:
                return lost

            await self.session.commit()
            await self.session.refresh(job)

            return self._job_to_dict(job)
        except Exception as e:
            await self.session.rollback()
            logger.error("Error in release_market_job_payment: %s: %s", type(e).__name__, e)
            raise

    async def refund_market_job_payment(
        self, job_id: str, reason: str = "", refund_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Refund the escrow for a failed or canceled market job."""
        try:
            refund_data = refund_data or {}
            job = await self.session.get(MarketJob, job_id)
            if not job:
                raise ValueError(f"Job not found: {job_id}")

            payment: MarketJobPayment | None = None
            if job.payment_id:
                payment = await self.session.get(MarketJobPayment, job.payment_id)

            replay = self._guard_refund_settlement(job, payment, job_id)
            if replay is not None:
                return replay

            tx_hash = refund_data.get("tx_hash")
            refunded_amount = refund_data.get("refunded_amount")
            if tx_hash:
                tx = await self._require_confirmed_settle_tx(tx_hash, job, "ESCROW_REFUND")
                # Same rule as release: the on-chain value is authoritative,
                # never the caller-supplied figure (#1584).
                refunded_amount = self._settled_amount_ait(tx)
            else:
                # Same canonical binding as release: the escrow path key is
                # the market job id, not escrow_contract_id (#1564).
                result = await self._rpc_client.refund_escrow(job.id)
                if not (result and result.get("success")):
                    raise ValueError(f"Escrow refund failed for job {job_id}: {result}")
                tx_hash = str(result.get("tx_hash", ""))
                refunded_amount = result.get("refunded_amount")

            now = datetime.now(UTC).replace(tzinfo=None)
            # #1835 F2: same CAS treatment as release — the refundable state
            # set mirrors _guard_refund_settlement, plus the no-open-dispute
            # predicate so a dispute landing mid-RPC also loses.
            job_values: dict[str, Any] = {
                "state": "REFUNDED",
                "payment_status": "refunded",
                "refund_tx_hash": tx_hash,
                "updated_at": now,
            }
            if reason:
                job_values["receipt"] = {"reason": reason}
            lost = await self._cas_settle_terminal(
                job_id,
                allowed_states=self._refundable_job_states(payment),
                job_values=job_values,
                payment=payment,
                payment_from_statuses=frozenset({"escrowed", "refund_pending"}),
                payment_values=self._settle_payment_values(
                    status="refunded",
                    tx_hash=tx_hash,
                    amount=refunded_amount,
                    now=now,
                    amount_field="refunded_amount",
                    hash_field="refund_transaction_hash",
                    ts_field="refunded_at",
                ),
            )
            if lost is not None:
                return lost

            await self.session.commit()
            await self.session.refresh(job)

            return self._job_to_dict(job)
        except Exception as e:
            await self.session.rollback()
            logger.error("Error in refund_market_job_payment: %s: %s", type(e).__name__, e)
            raise
