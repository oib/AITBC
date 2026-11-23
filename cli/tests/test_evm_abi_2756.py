"""#2756: _AIPOWER_RENTAL_ABI must match the deployed contract's real signature.

The hand-written ABI declared a `performance` tuple component on
getRentalAgreement's outputs — but the contract's function returns 12
values and omits PerformanceMetrics entirely (split to getRentalPerformance
in adf9d808b to dodge stack-too-deep). web3>=7 parses output types strictly
at .call() time and died with KeyError: components — a phantom-failure
class: createRental sealed on-chain while the CLI reported an error.

These pins keep the ABI honest: every tuple is well-formed, and the
getRentalAgreement output list equals the contract signature field-for-field.
"""

from __future__ import annotations

from aitbc_cli.utils.evm_contract import _AIPOWER_RENTAL_ABI


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
    """The contract returns 12 fields; performance lives on getRentalPerformance."""
    fn = _func_abi("getRentalAgreement")
    out = fn["outputs"][0]
    assert out["type"] == "tuple"
    names = [c["name"] for c in out["components"]]
    types = [c["type"] for c in out["components"]]
    assert names == [
        "agreementId",
        "provider",
        "consumer",
        "duration",
        "price",
        "startTime",
        "endTime",
        "platformFee",
        "status",
        "gpuModel",
        "computeUnits",
        "performanceProof",
    ]
    assert types == [
        "uint256",
        "address",
        "address",
        "uint256",
        "uint256",
        "uint256",
        "uint256",
        "uint256",
        "uint8",
        "string",
        "uint256",
        "bytes32",
    ]
    assert "performance" not in names
