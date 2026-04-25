"""
Production Trading Engine for AITBC
Handles order matching, trade execution, and settlement
"""

import asyncio
import json
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager

from aitbc import get_logger

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting AITBC Trading Engine")
    # Start background market simulation
    asyncio.create_task(simulate_market_activity())
    yield
    # Shutdown
    logger.info("Shutting down AITBC Trading Engine")

app = FastAPI(
    title="AITBC Trading Engine",
    description="High-performance order matching and trade execution",
    version="1.0.0",
    lifespan=lifespan
)

# Data models
class Order(BaseModel):
    order_id: str
    symbol: str
    side: str  # buy/sell
    type: str   # market/limit
    quantity: float
    price: Optional[float] = None
    user_id: str
    timestamp: datetime

class Trade(BaseModel):
    trade_id: str
    symbol: str
    buy_order_id: str
    sell_order_id: str
    quantity: float
    price: float
    timestamp: datetime

class OrderBookEntry(BaseModel):
    price: float
    quantity: float
    orders_count: int

# In-memory order books (in production, use more sophisticated data structures)
order_books: Dict[str, Dict] = {}
orders: Dict[str, Dict] = {}
trades: Dict[str, Dict] = {}
market_data: Dict[str, Dict] = {}

@app.get("/")
async def root():
    return {
        "service": "AITBC Trading Engine",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "active_order_books": len(order_books),
        "total_orders": len(orders),
        "total_trades": len(trades),
        "uptime": "running"
    }

@app.post("/api/v1/orders/submit")
async def submit_order(order: Order):
    """Submit a new order to the trading engine"""
    symbol = order.symbol
    
    # Initialize order book if not exists
    if symbol not in order_books:
        order_books[symbol] = {
            "bids": defaultdict(list),  # buy orders
            "asks": defaultdict(list),  # sell orders
            "last_price": None,
            "volume_24h": 0.0,
            "high_24h": None,
            "low_24h": None,
            "created_at": datetime.utcnow().isoformat()
        }
    
    # Store order
    order_data = {
        "order_id": order.order_id,
        "symbol": order.symbol,
        "side": order.side,
        "type": order.type,
        "quantity": order.quantity,
        "remaining_quantity": order.quantity,
        "price": order.price,
        "user_id": order.user_id,
        "timestamp": order.timestamp.isoformat(),
        "status": "open",
        "filled_quantity": 0.0,
        "average_price": None
    }
    
    orders[order.order_id] = order_data
    
    # Process order
    trades_executed = await process_order(order_data)
    
    logger.info(f"Order submitted: {order.order_id} - {order.side} {order.quantity} {order.symbol}")
    
    return {
        "order_id": order.order_id,
        "status": order_data["status"],
        "filled_quantity": order_data["filled_quantity"],
        "remaining_quantity": order_data["remaining_quantity"],
        "trades_executed": len(trades_executed),
        "average_price": order_data["average_price"]
    }

@app.get("/api/v1/orders/{order_id}")
async def get_order(order_id: str):
    """Get order details"""
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return orders[order_id]

@app.get("/api/v1/orders")
async def list_orders():
    """List all orders"""
    return {
        "orders": list(orders.values()),
        "total_orders": len(orders),
        "open_orders": len([o for o in orders.values() if o["status"] == "open"]),
        "filled_orders": len([o for o in orders.values() if o["status"] == "filled"])
    }

@app.get("/api/v1/orderbook/{symbol}")
async def get_order_book(symbol: str, depth: int = 10):
    """Get order book for a trading pair"""
    if symbol not in order_books:
        raise HTTPException(status_code=404, detail="Order book not found")
    
    book = order_books[symbol]
    
    # Get best bids and asks
    bids = sorted(book["bids"].items(), reverse=True)[:depth]
    asks = sorted(book["asks"].items())[:depth]
    
    return {
        "symbol": symbol,
        "bids": [
            {
                "price": price,
                "quantity": sum(order["remaining_quantity"] for order in orders_list),
                "orders_count": len(orders_list)
            }
            for price, orders_list in bids
        ],
        "asks": [
            {
                "price": price,
                "quantity": sum(order["remaining_quantity"] for order in orders_list),
                "orders_count": len(orders_list)
            }
            for price, orders_list in asks
        ],
        "last_price": book["last_price"],
        "volume_24h": book["volume_24h"],
        "high_24h": book["high_24h"],
        "low_24h": book["low_24h"],
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/v1/trades")
async def list_trades(symbol: Optional[str] = None, limit: int = 100):
    """List recent trades"""
    all_trades = list(trades.values())
    
    if symbol:
        all_trades = [t for t in all_trades if t["symbol"] == symbol]
    
    # Sort by timestamp (most recent first)
    all_trades.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return {
        "trades": all_trades[:limit],
        "total_trades": len(all_trades)
    }

@app.get("/api/v1/ticker/{symbol}")
async def get_ticker(symbol: str):
    """Get ticker information for a trading pair"""
    if symbol not in order_books:
        raise HTTPException(status_code=404, detail="Trading pair not found")
    
    book = order_books[symbol]
    
    # Calculate 24h statistics
    trades_24h = [t for t in trades.values() 
                 if t["symbol"] == symbol and 
                 datetime.fromisoformat(t["timestamp"]) > 
                 datetime.utcnow() - timedelta(hours=24)]
    
    if trades_24h:
        prices = [t["price"] for t in trades_24h]
        volume = sum(t["quantity"] for t in trades_24h)
        
        ticker = {
            "symbol": symbol,
            "last_price": book["last_price"],
            "bid_price": max(book["bids"].keys()) if book["bids"] else None,
            "ask_price": min(book["asks"].keys()) if book["asks"] else None,
            "high_24h": max(prices),
            "low_24h": min(prices),
            "volume_24h": volume,
            "change_24h": prices[-1] - prices[0] if len(prices) > 1 else 0,
            "change_percent_24h": ((prices[-1] - prices[0]) / prices[0] * 100) if len(prices) > 1 else 0
        }
    else:
        ticker = {
            "symbol": symbol,
            "last_price": book["last_price"],
            "bid_price": None,
            "ask_price": None,
            "high_24h": None,
            "low_24h": None,
            "volume_24h": 0.0,
            "change_24h": 0.0,
            "change_percent_24h": 0.0
        }
    
    return ticker

@app.delete("/api/v1/orders/{order_id}")
async def cancel_order(order_id: str):
    """Cancel an order"""
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = orders[order_id]
    
    if order["status"] != "open":
        raise HTTPException(status_code=400, detail="Order cannot be cancelled")
    
    # Remove from order book
    symbol = order["symbol"]
    if symbol in order_books:
        book = order_books[symbol]
        price_key = str(order["price"])
        
        if order["side"] == "buy" and price_key in book["bids"]:
            book["bids"][price_key] = [o for o in book["bids"][price_key] if o["order_id"] != order_id]
            if not book["bids"][price_key]:
                del book["bids"][price_key]
        elif order["side"] == "sell" and price_key in book["asks"]:
            book["asks"][price_key] = [o for o in book["asks"][price_key] if o["order_id"] != order_id]
            if not book["asks"][price_key]:
                del book["asks"][price_key]
    
    # Update order status
    order["status"] = "cancelled"
    order["cancelled_at"] = datetime.utcnow().isoformat()
    
    logger.info(f"Order cancelled: {order_id}")
    
    return {
        "order_id": order_id,
        "status": "cancelled",
        "cancelled_at": order["cancelled_at"]
    }

@app.get("/api/v1/market-data")
async def get_market_data():
    """Get market data for all symbols"""
    market_summary = {}
    
    for symbol, book in order_books.items():
        trades_24h = [t for t in trades.values() 
                     if t["symbol"] == symbol and 
                     datetime.fromisoformat(t["timestamp"]) > 
                     datetime.utcnow() - timedelta(hours=24)]
        
        market_summary[symbol] = {
            "last_price": book["last_price"],
            "volume_24h": book["volume_24h"],
            "high_24h": book["high_24h"],
            "low_24h": book["low_24h"],
            "trades_count_24h": len(trades_24h),
            "bid_price": max(book["bids"].keys()) if book["bids"] else None,
            "ask_price": min(book["asks"].keys()) if book["asks"] else None
        }
    
    return {
        "market_data": market_summary,
        "total_symbols": len(market_summary),
        "generated_at": datetime.utcnow().isoformat()
    }

@app.get("/api/v1/engine/stats")
async def get_engine_stats():
    """Get trading engine statistics"""
    total_orders = len(orders)
    total_trades = len(trades)
    total_volume = sum(t["quantity"] * t["price"] for t in trades.values())
    
    orders_by_status = defaultdict(int)
    for order in orders.values():
        orders_by_status[order["status"]] += 1
    
    trades_by_symbol = defaultdict(int)
    for trade in trades.values():
        trades_by_symbol[trade["symbol"]] += 1
    
    return {
        "engine_stats": {
            "total_orders": total_orders,
            "total_trades": total_trades,
            "total_volume": total_volume,
            "orders_by_status": dict(orders_by_status),
            "trades_by_symbol": dict(trades_by_symbol),
            "active_order_books": len(order_books),
            "uptime": "running"
        },
        "generated_at": datetime.utcnow().isoformat()
    }

# Core trading engine logic
async def process_order(order: Dict) -> List[Dict]:
    """Process an order and execute trades"""
    symbol = order["symbol"]
    book = order_books[symbol]
    trades_executed = []
    
    if order["type"] == "market":
        trades_executed = await process_market_order(order, book)
    else:
        trades_executed = await process_limit_order(order, book)
    
    # Update market data
    update_market_data(symbol, trades_executed)
    
    return trades_executed

async def process_market_order(order: Dict, book: Dict) -> List[Dict]:
    """Process a market order"""
    trades_executed = []
    
    if order["side"] == "buy":
        # Match against asks (sell orders)
        ask_prices = sorted(book["asks"].keys())
        
        for price in ask_prices:
            if order["remaining_quantity"] <= 0:
                break
            
            orders_at_price = book["asks"][price][:]
            for matching_order in orders_at_price:
                if order["remaining_quantity"] <= 0:
                    break
                
                trade = await execute_trade(order, matching_order, price)
                if trade:
                    trades_executed.append(trade)
    
    else:  # sell order
        # Match against bids (buy orders)
        bid_prices = sorted(book["bids"].keys(), reverse=True)
        
        for price in bid_prices:
            if order["remaining_quantity"] <= 0:
                break
            
            orders_at_price = book["bids"][price][:]
            for matching_order in orders_at_price:
                if order["remaining_quantity"] <= 0:
                    break
                
                trade = await execute_trade(order, matching_order, price)
                if trade:
                    trades_executed.append(trade)
    
    return trades_executed

async def process_limit_order(order: Dict, book: Dict) -> List[Dict]:
    """Process a limit order"""
    trades_executed = []
    
    if order["side"] == "buy":
        # Match against asks at or below the limit price
        ask_prices = sorted([p for p in book["asks"].keys() if float(p) <= order["price"]])
        
        for price in ask_prices:
            if order["remaining_quantity"] <= 0:
                break
            
            orders_at_price = book["asks"][price][:]
            for matching_order in orders_at_price:
                if order["remaining_quantity"] <= 0:
                    break
                
                trade = await execute_trade(order, matching_order, price)
                if trade:
                    trades_executed.append(trade)
        
        # Add remaining quantity to order book
        if order["remaining_quantity"] > 0:
            price_key = str(order["price"])
            book["bids"][price_key].append(order)
    
    else:  # sell order
        # Match against bids at or above the limit price
        bid_prices = sorted([p for p in book["bids"].keys() if float(p) >= order["price"]], reverse=True)
        
        for price in bid_prices:
            if order["remaining_quantity"] <= 0:
                break
            
            orders_at_price = book["bids"][price][:]
            for matching_order in orders_at_price:
                if order["remaining_quantity"] <= 0:
                    break
                
                trade = await execute_trade(order, matching_order, price)
                if trade:
                    trades_executed.append(trade)
        
        # Add remaining quantity to order book
        if order["remaining_quantity"] > 0:
            price_key = str(order["price"])
            book["asks"][price_key].append(order)
    
    return trades_executed

async def execute_trade(order1: Dict, order2: Dict, price: float) -> Optional[Dict]:
    """Execute a trade between two orders"""
    # Determine trade quantity
    trade_quantity = min(order1["remaining_quantity"], order2["remaining_quantity"])
    
    if trade_quantity <= 0:
        return None
    
    # Create trade record
    trade_id = f"trade_{int(datetime.utcnow().timestamp())}_{len(trades)}"
    
    trade = {
        "trade_id": trade_id,
        "symbol": order1["symbol"],
        "buy_order_id": order1["order_id"] if order1["side"] == "buy" else order2["order_id"],
        "sell_order_id": order2["order_id"] if order2["side"] == "sell" else order1["order_id"],
        "quantity": trade_quantity,
        "price": price,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    trades[trade_id] = trade
    
    # Update orders
    for order in [order1, order2]:
        order["filled_quantity"] += trade_quantity
        order["remaining_quantity"] -= trade_quantity
        
        if order["remaining_quantity"] <= 0:
            order["status"] = "filled"
            order["filled_at"] = trade["timestamp"]
        else:
            order["status"] = "partially_filled"
        
        # Update average price
        if order["average_price"] is None:
            order["average_price"] = price
        else:
            total_value = order["average_price"] * (order["filled_quantity"] - trade_quantity) + price * trade_quantity
            order["average_price"] = total_value / order["filled_quantity"]
    
    # Remove filled orders from order book
    symbol = order1["symbol"]
    book = order_books[symbol]
    price_key = str(price)
    
    for order in [order1, order2]:
        if order["remaining_quantity"] <= 0:
            if order["side"] == "buy" and price_key in book["bids"]:
                book["bids"][price_key] = [o for o in book["bids"][price_key] if o["order_id"] != order["order_id"]]
                if not book["bids"][price_key]:
                    del book["bids"][price_key]
            elif order["side"] == "sell" and price_key in book["asks"]:
                book["asks"][price_key] = [o for o in book["asks"][price_key] if o["order_id"] != order["order_id"]]
                if not book["asks"][price_key]:
                    del book["asks"][price_key]
    
    logger.info(f"Trade executed: {trade_id} - {trade_quantity} @ {price}")
    
    return trade

def update_market_data(symbol: str, trades_executed: List[Dict]):
    """Update market data after trades"""
    if not trades_executed:
        return
    
    book = order_books[symbol]
    
    # Update last price
    last_trade = trades_executed[-1]
    book["last_price"] = last_trade["price"]
    
    # Update 24h high/low
    trades_24h = [t for t in trades.values() 
                 if t["symbol"] == symbol and 
                 datetime.fromisoformat(t["timestamp"]) > 
                 datetime.utcnow() - timedelta(hours=24)]
    
    if trades_24h:
        prices = [t["price"] for t in trades_24h]
        book["high_24h"] = max(prices)
        book["low_24h"] = min(prices)
        book["volume_24h"] = sum(t["quantity"] for t in trades_24h)

# Background task for market data simulation
async def simulate_market_activity():
    """Background task to simulate market activity"""
    while True:
        await asyncio.sleep(60)  # Simulate activity every minute
        
        # Create some random market orders for demo
        if len(order_books) > 0:
            import random
            
            for symbol in list(order_books.keys())[:3]:  # Limit to 3 symbols
                if random.random() < 0.3:  # 30% chance of market activity
                    # Create random market order
                    side = random.choice(["buy", "sell"])
                    quantity = random.uniform(10, 1000)
                    
                    order_id = f"sim_order_{int(datetime.utcnow().timestamp())}"
                    order = Order(
                        order_id=order_id,
                        symbol=symbol,
                        side=side,
                        type="market",
                        quantity=quantity,
                        user_id="sim_user",
                        timestamp=datetime.utcnow()
                    )
                    
                    order_data = {
                        "order_id": order.order_id,
                        "symbol": order.symbol,
                        "side": order.side,
                        "type": order.type,
                        "quantity": order.quantity,
                        "remaining_quantity": order.quantity,
                        "price": order.price,
                        "user_id": order.user_id,
                        "timestamp": order.timestamp.isoformat(),
                        "status": "open",
                        "filled_quantity": 0.0,
                        "average_price": None
                    }
                    
                    orders[order_id] = order_data
                    await process_order(order_data)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8012, log_level="info")
