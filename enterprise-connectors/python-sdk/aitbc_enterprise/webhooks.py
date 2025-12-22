"""
Webhook handling for AITBC Enterprise Connectors
"""

import hashlib
import hmac
import json
import asyncio
from typing import Dict, Any, Optional, Callable, List, Awaitable
from datetime import datetime
from dataclasses import dataclass

from .exceptions import WebhookError


@dataclass
class WebhookEvent:
    """Webhook event representation"""
    id: str
    type: str
    source: str
    timestamp: datetime
    data: Dict[str, Any]
    signature: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "signature": self.signature
        }


class WebhookHandler:
    """Handles webhook processing and verification"""
    
    def __init__(self, secret: str = None):
        self.secret = secret
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
        
        # Event handlers
        self._handlers: Dict[str, List[Callable]] = {}
        
        # Processing state
        self._processing = False
        self._queue: asyncio.Queue = None
        self._worker_task = None
    
    async def setup(self, endpoint: str, secret: str = None):
        """Setup webhook handler"""
        if secret:
            self.secret = secret
        
        # Initialize queue and worker
        self._queue = asyncio.Queue(maxsize=1000)
        self._worker_task = asyncio.create_task(self._process_queue())
        
        self.logger.info(f"Webhook handler setup for endpoint: {endpoint}")
    
    async def cleanup(self):
        """Cleanup webhook handler"""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Webhook handler cleaned up")
    
    def add_handler(self, event_type: str, handler: Callable[[WebhookEvent], Awaitable[None]]):
        """Add handler for specific event type"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def remove_handler(self, event_type: str, handler: Callable):
        """Remove handler for specific event type"""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass
    
    async def verify(self, payload: bytes, signature: str, algorithm: str = "sha256") -> bool:
        """Verify webhook signature"""
        if not self.secret:
            self.logger.warning("No webhook secret configured, skipping verification")
            return True
        
        try:
            expected_signature = hmac.new(
                self.secret.encode(),
                payload,
                getattr(hashlib, algorithm)
            ).hexdigest()
            
            # Compare signatures securely
            return hmac.compare_digest(expected_signature, signature)
            
        except Exception as e:
            self.logger.error(f"Webhook verification failed: {e}")
            return False
    
    async def handle(self, payload: bytes, signature: str = None) -> Dict[str, Any]:
        """Handle incoming webhook"""
        try:
            # Parse payload
            data = json.loads(payload.decode())
            
            # Create event
            event = WebhookEvent(
                id=data.get("id", f"evt_{int(datetime.utcnow().timestamp())}"),
                type=data.get("type", "unknown"),
                source=data.get("source", "unknown"),
                timestamp=datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat())),
                data=data.get("data", {}),
                signature=signature
            )
            
            # Verify signature if provided
            if signature and not await self.verify(payload, signature):
                raise WebhookError("Invalid webhook signature")
            
            # Queue for processing
            if self._queue:
                await self._queue.put(event)
                return {
                    "status": "queued",
                    "event_id": event.id
                }
            else:
                # Process immediately
                result = await self._process_event(event)
                return result
                
        except json.JSONDecodeError as e:
            raise WebhookError(f"Invalid JSON payload: {e}")
        except Exception as e:
            self.logger.error(f"Webhook handling failed: {e}")
            raise WebhookError(f"Processing failed: {e}")
    
    async def _process_queue(self):
        """Process webhook events from queue"""
        while True:
            try:
                event = await self._queue.get()
                await self._process_event(event)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error processing webhook event: {e}")
    
    async def _process_event(self, event: WebhookEvent) -> Dict[str, Any]:
        """Process a single webhook event"""
        try:
            self.logger.debug(f"Processing webhook event: {event.type}")
            
            # Get handlers for event type
            handlers = self._handlers.get(event.type, [])
            
            # Also check for wildcard handlers
            wildcard_handlers = self._handlers.get("*", [])
            handlers.extend(wildcard_handlers)
            
            if not handlers:
                self.logger.warning(f"No handlers for event type: {event.type}")
                return {
                    "status": "ignored",
                    "event_id": event.id,
                    "message": "No handlers registered"
                }
            
            # Execute handlers
            tasks = []
            for handler in handlers:
                tasks.append(handler(event))
            
            # Wait for all handlers to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check for errors
            errors = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    errors.append(str(result))
                    self.logger.error(f"Handler {i} failed: {result}")
            
            return {
                "status": "processed" if not errors else "partial",
                "event_id": event.id,
                "handlers_count": len(handlers),
                "errors_count": len(errors),
                "errors": errors if errors else None
            }
            
        except Exception as e:
            self.logger.error(f"Failed to process webhook event: {e}")
            return {
                "status": "failed",
                "event_id": event.id,
                "error": str(e)
            }


class StripeWebhookHandler(WebhookHandler):
    """Stripe-specific webhook handler"""
    
    def __init__(self, secret: str):
        super().__init__(secret)
        self._setup_default_handlers()
    
    def _setup_default_handlers(self):
        """Setup default Stripe event handlers"""
        self.add_handler("charge.succeeded", self._handle_charge_succeeded)
        self.add_handler("charge.failed", self._handle_charge_failed)
        self.add_handler("payment_method.attached", self._handle_payment_method_attached)
        self.add_handler("invoice.payment_succeeded", self._handle_invoice_succeeded)
    
    async def verify(self, payload: bytes, signature: str) -> bool:
        """Verify Stripe webhook signature"""
        try:
            import stripe
            
            stripe.WebhookSignature.verify_header(
                payload,
                signature,
                self.secret,
                300  # 5 minutes tolerance
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Stripe webhook verification failed: {e}")
            return False
    
    async def _handle_charge_succeeded(self, event: WebhookEvent):
        """Handle successful charge"""
        charge = event.data.get("object", {})
        self.logger.info(f"Charge succeeded: {charge.get('id')} - ${charge.get('amount', 0) / 100:.2f}")
    
    async def _handle_charge_failed(self, event: WebhookEvent):
        """Handle failed charge"""
        charge = event.data.get("object", {})
        self.logger.warning(f"Charge failed: {charge.get('id')} - {charge.get('failure_message')}")
    
    async def _handle_payment_method_attached(self, event: WebhookEvent):
        """Handle payment method attachment"""
        pm = event.data.get("object", {})
        self.logger.info(f"Payment method attached: {pm.get('id')} - {pm.get('type')}")
    
    async def _handle_invoice_succeeded(self, event: WebhookEvent):
        """Handle successful invoice payment"""
        invoice = event.data.get("object", {})
        self.logger.info(f"Invoice paid: {invoice.get('id')} - ${invoice.get('amount_paid', 0) / 100:.2f}")


class WebhookServer:
    """Simple webhook server for testing"""
    
    def __init__(self, handler: WebhookHandler, port: int = 8080):
        self.handler = handler
        self.port = port
        self.server = None
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
    
    async def start(self):
        """Start webhook server"""
        from aiohttp import web
        
        async def handle_webhook(request):
            # Get signature from header
            signature = request.headers.get("Stripe-Signature") or request.headers.get("X-Signature")
            
            # Read payload
            payload = await request.read()
            
            try:
                # Handle webhook
                result = await self.handler.handle(payload, signature)
                return web.json_response(result)
            except WebhookError as e:
                return web.json_response(
                    {"error": str(e)},
                    status=400
                )
        
        # Create app
        app = web.Application()
        app.router.add_post("/webhook", handle_webhook)
        
        # Start server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", self.port)
        await site.start()
        
        self.server = runner
        self.logger.info(f"Webhook server started on port {self.port}")
    
    async def stop(self):
        """Stop webhook server"""
        if self.server:
            await self.server.cleanup()
            self.logger.info("Webhook server stopped")
