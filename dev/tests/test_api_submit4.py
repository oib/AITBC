import requests

resp = requests.post("http://127.0.0.1:8000/v1/jobs", json={
    "payload": {"type": "inference", "model": "test-model", "prompt": "test prompt"},
    "ttl_seconds": 900
}, headers={"X-Api-Key": "client_dev_key_1"})
print(resp.status_code, resp.text)
