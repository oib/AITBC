import pytest
import websockets
import asyncio
import json

WS_URL = "ws://127.0.0.1:8000/v1/multi-modal-rl/fusion"

@pytest.mark.asyncio
async def test_websocket_fusion_stream():
    # First get a valid fusion model via REST (mocking it for the test)
    import httpx
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "http://127.0.0.1:8000/v1/multi-modal-rl/fusion/models",
            json={
                "model_name": "StreamAnalyzer",
                "version": "1.0.0",
                "fusion_type": "cross_domain",
                "base_models": ["gemma3:1b"],
                "input_modalities": ["text"],
                "fusion_strategy": "ensemble_fusion"
            }
        )
        data = res.json()
        fusion_id = data.get("fusion_id", data.get("id"))
        
    uri = f"{WS_URL}/{fusion_id}/stream"
    try:
        async with websockets.connect(uri) as websocket:
            # Send test payload
            payload = {
                "text": "Streaming test data",
                "structured_data": {"test": True}
            }
            await websocket.send(json.dumps(payload))
            
            # Receive response
            response_str = await websocket.recv()
            response = json.loads(response_str)
            
            assert "combined_result" in response
            assert "metadata" in response
            assert response["metadata"]["protocol"] == "websocket"
            assert response["metadata"]["processing_time"] > 0
    except Exception as e:
        pytest.fail(f"WebSocket test failed: {e}")

