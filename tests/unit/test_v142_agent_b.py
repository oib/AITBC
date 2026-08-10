"""Unit tests for v0.14.2 Agent B TEE CLI and reference enclaves."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _runner_and_cli():
    import sys
    from pathlib import Path

    from click.testing import CliRunner

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from cli.aitbc_cli.core.main import cli

    return CliRunner(), cli


def test_tee_attest_command() -> None:
    runner, cli = _runner_and_cli()
    result = runner.invoke(cli, ["tee", "attest", "enc-1", "--measurement", "m-1"])
    assert result.exit_code == 0
    assert "enc-1" in result.output
    assert "m-1" in result.output


def test_tee_launch_command() -> None:
    runner, cli = _runner_and_cli()
    result = runner.invoke(cli, ["tee", "launch", "enc-2", "--image", "test-image"])
    assert result.exit_code == 0
    assert "enc-2" in result.output
    assert "running" in result.output


def test_tee_verify_command() -> None:
    runner, cli = _runner_and_cli()
    quote = base64.b64encode(b"valid-quote").decode("ascii")
    result = runner.invoke(
        cli,
        ["tee", "verify", "--quote", quote, "--measurement", "m-1", "--mode", "tee_only"],
    )
    assert result.exit_code == 0
    assert "valid" in result.output.lower() or "True" in result.output


def test_confidential_send_command() -> None:
    # The third argument is an amount. It used to be given as "commitment-100", which the
    # old Pedersen code accepted because it hashed the string -- see V23-19a. This test could
    # not report that, because the CLI module has been failing to import since the v0.23
    # remediation commit renamed decrypt_private_key at its call sites only.
    runner, cli = _runner_and_cli()
    result = runner.invoke(
        cli,
        ["confidential", "send", "wallet-1", "recipient-1", "100"],
    )
    assert result.exit_code == 0
    assert "wallet-1" in result.output
    assert "recipient-1" in result.output


def test_confidential_send_rejects_a_non_numeric_amount() -> None:
    runner, cli = _runner_and_cli()
    result = runner.invoke(
        cli,
        ["confidential", "send", "wallet-1", "recipient-1", "commitment-100"],
    )
    assert result.exit_code != 0
    assert "not a decimal number" in result.output


def test_confidential_balance_command() -> None:
    runner, cli = _runner_and_cli()
    result = runner.invoke(cli, ["confidential", "balance", "wallet-1"])
    assert result.exit_code == 0
    assert "wallet-1" in result.output


def test_hipaa_enclave_redacts_phi() -> None:
    from examples.tee.hipaa_enclave.enclave import HIPAAEnclave, PHIRecord

    enclave = HIPAAEnclave("hipaa-1")
    enclave.start()
    record = PHIRecord(patient_id="p-1", data={"ssn": "123", "diagnosis": "x"})
    redacted = enclave.process(record)
    assert redacted["patient_id"] == "p-1"
    assert redacted["ssn"] == "REDACTED"
    assert redacted["diagnosis"] == "REDACTED"


def test_finance_enclave_tokenizes_card() -> None:
    from decimal import Decimal
    from examples.tee.finance_enclave.enclave import FinanceEnclave

    enclave = FinanceEnclave("finance-1")
    enclave.start()
    token = enclave.tokenize("4111111111111111")
    assert token.last_four == "1111"
    assert token.bin_range == "411111"
    assert b"4111111111111111" in token.encrypted_pan
    auth = enclave.authorize(token, Decimal("10.00"))
    assert auth["approved"] is True
