"""
ZK Proof generation service for privacy-preserving receipt attestation
"""

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from aitbc.aitbc_logging import get_logger

from ....schemas import JobResult, Receipt
from .zkey_header import ZKeyFormatError, read_zkey_header

logger = get_logger(__name__)


# V23-24/V23-32: verification is off unless a deployment turns it on, matching the
# blockchain node, which answers "ZK proof verification is not enabled on this node" rather
# than accepting a proof. The coordinator's /zk/*/verify endpoints previously had no such
# gate, so the one subsystem that honestly declared the feature off was contradicted by
# another serving it.
#
# feature_flags.json used to carry an `enable_zk_proof_verification` entry, but nothing read
# it: aitbc/feature_flags.py was removed in v0.10.9 and no loader replaced it. That file has
# since been deleted (V23-32). An env var is the convention actually in use
# (AI_ENGINE_ALLOW_SIMULATION, EDGE_ALLOW_SIMULATED_SYNC), so that is what this uses.
ENABLE_ZK_VERIFICATION = os.getenv("COORDINATOR_ENABLE_ZK_VERIFICATION", "false").lower() == "true"

# The circuit that proves receipts. Named, because _generate_proof used to take whichever
# circuit sorted first in available_circuits (V23-26a).
RECEIPT_CIRCUIT = "receipt_simple"

VERIFICATION_DISABLED = (
    "ZK proof verification is not enabled on this coordinator. Set "
    "COORDINATOR_ENABLE_ZK_VERIFICATION=true to enable it, and read the trusted-setup "
    "record for these circuits first: a proving key with no phase-2 contribution lets "
    "whoever holds the setup secret forge proofs that verify."
)


def _resolve_proving_key(circuits_dir: Path, circuit: str) -> Path | None:
    """Return the highest-numbered contribution for ``circuit``, or None if unusable.

    Groth16 ``*_0000.zkey`` is the key straight out of ``groth16 setup``, before any phase-2
    contribution. Whoever holds the phase-2 secret for a key can forge proofs that verify
    against it, so a zero-contribution key is not a weaker key — it is one with a known
    forger. Two circuits were pinned to ``_0000`` while ``_0001`` sat unused in the same
    directory (V23-24), inconsistently within a single config literal, which is what marked
    it as an oversight rather than a decision.

    Selecting by highest index rather than by a written-out filename means a new
    contribution is picked up by adding the file, and a stale index cannot silently mean
    "unsecured".
    """
    candidates: list[tuple[int, Path]] = []
    for path in circuits_dir.glob(f"{circuit}_*.zkey"):
        stem, _, suffix = path.stem.rpartition("_")
        # The glob is a prefix match, so "ml_inference_verification_0001" would also be a
        # candidate for a circuit named "ml". Require the stem to be the circuit exactly:
        # picking up a neighbouring circuit's key is the same class of mistake as picking
        # up a zero-contribution one.
        if stem == circuit and suffix.isdigit():
            candidates.append((int(suffix), path))

    if not candidates:
        return None

    contribution, path = max(candidates)
    if contribution == 0:
        logger.error(
            "Circuit '%s' has no phase-2 contribution: %s is the only proving key present. "
            "Anyone holding the trusted-setup secret can forge proofs that verify against "
            "it, so the circuit is not being loaded. Run a phase-2 contribution and ship "
            "the resulting _0001.zkey (or later).",
            circuit,
            path.name,
        )
        return None
    return path


def _verification_key_mismatch(zkey_path: Path, vkey_path: Path) -> str | None:
    """Return why ``vkey_path`` cannot belong to ``zkey_path``, or None if it may.

    A single ``verification_key.json`` had been copied into four locations and served four
    circuits with 0, 1, 5 and 5 public signals (V23-26a). Comparing the public-signal count
    catches that: a verification key for a different circuit cannot verify this one's
    proofs, so the circuit must not be offered.

    This is necessary, not sufficient — two circuits can agree on the count and still be
    different circuits. Matching counts mean "not obviously wrong", and that is all this
    claims.
    """
    try:
        header = read_zkey_header(zkey_path)
    except (ZKeyFormatError, OSError) as e:
        return f"proving key {zkey_path.name} could not be read: {e}"

    if not header.is_groth16:
        return f"proving key {zkey_path.name} is not a Groth16 key (protocol id {header.protocol})"

    try:
        vkey = json.loads(vkey_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return f"verification key {vkey_path.name} could not be read: {e}"

    declared = vkey.get("nPublic")
    if declared is None:
        return f"verification key {vkey_path.name} declares no nPublic"

    if declared != header.n_public:
        return (
            f"verification key {vkey_path.name} is for a different circuit: it declares "
            f"nPublic={declared}, but proving key {zkey_path.name} has nPublic={header.n_public}. "
            f"Export the verification key from that proving key "
            f"(snarkjs zkey export verificationkey {zkey_path.name} {vkey_path.name})."
        )

    return None


class ZKProofService:
    """Service for generating zero-knowledge proofs for receipts and ML operations"""

    def __init__(self, circuits_dir: Path | None = None) -> None:
        # V23-26: the artifacts exist in two trees — this in-package copy and
        # apps/zk-circuits/, which is where they are built. They have diverged, and the
        # path being hardcoded is why nothing could be pointed at the other one to compare.
        # The in-package copy stays the default so deployments are unaffected.
        configured = os.getenv("COORDINATOR_ZK_CIRCUITS_DIR")
        self.circuits_dir = circuits_dir or (Path(configured) if configured else Path(__file__).parent.parent / "zk-circuits")
        self.circuits = {
            "receipt_simple": {
                "zkey_path": _resolve_proving_key(self.circuits_dir, "receipt_simple"),
                "wasm_path": self.circuits_dir / "receipt_simple_js" / "receipt_simple.wasm",
                "vkey_path": self.circuits_dir / "receipt_simple_js" / "verification_key.json",
            },
            "ml_inference_verification": {
                "zkey_path": _resolve_proving_key(self.circuits_dir, "ml_inference_verification"),
                "wasm_path": self.circuits_dir / "ml_inference_verification_js" / "ml_inference_verification.wasm",
                "vkey_path": self.circuits_dir / "ml_inference_verification_js" / "verification_key.json",
            },
            "ml_training_verification": {
                "zkey_path": _resolve_proving_key(self.circuits_dir, "ml_training_verification"),
                "wasm_path": self.circuits_dir / "ml_training_verification_js" / "ml_training_verification.wasm",
                "vkey_path": self.circuits_dir / "ml_training_verification_js" / "verification_key.json",
            },
            "modular_ml_components": {
                "zkey_path": _resolve_proving_key(self.circuits_dir, "modular_ml_components"),
                "wasm_path": self.circuits_dir / "modular_ml_components_js" / "modular_ml_components.wasm",
                "vkey_path": self.circuits_dir / "verification_key.json",
            },
        }
        # V23-46: `available_circuits` holds only circuits that passed every check, so its
        # paths are never None -- but `circuits` above is inferred as `Path | None` because
        # `_resolve_proving_key` may return None, and a subscript is not something the type
        # checker can narrow. Binding to a local does narrow, which is what the seven
        # `Path | None` errors in this file came down to.
        self.available_circuits: dict[str, dict[str, Path]] = {}
        for circuit_name, paths in self.circuits.items():
            zkey_path = paths["zkey_path"]
            if zkey_path is None:
                # _resolve_proving_key has already said why: either no key at all, or only
                # a zero-contribution one. Either way the circuit stays unavailable rather
                # than falling back to something forgeable.
                logger.warning("❌ Circuit '%s' unavailable: no usable proving key", circuit_name)
                continue
            # Only zkey_path is ever optional; the other two are built from circuits_dir.
            resolved = {name: path for name, path in paths.items() if path is not None}
            missing = [str(path) for path in resolved.values() if not path.exists()]
            if not missing:
                mismatch = _verification_key_mismatch(zkey_path, resolved["vkey_path"])
                if mismatch:
                    logger.error("❌ Circuit '%s' unavailable: %s", circuit_name, mismatch)
                    continue
                self.available_circuits[circuit_name] = resolved
                logger.info("✅ Circuit '%s' available, proving key %s", circuit_name, zkey_path.name)
            else:
                # Name the absent files. A bare "missing files" warning let an over-broad
                # .gitignore (*.zkey/*.wasm) silently untrack every proving key without
                # anyone noticing proving had been disabled.
                logger.warning("❌ Circuit '%s' unavailable, missing: %s", circuit_name, ", ".join(missing))
        logger.info("Available circuits: %s", list(self.available_circuits.keys()))
        self.enabled = len(self.available_circuits) > 0
        if not self.enabled:
            # Losing every circuit is a deployment fault, not a normal degraded mode:
            # callers get None from every generate_*_proof and receipts go unproven.
            logger.error(
                "ZK proving is DISABLED: no circuit has a complete set of files under %s. "
                "Proving keys (*.zkey) and witness calculators (*.wasm) must be present in the "
                "deployment; check they are tracked in git and not excluded by .gitignore.",
                self.circuits_dir,
            )

    async def generate_receipt_proof(
        self, receipt: Receipt, job_result: JobResult, privacy_level: str = "basic"
    ) -> dict[str, Any] | None:
        """Generate a ZK proof for a receipt"""
        if not self.enabled:
            logger.warning("ZK proof generation not available")
            return None
        try:
            inputs = await self._prepare_inputs(receipt, job_result, privacy_level)
            proof_data = await self._generate_proof(inputs)
            return {
                "proof": proof_data["proof"],
                "public_signals": proof_data["publicSignals"],
                "privacy_level": privacy_level,
                "circuit_hash": await self._get_circuit_hash(),
            }
        except Exception as e:
            logger.error("Failed to generate ZK proof: %s", e)
            return None

    async def generate_proof(
        self, circuit_name: str, inputs: dict[str, Any], private_inputs: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Generate a ZK proof for any supported circuit type"""
        if not self.enabled:
            logger.warning("ZK proof generation not available")
            return None
        if circuit_name not in self.available_circuits:
            logger.error("Circuit '%s' not available. Available: %s", circuit_name, list(self.available_circuits.keys()))
            return None
        try:
            circuit_paths = self.available_circuits[circuit_name]
            proof_data = await self._generate_proof_generic(
                inputs, private_inputs, circuit_paths["wasm_path"], circuit_paths["zkey_path"], circuit_paths["vkey_path"]
            )
            return {
                "proof_id": f"{circuit_name}_{asyncio.get_event_loop().time()}",
                "proof": proof_data["proof"],
                "public_signals": proof_data["publicSignals"],
                "verification_key": proof_data.get("verificationKey"),
                "circuit_type": circuit_name,
                "optimization_level": "phase3_optimized" if "modular" in circuit_name else "baseline",
            }
        except Exception as e:
            logger.error("Failed to generate %s proof: %s", circuit_name, e)
            return None

    async def verify_proof(
        self,
        proof: dict[str, Any],
        public_signals: list[str],
        circuit_name: str | None = None,
    ) -> dict[str, Any]:
        """Verify a ZK proof against a verification key this service trusts.

        The key is chosen by ``circuit_name`` from the circuits on disk. It is deliberately
        **not** a parameter: this method used to accept a caller-supplied
        ``verification_key`` and verify against it, which the ``/zk/verify`` and
        ``/zk/ml/verify/*`` endpoints exposed straight through to the network. Anyone could
        generate their own Groth16 keypair, prove any statement they liked, submit proof and
        key together, and be told ``verified: true``. A verifier that accepts the verifier's
        key from the party being verified is not checking anything.

        Args:
            proof: The ZK proof to verify
            public_signals: Public signals for the proof
            circuit_name: Which circuit's verification key to check against. Defaults to
                the first available circuit, preserving prior behaviour for callers that
                did not name one.
        """
        try:
            if not ENABLE_ZK_VERIFICATION:
                return {"verified": False, "error": VERIFICATION_DISABLED}
            if not self.enabled:
                return {"verified": False, "error": "ZK proof service not enabled"}
            if not self.available_circuits:
                return {"verified": False, "error": "No circuits available for verification"}

            if circuit_name is not None:
                if circuit_name not in self.available_circuits:
                    return {
                        "verified": False,
                        "error": (
                            f"Unknown or unavailable circuit '{circuit_name}'. Available: {sorted(self.available_circuits)}"
                        ),
                    }
                circuit = self.available_circuits[circuit_name]
            else:
                circuit = list(self.available_circuits.values())[0]

            vkey_path = circuit["vkey_path"]
            try:
                with open(vkey_path) as f:
                    vkey = json.load(f)
            except FileNotFoundError:
                return {"verified": False, "error": f"Verification key not found at {vkey_path}"}
            script = f"\nconst snarkjs = require('snarkjs');\n\nasync function main() {{\n    try {{\n        const vKey = {json.dumps(vkey)};\n        const proof = {json.dumps(proof)};\n        const publicSignals = {json.dumps(public_signals)};\n\n        const verified = await snarkjs.groth16.verify(vKey, publicSignals, proof);\n        console.log(verified);\n    }} catch (error) {{\n        console.error('Error:', error.message);\n        process.exit(1);\n    }}\n}}\n\nmain();\n"
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
                f.write(script)
                script_file = f.name
            try:
                # ponytail: subprocess.run() blocks event loop - should use asyncio.create_subprocess_exec()
                # This is acceptable for ZK proof verification (CPU-intensive, not a hot path), but could be improved
                result = subprocess.run(["node", script_file], capture_output=True, text=True, cwd=str(self.circuits_dir))
                if result.returncode != 0:
                    logger.error("Proof verification failed: %s", result.stderr)
                    return {
                        "verified": False,
                        "computation_correct": False,
                        "privacy_preserved": False,
                        "error": result.stderr,
                    }
                is_verified = result.stdout.strip() == "true"
                return {"verified": is_verified, "computation_correct": is_verified, "privacy_preserved": is_verified}
            finally:
                os.unlink(script_file)
        except Exception as e:
            logger.error("Failed to verify proof: %s", e)
            return {"verified": False, "error": str(e)}

    async def _prepare_inputs(self, receipt: Receipt, job_result: JobResult, privacy_level: str) -> dict[str, Any]:
        """Prepare circuit inputs based on privacy level"""
        if privacy_level == "basic":
            return {
                "data": [
                    str(receipt.receiptId),
                    str(receipt.miner),
                    str(getattr(job_result, "output_hash", "")),
                    str((receipt.payload or {}).get("rate", 0)),
                ],
                "hash": await self._hash_receipt(receipt),
            }
        elif privacy_level == "enhanced":
            payload = receipt.payload or {}
            return {
                "settlementAmount": payload.get("settlement_amount", 0),
                "timestamp": receipt.issuedAt.isoformat(),
                "receipt": self._serialize_receipt(receipt),
                "computationResult": getattr(job_result, "output_hash", ""),
                "pricingRate": payload.get("rate", 0),
                "minerReward": payload.get("miner_reward", 0),
                "coordinatorFee": payload.get("coordinator_fee", 0),
            }
        else:
            raise ValueError(f"Unknown privacy level: {privacy_level}")

    async def _hash_receipt(self, receipt: Receipt) -> str:
        """Hash receipt for public verification"""
        import hashlib

        payload = receipt.payload or {}
        receipt_data = {
            "receipt_id": receipt.receiptId,
            "miner": receipt.miner,
            "timestamp": receipt.issuedAt.isoformat(),
            "pricing": payload.get("pricing", {}),
        }
        receipt_str = json.dumps(receipt_data, sort_keys=True)
        return hashlib.sha256(receipt_str.encode()).hexdigest()

    def _serialize_receipt(self, receipt: Receipt) -> list[str]:
        """Serialize receipt for circuit input"""
        payload = receipt.payload or {}
        return [
            str(receipt.receiptId)[:32],
            str(receipt.miner)[:32],
            str(receipt.issuedAt)[:32],
            str(payload.get("settlement_amount", 0))[:32],
            str(payload.get("miner_reward", 0))[:32],
            str(payload.get("coordinator_fee", 0))[:32],
            "0",
            "0",
        ]

    async def _generate_proof(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Generate a receipt proof using snarkjs.

        Named explicitly rather than taken from ``available_circuits`` by position. This
        used to read ``list(self.available_circuits.values())[0]``, so which circuit proved
        a receipt depended on which circuits happened to load: withhold ``receipt_simple``
        and receipts would have been proven against ``ml_inference_verification`` instead,
        producing a valid proof of the wrong statement (V23-26a).
        """
        circuit = self.available_circuits.get(RECEIPT_CIRCUIT)
        if circuit is None:
            raise RuntimeError(
                f"Circuit '{RECEIPT_CIRCUIT}' is not available, so receipt proofs cannot be generated. "
                f"Loaded circuits: {list(self.available_circuits)}. See the startup log for why it was "
                f"withheld."
            )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(inputs, f)
            inputs_file = f.name
        try:
            script = f"\nconst snarkjs = require('snarkjs');\nconst fs = require('fs');\n\nasync function main() {{\n    try {{\n        // Load inputs\n        const inputs = JSON.parse(fs.readFileSync('{inputs_file}', 'utf8'));\n\n        // Load circuit\n        const wasm = fs.readFileSync('{circuit['wasm_path']}');\n        const zkey = fs.readFileSync('{circuit['zkey_path']}');\n\n        // Calculate witness\n        const {{ witness }} = await snarkjs.wtns.calculate(inputs, wasm, wasm);\n\n        // Generate proof\n        const {{ proof, publicSignals }} = await snarkjs.groth16.prove(zkey, witness);\n\n        // Output result\n        console.log(JSON.stringify({{ proof, publicSignals }}));\n    }} catch (error) {{\n        console.error('Error:', error);\n        process.exit(1);\n    }}\n}}\n\nmain();\n"
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
                f.write(script)
                script_file = f.name
            try:
                # ponytail: subprocess.run() blocks event loop - should use asyncio.create_subprocess_exec()
                # This is acceptable for ZK proof verification (CPU-intensive, not a hot path), but could be improved
                result = subprocess.run(["node", script_file], capture_output=True, text=True, cwd=str(self.circuits_dir))
                if result.returncode != 0:
                    raise Exception(f"Proof generation failed: {result.stderr}")
                return dict(json.loads(result.stdout))
            finally:
                os.unlink(script_file)
        finally:
            os.unlink(inputs_file)

    async def _generate_proof_generic(
        self,
        public_inputs: dict[str, Any],
        private_inputs: dict[str, Any] | None,
        wasm_path: Path,
        zkey_path: Path,
        vkey_path: Path,
    ) -> dict[str, Any]:
        """Generate proof using snarkjs with generic circuit paths"""
        inputs = public_inputs.copy()
        if private_inputs:
            inputs.update(private_inputs)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(inputs, f)
            inputs_file = f.name
        try:
            script = f"\nconst snarkjs = require('snarkjs');\nconst fs = require('fs');\n\nasync function main() {{\n    try {{\n        // Load inputs\n        const inputs = JSON.parse(fs.readFileSync('{inputs_file}', 'utf8'));\n\n        // Load circuit files\n        const wasm = fs.readFileSync('{wasm_path}');\n        const zkey = fs.readFileSync('{zkey_path}');\n\n        // Calculate witness\n        const {{ witness }} = await snarkjs.wtns.calculate(inputs, wasm);\n\n        // Generate proof\n        const {{ proof, publicSignals }} = await snarkjs.groth16.prove(zkey, witness);\n\n        // Load verification key\n        const vKey = JSON.parse(fs.readFileSync('{vkey_path}', 'utf8'));\n\n        // Output result\n        console.log(JSON.stringify({{ proof, publicSignals, verificationKey: vKey }}));\n    }} catch (error) {{\n        console.error('Error:', error.message);\n        process.exit(1);\n    }}\n}}\n\nmain();\n"
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
                f.write(script)
                script_file = f.name
            try:
                result = await asyncio.create_subprocess_exec(
                    "node", script_file, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await result.communicate()
                if result.returncode == 0:
                    proof_data: dict[str, Any] = json.loads(stdout.decode())
                    return proof_data
                else:
                    error_msg = stderr.decode() or stdout.decode()
                    raise Exception(f"Proof generation failed: {error_msg}")
            finally:
                os.unlink(script_file)
        finally:
            os.unlink(inputs_file)

    async def _get_circuit_hash(self) -> str:
        """Get hash of current circuit for verification.

        Hashes the zkey (proving key) of the first available circuit — the same
        circuit _generate_proof uses — so the proof's circuit_hash identifies the
        exact circuit version, not a placeholder.
        """
        import hashlib

        if not self.available_circuits:
            return ""
        zkey_path = list(self.available_circuits.values())[0]["zkey_path"]
        h = hashlib.sha256()
        with open(zkey_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def is_enabled(self) -> bool:
        """Check if ZK proof generation is available"""
        return self.enabled


zk_proof_service = ZKProofService()
