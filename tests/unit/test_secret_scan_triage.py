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
