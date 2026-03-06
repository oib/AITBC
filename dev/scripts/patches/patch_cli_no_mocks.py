import re

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/core/node_client.py", "r") as f:
    content = f.read()

# Fix the authenticate warning so it doesn't pollute stdout when auth is not supported
content = content.replace(
    "print(f\"Warning: Could not authenticate with node {self.config.id}: {e}\")",
    "pass # print(f\"Warning: Could not authenticate with node {self.config.id}: {e}\")"
)

# Replace the mock chain generation with just returning an empty list
content = re.sub(
    r'def _get_mock_chains\(self\).*?def _get_mock_node_info',
    'def _get_mock_chains(self):\n        return []\n\n    def _get_mock_node_info',
    content,
    flags=re.DOTALL
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/core/node_client.py", "w") as f:
    f.write(content)
