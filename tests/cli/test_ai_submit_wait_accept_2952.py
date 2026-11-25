"""#2952: ``aitbc ai submit --wait`` must not fire accept while the escrow is
still sealing, and must retry the accept once the payment reaches
``pending_acceptance`` instead of warning once and never trying again.
"""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from aitbc_cli.utils.http_client import NetworkError


@pytest.fixture
def runner():
    return CliRunner()


class _HttpCause(Exception):
    """Exception carrying a ``.response`` like requests.HTTPError."""

    def __init__(self, status_code: int, body: dict) -> None:
        super().__init__(f"{status_code} Error")
        self.response = Mock(status_code=status_code)
        self.response.json.return_value = body


def _accept_not_ready_error() -> NetworkError:
    """The coordinator's 409 while payment_status is still ``escrowed``."""
    err = NetworkError("409 Client Error")
    err.__cause__ = _HttpCause(409, {"detail": "job has no payment awaiting acceptance (payment_status=escrowed)"})
    return err


def _drive_wait(mock_client, job_polls: list[dict], accept_side_effect=None):
    """Wire GET /v1/jobs/{id} polls and POST routes for a --wait submit."""
    polls = iter(job_polls)

    def _get(path, **_kwargs):
        if path == "/v1/jobs/job_123/result":
            return {"result": "ok", "receipt": {"tx_hash": "0xabc"}}
        if path == "/v1/jobs/job_123/payment":
            return {"escrow_tx_hash": "0xlock"}
        return next(polls)

    accept_calls = []

    def _post(path, **_kwargs):
        if path == "/v1/jobs":
            return {"job_id": "job_123", "payment_id": "pay_1", "status": "queued"}
        if path == "/v1/jobs/job_123/accept":
            accept_calls.append(path)
            if accept_side_effect is not None:
                return accept_side_effect(len(accept_calls))
            return {"job_id": "job_123"}
        raise AssertionError(f"unexpected POST {path}")

    mock_client.get.side_effect = _get
    mock_client.post.side_effect = _post
    return accept_calls


class TestAutoAcceptEscrowRace:
    @patch("aitbc_cli.commands.ai.AITBCHTTPClient")
    @patch("aitbc_cli.commands.ai.get_config")
    def test_escrowed_payment_status_does_not_fire_accept(self, mock_get_config, mock_http_class, runner, mock_config):
        """payment_status=escrowed is seal/release latency — accept must wait."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        accept_calls = _drive_wait(
            mock_client,
            [
                {"state": "QUEUED", "job_id": "job_123"},
                {"state": "COMPLETED", "job_id": "job_123", "payment_status": "escrowed"},
                {"state": "COMPLETED", "job_id": "job_123", "payment_status": "released"},
            ],
        )

        from aitbc_cli.commands.ai import ai

        result = runner.invoke(
            ai,
            ["submit", "--wait", "--timeout", "10", "--poll-interval", "0.01", "--prompt", "hello"],
        )

        assert result.exit_code == 0, result.output
        assert accept_calls == []
        assert "Could not auto-accept" not in result.output

    @patch("aitbc_cli.commands.ai.AITBCHTTPClient")
    @patch("aitbc_cli.commands.ai.get_config")
    def test_not_ready_409_is_retried_once_pending_acceptance(self, mock_get_config, mock_http_class, runner, mock_config):
        """A 409 'no payment awaiting acceptance' retries on the next poll."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value

        def _accept(n: int):
            if n == 1:
                raise _accept_not_ready_error()
            return {"job_id": "job_123"}

        accept_calls = _drive_wait(
            mock_client,
            [
                {"state": "QUEUED", "job_id": "job_123"},
                {"state": "COMPLETED", "job_id": "job_123", "payment_status": "pending_acceptance"},
                {"state": "COMPLETED", "job_id": "job_123", "payment_status": "pending_acceptance"},
                {"state": "COMPLETED", "job_id": "job_123", "payment_status": "released"},
            ],
            accept_side_effect=_accept,
        )

        from aitbc_cli.commands.ai import ai

        result = runner.invoke(
            ai,
            ["submit", "--wait", "--timeout", "10", "--poll-interval", "0.01", "--prompt", "hello"],
        )

        assert result.exit_code == 0, result.output
        assert len(accept_calls) == 2
        assert "Could not auto-accept" not in result.output
