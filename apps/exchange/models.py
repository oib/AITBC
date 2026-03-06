#!/usr/bin/env python3
"""
Database models for the AITBC Trade Exchange
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    """User account for trading"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    bitcoin_address = Column(String(100), unique=True, nullable=False)
    aitbc_address = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    orders = relationship("Order", back_populates="user")
    trades = relationship("Trade", back_populates="buyer")
    
    def __repr__(self):
        return f"<User(username='{self.username}')>"


class Order(Base):
    """Trading order (buy or sell)"""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    order_type = Column(String(4), nullable=False)  # 'BUY' or 'SELL'
    amount = Column(Float, nullable=False)  # Amount of AITBC
    price = Column(Float, nullable=False)  # Price in BTC
    total = Column(Float, nullable=False)  # Total in BTC (amount * price)
    filled = Column(Float, default=0.0)  # Amount filled
    remaining = Column(Float, nullable=False)  # Amount remaining to fill
    status = Column(String(20), default='OPEN')  # OPEN, PARTIALLY_FILLED, FILLED, CANCELLED
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="orders")
    trades = relationship("Trade", back_populates="order")
    
    __table_args__ = (
        Index('idx_order_type_status', 'order_type', 'status'),
        Index('idx_price_status', 'price', 'status'),
    )
    
    def __repr__(self):
        return f"<Order(type='{self.order_type}', amount={self.amount}, price={self.price})>"


class Trade(Base):
    """Completed trade record"""
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, index=True)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    amount = Column(Float, nullable=False)  # Amount of AITBC traded
    price = Column(Float, nullable=False)  # Trade price in BTC
    total = Column(Float, nullable=False)  # Total value in BTC
    trade_hash = Column(String(100), unique=True, nullable=False)  # Blockchain transaction hash
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    buyer = relationship("User", back_populates="trades", foreign_keys=[buyer_id])
    seller = relationship("User", foreign_keys=[seller_id])
    order = relationship("Order", back_populates="trades")
    
    __table_args__ = (
        Index('idx_created_at', 'created_at'),
        Index('idx_price', 'price'),
    )
    
    def __repr__(self):
        return f"<Trade(amount={self.amount}, price={self.price}, total={self.total})>"


class Balance(Base):
    """User balance tracking"""
    __tablename__ = "balances"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    btc_balance = Column(Float, default=0.0)
    aitbc_balance = Column(Float, default=0.0)
    btc_locked = Column(Float, default=0.0)  # Locked in open orders
    aitbc_locked = Column(Float, default=0.0)  # Locked in open orders
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = relationship("User")
    
    def __repr__(self):
        return f"<Balance(btc={self.btc_balance}, aitbc={self.aitbc_balance})>"
