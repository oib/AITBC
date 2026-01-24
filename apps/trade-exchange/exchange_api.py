#!/usr/bin/env python3
"""
FastAPI backend for the AITBC Trade Exchange
"""

from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import desc, func, and_
from sqlalchemy.orm import Session

from database import init_db, get_db_session
from models import User, Order, Trade, Balance

# Initialize FastAPI app
app = FastAPI(title="AITBC Trade Exchange API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class OrderCreate(BaseModel):
    order_type: str  # 'BUY' or 'SELL'
    amount: float
    price: float

class OrderResponse(BaseModel):
    id: int
    order_type: str
    amount: float
    price: float
    total: float
    filled: float
    remaining: float
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class TradeResponse(BaseModel):
    id: int
    amount: float
    price: float
    total: float
    created_at: datetime
    
    class Config:
        from_attributes = True

class OrderBookResponse(BaseModel):
    buys: List[OrderResponse]
    sells: List[OrderResponse]

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()
    
    # Create mock data if database is empty
    db = get_db_session()
    try:
        # Check if we have any trades
        if db.query(Trade).count() == 0:
            create_mock_trades(db)
    finally:
        db.close()

def create_mock_trades(db: Session):
    """Create some mock trades for demonstration"""
    import random
    
    # Create mock trades over the last hour
    now = datetime.utcnow()
    trades = []
    
    for i in range(20):
        # Generate random trade data
        amount = random.uniform(10, 500)
        price = random.uniform(0.000009, 0.000012)
        total = amount * price
        
        trade = Trade(
            buyer_id=1,  # Mock user ID
            seller_id=2,  # Mock user ID
            order_id=1,  # Mock order ID
            amount=amount,
            price=price,
            total=total,
            trade_hash=f"mock_tx_{i:04d}",
            created_at=now - timedelta(minutes=random.randint(0, 60))
        )
        trades.append(trade)
    
    db.add_all(trades)
    db.commit()
    print(f"Created {len(trades)} mock trades")

@app.get("/api/trades/recent", response_model=List[TradeResponse])
def get_recent_trades(limit: int = 20, db: Session = Depends(get_db_session)):
    """Get recent trades"""
    trades = db.query(Trade).order_by(desc(Trade.created_at)).limit(limit).all()
    return trades

@app.get("/api/orders/orderbook", response_model=OrderBookResponse)
def get_orderbook(db: Session = Depends(get_db_session)):
    """Get current order book"""
    
    # Get open buy orders (sorted by price descending)
    buys = db.query(Order).filter(
        and_(Order.order_type == 'BUY', Order.status == 'OPEN')
    ).order_by(desc(Order.price)).limit(20).all()
    
    # Get open sell orders (sorted by price ascending)
    sells = db.query(Order).filter(
        and_(Order.order_type == 'SELL', Order.status == 'OPEN')
    ).order_by(Order.price).limit(20).all()
    
    return OrderBookResponse(buys=buys, sells=sells)

@app.post("/api/orders", response_model=OrderResponse)
def create_order(order: OrderCreate, db: Session = Depends(get_db_session)):
    """Create a new order"""
    
    # Validate order type
    if order.order_type not in ['BUY', 'SELL']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order type must be 'BUY' or 'SELL'"
        )
    
    # Create order
    total = order.amount * order.price
    db_order = Order(
        user_id=1,  # TODO: Get from authentication
        order_type=order.order_type,
        amount=order.amount,
        price=order.price,
        total=total,
        remaining=order.amount
    )
    
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    
    # Try to match the order
    try_match_order(db_order, db)
    
    return db_order

def try_match_order(order: Order, db: Session):
    """Try to match an order with existing orders"""
    
    if order.order_type == 'BUY':
        # Match with sell orders at same or lower price
        matching_orders = db.query(Order).filter(
            and_(
                Order.order_type == 'SELL',
                Order.status == 'OPEN',
                Order.price <= order.price
            )
        ).order_by(Order.price).all()
    else:
        # Match with buy orders at same or higher price
        matching_orders = db.query(Order).filter(
            and_(
                Order.order_type == 'BUY',
                Order.status == 'OPEN',
                Order.price >= order.price
            )
        ).order_by(desc(Order.price)).all()
    
    for match in matching_orders:
        if order.remaining <= 0:
            break
        
        # Calculate trade amount
        trade_amount = min(order.remaining, match.remaining)
        trade_total = trade_amount * match.price
        
        # Create trade record
        trade = Trade(
            buyer_id=order.user_id if order.order_type == 'BUY' else match.user_id,
            seller_id=match.user_id if order.order_type == 'BUY' else order.user_id,
            order_id=order.id,
            amount=trade_amount,
            price=match.price,
            total=trade_total,
            trade_hash=f"trade_{datetime.utcnow().timestamp()}"
        )
        
        db.add(trade)
        
        # Update orders
        order.filled += trade_amount
        order.remaining -= trade_amount
        match.filled += trade_amount
        match.remaining -= trade_amount
        
        # Update order statuses
        if order.remaining <= 0:
            order.status = 'FILLED'
        else:
            order.status = 'PARTIALLY_FILLED'
            
        if match.remaining <= 0:
            match.status = 'FILLED'
        else:
            match.status = 'PARTIALLY_FILLED'
    
    db.commit()

@app.get("/api/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.utcnow()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3003)
