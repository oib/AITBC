"""Genesis service accounts, and the guard that keeps derivable keys out of them.

Several generator scripts used to allocate the platform's service accounts at
addresses derived as ``sha256(name)`` -- see :func:`derive_address`. That makes
the private key a pure function of a name published in this repository, so every
such account is spendable by anyone who can read the source. It is a usable
convenience for a throwaway devnet and a full compromise anywhere else.

This module holds the canonical name list, the derivation (kept, but marked and
centralised), and :func:`find_derived`, which every genesis writer calls before
it commits an allocation set. Generators now mint real keypairs with
:func:`new_account` and persist them through whatever custody the caller already
uses.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterable

# The service accounts a production genesis pre-funds. Order is the historical
# allocation order; callers that care about balances keep their own mapping.
SERVICE_ACCOUNT_NAMES: tuple[str, ...] = (
    "aitbc1aiengine",
    "aitbc1surveillance",
    "aitbc1analytics",
    "aitbc1marketplace",
    "aitbc1enterprise",
    "aitbc1multimodal",
    "aitbc1zkproofs",
    "aitbc1crosschain",
    "aitbc1developer1",
    "aitbc1developer2",
    "aitbc1tester",
)

# Every name that has ever been fed to derive_address() by a genesis writer.
# The guard checks against all of them, not just the ones still in use, so an
# allocation set carried over from an older chain is still caught.
LEGACY_DERIVED_NAMES: tuple[str, ...] = (
    "aitbc1genesis",
    "aitbc1treasury",
    *SERVICE_ACCOUNT_NAMES,
)


def derive_address(name: str) -> str:
    """Return the EIP-55 address of the key ``sha256(name)``.

    **The private key is public.** ``name`` is a constant in this repository, so
    anyone can reproduce the key in two lines. Never allocate balance to the
    result outside a disposable local chain; use :func:`new_account` instead.
    Retained so :func:`find_derived` can recognise the addresses already in use.
    """
    from eth_account import Account

    return Account.from_key(hashlib.sha256(name.encode()).digest()).address


def new_account() -> tuple[str, str]:
    """Mint a fresh keypair. Returns ``(private_key_hex, address)``."""
    from eth_account import Account

    private_hex = secrets.token_hex(32)
    return private_hex, Account.from_key(private_hex).address


def derived_addresses() -> dict[str, str]:
    """Map every known derivable address (lower-case) to the name behind it."""
    return {derive_address(n).lower(): n for n in LEGACY_DERIVED_NAMES}


def find_derived(addresses: Iterable[str]) -> list[tuple[str, str]]:
    """Return ``(address, name)`` for each input address with a derivable key.

    Empty means the allocation set is clean. Comparison is case-insensitive so
    a set that lost its EIP-55 checksum casing in transit is still caught.
    """
    known = derived_addresses()
    found: list[tuple[str, str]] = []
    for address in addresses:
        name = known.get(str(address).lower())
        if name is not None:
            found.append((str(address), name))
    return found


def derived_key_error(found: list[tuple[str, str]], *, override: str) -> str:
    """Build the refusal message for an allocation set that failed the guard.

    ``override`` is the escape hatch the calling script offers -- a ``--flag``
    for the CLI entry points, an environment variable name for the rest.
    """
    escape = f"pass {override}" if override.startswith("-") else f"set {override}=1"
    lines = [
        f"refusing to write genesis: {len(found)} account(s) have publicly derivable private keys.",
        "",
        "These addresses are sha256(name) keys. The name is a constant in this",
        "public repository, so anyone can compute the key and spend the balance:",
        "",
    ]
    lines += [f"    {address}  <- sha256({name!r})" for address, name in found]
    lines += [
        "",
        f"Mint real keys instead, or {escape} for a disposable local chain.",
    ]
    return "\n".join(lines)
