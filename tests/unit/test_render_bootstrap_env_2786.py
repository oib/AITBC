"""#2786: render-bootstrap-env.sh must strip inline comments and validate
charset before publishing allowlisted values into bootstrap.env."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "render-bootstrap-env.sh"
TEMPLATE = REPO_ROOT / "examples" / "blockchain.env.open-island"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None or not TEMPLATE.exists(), reason="needs bash + template")


@pytest.fixture
def harness(tmp_path: Path) -> dict:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # install -m 0644 -o root -g root <src> <dst> — last two args win
    stub = bindir / "install"
    stub.write_text('#!/bin/bash\ncp "${@: -2:1}" "${@: -1}"\n')
    stub.chmod(0o755)
    src_env = tmp_path / "blockchain.env"
    out = tmp_path / "bootstrap.env"
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "TEMPLATE": str(TEMPLATE),
        "SOURCE_ENV": str(src_env),
        "OUT": str(out),
    }
    return {"src_env": src_env, "out": out, "env": env}


def _run(h: dict, env_lines: str) -> subprocess.CompletedProcess[str]:
    h["src_env"].write_text(env_lines)
    return subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=h["env"], timeout=30)


def test_inline_comment_is_stripped_from_published_value(harness: dict) -> None:
    result = _run(
        harness,
        "CHAIN_ID=bc-2 # island chain note\nFOLLOWER_API_KEY=abc123XYZ_-\n",
    )
    assert result.returncode == 0, result.stderr
    published = harness["out"].read_text()
    assert "CHAIN_ID=bc-2\n" in published
    assert "# island chain note" not in published


def test_hostile_value_is_refused(harness: dict) -> None:
    result = _run(harness, "CHAIN_ID=bc-2;rm -rf /\n")
    assert result.returncode != 0
    assert "Invalid CHAIN_ID" in result.stderr
    assert not harness["out"].exists() or "rm -rf" not in harness["out"].read_text()


def test_sourced_value_is_refused(harness: dict) -> None:
    result = _run(harness, "HUB_DISCOVERY_URL=http://h/$(id)\n")
    assert result.returncode != 0
    assert "Invalid HUB_DISCOVERY_URL" in result.stderr


def test_valid_urls_and_csv_pass(harness: dict) -> None:
    result = _run(
        harness,
        "CHAIN_ID=bc-2-island-1\n"
        "SUPPORTED_CHAINS=bc-2,bc-2-island-1\n"
        "HUB_DISCOVERY_URL=https://hub.example.net:8443/discover\n"
        "GOSSIP_WEBSOCKET_URL=wss://hub.example.net:7070/ws\n",
    )
    assert result.returncode == 0, result.stderr
    published = harness["out"].read_text()
    assert "CHAIN_ID=bc-2-island-1" in published
    assert "SUPPORTED_CHAINS=bc-2,bc-2-island-1" in published
