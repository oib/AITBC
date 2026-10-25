"""ESCROW-E2E-TEST-1 group 1: escrow create through the coordinator relay.

The real ``_escrow_create`` helper signs the lock, sees the customer node's
local RPC refuse ``/rpc/escrow/create`` (the nginx-allowlist 403), and falls
through to ``POST /v1/escrow/relay`` — crossing the real ``AuthMiddleware``
and relay service into the stub chain, which enforces the node-wallet `to`
rule the deployment broke on.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import click
import pytest

import aitbc_cli.commands.market.escrow as esc_mod

from conftest import (
    BUYER_ADDRESS,
    BUYER_PRIVATE_KEY,
    FOREIGN_ADDRESS,
    NODE_WALLET,
    PROVIDER_ADDRESS,
    auth_header,
    bind_wallet,
    cli_config,
    cli_ctx,
)
from stubchain import COORDINATOR_URL, SETTLEMENT_RPC_URL


def _create(wired, job_id: str, amount: str = "1.5", node_wallet: str | None = None, ctx=None):
    return esc_mod._escrow_create(
        ctx or cli_ctx(),
        job_id,
        BUYER_ADDRESS,
        PROVIDER_ADDRESS,
        Decimal(amount),
        cli_config(),
        private_key=BUYER_PRIVATE_KEY,
        node_wallet=node_wallet,
    )


@pytest.fixture
def bound_buyer(wired):
    bind_wallet(wired.session, "client-1", BUYER_ADDRESS)
    return wired


class TestCreateViaRelay:
    def test_create_locks_against_the_node_wallet(self, bound_buyer):
        """Happy path: local RPC 403 → relay → chain; lock `to` is the node wallet."""
        wired = bound_buyer
        contract_id = _create(wired, "e2e_create_1")
        assert contract_id == "esc-e2e_create_1"

        # The chain got exactly one create — via the relay's forward to the
        # settlement node — and the signed lock pays the node wallet.
        creates = wired.chain.calls_to("/rpc/escrow/create", base=SETTLEMENT_RPC_URL)
        assert len(creates) == 1
        lock_tx = creates[0][3]["lock_tx"]
        assert lock_tx["to"].lower() == NODE_WALLET.lower()
        assert lock_tx["to"].lower() != "0x02b8cc0d4f4d84e5d0a4a4c9a9d04a9c7dd3ef01"  # not the proposer id
        assert lock_tx["amount"] == 54_000_000  # 1.5 AIT in integer compute units
        assert wired.chain.escrows["e2e_create_1"]["state"] == "locked"

    def test_wrong_to_refused_by_the_chain_rule(self, bound_buyer):
        """A lock paying anything but the node wallet dies on the chain's own rule."""
        wired = bound_buyer
        with pytest.raises(click.Abort):
            _create(wired, "e2e_wrong_to", node_wallet="0x02B8cC0D4f4d84e5D0a4a4c9a9D04A9C7Dd3Ef01")  # proposer id
        assert "e2e_wrong_to" not in wired.chain.escrows

        # The refusal was the real chain rule, surfaced verbatim by the relay.
        creates = wired.chain.calls_to("/rpc/escrow/create", base=SETTLEMENT_RPC_URL)
        assert len(creates) == 1  # the relay forwarded it; the chain refused it

    def test_relay_passthrough_names_the_node_wallet_rule(self, bound_buyer):
        """Direct relay post: the chain detail reaches the caller unchanged."""
        wired = bound_buyer
        payload = {
            "job_id": "e2e_wrong_to2",
            "buyer": BUYER_ADDRESS,
            "provider": PROVIDER_ADDRESS,
            "amount": "1.5",
            "lock_tx": {
                "type": "ESCROW_LOCK",
                "from": BUYER_ADDRESS,
                "to": "0x02B8cC0D4f4d84e5D0a4a4c9a9D04A9C7Dd3Ef01",
                "amount": 54_000_000,
                "nonce": 0,
                "signature": "0xdeadbeef",
                "payload": {"job_id": "e2e_wrong_to2"},
            },
        }
        resp = wired.client.post("/v1/escrow/relay", json=payload, headers=auth_header("client-1"))
        assert resp.status_code == 400
        assert "node wallet" in resp.json()["detail"]

    def test_replay_returns_the_stored_contract(self, bound_buyer):
        """A second identical create is a relay dedup — the chain sees it once."""
        wired = bound_buyer
        first = _create(wired, "e2e_replay")
        second = _create(wired, "e2e_replay")
        assert first == second == "esc-e2e_replay"
        creates = wired.chain.calls_to("/rpc/escrow/create", base=SETTLEMENT_RPC_URL)
        assert len(creates) == 1

    def test_replay_relay_level_reports_duplicate(self, bound_buyer):
        wired = bound_buyer
        payload = {
            "job_id": "e2e_replay2",
            "buyer": BUYER_ADDRESS,
            "provider": PROVIDER_ADDRESS,
            "amount": "1.5",
            "lock_tx": {
                "type": "ESCROW_LOCK",
                "from": BUYER_ADDRESS,
                "to": NODE_WALLET,
                "amount": 54_000_000,
                "nonce": 0,
                "signature": "0xdeadbeef",
                "payload": {"job_id": "e2e_replay2"},
            },
        }
        r1 = wired.client.post("/v1/escrow/relay", json=payload, headers=auth_header("client-1"))
        r2 = wired.client.post("/v1/escrow/relay", json=payload, headers=auth_header("client-1"))
        assert r1.status_code == r2.status_code == 200
        assert r2.json()["contract_id"] == "esc-e2e_replay2"
        assert r2.json()["duplicate"] is True
        assert len(wired.chain.calls_to("/rpc/escrow/create", base=SETTLEMENT_RPC_URL)) == 1

    def test_foreign_buyer_is_forbidden(self, wired):
        """A credential bound to a different wallet cannot relay this buyer's lock."""
        bind_wallet(wired.session, "client-1", BUYER_ADDRESS)
        bind_wallet(wired.session, "client-2", FOREIGN_ADDRESS)
        payload = {
            "job_id": "e2e_foreign",
            "buyer": BUYER_ADDRESS,
            "provider": PROVIDER_ADDRESS,
            "amount": "1.5",
            "lock_tx": {
                "type": "ESCROW_LOCK",
                "from": BUYER_ADDRESS,
                "to": NODE_WALLET,
                "amount": 54_000_000,
                "nonce": 0,
                "signature": "0xdeadbeef",
                "payload": {"job_id": "e2e_foreign"},
            },
        }
        resp = wired.client.post("/v1/escrow/relay", json=payload, headers=auth_header("client-2"))
        assert resp.status_code == 403
        assert "buyer" in resp.json()["detail"]
        assert wired.chain.calls_to("/rpc/escrow/create", base=SETTLEMENT_RPC_URL) == []

    def test_amount_over_the_relay_cap_is_refused(self, bound_buyer):
        """The non-admin cap is 360,000,000 units (10 AIT); 10.1 AIT is refused."""
        wired = bound_buyer
        payload = {
            "job_id": "e2e_over_cap",
            "buyer": BUYER_ADDRESS,
            "provider": PROVIDER_ADDRESS,
            "amount": "10.1",  # 363,600,000 units
            "lock_tx": {
                "type": "ESCROW_LOCK",
                "from": BUYER_ADDRESS,
                "to": NODE_WALLET,
                "amount": 363_600_000,
                "nonce": 0,
                "signature": "0xdeadbeef",
                "payload": {"job_id": "e2e_over_cap"},
            },
        }
        resp = wired.client.post("/v1/escrow/relay", json=payload, headers=auth_header("client-1"))
        assert resp.status_code == 400
        assert "cap" in resp.json()["detail"]
        assert wired.chain.calls_to("/rpc/escrow/create", base=SETTLEMENT_RPC_URL) == []

    def test_amount_at_the_cap_is_relayed(self, bound_buyer):
        """Exactly 10 AIT (360,000,000 units) is inside the cap."""
        wired = bound_buyer
        payload = {
            "job_id": "e2e_at_cap",
            "buyer": BUYER_ADDRESS,
            "provider": PROVIDER_ADDRESS,
            "amount": "10",
            "lock_tx": {
                "type": "ESCROW_LOCK",
                "from": BUYER_ADDRESS,
                "to": NODE_WALLET,
                "amount": 360_000_000,
                "nonce": 0,
                "signature": "0xdeadbeef",
                "payload": {"job_id": "e2e_at_cap"},
            },
        }
        resp = wired.client.post("/v1/escrow/relay", json=payload, headers=auth_header("client-1"))
        assert resp.status_code == 200
        assert resp.json()["contract_id"] == "esc-e2e_at_cap"
        assert wired.chain.escrows["e2e_at_cap"]["locked_units"] == 360_000_000

    def test_no_token_means_no_relay_no_create(self, wired, monkeypatch):
        """Without a client credential the relay is skipped entirely — no escrow."""
        ctx = cli_ctx()
        ctx.obj["api_key"] = None
        monkeypatch.setattr(
            esc_mod,
            "AuthManager",
            lambda: SimpleNamespace(get_credential=lambda name: None),
        )
        bind_wallet(wired.session, "client-1", BUYER_ADDRESS)
        with pytest.raises(click.Abort):
            _create(wired, "e2e_no_token", ctx=ctx)
        # Relay never saw a request; the settlement retry got the local 403's
        # non-settlement detail so no create reached the chain either.
        assert wired.chain.calls_to("/v1/escrow/relay", base=COORDINATOR_URL) == []
        assert wired.chain.calls_to("/rpc/escrow/create", base=SETTLEMENT_RPC_URL) == []
