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

from ..models import Receipt, JobResult
from ..settings import settings
from ..logging import get_logger

logger = get_logger(__name__)


class ZKProofService:
    """Service for generating zero-knowledge proofs for receipts"""
    
    def __init__(self):
        self.circuits_dir = Path(__file__).parent.parent.parent.parent / "apps" / "zk-circuits"
        self.zkey_path = self.circuits_dir / "receipt_0001.zkey"
        self.wasm_path = self.circuits_dir / "receipt.wasm"
        self.vkey_path = self.circuits_dir / "verification_key.json"
        
        # Verify circuit files exist
        if not all(p.exists() for p in [self.zkey_path, self.wasm_path, self.vkey_path]):
            logger.warning("ZK circuit files not found. Proof generation disabled.")
            self.enabled = False
        else:
            self.enabled = True
    
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
    
    async def _get_circuit_hash(self) -> str:
        """Get hash of circuit for verification"""
        # In a real implementation, return the hash of the circuit
        # This ensures the proof is for the correct circuit version
        return "0x1234567890abcdef"
    
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
