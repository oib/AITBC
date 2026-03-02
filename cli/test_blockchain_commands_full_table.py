import subprocess
import os
import re

def run_cmd(cmd):
    print(f"Running: {' '.join(cmd)}")
    env = os.environ.copy()
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env
    )
    
    # Strip ANSI escape sequences
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_stdout = ansi_escape.sub('', result.stdout).strip()
    
    print(f"Exit code: {result.returncode}")
    print(f"Output:\n{clean_stdout}")
    if result.stderr:
        print(f"Stderr:\n{result.stderr.strip()}")
    print("-" * 40)

print("=== NEW BLOCKCHAIN API TESTS (TABLE OUTPUT) ===")

base_cmd = ["/home/oib/windsurf/aitbc/cli/venv/bin/aitbc", "--url", "http://10.1.223.93:8000/v1", "--api-key", "client_dev_key_1", "--output", "table"]

print("\n--- faucet (minting devnet funds to alice) ---")
run_cmd(base_cmd + ["blockchain", "faucet", "--address", "alice", "--amount", "5000000000"])

print("\n--- balance (checking alice's balance) ---")
run_cmd(base_cmd + ["blockchain", "balance", "--address", "alice"])

print("\n--- genesis ---")
run_cmd(base_cmd + ["blockchain", "genesis", "--chain-id", "ait-devnet"])

print("\n--- transactions ---")
run_cmd(base_cmd + ["blockchain", "transactions", "--chain-id", "ait-devnet"])

print("\n--- head ---")
run_cmd(base_cmd + ["blockchain", "head", "--chain-id", "ait-testnet"])

print("\n--- send (alice sending devnet funds to bob) ---")
run_cmd(base_cmd + ["blockchain", "send", "--chain-id", "ait-devnet", "--from", "alice", "--to", "bob", "--data", "test", "--nonce", "1"])
