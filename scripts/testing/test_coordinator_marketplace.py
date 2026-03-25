import requests

try:
    response = requests.get('http://127.0.0.1:8000/v1/marketplace/offers')
    print("Offers:", response.status_code)
    
    response = requests.get('http://127.0.0.1:8000/v1/marketplace/stats')
    print("Stats:", response.status_code)
except Exception as e:
    print("Error:", e)
