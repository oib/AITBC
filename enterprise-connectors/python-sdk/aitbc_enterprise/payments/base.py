"""
Base classes for payment processor connectors
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass
from enum import Enum


class PaymentStatus(Enum):
    """Payment status enumeration"""
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    CANCELED = "canceled"


class RefundStatus(Enum):
    """Refund status enumeration"""
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class SubscriptionStatus(Enum):
    """Subscription status enumeration"""
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"


@dataclass
class PaymentMethod:
    """Payment method representation"""
    id: str
    type: str
    created_at: datetime
    metadata: Dict[str, Any]
    
    # Card-specific fields
    brand: Optional[str] = None
    last4: Optional[str] = None
    exp_month: Optional[int] = None
    exp_year: Optional[int] = None
    
    # Bank account fields
    bank_name: Optional[str] = None
    last4_ach: Optional[str] = None
    routing_number: Optional[str] = None
    
    @classmethod
    def from_stripe_payment_method(cls, pm_data: Dict[str, Any]) -> 'PaymentMethod':
        """Create from Stripe payment method data"""
        card = pm_data.get("card", {})
        
        return cls(
            id=pm_data["id"],
            type=pm_data["type"],
            created_at=datetime.fromtimestamp(pm_data["created"]),
            metadata=pm_data.get("metadata", {}),
            brand=card.get("brand"),
            last4=card.get("last4"),
            exp_month=card.get("exp_month"),
            exp_year=card.get("exp_year")
        )


@dataclass
class Charge:
    """Charge representation"""
    id: str
    amount: int
    currency: str
    status: PaymentStatus
    created_at: datetime
    updated_at: datetime
    description: Optional[str]
    metadata: Dict[str, Any]
    
    # Refund information
    amount_refunded: int = 0
    refunds: List[Dict[str, Any]] = None
    
    # Payment method
    payment_method_id: Optional[str] = None
    payment_method_details: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.refunds is None:
            self.refunds = []
    
    @classmethod
    def from_stripe_charge(cls, charge_data: Dict[str, Any]) -> 'Charge':
        """Create from Stripe charge data"""
        return cls(
            id=charge_data["id"],
            amount=charge_data["amount"],
            currency=charge_data["currency"],
            status=PaymentStatus(charge_data["status"]),
            created_at=datetime.fromtimestamp(charge_data["created"]),
            updated_at=datetime.fromtimestamp(charge_data.get("updated", charge_data["created"])),
            description=charge_data.get("description"),
            metadata=charge_data.get("metadata", {}),
            amount_refunded=charge_data.get("amount_refunded", 0),
            refunds=[r.to_dict() for r in charge_data.get("refunds", {}).get("data", [])],
            payment_method_id=charge_data.get("payment_method"),
            payment_method_details=charge_data.get("payment_method_details")
        )


@dataclass
class Refund:
    """Refund representation"""
    id: str
    amount: int
    currency: str
    status: RefundStatus
    created_at: datetime
    updated_at: datetime
    charge_id: str
    reason: Optional[str]
    metadata: Dict[str, Any]
    
    @classmethod
    def from_stripe_refund(cls, refund_data: Dict[str, Any]) -> 'Refund':
        """Create from Stripe refund data"""
        return cls(
            id=refund_data["id"],
            amount=refund_data["amount"],
            currency=refund_data["currency"],
            status=RefundStatus(refund_data["status"]),
            created_at=datetime.fromtimestamp(refund_data["created"]),
            updated_at=datetime.fromtimestamp(refund_data.get("updated", refund_data["created"])),
            charge_id=refund_data["charge"],
            reason=refund_data.get("reason"),
            metadata=refund_data.get("metadata", {})
        )


@dataclass
class Subscription:
    """Subscription representation"""
    id: str
    status: SubscriptionStatus
    created_at: datetime
    updated_at: datetime
    current_period_start: datetime
    current_period_end: datetime
    customer_id: str
    metadata: Dict[str, Any]
    
    # Pricing
    amount: Optional[int] = None
    currency: Optional[str] = None
    interval: Optional[str] = None
    interval_count: Optional[int] = None
    
    # Trial
    trial_start: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    
    # Cancellation
    canceled_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    
    @classmethod
    def from_stripe_subscription(cls, sub_data: Dict[str, Any]) -> 'Subscription':
        """Create from Stripe subscription data"""
        items = sub_data.get("items", {}).get("data", [])
        first_item = items[0] if items else {}
        price = first_item.get("price", {})
        
        return cls(
            id=sub_data["id"],
            status=SubscriptionStatus(sub_data["status"]),
            created_at=datetime.fromtimestamp(sub_data["created"]),
            updated_at=datetime.fromtimestamp(sub_data.get("updated", sub_data["created"])),
            current_period_start=datetime.fromtimestamp(sub_data["current_period_start"]),
            current_period_end=datetime.fromtimestamp(sub_data["current_period_end"]),
            customer_id=sub_data["customer"],
            metadata=sub_data.get("metadata", {}),
            amount=price.get("unit_amount"),
            currency=price.get("currency"),
            interval=price.get("recurring", {}).get("interval"),
            interval_count=price.get("recurring", {}).get("interval_count"),
            trial_start=datetime.fromtimestamp(sub_data["trial_start"]) if sub_data.get("trial_start") else None,
            trial_end=datetime.fromtimestamp(sub_data["trial_end"]) if sub_data.get("trial_end") else None,
            canceled_at=datetime.fromtimestamp(sub_data["canceled_at"]) if sub_data.get("canceled_at") else None,
            ended_at=datetime.fromtimestamp(sub_data["ended_at"]) if sub_data.get("ended_at") else None
        )


class PaymentConnector(ABC):
    """Abstract base class for payment connectors"""
    
    def __init__(self, client, config):
        self.client = client
        self.config = config
    
    @abstractmethod
    async def create_charge(
        self,
        amount: int,
        currency: str,
        source: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Charge:
        """Create a charge"""
        pass
    
    @abstractmethod
    async def create_refund(
        self,
        charge_id: str,
        amount: Optional[int] = None,
        reason: Optional[str] = None
    ) -> Refund:
        """Create a refund"""
        pass
    
    @abstractmethod
    async def create_payment_method(
        self,
        type: str,
        card: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> PaymentMethod:
        """Create a payment method"""
        pass
    
    @abstractmethod
    async def create_subscription(
        self,
        customer: str,
        items: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Subscription:
        """Create a subscription"""
        pass
    
    @abstractmethod
    async def cancel_subscription(
        self,
        subscription_id: str,
        at_period_end: bool = True
    ) -> Subscription:
        """Cancel a subscription"""
        pass
