"""
Example usage of Stripe connector with AITBC Enterprise SDK
"""

import asyncio
import logging
from datetime import datetime

from aitbc_enterprise import AITBCClient, ConnectorConfig
from aitbc_enterprise.payments import StripeConnector
from aitbc_enterprise.exceptions import PaymentError


async def main():
    """Example Stripe integration"""
    
    # Configure AITBC client
    config = ConnectorConfig(
        base_url="https://api.aitbc.io",
        api_key="your-api-key",
        enterprise_id="enterprise-123",
        webhook_secret="whsec_your-webhook-secret"
    )
    
    # Create AITBC client
    async with AITBCClient(config) as client:
        
        # Initialize Stripe connector
        stripe = StripeConnector(
            client=client,
            config=config,
            stripe_api_key="sk_test_your-stripe-key",
            webhook_secret="whsec_your-stripe-webhook-secret"
        )
        
        # Initialize connector
        await stripe.initialize()
        
        try:
            # Example 1: Create a payment method
            print("Creating payment method...")
            payment_method = await stripe.create_payment_method(
                type="card",
                card={
                    "number": "4242424242424242",
                    "exp_month": 12,
                    "exp_year": 2024,
                    "cvc": "123"
                },
                metadata={"order_id": "12345"}
            )
            print(f"Created payment method: {payment_method.id}")
            
            # Example 2: Create a customer
            print("\nCreating customer...")
            customer_result = await stripe.execute_operation(
                "create_customer",
                {
                    "email": "customer@example.com",
                    "name": "John Doe",
                    "payment_method": payment_method.id
                }
            )
            
            if customer_result.success:
                customer_id = customer_result.data["id"]
                print(f"Created customer: {customer_id}")
            
            # Example 3: Create a charge
            print("\nCreating charge...")
            charge = await stripe.create_charge(
                amount=2000,  # $20.00
                currency="usd",
                source=payment_method.id,
                description="AITBC GPU computing service",
                metadata={"job_id": "job-123", "user_id": "user-456"}
            )
            print(f"Created charge: {charge.id} - ${charge.amount / 100:.2f}")
            
            # Example 4: Create a refund
            print("\nCreating refund...")
            refund = await stripe.create_refund(
                charge_id=charge.id,
                amount=500,  # $5.00 refund
                reason="requested_by_customer"
            )
            print(f"Created refund: {refund.id} - ${refund.amount / 100:.2f}")
            
            # Example 5: Create a subscription
            print("\nCreating subscription...")
            subscription = await stripe.create_subscription(
                customer=customer_id,
                items=[
                    {
                        "price": "price_1PHQX2RxeKt9VJxXzZXYZABC",  # Replace with actual price ID
                        "quantity": 1
                    }
                ],
                metadata={"tier": "pro"}
            )
            print(f"Created subscription: {subscription.id}")
            
            # Example 6: Batch operations
            print("\nExecuting batch operations...")
            batch_results = await stripe.batch_execute([
                {
                    "operation": "create_charge",
                    "data": {
                        "amount": 1000,
                        "currency": "usd",
                        "source": payment_method.id,
                        "description": "Batch charge 1"
                    }
                },
                {
                    "operation": "create_charge",
                    "data": {
                        "amount": 1500,
                        "currency": "usd",
                        "source": payment_method.id,
                        "description": "Batch charge 2"
                    }
                }
            ])
            
            successful = sum(1 for r in batch_results if r.success)
            print(f"Batch completed: {successful}/{len(batch_results)} successful")
            
            # Example 7: Check balance
            print("\nRetrieving balance...")
            balance = await stripe.retrieve_balance()
            available = balance.get("available", [{}])[0].get("amount", 0)
            print(f"Available balance: ${available / 100:.2f}")
            
            # Example 8: Get connector metrics
            print("\nConnector metrics:")
            metrics = stripe.metrics
            for key, value in metrics.items():
                print(f"  {key}: {value}")
            
        except PaymentError as e:
            print(f"Payment error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")
        
        finally:
            # Cleanup
            await stripe.cleanup()


async def webhook_example():
    """Example webhook handling"""
    
    config = ConnectorConfig(
        base_url="https://api.aitbc.io",
        api_key="your-api-key"
    )
    
    async with AITBCClient(config) as client:
        
        stripe = StripeConnector(
            client=client,
            config=config,
            stripe_api_key="sk_test_your-stripe-key",
            webhook_secret="whsec_your-stripe-webhook-secret"
        )
        
        await stripe.initialize()
        
        # Example webhook payload (you'd get this from Stripe)
        webhook_payload = b'''
        {
            "id": "evt_1234567890",
            "object": "event",
            "api_version": "2023-10-16",
            "created": 1703220000,
            "type": "charge.succeeded",
            "data": {
                "object": {
                    "id": "ch_1234567890",
                    "object": "charge",
                    "amount": 2000,
                    "currency": "usd",
                    "status": "succeeded"
                }
            }
        }
        '''
        
        # Example signature (you'd get this from Stripe)
        signature = "t=1703220000,v1=5257a869e7ecebeda32affa62ca2d3220b9a825a170d2e87a2ca2b10ef5"
        
        # Verify webhook
        if await stripe.verify_webhook(webhook_payload, signature):
            print("Webhook signature verified")
            
            # Handle webhook
            result = await stripe.handle_webhook(webhook_payload)
            print(f"Webhook processed: {result}")
        else:
            print("Invalid webhook signature")
        
        await stripe.cleanup()


async def enterprise_features_example():
    """Example with enterprise features"""
    
    # Enterprise configuration
    config = ConnectorConfig(
        base_url="https://api.aitbc.io",
        api_key="your-enterprise-api-key",
        enterprise_id="enterprise-123",
        tenant_id="tenant-456",
        region="us-east-1",
        rate_limit=100,  # 100 requests per second
        enable_metrics=True,
        log_level="DEBUG"
    )
    
    async with AITBCClient(config) as client:
        
        # Add custom event handler
        async def on_charge_created(data):
            print(f"Charge created event: {data.get('id')}")
            # Send to internal systems
            await client.post(
                "/internal/notifications",
                json={
                    "type": "charge_created",
                    "data": data
                }
            )
        
        stripe = StripeConnector(
            client=client,
            config=config,
            stripe_api_key="sk_test_your-stripe-key"
        )
        
        # Register event handler
        stripe.add_operation_handler("create_charge", on_charge_created)
        
        await stripe.initialize()
        
        # Create charge (will trigger event handler)
        charge = await stripe.create_charge(
            amount=5000,
            currency="usd",
            source="pm_card_visa",
            description="Enterprise GPU service",
            metadata={
                "department": "engineering",
                "project": "ml-training",
                "cost_center": "cc-123"
            }
        )
        
        print(f"Enterprise charge created: {charge.id}")
        
        # Wait for event processing
        await asyncio.sleep(1)
        
        await stripe.cleanup()


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Run examples
    print("=== Basic Stripe Example ===")
    asyncio.run(main())
    
    print("\n=== Webhook Example ===")
    asyncio.run(webhook_example())
    
    print("\n=== Enterprise Features Example ===")
    asyncio.run(enterprise_features_example())
