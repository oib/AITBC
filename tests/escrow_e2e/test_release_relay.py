"""ESCROW-E2E-TEST-1 group 2: escrow release through the coordinator relay.

The real ``_post_escrow_release`` helper (ESCROW-RELEASE-2) prefers the JWT
release relay and falls back to the local→hub rpc path only when the relay
cannot answer — never on a business refusal. The stub chain enforces the
real rules: amount ≤ locked, one release per job, refunded is terminal.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import aitbc_cli.commands.market.escrow as esc_mod

from conftest import (
    BUYER_ADDRESS,
    BUYER_PRIVATE_KEY,
    FOREIGN_ADDRESS,
    PROVIDER_ADDRESS,
    bind_wallet,
    cli_config,
    cli_ctx,
)
from stubchain import COORDINATOR_URL, LOCAL_RPC_URL, SETTLEMENT_RPC_URL


def _create(wired, job_id: str, amount: str = "1.5") -> str:
    bind_wallet(wired.session, "client-1", BUYER_ADDRESS)
    return esc_mod._escrow_create(
        cli_ctx(),
        job_id,
        BUYER_ADDRESS,
        PROVIDER_ADDRESS,
        Decimal(amount),
        cli_config(),
        private_key=BUYER_PRIVATE_KEY,
    )


def _release(ctx, config, job_id, **kw):
    return esc_mod._post_escrow_release(ctx, config, job_id, **kw)


class TestReleaseViaRelay:
    def test_release_happy_path_reaches_the_chain(self, wired):
        """CLI → middleware → relay → chain: the escrow settles released."""
        _create(wired, "e2e_rel_1")
        result, failures = _release(cli_ctx(), cli_config(), "e2e_rel_1", amount="1.0")
        assert failures == []
        assert result["tx_hash"].startswith("0xrelease")
        assert result["released_amount"] == "1.0"
        assert result["refunded_amount"] == "0.5"
        row = wired.chain.escrows["e2e_rel_1"]
        assert row["state"] == "released"
        # The relay POST — not the rpc fallback — carried the release.
        assert wired.chain.calls_to("/v1/escrow/release", base=COORDINATOR_URL)
        assert wired.chain.calls_to("release", base=LOCAL_RPC_URL) == []

    def test_replayed_release_returns_the_stored_result(self, wired):
        """A second release for the same job dedups — the chain releases once."""
        _create(wired, "e2e_rel_dup")
        first, _ = _release(cli_ctx(), cli_config(), "e2e_rel_dup", amount="1.0")
        second, _ = _release(cli_ctx(), cli_config(), "e2e_rel_dup", amount="1.0")
        assert first["tx_hash"] == second["tx_hash"]
        assert second["duplicate"] is True
        releases = wired.chain.calls_to("release", base=SETTLEMENT_RPC_URL)
        assert len(releases) == 1

    def test_foreign_client_cannot_release_and_never_falls_back(self, wired):
        """A credential bound to a different wallet is a terminal 403 —
        and the unauthenticated rpc path is never used to launder it."""
        _create(wired, "e2e_rel_foreign")
        bind_wallet(wired.session, "client-2", FOREIGN_ADDRESS)
        result, failures = _release(cli_ctx("client-2"), cli_config(), "e2e_rel_foreign", amount="1.0")
        assert result is None
        assert any("refused" in f and "403" in f for f in failures)
        # The chain never saw a release POST on either path.
        assert wired.chain.calls_to("release", base=SETTLEMENT_RPC_URL) == []
        assert wired.chain.calls_to("release", base=LOCAL_RPC_URL) == []
        assert wired.chain.escrows["e2e_rel_foreign"]["state"] == "locked"

    def test_already_refunded_is_a_terminal_409(self, wired):
        """A refunded escrow: the relay answers 409 and the rpc stays silent."""
        _create(wired, "e2e_rel_refunded")
        wired.chain.set_state("e2e_rel_refunded", state="refunded", refunded_at="earlier")
        result, failures = _release(cli_ctx(), cli_config(), "e2e_rel_refunded", amount="1.0")
        assert result is None
        assert any("409" in f and "refunded" in f for f in failures)
        assert wired.chain.calls_to("release", base=SETTLEMENT_RPC_URL) == []
        assert wired.chain.calls_to("release", base=LOCAL_RPC_URL) == []

    def test_release_over_the_lock_is_refused_before_the_chain(self, wired):
        """amount > locked is refused at the relay bound — chain untouched."""
        _create(wired, "e2e_rel_over", amount="1.5")
        result, failures = _release(cli_ctx(), cli_config(), "e2e_rel_over", amount="2.0")
        assert result is None
        assert any("refused" in f for f in failures)
        assert wired.chain.calls_to("release", base=SETTLEMENT_RPC_URL) == []
        assert wired.chain.escrows["e2e_rel_over"]["state"] == "locked"

    def test_zero_amount_goes_to_the_rpc_path_not_stuck(self, wired):
        """A 0-metered release must reach the rpc path — never a stuck lock.

        The relay refuses non-positive amounts as terminal business refusals;
        the helper skips it and the rpc answers the same refusal — the escrow
        is diagnosable, not silently stranded behind a dead relay call.
        """
        _create(wired, "e2e_rel_zero")
        result, failures = _release(cli_ctx(), cli_config(), "e2e_rel_zero", amount="0")
        # The relay was never asked — the rpc path took the call.
        assert wired.chain.calls_to("/v1/escrow/release", base=COORDINATOR_URL) == []
        rpc_releases = wired.chain.calls_to("release", base=LOCAL_RPC_URL) + wired.chain.calls_to(
            "release", base=SETTLEMENT_RPC_URL
        )
        assert rpc_releases, "zero amount never reached the rpc release path"
        # The rpc refusal is named — the failure list carries it, not a hang.
        assert result is None
        assert any("positive" in f or "amount" in f for f in failures)

    def test_zero_token_metered_job_releases_via_rpc(self, wired):
        """0 tokens billed → actual_cost '0.000000' → same rpc path, with proof."""
        _create(wired, "e2e_rel_0tok")
        result, failures = _release(cli_ctx(), cli_config(), "e2e_rel_0tok", amount="0.000000", job_tx_hash="0xproof")
        assert wired.chain.calls_to("/v1/escrow/release", base=COORDINATOR_URL) == []
        rpc_releases = wired.chain.calls_to("release", base=LOCAL_RPC_URL) + wired.chain.calls_to(
            "release", base=SETTLEMENT_RPC_URL
        )
        assert rpc_releases
        assert rpc_releases[0][3]["job_tx_hash"] == "0xproof"

    def test_no_credential_skips_the_relay_and_the_rpc_releases(self, wired, monkeypatch):
        """No stored client credential → relay skipped, rpc path settles it."""
        monkeypatch.setattr(
            esc_mod,
            "AuthManager",
            lambda: SimpleNamespace(get_credential=lambda name: None),
        )
        wired.chain.escrows["e2e_rel_nocreds"] = {
            "job_id": "e2e_rel_nocreds",
            "contract_id": "esc-e2e_rel_nocreds",
            "buyer": BUYER_ADDRESS,
            "provider": PROVIDER_ADDRESS,
            "amount": "1.5",
            "locked_units": 54_000_000,
            "state": "locked",
        }
        ctx = cli_ctx()
        ctx.obj["api_key"] = None
        result, failures = _release(ctx, cli_config(), "e2e_rel_nocreds", amount="1.0")
        assert wired.chain.calls_to("/v1/escrow/release", base=COORDINATOR_URL) == []
        rpc_releases = wired.chain.calls_to("release", base=LOCAL_RPC_URL) + wired.chain.calls_to(
            "release", base=SETTLEMENT_RPC_URL
        )
        assert rpc_releases
        assert result and result.get("tx_hash")
        assert wired.chain.escrows["e2e_rel_nocreds"]["state"] == "released"
