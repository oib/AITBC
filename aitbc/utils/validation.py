"""AITBC shared validation helpers."""


def validate_address_strict(address: str) -> bool:
    """Return True if the address looks like an AITBC bech32 address."""
    if not isinstance(address, str):
        return False
    return address.startswith("ait1") and len(address) >= 38
