"""Unit tests for v0.14.2 Agent B TEE CLI and reference enclaves."""

from __future__ import annotations

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
