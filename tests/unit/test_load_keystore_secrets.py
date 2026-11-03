"""UTILS-LOAD-SECRETS-DECRYPT-BRANCH-DEAD-1 — encrypted credentials must decrypt.

load-keystore-secrets.sh decided a credential was encrypted with
``file | grep -q "encrypted"``, but file(1) describes openssl enc output as
"openssl enc'd data with salted password" — the decrypt branch never ran and
ciphertext landed in the env file; ``decrypt || cat`` hid a wrong key the
same way. Encryption is now marked by a ``.enc`` name or the ``Salted__``
openssl magic, and a failed decrypt fails the script loudly.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "utils" / "load-keystore-secrets.sh"

KEY = "a" * 64


def _scratch(tmp_path: Path) -> dict:
    creds = tmp_path / "credentials"
    creds.mkdir()
    (creds / "encryption_key").write_text(KEY + "\n")
    run_dir = tmp_path / "run"
    audit = tmp_path / "audit.log"
    env = {
        "AITBC_CREDENTIALS_DIR": str(creds),
        "AITBC_SECRETS_RUN_DIR": str(run_dir),
        "AITBC_SECRETS_AUDIT_LOG": str(audit),
        "AITBC_BLOCKCHAIN_ENV": str(tmp_path / "no-blockchain.env"),
        "PATH": "/usr/bin:/bin",
    }
    return {"creds": creds, "run_dir": run_dir, "env": env}


def _run(scratch: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=scratch["env"])


def _encrypt(plaintext: str, key: str, out: Path) -> None:
    subprocess.run(
        ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-in", "-", "-out", str(out), "-k", key],
        input=plaintext.encode(),
        check=True,
    )


def _env_value(run_dir: Path, key: str) -> str:
    for line in (run_dir / ".env").read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1]
    raise AssertionError(f"{key} not in env file")


def test_enc_file_by_name_is_decrypted(tmp_path):
    s = _scratch(tmp_path)
    _encrypt("super-secret", KEY, s["creds"] / "api_hash_secret.enc")

    result = _run(s)

    assert result.returncode == 0, result.stderr
    assert _env_value(s["run_dir"], "API_KEY_HASH_SECRET") == "super-secret"


def test_salted_magic_body_is_decrypted_even_without_enc_suffix(tmp_path):
    s = _scratch(tmp_path)
    _encrypt("magic-secret", KEY, s["creds"] / "jwt_secret")

    result = _run(s)

    assert result.returncode == 0, result.stderr
    assert _env_value(s["run_dir"], "JWT_SECRET") == "magic-secret"


def test_undecryptable_enc_file_fails_loudly(tmp_path):
    """A credential marked .enc that openssl cannot decrypt must fail the
    script — the old `decrypt || cat` fallback wrote ciphertext into the env."""
    s = _scratch(tmp_path)
    (s["creds"] / "api_hash_secret.enc").write_bytes(b"definitely-not-openssl-output")

    result = _run(s)

    assert result.returncode != 0
    assert not (s["run_dir"] / ".env").exists() or "super-secret" not in (s["run_dir"] / ".env").read_text()


def test_plaintext_credential_still_loads(tmp_path):
    s = _scratch(tmp_path)
    (s["creds"] / "secret_key").write_text("plain-value")

    result = _run(s)

    assert result.returncode == 0, result.stderr
    assert _env_value(s["run_dir"], "SECRET_KEY") == "plain-value"
