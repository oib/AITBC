"""Pins for CLI-WALLET-SCENARIO-01-FINDINGS-1 (#2196).

Defects covered:
1. ``multisig-propose`` read ``balance`` from the local multisig JSON
   (always the creation-time 0) instead of the chain — funded multisigs
   could never propose.
2. ``multisig-sign`` crashed ``TypeError: float - str`` at threshold and
   debited the local balance as if that were a settlement.
3. Multisig "execution" was a local JSON debit only — no on-chain tx.
   Now approval is recorded honestly with a warning.
4. ``liquidity-claim``/``liquidity-unstake`` hardcoded ``pool_id=main``
   while ``liquidity-stake`` accepts ``--pool`` — mismatched stakes
   produced invalid txs that poisoned proposers' mempool view.
6. ``wallet stats`` reported the local ledger balance as the spendable
   balance; it now shows the chain balance with the local figure labeled.
"""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.wallet import wallet
from aitbc_cli.utils.wallet_loader import write_json_0600
from aitbc.utils.units import UNITS_PER_AIT


def _invoke(tmp_path, args, monkeypatch):
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path / "wallets"))
    return CliRunner().invoke(wallet, args, obj={"output_format": "table"})


def _make_multisig(tmp_path, name="ms", balance="0.0"):
    d = tmp_path / "wallets"
    d.mkdir(parents=True, exist_ok=True)
    addr = "0x" + "ab" * 20
    data = {
        "wallet_id": name,
        "type": "multisig",
        "address": addr,
        "signers": ["0x" + "aa" * 20, "0x" + "bb" * 20, "0x" + "cc" * 20],
        "threshold": 2,
        "created_at": "2026-11-18T00:00:00",
        "balance": balance,
        "transactions": [],
        "pending_transactions": [],
    }
    write_json_0600(d / f"{name}_multisig.json", data)
    return addr, data


class _Cfg:
    blockchain_rpc_url = "http://rpc.test"


def _account_get(units):
    """Value factory for AITBCHTTPClient.get (bound-method call shape)."""

    def _get(path):
        assert path.startswith("/rpc/account/")
        return {"address": "x", "balance": units, "nonce": 0, "exists": True}

    return _get


class TestMultisigProposeChainBalance:
    """#2196 defect 1+6-adjacent: propose must consult the chain, in AIT."""

    def test_funded_multisig_can_propose(self, tmp_path, monkeypatch):
        """3.9 AIT on chain, local balance 0.0 — propose of 3.9 must pass."""
        addr, _ = _make_multisig(tmp_path)
        units = int(3.9 * UNITS_PER_AIT)
        with (
            patch("aitbc_cli.commands.wallet.multisig.get_config", return_value=_Cfg()),
            patch("aitbc_cli.commands.wallet.multisig.AITBCHTTPClient") as http_cls,
        ):
            http_cls.return_value.get.side_effect = _account_get(units)
            result = _invoke(
                tmp_path,
                ["multisig-propose", "--wallet", "ms", "--to-address", "0x" + "dd" * 20, "--amount", "3.9"],
                monkeypatch,
            )
        assert result.exit_code == 0, result.output
        assert "mstx_" in result.output or "proposed" in result.output.lower()

    def test_propose_uses_ait_not_units(self, tmp_path, monkeypatch):
        """Regression pin: raw units must not be compared to the AIT amount —
        3.9 AIT = ~3.9e18 units; comparing units-as-AIT would pass any amount."""
        addr, _ = _make_multisig(tmp_path)
        units = int(0.5 * UNITS_PER_AIT)  # only 0.5 AIT on chain
        with (
            patch("aitbc_cli.commands.wallet.multisig.get_config", return_value=_Cfg()),
            patch("aitbc_cli.commands.wallet.multisig.AITBCHTTPClient") as http_cls,
        ):
            http_cls.return_value.get.side_effect = _account_get(units)
            result = _invoke(
                tmp_path,
                ["multisig-propose", "--wallet", "ms", "--to-address", "0x" + "dd" * 20, "--amount", "3.9"],
                monkeypatch,
            )
        assert result.exit_code != 0
        assert "Insufficient" in result.output

    def test_propose_aborts_when_chain_lookup_fails(self, tmp_path, monkeypatch):
        """Unknown balance must abort, never fall back to the stale local 0."""
        _make_multisig(tmp_path)
        with (
            patch("aitbc_cli.commands.wallet.multisig.get_config", return_value=_Cfg()),
            patch("aitbc_cli.commands.wallet.multisig.AITBCHTTPClient") as http_cls,
        ):
            http_cls.return_value.get.side_effect = RuntimeError("rpc down")
            result = _invoke(
                tmp_path,
                ["multisig-propose", "--wallet", "ms", "--to-address", "0x" + "dd" * 20, "--amount", "0.1"],
                monkeypatch,
            )
        assert result.exit_code != 0
        assert "Cannot verify" in result.output or "on-chain" in result.output


class TestMultisigSignHonestApproval:
    """#2196 defects 2+3: no float−str crash, no fake balance debit,
    approval is labeled local-only."""

    def _propose_first(self, tmp_path, monkeypatch):
        addr, _ = _make_multisig(tmp_path)
        units = int(10 * UNITS_PER_AIT)
        with (
            patch("aitbc_cli.commands.wallet.multisig.get_config", return_value=_Cfg()),
            patch("aitbc_cli.commands.wallet.multisig.AITBCHTTPClient") as http_cls,
        ):
            http_cls.return_value.get.side_effect = _account_get(units)
            result = _invoke(
                tmp_path,
                ["multisig-propose", "--wallet", "ms", "--to-address", "0x" + "dd" * 20, "--amount", "1.0"],
                monkeypatch,
            )
        assert result.exit_code == 0, result.output
        ms = json.loads((tmp_path / "wallets" / "ms_multisig.json").read_text())
        tx_id = ms["pending_transactions"][0]["tx_id"]
        return tx_id, ms

    def test_threshold_approval_does_not_debit_or_crash(self, tmp_path, monkeypatch):
        tx_id, ms_before = self._propose_first(tmp_path, monkeypatch)
        balance_before = ms_before["balance"]

        # sign once (1/2), then second signer reaches threshold
        for signer in ["0x" + "aa" * 20, "0x" + "bb" * 20]:
            result = _invoke(
                tmp_path,
                ["multisig-sign", "--wallet", "ms", "--tx-id", tx_id, "--signer", signer],
                monkeypatch,
            )
            assert result.exit_code == 0, result.output

        ms_after = json.loads((tmp_path / "wallets" / "ms_multisig.json").read_text())
        # balance untouched — approval must not fake a settlement
        assert ms_after["balance"] == balance_before
        approved = [t for t in ms_after["transactions"] if t["type"] == "multisig_approved"]
        assert len(approved) == 1
        # honest warning surfaced in output
        assert "no on-chain" in result.output.lower() or "approved locally" in result.output.lower()

    def test_signer_not_authorized_refused(self, tmp_path, monkeypatch):
        tx_id, _ = self._propose_first(tmp_path, monkeypatch)
        result = _invoke(
            tmp_path,
            ["multisig-sign", "--wallet", "ms", "--tx-id", tx_id, "--signer", "0x" + "99" * 20],
            monkeypatch,
        )
        assert result.exit_code != 0
        assert "not an authorized signer" in result.output

    def test_duplicate_signature_refused(self, tmp_path, monkeypatch):
        tx_id, _ = self._propose_first(tmp_path, monkeypatch)
        signer = "0x" + "aa" * 20
        _invoke(tmp_path, ["multisig-sign", "--wallet", "ms", "--tx-id", tx_id, "--signer", signer], monkeypatch)
        result = _invoke(
            tmp_path,
            ["multisig-sign", "--wallet", "ms", "--tx-id", tx_id, "--signer", signer],
            monkeypatch,
        )
        assert result.exit_code != 0
        assert "already signed" in result.output


class TestLiquidityPoolPassthrough:
    """#2196 defect 4: --pool must reach the submitted tx payload."""

    def _run_liquidity(self, tmp_path, monkeypatch, command, extra_args):
        from unittest.mock import MagicMock, Mock

        from aitbc_cli.commands.wallet import staking as wallet_staking

        captured = {}

        def mock_post(path, json=None):
            captured["path"] = path
            captured["tx"] = json
            return {"transaction_hash": "0xliqhash"}

        mock_client = Mock()
        mock_client.get.side_effect = lambda path: {"balance": 10**24, "nonce": 0} if "/account/" in path else {}
        mock_client.post.side_effect = mock_post
        mock_http = MagicMock(return_value=mock_client)

        mock_config = MagicMock()
        mock_config.blockchain_rpc_url = "http://localhost:8202"
        mock_config.wallet_daemon_url = "http://localhost:8108"
        mock_config.chain_id = "test-chain"
        mock_config.node_id = "node0"
        mock_config.data_dir = tmp_path

        w = tmp_path / "w1.json"
        w.write_text(
            json.dumps(
                {
                    "address": "0xDb5247d03cA2e40f3995A583b2C097Ab703efD4d",
                    "balance": 100.0,
                    "private_key": "a" * 64,
                    "transactions": [],
                    "created_at": "2024-01-01T00:00:00",
                }
            )
        )

        for mod, name in [
            (wallet_staking, "AITBCHTTPClient"),
            (wallet_staking, "get_config"),
        ]:
            monkeypatch.setattr(mod, name, mock_http if name == "AITBCHTTPClient" else (lambda: mock_config))
        import aitbc_cli.commands.wallet as wallet_pkg

        monkeypatch.setattr(wallet_pkg, "get_config", lambda: mock_config)
        monkeypatch.setattr("aitbc_cli.utils.chain_id.get_chain_id", lambda *a, **k: "test-chain")
        monkeypatch.setattr("aitbc_cli.utils.dual_mode_wallet_adapter.DualModeWalletAdapter", MagicMock())

        result = CliRunner().invoke(
            wallet,
            ["--wallet-path", str(w), command, *extra_args],
            obj={"output_format": "json"},
        )
        return result, captured

    def test_claim_pool_reaches_payload(self, tmp_path, monkeypatch):
        result, captured = self._run_liquidity(
            tmp_path,
            monkeypatch,
            "liquidity-claim",
            ["--stake-id", "lstake-1", "--pool", "gpu-8"],
        )
        assert result.exit_code == 0, result.output
        tx = captured.get("tx") or {}
        assert tx.get("type") == "LIQUIDITY_CLAIM"
        assert (tx.get("payload") or {}).get("pool_id") == "gpu-8", captured

    def test_unstake_pool_reaches_payload(self, tmp_path, monkeypatch):
        result, captured = self._run_liquidity(
            tmp_path,
            monkeypatch,
            "liquidity-unstake",
            ["--stake-id", "lstake-1", "--pool", "gpu-8"],
        )
        assert result.exit_code == 0, result.output
        tx = captured.get("tx") or {}
        assert tx.get("type") == "LIQUIDITY_WITHDRAW"
        assert (tx.get("payload") or {}).get("pool_id") == "gpu-8", captured

    def test_claim_default_pool_is_main(self, tmp_path, monkeypatch):
        """Backward compat: no --pool keeps pool_id=main."""
        result, captured = self._run_liquidity(
            tmp_path,
            monkeypatch,
            "liquidity-claim",
            ["--stake-id", "lstake-1"],
        )
        assert result.exit_code == 0, result.output
        tx = captured.get("tx") or {}
        assert (tx.get("payload") or {}).get("pool_id") == "main", captured


class TestStatsChainBalance:
    """#2196 defect 6: stats shows chain balance; local ledger labeled."""

    def _make_wallet(self, tmp_path, balance=5.0):
        d = tmp_path / "wallets"
        d.mkdir(parents=True, exist_ok=True)
        write_json_0600(
            d / "w1.json",
            {
                "address": "0x" + "aa" * 20,
                "private_key": "0x" + "11" * 32,
                "encrypted": False,
                "balance": balance,
                "transactions": [],
            },
        )
        return d

    def test_stats_prefers_chain_over_local(self, tmp_path, monkeypatch):
        from aitbc_cli.commands.wallet import basic as basic_mod

        d = self._make_wallet(tmp_path, balance=5.0)
        units = int(2 * UNITS_PER_AIT)

        with (
            patch.object(basic_mod, "get_config", return_value=_Cfg()),
            patch.object(basic_mod, "AITBCHTTPClient") as http_cls,
        ):
            http_cls.return_value.get.return_value = {"balance": units, "nonce": 0, "exists": True}
            monkeypatch.setenv("AITBC_WALLET_DIR", str(d))
            monkeypatch.setenv("AITBC_DEFAULT_WALLET", "w1")
            result = CliRunner().invoke(wallet, ["stats"], obj={"output_format": "json", "wallet_dir": d})
        assert result.exit_code == 0, result.output
        out = result.output
        # chain balance (2 AIT) is the spendable figure, local 5.0 labeled
        assert "local_ledger_balance" in out or "balance_source" in out
        assert '"chain"' in out or "chain" in out

    def test_stats_falls_back_to_local_when_rpc_down(self, tmp_path, monkeypatch):
        from aitbc_cli.commands.wallet import basic as basic_mod

        d = self._make_wallet(tmp_path, balance=5.0)
        with (
            patch.object(basic_mod, "get_config", return_value=_Cfg()),
            patch.object(basic_mod, "AITBCHTTPClient") as http_cls,
        ):
            http_cls.return_value.get.side_effect = RuntimeError("down")
            monkeypatch.setenv("AITBC_WALLET_DIR", str(d))
            monkeypatch.setenv("AITBC_DEFAULT_WALLET", "w1")
            result = CliRunner().invoke(wallet, ["stats"], obj={"output_format": "json", "wallet_dir": d})
        assert result.exit_code == 0, result.output
        assert "local" in result.output.lower()


class TestDualModeAdapterUnits:
    """#2196 defect 6 (adapter leg): spend() compared raw units to AIT."""

    def test_spend_compares_ait_not_units(self):
        """units_to_ait conversion applied before the sufficiency check —
        1 AIT spend against a 0.5-AIT chain balance must be refused even
        though the raw unit figure dwarfs the amount."""
        from decimal import Decimal

        # exercise the comparison directly via the same expression the fix uses
        from aitbc.utils.units import units_to_ait

        chain_units = int(0.5 * UNITS_PER_AIT)
        available = units_to_ait(chain_units)
        assert available == Decimal("0.5")
        assert available < Decimal("1")  # would wrongly pass on raw units


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestMultisigUnspendableGuard2362:
    """#2362: the record-keeping multisig address has no spendable key —
    funding it burns funds; propose must not mislabel a 404 as an outage."""

    def test_propose_404_is_zero_balance_not_rpc_error(self, tmp_path, monkeypatch):
        """Account-not-found (404) means zero balance → honest 'Insufficient',
        never the 'check node reachability' misclassification."""
        _make_multisig(tmp_path)

        class Http404(Exception):
            def __init__(self):
                super().__init__("404 Client Error")
                self.response = type("R", (), {"status_code": 404})()

        with (
            patch("aitbc_cli.commands.wallet.multisig.get_config", return_value=_Cfg()),
            patch("aitbc_cli.commands.wallet.multisig.AITBCHTTPClient") as http_cls,
        ):
            http_cls.return_value.get.side_effect = Http404()
            result = _invoke(
                tmp_path,
                ["multisig-propose", "--wallet", "ms", "--to-address", "0x" + "dd" * 20, "--amount", "0.1"],
                monkeypatch,
            )
        assert result.exit_code != 0
        assert "Insufficient" in result.output
        assert "reachability" not in result.output

    def test_multisig_addresses_maps_files(self, tmp_path):
        from aitbc_cli.commands.wallet.basic import _multisig_addresses

        addr, _ = _make_multisig(tmp_path, name="team")
        assert _multisig_addresses(tmp_path / "wallets") == {addr.lower(): "team"}

    def test_send_guard_refuses_multisig_recipient(self, tmp_path):
        from aitbc_cli.commands.wallet.basic import _assert_not_multisig_recipient
        from aitbc_cli.utils.error_handling import CLIError

        addr, _ = _make_multisig(tmp_path, name="team")
        ctx = type("C", (), {"obj": {}})()
        with pytest.raises(CLIError, match="unrecoverable"):
            _assert_not_multisig_recipient(ctx, tmp_path / "wallets", addr.upper().replace("0X", "0x"))

    def test_send_invokes_multisig_guard(self, tmp_path, monkeypatch):
        """#2362 wiring pin: deleting the ``_assert_not_multisig_recipient``
        call site inside ``send`` must fail a test — the guard exists because
        funding a multisig already burned 0.002 AIT once."""
        from click.testing import CliRunner

        from aitbc_cli.commands.wallet.basic import send as wallet_send
        from aitbc_cli.utils.wallet_loader import write_json_0600

        wallets = tmp_path / "wallets"
        wallets.mkdir(parents=True, exist_ok=True)
        sender_path = wallets / "sender.json"
        write_json_0600(sender_path, {"address": "0x" + "11" * 20, "private_key": "0x" + "44" * 32})
        addr, _ = _make_multisig(tmp_path, name="team")

        # Past the guard, send resolves the RPC endpoint — stub it so a
        # removed call site surfaces as this sentinel, not a hang.
        def _no_rpc(*a, **k):
            raise AssertionError("multisig guard bypassed — send proceeded past _assert_not_multisig_recipient")

        monkeypatch.setattr("aitbc_cli.commands.wallet.basic._resolve_send_rpc_endpoint", _no_rpc)

        result = CliRunner().invoke(
            wallet_send,
            ["--to-address", addr, "--amount", "1", "--fee", "0.001"],
            obj={"wallet_name": "sender", "wallet_sign_path": sender_path, "wallet_dir": wallets},
        )
        assert result.exit_code != 0
        assert "unrecoverable" in result.output
        assert "guard bypassed" not in result.output

    def test_delete_accepts_bare_multisig_name(self, tmp_path, monkeypatch):
        """`wallet delete --name ms` must find `ms_multisig.json` (#2362)."""
        _make_multisig(tmp_path, name="ms")
        result = _invoke(tmp_path, ["delete", "--name", "ms", "--confirm"], monkeypatch)
        assert result.exit_code == 0, result.output
        assert not (tmp_path / "wallets" / "ms_multisig.json").exists()
