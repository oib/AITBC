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

from aitbc import get_logger
from ..schemas import JobResult, Receipt

logger = get_logger(__name__)


class ZKProofService:
    """Service for generating zero-knowledge proofs for receipts and ML operations"""

    def __init__(self) -> None:
        self.circuits_dir = Path(__file__).parent.parent / "zk-circuits"

        # Circuit configurations for different types
        self.circuits = {
            "receipt_simple": {
                "zkey_path": self.circuits_dir / "receipt_simple_0001.zkey",
                "wasm_path": self.circuits_dir / "receipt_simple_js" / "receipt_simple.wasm",
                "vkey_path": self.circuits_dir / "receipt_simple_js" / "verification_key.json",
            },
            "ml_inference_verification": {
                "zkey_path": self.circuits_dir / "ml_inference_verification_0000.zkey",
                "wasm_path": self.circuits_dir / "ml_inference_verification_js" / "ml_inference_verification.wasm",
                "vkey_path": self.circuits_dir / "ml_inference_verification_js" / "verification_key.json",
            },
            "ml_training_verification": {
                "zkey_path": self.circuits_dir / "ml_training_verification_0000.zkey",
                "wasm_path": self.circuits_dir / "ml_training_verification_js" / "ml_training_verification.wasm",
                "vkey_path": self.circuits_dir / "ml_training_verification_js" / "verification_key.json",
            },
            "modular_ml_components": {
                "zkey_path": self.circuits_dir / "modular_ml_components_0001.zkey",
                "wasm_path": self.circuits_dir / "modular_ml_components_js" / "modular_ml_components.wasm",
                "vkey_path": self.circuits_dir / "verification_key.json",
            },
        }

        # Check which circuits are available
        self.available_circuits = {}
        for circuit_name, paths in self.circuits.items():
            if all(p.exists() for p in paths.values()):
                self.available_circuits[circuit_name] = paths
                logger.info(f"✅ Circuit '{circuit_name}' available at {paths['zkey_path'].parent}")
            else:
                logger.warning(f"❌ Circuit '{circuit_name}' missing files")

        logger.info(f"Available circuits: {list(self.available_circuits.keys())}")
        self.enabled = len(self.available_circuits) > 0

    async def generate_receipt_proof(
        self, receipt: Receipt, job_result: JobResult, privacy_level: str = "basic"
    ) -> dict[str, Any] | None:
        """Generate a ZK proof for a receipt"""

        if not self.enabled:
            logger.warning("ZK proof generation not available")
            return None

        try:
            # Prepare circuit inputs based on privacy level
            inputs = await self._prepare_inputs(receipt, job_result, privacy_level)

            # Generate proof using snarkjs
            proof_data = await self._generate_proof(inputs)

            # Return proof with verification data
            return {
                "proof": proof_data["proof"],
                "public_signals": proof_data["publicSignals"],
                "privacy_level": privacy_level,
                "circuit_hash": await self._get_circuit_hash(),
            }

        except Exception as e:
            logger.error(f"Failed to generate ZK proof: {e}")
            return None

    async def generate_proof(
        self, circuit_name: str, inputs: dict[str, Any], private_inputs: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Generate a ZK proof for any supported circuit type"""

        if not self.enabled:
            logger.warning("ZK proof generation not available")
            return None

        if circuit_name not in self.available_circuits:
            logger.error(f"Circuit '{circuit_name}' not available. Available: {list(self.available_circuits.keys())}")
            return None

        try:
            # Get circuit paths
            circuit_paths = self.available_circuits[circuit_name]

            # Generate proof using snarkjs with circuit-specific paths
            proof_data = await self._generate_proof_generic(
                inputs, private_inputs, circuit_paths["wasm_path"], circuit_paths["zkey_path"], circuit_paths["vkey_path"]
            )

            # Return proof with verification data
            return {
                "proof_id": f"{circuit_name}_{asyncio.get_event_loop().time()}",
                "proof": proof_data["proof"],
                "public_signals": proof_data["publicSignals"],
                "verification_key": proof_data.get("verificationKey"),
                "circuit_type": circuit_name,
                "optimization_level": "phase3_optimized" if "modular" in circuit_name else "baseline",
            }

        except Exception as e:
            logger.error(f"Failed to generate {circuit_name} proof: {e}")
            return None

    async def verify_proof(
        self, proof: dict[str, Any], public_signals: list[str], verification_key: dict[str, Any] | None = None, test_mode: bool = False
    ) -> dict[str, Any]:
        """Verify a ZK proof using Groth16 verification
        
        Args:
            proof: The ZK proof to verify
            public_signals: Public signals for the proof
            verification_key: Optional verification key (uses default if not provided)
            test_mode: If True, accepts mock proofs for development/testing
        """
        try:
            if not self.enabled:
                return {"verified": False, "error": "ZK proof service not enabled"}
            
            # Test mode: accept mock proofs for development
            if test_mode:
                logger.info("Test mode enabled: accepting mock proof without cryptographic verification")
                return {
                    "verified": True,
                    "computation_correct": True,
                    "privacy_preserved": True,
                    "test_mode": True
                }

            # Use provided verification key or load from default circuit
            if verification_key:
                vkey = verification_key
            else:
                # Try to load from the first available circuit's verification key
                if not self.available_circuits:
                    return {"verified": False, "error": "No circuits available for verification"}
                
                # Use the first available circuit's verification key
                first_circuit = list(self.available_circuits.values())[0]
                vkey_path = first_circuit["vkey_path"]
                
                try:
                    with open(vkey_path) as f:
                        vkey = json.load(f)
                except FileNotFoundError:
                    return {"verified": False, "error": f"Verification key not found at {vkey_path}"}

            # Create verification script
            script = f"""
const snarkjs = require('snarkjs');

async function main() {{
    try {{
        const vKey = {json.dumps(vkey)};
        const proof = {json.dumps(proof)};
        const publicSignals = {json.dumps(public_signals)};

        const verified = await snarkjs.groth16.verify(vKey, publicSignals, proof);
        console.log(verified);
    }} catch (error) {{
        console.error('Error:', error.message);
        process.exit(1);
    }}
}}

main();
"""

            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
                f.write(script)
                script_file = f.name

            try:
                result = subprocess.run(["node", script_file], capture_output=True, text=True, cwd=str(self.circuits_dir))

                if result.returncode != 0:
                    logger.error(f"Proof verification failed: {result.stderr}")
                    return {"verified": False, "computation_correct": False, "privacy_preserved": False, "error": result.stderr}

                is_verified = result.stdout.strip() == "true"
                return {
                    "verified": is_verified,
                    "computation_correct": is_verified,
                    "privacy_preserved": is_verified
                }

            finally:
                os.unlink(script_file)

        except Exception as e:
            logger.error(f"Failed to verify proof: {e}")
            return {"verified": False, "error": str(e)}

    async def _prepare_inputs(self, receipt: Receipt, job_result: JobResult, privacy_level: str) -> dict[str, Any]:
        """Prepare circuit inputs based on privacy level"""

        if privacy_level == "basic":
            # Hide computation details, reveal settlement amount
            return {
                "data": [str(receipt.receiptId), str(receipt.miner), str(getattr(job_result, 'output_hash', '')), str((receipt.payload or {}).get('rate', 0))],
                "hash": await self._hash_receipt(receipt),
            }

        elif privacy_level == "enhanced":
            payload = receipt.payload or {}
            return {
                "settlementAmount": payload.get("settlement_amount", 0),
                "timestamp": receipt.issuedAt.isoformat(),
                "receipt": self._serialize_receipt(receipt),
                "computationResult": getattr(job_result, 'output_hash', ''),
                "pricingRate": payload.get("rate", 0),
                "minerReward": payload.get("miner_reward", 0),
                "coordinatorFee": payload.get("coordinator_fee", 0),
            }

        else:
            raise ValueError(f"Unknown privacy level: {privacy_level}")

    async def _hash_receipt(self, receipt: Receipt) -> str:
        """Hash receipt for public verification"""
        # In a real implementation, use Poseidon or the same hash as circuit
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
        # Convert receipt to field elements for circuit
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
        """Generate proof using snarkjs"""

        # Write inputs to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(inputs, f)
            inputs_file = f.name

        try:
            # Create Node.js script for proof generation
            script = f"""
const snarkjs = require('snarkjs');
const fs = require('fs');

async function main() {{
    try {{
        // Load inputs
        const inputs = JSON.parse(fs.readFileSync('{inputs_file}', 'utf8'));

        // Load circuit
        const wasm = fs.readFileSync('{list(self.available_circuits.values())[0]["wasm_path"]}');
        const zkey = fs.readFileSync('{list(self.available_circuits.values())[0]["zkey_path"]}');

        // Calculate witness
        const {{ witness }} = await snarkjs.wtns.calculate(inputs, wasm, wasm);

        // Generate proof
        const {{ proof, publicSignals }} = await snarkjs.groth16.prove(zkey, witness);

        // Output result
        console.log(JSON.stringify({{ proof, publicSignals }}));
    }} catch (error) {{
        console.error('Error:', error);
        process.exit(1);
    }}
}}

main();
"""

            # Write script to temporary file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
                f.write(script)
                script_file = f.name

            try:
                # Run script
                result = subprocess.run(["node", script_file], capture_output=True, text=True, cwd=str(self.circuits_dir))

                if result.returncode != 0:
                    raise Exception(f"Proof generation failed: {result.stderr}")

                # Parse result
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

        # Combine public and private inputs
        inputs = public_inputs.copy()
        if private_inputs:
            inputs.update(private_inputs)

        # Write inputs to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(inputs, f)
            inputs_file = f.name

        try:
            # Create Node.js script for proof generation
            script = f"""
const snarkjs = require('snarkjs');
const fs = require('fs');

async function main() {{
    try {{
        // Load inputs
        const inputs = JSON.parse(fs.readFileSync('{inputs_file}', 'utf8'));

        // Load circuit files
        const wasm = fs.readFileSync('{wasm_path}');
        const zkey = fs.readFileSync('{zkey_path}');

        // Calculate witness
        const {{ witness }} = await snarkjs.wtns.calculate(inputs, wasm);

        // Generate proof
        const {{ proof, publicSignals }} = await snarkjs.groth16.prove(zkey, witness);

        // Load verification key
        const vKey = JSON.parse(fs.readFileSync('{vkey_path}', 'utf8'));

        // Output result
        console.log(JSON.stringify({{ proof, publicSignals, verificationKey: vKey }}));
    }} catch (error) {{
        console.error('Error:', error.message);
        process.exit(1);
    }}
}}

main();
"""

            # Write script to temporary file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
                f.write(script)
                script_file = f.name

            try:
                # Execute the Node.js script
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
                # Clean up temporary files
                os.unlink(script_file)

        finally:
            # Clean up inputs file
            os.unlink(inputs_file)

    async def _get_circuit_hash(self) -> str:
        """Get hash of current circuit for verification"""
        # In a real implementation, compute hash of circuit files
        return "placeholder_hash"

    def is_enabled(self) -> bool:
        """Check if ZK proof generation is available"""
        return self.enabled


# Global instance
zk_proof_service = ZKProofService()
