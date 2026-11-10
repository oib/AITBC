"""Tests for the market host (IPFS rental) CLI helpers."""

from unittest.mock import patch

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
        # refund helper is called with (job_id, contract_id); job_id is generated
        args = mocks["_refund_orphaned_escrow"].call_args[0]
        assert args[1] == "contract-1"
        assert args[0].startswith("sw_job_ipfs_")

    def test_preexisting_pin_is_not_removed_on_abort(self):
        mocks, aborted = self._run(self._patches(pin_ok=True, market_ok=False, was_pinned=True))
        assert aborted
        mocks["_ipfs_unpin_cid"].assert_not_called()
        mocks["_refund_orphaned_escrow"].assert_called_once()

    def test_pin_failure_refunds_without_unpin(self):
        mocks, aborted = self._run(self._patches(pin_ok=False))
        assert aborted
        mocks["_ipfs_unpin_cid"].assert_not_called()
        mocks["_refund_orphaned_escrow"].assert_called_once()
        mocks["_track_market_job"].assert_not_called()
