"""
ZK Proof generation service for privacy-preserving receipt attestation
"""

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
import tempfile
import os
import logging

from ..schemas import Receipt, JobResult
from ..config import settings
from ..app_logging import get_logger

logger = get_logger(__name__)




class ZKProofService:
    """Service for generating zero-knowledge proofs for receipts and ML operations"""

    def __init__(self):
        self.circuits_dir = Path(__file__).parent.parent / "zk-circuits"

        # Circuit configurations for different types
        self.circuits = {
            "receipt_simple": {
                "zkey_path": self.circuits_dir / "receipt_simple_0001.zkey",
                "wasm_path": self.circuits_dir / "receipt_simple_js" / "receipt_simple.wasm",
                "vkey_path": self.circuits_dir / "receipt_simple_js" / "verification_key.json"
            },
            "ml_inference_verification": {
                "zkey_path": self.circuits_dir / "ml_inference_verification_0000.zkey",
                "wasm_path": self.circuits_dir / "ml_inference_verification_js" / "ml_inference_verification.wasm",
                "vkey_path": self.circuits_dir / "ml_inference_verification_js" / "verification_key.json"
            },
            "ml_training_verification": {
                "zkey_path": self.circuits_dir / "ml_training_verification_0000.zkey",
                "wasm_path": self.circuits_dir / "ml_training_verification_js" / "ml_training_verification.wasm",
                "vkey_path": self.circuits_dir / "ml_training_verification_js" / "verification_key.json"
            },
            "modular_ml_components": {
                "zkey_path": self.circuits_dir / "modular_ml_components_0001.zkey",
                "wasm_path": self.circuits_dir / "modular_ml_components_js" / "modular_ml_components.wasm",
                "vkey_path": self.circuits_dir / "verification_key.json"
            }
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
        self, 
        receipt: Receipt, 
        job_result: JobResult,
        privacy_level: str = "basic"
    ) -> Optional[Dict[str, Any]]:
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
                "circuit_hash": await self._get_circuit_hash()
            }
            
        except Exception as e:
            logger.error(f"Failed to generate ZK proof: {e}")
            return None

    async def generate_proof(
        self,
        circuit_name: str,
        inputs: Dict[str, Any],
        private_inputs: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
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
                inputs,
                private_inputs,
                circuit_paths["wasm_path"],
                circuit_paths["zkey_path"],
                circuit_paths["vkey_path"]
            )

            # Return proof with verification data
            return {
                "proof_id": f"{circuit_name}_{asyncio.get_event_loop().time()}",
                "proof": proof_data["proof"],
                "public_signals": proof_data["publicSignals"],
                "verification_key": proof_data.get("verificationKey"),
                "circuit_type": circuit_name,
                "optimization_level": "phase3_optimized" if "modular" in circuit_name else "baseline"
            }

        except Exception as e:
            logger.error(f"Failed to generate {circuit_name} proof: {e}")
            return None

    async def verify_proof(
        self,
        proof: Dict[str, Any],
        public_signals: List[str],
        verification_key: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Verify a ZK proof"""
        try:
            # For now, return mock verification - in production, implement actual verification
            return {
                "verified": True,
                "computation_correct": True,
                "privacy_preserved": True
            }
        except Exception as e:
            logger.error(f"Failed to verify proof: {e}")
            return {
                "verified": False,
                "error": str(e)
            }
    
    async def _prepare_inputs(
        self, 
        receipt: Receipt, 
        job_result: JobResult,
        privacy_level: str
    ) -> Dict[str, Any]:
        """Prepare circuit inputs based on privacy level"""
        
        if privacy_level == "basic":
            # Hide computation details, reveal settlement amount
            return {
                "data": [
                    str(receipt.job_id),
                    str(receipt.miner_id),
                    str(job_result.result_hash),
                    str(receipt.pricing.rate)
                ],
                "hash": await self._hash_receipt(receipt)
            }
        
        elif privacy_level == "enhanced":
            # Hide all amounts, prove correctness
            return {
                "settlementAmount": receipt.settlement_amount,
                "timestamp": receipt.timestamp,
                "receipt": self._serialize_receipt(receipt),
                "computationResult": job_result.result_hash,
                "pricingRate": receipt.pricing.rate,
                "minerReward": receipt.miner_reward,
                "coordinatorFee": receipt.coordinator_fee
            }
        
        else:
            raise ValueError(f"Unknown privacy level: {privacy_level}")
    
    async def _hash_receipt(self, receipt: Receipt) -> str:
        """Hash receipt for public verification"""
        # In a real implementation, use Poseidon or the same hash as circuit
        import hashlib
        
        receipt_data = {
            "job_id": receipt.job_id,
            "miner_id": receipt.miner_id,
            "timestamp": receipt.timestamp,
            "pricing": receipt.pricing.dict()
        }
        
        receipt_str = json.dumps(receipt_data, sort_keys=True)
        return hashlib.sha256(receipt_str.encode()).hexdigest()
    
    def _serialize_receipt(self, receipt: Receipt) -> List[str]:
        """Serialize receipt for circuit input"""
        # Convert receipt to field elements for circuit
        return [
            str(receipt.job_id)[:32],  # Truncate for field size
            str(receipt.miner_id)[:32],
            str(receipt.timestamp)[:32],
            str(receipt.settlement_amount)[:32],
            str(receipt.miner_reward)[:32],
            str(receipt.coordinator_fee)[:32],
            "0", "0"  # Padding
        ]
    
    async def _generate_proof(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Generate proof using snarkjs"""
        
        # Write inputs to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
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
        const wasm = fs.readFileSync('{self.wasm_path}');
        const zkey = fs.readFileSync('{self.zkey_path}');
        
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
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(script)
                script_file = f.name
            
            try:
                # Run script
                result = subprocess.run(
                    ["node", script_file],
                    capture_output=True,
                    text=True,
                    cwd=str(self.circuits_dir)
                )
                
                if result.returncode != 0:
                    raise Exception(f"Proof generation failed: {result.stderr}")
                
                # Parse result
                return json.loads(result.stdout)
                
            finally:
                os.unlink(script_file)
                
        finally:
            os.unlink(inputs_file)
    
    async def _generate_proof_generic(
        self,
        public_inputs: Dict[str, Any],
        private_inputs: Optional[Dict[str, Any]],
        wasm_path: Path,
        zkey_path: Path,
        vkey_path: Path
    ) -> Dict[str, Any]:
        """Generate proof using snarkjs with generic circuit paths"""

        # Combine public and private inputs
        inputs = public_inputs.copy()
        if private_inputs:
            inputs.update(private_inputs)

        # Write inputs to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
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
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(script)
                script_file = f.name

            try:
                # Execute the Node.js script
                result = await asyncio.create_subprocess_exec(
                    'node', script_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await result.communicate()

                if result.returncode == 0:
                    proof_data = json.loads(stdout.decode())
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

    async def verify_proof(
        self, 
        proof: Dict[str, Any], 
        public_signals: List[str]
    ) -> bool:
        """Verify a ZK proof"""
        
        if not self.enabled:
            return False
        
        try:
            # Load verification key
            with open(self.vkey_path) as f:
                vkey = json.load(f)
            
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
        console.error('Error:', error);
        process.exit(1);
    }}
}}

main();
"""
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(script)
                script_file = f.name
            
            try:
                result = subprocess.run(
                    ["node", script_file],
                    capture_output=True,
                    text=True,
                    cwd=str(self.circuits_dir)
                )
                
                if result.returncode != 0:
                    logger.error(f"Proof verification failed: {result.stderr}")
                    return False
                
                return result.stdout.strip() == "true"
                
            finally:
                os.unlink(script_file)
                
        except Exception as e:
            logger.error(f"Failed to verify proof: {e}")
            return False
    
    def is_enabled(self) -> bool:
        """Check if ZK proof generation is available"""
        return self.enabled


# Global instance
zk_proof_service = ZKProofService()
