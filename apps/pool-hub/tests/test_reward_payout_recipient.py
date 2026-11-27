"""Reward payout recipient pin — #1401 (POOLHUB-PAY-1).

``distribute_rewards`` must submit the on-chain reward to the miner's
registered ``wallet_address`` — the pool-hub miner identifier is not a
wallet and pays an invalid recipient the moment the pipeline is enabled.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from poolhub.clients.blockchain import PoolHubBlockchainClient
from poolhub.services.reward_shares import record_verified_share

# Same deterministic secp256k1 pair as test_reward_payout_idempotency.py.
SIGNER_ADDRESS = "0x1a642f0E3c3aF545E7AcBD38b07251B3990914F1"
SIGNER_KEY = "0101010101010101010101010101010101010101010101010101010101010101"

PAYOUT_HEIGHT = 1500


@pytest.fixture
def client():
    return PoolHubBlockchainClient(signer_address=SIGNER_ADDRESS, signer_private_key=SIGNER_KEY)


@pytest.fixture(autouse=True)
def _empty_mempool():
    with patch(
        "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
        new_callable=AsyncMock,
        return_value={"success": True, "transactions": [], "count": 0},
    ):
        yield


class TestRewardRecipient:
    async def test_payout_goes_to_wallet_address_not_miner_id(self, client, payout_session):
        session = payout_session
        await record_verified_share(
            session,
            miner_id="miner-1",
            chain_id="ait-hub",
            epoch_number=0,
            shares=5000,
            evidence_tx_hash="0x" + "cd" * 32,
        )

        with (
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(
                client._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx-1"}
            ) as submit,
        ):
            payouts = await client.distribute_rewards(block_height=PAYOUT_HEIGHT, session=session)

        assert payouts[0]["status"] == "paid"
        tx = submit.await_args.args[0]
        assert tx["to"].startswith("0x"), f"reward recipient must be a wallet address, got miner_id {tx['to']!r}; see #1401"
