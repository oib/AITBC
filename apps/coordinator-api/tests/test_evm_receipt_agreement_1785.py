"""PaymentService EVM receipt agreement binding (#1785)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from aitbc.market.energy_pricing import FeeModel, SettlementRoute
from aitbc.market.evm_rental_receipt import AGREEMENT_STARTED_TOPIC0
from aitbc_shared import JobPayment
from coordinator_api.contexts.payments.services.payments import PaymentService
from coordinator_api.schemas import JobPaymentCreate


CONTRACT = "0xAIPowerRental00000000000000000000000001"
CHAIN_ID = 11155111


def _agreement_log(agreement_id: int) -> dict:
    topic1 = "0x" + agreement_id.to_bytes(32, "big").hex()
    return {
        "address": CONTRACT,
        "topics": [AGREEMENT_STARTED_TOPIC0, topic1],
        "data": "0x",
    }


def _minimal_quote():
    from aitbc.market.energy_pricing import EnergyQuote

    now = 1_700_000_000
    return EnergyQuote(
        domain="aitbc-energy",
        chain_id="ait-test",
        settlement_asset="AIT",
        settlement_unit_scale=10**18,
        buyer="0xBuyer0000000000000000000000000000000001",
        provider="0xProvider000000000000000000000000000001",
        job_id="job-1",
        quote_id="quote-1",
        settlement_route=SettlementRoute.EVM,
        resource_id="gpu-1",
        model_id="model-a",
        gpu_count=1,
        duration_seconds=3600,
        eur_per_kwh_scaled=10**18,
        tbp_watts=300,
        ait_per_eur_scaled=10**18,
        rate_version=1,
        rate_observed_at=now,
        rate_source_kind="test",
        profile_revision=1,
        evm_chain_id=CHAIN_ID,
        evm_contract=CONTRACT,
        fee_model=FeeModel.BUYER_PAYS_ON_TOP,
        issued_at=now,
        expires_at=now + 300,
        principal_units=10**18,
        net_energy_floor_units=10**18,
    )


@pytest.fixture
def payment_service(db_session):
    return PaymentService(db_session)


def test_verify_receipt_binds_agreement_id(payment_service, db_session) -> None:
    payment = JobPayment(
        job_id="job-1",
        amount=Decimal("1"),
        currency="AITBC",
        payment_method="evm",
        status="pending",
    )
    db_session.add(payment)
    db_session.commit()
    quote = _minimal_quote()
    payment_data = JobPaymentCreate(
        job_id="job-1",
        amount=Decimal("1"),
        currency="AITBC",
        payment_method="evm",
        evm_tx_hash="0xabc",
        evm_agreement_id=99,
        protected=True,
    )
    receipt = {
        "status": 1,
        "to": CONTRACT.lower(),
        "chainId": CHAIN_ID,
        "log_entries": [_agreement_log(99)],
    }
    with patch("coordinator_api.contexts.payments.services.payments.settings") as mock_settings:
        mock_settings.eth_rpc_url = "http://127.0.0.1:8545"
        mock_settings.energy_pricing_chain_id = CHAIN_ID
        with patch("aitbc.ethereum_rpc.EthereumRPCClient.get_transaction_receipt", return_value=receipt):
            payment_service._verify_evm_receipt(payment, payment_data, quote)
    assert payment.status == "confirmed"


def test_verify_receipt_rejects_mismatched_agreement(payment_service, db_session) -> None:
    payment = JobPayment(job_id="job-1", amount=Decimal("1"), currency="AITBC", payment_method="evm")
    db_session.add(payment)
    db_session.commit()
    quote = _minimal_quote()
    payment_data = JobPaymentCreate(
        job_id="job-1",
        amount=Decimal("1"),
        evm_tx_hash="0xabc",
        evm_agreement_id=99,
    )
    receipt = {
        "status": 1,
        "to": CONTRACT.lower(),
        "chainId": CHAIN_ID,
        "log_entries": [_agreement_log(100)],
    }
    with patch("coordinator_api.contexts.payments.services.payments.settings") as mock_settings:
        mock_settings.eth_rpc_url = "http://127.0.0.1:8545"
        mock_settings.energy_pricing_chain_id = CHAIN_ID
        with patch("aitbc.ethereum_rpc.EthereumRPCClient.get_transaction_receipt", return_value=receipt):
            with pytest.raises(HTTPException) as exc:
                payment_service._verify_evm_receipt(payment, payment_data, quote)
    assert exc.value.status_code == 422
    assert payment.status == "failed"


def test_verify_receipt_rejects_missing_agreement_log(payment_service, db_session) -> None:
    payment = JobPayment(job_id="job-1", amount=Decimal("1"), currency="AITBC", payment_method="evm")
    db_session.add(payment)
    db_session.commit()
    quote = _minimal_quote()
    payment_data = JobPaymentCreate(
        job_id="job-1",
        amount=Decimal("1"),
        evm_tx_hash="0xabc",
        evm_agreement_id=1,
    )
    receipt = {"status": 1, "to": CONTRACT.lower(), "chainId": CHAIN_ID, "log_entries": []}
    with patch("coordinator_api.contexts.payments.services.payments.settings") as mock_settings:
        mock_settings.eth_rpc_url = "http://127.0.0.1:8545"
        mock_settings.energy_pricing_chain_id = CHAIN_ID
        with patch("aitbc.ethereum_rpc.EthereumRPCClient.get_transaction_receipt", return_value=receipt):
            with pytest.raises(HTTPException):
                payment_service._verify_evm_receipt(payment, payment_data, quote)
    assert payment.status == "failed"
