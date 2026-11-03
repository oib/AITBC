"""#877: validate-env.sh must parse env files, not source them, case-insensitively.

The validator used to ``source`` /etc/aitbc/*.env — executing whatever the
file contained — and then only read the *lowercase* spellings
(rpc_bind_port, p2p_bind_port, enable_block_production), so an
EnvironmentFile written in the uppercase style systemd units actually
consume passed silently unvalidated. It also required PROPOSER_ID in
node.env although aitbc-blockchain-node reads it from blockchain.env
(setup.sh writes it there).

The rewrite reads values through scripts/utils/systemd-env.sh (the
EnvironmentFile parser used by update.sh), accepts both KEY spellings, and
checks PROPOSER_ID in blockchain.env. Tests run against scratch env files
via the BLOCKCHAIN_ENV_FILE / NODE_ENV_FILE overrides — never /etc.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "deployment" / "validate-env.sh"

BLOCKCHAIN_ENV = """\
CHAIN_ID=bc-2
RPC_BIND_PORT=8202
P2P_BIND_PORT=9000
ENABLE_BLOCK_PRODUCTION=false
PROPOSER_ID=0xE8948a556E8F2317d255b5d5021f2CECcBBd9CE2
"""

NODE_ENV = """\
NODE_ID=node-test
P2P_NODE_ID=p2p-test
"""


def _run(tmp_path: Path, blockchain: str = BLOCKCHAIN_ENV, node: str = NODE_ENV):
    bc = tmp_path / "blockchain.env"
    bc.write_text(blockchain)
    ne = tmp_path / "node.env"
    ne.write_text(node)
    env = dict(os.environ)
    env["BLOCKCHAIN_ENV_FILE"] = str(bc)
    env["NODE_ENV_FILE"] = str(ne)
    env["REPO_ROOT"] = str(REPO)
    return subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env)


def test_uppercase_keys_validate(tmp_path):
    """The systemd-style UPPERCASE spellings are read, not skipped."""
    proc = _run(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_lowercase_keys_still_validate(tmp_path):
    proc = _run(
        tmp_path,
        blockchain="chain_id=bc-2\nrpc_bind_port=8202\np2p_bind_port=9000\n"
        "enable_block_production=false\nproposer_id=0xE8948a556E8F2317d255b5d5021f2CECcBBd9CE2\n",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_bad_uppercase_boolean_is_caught(tmp_path):
    proc = _run(tmp_path, blockchain=BLOCKCHAIN_ENV.replace("false", "yes"))
    assert proc.returncode != 0
    assert "ENABLE_BLOCK_PRODUCTION" in proc.stdout + proc.stderr or "true" in proc.stdout + proc.stderr


def test_proposer_id_must_be_in_blockchain_env(tmp_path):
    """aitbc-blockchain-node reads PROPOSER_ID from blockchain.env."""
    proc = _run(
        tmp_path,
        blockchain=BLOCKCHAIN_ENV.replace("PROPOSER_ID=0xE8948a556E8F2317d255b5d5021f2CECcBBd9CE2\n", ""),
        node=NODE_ENV + "PROPOSER_ID=0xE8948a556E8F2317d255b5d5021f2CECcBBd9CE2\n",
    )
    assert proc.returncode != 0
    assert "PROPOSER_ID" in proc.stdout + proc.stderr


def test_env_files_are_parsed_never_executed(tmp_path):
    """A sourcing hazard line must stay inert — files are parsed, not run."""
    sentinel = tmp_path / "executed"
    proc = _run(
        tmp_path,
        blockchain=BLOCKCHAIN_ENV + f'PWNED=$(touch "{sentinel}")\n',
    )
    assert not sentinel.exists(), "validate-env.sh executed the env file as shell"
    assert proc.returncode == 0, proc.stdout + proc.stderr
