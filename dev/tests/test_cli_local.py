import subprocess
import sys

result = subprocess.run(
    ["/home/oib/windsurf/aitbc/cli/venv/bin/aitbc", "--url", "http://10.1.223.93:8000/v1", "--api-key", "client_dev_key_1", "--debug", "client", "submit", "--type", "inference", "--model", "test-model", "--prompt", "test prompt"],
    capture_output=True,
    text=True
)
print("STDOUT:")
print(result.stdout)
print("STDERR:")
print(result.stderr)
