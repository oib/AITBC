"""Reward payout recipient pin — #1401 (POOLHUB-PAY-1).

``distribute_rewards`` submits the on-chain reward with
``miner_address=contrib.miner_id`` — the pool-hub miner identifier, not the
wallet address registered on ``Miner.wallet_address``. The signed tx's ``to``
field therefore carries a non-address string; the path is dormant today
(feature-flagged, no production callers) but pays the wrong/invalid recipient
the moment it is enabled.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from poolhub.clients.blockchain import PoolHubBlockchainClient

# Same deterministic secp256k1 pair as test_reward_payout_idempotency.py.
SIGNER_ADDRESS = "0x1a642f0E3c3aF545E7AcBD38b07251B3990914F1"
SIGNER_KEY = "0101010101010101010101010101010101010101010101010101010101010101"


@pytest.fixture
def client():
    return PoolHubBlockchainClient(signer_address=SIGNER_ADDRESS, signer_private_key=SIGNER_KEY)


class TestRewardRecipient:
    @pytest.mark.xfail(
        strict=True,
        reason="reward tx 'to' is contrib.miner_id (e.g. 'miner-1'), not Miner.wallet_address — dormant payout path pays invalid/wrong recipient; fix tracked in #1401",
    )
    async def test_payout_goes_to_wallet_address_not_miner_id(self, client, payout_session):
        client.record_contribution("miner-1", score=90.0, shares=5000)
        session = payout_session

        with (
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(
                client._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx-1"}
            ) as submit,
        ):
            payouts = await client.distribute_rewards(block_height=100, session=session)

        assert payouts[0]["status"] == "paid"
        tx = submit.await_args.args[0]
        assert tx["to"].startswith("0x"), f"reward recipient must be a wallet address, got miner_id {tx['to']!r}; see #1401"
