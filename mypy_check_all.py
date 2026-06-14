#!/usr/bin/env python3
import subprocess
import glob

files = glob.glob("/opt/aitbc/apps/agent-management/src/**/*.py", recursive=True)
total_errors = 0
all_output = []

for f in files:
    result = subprocess.run(
        ["/opt/aitbc/venv/bin/mypy", "--config-file", "pyproject.toml", f, "--no-error-summary"],
        capture_output=True,
        text=True,
    )
    errors = [line for line in result.stdout.splitlines() if "error:" in line]
    if errors:
        total_errors += len(errors)
        all_output.extend(errors)

print(f"Total errors: {total_errors}")
for line in all_output:
    print(line)
