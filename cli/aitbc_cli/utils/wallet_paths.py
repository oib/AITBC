"""Resolve the CLI file-wallet directory.

Service wallets on a node live under ``/var/lib/aitbc/wallets``.  The default
for a normal user is still ``~/.aitbc/wallets``.  The service users
(``aitbc`` and ``aitbc-wallet``) resolve to ``/var/lib/aitbc/wallets`` even when
their interactive ``$HOME`` is ``/home/aitbc`` or similar, so services and
operator shells share one standard.
"""

from __future__ import annotations

import os
import pwd
from dataclasses import dataclass, field
from pathlib import Path

# Service directories searched in addition to the configured wallet_dir.
# The old ``/var/lib/aitbc/.aitbc/wallets`` path is no longer supported.
_SERVICE_WALLET_DIRS = ["/var/lib/aitbc/wallets"]


def _default_wallet_dir() -> Path:
    """Return the default wallet directory for the current user.

    * ``AITBC_WALLET_DIR`` always wins.
    * The ``aitbc`` and ``aitbc-wallet`` system accounts always use
      ``/var/lib/aitbc/wallets``.
    * Any other account keeps the original ``~/.aitbc/wallets`` default.
    """
    home = Path.home()
    if home == Path("/var/lib/aitbc"):
        return home / "wallets"
    try:
        user = pwd.getpwuid(os.getuid()).pw_name
    except (KeyError, OSError):
        user = ""
    if user in ("aitbc", "aitbc-wallet"):
        return Path("/var/lib/aitbc/wallets")
    return home / ".aitbc" / "wallets"


def wallet_dir(override: Path | str | None = None) -> Path:
    """Return the directory that holds ``<name>.json`` file wallets.

    Precedence: explicit *override*, then ``AITBC_WALLET_DIR``, then the
    default home-based wallet directory.
    """
    if override is not None:
        return Path(override)
    env = os.getenv("AITBC_WALLET_DIR")
    if env:
        return Path(env)
    return _default_wallet_dir()


def wallet_search_dirs() -> list[Path]:
    """Return all directories that should be searched for file wallets.

    For load/sign/read paths only: commands that remove, overwrite, re-key
    or export a wallet file (``wallet delete``/``restore``/``import``/
    ``backup``) must keep resolving in the configured ``wallet_dir`` alone —
    a bare name must never reach into the service dir for a destructive act
    (CLI-6 ASK answer). Send/sign commands use this shared order.
    """
    dirs: list[Path] = [wallet_dir()]
    seen = {dirs[0]}
    for candidate in _SERVICE_WALLET_DIRS:
        p = Path(candidate)
        if p not in seen:
            seen.add(p)
            dirs.append(p)
    return dirs


@dataclass
class WalletSearchResult:
    """Outcome of resolving a wallet name across the search directories.

    ``path`` is the winning file (first hit in search order); ``matches``
    lists every directory that also carries a ``<name>.json`` so callers can
    surface ambiguity instead of silently picking one. ``searched`` records
    every directory that was considered and ``unreadable`` those the caller
    cannot read — a service dir that exists but is root-only shows up in the
    error text instead of masquerading as a missing wallet.
    """

    name: str
    path: Path | None
    matches: list[Path] = field(default_factory=list)
    searched: list[Path] = field(default_factory=list)
    unreadable: list[Path] = field(default_factory=list)


def _dir_readable(directory: Path) -> bool:
    return directory.is_dir() and os.access(directory, os.R_OK | os.X_OK)


def find_wallet_file_report(wallet_name: str) -> WalletSearchResult:
    """Resolve ``<wallet_name>.json`` across the search directories with diagnostics."""
    searched: list[Path] = []
    unreadable: list[Path] = []
    matches: list[Path] = []
    for directory in wallet_search_dirs():
        searched.append(directory)
        candidate = directory / f"{wallet_name}.json"
        try:
            exists = candidate.exists()
        except OSError:
            exists = False
        if exists:
            if os.access(candidate, os.R_OK):
                matches.append(candidate)
            else:
                unreadable.append(candidate)
        elif directory.exists() and not _dir_readable(directory):
            unreadable.append(directory)
    return WalletSearchResult(
        name=wallet_name,
        path=matches[0] if matches else None,
        matches=matches,
        searched=searched,
        unreadable=unreadable,
    )


def find_wallet_file(wallet_name: str) -> Path | None:
    """Find a file wallet by name across the configured and service directories."""
    return find_wallet_file_report(wallet_name).path


def is_service_wallet_path(path: Path) -> bool:
    """True when *path* sits inside one of the service wallet directories."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    for candidate in _SERVICE_WALLET_DIRS:
        try:
            base = Path(candidate).resolve()
        except OSError:
            base = Path(candidate).absolute()
        if resolved == base or base in resolved.parents:
            return True
    return False


def service_dir_wallet_note(report: WalletSearchResult, *, explicit: bool = False) -> str | None:
    """``Using wallet file: <path>`` when a name search resolved into a service
    wallet directory — the location an operator least expects a bare name to
    land. ``explicit`` suppresses the note for callers that passed an explicit
    path (``--wallet-path``/``--private-key-file``/``keystore_dir``), per the
    CLI-6 ASK answer: only the path is printed, never file contents.
    """
    if explicit or report.path is None or not is_service_wallet_path(report.path):
        return None
    return f"Using wallet file: {report.path}"


def wallet_not_found_hint(report: WalletSearchResult) -> str:
    """Render the searched-directory block for a failed name resolution.

    Names every directory looked at and marks the ones this caller cannot
    read, so a root-only service dir is distinguishable from a missing wallet.
    Paths only — never file contents.
    """
    parts = []
    for directory in report.searched:
        if directory in report.unreadable:
            parts.append(f"{directory} (unreadable)")
        elif not directory.exists():
            parts.append(f"{directory} (missing)")
        else:
            parts.append(str(directory))
    return "searched: " + ", ".join(parts)


def ambiguous_wallet_note(report: WalletSearchResult) -> str | None:
    """Note to print when the name resolves in more than one directory.

    The first hit in search order wins; the note names the path actually
    used so the choice is visible instead of implicit.
    """
    if len(report.matches) < 2 or report.path is None:
        return None
    return f"wallet '{report.name}' found in multiple directories; using {report.path}"


def wallet_not_found_message(report: WalletSearchResult) -> str:
    """Full operator-facing text for a failed wallet-name resolution."""
    daemon = daemon_keystore_has(report.name)
    lines = [f"Wallet '{report.name}' not found as a file wallet."]
    lines.append("  " + wallet_not_found_hint(report))
    if report.unreadable:
        lines.append("  unreadable: " + ", ".join(str(p) for p in report.unreadable))
    if daemon is True:
        lines.append(
            "  the name exists in the wallet daemon keystore — signing needs a file wallet; pass --wallet-path <file>"
        )
    else:
        lines.append("  pass --wallet-path <file> to point at it directly")
    return "\n".join(lines)


def daemon_keystore_has(wallet_name: str) -> bool | None:
    """True/False when the wallet daemon answers whether it knows the name.

    ``None`` means the daemon could not be asked (unreachable, no config),
    so callers only claim daemon membership on a definite answer. Read-only
    probe with a short timeout — used to explain "wallet list shows it but
    send cannot sign" cases.
    """
    try:
        from ..config import get_config
        from .http_client import AITBCHTTPClient

        config = get_config()
        base_url = getattr(config, "wallet_url", "") or ""
        if not base_url:
            return None
        client = AITBCHTTPClient(
            base_url=base_url.rstrip("/"),
            timeout=2,
            max_retries=0,
            api_key=getattr(config, "wallet_api_key", None),
        )
        data = client.get("/v1/wallets")
        items = (data.get("wallets") or data.get("items") or []) if isinstance(data, dict) else []
        for item in items:
            if wallet_name in (item.get("wallet_id"), item.get("wallet_name")):
                return True
        return False
    except Exception:
        return None
