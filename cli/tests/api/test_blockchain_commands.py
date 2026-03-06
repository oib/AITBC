import subprocess
import re

def run_cmd(cmd):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )
    
    # Strip ANSI escape sequences
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_stdout = ansi_escape.sub('', result.stdout).strip()
    
    print(f"Exit code: {result.returncode}")
    print(f"Output:\n{clean_stdout}")
    if result.stderr:
        print(f"Stderr:\n{result.stderr}")
    print("-" * 40)

print("=== BLOCKCHAIN API TESTS ===")

base_cmd = ["/home/oib/windsurf/aitbc/cli/venv/bin/aitbc", "--url", "http://10.1.223.93:8000/v1", "--api-key", "client_dev_key_1", "--output", "json"]

print("\n--- genesis ---")
run_cmd(base_cmd + ["blockchain", "genesis", "--chain-id", "ait-devnet"])

print("\n--- mempool ---")
run_cmd(base_cmd + ["blockchain", "mempool", "--chain-id", "ait-healthchain"])

print("\n--- head ---")
run_cmd(base_cmd + ["blockchain", "head", "--chain-id", "ait-testnet"])

print("\n--- send ---")
run_cmd(base_cmd + ["blockchain", "send", "--chain-id", "ait-devnet", "--from", "alice", "--to", "bob", "--data", "test", "--nonce", "1"])
