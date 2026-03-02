import re
import os
from glob import glob

# The issue is that config.coordinator_url in the CLI already contains "/v1" if run with `--url http://127.0.0.1:8000/v1`
# Thus f"{config.coordinator_url}/v1/jobs" results in "http://127.0.0.1:8000/v1/v1/jobs" which is a 404!
# Let's fix ALL files in cli/aitbc_cli/commands/ to remove the extra /v1 when hitting the coordinator.

cli_commands_dir = "/home/oib/windsurf/aitbc/cli/aitbc_cli/commands"
for filepath in glob(os.path.join(cli_commands_dir, "*.py")):
    with open(filepath, "r") as f:
        content = f.read()
    
    # We want to replace {config.coordinator_url}/v1/ with {config.coordinator_url}/
    new_content = content.replace('{config.coordinator_url}/v1/', '{config.coordinator_url}/')
    
    if new_content != content:
        with open(filepath, "w") as f:
            f.write(new_content)
            print(f"Patched {filepath}")
