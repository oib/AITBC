import os
import requests
import time

try:
    resp = requests.get("http://127.0.0.1:8182/rpc/head?chain_id=ait-devnet")
    print("Devnet head:", resp.json())
except Exception as e:
    print("Error:", e)
