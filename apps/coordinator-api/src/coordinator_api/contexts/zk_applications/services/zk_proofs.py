"""
ZK Proof generation service for privacy-preserving receipt attestation
"""

import asyncio
import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from aitbc.aitbc_logging import get_logger

from ....schemas import JobResult, Receipt
from .model_registry import compute_public_inputs, get_model, resolve_model_id
from .zkey_header import ZKeyFormatError, read_zkey_contribution_count, read_zkey_header

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

# The circuit that proves receipts. P2.1 uses `receipt_public`, whose `receiptHash` is a
# public signal and can be checked against the on-chain job result before escrow release.
# It falls back to the previous `receipt_simple` only if `receipt_public` is unavailable.
RECEIPT_CIRCUIT = os.getenv("COORDINATOR_RECEIPT_CIRCUIT", "receipt_public")

# Node resolves `require()` against the directory of the script being executed, not against
# the process cwd. Every snarkjs call below writes its script to a tempfile under /tmp, so
# `require('snarkjs')` searched /tmp/node_modules and /node_modules and found nothing --
# `cwd=self.circuits_dir`, which two of the three call sites passed, has no bearing on module
# resolution. Proving and verification could not work regardless of which circuits loaded or
# where snarkjs was installed, including a global `npm install -g` (global roots are not on
# the default require path either). NODE_PATH is what moves the search path (V23-91).
_DEFAULT_SNARKJS_NODE_PATH = Path(__file__).parents[6] / "zk-circuits" / "node_modules"
SNARKJS_NODE_PATH = Path(os.getenv("COORDINATOR_SNARKJS_NODE_PATH") or _DEFAULT_SNARKJS_NODE_PATH)


def _node_env() -> dict[str, str]:
    """Environment for a ``node`` subprocess that has to ``require('snarkjs')``."""
    env = dict(os.environ)
    inherited = env.get("NODE_PATH", "")
    env["NODE_PATH"] = f"{SNARKJS_NODE_PATH}{os.pathsep}{inherited}" if inherited else str(SNARKJS_NODE_PATH)
    return env


def snarkjs_available() -> bool:
    """Whether ``NODE_PATH`` will resolve snarkjs for the subprocesses below."""
    return (SNARKJS_NODE_PATH / "snarkjs" / "package.json").is_file()


VERIFICATION_DISABLED = (
    "ZK proof verification is not enabled on this coordinator. Set "
    "COORDINATOR_ENABLE_ZK_VERIFICATION=true to enable it, and read the trusted-setup "
    "record for these circuits first: a proving key with no phase-2 contribution lets "
    "whoever holds the setup secret forge proofs that verify."
)

#: Circuits that expose a "success" public output in addition to the Groth16 proof itself.
#: The value is the index of that signal in the public-signals array, or ``-1`` to mean
#: the last public signal (used when the success flag is appended after other public outputs).
CIRCUIT_SUCCESS_SIGNALS: dict[str, int | None] = {
    "ml_inference_verification": 0,  # output ``verified`` is the only public signal
    "ml_training_verification": -1,  # ``training_complete`` is the last public signal
    "modular_ml_components": -1,  # ``training_complete`` is the last public signal
    "receipt_public": None,
    "receipt_simple": None,
}


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

    # The check above reads the filename, and a filename is a claim rather than a fact.
    # `modular_ml_components_0001.zkey` was a key straight out of `groth16 setup` with zero
    # contributions, and the `_0001` in its name was enough to satisfy the guard for three
    # releases (V23-91). The zkey states its own contribution count, so ask the file.
    try:
        contributions = read_zkey_contribution_count(path)
    except (ZKeyFormatError, OSError) as e:
        logger.error("Circuit '%s' proving key %s could not be read for contributions: %s", circuit, path.name, e)
        return None

    if contributions == 0:
        logger.error(
            "Circuit '%s' is not being loaded: %s is named as contribution %d but carries "
            "none — it is the output of `groth16 setup`, so whoever ran the setup can forge "
            "proofs that verify against it. Contribute with `snarkjs zkey contribute` and "
            "ship the result under the next index.",
            circuit,
            path.name,
            contribution,
        )
        return None
    return path


# Coordinates in a bn128 verification key are decimal strings of elements of Fq.
_BN128_FQ = 21888242871839275222246405745257275088696311157297823662689037894645226208583

# The group elements every Groth16 verification key must carry, besides IC.
_VKEY_POINTS = ("vk_alpha_1", "vk_beta_2", "vk_gamma_2", "vk_delta_2")


def _coordinates(value: Any) -> Iterator[Any]:
    """Yield the leaves of a nested coordinate list (G1 is flat, G2 and GT are nested)."""
    if isinstance(value, list):
        for item in value:
            yield from _coordinates(item)
    else:
        yield value


def _verification_key_mismatch(zkey_path: Path, vkey_path: Path) -> str | None:
    """Return why ``vkey_path`` cannot belong to ``zkey_path``, or None if it may.

    A single ``verification_key.json`` had been copied into four locations and served four
    circuits with 0, 1, 5 and 5 public signals (V23-26a). Comparing the public-signal count
    catches that: a verification key for a different circuit cannot verify this one's
    proofs, so the circuit must not be offered.

    The count alone was not enough. ``ml_inference_verification`` shipped a key whose every
    group element was the literal placeholder ``["0x1234", "0x5678", "0x0"]`` and whose ``IC``
    held one point where a 1-signal circuit needs two. It declared ``nPublic: 1``, matched its
    proving key on that one number, and was the only circuit this service offered for three
    releases (V23-91). So the shape is checked too: ``IC`` must have one point per public
    signal plus one, and every coordinate must be a decimal element of Fq.

    Still necessary rather than sufficient — two circuits can agree on all of this and be
    different circuits. Nothing here checks curve membership or that the key was exported
    from *this* proving key; it rejects the keys that demonstrably cannot verify anything.
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

    export_it = f"Export it with: snarkjs zkey export verificationkey {zkey_path.name} {vkey_path.name}"

    absent = [name for name in _VKEY_POINTS if name not in vkey]
    if absent:
        return f"verification key {vkey_path.name} is missing {', '.join(absent)}. {export_it}"

    ic = vkey.get("IC")
    if not isinstance(ic, list) or len(ic) != declared + 1:
        found = len(ic) if isinstance(ic, list) else "no list"
        return (
            f"verification key {vkey_path.name} has an IC of {found} where a circuit with "
            f"{declared} public signal(s) needs {declared + 1}. {export_it}"
        )

    for name in (*_VKEY_POINTS, "IC"):
        for coordinate in _coordinates(vkey[name]):
            if not isinstance(coordinate, str) or not coordinate.isdigit() or int(coordinate) >= _BN128_FQ:
                return (
                    f"verification key {vkey_path.name} is not real key material: {name} contains "
                    f"{coordinate!r}, which is not a decimal bn128 field element. {export_it}"
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
            "receipt_model": {
                "zkey_path": _resolve_proving_key(self.circuits_dir, "receipt_model"),
                "wasm_path": self.circuits_dir / "receipt_model_js" / "receipt_model.wasm",
                "vkey_path": self.circuits_dir / "receipt_model_js" / "verification_key.json",
            },
            "receipt_public": {
                "zkey_path": _resolve_proving_key(self.circuits_dir, "receipt_public"),
                "wasm_path": self.circuits_dir / "receipt_public_js" / "receipt_public.wasm",
                "vkey_path": self.circuits_dir / "receipt_public_js" / "verification_key.json",
            },
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
                # The other three read their key from `<circuit>_js/`, which is where snarkjs
                # writes and where the .wasm already lives. This one pointed at the root of
                # circuits_dir, a path no circuit's key occupies, so the circuit was withheld
                # for a missing file that was never going to be there (V23-91).
                "vkey_path": self.circuits_dir / "modular_ml_components_js" / "verification_key.json",
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
        if self.available_circuits and not snarkjs_available():
            # Loading a circuit says the artifacts are consistent; it says nothing about
            # whether the prover can run. Without this the first symptom is a
            # MODULE_NOT_FOUND stack trace inside a caught exception, and generate_*_proof
            # returning None as though the receipt simply had no proof (V23-91).
            logger.error(
                "snarkjs is not installed under %s, so every proof and verification "
                "subprocess will fail with MODULE_NOT_FOUND even though %d circuit(s) loaded. "
                "Run `npm install` in apps/zk-circuits, or set COORDINATOR_SNARKJS_NODE_PATH "
                "to a node_modules directory that contains snarkjs.",
                SNARKJS_NODE_PATH,
                len(self.available_circuits),
            )
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
                "receipt": inputs.get("receipt", []),
                "circuit": RECEIPT_CIRCUIT,
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

    async def generate_model_proof(
        self,
        job: Any,
        result: Any,
    ) -> dict[str, Any] | None:
        """Generate a receipt_model proof for a supported deterministic model.

        Returns None if no model is identified, if the model is not in the
        supported registry, or if the receipt_model circuit is not available.
        """
        model_id = resolve_model_id(job, result)
        if not model_id:
            logger.warning("No model_id in job/result; cannot generate receipt_model proof")
            return None
        model = get_model(model_id)
        if model is None:
            logger.warning("Model %r is not in the supported model registry", model_id)
            return None
        if "receipt_model" not in self.available_circuits:
            logger.error("receipt_model circuit is not available")
            return None

        inputs = compute_public_inputs(job, result, model)
        circuit = self.available_circuits["receipt_model"]
        try:
            proof_data = await self._generate_proof_generic(
                inputs["public_inputs"],
                inputs["private_inputs"],
                circuit["wasm_path"],
                circuit["zkey_path"],
                circuit["vkey_path"],
            )
            return {
                "proof": proof_data["proof"],
                "public_signals": proof_data["publicSignals"],
                "circuit": "receipt_model",
                "circuit_hash": await self._get_circuit_hash("receipt_model"),
                "model_id": model.model_id,
                "model_name": model.name,
            }
        except Exception as e:
            logger.error("Failed to generate receipt_model proof: %s", e)
            return None

    async def verify_model_proof(
        self,
        proof: dict[str, Any],
        public_signals: list[str],
        expected_public: list[str],
    ) -> dict[str, Any]:
        """Verify a receipt_model proof and confirm public-signal binding.

        A proof only counts as ``computation_correct`` if it verifies *and*
        its public signals equal the coordinator-derived expected values. This
        prevents a miner from generating a proof for an arbitrary input/model/output.
        """
        verify_result = await self.verify_proof(proof, public_signals, circuit_name="receipt_model")
        if not verify_result.get("verified"):
            return {**verify_result, "computation_correct": False}
        if public_signals != expected_public:
            logger.error(
                "receipt_model public signals do not match expected: got %s, want %s",
                public_signals,
                expected_public,
            )
            return {
                "verified": True,
                "computation_correct": False,
                "privacy_preserved": True,
                "error": "public_signal_mismatch",
            }
        return {
            "verified": True,
            "computation_correct": True,
            "privacy_preserved": True,
        }

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

            if circuit_name is None:
                circuit_name = RECEIPT_CIRCUIT
            if circuit_name not in self.available_circuits:
                return {
                    "verified": False,
                    "error": (
                        f"Unknown or unavailable circuit '{circuit_name}'. Available: {sorted(self.available_circuits)}"
                    ),
                }
            circuit = self.available_circuits[circuit_name]

            vkey_path = circuit["vkey_path"]
            try:
                with open(vkey_path) as f:
                    vkey = json.load(f)
            except FileNotFoundError:
                return {"verified": False, "error": f"Verification key not found at {vkey_path}"}
            # process.exit(0) is required: snarkjs keeps worker threads alive after
            # groth16.verify, so Node never leaves the event loop and communicate() hangs
            # (V23-91).
            script = f"\nconst snarkjs = require('snarkjs');\n\nasync function main() {{\n    try {{\n        const vKey = {json.dumps(vkey)};\n        const proof = {json.dumps(proof)};\n        const publicSignals = {json.dumps(public_signals)};\n\n        const verified = await snarkjs.groth16.verify(vKey, publicSignals, proof);\n        console.log(verified);\n        process.exit(0);\n    }} catch (error) {{\n        console.error('Error:', error.message);\n        process.exit(1);\n    }}\n}}\n\nmain();\n"
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
                f.write(script)
                script_file = f.name
            try:
                proc = await asyncio.create_subprocess_exec(
                    "node",
                    script_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.circuits_dir),
                    env=_node_env(),
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    error = stderr.decode()
                    logger.error("Proof verification failed: %s", error)
                    return {
                        "verified": False,
                        "computation_correct": False,
                        "privacy_preserved": False,
                        "error": error,
                    }
                is_verified = stdout.decode().strip() == "true"
                success_index = CIRCUIT_SUCCESS_SIGNALS.get(circuit_name)
                if is_verified and success_index is not None:
                    if success_index == -1:
                        success_value = public_signals[-1] if public_signals else None
                    else:
                        success_value = public_signals[success_index] if len(public_signals) > success_index else None
                    computation_correct = success_value == "1"
                else:
                    # No success signal: a verified Groth16 proof only shows that the
                    # statement selected by the public inputs is internally consistent.
                    # It does not, on its own, show that the statement is the one the
                    # coordinator wanted (e.g. receipt_public only proves hash
                    # consistency; receipt_model needs public-signal binding in
                    # verify_model_proof).
                    computation_correct = False
                return {"verified": is_verified, "computation_correct": computation_correct, "privacy_preserved": is_verified}
            finally:
                os.unlink(script_file)
        except Exception as e:
            logger.error("Failed to verify proof: %s", e)
            return {"verified": False, "error": str(e)}

    async def _prepare_inputs(self, receipt: Receipt, job_result: JobResult, privacy_level: str) -> dict[str, Any]:
        """Prepare `receipt_public` inputs: public Poseidon hash of 4 private receipt fields."""
        payload = receipt.payload or {}
        try:
            units = float(payload.get("units", 0.0))
        except (TypeError, ValueError):
            units = 0.0
        # Derive 4 field elements from receipt metadata.
        job_id_felt = self._field_encode(receipt.payload.get("job_id") if receipt.payload else None, receipt.receiptId)
        provider_felt = self._field_encode(receipt.miner)
        output_hash = self._result_hash(job_result)
        result_felt = self._field_encode(output_hash)
        units_felt = self._field_encode(str(int(units * 1_000_000)))
        receipt_values = [job_id_felt, provider_felt, result_felt, units_felt]
        receipt_hash = await self._poseidon4(receipt_values)
        return {
            "receiptHash": str(receipt_hash),
            "receipt": [str(v) for v in receipt_values],
        }

    def _result_hash(self, job_result: JobResult | dict[str, Any] | None) -> str:
        """Deterministic hash of the job result for the circuit."""
        import hashlib

        if job_result is None:
            return ""
        if isinstance(job_result, dict):
            data = job_result
        else:
            data = getattr(job_result, "result", None) or job_result.model_dump(by_alias=True)
        result = data.get("output") or data.get("result") or data.get("output_hash") or ""
        return hashlib.sha256(str(result).encode()).hexdigest()

    def _field_encode(self, *values: Any) -> int:
        """Encode a value as a bn128 field element (< _BN128_FQ)."""
        import hashlib

        raw = "".join(str(v) for v in values if v is not None) or "0"
        # 32 hex chars = 128 bits, comfortably below the 254-bit field prime.
        return int(hashlib.sha256(raw.encode()).hexdigest()[:32], 16)

    async def _poseidon4(self, inputs: list[int]) -> int:
        """Compute Poseidon hash of 4 field elements using the same circomlib parameters."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(
                "const { poseidon4 } = require('poseidon-lite');\n"
                f"const inputs = {json.dumps([str(v) for v in inputs])}.map(BigInt);\n"
                "console.log(poseidon4(inputs).toString());\n"
            )
            script_file = f.name
        try:
            proc = await asyncio.create_subprocess_exec(
                "node",
                script_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.circuits_dir),
                env=_node_env(),
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"Poseidon4 computation failed: {stderr.decode()}")
            return int(stdout.decode().strip())
        finally:
            os.unlink(script_file)

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
            # groth16.fullProve, given paths, rather than wtns.calculate followed by
            # groth16.prove. That pairing could not have worked: wtns.calculate takes a path
            # or a {type: "mem"} object and was handed a Buffer, and it writes the witness to
            # its third argument instead of returning one, so `witness` was undefined before
            # the Buffer ever reached snarkjs (V23-91).
            script = f"\nconst snarkjs = require('snarkjs');\nconst fs = require('fs');\n\nasync function main() {{\n    try {{\n        // Load inputs\n        const inputs = JSON.parse(fs.readFileSync('{inputs_file}', 'utf8'));\n\n        // Generate proof\n        const {{ proof, publicSignals }} = await snarkjs.groth16.fullProve(inputs, '{circuit['wasm_path']}', '{circuit['zkey_path']}');\n\n        // Output result\n        console.log(JSON.stringify({{ proof, publicSignals }}));\n        process.exit(0);\n    }} catch (error) {{\n        console.error('Error:', error);\n        process.exit(1);\n    }}\n}}\n\nmain();\n"
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
                f.write(script)
                script_file = f.name
            try:
                proc = await asyncio.create_subprocess_exec(
                    "node",
                    script_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.circuits_dir),
                    env=_node_env(),
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    raise Exception(f"Proof generation failed (NODE_PATH={SNARKJS_NODE_PATH}): {stderr.decode()}")
                return dict(json.loads(stdout.decode()))
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
            # Same fullProve-with-paths pairing as _generate_proof. This path is what
            # /zk/generate and the ML prove endpoints actually call (V23-91).
            script = (
                "\nconst snarkjs = require('snarkjs');\nconst fs = require('fs');\n\n"
                "async function main() {\n    try {\n"
                f"        const inputs = JSON.parse(fs.readFileSync('{inputs_file}', 'utf8'));\n"
                f"        const {{ proof, publicSignals }} = await snarkjs.groth16.fullProve("
                f"inputs, '{wasm_path}', '{zkey_path}');\n"
                f"        const vKey = JSON.parse(fs.readFileSync('{vkey_path}', 'utf8'));\n"
                "        console.log(JSON.stringify({ proof, publicSignals, verificationKey: vKey }));\n"
                "        process.exit(0);\n"
                "    } catch (error) {\n"
                "        console.error('Error:', error.message);\n        process.exit(1);\n"
                "    }\n}\n\nmain();\n"
            )
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
                f.write(script)
                script_file = f.name
            try:
                result = await asyncio.create_subprocess_exec(
                    "node",
                    script_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=_node_env(),
                )
                stdout, stderr = await result.communicate()
                if result.returncode == 0:
                    proof_data: dict[str, Any] = json.loads(stdout.decode())
                    return proof_data
                else:
                    error_msg = stderr.decode() or stdout.decode()
                    raise Exception(f"Proof generation failed (NODE_PATH={SNARKJS_NODE_PATH}): {error_msg}")
            finally:
                os.unlink(script_file)
        finally:
            os.unlink(inputs_file)

    async def _get_circuit_hash(self, circuit_name: str | None = None) -> str:
        """Get hash of current circuit for verification.

        Hashes the proving key of ``circuit_name`` (default ``RECEIPT_CIRCUIT``) so
        the proof's circuit_hash identifies that circuit.
        """
        import hashlib

        circuit = self.available_circuits.get(circuit_name or RECEIPT_CIRCUIT)
        if circuit is None:
            return ""
        zkey_path = circuit["zkey_path"]
        h = hashlib.sha256()
        with open(zkey_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def is_enabled(self) -> bool:
        """Check if ZK proof generation is available"""
        return self.enabled


zk_proof_service = ZKProofService()
