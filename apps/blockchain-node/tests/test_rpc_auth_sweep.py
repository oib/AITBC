"""Auth sweep — every mutating route under the public /rpc proxy must reject
uncredentialed callers.

GAP-56: nginx ``location /rpc/`` is a blanket proxy, so any router mounted
there is internet-facing. The audit found unauthenticated mutations ranging
from lease revocation to a full governance takeover chain (public proposal →
vote with caller-chosen voting_power → execute signed by the node's genesis
key). These tests pin the X-API-Key gate on each route and the stake-derived
voting power, so the surface cannot silently reopen.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import aitbc_chain.rpc.escrow_routes as escrow_routes

KEY = "test-key-123"


def _app(*routers) -> TestClient:
    app = FastAPI()
    for r in routers:
        app.include_router(r, prefix="/rpc")
    # Handlers without a test DB may crash; we only care that the status isn't
    # 403, so convert handler exceptions to 500s instead of raising.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setattr(escrow_routes, "_RPC_API_KEY", KEY)


class TestGovernanceIdentityAuth:
    """The public proposal→vote→execute chain was a remote chain-parameter
    write signed by the node's own genesis key — a takeover. All five
    mutating routes now require X-API-Key."""

    @pytest.fixture
    def client(self):
        from aitbc_chain.rpc.routers.staking import router

        return _app(router)

    @pytest.mark.parametrize(
        "path",
        [
            "/rpc/identity/register",
            "/rpc/identity/verify",
            "/rpc/governance/proposal",
            "/rpc/governance/vote",
            "/rpc/governance/proposal/p1/execute",
        ],
    )
    def test_reject_missing_key(self, client, path):
        assert client.post(path, json={}).status_code == 403, path

    @pytest.mark.parametrize(
        "path",
        [
            "/rpc/identity/register",
            "/rpc/governance/proposal",
            "/rpc/governance/vote",
            "/rpc/governance/proposal/p1/execute",
        ],
    )
    def test_reject_wrong_key(self, client, path):
        assert client.post(path, json={}, headers={"X-API-Key": "nope"}).status_code == 403, path

    def test_valid_key_reaches_handler(self, client):
        resp = client.post("/rpc/governance/vote", json={}, headers={"X-API-Key": KEY})
        assert resp.status_code != 403

    def test_reads_stay_public(self, client):
        assert client.get("/rpc/governance/proposal/p1").status_code != 403
        assert client.get("/rpc/identity/agent-1").status_code != 403


class TestControlPlaneAuth:
    """Chain lifecycle and block import are operator operations."""

    @pytest.fixture
    def client(self):
        from aitbc_chain.rpc.routers.core import router

        return _app(router)

    def test_chains_start_stop_reject_missing_key(self, client):
        body = {"chain_id": "micro-1", "chain_type": "micro"}
        assert client.post("/rpc/chains/start", json=body).status_code == 403
        assert client.post("/rpc/chains/stop", json=body).status_code == 403

    def test_import_block_rejects_missing_key(self, client):
        assert client.post("/rpc/importBlock", json={}).status_code == 403

    def test_wrong_key_rejected(self, client):
        body = {"chain_id": "micro-1", "chain_type": "micro"}
        assert client.post("/rpc/chains/stop", json=body, headers={"X-API-Key": "nope"}).status_code == 403

    def test_valid_key_reaches_handler(self, client):
        body = {"chain_id": "micro-1", "chain_type": "micro"}
        resp = client.post("/rpc/chains/start", json=body, headers={"X-API-Key": KEY})
        assert resp.status_code != 403

    def test_register_account_stays_public(self, client):
        """register-account is a read-only report (documented no-write)."""
        assert client.post("/rpc/register-account", json={}).status_code != 403


class TestSubscriptionAuth:
    """Lease register/heartbeat/revoke are node-internal. Fleet nodes each
    hold their own BLOCKCHAIN_RPC_API_KEY, so the hub accepts its own key OR
    the peer set in BLOCKCHAIN_RPC_API_KEY_PEERS — scoped to these routes
    only, never the control plane."""

    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setattr(escrow_routes, "_RPC_API_PEER_KEYS", frozenset({"peer-key-a", "peer-key-b"}))
        from aitbc_chain.rpc.routers.subscription import router

        return _app(router)

    def test_reject_missing_key(self, client):
        assert client.post("/rpc/subscribe", json={}).status_code == 403
        assert client.post("/rpc/heartbeat", json={}).status_code == 403
        assert client.delete("/rpc/lease/node-1").status_code == 403

    def test_valid_key_reaches_handler(self, client):
        resp = client.post(
            "/rpc/subscribe",
            json={"node_id": "n1", "transport": "redis", "chain_id": "ait-testnet"},
            headers={"X-API-Key": KEY},
        )
        assert resp.status_code != 403

    def test_peer_key_reaches_handler(self, client):
        resp = client.post(
            "/rpc/heartbeat",
            json={"node_id": "n1", "chain_id": "ait-testnet"},
            headers={"X-API-Key": "peer-key-a"},
        )
        assert resp.status_code != 403

    def test_peer_key_does_not_open_control_plane(self):
        """A leaked peer key must not unlock governance or chain control."""
        from aitbc_chain.rpc.routers.staking import router as staking_router
        from aitbc_chain.rpc.routers.core import router as core_router

        c = _app(staking_router, core_router)
        h = {"X-API-Key": "peer-key-a"}
        assert c.post("/rpc/governance/vote", json={}, headers=h).status_code == 403
        assert c.post("/rpc/chains/stop", json={"chain_id": "x"}, headers=h).status_code == 403

    def test_lease_reads_stay_public(self, client):
        assert client.get("/rpc/lease/node-1").status_code != 403
        assert client.get("/rpc/subscribers").status_code != 403


class TestIslandsAuth:
    """islands/join returned node credentials publicly."""

    @pytest.fixture
    def client(self):
        from aitbc_chain.rpc.routers.islands import router

        return _app(router)

    def test_reject_missing_key(self, client):
        join = {"island_id": "i1", "island_name": "i1", "chain_id": "ait-testnet"}
        assert client.post("/rpc/islands/join", json=join).status_code == 403
        assert client.post("/rpc/islands/leave", json={"island_id": "i1"}).status_code == 403
        assert client.post("/rpc/islands/bridge", json={"target_island_id": "i2"}).status_code == 403

    def test_valid_key_reaches_handler(self, client):
        join = {"island_id": "i1", "island_name": "i1", "chain_id": "ait-testnet"}
        resp = client.post("/rpc/islands/join", json=join, headers={"X-API-Key": KEY})
        assert resp.status_code != 403

    def test_reads_stay_public(self, client):
        assert client.get("/rpc/islands").status_code != 403


class TestContractsAuth:
    """Contracts deploy + forum mutations trusted caller-supplied identities;
    moderate_message had an unenforced 'moderator only' docstring."""

    @pytest.fixture
    def client(self):
        from aitbc_chain.rpc.routers.contracts import router

        return _app(router)

    @pytest.mark.parametrize(
        "path",
        [
            "/rpc/contracts/deploy",
            "/rpc/contracts/deploy/messaging",
            "/rpc/contracts/messaging/topics/create",
            "/rpc/contracts/messaging/messages/post",
            "/rpc/contracts/messaging/messages/m1/vote",
            "/rpc/contracts/messaging/messages/m1/moderate",
        ],
    )
    def test_reject_missing_key(self, client, path):
        assert client.post(path, json={}).status_code == 403, path

    def test_valid_key_reaches_handler(self, client):
        resp = client.post("/rpc/contracts/messaging/messages/post", json={}, headers={"X-API-Key": KEY})
        assert resp.status_code != 403

    def test_reads_stay_public(self, client):
        """call/verify are pure reads (select-only); keep them open."""
        assert client.post("/rpc/contracts/call", json={}).status_code != 403
        assert client.get("/rpc/contracts/messaging/topics").status_code != 403


class TestGpuResourcesAuth:
    """GPU/edge registration wrote resource claims with no auth."""

    @pytest.fixture
    def client(self):
        from aitbc_chain.rpc.gpu_resources import router

        return _app(router)

    def test_reject_missing_key(self, client):
        assert client.post("/rpc/gpu/register", json={}).status_code == 403
        assert client.post("/rpc/gpu/allocate", json={}).status_code == 403
        assert client.post("/rpc/edge/register", json={}).status_code == 403


class TestVotingPowerFromStake:
    """cast_governance_vote must derive voting_power from the voter's active
    stake — the request field was caller-chosen, so one vote with
    voting_power=N could push any proposal over quorum (which defaults to 0)."""

    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        from aitbc_chain.metadata import chain_metadata
        from aitbc_chain.models import Account, Stake
        from aitbc_chain.base_models import GovernanceProposal
        from aitbc_chain.rpc import staking as staking_module
        from sqlmodel import Session, create_engine

        engine = create_engine(f"sqlite:///{tmp_path / 'gov.db'}")
        chain_metadata.create_all(engine)

        @contextmanager
        def _scope():
            with Session(engine) as s:
                yield s

        monkeypatch.setattr(staking_module, "session_scope", _scope)
        monkeypatch.setattr(staking_module, "get_chain_id", lambda cid: cid or "ait-testnet")

        now = datetime.now(UTC)
        with Session(engine) as s:
            s.add(
                GovernanceProposal(
                    chain_id="ait-testnet",
                    proposal_id="p1",
                    proposer_address="0x" + "a" * 40,
                    title="t",
                    description="d",
                    status="active",
                    quorum_required=100,
                    voting_starts=now,
                    voting_ends=now + timedelta(days=7),
                )
            )
            s.add(
                Account(
                    chain_id="ait-testnet",
                    address="0x" + "b" * 40,
                    balance=10_000,
                    nonce=0,
                )
            )
            s.add(
                Stake(
                    chain_id="ait-testnet",
                    address="0x" + "b" * 40,
                    amount=250,
                    locked_until=now + timedelta(days=30),
                    status="active",
                )
            )
            s.commit()
        return staking_module

    @pytest.mark.anyio
    async def test_voting_power_comes_from_stake(self, env):
        """Caller claims voting_power=999999; only 250 (the active stake) counts."""
        resp = await env.cast_governance_vote(
            None,
            {
                "proposal_id": "p1",
                "voter_address": "0x" + "b" * 40,
                "vote_type": "for",
                "voting_power": 999999,
                "chain_id": "ait-testnet",
            },
        )
        assert resp["voting_power"] == 250

    @pytest.mark.anyio
    async def test_no_stake_means_no_power(self, env):
        resp = await env.cast_governance_vote(
            None,
            {
                "proposal_id": "p1",
                "voter_address": "0x" + "c" * 40,
                "vote_type": "for",
                "voting_power": 999999,
                "chain_id": "ait-testnet",
            },
        )
        assert resp["voting_power"] == 0


class TestBountyAuthBinding:
    """Bounty protocol transfers now carry auth evidence; the consensus
    binding must bind bounty_id / submission_id / party per type."""

    def _bind(self, tx_type, message, tx_data):
        from aitbc_chain.state.state_transition import _payload_auth_binds_transfer

        return _payload_auth_binds_transfer(tx_type, message, tx_data)

    def test_lock_binds_creator_amount_bounty(self):
        msg = {"bounty_id": "b1", "user_address": "0x" + "a" * 40, "reward_amount": 500}
        tx = {"from": "0x" + "a" * 40, "value": 500, "payload": {"bounty_id": "b1"}}
        assert self._bind("BOUNTY_LOCK", msg, tx)

    def test_lock_rejects_wrong_creator(self):
        msg = {"bounty_id": "b1", "user_address": "0x" + "a" * 40, "reward_amount": 500}
        tx = {"from": "0x" + "b" * 40, "value": 500, "payload": {"bounty_id": "b1"}}
        assert not self._bind("BOUNTY_LOCK", msg, tx)

    def test_lock_rejects_amount_mismatch(self):
        msg = {"bounty_id": "b1", "user_address": "0x" + "a" * 40, "reward_amount": 500}
        tx = {"from": "0x" + "a" * 40, "value": 9000, "payload": {"bounty_id": "b1"}}
        assert not self._bind("BOUNTY_LOCK", msg, tx)

    def test_lock_rejects_bounty_mismatch(self):
        msg = {"bounty_id": "b1", "user_address": "0x" + "a" * 40, "reward_amount": 500}
        tx = {"from": "0x" + "a" * 40, "value": 500, "payload": {"bounty_id": "b2"}}
        assert not self._bind("BOUNTY_LOCK", msg, tx)

    def test_payout_binds_submission(self):
        msg = {"submission_id": "s1", "verified": True}
        tx = {"to": "0x" + "a" * 40, "payload": {"bounty_id": "b1", "submission_id": "s1"}}
        assert self._bind("BOUNTY_PAYOUT", msg, tx)

    def test_payout_rejects_submission_mismatch(self):
        msg = {"submission_id": "s1", "verified": True}
        tx = {"to": "0x" + "a" * 40, "payload": {"bounty_id": "b1", "submission_id": "s2"}}
        assert not self._bind("BOUNTY_PAYOUT", msg, tx)

    def test_refund_binds_payee(self):
        msg = {"user_address": "0x" + "a" * 40}
        tx = {"to": "0x" + "a" * 40, "payload": {"bounty_id": "b1"}}
        assert self._bind("BOUNTY_REFUND", msg, tx)

    def test_refund_rejects_wrong_payee(self):
        msg = {"user_address": "0x" + "a" * 40}
        tx = {"to": "0x" + "b" * 40, "payload": {"bounty_id": "b1"}}
        assert not self._bind("BOUNTY_REFUND", msg, tx)

    def test_unknown_type_still_rejected(self):
        assert not self._bind("TRANSFER", {"user_address": "0x" + "a" * 40}, {})


class TestGovernanceExecutorGate:
    """The consensus gate at validate_transaction: once the
    ``governance_executors`` chain parameter is set, only listed senders may
    land a GOVERNANCE_EXECUTE. While unset (live chain today) the gate is
    open — the param write in the deploy closes it fleet-wide."""

    @pytest.fixture
    def session(self, tmp_path):
        from aitbc_chain.metadata import chain_metadata
        from aitbc_chain.models import Account
        from aitbc_chain.base_models import ChainParameter
        from sqlmodel import Session, create_engine

        engine = create_engine(f"sqlite:///{tmp_path / 'exec.db'}")
        chain_metadata.create_all(engine)
        s = Session(engine)
        s.add(Account(chain_id="ait-testnet", address="0x" + "a" * 40, balance=1000, nonce=0))
        s.add(Account(chain_id="ait-testnet", address="0x" + "e" * 40, balance=1000, nonce=0))
        s.add(
            ChainParameter(
                chain_id="ait-testnet",
                parameter="governance_executors",
                value="0x" + "e" * 40,
            )
        )
        s.commit()
        yield s
        s.close()

    def _tx(self, sender: str) -> dict:
        return {
            "type": "GOVERNANCE_EXECUTE",
            "from": sender,
            "to": sender,
            "value": 0,
            "fee": 0,
            "nonce": 0,
            "chain_id": "ait-testnet",
            "payload": {"proposal_id": "p1", "parameter_change": {"parameter": "x", "value": "1"}},
        }

    def test_non_executor_rejected(self, session):
        from aitbc_chain.state.state_transition import StateTransition

        ok, msg = StateTransition().validate_transaction(session, "ait-testnet", self._tx("0x" + "a" * 40), "0xdead01")
        assert not ok
        assert "not an authorized executor" in msg

    def test_executor_passes_gate(self, session):
        from aitbc_chain.state.state_transition import StateTransition

        ok, msg = StateTransition().validate_transaction(session, "ait-testnet", self._tx("0x" + "e" * 40), "0xdead02")
        assert ok, msg
