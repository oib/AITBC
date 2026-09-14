"""Shared asyncpg/libpq-style sslmode resolution for AITBC services.

Moved out of ``apps/governance/.../storage.py`` so every service that builds an
asyncpg engine gets the same TLS behaviour instead of each carrying its own
copy (or, like pool-hub before this, none at all).
"""

from __future__ import annotations

import os
import ssl

# libpq sslmode values, in the order libpq defines them. Anything else is a
# configuration error rather than something to guess at.
SSLMODES_WITHOUT_VERIFICATION = ("allow", "prefer", "require")
SSLMODES_WITH_VERIFICATION = ("verify-ca", "verify-full")


def resolve_sslmode() -> str:
    """Return the configured sslmode, defaulting to asyncpg's own default."""
    for var in ("DB_SSLMODE", "PGSSLMODE"):
        value = os.getenv(var)
        if value:
            return value.strip().lower().replace("_", "-")
    return "prefer"


def build_ssl_arg() -> ssl.SSLContext | bool:
    """Resolve the `ssl` connect argument handed to asyncpg.

    `DB_SSLMODE` wins, then the libpq-standard `PGSSLMODE`, else `prefer` --
    asyncpg's own default, so a host that configures neither keeps the behaviour
    it has today.

    The reason this builds an `SSLContext` instead of just forwarding the mode
    *string* asyncpg would happily parse: for every mode above `disable`, asyncpg
    resolves `~/.postgresql/root.crl` and `~/.postgresql/postgresql.key` itself
    (`connect_utils._dot_postgresql_path`), and it guards those lookups against
    FileNotFoundError but not PermissionError. Units run under `ProtectHome=yes`,
    so wherever the service user's home sits under /home that lookup raises EACCES
    and the connection dies before it is ever attempted -- an outage whose only
    visible symptom is that the database is unreachable while the database is
    perfectly healthy. The workaround is `PGSSLMODE=disable` in the environment,
    which is a poor place for it: it is invisible to the repo, it silently costs
    the encryption, and any redeploy that loses the line re-arms the fault.
    Supplying the context here means the home directory is never consulted,
    whatever HOME happens to be, and the setting travels with the code.

    One deliberate behaviour change comes with that: asyncpg treats `prefer` as
    advisory and falls back to an unencrypted connection when the server refuses
    TLS. A caller-supplied context gets no such fallback, so `prefer` against a
    server with `ssl = off` now fails loudly instead of quietly downgrading. A
    deployment that really does want plaintext has to say `DB_SSLMODE=disable`
    and mean it, which is the right way round for a security default.
    """
    mode = resolve_sslmode()
    if mode == "disable":
        return False
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if mode in SSLMODES_WITHOUT_VERIFICATION:
        # Encrypt, but do not authenticate the server -- libpq's semantics for
        # these three, and what asyncpg does with them. check_hostname must go
        # first: CERT_NONE while it is still True raises ValueError.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    elif mode in SSLMODES_WITH_VERIFICATION:
        context.check_hostname = mode == "verify-full"
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_default_certs(ssl.Purpose.SERVER_AUTH)
    else:
        supported = ("disable", *SSLMODES_WITHOUT_VERIFICATION, *SSLMODES_WITH_VERIFICATION)
        raise ValueError(f"Unsupported sslmode {mode!r}; expected one of: {', '.join(supported)}")
    return context
