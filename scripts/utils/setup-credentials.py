#!/usr/bin/env python3
"""
Setup systemd credentials for AITBC services
Stores secrets in /etc/aitbc/credentials with proper permissions

A rerun never rotates an already-installed secret: existing credential files
are skipped unless --rotate is passed, and new files are written O_EXCL 0600.
"""

import argparse
import os
from pathlib import Path
from secrets import token_hex


def _write_credential(cred_file: Path, value: str, rotate: bool) -> str:
    """Write ``value`` to ``cred_file`` O_EXCL 0600; returns a status word."""
    flags = os.O_WRONLY | os.O_CREAT
    if not rotate:
        flags |= os.O_EXCL
    try:
        fd = os.open(cred_file, flags, 0o600)
    except FileExistsError:
        return "kept"
    with os.fdopen(fd, "w") as f:
        f.write(value)
    os.chmod(cred_file, 0o600)
    return "rotated" if rotate else "created"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rotate",
        action="store_true",
        help="Overwrite credential files that already exist (default: keep them)",
    )
    parser.add_argument("--credentials-dir", type=Path, default=Path("/etc/aitbc/credentials"))
    parser.add_argument("--env-file", type=Path, default=Path("/etc/aitbc/blockchain.env"))
    args = parser.parse_args(argv)

    credentials_dir = args.credentials_dir
    credentials_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(credentials_dir, 0o700)

    env_file = args.env_file

    # Read current .env values
    env_vars = {}
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()

    # Create credential files for sensitive values. Generated secrets are only
    # produced when the env file lacks the value AND no credential file exists
    # yet — a rerun must not change a secret the first run installed.
    credentials = {
        "api_hash_secret": env_vars.get("API_KEY_HASH_SECRET"),
        "proposer_id": env_vars.get("PROPOSER_ID", ""),
        "keystore_password": env_vars.get("KEYSTORE_PASSWORD"),
    }

    for name, value in credentials.items():
        cred_file = credentials_dir / name
        if value is None:
            if cred_file.exists() and not args.rotate:
                print(f"Kept credential:    {cred_file} (exists, use --rotate to replace)")
                continue
            value = token_hex(32)
        if not value:
            continue
        status = _write_credential(cred_file, value, args.rotate)
        if status == "kept":
            print(f"Kept credential:    {cred_file} (exists, use --rotate to replace)")
        else:
            print(f"{status.capitalize()} credential: {cred_file}")

    print(f"\nCredentials stored in: {credentials_dir}")
    print("All files have 600 permissions (root read/write only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
