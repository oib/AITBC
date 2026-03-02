import re

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/client.py", "r") as f:
    content = f.read()

# Fix the auth header from "X-Api-Key" to "x-api-key" or check how it's sent
# Fastapi headers are case insensitive, but maybe httpx is sending it wrong or it's being stripped?
# Wait! In test_api_submit2.py we sent "X-Api-Key": "client_dev_key_1" and it worked when we used the CLI before we patched the endpoints?
# No, test_api_submit2.py returned 401 {"detail":"invalid api key"}.
# Why is "client_dev_key_1" invalid?
