import subprocess
import re

def run_cmd(cmd):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )
    
    # Strip ANSI escape sequences and extra whitespace
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_stdout = ansi_escape.sub('', result.stdout).strip()
    
    print(f"Exit code: {result.returncode}")
    print(f"Output:\n{clean_stdout}")
    if result.stderr:
        print(f"Stderr:\n{result.stderr}")
    print("-" * 40)

print("=== TESTING aitbc (10.1.223.93) ===")
base_cmd = ["/home/oib/windsurf/aitbc/cli/venv/bin/aitbc", "--url", "http://10.1.223.93:8000/v1", "--api-key", "client_dev_key_1", "--output", "json"]

run_cmd(base_cmd + ["blockchain", "info"])
run_cmd(base_cmd + ["chain", "list"])
run_cmd(base_cmd + ["node", "list"])
run_cmd(base_cmd + ["client", "submit", "--type", "inference", "--model", "test-model", "--prompt", "test prompt"])

print("\n=== TESTING aitbc1 (10.1.223.40) ===")
base_cmd1 = ["/home/oib/windsurf/aitbc/cli/venv/bin/aitbc", "--url", "http://10.1.223.40:8000/v1", "--api-key", "client_dev_key_1", "--output", "json"]

run_cmd(base_cmd1 + ["blockchain", "info"])
run_cmd(base_cmd1 + ["chain", "list"])
run_cmd(base_cmd1 + ["node", "list"])
run_cmd(base_cmd1 + ["client", "submit", "--type", "inference", "--model", "test-model", "--prompt", "test prompt"])
