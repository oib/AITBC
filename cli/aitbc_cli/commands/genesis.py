"""Genesis block and wallet generation commands for AITBC CLI"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import click
import httpx

from ..utils import error, genesis_reset, output, success, warning
from ..utils.wallet_secret import resolve_new_wallet_password, wallet_password_options

# Expected failure surface for the genesis handlers below: filesystem/JSON,
# sqlite and HTTP-client errors. BaseExceptions still propagate.
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    sqlite3.Error,
    httpx.HTTPError,
)


@click.group(
    epilog="""Examples:

  aitbc genesis init

  aitbc genesis info --chain-id ait-mainnet"""
)
def genesis():
    """Initialize, verify, and inspect the genesis block, and sync it from the hub."""
    pass


@genesis.command(
    epilog="""Examples:

  aitbc genesis init

  aitbc genesis init --chain-id ait-mainnet"""
)
@click.option("--chain-id", default=None, help="Chain ID for genesis (auto-detected from config if not provided)")
@click.option("--create-wallet", is_flag=True, help="Create the treasury (genesis) wallet with a secure random key")
@click.option("--proposer", help="Proposer address (defaults to the treasury wallet)")
@click.option("--force", is_flag=True, help="Force overwrite existing genesis")
@click.option("--register-service", is_flag=True, help="Register the treasury (genesis) wallet with the wallet service")
@click.option("--service-url", default="http://localhost:8108", help="Wallet service URL")
@wallet_password_options
@click.pass_context
def init(
    ctx,
    chain_id: str,
    create_wallet: bool,
    proposer: str | None,
    force: bool,
    register_service: bool,
    service_url: str,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
):
    """Retired — cannot produce the canonical bc-2 genesis; use scripts/ops/build-genesis.py.

    This command drives the legacy unified_genesis.py builder, whose output
    a bc-2 node would not accept (no canonical state_root or
    bridge-validator digest). It now refuses before reading or writing any
    file. The only builder is apps/blockchain-node/src/aitbc_chain/
    genesis_builder.py, driven by scripts/ops/build-genesis.py — see
    docs/deployment/bc2-consumers.md.
    """
    error(
        "genesis init is retired: it cannot produce the canonical bc-2 "
        "genesis. The only builder is scripts/ops/build-genesis.py "
        "(see docs/deployment/bc2-consumers.md)"
    )
    ctx.exit(1)
    # Auto-detect chain_id from config if not provided
    if not chain_id:
        from ..config import get_config

        config = get_config()
        chain_id = getattr(config, "chain_id", os.getenv("CHAIN_ID", ""))

    # Derived relative to this file rather than hardcoded to /opt/aitbc: the
    # CI runner checks the repo out to its own ephemeral workspace, not /opt/aitbc.
    _repo_root = Path(__file__).resolve().parents[3]
    script_path = _repo_root / "apps/blockchain-node/scripts/unified_genesis.py"

    if not script_path.exists():
        error(f"Genesis generation script not found: {script_path}")
        ctx.exit(1)

    # Build command
    cmd = [sys.executable, str(script_path), "--chain-id", chain_id]

    if create_wallet:
        cmd.append("--create-wallet")

    if proposer:
        cmd.extend(["--proposer", proposer])

    if force:
        cmd.append("--force")

    if register_service:
        cmd.append("--register-service")
        cmd.extend(["--service-url", service_url])

    child_env = dict(os.environ)
    if not create_wallet and (password is not None or password_file or password_stdin):
        error("--password* applies only with --create-wallet")
        ctx.exit(1)
        return
    if create_wallet and (password is not None or password_file or password_stdin):
        child_env["AITBC_GENESIS_PASSWORD"] = resolve_new_wallet_password(
            None,
            password=password,
            password_file=password_file,
            password_stdin=password_stdin,
            interactive_ok=False,
            ctx=ctx,
        )

    try:
        success(f"Running genesis generation for {chain_id}...")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=child_env)
        output(result.stdout, ctx.obj.get("output_format", "table"))
        success("Genesis generation completed successfully")
    except subprocess.CalledProcessError as e:
        error(f"Genesis generation failed: {e.stderr}")
        ctx.exit(1)


@genesis.command(
    epilog="""Examples:

  aitbc genesis verify --chain-id ait-mainnet

  aitbc genesis verify --chain-id ait-mainnet --output json"""
)
@click.option("--chain-id", default=None, help="Chain ID to verify (auto-detected from config if not provided)")
@click.option(
    "--data-dir",
    default="/var/lib/aitbc/data",
    show_default=True,
    help="Data directory holding <chain_id>/genesis.json and chain.db",
)
@click.pass_context
def verify(ctx, chain_id: str, data_dir: str):
    """Verify the genesis block and configuration for a chain."""
    # Auto-detect chain_id from config if not provided
    if not chain_id:
        from ..config import get_config

        config = get_config()
        chain_id = getattr(config, "chain_id", os.getenv("CHAIN_ID", ""))

    genesis_data = _verify_genesis_config(ctx, chain_id, data_dir)
    db_verified, db_genesis_hash = _verify_genesis_db(ctx, chain_id, data_dir)
    verified = genesis_data is not None and db_verified
    if genesis_data is not None:
        verified = _crosscheck_genesis(ctx, chain_id, genesis_data, db_genesis_hash) and verified
    verified = _verify_treasury_wallet(ctx) and verified

    if not verified:
        ctx.exit(1)


def _verify_genesis_config(ctx, chain_id: str, data_dir: str = "/var/lib/aitbc/data") -> dict[str, Any] | None:
    """Check the genesis config file; exits the command on hard failures.

    Returns the parsed document, or None when required fields are missing —
    any parseable JSON used to pass here, so a placeholder file verified
    clean (#2543).
    """
    import json

    # Check genesis config file
    genesis_path = Path(data_dir) / chain_id / "genesis.json"
    if not genesis_path.exists():
        error(f"Genesis config not found: {genesis_path}")
        ctx.exit(1)

    try:
        with open(genesis_path) as f:
            genesis_data: dict[str, Any] = json.load(f)

        success(f"✓ Genesis config found: {genesis_path}")
        # The canonical genesis document carries ``genesis_hash`` at top
        # level and has no ``block`` record — the old ``block.*`` lookups
        # always rendered empty (#2200). ``block.*`` stays as a fallback for
        # legacy documents that did embed one.
        block = genesis_data.get("block") or {}
        output(
            {
                "chain_id": genesis_data.get("chain_id"),
                "genesis_hash": genesis_data.get("genesis_hash") or block.get("hash"),
                "proposer": genesis_data.get("proposer") or block.get("proposer"),
                "allocations_count": len(genesis_data.get("allocations", [])),
            },
            ctx.obj.get("output_format", "table"),
        )

        missing = []
        if not genesis_data.get("chain_id"):
            missing.append("chain_id")
        if not (genesis_data.get("genesis_hash") or block.get("hash")):
            missing.append("genesis_hash")
        if not isinstance(genesis_data.get("allocations"), list):
            missing.append("allocations")
        if missing:
            error(f"Genesis config missing required fields: {', '.join(missing)}")
            return None
        return genesis_data
    except _OPS_ERRORS as e:
        error(f"Failed to read genesis config: {e}")
        ctx.exit(1)
    return None


def _crosscheck_genesis(ctx, chain_id: str, genesis_data: dict[str, Any], db_genesis_hash: str | None) -> bool:
    """Compare the genesis file against the requested chain and the sealed
    block-0 row — file and DB are only trustworthy together (#2543)."""
    ok = True
    file_chain = genesis_data.get("chain_id")
    if file_chain != chain_id:
        error(f"Genesis file chain_id {file_chain!r} does not match requested chain {chain_id!r}")
        ok = False
    file_hash = genesis_data.get("genesis_hash") or (genesis_data.get("block") or {}).get("hash")
    if not file_hash:
        error("Genesis file carries no genesis hash (genesis_hash or block.hash)")
        ok = False
    elif db_genesis_hash and file_hash != db_genesis_hash:
        error(f"Genesis file hash {file_hash} does not match sealed block-0 hash {db_genesis_hash}")
        ok = False
    return ok


def _verify_genesis_db(ctx, chain_id: str, data_dir: str = "/var/lib/aitbc/data") -> tuple[bool, str | None]:
    """Check the genesis block and accounts in the chain database.

    Returns (verified, sealed block-0 hash) so the caller can cross-check it
    against the genesis file (#2543)."""
    import sqlite3

    # Check database (chain-specific path)
    db_path = Path(data_dir) / chain_id / "chain.db"
    if not db_path.exists():
        # Fallback to legacy path
        db_path = Path(data_dir) / "chain.db"
        if not db_path.exists():
            error("Database not found at chain-specific or legacy path")
            ctx.exit(1)

    verified = True
    db_genesis_hash: str | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check genesis block — named columns: the block schema is
        # id, chain_id, height, hash, parent_hash, proposer, ... and the old
        # positional SELECT * indices printed chain_id/height/parent_hash
        # under the height/hash/proposer labels (#2200).
        cursor.execute(
            "SELECT height, hash, proposer FROM block WHERE height=0 AND chain_id=?",
            (chain_id,),
        )
        genesis_block = cursor.fetchone()

        if genesis_block:
            success("✓ Genesis block found in database")
            db_genesis_hash = genesis_block[1]
            output(
                {"height": genesis_block[0], "hash": genesis_block[1], "proposer": genesis_block[2]},
                ctx.obj.get("output_format", "table"),
            )
        else:
            error(f"Genesis block not found in database for chain {chain_id}")
            verified = False

        # Check genesis accounts
        cursor.execute("SELECT COUNT(*) FROM account WHERE chain_id=?", (chain_id,))
        account_count = cursor.fetchone()[0]

        if account_count > 0:
            success(f"✓ Found {account_count} accounts in database")
        else:
            error(f"No accounts found in database for chain {chain_id}")
            verified = False

        conn.close()
    except _OPS_ERRORS as e:
        error(f"Failed to verify database: {e}")
        ctx.exit(1)
    return verified, db_genesis_hash


def _verify_treasury_wallet(ctx) -> bool:
    """Check the treasury (genesis) wallet file."""
    import json

    wallet_path = Path("/var/lib/aitbc/keystore/genesis.json")
    verified = True
    if wallet_path.exists():
        success(f"✓ Treasury (genesis) wallet found: {wallet_path}")
        try:
            with open(wallet_path) as f:
                wallet_data = json.load(f)
            output(
                {
                    "address": wallet_data.get("address"),
                    "public_key": wallet_data.get("public_key")[:16] + "..." if wallet_data.get("public_key") else None,
                },
                ctx.obj.get("output_format", "table"),
            )
        except _OPS_ERRORS as e:
            error(f"Failed to read the treasury (genesis) wallet: {e}")
            verified = False
    else:
        # A missing treasury wallet is normal on follower/customer nodes —
        # only the genesis issuer holds it. Verify's job is chain-state
        # integrity, so absence is a warning, not a failure (#2200).
        warning(f"Treasury (genesis) wallet not found: {wallet_path} (expected only on the genesis-issuer node)")
    return verified


def _sealed_genesis_block(db_path: Path, chain_id: str) -> dict[str, Any] | None:
    """Read block 0 from the chain DB read-only when the genesis file has no block record (CLI-POLISH-1)."""
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT height, hash, parent_hash, proposer, timestamp, tx_count FROM block WHERE height=0 AND chain_id=?",
                (chain_id,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return {
        "height": row[0],
        "hash": row[1],
        "parent_hash": row[2],
        "proposer": row[3],
        "timestamp": str(row[4]) if row[4] is not None else None,
        "tx_count": row[5],
    }


@genesis.command(
    epilog="""Examples:

  aitbc genesis info --chain-id ait-mainnet

  aitbc genesis info --chain-id ait-mainnet --data-dir /var/aitbc"""
)
@click.option(
    "--chain-id", default=None, help="Chain ID to show info for (auto-detected from blockchain node if not provided)"
)
@click.option("--data-dir", default=None, help="Data directory path (default: /var/lib/aitbc/data)")
@click.option(
    "--rpc-url", default=None, help="Blockchain RPC URL for chain ID auto-detection (default: http://localhost:8202)"
)
@click.pass_context
def info(ctx, chain_id: str, data_dir: str | None, rpc_url: str | None):
    """Show the genesis block information for a chain."""
    # Auto-detect chain_id from blockchain node if not provided
    if not chain_id:
        from ..config import get_config
        from ..utils.chain_id import resolve_chain_id as _resolve_chain_id

        config = get_config()

        # Try to get chain_id from RPC health endpoint
        if not rpc_url:
            rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")

        chain_id = _resolve_chain_id(ctx, rpc_url)

    # Use provided data dir or default
    if not data_dir:
        data_dir = "/var/lib/aitbc/data"

    import json

    genesis_path = Path(data_dir) / chain_id / "genesis.json"
    if not genesis_path.exists():
        error(f"Genesis config not found: {genesis_path}")
        error(f"Chain ID: {chain_id}, Data directory: {data_dir}")
        error(f"RPC URL used for detection: {rpc_url}")
        error("Run 'aitbc genesis init' to create genesis block")
        ctx.exit(1)

    try:
        with open(genesis_path) as f:
            genesis_data = json.load(f)

        block = genesis_data.get("block", {})
        allocations = genesis_data.get("allocations", [])

        genesis_block = {
            "height": block.get("height"),
            "hash": block.get("hash"),
            "parent_hash": block.get("parent_hash"),
            "proposer": block.get("proposer"),
            "timestamp": block.get("timestamp"),
            "tx_count": block.get("tx_count"),
        }
        note = None
        if not any(v is not None for v in genesis_block.values()):
            sealed = _sealed_genesis_block(Path(data_dir) / chain_id / "chain.db", chain_id)
            if sealed:
                genesis_block = sealed
            else:
                note = "genesis file carries no block record and block 0 is not sealed in the chain DB yet"

        result: dict[str, Any] = {
            "chain_id": genesis_data.get("chain_id"),
            "genesis_block": genesis_block,
            "allocations": [
                {"address": alloc.get("address"), "balance": alloc.get("balance"), "nonce": alloc.get("nonce")}
                for alloc in allocations[:5]  # Show first 5
            ],
            "total_allocations": len(allocations),
        }
        if note:
            result["note"] = note
        output(result, ctx.obj.get("output_format", "table"))

    except _OPS_ERRORS as e:
        error(f"Failed to read genesis info: {e}")
        ctx.exit(1)


def _validate_synced_genesis(ctx, genesis_data: Any, chain_id: str) -> bool:
    """The synced document must be a complete genesis doc for *chain_id* —
    matching chain id, a genesis hash, and a non-empty allocations list.
    Anything less is a placeholder and is refused (#2542)."""
    if not isinstance(genesis_data, dict):
        error("Hub did not return a genesis document (not a JSON object)")
        return False
    doc_chain = genesis_data.get("chain_id")
    if doc_chain != chain_id:
        error(f"Genesis document chain_id {doc_chain!r} does not match requested chain {chain_id!r}")
        return False
    genesis_hash = genesis_data.get("genesis_hash") or (genesis_data.get("block") or {}).get("hash")
    if not genesis_hash:
        error("Genesis document carries no genesis hash (genesis_hash or block.hash)")
        return False
    allocations = genesis_data.get("allocations")
    if not isinstance(allocations, list) or not allocations:
        error("Genesis document has no allocations — refusing to write a placeholder")
        return False
    return True


def _fetch_genesis_document(ctx, rpc_url: str) -> Any:
    """GET {rpc_url}/agent/genesis.json and return the parsed JSON.

    Exits the command on transport/HTTP errors; the caller validates the
    document itself (#2542)."""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{rpc_url}/agent/genesis.json")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        error(f"Failed to fetch genesis document from hub: HTTP {e.response.status_code}")
        error("The hub must serve the genesis document at /agent/genesis.json")
        ctx.exit(1)
    except httpx.RequestError as e:
        error(f"Failed to connect to hub: {e}")
        ctx.exit(1)
    except _OPS_ERRORS as e:
        error(f"Failed to sync genesis: {e}")
        ctx.exit(1)
    return None


def _write_genesis_atomic(path: Path, genesis_data: dict[str, Any]) -> None:
    """Write the genesis document via temp file + os.replace so an
    interrupted sync never leaves a truncated genesis.json (#2542)."""
    st = path.stat() if path.exists() else None
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".genesis.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(genesis_data, f, indent=2, default=str)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if st is not None:
        try:
            os.chown(path, st.st_uid, st.st_gid)
        except OSError:
            pass


@genesis.command(
    epilog="""Examples:

  aitbc genesis sync-from-hub --chain-id ait-mainnet

  aitbc genesis sync-from-hub --chain-id ait-mainnet --force"""
)
@click.option("--chain-id", default=None, help="Chain ID to sync genesis for (auto-detected from config if not provided)")
@click.option(
    "--rpc-url",
    default=None,
    help="Hub base URL serving /agent/genesis.json (default: blockchain_rpc_url from config)",
)
@click.option("--data-dir", default=None, help="Data directory path (default: /var/lib/aitbc/data)")
@click.option("--force", is_flag=True, help="Force overwrite existing genesis.json")
@click.pass_context
def sync_from_hub(ctx, chain_id: str, rpc_url: str | None, data_dir: str | None, force: bool):
    """Sync the genesis block from the hub for a chain."""
    # Auto-detect chain_id from config if not provided
    if not chain_id:
        from ..config import get_config

        config = get_config()
        chain_id = getattr(config, "chain_id", os.getenv("CHAIN_ID", ""))

    # Auto-detect rpc_url from config if not provided
    if not rpc_url:
        from ..config import get_config

        config = get_config()
        rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")

    # Use provided data dir or default
    if not data_dir:
        data_dir = "/var/lib/aitbc/data"

    genesis_dir = Path(data_dir) / chain_id
    genesis_path = genesis_dir / "genesis.json"

    # Scratch-only reset guard: syncing a genesis file replaces chain state
    # under the data dir, so it shares the guard with the other reset tools.
    try:
        from aitbc.utils import reset_guard
    except ImportError as exc:
        error(f"reset-guard: cannot load aitbc.utils.reset_guard ({exc}) — refusing")
        ctx.exit(1)
    try:
        reset_guard.assert_scratch_targets(genesis_path)
        reset_guard.assert_not_live_chain(chain_id)
    except reset_guard.ResetGuardError as exc:
        error(str(exc))
        ctx.exit(1)

    # Check if genesis.json already exists
    if genesis_path.exists() and not force:
        error(f"Genesis file already exists: {genesis_path}")
        error("Use --force to overwrite")
        ctx.exit(1)

    # Create directory if it doesn't exist
    genesis_dir.mkdir(parents=True, exist_ok=True)

    success(f"Fetching genesis document from hub: {rpc_url}")
    success(f"Chain ID: {chain_id}")

    # The join genesis document is served at /agent/genesis.json on the hub
    # site (docs/agent/guides/open-island-joining-guide.md). The old
    # /rpc/blocks/0 row is NOT a genesis document — it carries no chain_id
    # or allocations, so writing it produced a placeholder that --force
    # could clobber a complete genesis.json with (#2542). Refuse rather
    # than write an unverified document.
    genesis_data = _fetch_genesis_document(ctx, rpc_url)
    if not _validate_synced_genesis(ctx, genesis_data, chain_id):
        ctx.exit(1)

    # --force replaces a complete genesis.json: keep a timestamped copy
    # first so the overwrite stays recoverable (#2542).
    if genesis_path.exists():
        backup = genesis_path.with_name(f"genesis.json.bak-{int(time.time())}")
        shutil.copy2(genesis_path, backup)
        warning(f"Existing genesis file backed up to {backup} before --force overwrite")

    # Write atomically: temp file + os.replace, so an interrupted sync never
    # leaves a truncated genesis.json (#2542).
    _write_genesis_atomic(genesis_path, genesis_data)

    success(f"✓ Genesis synced successfully: {genesis_path}")
    genesis_hash = genesis_data.get("genesis_hash") or (genesis_data.get("block") or {}).get("hash")
    output(
        {
            "chain_id": chain_id,
            "genesis_hash": genesis_hash,
            "timestamp": genesis_data.get("timestamp") or (genesis_data.get("block") or {}).get("timestamp"),
            "file_path": str(genesis_path),
        },
        ctx.obj.get("output_format", "table"),
    )


@genesis.command(
    epilog="""Examples:

  aitbc genesis reset --new-wallet --yes

  aitbc genesis reset --chain-id ait-localnet --new-wallet"""
)
@click.option("--chain-id", default=None, help="Chain ID (defaults to CHAIN_ID env or config)")
@click.option("--new-wallet", is_flag=True, help="Generate a new genesis wallet and update env files")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--data-dir", type=click.Path(), help="Override chain data directory")
@click.option("--etc-dir", type=click.Path(), help="Override env directory")
@click.option("--wallet-dir", type=click.Path(), help="Override wallet directory")
@wallet_password_options
@click.pass_context
def reset(
    ctx,
    chain_id: str,
    new_wallet: bool,
    yes: bool,
    data_dir: str,
    etc_dir: str,
    wallet_dir: str,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
):
    """Reset the local chain: back up old data, generate a new genesis block, and restart services.

    This is a destructive operation. It stops the local blockchain services,
    backs up the chain data and environment, optionally creates a new genesis
    wallet, runs the genesis reset script, and restarts services. Use only when
    the current chain is being intentionally replaced.
    """
    if not chain_id:
        chain_id = os.environ.get("CHAIN_ID", "")
        if not chain_id:
            from ..config import get_config

            chain_id = getattr(get_config(), "chain_id", "")

    if not chain_id:
        error("Could not determine chain ID. Set CHAIN_ID or pass --chain-id.")
        ctx.exit(1)

    if not yes:
        click.confirm(
            f"This will STOP services, BACK UP, and RESET chain {chain_id}.\nContinue?",
            abort=True,
        )

    resolved_password = None
    if password is not None or password_file or password_stdin:
        resolved_password = resolve_new_wallet_password(
            None,
            password=password,
            password_file=password_file,
            password_stdin=password_stdin,
            interactive_ok=False,
            ctx=ctx,
        )

    kwargs: dict[str, Any] = {"output_format": ctx.obj.get("output_format", "table")}
    if data_dir:
        kwargs["data_dir"] = Path(data_dir)
    if etc_dir:
        kwargs["etc_dir"] = Path(etc_dir)
    if wallet_dir:
        kwargs["wallet_dir"] = Path(wallet_dir)

    result = genesis_reset.reset_genesis(
        chain_id=chain_id,
        new_wallet=new_wallet,
        password=resolved_password,
        yes=yes,
        **kwargs,
    )
    if result:
        output(result, ctx.obj.get("output_format", "table"), title="Genesis Reset Summary")
    else:
        ctx.exit(1)
