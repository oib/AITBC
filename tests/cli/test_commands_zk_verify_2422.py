"""#2422 pins: ``zk verify --job-id`` must use the job-bound receipt route.

The generic ``/v1/zk/verify`` refuses receipt circuits because
caller-supplied public signals cannot bind a proof to stored job state;
the documented verify step therefore has to POST ``{"job_id": ...}`` to
``/v1/zk/receipt/verify`` and let the server re-derive the signals.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _invoke_verify(runner, args, post_return=None):
    from aitbc_cli.commands import zk as zk_mod

    mock_client = MagicMock()
    mock_client.post.return_value = post_return if post_return is not None else {"verified": True}
    mock_client.get.return_value = {"receipt": {"zk_proof": {"proof": {}, "public_signals": {}}}}

    config = SimpleNamespace(coordinator_api_url="http://coord.example", api_key=None)
    with (
        patch.object(zk_mod, "get_config", return_value=config),
        patch.object(zk_mod, "auth_client_kwargs", return_value={}),
        patch.object(zk_mod, "AITBCHTTPClient", return_value=mock_client),
    ):
        result = runner.invoke(zk_mod.zk, ["verify", *args, "--format", "json"])
    return result, mock_client


class TestZkVerifyJobId:
    def test_job_id_posts_to_receipt_verify(self, runner):
        result, client = _invoke_verify(runner, ["--job-id", "job-abc"])

        assert result.exit_code == 0, result.output
        client.post.assert_called_once_with("/v1/zk/receipt/verify", json={"job_id": "job-abc"})
        # The old flow fetched the receipt then posted proof+signals to
        # /v1/zk/verify — both calls must be gone.
        client.get.assert_not_called()

    def test_job_id_does_not_hit_generic_verify(self, runner):
        result, client = _invoke_verify(runner, ["--job-id", "job-abc"])

        assert result.exit_code == 0, result.output
        for call in client.post.call_args_list:
            assert call.args[0] != "/v1/zk/verify"

    def test_proof_signals_still_use_generic_verify(self, runner):
        result, client = _invoke_verify(
            runner,
            ["--proof", '{"a": 1}', "--public-signals", '{"x": 2}', "--circuit", "poseidon"],
        )

        assert result.exit_code == 0, result.output
        client.post.assert_called_once()
        args, kwargs = client.post.call_args
        assert args[0] == "/v1/zk/verify"
        assert kwargs["json"]["circuit_name"] == "poseidon"
        assert kwargs["json"]["proof"] == {"a": 1}

    def test_job_id_output_is_verification_response(self, runner):
        result, _client = _invoke_verify(runner, ["--job-id", "job-abc"], post_return={"verified": True, "reason": "ok"})

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output[result.output.index("{"):])
        assert payload["verified"] is True
