"""#1953 / #1941: parametrized regression pins for gpu-onchain gated /rpc reads."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from click.testing import CliRunner

import aitbc_cli.utils.chain_id as chain_id_mod


def _failing_chain_lookup(rpc_url, override=None, timeout=5, *, strict=False):
    if override:
        return override
    if strict:
        raise chain_id_mod.ChainIdLookupError(f"{rpc_url}: connection refused")
    return ""


@pytest.fixture
def runner():
    return CliRunner()


class TestGpuOnchainRpcAuth:
    """gpu-onchain query/allocations/list must pass blockchain_rpc_api_key to AITBCHTTPClient."""

    def _config_with_key(self):
        return SimpleNamespace(
            blockchain_rpc_url="http://127.0.0.1:1",
            hub_discovery_url="",
            blockchain_rpc_api_key="test-rpc-key",
        )

    def _invoke(self, runner, args):
        from aitbc_cli.commands import gpu_resources as gpu_mod

        ctor_kwargs: dict[str, object] = {}

        class _C:
            def __init__(self, base_url="", **kw):
                ctor_kwargs.update(kw)
                self.base_url = base_url

            def get(self, endpoint, params=None, **kw):
                return {"ok": True}

        with (
            patch("aitbc_cli.commands.gpu_resources.get_config", return_value=self._config_with_key()),
            patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup),
            patch("aitbc_cli.commands.gpu_resources.AITBCHTTPClient", _C),
        ):
            result = runner.invoke(gpu_mod.gpu, args, obj={})
        assert result.exit_code == 0, result.output
        return ctor_kwargs

    @pytest.mark.parametrize(
        "args",
        [
            ["query", "--gpu-id", "gpu-1"],
            ["allocations", "--gpu-id", "gpu-1"],
            ["list"],
        ],
        ids=["query", "allocations", "list"],
    )
    def test_read_commands_send_rpc_api_key(self, runner, args):
        ctor_kwargs = self._invoke(runner, args)
        assert ctor_kwargs.get("api_key") == "test-rpc-key"
