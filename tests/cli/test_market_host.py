"""Tests for the market host (IPFS rental) CLI helpers."""

from unittest.mock import patch

from eth_account import Account

from aitbc_cli.commands.market import host as host_module


class TestResolveIpfsApi:
    """The buyer's local daemon is used, never the provider's offer endpoint."""

    def test_env_wins(self, monkeypatch):
        monkeypatch.setenv("IPFS_API_URL", "http://10.0.0.9:5002")
        offer = {"endpoint": "http://localhost:5001"}
        assert host_module._resolve_ipfs_api(offer) == "http://10.0.0.9:5002"

    def test_ignores_offer_endpoint_and_probes_island_first(self, monkeypatch):
        monkeypatch.delenv("IPFS_API_URL", raising=False)
        offer = {"endpoint": "http://localhost:5001"}
        with patch.object(host_module, "_daemon_available", side_effect=lambda url: url.endswith("5002")):
            assert host_module._resolve_ipfs_api(offer) == "http://127.0.0.1:5002"

    def test_falls_back_to_legacy_kubo(self, monkeypatch):
        monkeypatch.delenv("IPFS_API_URL", raising=False)
        offer = {"endpoint": "http://localhost:5002"}
        with patch.object(host_module, "_daemon_available", side_effect=lambda url: url.endswith("5001")):
            assert host_module._resolve_ipfs_api(offer) == "http://127.0.0.1:5001"

    def test_defaults_to_island_when_nothing_reachable(self, monkeypatch):
        monkeypatch.delenv("IPFS_API_URL", raising=False)
        with patch.object(host_module, "_daemon_available", return_value=False):
            assert host_module._resolve_ipfs_api({}) == "http://127.0.0.1:5002"


class TestIpfsHostingAbortCleanup:
    """IPFS-PIN-LEAK-1 (#1687): post-pin aborts must undo pin + escrow."""

    CID = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi"

    def _offer(self):
        return {
            "offer_id": "offer-1",
            "plugin_id": "ipfs-ipfs-host",
            "service_type": "ipfs",
            "price_unit": "per_day",
            "price": "1",
            "provider_address": "0xProvider",
            "disk_quota_mb": 100,
        }

    def _patches(self, pin_ok=True, market_ok=False, was_pinned=False):
        from pathlib import Path

        return {
            "_resolve_offer": patch.object(host_module, "_resolve_offer", return_value=self._offer()),
            "_resolve_hosting_content": patch.object(
                host_module, "_resolve_hosting_content", return_value=(Path("data.bin"), self.CID, 100)
            ),
            "get_market_wallet": patch.object(host_module, "get_market_wallet", return_value=("0xBuyer", "pk", "w1")),
            "_buyer_used_bytes": patch.object(host_module, "_buyer_used_bytes", return_value=0),
            "_upload_hosting_file": patch.object(
                host_module, "_upload_hosting_file", return_value=(self.CID, 100)
            ),
            "_escrow_create": patch.object(host_module, "_escrow_create", return_value="contract-1"),
            "_ipfs_is_pinned": patch.object(host_module, "_ipfs_is_pinned", return_value=was_pinned),
            "_ipfs_pin_cid": patch.object(host_module, "_ipfs_pin_cid", return_value=pin_ok),
            "_track_market_job": patch.object(
                host_module,
                "_track_market_job",
                return_value={"job_id": "j1"} if market_ok else None,
            ),
            "_refund_orphaned_escrow": patch.object(host_module, "_refund_orphaned_escrow"),
            "_ipfs_unpin_cid": patch.object(host_module, "_ipfs_unpin_cid"),
        }

    def _run(self, patches):
        import click
        from contextlib import ExitStack

        aborted = False
        with ExitStack() as stack:
            mocks = {name: stack.enter_context(p) for name, p in patches.items()}
            try:
                host_module._run_ipfs_hosting(
                    None, "offer-1", self.CID, 1, True, False, "json"
                )
            except click.Abort:
                aborted = True
            return mocks, aborted

    def test_market_registration_failure_unpins_and_refunds(self):
        mocks, aborted = self._run(self._patches(pin_ok=True, market_ok=False, was_pinned=False))
        assert aborted
        mocks["_ipfs_unpin_cid"].assert_called_once()
        assert mocks["_ipfs_unpin_cid"].call_args[0][1] == self.CID
        # refund helper is called with (ctx, job_id, contract_id); job_id is generated
        args = mocks["_refund_orphaned_escrow"].call_args[0]
        assert args[2] == "contract-1"
        assert args[1].startswith("sw_job_ipfs_")

    def test_preexisting_pin_is_not_removed_on_abort(self):
        mocks, aborted = self._run(self._patches(pin_ok=True, market_ok=False, was_pinned=True))
        assert aborted
        mocks["_ipfs_unpin_cid"].assert_not_called()
        mocks["_refund_orphaned_escrow"].assert_called_once()

    def test_pin_failure_aborts_before_escrow(self):
        """#2340: pin now runs BEFORE the escrow lock — a pin failure aborts
        with nothing locked, so no refund is needed or attempted."""
        mocks, aborted = self._run(self._patches(pin_ok=False))
        assert aborted
        mocks["_ipfs_unpin_cid"].assert_not_called()
        mocks["_escrow_create"].assert_not_called()
        mocks["_refund_orphaned_escrow"].assert_not_called()
        mocks["_track_market_job"].assert_not_called()


class TestCoordinatorHostEscrow:
    """#2340: market host locks escrow through the coordinator payment rail so
    JobPayment/PaymentEscrow rows exist and StuckEscrowSweeper covers the lock."""

    CID = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi"

    class _FakeClient:
        def __init__(self, responses):
            self.responses = responses
            self.calls = []

        def post(self, path, json=None, **kw):
            self.calls.append((path, json))
            return self.responses[path]

    def _escrow_kwargs(self):
        from decimal import Decimal

        return dict(
            job_id="sw_job_ipfs_test",
            buyer="0xBuyer",
            provider="0xProvider",
            total_cost=Decimal("1.5"),
            config=object(),
            private_key="pk",
            node_wallet="0xNode",
            offer={"offer_id": "offer-1", "model": "m"},
            days=3,
        )

    def _patches(self, client):
        import aitbc_cli.utils.escrow as utils_escrow

        return {
            "_coordinator_payment_client": patch.object(
                host_module, "_coordinator_payment_client", return_value=client
            ),
            "_resolve_escrow_node_wallet": patch.object(
                host_module, "_resolve_escrow_node_wallet", return_value="0xNode"
            ),
            "_get_blockchain_rpc_url": patch.object(
                host_module, "_get_blockchain_rpc_url", return_value="http://rpc"
            ),
            "create_signed_escrow_lock": patch.object(
                utils_escrow,
                "create_signed_escrow_lock",
                return_value=(
                    {"from": "0xBuyer", "nonce": 7, "fee": 100, "payload": {"provider": "0xProvider"}},
                    "0xsig",
                ),
            ),
            "get_chain_id": patch.object(host_module, "get_chain_id", return_value="testnet"),
        }

    def test_happy_path_posts_job_then_signed_payment(self):
        client = self._FakeClient(
            {
                "/v1/jobs": {"job_id": "coord-job-1", "payment_status": "pending"},
                "/v1/payments": {
                    "payment_id": "pay-1",
                    "status": "escrowed",
                    "escrow_address": "contract-9",
                },
            }
        )
        from contextlib import ExitStack

        with ExitStack() as stack:
            mocks = {n: stack.enter_context(p) for n, p in self._patches(client).items()}
            result = host_module._create_coordinator_host_escrow(None, **self._escrow_kwargs())

        assert result == {
            "escrow_job_id": "coord-job-1",
            "contract_id": "contract-9",
            "payment_id": "pay-1",
            "tracked": True,
        }
        paths = [c[0] for c in client.calls]
        assert paths == ["/v1/jobs", "/v1/payments"]
        job_body = client.calls[0][1]
        assert job_body["payment_amount"] == "1.5"
        # days=3 → ttl covers rental + 1d settle slack; timeout capped at 24h
        assert job_body["ttl_seconds"] == 4 * 86400
        pay_body = client.calls[1][1]
        assert pay_body["job_id"] == "coord-job-1"
        assert pay_body["buyer_lock_signature"] == "0xsig"
        assert pay_body["buyer_lock_nonce"] == 7
        assert pay_body["buyer_lock_fee"] == 100
        assert pay_body["offer_quantity"] == "3"
        assert pay_body["escrow_timeout_seconds"] == 86400

    def test_ttl_and_timeout_scale_with_days(self):
        """#2340 respin: a 1-day rental must not inherit the old fixed 24h ttl —
        the coordinator job would hit EXPIRED mid-rental and the sweeper would
        auto-refund the escrow."""
        client = self._FakeClient(
            {
                "/v1/jobs": {"job_id": "coord-job-1"},
                "/v1/payments": {"payment_id": "pay-1", "status": "escrowed"},
            }
        )
        kwargs = self._escrow_kwargs()
        kwargs["days"] = 1
        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in self._patches(client).values():
                stack.enter_context(p)
            host_module._create_coordinator_host_escrow(None, **kwargs)

        job_body = client.calls[0][1]
        assert job_body["ttl_seconds"] == 2 * 86400
        pay_body = client.calls[1][1]
        assert pay_body["escrow_timeout_seconds"] == 86400

    def test_no_client_returns_none_for_fallback(self):
        with patch.object(host_module, "_coordinator_payment_client", return_value=None):
            assert host_module._create_coordinator_host_escrow(None, **self._escrow_kwargs()) is None

    def test_job_create_failure_returns_none(self):
        client = self._FakeClient({"/v1/jobs": {"error": "boom"}})
        # no job_id in response -> safe fallback
        with patch.object(host_module, "_coordinator_payment_client", return_value=client):
            assert host_module._create_coordinator_host_escrow(None, **self._escrow_kwargs()) is None
        assert [c[0] for c in client.calls] == ["/v1/jobs"]

    def test_payment_not_escrowed_aborts(self):
        import click

        client = self._FakeClient(
            {
                "/v1/jobs": {"job_id": "coord-job-1"},
                "/v1/payments": {"payment_id": "pay-1", "status": "failed"},
            }
        )
        from contextlib import ExitStack

        aborted = False
        with ExitStack() as stack:
            for p in self._patches(client).values():
                stack.enter_context(p)
            try:
                host_module._create_coordinator_host_escrow(None, **self._escrow_kwargs())
            except click.Abort:
                aborted = True
        assert aborted

    def test_lock_host_escrow_falls_back_to_direct_lock(self):
        with patch.object(host_module, "_coordinator_payment_client", return_value=None), patch.object(
            host_module, "_escrow_create", return_value="contract-1"
        ) as escrow_create:
            result = host_module._lock_host_escrow(None, **self._escrow_kwargs())
        assert result["tracked"] is False
        assert result["escrow_job_id"] == "sw_job_ipfs_test"
        escrow_create.assert_called_once()

    def test_refund_host_escrow_tracked_uses_coordinator_job_id(self):
        with patch.object(host_module, "refund_escrow") as refund:
            host_module._refund_host_escrow(
                None, {"escrow_job_id": "coord-job-1", "tracked": True}, "sw_job_ipfs_test"
            )
        refund.assert_called_once_with(None, "coord-job-1", reason="job_failed")

    def test_refund_host_escrow_legacy_uses_orphan_refund(self):
        with patch.object(host_module, "_refund_orphaned_escrow") as orphan:
            host_module._refund_host_escrow(
                None,
                {"escrow_job_id": "sw_job_ipfs_test", "contract_id": "c-1", "tracked": False},
                "sw_job_ipfs_test",
            )
        orphan.assert_called_once_with(None, "sw_job_ipfs_test", "c-1")


class TestProviderPin:
    """#2348: provider-side pin + attestation + rental-token registration."""

    def test_attestation_posts_signed_provider_confirmed(self):
        posted = {}

        class _Client:
            def post(self, path, json=None):
                posted["path"] = path
                posted["json"] = json
                return {"state": "RUNNING"}

        signer = Account.create()
        with (
            patch.object(host_module, "_market_client", return_value=_Client()),
            patch.object(host_module, "get_chain_id", return_value="test-chain"),
            patch.object(host_module.time, "time", return_value=1700000000),
        ):
            result = host_module._provider_pin_attestation(
                ctx=None,
                job_id="j1",
                cid="QmX",
                size=42,
                wallet_address=signer.address,
                private_key=signer.key.hex(),
            )
        assert result == {"state": "RUNNING"}
        assert posted["path"] == "/v1/market/jobs/j1/pin-confirm"
        body = posted["json"]
        assert body["provider_confirmed"] is True
        assert body["size"] == 42
        assert body["binding"] == {"cid": "QmX", "size": 42}
        assert body["signer_address"] == signer.address
        assert body["chain_id"] == "test-chain"
        assert body["issued_at"] == 1700000000
        assert body["signature"]

    def test_rental_token_registers_with_job_keyed_fields(self):
        posted = {}

        class _Client:
            def post(self, path, json=None):
                posted["path"] = path
                posted["json"] = json
                return {"access_key": "ak"}

        job = {
            "offer_id": "offer-1",
            "buyer_address": "0xBuyer",
            "provider_address": "0xProvider",
            "payload": {"access_key": "ak", "access_secret": "as", "public_endpoint": "/ip4/1.2.3.4"},
            "constraints": {"disk_quota_mb": 10},
        }
        with patch.object(host_module, "_market_client", return_value=_Client()):
            host_module._register_ipfs_rental_token(job, "job-1", "QmX", 7, "http://127.0.0.1:5002")
        assert posted["path"] == "/v1/market/ipfs/rental-token"
        data = posted["json"]
        assert data["rental_id"] == "job-1"
        assert data["cid"] == "QmX"
        assert data["access_key"] == "ak"
        assert data["pinned"] is True
        # Settlement fields are service-owned — the CLI must not send them.
        assert "escrow_contract_id" not in data
        assert "expires_at" not in data

    def test_rental_token_skipped_without_access_credentials(self):
        called = []

        class _Client:
            def post(self, path, json=None):
                called.append(path)
                return {}

        job = {"payload": {}}
        with patch.object(host_module, "_market_client", return_value=_Client()):
            assert host_module._register_ipfs_rental_token(job, "j", "QmX", 1, "api") is None
        assert called == []
