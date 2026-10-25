"""OPS-NOISE-2: designed escrow refusals log at WARNING, not ERROR.

A node without a settlement key *must* refuse settlement ops — that is a
designed refusal, not a fault. Logging it at ERROR made every such refusal
fire AITBCJournalErrors; the response (503) is unchanged either way.
"""

import logging

import pytest
from fastapi import HTTPException

from aitbc_chain.rpc import escrow_routes


@pytest.fixture
def _no_settlement_key(monkeypatch):
    monkeypatch.setattr(escrow_routes, "_ESCROW_RELEASE_PRIVATE_KEY", "")
    monkeypatch.setattr(escrow_routes, "_GENESIS_WALLET_PRIVATE_KEY", "")
    monkeypatch.setattr(escrow_routes, "_ESCROW_RELEASE_ADDRESS", "")


def test_refusal_logs_warning_not_error(_no_settlement_key, caplog):
    with caplog.at_level(logging.WARNING, logger=escrow_routes._logger.name):
        with pytest.raises(HTTPException) as exc:
            escrow_routes._require_settlement_signing("job_1", "ESCROW_RELEASE")
    assert exc.value.status_code == 503
    assert "Settlement key/address is not configured correctly" in exc.value.detail
    recs = [r for r in caplog.records if "refusing job_id=job_1" in r.getMessage()]
    assert len(recs) == 1
    assert recs[0].levelno == logging.WARNING


def test_ready_node_logs_nothing(_no_settlement_key, monkeypatch, caplog):
    monkeypatch.setattr(escrow_routes, "_settlement_signing_ready", lambda: True)
    with caplog.at_level(logging.WARNING, logger=escrow_routes._logger.name):
        escrow_routes._require_settlement_signing("job_1", "ESCROW_RELEASE")
    assert not [r for r in caplog.records if "refusing" in r.getMessage()]
