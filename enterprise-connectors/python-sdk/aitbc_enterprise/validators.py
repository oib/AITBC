"""
Validation utilities for AITBC Enterprise Connectors
"""

import re
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
from datetime import datetime

from .exceptions import ValidationError


@dataclass
class ValidationRule:
    """Validation rule definition"""
    name: str
    required: bool = True
    type: type = str
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    allowed_values: Optional[List[Any]] = None
    custom_validator: Optional[callable] = None


class BaseValidator(ABC):
    """Abstract base class for validators"""
    
    @abstractmethod
    async def validate(self, operation: str, data: Dict[str, Any]) -> bool:
        """Validate operation data"""
        pass


class SchemaValidator(BaseValidator):
    """Schema-based validator"""
    
    def __init__(self, schemas: Dict[str, Dict[str, ValidationRule]]):
        self.schemas = schemas
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
    
    async def validate(self, operation: str, data: Dict[str, Any]) -> bool:
        """Validate data against schema"""
        if operation not in self.schemas:
            self.logger.warning(f"No schema for operation: {operation}")
            return True
        
        schema = self.schemas[operation]
        errors = []
        
        # Validate each field
        for field_name, rule in schema.items():
            try:
                self._validate_field(field_name, data.get(field_name), rule)
            except ValidationError as e:
                errors.append(f"{field_name}: {str(e)}")
        
        # Check for unexpected fields
        allowed_fields = set(schema.keys())
        provided_fields = set(data.keys())
        unexpected = provided_fields - allowed_fields
        
        if unexpected:
            self.logger.warning(f"Unexpected fields: {unexpected}")
        
        if errors:
            raise ValidationError(f"Validation failed: {'; '.join(errors)}")
        
        return True
    
    def _validate_field(self, name: str, value: Any, rule: ValidationRule):
        """Validate a single field"""
        # Check required
        if rule.required and value is None:
            raise ValidationError(f"{name} is required")
        
        # Skip validation if not required and value is None
        if not rule.required and value is None:
            return
        
        # Type validation
        if not isinstance(value, rule.type):
            try:
                value = rule.type(value)
            except (ValueError, TypeError):
                raise ValidationError(f"{name} must be of type {rule.type.__name__}")
        
        # String validations
        if isinstance(value, str):
            if rule.min_length and len(value) < rule.min_length:
                raise ValidationError(f"{name} must be at least {rule.min_length} characters")
            
            if rule.max_length and len(value) > rule.max_length:
                raise ValidationError(f"{name} must be at most {rule.max_length} characters")
            
            if rule.pattern and not re.match(rule.pattern, value):
                raise ValidationError(f"{name} does not match required pattern")
        
        # Numeric validations
        if isinstance(value, (int, float)):
            if rule.min_value is not None and value < rule.min_value:
                raise ValidationError(f"{name} must be at least {rule.min_value}")
            
            if rule.max_value is not None and value > rule.max_value:
                raise ValidationError(f"{name} must be at most {rule.max_value}")
        
        # Allowed values
        if rule.allowed_values and value not in rule.allowed_values:
            raise ValidationError(f"{name} must be one of: {rule.allowed_values}")
        
        # Custom validator
        if rule.custom_validator:
            try:
                if not rule.custom_validator(value):
                    raise ValidationError(f"{name} failed custom validation")
            except Exception as e:
                raise ValidationError(f"{name} validation error: {str(e)}")


class PaymentValidator(SchemaValidator):
    """Validator for payment operations"""
    
    def __init__(self):
        schemas = {
            "create_charge": {
                "amount": ValidationRule(
                    name="amount",
                    type=int,
                    min_value=50,  # Minimum $0.50
                    max_value=99999999,  # Maximum $999,999.99
                    custom_validator=lambda x: x % 1 == 0  # Must be whole cents
                ),
                "currency": ValidationRule(
                    name="currency",
                    type=str,
                    min_length=3,
                    max_length=3,
                    pattern=r"^[A-Z]{3}$",
                    allowed_values=["USD", "EUR", "GBP", "JPY", "CAD", "AUD"]
                ),
                "source": ValidationRule(
                    name="source",
                    type=str,
                    min_length=1,
                    max_length=255
                ),
                "description": ValidationRule(
                    name="description",
                    type=str,
                    required=False,
                    max_length=1000
                )
            },
            "create_refund": {
                "charge": ValidationRule(
                    name="charge",
                    type=str,
                    min_length=1,
                    pattern=r"^ch_[a-zA-Z0-9]+$"
                ),
                "amount": ValidationRule(
                    name="amount",
                    type=int,
                    required=False,
                    min_value=50,
                    custom_validator=lambda x: x % 1 == 0
                ),
                "reason": ValidationRule(
                    name="reason",
                    type=str,
                    required=False,
                    allowed_values=["duplicate", "fraudulent", "requested_by_customer"]
                )
            },
            "create_payment_method": {
                "type": ValidationRule(
                    name="type",
                    type=str,
                    allowed_values=["card", "bank_account"]
                ),
                "card": ValidationRule(
                    name="card",
                    type=dict,
                    custom_validator=lambda x: all(k in x for k in ["number", "exp_month", "exp_year"])
                )
            }
        }
        
        super().__init__(schemas)


class ERPValidator(SchemaValidator):
    """Validator for ERP operations"""
    
    def __init__(self):
        schemas = {
            "create_customer": {
                "name": ValidationRule(
                    name="name",
                    type=str,
                    min_length=1,
                    max_length=100
                ),
                "email": ValidationRule(
                    name="email",
                    type=str,
                    pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
                ),
                "phone": ValidationRule(
                    name="phone",
                    type=str,
                    required=False,
                    pattern=r"^\+?[1-9]\d{1,14}$"
                ),
                "address": ValidationRule(
                    name="address",
                    type=dict,
                    required=False
                )
            },
            "create_order": {
                "customer_id": ValidationRule(
                    name="customer_id",
                    type=str,
                    min_length=1
                ),
                "items": ValidationRule(
                    name="items",
                    type=list,
                    min_length=1,
                    custom_validator=lambda x: all(isinstance(i, dict) and "product_id" in i and "quantity" in i for i in x)
                ),
                "currency": ValidationRule(
                    name="currency",
                    type=str,
                    pattern=r"^[A-Z]{3}$"
                )
            },
            "sync_data": {
                "entity_type": ValidationRule(
                    name="entity_type",
                    type=str,
                    allowed_values=["customers", "orders", "products", "invoices"]
                ),
                "since": ValidationRule(
                    name="since",
                    type=str,
                    required=False,
                    pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
                ),
                "limit": ValidationRule(
                    name="limit",
                    type=int,
                    required=False,
                    min_value=1,
                    max_value=1000
                )
            }
        }
        
        super().__init__(schemas)


class CompositeValidator(BaseValidator):
    """Combines multiple validators"""
    
    def __init__(self, validators: List[BaseValidator]):
        self.validators = validators
    
    async def validate(self, operation: str, data: Dict[str, Any]) -> bool:
        """Run all validators"""
        errors = []
        
        for validator in self.validators:
            try:
                await validator.validate(operation, data)
            except ValidationError as e:
                errors.append(str(e))
        
        if errors:
            raise ValidationError(f"Validation failed: {'; '.join(errors)}")
        
        return True


# Common validation functions
def validate_email(email: str) -> bool:
    """Validate email address"""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def validate_phone(phone: str) -> bool:
    """Validate phone number (E.164 format)"""
    pattern = r"^\+?[1-9]\d{1,14}$"
    return re.match(pattern, phone) is not None


def validate_amount(amount: int) -> bool:
    """Validate amount in cents"""
    return amount > 0 and amount % 1 == 0


def validate_currency(currency: str) -> bool:
    """Validate currency code"""
    return len(currency) == 3 and currency.isupper()


def validate_timestamp(timestamp: str) -> bool:
    """Validate ISO 8601 timestamp"""
    try:
        datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return True
    except ValueError:
        return False
