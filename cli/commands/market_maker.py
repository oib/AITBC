"""Market making commands for AITBC CLI"""

import click
import json
import uuid
import httpx
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, UTC, timedelta
from utils import output, error, success, warning


@click.group()
def market_maker():
    """Market making bot management commands"""
    pass


@market_maker.command()
@click.option("--exchange", required=True, help="Exchange name")
@click.option("--pair", required=True, help="Trading pair symbol (e.g., AITBC/BTC)")
@click.option("--spread", type=float, default=0.005, help="Bid-ask spread (as percentage)")
@click.option("--depth", type=float, default=1000000, help="Order book depth amount")
@click.option("--max-order-size", type=float, default=1000, help="Maximum order size")
@click.option("--min-order-size", type=float, default=10, help="Minimum order size")
@click.option("--target-inventory", type=float, default=50000, help="Target inventory balance")
@click.option("--rebalance-threshold", type=float, default=0.1, help="Inventory rebalance threshold")
@click.option("--description", help="Bot description")
@click.pass_context
def create(ctx, exchange: str, pair: str, spread: float, depth: float, max_order_size: float, min_order_size: float, target_inventory: float, rebalance_threshold: float, description: Optional[str]):
    """Create a new market making bot"""
    
    # Generate unique bot ID
    bot_id = f"mm_{exchange.lower()}_{pair.replace('/', '_')}_{str(uuid.uuid4())[:8]}"
    
    # Create bot configuration
    bot_config = {
        "bot_id": bot_id,
        "exchange": exchange,
        "pair": pair,
        "status": "stopped",
        "strategy": "basic_market_making",
        "config": {
            "spread": spread,
            "depth": depth,
            "max_order_size": max_order_size,
            "min_order_size": min_order_size,
            "target_inventory": target_inventory,
            "rebalance_threshold": rebalance_threshold
        },
        "performance": {
            "total_trades": 0,
            "total_volume": 0.0,
            "total_profit": 0.0,
            "inventory_value": 0.0,
            "orders_placed": 0,
            "orders_filled": 0
        },
        "created_at": datetime.now(datetime.UTC).isoformat(),
        "last_updated": None,
        "description": description or f"Market making bot for {pair} on {exchange}",
        "current_orders": [],
        "inventory": {
            "base_asset": 0.0,
            "quote_asset": target_inventory
        }
    }
    
    # Store bot configuration
    bots_file = Path.home() / ".aitbc" / "market_makers.json"
    bots_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing bots
    bots = {}
    if bots_file.exists():
        with open(bots_file, 'r') as f:
            bots = json.load(f)
    
    # Add new bot
    bots[bot_id] = bot_config
    
    # Save bots
    with open(bots_file, 'w') as f:
        json.dump(bots, f, indent=2)
    
    success(f"Market making bot created: {bot_id}")
    output({
        "bot_id": bot_id,
        "exchange": exchange,
        "pair": pair,
        "status": "created",
        "spread": spread,
        "depth": depth,
        "created_at": bot_config["created_at"]
    })


@market_maker.command()
@click.option("--bot-id", required=True, help="Bot ID to configure")
@click.option("--spread", type=float, help="New bid-ask spread")
@click.option("--depth", type=float, help="New order book depth")
@click.option("--max-order-size", type=float, help="New maximum order size")
@click.option("--target-inventory", type=float, help="New target inventory")
@click.option("--rebalance-threshold", type=float, help="New rebalance threshold")
@click.pass_context
def config(ctx, bot_id: str, spread: Optional[float], depth: Optional[float], max_order_size: Optional[float], target_inventory: Optional[float], rebalance_threshold: Optional[float]):
    """Configure market making bot parameters"""
    
    # Load bots
    bots_file = Path.home() / ".aitbc" / "market_makers.json"
    if not bots_file.exists():
        error("No market making bots found.")
        return
    
    with open(bots_file, 'r') as f:
        bots = json.load(f)
    
    if bot_id not in bots:
        error(f"Bot '{bot_id}' not found.")
        return
    
    bot = bots[bot_id]
    
    # Update configuration
    config_updates = {}
    if spread is not None:
        bot["config"]["spread"] = spread
        config_updates["spread"] = spread
    if depth is not None:
        bot["config"]["depth"] = depth
        config_updates["depth"] = depth
    if max_order_size is not None:
        bot["config"]["max_order_size"] = max_order_size
        config_updates["max_order_size"] = max_order_size
    if target_inventory is not None:
        bot["config"]["target_inventory"] = target_inventory
        config_updates["target_inventory"] = target_inventory
    if rebalance_threshold is not None:
        bot["config"]["rebalance_threshold"] = rebalance_threshold
        config_updates["rebalance_threshold"] = rebalance_threshold
    
    if not config_updates:
        error("No configuration updates provided.")
        return
    
    # Update timestamp
    bot["last_updated"] = datetime.now(datetime.UTC).isoformat()
    
    # Save bots
    with open(bots_file, 'w') as f:
        json.dump(bots, f, indent=2)
    
    success(f"Bot '{bot_id}' configuration updated")
    output({
        "bot_id": bot_id,
        "config_updates": config_updates,
        "updated_at": bot["last_updated"]
    })


@market_maker.command()
@click.option("--bot-id", required=True, help="Bot ID to start")
@click.option("--dry-run", is_flag=True, help="Run in simulation mode without real orders")
@click.pass_context
def start(ctx, bot_id: str, dry_run: bool):
    """Start a market making bot"""
    
    # Load bots
    bots_file = Path.home() / ".aitbc" / "market_makers.json"
    if not bots_file.exists():
        error("No market making bots found.")
        return
    
    with open(bots_file, 'r') as f:
        bots = json.load(f)
    
    if bot_id not in bots:
        error(f"Bot '{bot_id}' not found.")
        return
    
    bot = bots[bot_id]
    
    # Check if bot is already running
    if bot["status"] == "running":
        warning(f"Bot '{bot_id}' is already running.")
        return
    
    # Update bot status
    bot["status"] = "running" if not dry_run else "simulation"
    bot["started_at"] = datetime.now(datetime.UTC).isoformat()
    bot["last_updated"] = datetime.now(datetime.UTC).isoformat()
    bot["dry_run"] = dry_run
    
    # Initialize performance tracking for this run
    bot["current_run"] = {
        "started_at": bot["started_at"],
        "orders_placed": 0,
        "orders_filled": 0,
        "total_volume": 0.0,
        "total_profit": 0.0
    }
    
    # Save bots
    with open(bots_file, 'w') as f:
        json.dump(bots, f, indent=2)
    
    mode = "simulation" if dry_run else "live"
    success(f"Bot '{bot_id}' started in {mode} mode")
    output({
        "bot_id": bot_id,
        "status": bot["status"],
        "mode": mode,
        "started_at": bot["started_at"],
        "exchange": bot["exchange"],
        "pair": bot["pair"]
    })


@market_maker.command()
@click.option("--bot-id", required=True, help="Bot ID to stop")
@click.pass_context
def stop(ctx, bot_id: str):
    """Stop a market making bot"""
    
    # Load bots
    bots_file = Path.home() / ".aitbc" / "market_makers.json"
    if not bots_file.exists():
        error("No market making bots found.")
        return
    
    with open(bots_file, 'r') as f:
        bots = json.load(f)
    
    if bot_id not in bots:
        error(f"Bot '{bot_id}' not found.")
        return
    
    bot = bots[bot_id]
    
    # Check if bot is running
    if bot["status"] not in ["running", "simulation"]:
        warning(f"Bot '{bot_id}' is not currently running.")
        return
    
    # Update bot status
    bot["status"] = "stopped"
    bot["stopped_at"] = datetime.now(datetime.UTC).isoformat()
    bot["last_updated"] = datetime.now(datetime.UTC).isoformat()
    
    # Cancel all current orders (simulation)
    bot["current_orders"] = []
    
    # Save bots
    with open(bots_file, 'w') as f:
        json.dump(bots, f, indent=2)
    
    success(f"Bot '{bot_id}' stopped")
    output({
        "bot_id": bot_id,
        "status": "stopped",
        "stopped_at": bot["stopped_at"],
        "final_performance": bot.get("current_run", {})
    })


@market_maker.command()
@click.option("--bot-id", help="Specific bot ID to check")
@click.option("--exchange", help="Filter by exchange")
@click.option("--pair", help="Filter by trading pair")
@click.pass_context
def performance(ctx, bot_id: Optional[str], exchange: Optional[str], pair: Optional[str]):
    """Get performance metrics for market making bots"""
    
    # Load bots
    bots_file = Path.home() / ".aitbc" / "market_makers.json"
    if not bots_file.exists():
        error("No market making bots found.")
        return
    
    with open(bots_file, 'r') as f:
        bots = json.load(f)
    
    # Filter bots
    performance_data = {}
    
    for current_bot_id, bot in bots.items():
        if bot_id and current_bot_id != bot_id:
            continue
        if exchange and bot["exchange"] != exchange:
            continue
        if pair and bot["pair"] != pair:
            continue
        
        # Calculate performance metrics
        perf = bot.get("performance", {})
        current_run = bot.get("current_run", {})
        
        bot_performance = {
            "bot_id": current_bot_id,
            "exchange": bot["exchange"],
            "pair": bot["pair"],
            "status": bot["status"],
            "created_at": bot["created_at"],
            "total_trades": perf.get("total_trades", 0),
            "total_volume": perf.get("total_volume", 0.0),
            "total_profit": perf.get("total_profit", 0.0),
            "orders_placed": perf.get("orders_placed", 0),
            "orders_filled": perf.get("orders_filled", 0),
            "fill_rate": (perf.get("orders_filled", 0) / max(perf.get("orders_placed", 1), 1)) * 100,
            "current_inventory": bot.get("inventory", {}),
            "current_orders": len(bot.get("current_orders", [])),
            "strategy": bot.get("strategy", "unknown"),
            "config": bot.get("config", {})
        }
        
        # Add current run data if available
        if current_run:
            bot_performance["current_run"] = current_run
            if "started_at" in current_run:
                start_time = datetime.fromisoformat(current_run["started_at"].replace('Z', '+00:00'))
                runtime = datetime.now(datetime.UTC) - start_time
                bot_performance["run_time_hours"] = runtime.total_seconds() / 3600
        
        performance_data[current_bot_id] = bot_performance
    
    if not performance_data:
        error("No market making bots found matching the criteria.")
        return
    
    output({
        "performance_data": performance_data,
        "total_bots": len(performance_data),
        "generated_at": datetime.now(datetime.UTC).isoformat()
    })


@market_maker.command()
@click.pass_context
def list(ctx):
    """List all market making bots"""
    
    # Load bots
    bots_file = Path.home() / ".aitbc" / "market_makers.json"
    if not bots_file.exists():
        warning("No market making bots found.")
        return
    
    with open(bots_file, 'r') as f:
        bots = json.load(f)
    
    # Format bot list
    bot_list = []
    for bot_id, bot in bots.items():
        bot_info = {
            "bot_id": bot_id,
            "exchange": bot["exchange"],
            "pair": bot["pair"],
            "status": bot["status"],
            "strategy": bot.get("strategy", "unknown"),
            "created_at": bot["created_at"],
            "last_updated": bot.get("last_updated"),
            "total_trades": bot.get("performance", {}).get("total_trades", 0),
            "current_orders": len(bot.get("current_orders", []))
        }
        bot_list.append(bot_info)
    
    output({
        "market_makers": bot_list,
        "total_bots": len(bot_list),
        "running_bots": len([b for b in bot_list if b["status"] in ["running", "simulation"]]),
        "stopped_bots": len([b for b in bot_list if b["status"] == "stopped"])
    })


@market_maker.command()
@click.argument("bot_id")
@click.pass_context
def status(ctx, bot_id: str):
    """Get detailed status of a specific market making bot"""
    
    # Load bots
    bots_file = Path.home() / ".aitbc" / "market_makers.json"
    if not bots_file.exists():
        error("No market making bots found.")
        return
    
    with open(bots_file, 'r') as f:
        bots = json.load(f)
    
    if bot_id not in bots:
        error(f"Bot '{bot_id}' not found.")
        return
    
    bot = bots[bot_id]
    
    # Calculate uptime if running
    uptime_hours = None
    if bot["status"] in ["running", "simulation"] and "started_at" in bot:
        start_time = datetime.fromisoformat(bot["started_at"].replace('Z', '+00:00'))
        uptime = datetime.now(datetime.UTC) - start_time
        uptime_hours = uptime.total_seconds() / 3600
    
    output({
        "bot_id": bot_id,
        "exchange": bot["exchange"],
        "pair": bot["pair"],
        "status": bot["status"],
        "strategy": bot.get("strategy", "unknown"),
        "config": bot.get("config", {}),
        "performance": bot.get("performance", {}),
        "inventory": bot.get("inventory", {}),
        "current_orders": bot.get("current_orders", []),
        "created_at": bot["created_at"],
        "last_updated": bot.get("last_updated"),
        "started_at": bot.get("started_at"),
        "stopped_at": bot.get("stopped_at"),
        "uptime_hours": uptime_hours,
        "dry_run": bot.get("dry_run", False),
        "description": bot.get("description")
    })


@market_maker.command()
@click.argument("bot_id")
@click.pass_context
def remove(ctx, bot_id: str):
    """Remove a market making bot"""
    
    # Load bots
    bots_file = Path.home() / ".aitbc" / "market_makers.json"
    if not bots_file.exists():
        error("No market making bots found.")
        return
    
    with open(bots_file, 'r') as f:
        bots = json.load(f)
    
    if bot_id not in bots:
        error(f"Bot '{bot_id}' not found.")
        return
    
    bot = bots[bot_id]
    
    # Check if bot is running
    if bot["status"] in ["running", "simulation"]:
        error(f"Cannot remove bot '{bot_id}' while it is running. Stop it first.")
        return
    
    # Remove bot
    del bots[bot_id]
    
    # Save bots
    with open(bots_file, 'w') as f:
        json.dump(bots, f, indent=2)
    
    success(f"Market making bot '{bot_id}' removed")
    output({
        "bot_id": bot_id,
        "status": "removed",
        "exchange": bot["exchange"],
        "pair": bot["pair"]
    })


@click.group()
def market_maker():
    """Market making operations"""
    pass


@market_maker.command()
@click.option("--exchange", required=True, help="Exchange name (e.g., Binance, Coinbase)")
@click.option("--pair", required=True, help="Trading pair (e.g., AITBC/BTC)")
@click.option("--spread", type=float, default=0.001, help="Bid-ask spread (as percentage)")
@click.option("--depth", type=int, default=5, help="Order book depth levels")
@click.option("--base-balance", type=float, help="Base asset balance for market making")
@click.option("--quote-balance", type=float, help="Quote asset balance for market making")
@click.option("--min-order-size", type=float, help="Minimum order size")
@click.option("--max-order-size", type=float, help="Maximum order size")
@click.option("--strategy", default="simple", help="Market making strategy")
@click.pass_context
def create(ctx, exchange: str, pair: str, spread: float, depth: int,
           base_balance: Optional[float], quote_balance: Optional[float],
           min_order_size: Optional[float], max_order_size: Optional[float],
           strategy: str):
    """Create a new market making bot"""
    config = ctx.obj['config']
    
    bot_config = {
        "exchange": exchange,
        "pair": pair,
        "spread": spread,
        "depth": depth,
        "strategy": strategy,
        "status": "created"
    }
    
    if base_balance is not None:
        bot_config["base_balance"] = base_balance
    if quote_balance is not None:
        bot_config["quote_balance"] = quote_balance
    if min_order_size is not None:
        bot_config["min_order_size"] = min_order_size
    if max_order_size is not None:
        bot_config["max_order_size"] = max_order_size
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/api/v1/market-maker/create",
                json=bot_config,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Market maker bot created for '{pair}' on '{exchange}'!")
                success(f"Bot ID: {result.get('bot_id')}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to create market maker: {response.status_code}")
                if response.text:
                    error(f"Error details: {response.text}")
    except Exception as e:
        error(f"Network error: {e}")


@market_maker.command()
@click.option("--bot-id", required=True, help="Market maker bot ID")
@click.option("--spread", type=float, help="New bid-ask spread")
@click.option("--depth", type=int, help="New order book depth")
@click.option("--base-balance", type=float, help="New base asset balance")
@click.option("--quote-balance", type=float, help="New quote asset balance")
@click.option("--min-order-size", type=float, help="New minimum order size")
@click.option("--max-order-size", type=float, help="New maximum order size")
@click.option("--strategy", help="New market making strategy")
@click.pass_context
def config(ctx, bot_id: str, spread: Optional[float], depth: Optional[int],
           base_balance: Optional[float], quote_balance: Optional[float],
           min_order_size: Optional[float], max_order_size: Optional[float],
           strategy: Optional[str]):
    """Configure market maker bot settings"""
    config = ctx.obj['config']
    
    updates = {}
    if spread is not None:
        updates["spread"] = spread
    if depth is not None:
        updates["depth"] = depth
    if base_balance is not None:
        updates["base_balance"] = base_balance
    if quote_balance is not None:
        updates["quote_balance"] = quote_balance
    if min_order_size is not None:
        updates["min_order_size"] = min_order_size
    if max_order_size is not None:
        updates["max_order_size"] = max_order_size
    if strategy is not None:
        updates["strategy"] = strategy
    
    if not updates:
        error("No configuration updates provided")
        return
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/api/v1/market-maker/config/{bot_id}",
                json=updates,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Market maker {bot_id} configured successfully!")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to configure market maker: {response.status_code}")
                if response.text:
                    error(f"Error details: {response.text}")
    except Exception as e:
        error(f"Network error: {e}")


@market_maker.command()
@click.option("--bot-id", required=True, help="Market maker bot ID")
@click.option("--dry-run", is_flag=True, help="Test run without executing real trades")
@click.pass_context
def start(ctx, bot_id: str, dry_run: bool):
    """Start market maker bot"""
    config = ctx.obj['config']
    
    start_data = {
        "dry_run": dry_run
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/api/v1/market-maker/start/{bot_id}",
                json=start_data,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                mode = " (dry run)" if dry_run else ""
                success(f"Market maker {bot_id} started{mode}!")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to start market maker: {response.status_code}")
                if response.text:
                    error(f"Error details: {response.text}")
    except Exception as e:
        error(f"Network error: {e}")


@market_maker.command()
@click.option("--bot-id", required=True, help="Market maker bot ID")
@click.pass_context
def stop(ctx, bot_id: str):
    """Stop market maker bot"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/api/v1/market-maker/stop/{bot_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Market maker {bot_id} stopped!")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to stop market maker: {response.status_code}")
                if response.text:
                    error(f"Error details: {response.text}")
    except Exception as e:
        error(f"Network error: {e}")


@market_maker.command()
@click.option("--bot-id", help="Specific bot ID to check")
@click.option("--exchange", help="Filter by exchange")
@click.option("--pair", help="Filter by trading pair")
@click.option("--status", help="Filter by status (running, stopped, created)")
@click.pass_context
def performance(ctx, bot_id: Optional[str], exchange: Optional[str], 
                pair: Optional[str], status: Optional[str]):
    """Get market maker performance analytics"""
    config = ctx.obj['config']
    
    params = {}
    if bot_id:
        params["bot_id"] = bot_id
    if exchange:
        params["exchange"] = exchange
    if pair:
        params["pair"] = pair
    if status:
        params["status"] = status
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/api/v1/market-maker/performance",
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                performance_data = response.json()
                success("Market maker performance:")
                output(performance_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get performance data: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@market_maker.command()
@click.option("--bot-id", help="Specific bot ID to list")
@click.option("--exchange", help="Filter by exchange")
@click.option("--pair", help="Filter by trading pair")
@click.option("--status", help="Filter by status")
@click.pass_context
def list(ctx, bot_id: Optional[str], exchange: Optional[str], 
         pair: Optional[str], status: Optional[str]):
    """List market maker bots"""
    config = ctx.obj['config']
    
    params = {}
    if bot_id:
        params["bot_id"] = bot_id
    if exchange:
        params["exchange"] = exchange
    if pair:
        params["pair"] = pair
    if status:
        params["status"] = status
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/api/v1/market-maker/list",
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                bots = response.json()
                success("Market maker bots:")
                output(bots, ctx.obj['output_format'])
            else:
                error(f"Failed to list market makers: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@market_maker.command()
@click.option("--bot-id", required=True, help="Market maker bot ID")
@click.option("--hours", type=int, default=24, help="Hours of history to retrieve")
@click.pass_context
def history(ctx, bot_id: str, hours: int):
    """Get market maker trading history"""
    config = ctx.obj['config']
    
    params = {
        "hours": hours
    }
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/api/v1/market-maker/history/{bot_id}",
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                history_data = response.json()
                success(f"Market maker {bot_id} history (last {hours} hours):")
                output(history_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get market maker history: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@market_maker.command()
@click.option("--bot-id", required=True, help="Market maker bot ID")
@click.pass_context
def status(ctx, bot_id: str):
    """Get market maker bot status"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/api/v1/market-maker/status/{bot_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                status_data = response.json()
                success(f"Market maker {bot_id} status:")
                output(status_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get market maker status: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@market_maker.command()
@click.pass_context
def strategies(ctx):
    """List available market making strategies"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/api/v1/market-maker/strategies",
                timeout=10
            )
            
            if response.status_code == 200:
                strategies = response.json()
                success("Available market making strategies:")
                output(strategies, ctx.obj['output_format'])
            else:
                error(f"Failed to list strategies: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
