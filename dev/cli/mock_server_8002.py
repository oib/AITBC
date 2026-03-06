import uvicorn
from fastapi import FastAPI

app = FastAPI()

@app.get('/blockchain/status')
async def blockchain_status():
    return {
        'status': 'connected',
        'height': 12345,
        'hash': '0x1234567890abcdef',
        'timestamp': '2026-03-04T17:10:00Z',
        'tx_count': 678
    }

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=8002)
