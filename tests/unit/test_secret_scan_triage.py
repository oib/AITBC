"""Pin for OPS-SECRET-SCAN-DEMOTES-REAL-1 (#907): the triage used to downgrade
real credentials — 'localhost' anywhere on the line meant placeholder, and
'test' in any path substring meant test-fixture?."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))
import secret_scan


def test_password_url_at_localhost_is_real():
    cls, v = secret_scan.classify("postgres://user:Sup3rSecret@localhost:5432/db", "cfg/prod.env")
    assert cls == "cred-url" and v == "REAL?"


def test_key_in_attestation_path_is_real():
    cls, v = secret_scan.classify('api_key="0x' + "ab" * 32 + '"', "apps/blockchain-node/src/aitbc_chain/attestation.py")
    assert cls == "hex64-keyname" and v == "REAL?"


def test_real_test_dir_still_demotes():
    cls, v = secret_scan.classify('api_key="0x' + "ab" * 32 + '"', "tests/fixtures/wallet.json")
    assert v in ("test-fixture?", "test-fixture")


def test_explicit_placeholder_still_demotes():
    cls, v = secret_scan.classify("postgres://user:changeme@localhost:5432/db", "docs/eg.env")
    assert v == "placeholder"


def test_ere_list_covers_every_pattern():
    """#908: tree scan must ask git-grep for every class classify() knows."""
    assert len(secret_scan.ERE_LIST) == len(secret_scan.PATTERNS)


def test_gitea_token_classifies():
    cls, v = secret_scan.classify('gitea_token = "' + "ab" * 20 + '"', "cfg/prod.env")
    assert cls == "gitea-token"


def test_mnemonic_classifies():
    cls, v = secret_scan.classify("word " * 11 + "final", "keys/wallet.txt")
    assert cls == "mnemonic-line"


def test_tree_and_history_find_the_dead_classes(tmp_path):
    """done_when: a scratch repo holding a gitea token and a 12-word line is
    reported by BOTH scan modes."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@t"],
        ["git", "config", "user.name", "t"],
    ):
        subprocess.run(cmd, cwd=repo, check=True)
    (repo / "leak.txt").write_text('gitea_token = "' + "ab" * 20 + '"\n')
    (repo / "seed.txt").write_text("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda muse\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=repo, check=True)

    tree_rows = list(secret_scan.scan_tree(str(repo)))
    classes = {r[4] for r in tree_rows}
    assert "gitea-token" in classes
    assert "mnemonic-line" in classes

    hist_rows = list(secret_scan.scan_history(str(repo)))
    hclasses = {r[4] for r in hist_rows}
    assert "gitea-token" in hclasses
    assert "mnemonic-line" in hclasses
