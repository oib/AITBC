import json

wallet_data = {
    "name": "test_wallet",
    "type": "hd",
    "address": "aitbc1genesis",
    "private_key": "dummy",
    "public_key": "dummy",
    "encrypted": False,
    "transactions": [],
    "balance": 1000000
}

import os
import pathlib

wallet_dir = pathlib.Path("/root/.aitbc/wallets")
wallet_dir.mkdir(parents=True, exist_ok=True)
wallet_path = wallet_dir / "test_wallet.json"

with open(wallet_path, "w") as f:
    json.dump(wallet_data, f)
