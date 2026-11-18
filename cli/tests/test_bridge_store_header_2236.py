"""Tests for ``aitbc bridge store-header`` proof-file validation (#2236).

Regression: the scenario doc prescribes the minimal fixture
``{"transfer_id": "nosuch-bo1", "proof": []}`` after the proof-build step
refuses to write one. ``store-header`` indexed ``proof["chain_id"]``
unconditionally, so following the doc produced a raw ``KeyError`` traceback
instead of a clean validation error. These tests pin the clean-abort path
through click's CliRunner.
"""

import json

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.bridge import sign_proof, store_header


@pytest.fixture
def runner():
    return CliRunner()


_MINIMAL_PROOF = {"transfer_id": "nosuch-bo1", "proof": []}

_FULL_PROOF = {
    "chain_id": "ait-mainnet",
    "block_height": 100,
    "block_hash": "0x" + "ab" * 32,
    "state_root": "0x" + "cd" * 32,
}

_ARGS = ["--admin-private-key", "0x" + "11" * 32]


def _write(tmp_path, doc, name="proof.json"):
    path = tmp_path / name
    path.write_text(json.dumps(doc))
    return str(path)


class TestStoreHeaderProofValidation:
    def test_minimal_fixture_aborts_cleanly(self, runner, tmp_path):
        # The doc-prescribed fixture must not traceback on missing fields.
        proof_file = _write(tmp_path, _MINIMAL_PROOF)
        result = runner.invoke(
            store_header,
            obj={"output_format": "table"},
            args=["--proof-file", proof_file, *_ARGS],
        )
        assert result.exit_code != 0
        assert "missing required field" in result.output
        assert "Traceback" not in result.output
        assert "chain_id" in result.output

    def test_missing_single_field_named(self, runner, tmp_path):
        doc = dict(_FULL_PROOF)
        del doc["state_root"]
        proof_file = _write(tmp_path, doc)
        result = runner.invoke(
            store_header,
            obj={"output_format": "table"},
            args=["--proof-file", proof_file, *_ARGS],
        )
        assert result.exit_code != 0
        assert "state_root" in result.output
        assert "Traceback" not in result.output

    def test_non_dict_proof_aborts_cleanly(self, runner, tmp_path):
        proof_file = _write(tmp_path, ["not", "a", "dict"])
        result = runner.invoke(
            store_header,
            obj={"output_format": "table"},
            args=["--proof-file", proof_file, *_ARGS],
        )
        assert result.exit_code != 0
        assert "JSON object" in result.output
        assert "Traceback" not in result.output


class TestSignProofNonDict:
    def test_non_dict_proof_aborts_cleanly(self, runner, tmp_path):
        proof_file = _write(tmp_path, ["not", "a", "dict"])
        result = runner.invoke(
            sign_proof,
            obj={"output_format": "table"},
            args=["--proof-file", proof_file, "--private-key", "0x" + "11" * 32],
        )
        assert result.exit_code != 0
        assert "JSON object" in result.output
        assert "Traceback" not in result.output
