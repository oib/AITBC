"""#2756: _AIPOWER_RENTAL_ABI must match the deployed contract's real signature.

Two failure classes hit this ABI on the live Sepolia deployment:

1. A phantom ``performance`` tuple component (no ``components``) — web3>=7
   parses output types strictly and died with ``KeyError: components``
   while ``createRental`` had already sealed on-chain.
2. The respin's single-tuple output still died with
   ``BadFunctionCallOutput``: the deployed struct contains a dynamic member
   (``gpuModel`` string) and the chain returns the struct head inline
   *without* the outer tuple offset that eth_abi tuple decoding expects.
   Flat outputs decode the identical 12 fields in the identical order.

These pins keep the ABI honest: every tuple is well-formed, and the
getRentalAgreement outputs equal the contract signature field-for-field.
"""

from __future__ import annotations

from aitbc_cli.utils.evm_contract import _AIPOWER_RENTAL_ABI

_EXPECTED_OUTPUTS = [
    ("agreementId", "uint256"),
    ("provider", "address"),
    ("consumer", "address"),
    ("duration", "uint256"),
    ("price", "uint256"),
    ("startTime", "uint256"),
    ("endTime", "uint256"),
    ("platformFee", "uint256"),
    ("status", "uint8"),
    ("gpuModel", "string"),
    ("computeUnits", "uint256"),
    ("performanceProof", "bytes32"),
]


def _func_abi(name: str) -> dict:
    for entry in _AIPOWER_RENTAL_ABI:
        if entry.get("type") == "function" and entry.get("name") == name:
            return entry
    raise AssertionError(f"{name} not in _AIPOWER_RENTAL_ABI")


def test_every_tuple_type_declares_components() -> None:
    """web3>=7 requires components on every tuple — recursively."""

    def check(param: dict) -> None:
        if param.get("type") == "tuple":
            assert param.get("components"), f"tuple {param.get('name')} missing components"
            for comp in param["components"]:
                check(comp)
        elif param.get("type", "").startswith("tuple["):
            for comp in param.get("components") or []:
                check(comp)

    for entry in _AIPOWER_RENTAL_ABI:
        for param in entry.get("inputs", []) + entry.get("outputs", []):
            check(param)


def test_get_rental_agreement_outputs_match_contract() -> None:
    """12 flat outputs — the encoding the deployed contract actually returns."""
    fn = _func_abi("getRentalAgreement")
    outputs = fn["outputs"]
    assert all(o["type"] != "tuple" for o in outputs), (
        "tuple output breaks web3 decode of the deployed contract's inline struct head"
    )
    assert [(o["name"], o["type"]) for o in outputs] == _EXPECTED_OUTPUTS
    assert "performance" not in [o["name"] for o in outputs]
