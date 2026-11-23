"""Regression pin for #2739 — LIQUIDITY_WITHDRAW/CLAIM signature rejection.

``TransactionRequest.validate_payload`` injects ``payload.amount`` from the
top-level ``amount`` when the payload lacks it. For liquidity withdraw/claim
the top-level amount is intentionally 0 (payout is pool-state), so a client
that omits ``payload.amount`` signs one message while the node verifies
another — submit then 403s with the misleading "Invalid transaction
signature". These pins lock in both halves: the injection really does break
the signature, and a payload that carries ``amount`` verifies cleanly.
"""

from eth_keys import keys

from aitbc_chain.rpc.transactions import TransactionRequest
from aitbc_chain.rpc.utils import sign_transaction_data, verify_transaction_signature

_PRIV = "0x" + "11" * 32
_SENDER = keys.PrivateKey(bytes.fromhex(_PRIV[2:])).public_key.to_checksum_address()
_ADDR = "0x" + "22" * 20
_CHAIN = "bc-2"


def _cli_shaped_tx(payload: dict) -> dict:
    """The dict ``wallet liquidity-unstake``/``liquidity-claim`` signs."""
    return {
        "type": "LIQUIDITY_WITHDRAW",
        "from": _SENDER,
        "to": _ADDR,
        "amount": 0,
        "fee": 1000,
        "nonce": 7,
        "chain_id": _CHAIN,
        "payload": payload,
    }


def _submit_verify_path(tx: dict) -> bool:
    """Replicate submit_transaction's model validation + verify call."""
    req = TransactionRequest.model_validate({**tx, "signature": tx["signature"]})
    tx_data_dict = {
        "from": req.sender,
        "to": req.recipient,
        "amount": req.amount,
        "fee": req.fee,
        "nonce": req.nonce,
        "payload": req.payload,
        "type": req.type,
        "chain_id": _CHAIN,
        "signature": req.sig,
    }
    return verify_transaction_signature(tx_data_dict, req.sig, req.sender)


def test_payload_amount_omitted_breaks_signature():
    """The #2739 trap: signing without payload.amount, then letting the node
    inject amount=0, must fail verification — this is what produced the 403."""
    tx = _cli_shaped_tx({"pool_id": "default", "stake_id": "liq_x", "to": _ADDR})
    tx["signature"] = sign_transaction_data(tx, _PRIV)

    req = TransactionRequest.model_validate(tx)
    assert req.payload["amount"] == 0  # injected post-sign
    assert _submit_verify_path(tx) is False


def test_payload_amount_present_verifies():
    """With payload.amount in the signed payload the node verifies the same
    message the client signed."""
    tx = _cli_shaped_tx({"pool_id": "default", "stake_id": "liq_x", "to": _ADDR, "amount": 18000000})
    tx["signature"] = sign_transaction_data(tx, _PRIV)

    req = TransactionRequest.model_validate(tx)
    assert req.payload["amount"] == 18000000  # not overwritten
    assert _submit_verify_path(tx) is True
