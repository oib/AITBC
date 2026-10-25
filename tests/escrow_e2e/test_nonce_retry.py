"""ESCROW-E2E-TEST-1 group 4: the record-leg nonce retry.

``_record_job_on_chain`` reads the account's *sealed* nonce, but the escrow
lock can still sit pending in the mempool on that slot — the real race that
shipped. The only safe retry is one re-signed post at N+1, and only when the
node's refusal is the occupied-slot 400. Any other 400 is a payload problem
a bumped nonce cannot fix.
"""

from __future__ import annotations

from decimal import Decimal

import aitbc_cli.commands.market.escrow as esc_mod
import aitbc_cli.commands.market.jobs as jobs_mod

from conftest import (
    BUYER_ADDRESS,
    BUYER_PRIVATE_KEY,
    PROVIDER_ADDRESS,
    bind_wallet,
    cli_config,
    cli_ctx,
)
from stubchain import SETTLEMENT_RPC_URL


def _create(wired, job_id: str) -> str:
    """Create via the relay — the signed lock occupies nonce 0 in the mempool."""
    bind_wallet(wired.session, "client-1", BUYER_ADDRESS)
    return esc_mod._escrow_create(
        cli_ctx(),
        job_id,
        BUYER_ADDRESS,
        PROVIDER_ADDRESS,
        Decimal("1.5"),
        cli_config(),
        private_key=BUYER_PRIVATE_KEY,
    )


def _job_data(nonce: int = 0) -> dict:
    return {
        "from": BUYER_ADDRESS,
        "to": "0x0000000000000000000000000000000000000000",
        "amount": 0,
        "fee": 360_000,
        "nonce": nonce,
        "type": "GPU_MARKET",
        "chain_id": "ait-testchain",
        "payload": {"action": "software_job", "job_id": "j", "status": "completed"},
    }


def _market_tx_posts(wired):
    return wired.chain.calls_to("/rpc/transactions/market", base=SETTLEMENT_RPC_URL)


class TestRecordLegNonceRetry:
    def test_pending_lock_slot_retries_once_at_n_plus_1(self, wired):
        """Lock pending at nonce 0 → record leg collides → one retry at 1."""
        _create(wired, "e2e_nonce_1")
        assert (BUYER_ADDRESS.lower(), 0) in wired.chain.occupied_slots

        tx_hash = jobs_mod._record_job_on_chain(cli_config(), _job_data(nonce=0), BUYER_PRIVATE_KEY)
        assert tx_hash is not None
        posts = _market_tx_posts(wired)
        assert [p[3]["nonce"] for p in posts] == [0, 1]
        # Re-signed, not re-sent: the signature covers the nonce.
        assert posts[0][3]["signature"] != posts[1][3]["signature"]

    def test_occupied_retry_slot_is_not_retried_again(self, wired):
        """If N+1 is also occupied, the leg stops — exactly two posts."""
        _create(wired, "e2e_nonce_2")
        wired.chain.occupy_slot(BUYER_ADDRESS, 1)

        tx_hash = jobs_mod._record_job_on_chain(cli_config(), _job_data(nonce=0), BUYER_PRIVATE_KEY)
        assert tx_hash is None
        posts = _market_tx_posts(wired)
        assert [p[3]["nonce"] for p in posts] == [0, 1]

    def test_other_400_is_never_retried(self, wired):
        """A non-occupied-slot 400 must not bump the nonce — one post only."""
        wired.chain.next_market_tx_error = (400, "payload malformed: unknown action")
        tx_hash = jobs_mod._record_job_on_chain(cli_config(), _job_data(nonce=7), BUYER_PRIVATE_KEY)
        assert tx_hash is None
        posts = _market_tx_posts(wired)
        assert len(posts) == 1
        assert posts[0][3]["nonce"] == 7

    def test_non_400_refusal_is_never_retried(self, wired):
        """A 403 refusal is not the occupied-slot signal either."""
        wired.chain.next_market_tx_error = (403, "Forbidden")
        tx_hash = jobs_mod._record_job_on_chain(cli_config(), _job_data(nonce=3), BUYER_PRIVATE_KEY)
        assert tx_hash is None
        assert len(_market_tx_posts(wired)) == 1

    def test_free_slot_posts_once(self, wired):
        """No collision: the record seals on the first try."""
        tx_hash = jobs_mod._record_job_on_chain(cli_config(), _job_data(nonce=9), BUYER_PRIVATE_KEY)
        assert tx_hash is not None
        assert len(_market_tx_posts(wired)) == 1
        assert (BUYER_ADDRESS.lower(), 9) in wired.chain.occupied_slots
