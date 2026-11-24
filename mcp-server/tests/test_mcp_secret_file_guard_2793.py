"""AUDIT-EDGE-MCP-SECRET-FILE-READ (#2793): ``_read_secret_file`` read any
path on the MCP host — ``~/.ssh/id_rsa``, ``~/.git-credentials`` — and
forwarded the content to the node's market service. Credential-store paths
are now refused and reads are size-capped.
"""

import json
import sys
from pathlib import Path

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_rpc_tools as rpc_tools


def test_read_secret_file_refuses_ssh_key(tmp_path, monkeypatch):
    home = tmp_path / "home"
    key = home / ".ssh" / "id_rsa"
    key.parent.mkdir(parents=True)
    key.write_text("PRIVATE KEY MATERIAL")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    content, error = rpc_tools._read_secret_file(str(key))
    assert content is None
    assert "refusing" in error


def test_read_secret_file_refuses_git_credentials(tmp_path, monkeypatch):
    home = tmp_path / "home"
    cred = home / ".git-credentials"
    cred.parent.mkdir(parents=True)
    cred.write_text("https://user:tok@host")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    content, error = rpc_tools._read_secret_file(str(cred))
    assert content is None
    assert "refusing" in error


def test_read_secret_file_refuses_aws_credentials_dir(tmp_path, monkeypatch):
    home = tmp_path / "home"
    cred = home / ".aws" / "credentials"
    cred.parent.mkdir(parents=True)
    cred.write_text("[default]")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    content, error = rpc_tools._read_secret_file(str(cred))
    assert content is None
    assert "refusing" in error


def test_read_secret_file_allows_operator_secret(tmp_path):
    secret = tmp_path / "rental-secret"
    secret.write_text("s3cr3t-value\n")
    content, error = rpc_tools._read_secret_file(str(secret))
    assert error is None
    assert content == "s3cr3t-value"


def test_read_secret_file_refuses_oversized(tmp_path):
    big = tmp_path / "big-secret"
    big.write_bytes(b"x" * (rpc_tools._SECRET_FILE_MAX_BYTES + 1))
    content, error = rpc_tools._read_secret_file(str(big))
    assert content is None
    assert "exceeds" in error


def test_ipfs_rental_token_tool_surfaces_refusal(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh" / "id_rsa").write_text("KEY")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    out = json.loads(
        rpc_tools.get_ipfs_rental_token(access_key="ak", access_secret_file=str(home / ".ssh" / "id_rsa"), role="hub")
    )
    assert "refusing" in out.get("error", "")
