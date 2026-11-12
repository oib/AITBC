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


class TestEscrowSettlementAuth:
    """#1917: escrow release/refund move money, so they require the dedicated
    settlement credential (X-Settlement-Key, BLOCKCHAIN_RPC_SETTLEMENT_API_KEY)
    ON TOP OF the router-wide X-API-Key. Possession of the shared RPC key —
    which every service and issued join key's parent holds — must no longer
    be sufficient to settle an escrow. Other escrow routes (create, reads)
    keep the base-key gate only."""

    SETTLE_KEY = "settle-key-9"

    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setattr(escrow_routes, "_RPC_SETTLEMENT_API_KEY", self.SETTLE_KEY)
        return _app(escrow_routes.router)

    def _post(self, client, path, *, api_key=KEY, settle_key="__unset__"):
        headers = {"X-API-Key": api_key} if api_key is not None else {}
        if settle_key != "__unset__":
            headers["X-Settlement-Key"] = settle_key
        return client.post(path, json={}, headers=headers)

    @pytest.mark.parametrize("path", ["/rpc/escrow/job-1/release", "/rpc/escrow/job-1/refund"])
    def test_rejects_missing_settlement_key(self, client, path):
        """Valid base RPC key alone is no longer sufficient to settle."""
        assert self._post(client, path).status_code == 403, path

    @pytest.mark.parametrize("path", ["/rpc/escrow/job-1/release", "/rpc/escrow/job-1/refund"])
    def test_rejects_wrong_settlement_key(self, client, path):
        assert self._post(client, path, settle_key="nope").status_code == 403, path

    @pytest.mark.parametrize("path", ["/rpc/escrow/job-1/release", "/rpc/escrow/job-1/refund"])
    def test_rejects_missing_base_key_even_with_settlement_key(self, client, path):
        """The settlement credential does not replace X-API-Key."""
        assert self._post(client, path, api_key=None, settle_key=self.SETTLE_KEY).status_code == 403, path

    @pytest.mark.parametrize("path", ["/rpc/escrow/job-1/release", "/rpc/escrow/job-1/refund"])
    def test_valid_both_keys_reaches_handler(self, client, path):
        """Both credentials pass auth; the handler then runs (and fails on
        test scaffolding — no escrow manager / signing key — never 403)."""
        resp = self._post(client, path, settle_key=self.SETTLE_KEY)
        assert resp.status_code != 403, path

    @pytest.mark.parametrize("path", ["/rpc/escrow/job-1/release", "/rpc/escrow/job-1/refund"])
    def test_unset_settlement_key_fails_closed_503(self, client, monkeypatch, path):
        """An unconfigured node refuses settlement outright — never open."""
        monkeypatch.setattr(escrow_routes, "_RPC_SETTLEMENT_API_KEY", "")
        resp = self._post(client, path, settle_key=self.SETTLE_KEY)
        assert resp.status_code == 503, path

    def test_non_settlement_routes_keep_base_key_only(self, client):
        """Create/read stay on the shared key — the settlement credential is
        scoped to release/refund and must not be required elsewhere."""
        create = client.post("/rpc/escrow/create", json={}, headers={"X-API-Key": KEY})
        assert create.status_code != 403
        read = client.get("/rpc/escrow/job-1", headers={"X-API-Key": KEY})
        assert read.status_code != 403


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

    @pytest.mark.slow
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


class TestExportChainAuth:
    """export-chain is a bulk/state-disclosure route: fleet keys only — the
    node's own BLOCKCHAIN_RPC_API_KEY or a BLOCKCHAIN_RPC_API_KEY_PEERS
    member. Issued /rpc/join keys are self-serve and must not unlock a full
    chain export (#1871)."""

    @pytest.fixture
    def client(self, monkeypatch, tmp_path):
        monkeypatch.setattr(escrow_routes, "_RPC_API_PEER_KEYS", frozenset({"peer-key-a"}))
        monkeypatch.setenv("PEER_KEYS_DB", str(tmp_path / "peer_keys.db"))
        from aitbc_chain.rpc.routers.core import router

        return _app(router)

    def test_reject_missing_key(self, client):
        assert client.get("/rpc/export-chain").status_code == 403

    def test_reject_wrong_key(self, client):
        assert client.get("/rpc/export-chain", headers={"X-API-Key": "nope"}).status_code == 403

    def test_issued_join_key_rejected(self, client):
        """A live issued join key — valid for subscribe/heartbeat/lease —
        must still get 403 here."""
        from aitbc_chain.rpc import peer_keys

        issued = peer_keys.issue("joiner.example.net", "10.9.9.9")
        assert client.get("/rpc/export-chain", headers={"X-API-Key": issued}).status_code == 403

    def test_peer_key_reaches_handler(self, client):
        resp = client.get("/rpc/export-chain", headers={"X-API-Key": "peer-key-a"})
        assert resp.status_code != 403

    def test_admin_key_reaches_handler(self, client):
        resp = client.get("/rpc/export-chain", headers={"X-API-Key": KEY})
        assert resp.status_code != 403


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
    @pytest.mark.asyncio
    async def test_voting_power_comes_from_stake(self, env):
        """Caller claims voting_power=999999; only 250 (the active stake) counts."""
        resp = env.cast_governance_vote(
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
    @pytest.mark.asyncio
    async def test_no_stake_means_no_power(self, env):
        resp = env.cast_governance_vote(
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

    @pytest.mark.anyio
    @pytest.mark.asyncio
    async def test_checksummed_stake_row_matches_lowercase_voter(self, env):
        """Stake rows are written EIP-55-checksummed by the state transition;
        the request address is lowercased. The lookup must still match."""
        now = datetime.now(UTC)
        with env.session_scope() as s:
            s.add(
                env.Stake(
                    chain_id="ait-testnet",
                    address="0x" + "Dd" * 20,
                    amount=777,
                    locked_until=now + timedelta(days=30),
                    status="active",
                )
            )
            s.commit()
        resp = env.cast_governance_vote(
            None,
            {
                "proposal_id": "p1",
                "voter_address": "0x" + "dd" * 20,
                "vote_type": "for",
                "chain_id": "ait-testnet",
            },
        )
        assert resp["voting_power"] == 777

    @pytest.mark.anyio
    @pytest.mark.asyncio
    async def test_zero_power_vote_on_zero_quorum_proposal_does_not_500(self, env):
        """quorum_required defaults to 0; a 0-power vote made total_votes=0 ≥ 0,
        then divided by zero. The proposal must stay 'active', not crash."""
        now = datetime.now(UTC)
        with env.session_scope() as s:
            s.add(
                env.GovernanceProposal(
                    chain_id="ait-testnet",
                    proposal_id="p-zeroq",
                    proposer_address="0x" + "a" * 40,
                    title="t",
                    description="d",
                    status="active",
                    quorum_required=0,
                    voting_starts=now,
                    voting_ends=now + timedelta(days=7),
                )
            )
            s.commit()
        resp = env.cast_governance_vote(
            None,
            {
                "proposal_id": "p-zeroq",
                "voter_address": "0x" + "e" * 40,
                "vote_type": "for",
                "chain_id": "ait-testnet",
            },
        )
        assert resp["voting_power"] == 0
        with env.session_scope() as s:
            prop = s.exec(env.select(env.GovernanceProposal).where(env.GovernanceProposal.proposal_id == "p-zeroq")).one()
        assert prop.status == "active"


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
