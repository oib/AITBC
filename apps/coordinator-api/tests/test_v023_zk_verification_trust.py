"""V23-24: what the ZK verification path is willing to trust.

Two problems, one enclosing the other.

The audit found that two of four circuits loaded ``*_0000.zkey`` — the key straight
out of ``groth16 setup``, before any phase-2 contribution — while the contributed
``_0001`` sat unused in the same directory. Whoever holds the phase-2 secret for a
key can forge proofs that verify against it.

Fixing that turned up something larger in the same call path: ``verify_proof``
accepted a caller-supplied ``verification_key`` and verified against it, and both
``/zk/verify`` and ``/zk/ml/verify/*`` passed one straight through from the request
body. Anyone could generate their own keypair, prove any statement, submit proof and
key together, and be told ``verified: true``. Which proving key sat on disk did not
matter, because the disk was not consulted.
"""

from __future__ import annotations

from pathlib import Path

from coordinator_api.contexts.zk_applications.services import zk_proofs as zk_module
from coordinator_api.contexts.zk_applications.services.zk_proofs import (
    ZKProofService,
    _resolve_proving_key,
)
from coordinator_api.contexts.zk_applications.services.zkey_header import read_zkey_contribution_count

_SERVICE_ZKEYS = Path(__file__).resolve().parents[1] / "src/coordinator_api/contexts/zk_applications/zk-circuits"
_ZERO_CONTRIB = _SERVICE_ZKEYS / "ml_inference_verification_0000.zkey"
_ONE_CONTRIB = _SERVICE_ZKEYS / "ml_inference_verification_0001.zkey"


def _install(tmp_path: Path, name: str, src: Path) -> Path:
    dest = tmp_path / name
    dest.write_bytes(src.read_bytes())
    return dest


class TestProvingKeySelection:
    """V23-24 proper: a zero-contribution key is one with a known forger."""

    def test_highest_contribution_wins(self, tmp_path):
        _install(tmp_path, "c_0000.zkey", _ZERO_CONTRIB)
        _install(tmp_path, "c_0001.zkey", _ONE_CONTRIB)
        _install(tmp_path, "c_0002.zkey", _ONE_CONTRIB)

        assert _resolve_proving_key(tmp_path, "c").name == "c_0002.zkey"

    def test_zero_contribution_only_is_refused(self, tmp_path, caplog):
        """Not 'use it anyway with a warning' — the circuit does not load."""
        (tmp_path / "c_0000.zkey").touch()

        with caplog.at_level("ERROR"):
            assert _resolve_proving_key(tmp_path, "c") is None

        assert "no phase-2 contribution" in caplog.text

    def test_renamed_zero_contribution_is_refused(self, tmp_path, caplog):
        """The suffix is a claim. V23-91: modular_ml_components_0001.zkey had zero contributions."""
        _install(tmp_path, "c_0001.zkey", _ZERO_CONTRIB)
        assert read_zkey_contribution_count(tmp_path / "c_0001.zkey") == 0

        with caplog.at_level("ERROR"):
            assert _resolve_proving_key(tmp_path, "c") is None

        assert "named as contribution" in caplog.text

    def test_missing_key_is_refused(self, tmp_path):
        assert _resolve_proving_key(tmp_path, "c") is None

    def test_other_circuits_do_not_leak_in(self, tmp_path):
        """A prefix match must not pick up a different circuit's key."""
        _install(tmp_path, "c_0001.zkey", _ONE_CONTRIB)
        _install(tmp_path, "c_extra_0009.zkey", _ONE_CONTRIB)

        assert _resolve_proving_key(tmp_path, "c").name == "c_0001.zkey"

    def test_non_numeric_suffixes_are_ignored(self, tmp_path):
        _install(tmp_path, "c_final.zkey", _ONE_CONTRIB)
        _install(tmp_path, "c_0001.zkey", _ONE_CONTRIB)

        assert _resolve_proving_key(tmp_path, "c").name == "c_0001.zkey"

    def test_shipped_circuits_use_a_contributed_key(self):
        """The regression that started this: no circuit resolves to _0000."""
        service = ZKProofService()

        for name, paths in service.circuits.items():
            zkey = paths["zkey_path"]
            if zkey is not None:
                assert not zkey.name.endswith("_0000.zkey"), f"{name} resolved to a zero-contribution key"

    def test_unusable_key_makes_the_circuit_unavailable(self, monkeypatch):
        """Refusing a key must not fall back to proving with it anyway."""
        monkeypatch.setattr(zk_module, "_resolve_proving_key", lambda _dir, _circuit: None)

        service = ZKProofService()

        assert service.available_circuits == {}
        assert service.enabled is False


class TestVerificationKeyIsNotCallerSupplied:
    """The larger hole: a verifier must not take its key from the party being verified."""

    def test_request_model_rejects_a_verification_key(self):
        """The field is gone from the API, not merely ignored by the service."""
        from coordinator_api.contexts.zk_applications.routers.zk_proofs import VerifyProofRequest

        assert "verification_key" not in VerifyProofRequest.model_fields
        assert "circuit_name" in VerifyProofRequest.model_fields


class TestVerificationIsOffByDefault:
    """V23-32's coordinator half: the node fails closed, this now does too."""

    def test_flag_default_is_off(self, monkeypatch):
        import importlib

        monkeypatch.delenv("COORDINATOR_ENABLE_ZK_VERIFICATION", raising=False)
        reloaded = importlib.reload(zk_module)
        try:
            assert reloaded.ENABLE_ZK_VERIFICATION is False
        finally:
            importlib.reload(zk_module)
