"""Single wallet-secret input standard for signing commands.

Every command that signs or unlocks a wallet resolves its password through
:func:`resolve_wallet_password` and exposes the same three options via the
:func:`wallet_password_options` decorator. Agents must be able to sign
without a TTY and without the secret appearing in argv, ``ps``, shell
history, logs, or output.

Precedence (highest first):

1. ``--password-stdin`` — one line from stdin (one trailing newline removed)
2. ``--password-file <path>`` — checked file read
3. ``AITBC_WALLET_PASSWORD_FILE`` — checked file read
4. ``AITBC_WALLET_PASSWORD_<NAME>`` / ``AITBC_WALLET_PASSWORD`` — environment
   (inherited by child processes; the file/stdin forms are safer)
5. ``--password <value>`` — deprecated; emits a one-line stderr warning
   because the value is visible in process lists and shell history
6. interactive ``getpass`` prompt — only when a TTY is available and
   ``interactive_ok`` is true

Two explicit flag sources at once (e.g. ``--password`` together with
``--password-file``) are an error, never a guess. When nothing applies and
no TTY exists, the failure message lists the supported ways.

The secret is never printed, logged, echoed, or embedded in an exception
message — error text names paths and problems only.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import click

from .error_handling import abort

ENV_PASSWORD = "AITBC_WALLET_PASSWORD"
ENV_PASSWORD_FILE = "AITBC_WALLET_PASSWORD_FILE"
MAX_PASSWORD_FILE_BYTES = 4096

_PROMPT = "Enter wallet password: "


def _env_password_name(wallet_name: str | None) -> str | None:
    """Per-wallet env var honoured inside the generic env step."""
    if not wallet_name:
        return None
    return f"{ENV_PASSWORD}_{wallet_name.upper()}"


def _strip_one_trailing_newline(text: str) -> str:
    """Remove exactly one trailing newline sequence; keep all other whitespace."""
    if text.endswith("\r\n"):
        return text[:-2]
    if text.endswith("\n"):
        return text[:-1]
    return text


def _read_password_file(path_str: str, ctx=None) -> str:
    """Read a password file after ownership/permission/size checks."""
    path = Path(path_str).expanduser()
    try:
        resolved = path.resolve(strict=True)
        st = resolved.stat()
    except OSError as e:
        abort(ctx, f"Cannot read password file '{path_str}': {e.strerror or 'no such file'}")
        raise  # unreachable: abort always raises
    if not stat.S_ISREG(st.st_mode):
        abort(ctx, f"Password file '{path_str}' is not a regular file")
    if st.st_uid != os.geteuid():
        abort(ctx, f"Password file '{path_str}' is not owned by the current user")
    if st.st_mode & 0o077:
        abort(ctx, f"Password file '{path_str}' is accessible by group or others; run: chmod 600 '{path_str}'")
    if st.st_size > MAX_PASSWORD_FILE_BYTES:
        abort(ctx, f"Password file '{path_str}' is larger than {MAX_PASSWORD_FILE_BYTES} bytes")
    try:
        content = resolved.read_text(encoding="utf-8")
    except OSError as e:
        abort(ctx, f"Cannot read password file '{path_str}': {e.strerror or 'read error'}")
        raise  # unreachable
    except UnicodeDecodeError:
        abort(ctx, f"Password file '{path_str}' is not valid UTF-8")
        raise  # unreachable
    content = _strip_one_trailing_newline(content)
    if not content:
        abort(ctx, f"Password file '{path_str}' is empty")
    return content


def _wallet_is_unencrypted(wallet_name: str, wallet_path: Path | None = None) -> bool:
    """True when the wallet file exists and stores no encrypted key material.

    Keeps the historical ipfs/transactions behaviour: an unencrypted wallet
    needs no password at all. Checks both field shapes the two old resolvers
    used (``encrypted`` and ``encrypted_private_key``).
    """
    try:
        path = wallet_path
        if path is None:
            from .wallet_paths import find_wallet_file

            path = find_wallet_file(wallet_name)
        if path is None or not path.exists():
            return False
        import json

        data = json.loads(Path(path).read_text())
        return not data.get("encrypted") and not data.get("encrypted_private_key")
    except Exception:
        return False


def resolve_wallet_password(
    wallet_name: str | None = None,
    *,
    password: str | None = None,
    password_file: str | None = None,
    password_stdin: bool = False,
    interactive_ok: bool = True,
    allow_unencrypted: bool = False,
    wallet_path: Path | None = None,
    legacy_env_names: tuple[str, ...] = (),
    ctx=None,
) -> str:
    """Resolve the wallet signing password from the standard sources.

    ``interactive_ok`` disables the getpass fallback (batch/agent callers).
    ``allow_unencrypted`` keeps the ipfs/transactions behaviour of accepting
    a wallet file that stores no encrypted key (returns ``""``). The wallet
    name is used for the per-wallet env var, the unencrypted check, and the
    prompt label. ``legacy_env_names`` lists additional env vars consulted in
    the env step for pre-WAL-1 compatibility (e.g. ``WALLET_PASSWORD``).
    """
    explicit = [
        name
        for name, given in (
            ("--password-stdin", password_stdin),
            ("--password-file", password_file),
            ("--password", password is not None),
        )
        if given
    ]
    if len(explicit) > 1:
        abort(ctx, f"Conflicting password sources: {' and '.join(explicit)} — provide only one")

    if password_stdin:
        line = sys.stdin.readline()
        if line == "":
            abort(ctx, "No password on stdin (--password-stdin reads exactly one line)")
        resolved = _strip_one_trailing_newline(line)
        if not resolved:
            abort(ctx, "Empty password on stdin")
        return resolved

    if password_file:
        return _read_password_file(password_file, ctx)

    env_file = os.environ.get(ENV_PASSWORD_FILE)
    if env_file:
        return _read_password_file(env_file, ctx)

    per_name = _env_password_name(wallet_name)
    for var in (per_name, ENV_PASSWORD, *legacy_env_names):
        if var and var in os.environ:
            return os.environ[var]

    # System keyring — pre-existing non-TTY source used by the wallet command
    # group; kept so existing keyring users keep working without flags.
    if wallet_name:
        try:
            import keyring

            kr_password = keyring.get_password("aitbc-wallet", wallet_name)
            if kr_password:
                return kr_password
        except Exception:
            pass

    if password is not None:
        click.echo(
            "warning: --password exposes the secret in process lists and shell history; "
            "prefer --password-stdin or --password-file",
            err=True,
        )
        return password

    if allow_unencrypted and wallet_name and _wallet_is_unencrypted(wallet_name, wallet_path):
        return ""

    if interactive_ok and sys.stdin.isatty():
        import getpass

        prompt = f"Enter password for wallet '{wallet_name}': " if wallet_name else _PROMPT
        try:
            return getpass.getpass(prompt)
        except Exception:
            abort(ctx, "Password prompt failed")
            raise  # unreachable

    abort(
        ctx,
        "No wallet password available and no TTY for a prompt. Provide one via "
        "--password-stdin, --password-file <path>, AITBC_WALLET_PASSWORD_FILE, or "
        "AITBC_WALLET_PASSWORD (or --password <value>, deprecated).",
    )
    raise AssertionError("unreachable")  # abort always raises


def wallet_password_options(func):
    """Click decorator adding the standard ``--password*`` option trio.

    Adds ``--password-stdin``, ``--password-file`` and the deprecated
    ``--password`` so every signing command shows identical help text.
    """
    func = click.option(
        "--password",
        help="Wallet password (deprecated: visible in process lists and shell history; "
        "prefer --password-stdin or --password-file)",
    )(func)
    func = click.option(
        "--password-file",
        type=click.Path(dir_okay=False),
        help="Path to a file containing only the wallet password (mode 0600, owned by you)",
    )(func)
    func = click.option(
        "--password-stdin",
        is_flag=True,
        help="Read the wallet password from one line of standard input",
    )(func)
    return func
