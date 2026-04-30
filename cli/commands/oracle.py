"""Oracle price discovery commands for AITBC CLI"""

import click
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, UTC, timedelta
from utils import output, error, success, warning


@click.group()
def oracle():
    """Oracle price discovery and management commands"""
    pass


@oracle.command()
@click.option("--pair", required=True, help="Trading pair symbol (e.g., AITBC/BTC)")
@click.option("--price", type=float, required=True, help="Price to set")
@click.option("--source", default="creator", help="Price source (creator, market, oracle)")
@click.option("--confidence", type=float, default=1.0, help="Confidence level (0.0-1.0)")
@click.option("--description", help="Price update description")
@click.pass_context
def set_price(ctx, pair: str, price: float, source: str, confidence: float, description: Optional[str]):
    """Set price for a trading pair"""
    
    # Create oracle data structure
    oracle_file = Path.home() / ".aitbc" / "oracle_prices.json"
    oracle_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing oracle data
    oracle_data = {}
    if oracle_file.exists():
        with open(oracle_file, 'r') as f:
            oracle_data = json.load(f)
    
    # Create price entry
    price_entry = {
        "pair": pair,
        "price": price,
        "source": source,
        "confidence": confidence,
        "description": description or f"Price set by {source}",
        "timestamp": datetime.now(datetime.UTC).isoformat(),
        "volume": 0.0,
        "spread": 0.0
    }
    
    # Add to oracle data
    if pair not in oracle_data:
        oracle_data[pair] = {"history": [], "current_price": None, "last_updated": None}
    
    # Add to history
    oracle_data[pair]["history"].append(price_entry)
    # Keep only last 1000 entries
    if len(oracle_data[pair]["history"]) > 1000:
        oracle_data[pair]["history"] = oracle_data[pair]["history"][-1000:]
    
    # Update current price
    oracle_data[pair]["current_price"] = price_entry
    oracle_data[pair]["last_updated"] = price_entry["timestamp"]
    
    # Save oracle data
    with open(oracle_file, 'w') as f:
        json.dump(oracle_data, f, indent=2)
    
    success(f"Price set for {pair}: {price} (source: {source})")
    output({
        "pair": pair,
        "price": price,
        "source": source,
        "confidence": confidence,
        "timestamp": price_entry["timestamp"]
    })


@oracle.command()
@click.option("--pair", required=True, help="Trading pair symbol (e.g., AITBC/BTC)")
@click.option("--source", default="market", help="Price source (market, oracle, external)")
@click.option("--market-price", type=float, help="Market price to update from")
@click.option("--confidence", type=float, default=0.8, help="Confidence level for market price")
@click.option("--volume", type=float, default=0.0, help="Trading volume")
@click.option("--spread", type=float, default=0.0, help="Bid-ask spread")
@click.pass_context
def update_price(ctx, pair: str, source: str, market_price: Optional[float], confidence: float, volume: float, spread: float):
    """Update price from market data"""
    
    # For demo purposes, if no market price provided, simulate one
    if market_price is None:
        # Load current price and apply small random variation
        oracle_file = Path.home() / ".aitbc" / "oracle_prices.json"
        if oracle_file.exists():
            with open(oracle_file, 'r') as f:
                oracle_data = json.load(f)
            
            if pair in oracle_data and oracle_data[pair]["current_price"]:
                current_price = oracle_data[pair]["current_price"]["price"]
                # Simulate market movement (-2% to +2%)
                import random
                variation = random.uniform(-0.02, 0.02)
                market_price = round(current_price * (1 + variation), 8)
            else:
                market_price = 0.00001  # Default AITBC price
        else:
            market_price = 0.00001  # Default AITBC price
    
    # Use set_price logic
    ctx.invoke(set_price, 
              pair=pair, 
              price=market_price, 
              source=source, 
              confidence=confidence,
              description=f"Market price update from {source}")
    
    # Update additional market data
    oracle_file = Path.home() / ".aitbc" / "oracle_prices.json"
    with open(oracle_file, 'r') as f:
        oracle_data = json.load(f)
    
    # Update market-specific fields
    oracle_data[pair]["current_price"]["volume"] = volume
    oracle_data[pair]["current_price"]["spread"] = spread
    oracle_data[pair]["current_price"]["market_data"] = True
    
    # Save updated data
    with open(oracle_file, 'w') as f:
        json.dump(oracle_data, f, indent=2)
    
    success(f"Market price updated for {pair}: {market_price}")
    output({
        "pair": pair,
        "market_price": market_price,
        "source": source,
        "volume": volume,
        "spread": spread
    })


@oracle.command()
@click.option("--pair", help="Trading pair symbol (e.g., AITBC/BTC)")
@click.option("--days", type=int, default=7, help="Number of days of history to show")
@click.option("--limit", type=int, default=100, help="Maximum number of records to show")
@click.option("--source", help="Filter by price source")
@click.pass_context
def price_history(ctx, pair: Optional[str], days: int, limit: int, source: Optional[str]):
    """Get price history for trading pairs"""
    
    oracle_file = Path.home() / ".aitbc" / "oracle_prices.json"
    if not oracle_file.exists():
        warning("No price data available.")
        return
    
    with open(oracle_file, 'r') as f:
        oracle_data = json.load(f)
    
    # Filter data
    history_data = {}
    cutoff_time = datetime.now(datetime.UTC) - timedelta(days=days)
    
    for pair_name, pair_data in oracle_data.items():
        if pair and pair_name != pair:
            continue
            
        # Filter history by date and source
        filtered_history = []
        for entry in pair_data.get("history", []):
            entry_time = datetime.fromisoformat(entry["timestamp"].replace('Z', '+00:00'))
            if entry_time >= cutoff_time:
                if source and entry.get("source") != source:
                    continue
                filtered_history.append(entry)
        
        # Limit results
        filtered_history = filtered_history[-limit:]
        
        if filtered_history:
            history_data[pair_name] = {
                "current_price": pair_data.get("current_price"),
                "last_updated": pair_data.get("last_updated"),
                "history": filtered_history,
                "total_entries": len(filtered_history)
            }
    
    if not history_data:
        error("No price history found for the specified criteria.")
        return
    
    output({
        "price_history": history_data,
        "filter_criteria": {
            "pair": pair or "all",
            "days": days,
            "limit": limit,
            "source": source or "all"
        },
        "generated_at": datetime.now(datetime.UTC).isoformat()
    })


@oracle.command()
@click.option("--pairs", help="Comma-separated list of pairs to include (e.g., AITBC/BTC,AITBC/ETH)")
@click.option("--interval", type=int, default=60, help="Update interval in seconds")
@click.option("--sources", help="Comma-separated list of sources to include")
@click.pass_context
def price_feed(ctx, pairs: Optional[str], interval: int, sources: Optional[str]):
    """Get real-time price feed for multiple pairs"""
    
    oracle_file = Path.home() / ".aitbc" / "oracle_prices.json"
    if not oracle_file.exists():
        warning("No price data available.")
        return
    
    with open(oracle_file, 'r') as f:
        oracle_data = json.load(f)
    
    # Parse pairs list
    pair_list = None
    if pairs:
        pair_list = [p.strip() for p in pairs.split(',')]
    
    # Parse sources list
    source_list = None
    if sources:
        source_list = [s.strip() for s in sources.split(',')]
    
    # Build price feed
    feed_data = {}
    
    for pair_name, pair_data in oracle_data.items():
        if pair_list and pair_name not in pair_list:
            continue
            
        current_price = pair_data.get("current_price")
        if not current_price:
            continue
            
        # Filter by source if specified
        if source_list and current_price.get("source") not in source_list:
            continue
        
        feed_data[pair_name] = {
            "price": current_price["price"],
            "source": current_price["source"],
            "confidence": current_price.get("confidence", 1.0),
            "timestamp": current_price["timestamp"],
            "volume": current_price.get("volume", 0.0),
            "spread": current_price.get("spread", 0.0),
            "description": current_price.get("description")
        }
    
    if not feed_data:
        error("No price data available for the specified criteria.")
        return
    
    output({
        "price_feed": feed_data,
        "feed_config": {
            "pairs": pair_list or "all",
            "interval": interval,
            "sources": source_list or "all"
        },
        "generated_at": datetime.now(datetime.UTC).isoformat(),
        "total_pairs": len(feed_data)
    })
    
    if interval > 0:
        warning(f"Price feed configured for {interval}-second intervals.")


@oracle.command()
@click.option("--pair", help="Specific trading pair to analyze")
@click.option("--hours", type=int, default=24, help="Time window in hours for analysis")
@click.pass_context
def analyze(ctx, pair: Optional[str], hours: int):
    """Analyze price trends and volatility"""
    
    oracle_file = Path.home() / ".aitbc" / "oracle_prices.json"
    if not oracle_file.exists():
        error("No price data available for analysis.")
        return
    
    with open(oracle_file, 'r') as f:
        oracle_data = json.load(f)
    
    cutoff_time = datetime.now(datetime.UTC) - timedelta(hours=hours)
    analysis_results = {}
    
    for pair_name, pair_data in oracle_data.items():
        if pair and pair_name != pair:
            continue
            
        # Get recent price history
        recent_prices = []
        for entry in pair_data.get("history", []):
            entry_time = datetime.fromisoformat(entry["timestamp"].replace('Z', '+00:00'))
            if entry_time >= cutoff_time:
                recent_prices.append(entry["price"])
        
        if len(recent_prices) < 2:
            continue
        
        # Calculate statistics
        prices = sorted(recent_prices)
        current_price = recent_prices[-1]
        
        analysis = {
            "pair": pair_name,
            "time_window_hours": hours,
            "data_points": len(recent_prices),
            "current_price": current_price,
            "min_price": min(prices),
            "max_price": max(prices),
            "price_range": max(prices) - min(prices),
            "avg_price": sum(prices) / len(prices),
            "price_change": current_price - recent_prices[0],
            "price_change_percent": ((current_price - recent_prices[0]) / recent_prices[0]) * 100 if recent_prices[0] > 0 else 0
        }
        
        # Calculate volatility (standard deviation)
        mean_price = analysis["avg_price"]
        variance = sum((p - mean_price) ** 2 for p in recent_prices) / len(recent_prices)
        analysis["volatility"] = variance ** 0.5
        analysis["volatility_percent"] = (analysis["volatility"] / mean_price) * 100 if mean_price > 0 else 0
        
        analysis_results[pair_name] = analysis
    
    if not analysis_results:
        error("No sufficient data for analysis.")
        return
    
    output({
        "analysis": analysis_results,
        "analysis_config": {
            "pair": pair or "all",
            "time_window_hours": hours
        },
        "generated_at": datetime.now(datetime.UTC).isoformat()
    })


@oracle.command()
@click.pass_context
def status(ctx):
    """Get oracle system status"""
    
    oracle_file = Path.home() / ".aitbc" / "oracle_prices.json"
    
    if not oracle_file.exists():
        output({
            "status": "no_data",
            "message": "No price data available",
            "total_pairs": 0,
            "last_update": None
        })
        return
    
    with open(oracle_file, 'r') as f:
        oracle_data = json.load(f)
    
    # Calculate status metrics
    total_pairs = len(oracle_data)
    active_pairs = 0
    total_updates = 0
    last_update = None
    
    for pair_name, pair_data in oracle_data.items():
        if pair_data.get("current_price"):
            active_pairs += 1
            total_updates += len(pair_data.get("history", []))
            
            pair_last_update = pair_data.get("last_updated")
            if pair_last_update:
                pair_time = datetime.fromisoformat(pair_last_update.replace('Z', '+00:00'))
                if not last_update or pair_time > last_update:
                    last_update = pair_time
    
    # Get sources
    sources = set()
    for pair_data in oracle_data.values():
        current = pair_data.get("current_price")
        if current:
            sources.add(current.get("source", "unknown"))
    
    output({
        "status": "active",
        "total_pairs": total_pairs,
        "active_pairs": active_pairs,
        "total_updates": total_updates,
        "last_update": last_update.isoformat() if last_update else None,
        "sources": list(sources),
        "data_file": str(oracle_file)
    })


@oracle.command()
@click.argument("pair")
@click.pass_context
def get_price(ctx, pair: str):
    """Get current price for a specific pair"""
    
    oracle_file = Path.home() / ".aitbc" / "oracle_prices.json"
    if not oracle_file.exists():
        error("No price data available.")
        return
    
    with open(oracle_file, 'r') as f:
        oracle_data = json.load(f)
    
    if pair not in oracle_data:
        error(f"No price data available for {pair}.")
        return
    
    current_price = oracle_data[pair].get("current_price")
    if not current_price:
        error(f"No current price available for {pair}.")
        return
    
    output({
        "pair": pair,
        "price": current_price["price"],
        "source": current_price["source"],
        "confidence": current_price.get("confidence", 1.0),
        "timestamp": current_price["timestamp"],
        "volume": current_price.get("volume", 0.0),
        "spread": current_price.get("spread", 0.0),
        "description": current_price.get("description")
    })
