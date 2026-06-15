# WebSocket API Documentation

> **Important:** This document describes the WebSocket API endpoints. For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

The AITBC platform provides WebSocket endpoints for real-time updates on job status, blockchain events, and marketplace activities.

## Overview

WebSocket connections provide real-time, bidirectional communication with the AITBC services. This is particularly useful for:
- Monitoring job status changes
- Receiving blockchain event notifications
- Tracking marketplace offers and transactions
- Real-time system health monitoring

## Connection URLs

> **Note:** Port assignments below represent designed configuration. For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

### Coordinator API WebSocket

- Development: `ws://localhost:8203/v1/jobs/{job_id}/ws`
- Production: `wss://aitbc.bubuit.net/api/v1/jobs/{job_id}/ws`

### Blockchain API WebSocket

- Development: `ws://localhost:8202/v1/events`
- Production: `wss://aitbc.bubuit.net/api/v1/events`

### Marketplace WebSocket

- Development: `ws://localhost:8102/v1/events`
- Production: `wss://aitbc.bubuit.net/api/v1/events`

## Authentication

WebSocket connections require authentication via query parameters:

```
ws://localhost:8203/v1/jobs/{job_id}/ws?api_key=your-api-key
```

Alternatively, use the `X-Api-Key` header during the WebSocket handshake.

## Job Status WebSocket

### Endpoint

```
ws://localhost:8203/v1/jobs/{job_id}/ws
```

### Message Format

Status updates are sent as JSON messages:

```json
{
  "job_id": "abc123",
  "state": "RUNNING",
  "assigned_miner_id": "miner-456",
  "timestamp": "2026-05-11T10:00:00Z",
  "progress": 0.5
}
```

### States

- `QUEUED` - Job waiting for miner assignment
- `RUNNING` - Job currently processing
- `COMPLETED` - Job finished successfully
- `FAILED` - Job failed with error
- `CANCELLED` - Job cancelled by user
- `EXPIRED` - Job exceeded TTL

### Example (Python)

```python
import asyncio
import websockets
import json

async def monitor_job(job_id: str, api_key: str):
    uri = f"ws://localhost:8203/v1/jobs/{job_id}/ws?api_key={api_key}"

    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            data = json.loads(message)
            print(f"State: {data['state']}")
            print(f"Progress: {data.get('progress', 0)}")

            if data['state'] in ['COMPLETED', 'FAILED', 'CANCELLED', 'EXPIRED']:
                break

asyncio.run(monitor_job("job-id", "your-api-key"))
```

### Example (JavaScript)

```javascript
const ws = new WebSocket('ws://localhost:8203/v1/jobs/job-id/ws?api_key=your-api-key');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`State: ${data.state}`);
  console.log(`Progress: ${data.progress || 0}`);

  if (['COMPLETED', 'FAILED', 'CANCELLED', 'EXPIRED'].includes(data.state)) {
    ws.close();
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('WebSocket connection closed');
};
```

### Example (cURL with websocat)

```bash
websocat ws://localhost:8203/v1/jobs/job-id/ws?api_key=your-api-key
```

## Blockchain Events WebSocket

### Endpoint

```
ws://localhost:8202/v1/events
```

### Message Format

Blockchain events are sent as JSON messages:

```json
{
  "type": "new_block",
  "block": {
    "height": 12346,
    "hash": "0x...",
    "timestamp": "2026-05-11T10:00:00Z",
    "transactions": []
  }
}
```

### Event Types

- `new_block` - New block mined
- `transaction_confirmed` - Transaction confirmed
- `transaction_pending` - Transaction submitted to mempool
- `fork_detected` - Blockchain fork detected
- `sync_status` - Node sync status update

### Example (Python)

```python
import asyncio
import websockets
import json

async def monitor_blockchain():
    uri = "ws://localhost:8202/v1/events"

    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            data = json.loads(message)

            if data['type'] == 'new_block':
                print(f"New block: {data['block']['height']}")
            elif data['type'] == 'transaction_confirmed':
                print(f"Transaction confirmed: {data['tx_hash']}")

asyncio.run(monitor_blockchain())
```

### Example (JavaScript)

```javascript
const ws = new WebSocket('ws://localhost:8202/v1/events');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  switch (data.type) {
    case 'new_block':
      console.log(`New block: ${data.block.height}`);
      break;
    case 'transaction_confirmed':
      console.log(`Transaction confirmed: ${data.tx_hash}`);
      break;
    default:
      console.log(`Unknown event type: ${data.type}`);
  }
};
```

## Marketplace WebSocket

### Endpoint

```
ws://localhost:8102/v1/events
```

### Message Format

Marketplace events are sent as JSON messages:

```json
{
  "type": "new_offer",
  "offer": {
    "id": "offer-123",
    "gpu_type": "nvidia-rtx-3090",
    "gpu_memory": 24,
    "price_per_hour": 0.5,
    "currency": "AITBC"
  }
}
```

### Event Types

- `new_offer` - New GPU offer posted
- `offer_matched` - Offer matched with job
- `offer_expired` - Offer expired
- `offer_cancelled` - Offer cancelled by provider
- `price_update` - Offer price updated

### Example (Python)

```python
import asyncio
import websockets
import json

async def monitor_marketplace():
    uri = "ws://localhost:8102/v1/events"

    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            data = json.loads(message)

            if data['type'] == 'new_offer':
                offer = data['offer']
                print(f"New offer: {offer['gpu_type']}, {offer['gpu_memory']}GB, ${offer['price_per_hour']}/hr")

asyncio.run(monitor_marketplace())
```

## Connection Management

### Heartbeat

WebSocket connections should send periodic heartbeat messages to keep the connection alive:

```python
import asyncio
import websockets

async def send_heartbeat(websocket, interval=30):
    while True:
        try:
            await websocket.send(json.dumps({"type": "ping"}))
            await asyncio.sleep(interval)
        except:
            break
```

### Reconnection Logic

Implement automatic reconnection with exponential backoff:

```python
import asyncio
import websockets

async def connect_with_retry(uri, max_retries=5):
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            async with websockets.connect(uri) as websocket:
                return websocket
        except:
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                raise
```

### Error Handling

Handle common WebSocket errors:

```python
async def handle_websocket_errors(websocket):
    try:
        async for message in websocket:
            # Process message
            pass
    except websockets.exceptions.ConnectionClosed:
        print("Connection closed")
    except websockets.exceptions.WebSocketException as e:
        print(f"WebSocket error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
```

## Security Considerations

### Use WSS in Production

Always use secure WebSocket connections (`wss://`) in production:

```javascript
// Production
const ws = new WebSocket('wss://aitbc.bubuit.net/api/v1/jobs/job-id/ws');

// Development only
const ws = new WebSocket('ws://localhost:8203/v1/jobs/job-id/ws');
```

### API Key Protection

- Never expose API keys in client-side code
- Use environment variables or secure token storage
- Rotate API keys regularly
- Implement rate limiting on WebSocket connections

### Origin Validation

The server validates the `Origin` header to prevent CSRF attacks. Ensure your client sends the correct origin:

```javascript
const ws = new WebSocket('ws://localhost:8203/v1/jobs/job-id/ws', [], {
  headers: {
    'Origin': 'https://your-domain.com'
  }
});
```

## Rate Limiting

WebSocket connections are rate limited:
- Maximum connections per IP: 10
- Maximum messages per second: 100
- Connection duration limit: 24 hours

Exceeding limits will result in connection termination.

## Testing

### Python Testing

```python
import pytest
import asyncio
import websockets

@pytest.mark.asyncio
async def test_job_websocket():
    uri = "ws://localhost:8203/v1/jobs/test-job/ws?api_key=test-key"

    async with websockets.connect(uri) as websocket:
        message = await websocket.recv()
        data = json.loads(message)
        assert 'state' in data
```

### JavaScript Testing

```javascript
import { describe, it, expect, vi } from 'vitest';

describe('WebSocket', () => {
  it('should connect to job WebSocket', async () => {
    const WebSocket = vi.fn();
    WebSocket.mockReturnValueOnce({
      onmessage: vi.fn(),
      onerror: vi.fn(),
      onclose: vi.fn()
    });

    const ws = new WebSocket('ws://localhost:8203/v1/jobs/test/ws');
    expect(WebSocket).toHaveBeenCalledWith('ws://localhost:8203/v1/jobs/test/ws');
  });
});
```

## Troubleshooting

### Connection Refused

- Check if the service is running
- Verify the URL and port are correct
- Check firewall rules

### Authentication Failed

- Verify API key is valid
- Check API key is passed correctly (query parameter or header)
- Ensure API key has required permissions

### Connection Drops

- Check network stability
- Implement reconnection logic
- Verify server logs for errors

### No Messages Received

- Verify event subscription
- Check if events are being generated
- Monitor server logs

## Best Practices

1. **Always implement reconnection logic** - Network connections can be unstable
2. **Use exponential backoff** - Don't flood the server with reconnection attempts
3. **Clean up connections** - Close WebSocket connections when no longer needed
4. **Handle errors gracefully** - Provide user feedback for connection issues
5. **Rate limit client-side** - Don't send messages faster than the server can handle
6. **Use message queuing** - Buffer messages if the connection is temporarily unavailable
7. **Monitor connection health** - Implement heartbeat/ping-pong mechanism
8. **Log connection events** - Track connection lifecycle for debugging
