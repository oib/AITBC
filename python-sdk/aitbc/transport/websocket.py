"""
WebSocket transport implementation for AITBC Python SDK
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, AsyncIterator, Callable
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK

from .base import Transport, TransportError, TransportConnectionError, TransportRequestError

logger = logging.getLogger(__name__)


class WebSocketTransport(Transport):
    """WebSocket transport for real-time updates"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.ws_url = config['ws_url']
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._subscriptions: Dict[str, Dict[str, Any]] = {}
        self._message_handlers: Dict[str, Callable] = {}
        self._message_queue = asyncio.Queue()
        self._consumer_task: Optional[asyncio.Task] = None
        self._heartbeat_interval = config.get('heartbeat_interval', 30)
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._reconnect_enabled = config.get('reconnect', True)
        self._max_reconnect_attempts = config.get('max_reconnect_attempts', 5)
        self._reconnect_delay = config.get('reconnect_delay', 5)
        self._ping_timeout = config.get('ping_timeout', 20)
        self._close_code: Optional[int] = None
        self._close_reason: Optional[str] = None
    
    async def connect(self) -> None:
        """Connect to WebSocket"""
        try:
            # Prepare connection parameters
            extra_headers = self.config.get('headers', {})
            ping_interval = self.config.get('ping_interval', self._heartbeat_interval)
            ping_timeout = self._ping_timeout
            
            # Connect to WebSocket
            logger.info(f"Connecting to WebSocket: {self.ws_url}")
            self.websocket = await websockets.connect(
                self.ws_url,
                extra_headers=extra_headers,
                ping_interval=ping_interval,
                ping_timeout=ping_timeout,
                close_timeout=self.config.get('close_timeout', 10)
            )
            
            # Start consumer task
            self._consumer_task = asyncio.create_task(self._consume_messages())
            
            # Start heartbeat task
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
            
            self._connected = True
            logger.info("WebSocket transport connected")
            
        except Exception as e:
            logger.error(f"Failed to connect WebSocket: {e}")
            raise TransportConnectionError(f"WebSocket connection failed: {e}")
    
    async def disconnect(self) -> None:
        """Disconnect WebSocket"""
        self._connected = False
        
        # Cancel tasks
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Close WebSocket
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
            finally:
                self.websocket = None
        
        logger.info("WebSocket transport disconnected")
    
    async def request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Send request via WebSocket"""
        await self.ensure_connected()
        
        if not self.websocket:
            raise TransportConnectionError("WebSocket not connected")
        
        # Generate request ID
        request_id = self._generate_id()
        
        # Create message
        message = {
            'id': request_id,
            'type': 'request',
            'method': method,
            'path': path,
            'data': data,
            'params': params,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Send request
        await self._send_message(message)
        
        # Wait for response
        timeout = timeout or self.config.get('request_timeout', 30)
        
        try:
            response = await asyncio.wait_for(
                self._wait_for_response(request_id),
                timeout=timeout
            )
            return response
        except asyncio.TimeoutError:
            raise TransportError(f"Request timed out after {timeout}s")
    
    async def stream(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream responses from WebSocket"""
        await self.ensure_connected()
        
        # Create subscription
        subscription_id = self._generate_id()
        
        # Subscribe
        message = {
            'id': subscription_id,
            'type': 'subscribe',
            'method': method,
            'path': path,
            'data': data,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self._send_message(message)
        
        # Store subscription
        self._subscriptions[subscription_id] = {
            'method': method,
            'path': path,
            'created_at': datetime.utcnow()
        }
        
        try:
            # Yield messages as they come
            async for message in self._stream_subscription(subscription_id):
                yield message
        finally:
            # Unsubscribe
            await self._unsubscribe(subscription_id)
    
    async def subscribe(
        self,
        event: str,
        callback: Callable[[Dict[str, Any]], None],
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Subscribe to events"""
        await self.ensure_connected()
        
        subscription_id = self._generate_id()
        
        # Store subscription with callback
        self._subscriptions[subscription_id] = {
            'event': event,
            'callback': callback,
            'data': data,
            'created_at': datetime.utcnow()
        }
        
        # Send subscription message
        message = {
            'id': subscription_id,
            'type': 'subscribe',
            'event': event,
            'data': data,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self._send_message(message)
        
        logger.info(f"Subscribed to event: {event}")
        return subscription_id
    
    async def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from events"""
        if subscription_id in self._subscriptions:
            # Send unsubscribe message
            message = {
                'id': subscription_id,
                'type': 'unsubscribe',
                'timestamp': datetime.utcnow().isoformat()
            }
            
            await self._send_message(message)
            
            # Remove subscription
            del self._subscriptions[subscription_id]
            
            logger.info(f"Unsubscribed: {subscription_id}")
    
    async def emit(self, event: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit event to server"""
        await self.ensure_connected()
        
        message = {
            'type': 'event',
            'event': event,
            'data': data,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self._send_message(message)
    
    async def _send_message(self, message: Dict[str, Any]) -> None:
        """Send message to WebSocket"""
        if not self.websocket:
            raise TransportConnectionError("WebSocket not connected")
        
        try:
            await self.websocket.send(json.dumps(message))
            logger.debug(f"Sent WebSocket message: {message.get('type', 'unknown')}")
        except ConnectionClosed:
            await self._handle_disconnect()
            raise TransportConnectionError("WebSocket connection closed")
        except Exception as e:
            raise TransportError(f"Failed to send message: {e}")
    
    async def _consume_messages(self) -> None:
        """Consume messages from WebSocket"""
        while self._connected:
            try:
                # Wait for message
                message = await asyncio.wait_for(
                    self.websocket.recv(),
                    timeout=self._heartbeat_interval * 2
                )
                
                # Parse message
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON message: {message}")
                    continue
                
                # Handle message
                await self._handle_message(data)
                
            except asyncio.TimeoutError:
                # No message received, check connection
                continue
            except ConnectionClosedOK:
                logger.info("WebSocket closed normally")
                break
            except ConnectionClosedError as e:
                logger.warning(f"WebSocket connection closed: {e}")
                await self._handle_disconnect()
                break
            except Exception as e:
                logger.error(f"Error consuming message: {e}")
                break
    
    async def _handle_message(self, data: Dict[str, Any]) -> None:
        """Handle incoming message"""
        message_type = data.get('type')
        
        if message_type == 'response':
            # Request response
            await self._message_queue.put(data)
        
        elif message_type == 'event':
            # Event message
            await self._handle_event(data)
        
        elif message_type == 'subscription':
            # Subscription update
            await self._handle_subscription_update(data)
        
        elif message_type == 'error':
            # Error message
            logger.error(f"WebSocket error: {data.get('message')}")
        
        else:
            logger.warning(f"Unknown message type: {message_type}")
    
    async def _handle_event(self, data: Dict[str, Any]) -> None:
        """Handle event message"""
        event = data.get('event')
        event_data = data.get('data')
        
        # Find matching subscriptions
        for sub_id, sub in self._subscriptions.items():
            if sub.get('event') == event:
                callback = sub.get('callback')
                if callback:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(event_data)
                        else:
                            callback(event_data)
                    except Exception as e:
                        logger.error(f"Error in event callback: {e}")
    
    async def _handle_subscription_update(self, data: Dict[str, Any]) -> None:
        """Handle subscription update"""
        subscription_id = data.get('subscription_id')
        status = data.get('status')
        
        if subscription_id in self._subscriptions:
            sub = self._subscriptions[subscription_id]
            sub['status'] = status
            
            if status == 'confirmed':
                logger.info(f"Subscription confirmed: {subscription_id}")
            elif status == 'error':
                logger.error(f"Subscription error: {subscription_id}")
    
    async def _wait_for_response(self, request_id: str) -> Dict[str, Any]:
        """Wait for specific response"""
        while True:
            message = await self._message_queue.get()
            
            if message.get('id') == request_id:
                if message.get('type') == 'error':
                    raise TransportRequestError(
                        message.get('message', 'Request failed')
                    )
                return message
    
    async def _stream_subscription(self, subscription_id: str) -> AsyncIterator[Dict[str, Any]]:
        """Stream messages for subscription"""
        queue = asyncio.Queue()
        
        # Add queue to subscriptions
        if subscription_id in self._subscriptions:
            self._subscriptions[subscription_id]['queue'] = queue
        
        try:
            while True:
                message = await queue.get()
                if message.get('type') == 'unsubscribe':
                    break
                yield message
        finally:
            # Clean up queue
            if subscription_id in self._subscriptions:
                self._subscriptions[subscription_id].pop('queue', None)
    
    async def _unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe and clean up"""
        await self.unsubscribe(subscription_id)
    
    async def _heartbeat(self) -> None:
        """Send periodic heartbeat"""
        while self._connected:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                
                if self.websocket and self._connected:
                    # Send ping
                    await self.websocket.ping()
                    
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
                break
    
    async def _handle_disconnect(self) -> None:
        """Handle unexpected disconnect"""
        self._connected = False
        
        if self._reconnect_enabled:
            logger.info("Attempting to reconnect...")
            await self._reconnect()
    
    async def _reconnect(self) -> None:
        """Attempt to reconnect"""
        for attempt in range(self._max_reconnect_attempts):
            try:
                logger.info(f"Reconnect attempt {attempt + 1}/{self._max_reconnect_attempts}")
                
                # Wait before reconnect
                await asyncio.sleep(self._reconnect_delay)
                
                # Reconnect
                await self.connect()
                
                # Resubscribe to all subscriptions
                for sub_id, sub in list(self._subscriptions.items()):
                    if sub.get('event'):
                        await self.subscribe(
                            sub['event'],
                            sub['callback'],
                            sub.get('data')
                        )
                
                logger.info("Reconnected successfully")
                return
                
            except Exception as e:
                logger.error(f"Reconnect attempt {attempt + 1} failed: {e}")
        
        logger.error("Failed to reconnect after all attempts")
    
    def _generate_id(self) -> str:
        """Generate unique ID"""
        import uuid
        return str(uuid.uuid4())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get transport statistics"""
        return {
            'connected': self._connected,
            'ws_url': self.ws_url,
            'subscriptions': len(self._subscriptions),
            'close_code': self._close_code,
            'close_reason': self._close_reason
        }
