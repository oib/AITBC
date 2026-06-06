const fs = require("fs");
const snarkjs = require("snarkjs");

async function generateProof() {
    console.log("Generating ZK proof for receipt attestation...");
    
    try {
        // Load the WASM circuit
        const wasmBuffer = fs.readFileSync("receipt.wasm");
        
        // Load the zKey (proving key)
        const zKeyBuffer = fs.readFileSync("receipt_0001.zkey");
        
        // Prepare inputs
        // In a real implementation, these would come from actual receipt data
        const input = {
            // Private inputs (receipt data)
            data: [
                "12345", // job ID
                "67890", // miner ID
                "1000",  // computation result
                "500"    // pricing rate
            ],
            
            // Public inputs
            hash: "1234567890123456789012345678901234567890123456789012345678901234"
        };
        
        console.log("Input:", input);
        
        // Calculate witness
        console.log("Calculating witness...");
        const { witness, wasm } = await snarkjs.wtns.calculate(input, wasmBuffer, wasmBuffer);
        
        // Generate proof
        console.log("Generating proof...");
        const { proof, publicSignals } = await snarkjs.groth16.prove(zKeyBuffer, witness);
        
        // Save proof and public signals
        fs.writeFileSync("proof.json", JSON.stringify(proof, null, 2));
        fs.writeFileSync("public.json", JSON.stringify(publicSignals, null, 2));
        
        console.log("Proof generated successfully!");
        console.log("Proof saved to proof.json");
        console.log("Public signals saved to public.json");
        
        // Verify the proof
        console.log("\nVerifying proof...");
        const vKey = JSON.parse(fs.readFileSync("verification_key.json"));
        const verified = await snarkjs.groth16.verify(vKey, publicSignals, proof);
        
        if (verified) {
            console.log("✅ Proof verified successfully!");
        } else {
            console.log("❌ Proof verification failed!");
        }
        
        return { proof, publicSignals };
        
    } catch (error) {
        console.error("Error generating proof:", error);
        throw error;
    }
}

// Generate a sample receipt hash for testing
function generateReceiptHash(receipt) {
    // In a real implementation, use Poseidon or other hash function
    // For now, return a placeholder
    return "1234567890123456789012345678901234567890123456789012345678901234";
}

// Run if called directly
if (require.main === module) {
    generateProof()
        .then(() => process.exit(0))
        .catch(error => {
            console.error(error);
            process.exit(1);
        });
}

module.exports = { generateProof, generateReceiptHash };
