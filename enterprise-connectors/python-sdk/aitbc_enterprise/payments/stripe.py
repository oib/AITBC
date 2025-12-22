"""
Stripe payment connector for AITBC Enterprise
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import stripe

from ..base import BaseConnector, OperationResult, Transaction
from ..core import ConnectorConfig
from .base import PaymentConnector, PaymentMethod, Charge, Refund, Subscription
from ..exceptions import PaymentError, ValidationError


class StripeConnector(PaymentConnector):
    """Stripe payment processor connector"""
    
    def __init__(
        self,
        client: 'AITBCClient',
        config: ConnectorConfig,
        stripe_api_key: str,
        webhook_secret: Optional[str] = None
    ):
        super().__init__(client, config)
        
        # Stripe configuration
        self.stripe_api_key = stripe_api_key
        self.webhook_secret = webhook_secret
        
        # Initialize Stripe client
        stripe.api_key = stripe_api_key
        stripe.api_version = "2023-10-16"
        
        # Stripe-specific configuration
        self._stripe_config = {
            "api_key": stripe_api_key,
            "api_version": stripe.api_version,
            "connect_timeout": config.timeout,
            "read_timeout": config.timeout
        }
    
    async def _initialize(self) -> None:
        """Initialize Stripe connector"""
        try:
            # Test Stripe connection
            await self._test_stripe_connection()
            
            # Set up webhook handler
            if self.webhook_secret:
                await self._setup_webhook_handler()
            
            self.logger.info("Stripe connector initialized")
            
        except Exception as e:
            raise PaymentError(f"Failed to initialize Stripe: {e}")
    
    async def _cleanup(self) -> None:
        """Cleanup Stripe connector"""
        # No specific cleanup needed for Stripe
        pass
    
    async def _execute_operation(
        self,
        operation: str,
        data: Dict[str, Any],
        **kwargs
    ) -> OperationResult:
        """Execute Stripe-specific operations"""
        try:
            if operation == "create_charge":
                return await self._create_charge(data)
            elif operation == "create_refund":
                return await self._create_refund(data)
            elif operation == "create_payment_method":
                return await self._create_payment_method(data)
            elif operation == "create_customer":
                return await self._create_customer(data)
            elif operation == "create_subscription":
                return await self._create_subscription(data)
            elif operation == "cancel_subscription":
                return await self._cancel_subscription(data)
            elif operation == "retrieve_balance":
                return await self._retrieve_balance()
            else:
                raise ValidationError(f"Unknown operation: {operation}")
                
        except stripe.error.StripeError as e:
            self.logger.error(f"Stripe error: {e}")
            return OperationResult(
                success=False,
                error=str(e),
                metadata={"stripe_error_code": getattr(e, 'code', None)}
            )
        except Exception as e:
            self.logger.error(f"Operation failed: {e}")
            return OperationResult(
                success=False,
                error=str(e)
            )
    
    async def create_charge(
        self,
        amount: int,
        currency: str,
        source: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Charge:
        """Create a charge"""
        result = await self.execute_operation(
            "create_charge",
            {
                "amount": amount,
                "currency": currency,
                "source": source,
                "description": description,
                "metadata": metadata or {}
            }
        )
        
        if not result.success:
            raise PaymentError(result.error)
        
        return Charge.from_stripe_charge(result.data)
    
    async def create_refund(
        self,
        charge_id: str,
        amount: Optional[int] = None,
        reason: Optional[str] = None
    ) -> Refund:
        """Create a refund"""
        result = await self.execute_operation(
            "create_refund",
            {
                "charge": charge_id,
                "amount": amount,
                "reason": reason
            }
        )
        
        if not result.success:
            raise PaymentError(result.error)
        
        return Refund.from_stripe_refund(result.data)
    
    async def create_payment_method(
        self,
        type: str,
        card: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> PaymentMethod:
        """Create a payment method"""
        result = await self.execute_operation(
            "create_payment_method",
            {
                "type": type,
                "card": card,
                "metadata": metadata or {}
            }
        )
        
        if not result.success:
            raise PaymentError(result.error)
        
        return PaymentMethod.from_stripe_payment_method(result.data)
    
    async def create_subscription(
        self,
        customer: str,
        items: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Subscription:
        """Create a subscription"""
        result = await self.execute_operation(
            "create_subscription",
            {
                "customer": customer,
                "items": items,
                "metadata": metadata or {}
            }
        )
        
        if not result.success:
            raise PaymentError(result.error)
        
        return Subscription.from_stripe_subscription(result.data)
    
    async def cancel_subscription(
        self,
        subscription_id: str,
        at_period_end: bool = True
    ) -> Subscription:
        """Cancel a subscription"""
        result = await self.execute_operation(
            "cancel_subscription",
            {
                "subscription": subscription_id,
                "at_period_end": at_period_end
            }
        )
        
        if not result.success:
            raise PaymentError(result.error)
        
        return Subscription.from_stripe_subscription(result.data)
    
    async def retrieve_balance(self) -> Dict[str, Any]:
        """Retrieve account balance"""
        result = await self.execute_operation("retrieve_balance", {})
        
        if not result.success:
            raise PaymentError(result.error)
        
        return result.data
    
    async def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """Verify Stripe webhook signature"""
        try:
            stripe.WebhookSignature.verify_header(
                payload,
                signature,
                self.webhook_secret,
                300
            )
            return True
        except stripe.error.SignatureVerificationError:
            return False
    
    async def handle_webhook(self, payload: bytes) -> Dict[str, Any]:
        """Handle Stripe webhook"""
        try:
            event = stripe.Webhook.construct_event(
                payload,
                None,  # Already verified
                self.webhook_secret,
                300
            )
            
            # Process event based on type
            result = await self._process_webhook_event(event)
            
            return {
                "processed": True,
                "event_type": event.type,
                "event_id": event.id,
                "result": result
            }
            
        except Exception as e:
            self.logger.error(f"Webhook processing failed: {e}")
            return {
                "processed": False,
                "error": str(e)
            }
    
    # Private methods
    
    async def _test_stripe_connection(self):
        """Test Stripe API connection"""
        try:
            # Use asyncio to run in thread
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, stripe.Balance.retrieve)
        except Exception as e:
            raise PaymentError(f"Stripe connection test failed: {e}")
    
    async def _setup_webhook_handler(self):
        """Setup webhook handler"""
        # Register webhook verification with base connector
        self.add_operation_handler("webhook.verified", self._handle_verified_webhook)
    
    async def _create_charge(self, data: Dict[str, Any]) -> OperationResult:
        """Create Stripe charge"""
        loop = asyncio.get_event_loop()
        
        try:
            charge = await loop.run_in_executor(
                None,
                lambda: stripe.Charge.create(**data)
            )
            
            return OperationResult(
                success=True,
                data=charge.to_dict(),
                metadata={"charge_id": charge.id}
            )
            
        except Exception as e:
            raise PaymentError(f"Failed to create charge: {e}")
    
    async def _create_refund(self, data: Dict[str, Any]) -> OperationResult:
        """Create Stripe refund"""
        loop = asyncio.get_event_loop()
        
        try:
            refund = await loop.run_in_executor(
                None,
                lambda: stripe.Refund.create(**data)
            )
            
            return OperationResult(
                success=True,
                data=refund.to_dict(),
                metadata={"refund_id": refund.id}
            )
            
        except Exception as e:
            raise PaymentError(f"Failed to create refund: {e}")
    
    async def _create_payment_method(self, data: Dict[str, Any]) -> OperationResult:
        """Create Stripe payment method"""
        loop = asyncio.get_event_loop()
        
        try:
            pm = await loop.run_in_executor(
                None,
                lambda: stripe.PaymentMethod.create(**data)
            )
            
            return OperationResult(
                success=True,
                data=pm.to_dict(),
                metadata={"payment_method_id": pm.id}
            )
            
        except Exception as e:
            raise PaymentError(f"Failed to create payment method: {e}")
    
    async def _create_customer(self, data: Dict[str, Any]) -> OperationResult:
        """Create Stripe customer"""
        loop = asyncio.get_event_loop()
        
        try:
            customer = await loop.run_in_executor(
                None,
                lambda: stripe.Customer.create(**data)
            )
            
            return OperationResult(
                success=True,
                data=customer.to_dict(),
                metadata={"customer_id": customer.id}
            )
            
        except Exception as e:
            raise PaymentError(f"Failed to create customer: {e}")
    
    async def _create_subscription(self, data: Dict[str, Any]) -> OperationResult:
        """Create Stripe subscription"""
        loop = asyncio.get_event_loop()
        
        try:
            subscription = await loop.run_in_executor(
                None,
                lambda: stripe.Subscription.create(**data)
            )
            
            return OperationResult(
                success=True,
                data=subscription.to_dict(),
                metadata={"subscription_id": subscription.id}
            )
            
        except Exception as e:
            raise PaymentError(f"Failed to create subscription: {e}")
    
    async def _cancel_subscription(self, data: Dict[str, Any]) -> OperationResult:
        """Cancel Stripe subscription"""
        loop = asyncio.get_event_loop()
        
        try:
            subscription = await loop.run_in_executor(
                None,
                lambda: stripe.Subscription.retrieve(data["subscription"])
            )
            
            subscription = await loop.run_in_executor(
                None,
                lambda: subscription.cancel(at_period_end=data.get("at_period_end", True))
            )
            
            return OperationResult(
                success=True,
                data=subscription.to_dict(),
                metadata={"subscription_id": subscription.id}
            )
            
        except Exception as e:
            raise PaymentError(f"Failed to cancel subscription: {e}")
    
    async def _retrieve_balance(self) -> OperationResult:
        """Retrieve Stripe balance"""
        loop = asyncio.get_event_loop()
        
        try:
            balance = await loop.run_in_executor(None, stripe.Balance.retrieve)
            
            return OperationResult(
                success=True,
                data=balance.to_dict()
            )
            
        except Exception as e:
            raise PaymentError(f"Failed to retrieve balance: {e}")
    
    async def _process_webhook_event(self, event) -> Dict[str, Any]:
        """Process webhook event"""
        event_type = event.type
        
        if event_type.startswith("charge."):
            return await self._handle_charge_event(event)
        elif event_type.startswith("payment_method."):
            return await self._handle_payment_method_event(event)
        elif event_type.startswith("customer."):
            return await self._handle_customer_event(event)
        elif event_type.startswith("invoice."):
            return await self._handle_invoice_event(event)
        else:
            self.logger.info(f"Unhandled webhook event type: {event_type}")
            return {"status": "ignored"}
    
    async def _handle_charge_event(self, event) -> Dict[str, Any]:
        """Handle charge-related webhook events"""
        charge = event.data.object
        
        # Emit to AITBC
        await self.client.post(
            "/webhooks/stripe/charge",
            json={
                "event_id": event.id,
                "event_type": event.type,
                "charge": charge.to_dict()
            }
        )
        
        return {"status": "processed", "charge_id": charge.id}
    
    async def _handle_payment_method_event(self, event) -> Dict[str, Any]:
        """Handle payment method webhook events"""
        pm = event.data.object
        
        await self.client.post(
            "/webhooks/stripe/payment_method",
            json={
                "event_id": event.id,
                "event_type": event.type,
                "payment_method": pm.to_dict()
            }
        )
        
        return {"status": "processed", "payment_method_id": pm.id}
    
    async def _handle_customer_event(self, event) -> Dict[str, Any]:
        """Handle customer webhook events"""
        customer = event.data.object
        
        await self.client.post(
            "/webhooks/stripe/customer",
            json={
                "event_id": event.id,
                "event_type": event.type,
                "customer": customer.to_dict()
            }
        )
        
        return {"status": "processed", "customer_id": customer.id}
    
    async def _handle_invoice_event(self, event) -> Dict[str, Any]:
        """Handle invoice webhook events"""
        invoice = event.data.object
        
        await self.client.post(
            "/webhooks/stripe/invoice",
            json={
                "event_id": event.id,
                "event_type": event.type,
                "invoice": invoice.to_dict()
            }
        )
        
        return {"status": "processed", "invoice_id": invoice.id}
    
    async def _handle_verified_webhook(self, data: Dict[str, Any]):
        """Handle verified webhook"""
        self.logger.info(f"Webhook verified: {data}")
