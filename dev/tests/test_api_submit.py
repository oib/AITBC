import requests

data = {
    "payload": {"type": "inference", "model": "test-model", "prompt": "test prompt"},
    "ttl_seconds": 900
}

try:
    resp = requests.post("http://10.1.223.93:8000/v1/jobs", json=data, headers={"X-Api-Key": "client_dev_key_1"})
    print(resp.status_code, resp.text)
except Exception as e:
    print(e)
