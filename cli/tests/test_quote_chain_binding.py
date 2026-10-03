"""Energy-quote chain binding: read-only checks bind expected_chain_id to the
configured NATIVE_CHAIN_ID if set, else to the resolved chain — never to the
CLIConfig default literal. The signing path always signs the resolved chain;
a configured id only asserts what chain the quote was minted for."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

ACCOUNT = "0x" + "11" * 20
PROVIDER = "0x" + "22" * 20
NODE_WALLET = "0x" + "33" * 20
DOMAIN = "aitbc.energy.quote.v1"
RESOLVED = "ait-hub.aitbc.bubuit.net"
OTHER = "ait-other-chain"


@pytest.fixture
def runner():
    return CliRunner()


def _quote_dict(chain_id: str) -> dict:
    """A structurally valid, unexpired quote for ``chain_id``."""
    from aitbc.market.energy_pricing import EnergyQuote, SettlementRoute
    from aitbc_cli.utils.energy_quote import compute_energy_net_units
    from aitbc_cli.utils.address import to_canonical

    now = int(time.time())
    floor = compute_energy_net_units(
        tbp_watts=100,
        eur_per_kwh_scaled=30 * 10**16,
        ait_per_eur_scaled=10**18,
        gpu_count=1,
        duration_seconds=3600,
        settlement_unit_scale=10**18,
    )
    q = EnergyQuote(
        domain=DOMAIN,
        chain_id=chain_id,
        settlement_asset="AITBC",
        settlement_unit_scale=10**18,
        buyer=to_canonical(ACCOUNT),
        provider=PROVIDER,
        job_id="job-1",
        quote_id="q-1",
        settlement_route=SettlementRoute.NATIVE,
        resource_id="res-1",
        model_id="m-1",
        gpu_count=1,
        duration_seconds=3600,
        eur_per_kwh_scaled=30 * 10**16,
        tbp_watts=100,
        ait_per_eur_scaled=10**18,
        rate_version=1,
        rate_observed_at=now,
        rate_source_kind="manual",
        profile_revision=1,
        net_energy_floor_units=floor,
        principal_units=floor * 2,
        issued_at=now,
        expires_at=now + 300,
        operator_signature=b"\xde\xad\xbe\xef",
    )
    return q.to_dict(include_signature=True)


def _config(native_chain_id=""):
    c = MagicMock()
    c.native_chain_id = native_chain_id
    c.blockchain_rpc_url = "http://localhost:8202"
    c.coordinator_api_url = "http://localhost:8203"
    c.energy_operator_address = None
    c.energy_quote_domain = DOMAIN
    c.energy_max_rate_age_seconds = 86400  # real int: int > MagicMock comparison crashes in verify_quote
    c.energy_pricing_contract_address = None
    c.evm_rpc_url = None
    return c


def _ok_probe(chain_id=RESOLVED):
    prober = MagicMock()
    prober.get.return_value = {"chain_id": chain_id}
    return patch("aitbc_cli.utils.chain_id.AITBCHTTPClient", return_value=prober)


def _failing_probe():
    prober = MagicMock()
    prober.get.side_effect = RuntimeError("connection refused")
    return patch("aitbc_cli.utils.chain_id.AITBCHTTPClient", return_value=prober)


def _invoke(runner, args, obj=None):
    from aitbc_cli.commands.market import market

    base = {"output_format": "table", "api_key": "k"}
    base.update(obj or {})
    return runner.invoke(market, args, obj=base)


QUOTE_ARGS = ["gpu", "quote", "--gpu-id", "g1", "--buyer-id", ACCOUNT]


def _quote_patches(config, result_quote_dict):
    client = MagicMock()
    client.post.return_value = {"energy_quote": result_quote_dict, "buyer_charge_ait": "1"}
    return (
        patch("aitbc_cli.commands.market.gpu.AITBCHTTPClient", return_value=client),
        patch("aitbc_cli.commands.market.gpu.get_config", return_value=config),
        patch("aitbc_cli.config.get_config", return_value=config),
        client,
    )


def _buy_args(tmp_path, quote_dict):
    f = tmp_path / "q.json"
    f.write_text(json.dumps(quote_dict))
    return [
        "gpu",
        "buy",
        "--gpu-id",
        "g1",
        "--buyer-id",
        ACCOUNT,
        "--job-id",
        "job-1",
        "--duration-hours",
        "1",
        "--settlement",
        "native",
        "--wallet",
        "w",
        "--password",
        "pw",
        "--yes",
        "--energy-quote",
        str(f),
    ]


def _buy_patches(config):
    client = MagicMock()
    client.post.return_value = {"payment_id": "pay-1"}
    lock_tx = {"from": ACCOUNT, "payload": {"provider": PROVIDER}, "nonce": 1, "fee": "1"}
    return (
        patch("aitbc_cli.commands.market.gpu.get_config", return_value=config),
        patch("aitbc_cli.config.get_config", return_value=config),
        patch("aitbc_cli.commands.market.gpu.load_wallet_for_payment", return_value=(ACCOUNT, "0xpriv", "w")),
        patch("aitbc_cli.utils.escrow.get_node_wallet", return_value=NODE_WALLET),
        patch("aitbc_cli.commands.market.gpu.create_signed_escrow_lock", return_value=(lock_tx, "0xsig")),
        patch("aitbc_cli.commands.market.gpu.AITBCHTTPClient", return_value=client),
        client,
    )


def test_quote_binds_to_resolved_chain(runner):
    """No NATIVE_CHAIN_ID: a quote for the resolved chain verifies."""
    config = _config()
    q = _quote_dict(RESOLVED)
    *patches, client = _quote_patches(config, q)
    with patches[0], patches[1], patches[2], _ok_probe():
        result = _invoke(runner, QUOTE_ARGS)
    assert result.exit_code == 0, result.output
    assert "Quote verified locally" in result.output


def test_buy_refuses_before_signing_on_mismatch(runner, tmp_path):
    """A quote for a different chain is refused before any signing call."""
    config = _config()
    q = _quote_dict(OTHER)
    *patches, client = _buy_patches(config)
    with patches[0], patches[1], patches[2] as loader, patches[3], patches[4] as signer, patches[5], _ok_probe():
        result = _invoke(runner, _buy_args(tmp_path, q))
    assert result.exit_code != 0
    text = result.output + str(result.exception)
    assert OTHER in text and RESOLVED in text
    assert "resolved" in text
    loader.assert_not_called()
    signer.assert_not_called()


def test_quote_warns_not_refuses_on_mismatch(runner):
    """`market gpu quote` warns on a chain mismatch but still exits 0."""
    config = _config()
    q = _quote_dict(OTHER)
    *patches, client = _quote_patches(config, q)
    with patches[0], patches[1], patches[2], _ok_probe():
        result = _invoke(runner, QUOTE_ARGS)
    assert result.exit_code == 0, result.output
    assert "does not match" in result.output


def test_explicit_native_chain_id_wins(runner):
    """A configured NATIVE_CHAIN_ID binds verification and skips the probe."""
    config = _config(native_chain_id="explicit-native")
    q = _quote_dict("explicit-native")
    *patches, client = _quote_patches(config, q)
    with patches[0], patches[1], patches[2], _failing_probe() as probe_cls:
        result = _invoke(runner, QUOTE_ARGS)
    assert result.exit_code == 0, result.output
    assert "Quote verified locally" in result.output
    probe_cls.assert_not_called()


def test_quote_unresolved_prints_caveat(runner):
    """A failing probe on the read path skips the binding check but says so."""
    config = _config()
    q = _quote_dict(OTHER)  # any chain id: the check is skipped entirely
    *patches, client = _quote_patches(config, q)
    with patches[0], patches[1], patches[2], _failing_probe():
        result = _invoke(runner, QUOTE_ARGS)
    assert result.exit_code == 0, result.output
    assert "chain binding not checked: chain id unresolved" in result.output


def test_buy_unresolved_aborts_loudly(runner, tmp_path):
    """A failing probe on the signing path aborts the buy."""
    config = _config()
    q = _quote_dict(RESOLVED)
    *patches, client = _buy_patches(config)
    with patches[0], patches[1], patches[2], patches[3], patches[4] as signer, patches[5], _failing_probe():
        result = _invoke(runner, _buy_args(tmp_path, q))
    assert result.exit_code != 0
    signer.assert_not_called()


def test_buy_signs_the_chain_it_verified(runner, tmp_path):
    """The ESCROW_LOCK is signed with the same id the quote verified against."""
    config = _config()
    q = _quote_dict(RESOLVED)
    *patches, client = _buy_patches(config)
    with patches[0], patches[1], patches[2], patches[3], patches[4] as signer, patches[5], _ok_probe():
        result = _invoke(runner, _buy_args(tmp_path, q))
    assert result.exit_code == 0, result.output
    signer.assert_called_once()
    assert signer.call_args.kwargs["chain_id"] == RESOLVED


def test_buy_configured_mismatch_aborts_before_wallet(runner, tmp_path, monkeypatch):
    """a) configured X + root flag Y: refuse before wallet load or signing, naming both ids."""
    monkeypatch.delenv("CHAIN_ID", raising=False)
    config = _config(native_chain_id="conf-chain")
    q = _quote_dict("conf-chain")
    *patches, client = _buy_patches(config)
    with patches[0], patches[1], patches[2] as loader, patches[3], patches[4] as signer, patches[5], _ok_probe():
        result = _invoke(runner, _buy_args(tmp_path, q), obj={"chain_id_explicit": "flag-chain"})
    assert result.exit_code != 0
    text = result.output + str(result.exception)
    assert "conf-chain" in text and "flag-chain" in text
    loader.assert_not_called()
    signer.assert_not_called()


def test_buy_configured_mismatch_vs_probe(runner, tmp_path, monkeypatch):
    """b) configured X, no flag, probe answers Z != X: same refusal."""
    monkeypatch.delenv("CHAIN_ID", raising=False)
    config = _config(native_chain_id="conf-chain")
    q = _quote_dict("conf-chain")
    *patches, client = _buy_patches(config)
    with patches[0], patches[1], patches[2] as loader, patches[3], patches[4] as signer, patches[5], _ok_probe("probe-chain"):
        result = _invoke(runner, _buy_args(tmp_path, q))
    assert result.exit_code != 0
    text = result.output + str(result.exception)
    assert "conf-chain" in text and "probe-chain" in text
    loader.assert_not_called()
    signer.assert_not_called()


def test_buy_configured_match_signs_resolved(runner, tmp_path, monkeypatch):
    """c) configured id equal to the resolved id: buy proceeds, signs the resolved id."""
    monkeypatch.delenv("CHAIN_ID", raising=False)
    config = _config(native_chain_id=RESOLVED)
    q = _quote_dict(RESOLVED)
    *patches, client = _buy_patches(config)
    with patches[0], patches[1], patches[2], patches[3], patches[4] as signer, patches[5], _ok_probe(RESOLVED):
        result = _invoke(runner, _buy_args(tmp_path, q))
    assert result.exit_code == 0, result.output
    signer.assert_called_once()
    assert signer.call_args.kwargs["chain_id"] == RESOLVED


def test_buy_flag_signs_flag_without_probe(runner, tmp_path, monkeypatch):
    """d) empty config + flag Y + quote minted for Y: signs Y, probe never called."""
    monkeypatch.delenv("CHAIN_ID", raising=False)
    config = _config()
    q = _quote_dict("flag-chain")
    *patches, client = _buy_patches(config)
    with patches[0], patches[1], patches[2], patches[3], patches[4] as signer, patches[5], _failing_probe() as probe_cls:
        result = _invoke(runner, _buy_args(tmp_path, q), obj={"chain_id_explicit": "flag-chain"})
    assert result.exit_code == 0, result.output
    signer.assert_called_once()
    assert signer.call_args.kwargs["chain_id"] == "flag-chain"
    probe_cls.assert_not_called()


def test_real_config_native_chain_id_contract(runner, tmp_path, monkeypatch):
    """e) real CLIConfig: default is ""; helper honours NATIVE_CHAIN_ID env and its source."""
    from aitbc_cli.config import CLIConfig
    from aitbc_cli.utils.energy_quote import expected_quote_chain_id

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AITBC_CONFIG_FILE", str(tmp_path / "absent.yaml"))
    monkeypatch.delenv("NATIVE_CHAIN_ID", raising=False)
    monkeypatch.delenv("CHAIN_ID", raising=False)

    assert CLIConfig().native_chain_id == ""
    with _ok_probe("probe-chain"):
        assert expected_quote_chain_id(None, "http://x", strict=False) == (
            "probe-chain",
            "resolved --chain-id/CHAIN_ID/RPC probe",
        )

    monkeypatch.setenv("NATIVE_CHAIN_ID", "foo")
    with _failing_probe():
        assert expected_quote_chain_id(None, "http://x", strict=False) == ("foo", "NATIVE_CHAIN_ID config")
